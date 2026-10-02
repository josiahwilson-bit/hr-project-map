"""Human review of submitted work (v0.4).

Review is an explicit step between submission and completion:

    Submitted -> Under Review -> Accepted -> Completed -> Verified
                        |
                        v
                     Rejected (TERMINAL)

Accepted, Completed, and Verified remain three separate recorded facts.
Rejected is a recorded terminal outcome, not an invitation to rewrite
history: a rejected task can never be reopened. Rework is modeled as a
new task referencing the original (see ``tasks.rework_task``).

Rules enforced here (on top of the transition table):
  * a reviewer must be an existing, active person;
  * the reviewer who accepts/rejects must be the one who started the review;
  * rejection requires a reason;
  * every accepted review decision emits exactly one audit event, via the
    single logging point in ``tasks.update_task_status`` (actor=reviewer);
  * refused review actions emit no event and write no review row.
"""

import uuid

from .db import connect, row_to_dict, utcnow
from .tasks import _get_task_row, update_task_status


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


def _require_matching_reviewer(conn, task_row, task_id, reviewer_id):
    """The reviewer deciding must be the reviewer who started the review."""
    if task_row["reviewer_id"] != reviewer_id:
        raise ValueError(
            "Review of task {!r} was started by {!r}, not {!r}.".format(task_id, task_row["reviewer_id"], reviewer_id)
        )


def _record_decision(db_path, task_id, reviewer_id, decision, reason):
    """Write one row to the reviews table. Called only after the review
    transition has committed successfully."""
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO reviews (id, task_id, reviewer_id, decision,"
            " reason, decided_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, task_id, reviewer_id, decision, reason,
             utcnow()),
        )
        conn.commit()
    finally:
        conn.close()


def start_review(db_path, task_id, reviewer_id, actor_id=None):
    """Begin human review: Submitted -> Under Review.

    ``reviewer_id`` must be an existing, active person and is recorded on
    the task; only that reviewer may later accept or reject. The reviewer
    is the actor of the audit event unless ``actor_id`` is given.
    """
    if not reviewer_id:
        raise ValueError("reviewer_id is required to start a review")
    conn = connect(db_path)
    try:
        row = _get_task_row(conn, task_id)
        if row["status"] != "Submitted":
            raise ValueError(
                "Only Submitted tasks can enter review; task {!r} is {!r}.".format(task_id, row["status"])
            )
        _require_active_person(conn, reviewer_id, "review tasks")
        conn.execute(
            "UPDATE tasks SET reviewer_id = ? WHERE id = ?",
            (reviewer_id, task_id),
        )
        conn.commit()
    finally:
        conn.close()
    # Single logging point: one audit event for Submitted -> Under Review.
    update_task_status(
        db_path, task_id, "Under Review",
        actor_id=actor_id or reviewer_id,
    )


def accept_review(db_path, task_id, reviewer_id, note=None, actor_id=None):
    """Accept reviewed work: Under Review -> Accepted.

    The reviewer must be the one who started the review. Acceptance emits
    one audit event (actor=reviewer) and one row in the reviews table.
    """
    if not reviewer_id:
        raise ValueError("reviewer_id is required to accept a review")
    conn = connect(db_path)
    try:
        row = _get_task_row(conn, task_id)
        if row["status"] != "Under Review":
            raise ValueError(
                "Only tasks Under Review can be accepted; task {!r} is {!r}.".format(task_id, row["status"])
            )
        _require_active_person(conn, reviewer_id, "accept reviews")
        _require_matching_reviewer(conn, row, task_id, reviewer_id)
    finally:
        conn.close()
    update_task_status(
        db_path, task_id, "Accepted", actor_id=actor_id or reviewer_id
    )
    _record_decision(db_path, task_id, reviewer_id, "Accepted", note)


def reject_review(db_path, task_id, reviewer_id, reason, actor_id=None):
    """Reject reviewed work: Under Review -> Rejected (TERMINAL).

    ``reason`` is required — a rejection without a recorded reason is
    refused. The reviewer must be the one who started the review. One
    audit event (actor=reviewer) and one reviews row are written. The
    task can never leave Rejected afterwards.
    """
    if not reviewer_id:
        raise ValueError("reviewer_id is required to reject a review")
    if not reason or not reason.strip():
        raise ValueError(
            "A reason is required to reject reviewed work."
        )
    conn = connect(db_path)
    try:
        row = _get_task_row(conn, task_id)
        if row["status"] != "Under Review":
            raise ValueError(
                "Only tasks Under Review can be rejected; task {!r} is {!r}.".format(task_id, row["status"])
            )
        _require_active_person(conn, reviewer_id, "reject reviews")
        _require_matching_reviewer(conn, row, task_id, reviewer_id)
    finally:
        conn.close()
    update_task_status(
        db_path, task_id, "Rejected", actor_id=actor_id or reviewer_id
    )
    _record_decision(
        db_path, task_id, reviewer_id, "Rejected", reason.strip()
    )


def get_reviews(db_path, task_id):
    """Return review decisions for a task, oldest first. Read-only."""
    conn = connect(db_path)
    try:
        if not conn.execute(
            "SELECT id FROM tasks WHERE id = ?", (task_id,)
        ).fetchone():
            raise ValueError(f"No task found with id {task_id!r}.")
        rows = conn.execute(
            "SELECT * FROM reviews WHERE task_id = ? ORDER BY decided_at,"
            " rowid",
            (task_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()
