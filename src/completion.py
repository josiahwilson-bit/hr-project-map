"""Evidence-gated completion and verification.

Core principle: the system records what happened; it does not manufacture
evidence that something happened.

  * A task becomes Completed only when at least one evidence record exists
    for it (Submitted -> Completed).
  * A task becomes Verified only when that evidence was independently
    verified by someone other than the submitter (Completed -> Verified).

No synthetic evidence is ever generated: these functions only move a task
forward when the required records already exist.
"""

from .db import connect
from .tasks import (
    _get_task_row,
    _has_evidence,
    update_task_status,
)


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


def complete_task(db_path, task_id, actor_id=None):
    """Move a Submitted task to Completed.

    Raises ValueError unless the task is Submitted AND at least one evidence
    record exists for it. The exact message for the missing-evidence case is
    "cannot complete task without evidence".

    ``actor_id`` is passed through to the underlying transition, which emits
    the single audit event for Submitted -> Completed. Refused completions
    emit no event.
    """
    conn = connect(db_path)
    try:
        row = _get_task_row(conn, task_id)
        if row["status"] != "Submitted":
            raise ValueError(
                "Only Submitted tasks can be completed; task %r is %r."
                % (task_id, row["status"])
            )
        if not _has_evidence(conn, task_id):
            raise ValueError("cannot complete task without evidence")
    finally:
        conn.close()
    update_task_status(db_path, task_id, "Completed", actor_id=actor_id)


def verify_task(db_path, task_id, verifier_id):
    """Move a Completed task to Verified.

    Raises ValueError unless the task is Completed AND an evidence record
    exists that was verified by ``verifier_id`` where the verifier differs
    from the submitter. The verifier must be an active person.

    The verifier is recorded as the actor of the single audit event for
    Completed -> Verified. Refused verifications emit no event.
    """
    conn = connect(db_path)
    try:
        row = _get_task_row(conn, task_id)
        if row["status"] != "Completed":
            raise ValueError(
                "Only Completed tasks can be verified; task %r is %r."
                % (task_id, row["status"])
            )
        _require_active_person(conn, verifier_id, "verify tasks")
        ev = conn.execute(
            "SELECT id FROM evidence"
            " WHERE task_id = ? AND verified_by = ?"
            " AND verified_by != submitted_by",
            (task_id, verifier_id),
        ).fetchone()
        if not ev:
            raise ValueError(
                "cannot verify task without independent verification:"
                " task %r has no evidence verified by %r (distinct from"
                " the submitter)" % (task_id, verifier_id)
            )
    finally:
        conn.close()
    update_task_status(db_path, task_id, "Verified", actor_id=verifier_id)
