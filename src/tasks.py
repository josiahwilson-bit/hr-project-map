"""Task records with enforced lifecycle status transitions.

Lifecycle (v0.4): Proposed -> Assigned -> In Progress -> Submitted
-> Under Review -> Accepted -> Completed -> Verified, with
Under Review -> Rejected as a TERMINAL branch. The only backward move
allowed is Assigned -> Proposed.

Rejected is a recorded terminal outcome, not an invitation to rewrite
history: a rejected task can never be reopened. Rework is modeled as a
new task referencing the original via ``supersedes_task_id``
(see ``rework_task``).

Evidence gates (v0.2): a task cannot become Completed without at least one
evidence record, and cannot become Verified without independently verified
evidence (verifier != submitter). Review gates (v0.4): review transitions
go through ``review.*`` — reviewer identity required, rejection requires
a reason. The system records what happened; it does not manufacture
evidence that something happened.
"""

import uuid

from . import audit
from .db import connect, row_to_dict, validate_transition


def _get_task_row(conn, task_id):
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise ValueError(f"No task found with id {task_id!r}.")
    return row


def _has_evidence(conn, task_id):
    """True when at least one evidence record exists for the task."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM evidence WHERE task_id = ?", (task_id,)
    ).fetchone()
    return row["n"] > 0


def _has_independent_verification(conn, task_id):
    """True when the task has evidence verified by someone other than the
    submitter."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM evidence"
        " WHERE task_id = ? AND verified_by IS NOT NULL"
        " AND verified_by != submitted_by",
        (task_id,),
    ).fetchone()
    return row["n"] > 0


def _require_active_person(conn, person_id, action):
    row = conn.execute(
        "SELECT id, active FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"No person found with id {person_id!r}.")
    if not row["active"]:
        raise ValueError(
            f"Person {person_id!r} is inactive and cannot {action}."
        )


def add_task(db_path, project_id, title, assignee_id=None, due_date=None,
            milestone_id=None, supersedes_task_id=None):
    """Add a task to a project and return its id.

    Starts in ``Proposed`` unless ``assignee_id`` is given, in which case it
    starts in ``Assigned``. ``milestone_id`` is optional; when given, the
    milestone must exist and belong to the same project.
    ``supersedes_task_id`` is optional; when given, it must reference an
    existing task (used by ``rework_task`` to link rework to the original).
    """
    if not title or not title.strip():
        raise ValueError("title is required")
    conn = connect(db_path)
    try:
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if not project:
            raise ValueError(f"No project found with id {project_id!r}.")
        if milestone_id:
            ms = conn.execute(
                "SELECT id, project_id FROM milestones WHERE id = ?",
                (milestone_id,),
            ).fetchone()
            if not ms:
                raise ValueError(
                    f"No milestone found with id {milestone_id!r}."
                )
            if ms["project_id"] != project_id:
                raise ValueError(
                    "Milestone {!r} belongs to project {!r}, not {!r}.".format(milestone_id, ms["project_id"], project_id)
                )
        if supersedes_task_id:
            orig = conn.execute(
                "SELECT id FROM tasks WHERE id = ?",
                (supersedes_task_id,),
            ).fetchone()
            if not orig:
                raise ValueError(
                    f"No task found with id {supersedes_task_id!r} (supersedes_task_id)."
                )
        status = "Proposed"
        if assignee_id:
            _require_active_person(conn, assignee_id, "be assigned tasks")
            status = "Assigned"
        task_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO tasks (id, project_id, milestone_id, title,"
            " assignee_id, status, due_date, supersedes_task_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, project_id, milestone_id, title.strip(), assignee_id,
             status, due_date, supersedes_task_id),
        )
        conn.commit()
    finally:
        conn.close()
    return task_id


