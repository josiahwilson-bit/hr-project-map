"""Milestone records: project checkpoints with a simplified lifecycle.

Lifecycle: Proposed -> Assigned -> In Progress -> Completed, strictly
forward-only. Unlike tasks, milestones do NOT require evidence — only tasks
carry the evidence gate.
"""

import uuid

from . import audit
from .db import (
    MILESTONE_STATUSES,
    MILESTONE_TRANSITIONS,
    connect,
    row_to_dict,
    utcnow,
)


def _get_milestone_row(conn, milestone_id):
    row = conn.execute(
        "SELECT * FROM milestones WHERE id = ?", (milestone_id,)
    ).fetchone()
    if not row:
        raise ValueError("No milestone found with id %r." % milestone_id)
    return row


def add_milestone(db_path, project_id, name, description=None, due_date=None):
    """Add a milestone to a project and return its id.

    Starts in ``Proposed``. The project must exist.
    """
    if not name or not name.strip():
        raise ValueError("name is required")
    conn = connect(db_path)
    try:
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if not project:
            raise ValueError("No project found with id %r." % project_id)
        milestone_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO milestones (id, project_id, name, description,"
            " status, due_date, created_at)"
            " VALUES (?, ?, ?, ?, 'Proposed', ?, ?)",
            (milestone_id, project_id, name.strip(), description, due_date,
             utcnow()),
        )
        conn.commit()
    finally:
        conn.close()
    return milestone_id


def get_milestone(db_path, milestone_id):
    """Return the milestone dict for ``milestone_id``, or None if not found."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM milestones WHERE id = ?", (milestone_id,)
        ).fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_milestones_by_project(db_path, project_id):
    """Return all milestones for a project, ordered by row creation."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM milestones WHERE project_id = ? ORDER BY rowid",
            (project_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_milestone_status(db_path, milestone_id, new_status, actor_id=None):
    """Move a milestone to ``new_status``.

    Transitions are strictly forward-only:
    Proposed -> Assigned -> In Progress -> Completed. No backward moves.

    ``actor_id`` is the person performing the transition (may be None when
    unknown). Every accepted transition emits exactly one audit event;
    refused transitions emit none.
    """
    if new_status not in MILESTONE_STATUSES:
        raise ValueError(
            "Unknown status %r. Must be one of %s."
            % (new_status, list(MILESTONE_STATUSES))
        )
    conn = connect(db_path)
    try:
        row = _get_milestone_row(conn, milestone_id)
        current = row["status"]
        if new_status == current:
            return  # idempotent: already there, nothing to record
        if new_status not in MILESTONE_TRANSITIONS.get(current, set()):
            raise ValueError(
                "Invalid milestone status transition: %r -> %r."
                % (current, new_status)
            )
        conn.execute(
            "UPDATE milestones SET status = ? WHERE id = ?",
            (new_status, milestone_id),
        )
        conn.commit()
    finally:
        conn.close()
    # Log only after the transition committed successfully.
    audit.log_event(db_path, "milestone", milestone_id, current, new_status,
                    actor_id=actor_id)
