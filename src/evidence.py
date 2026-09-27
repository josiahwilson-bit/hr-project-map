"""Evidence submission and independent verification.

Submitting evidence moves a task to Submitted. Verifying evidence moves the
task to Verified — but only when the verifier is a *different* person than
the submitter. Self-verification is rejected.
"""

import uuid

from .db import connect, row_to_dict, utcnow
from .tasks import update_task_status


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


def submit_evidence(db_path, task_id, submitted_by, evidence_type,
                    url_or_path=None):
    """Record evidence for a task and return the evidence id.

    The task must be ``In Progress`` (first submission) or already
    ``Submitted`` (additional evidence). The task is moved to ``Submitted``.
    """
    if not evidence_type or not evidence_type.strip():
        raise ValueError("evidence_type is required")
    conn = connect(db_path)
    try:
        task = conn.execute(
            "SELECT id, status FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not task:
            raise ValueError("No task found with id %r." % task_id)
        _require_active_person(conn, submitted_by, "submit evidence")
        if task["status"] not in ("In Progress", "Submitted"):
            raise ValueError(
                "Cannot submit evidence for task in status %r."
                " Task must be In Progress." % task["status"]
            )
        evidence_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO evidence (id, task_id, submitted_by, evidence_type,"
            " url_or_path, submitted_at) VALUES (?, ?, ?, ?, ?, ?)",
            (evidence_id, task_id, submitted_by, evidence_type.strip(),
             url_or_path, utcnow()),
        )
        conn.commit()
    finally:
        conn.close()
    # Move the task to Submitted (no-op if already Submitted).
    if task["status"] == "In Progress":
        update_task_status(db_path, task_id, "Submitted")
    return evidence_id


def verify_evidence(db_path, evidence_id, verified_by):
    """Verify an evidence record.

    ``verified_by`` must be a different person than the submitter —
    self-verification raises ValueError. On success the evidence is stamped
    and its task is moved to ``Verified``.
    """
    conn = connect(db_path)
    try:
        ev = conn.execute(
            "SELECT * FROM evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
        if not ev:
            raise ValueError("No evidence found with id %r." % evidence_id)
        if ev["verified_by"]:
            raise ValueError(
                "Evidence %r was already verified." % evidence_id
            )
        _require_active_person(conn, verified_by, "verify evidence")
        if verified_by == ev["submitted_by"]:
            raise ValueError(
                "Self-verification is not allowed: verifier %r is also the"
                " submitter." % verified_by
            )
        task_id = ev["task_id"]
        conn.execute(
            "UPDATE evidence SET verified_by = ?, verified_at = ?"
            " WHERE id = ?",
            (verified_by, utcnow(), evidence_id),
        )
        conn.commit()
    finally:
        conn.close()
    # Move the task to Verified (no-op if a previous evidence item already did).
    from .tasks import get_task
    if get_task(db_path, task_id)["status"] == "Submitted":
        update_task_status(db_path, task_id, "Verified")


def get_evidence(db_path, evidence_id):
    """Return the evidence dict for ``evidence_id``, or None if not found."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_evidence_for_task(db_path, task_id):
    """Return all evidence records for a task, oldest first."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM evidence WHERE task_id = ? ORDER BY submitted_at",
            (task_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()
