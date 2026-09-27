"""Structured project intake (v0.4).

An intake is a staged project request — title, scope, and an explicit
requester — captured BEFORE a project exists. Approving an intake creates
exactly one project; rejecting it records the decision. Decided intakes
are never re-decided, so approval can never create duplicate projects.

Intake lifecycle: Pending -> Approved | Rejected (both terminal).
"""

import uuid

from .db import connect, row_to_dict, utcnow
from .projects import add_project

# Intake states. Pending is the only non-terminal state.
INTAKE_STATUSES = ("Pending", "Approved", "Rejected")


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


def _get_intake_row(conn, intake_id):
    row = conn.execute(
        "SELECT * FROM intakes WHERE id = ?", (intake_id,)
    ).fetchone()
    if not row:
        raise ValueError("No intake found with id %r." % intake_id)
    return row


def create_intake(db_path, title, scope, requester_id, description=None):
    """Stage a project request and return its id.

    ``title``, ``scope``, and ``requester_id`` are all required; the
    requester must be an existing, active person. Nothing is created when
    validation fails.
    """
    if not title or not title.strip():
        raise ValueError("title is required")
    if not scope or not scope.strip():
        raise ValueError("scope is required: the request must state its scope")
    if not requester_id:
        raise ValueError("requester_id is required")
    conn = connect(db_path)
    try:
        _require_active_person(conn, requester_id, "request projects")
        intake_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO intakes (id, title, scope, description,"
            " requester_id, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'Pending', ?)",
            (intake_id, title.strip(), scope.strip(), description,
             requester_id, utcnow()),
        )
        conn.commit()
    finally:
        conn.close()
    return intake_id


def get_intake(db_path, intake_id):
    """Return the intake dict for ``intake_id``, or None if not found."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM intakes WHERE id = ?", (intake_id,)
        ).fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_intakes(db_path, status=None):
    """List intakes, optionally filtered by status. Oldest first."""
    if status is not None and status not in INTAKE_STATUSES:
        raise ValueError(
            "Invalid intake status %r. Must be one of %s."
            % (status, list(INTAKE_STATUSES))
        )
    conn = connect(db_path)
    try:
        if status is None:
            rows = conn.execute(
                "SELECT * FROM intakes ORDER BY rowid"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM intakes WHERE status = ? ORDER BY rowid",
                (status,),
            ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def approve_intake(db_path, intake_id, approver_id):
    """Approve a pending intake, creating exactly one project.

    The project is named after the intake title, described by its scope,
    and owned by the requester; the approver is recorded as ``decided_by``.
    Raises ValueError when the intake is not Pending (an approved intake
    can never be approved again — no duplicate projects), or when the
    approver is unknown/inactive. Returns the new project id.
    """
    conn = connect(db_path)
    try:
        row = _get_intake_row(conn, intake_id)
        if row["status"] != "Pending":
            raise ValueError(
                "Intake %r is already %r and cannot be approved."
                % (intake_id, row["status"])
            )
        _require_active_person(conn, approver_id, "approve intakes")
        requester_id = row["requester_id"]
    finally:
        conn.close()
    # add_project validates the owner and commits the project row.
    project_id = add_project(
        db_path,
        row["title"],
        description=row["scope"],
        owner_id=requester_id,
    )
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE intakes SET status = 'Approved', decided_by = ?,"
            " decided_at = ?, project_id = ? WHERE id = ?",
            (approver_id, utcnow(), project_id, intake_id),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id


def reject_intake(db_path, intake_id, decided_by, reason):
    """Reject a pending intake. ``reason`` is required.

    Raises ValueError when the intake is not Pending, the decider is
    unknown/inactive, or no reason is given.
    """
    if not reason or not reason.strip():
        raise ValueError("A reason is required to reject an intake.")
    conn = connect(db_path)
    try:
        row = _get_intake_row(conn, intake_id)
        if row["status"] != "Pending":
            raise ValueError(
                "Intake %r is already %r and cannot be rejected."
                % (intake_id, row["status"])
            )
        _require_active_person(conn, decided_by, "reject intakes")
        conn.execute(
            "UPDATE intakes SET status = 'Rejected', decided_by = ?,"
            " decided_at = ?, decision_reason = ? WHERE id = ?",
            (decided_by, utcnow(), reason.strip(), intake_id),
        )
        conn.commit()
    finally:
        conn.close()