def get_task(db_path, task_id):
    """Return the task dict for ``task_id``, or None if not found."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_tasks_by_project(db_path, project_id):
    """Return all tasks for a project, ordered by row creation."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def assign_task(db_path, task_id, assignee_id, actor_id=None):
    """Assign a task to a person (Proposed -> Assigned).

    Also supports reassignment while still Assigned. Tasks that have moved
    past Assigned cannot be (re)assigned — model rework as a new task.

    ``actor_id`` is the person performing the assignment (may be None when
    unknown). A successful assignment emits one audit event.
    """
    conn = connect(db_path)
    try:
        _require_active_person(conn, assignee_id, "be assigned tasks")
        row = _get_task_row(conn, task_id)
        current = row["status"]
        if current == "Proposed":
            validate_transition(current, "Assigned")
            new_status = "Assigned"
            note = f"assigned to {assignee_id}"
        elif current == "Assigned":
            new_status = "Assigned"  # reassignment, no status change
            note = f"reassigned to {assignee_id}"
        else:
            raise ValueError(
                f"Cannot assign task in status {current!r}. Only Proposed or Assigned"
                " tasks can be assigned."
            )
        conn.execute(
            "UPDATE tasks SET assignee_id = ?, status = ? WHERE id = ?",
            (assignee_id, new_status, task_id),
        )
        conn.commit()
    finally:
        conn.close()
    # Log only after the assignment committed successfully.
    audit.log_event(db_path, "task", task_id, current, new_status,
                    actor_id=actor_id, note=note)


def update_task_status(db_path, task_id, new_status, actor_id=None):
    """Move a task to ``new_status``, enforcing the allowed transitions.

    Evidence gates (v0.2 — the system records what happened; it never
    manufactures it):
      * ``Completed`` requires at least one evidence record for the task.
      * ``Verified`` requires independently verified evidence, i.e. an
        evidence record whose verifier differs from its submitter.

    Review gates (v0.4) are enforced by ``review.start_review``,
    ``review.accept_review``, and ``review.reject_review`` — use those for
    the Submitted -> Under Review -> Accepted/Rejected steps. ``Rejected``
    is terminal: no transition out of it is allowed.

    ``actor_id`` is the person performing the transition (may be None when
    unknown). Every accepted transition emits exactly one audit event;
    refused transitions emit none. A no-op (new_status == current) emits
    no event.
    """
    conn = connect(db_path)
    try:
        row = _get_task_row(conn, task_id)
        current = row["status"]
        if new_status == current:
            return  # idempotent: already there, nothing to record
        validate_transition(current, new_status)
        if new_status == "Completed" and not _has_evidence(conn, task_id):
            raise ValueError(
                f"cannot complete task without evidence: task {task_id!r} has no"
                " evidence records"
            )
        if new_status == "Verified" and not _has_independent_verification(
            conn, task_id
        ):
            raise ValueError(
                "cannot verify task without independent verification:"
                f" task {task_id!r} has no evidence verified by someone other than"
                " its submitter"
            )
        conn.execute(
            "UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id)
        )
        conn.commit()
    finally:
        conn.close()
    # Log only after the transition committed successfully.
    audit.log_event(db_path, "task", task_id, current, new_status,
                    actor_id=actor_id)


def rework_task(db_path, original_task_id, title=None, assignee_id=None,
                actor_id=None):
    """Create a rework task for a rejected task and return the new task id.

    Rejected is a recorded terminal outcome, not an invitation to rewrite
    history: the original task is never reopened. Instead a NEW task is
    created in ``Proposed`` (or ``Assigned`` when ``assignee_id`` is given)
    with ``supersedes_task_id`` pointing at the original, preserving the
    relationship.

    Raises ValueError unless the original task exists and is Rejected.
    ``title`` defaults to the original title plus " (rework)".
    """
    conn = connect(db_path)
    try:
        row = _get_task_row(conn, original_task_id)
        if row["status"] != "Rejected":
            raise ValueError(
                "Rework is only allowed for Rejected tasks; task {!r} is {!r}.".format(original_task_id, row["status"])
            )
        project_id = row["project_id"]
        milestone_id = row["milestone_id"]
        new_title = title.strip() if title and title.strip() else (
            row["title"] + " (rework)"
        )
    finally:
        conn.close()
    return add_task(
        db_path, project_id, new_title,
        assignee_id=assignee_id,
        milestone_id=milestone_id,
        supersedes_task_id=original_task_id,
    )
