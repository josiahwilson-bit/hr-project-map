"""Task records with enforced lifecycle status transitions.

Lifecycle: Proposed -> Assigned -> In Progress -> Submitted -> Completed
-> Verified. The only backward move allowed is Assigned -> Proposed.

Evidence gates (v0.2): a task cannot become Completed without at least one
evidence record, and cannot become Verified without independently verified
evidence (verifier != submitter). The system records what happened; it does
not manufacture evidence that something happened.
"""

import uuid

from .db import connect, row_to_dict, validate_transition


def _get_task_row(conn, task_id):
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise ValueError("No task found with id %r." % task_id)
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
        raise ValueError("No person found with id %r." % person_id)
    if not row["active"]:
        raise ValueError(
            "Person %r is inactive and cannot %s." % (person_id, action)
        )


def add_task(db_path, project_id, title, assignee_id=None, due_date=None,
            milestone_id=None):
    """Add a task to a project and return its id.

    Starts in ``Proposed`` unless ``assignee_id`` is given, in which case it
    starts in ``Assigned``. ``milestone_id`` is optional; when given, the
    milestone must exist and belong to the same project.
    """
    if not title or not title.strip():
        raise ValueError("title is required")
    conn = connect(db_path)
    try:
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if not project:
            raise ValueError("No project found with id %r." % project_id)
        if milestone_id:
            ms = conn.execute(
                "SELECT id, project_id FROM milestones WHERE id = ?",
                (milestone_id,),
            ).fetchone()
            if not ms:
                raise ValueError(
                    "No milestone found with id %r." % milestone_id
                )
            if ms["project_id"] != project_id:
                raise ValueError(
                    "Milestone %r belongs to project %r, not %r."
                    % (milestone_id, ms["project_id"], project_id)
                )
        status = "Proposed"
        if assignee_id:
            _require_active_person(conn, assignee_id, "be assigned tasks")
            status = "Assigned"
        task_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO tasks (id, project_id, milestone_id, title,"
            " assignee_id, status, due_date)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, project_id, milestone_id, title.strip(), assignee_id,
             status, due_date),
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


def assign_task(db_path, task_id, assignee_id):
    """Assign a task to a person (Proposed -> Assigned).

    Also supports reassignment while still Assigned. Tasks that have moved
    past Assigned cannot be (re)assigned — model rework as a new task.
    """
    conn = connect(db_path)
    try:
        _require_active_person(conn, assignee_id, "be assigned tasks")
        row = _get_task_row(conn, task_id)
        current = row["status"]
        if current == "Proposed":
            validate_transition(current, "Assigned")
            new_status = "Assigned"
        elif current == "Assigned":
            new_status = "Assigned"  # reassignment, no status change
        else:
            raise ValueError(
                "Cannot assign task in status %r. Only Proposed or Assigned"
                " tasks can be assigned." % current
            )
        conn.execute(
            "UPDATE tasks SET assignee_id = ?, status = ? WHERE id = ?",
            (assignee_id, new_status, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_task_status(db_path, task_id, new_status):
    """Move a task to ``new_status``, enforcing the allowed transitions.

    Evidence gates (v0.2 — the system records what happened; it never
    manufactures it):
      * ``Completed`` requires at least one evidence record for the task.
      * ``Verified`` requires independently verified evidence, i.e. an
        evidence record whose verifier differs from its submitter.
    """
    conn = connect(db_path)
    try:
        row = _get_task_row(conn, task_id)
        current = row["status"]
        if new_status == current:
            return  # idempotent: already there
        validate_transition(current, new_status)
        if new_status == "Completed" and not _has_evidence(conn, task_id):
            raise ValueError(
                "cannot complete task without evidence: task %r has no"
                " evidence records" % task_id
            )
        if new_status == "Verified" and not _has_independent_verification(
            conn, task_id
        ):
            raise ValueError(
                "cannot verify task without independent verification:"
                " task %r has no evidence verified by someone other than"
                " its submitter" % task_id
            )
        conn.execute(
            "UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id)
        )
        conn.commit()
    finally:
        conn.close()
