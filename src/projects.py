"""Project records: add, get, list, and manual status updates."""

import uuid

from .db import TASK_STATUSES, connect, row_to_dict, utcnow


def add_project(db_path, name, description=None, owner_id=None, status="Proposed"):
    """Add a project and return its id.

    ``owner_id`` is required: every project has exactly one accountable
    owner. ``status`` must be one of the six lifecycle stages.
    """
    if not name or not name.strip():
        raise ValueError("name is required")
    if not owner_id:
        raise ValueError("owner_id is required: every project needs an owner")
    if status not in TASK_STATUSES:
        raise ValueError(
            "Invalid status %r. Must be one of %s." % (status, list(TASK_STATUSES))
        )
    conn = connect(db_path)
    try:
        owner = conn.execute(
            "SELECT id FROM people WHERE id = ?", (owner_id,)
        ).fetchone()
        if not owner:
            raise ValueError("No person found with id %r." % owner_id)
        project_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO projects (id, name, description, owner_id, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, name.strip(), description, owner_id, status, utcnow()),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id


def get_project(db_path, project_id):
    """Return the project dict for ``project_id``, or None if not found."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_projects(db_path):
    """Return all projects ordered by creation time."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at"
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_project_status(db_path, project_id, new_status):
    """Set a project's status. Project status is a manual judgment call by
    the owner, so any of the six lifecycle stages is accepted."""
    if new_status not in TASK_STATUSES:
        raise ValueError(
            "Invalid status %r. Must be one of %s."
            % (new_status, list(TASK_STATUSES))
        )
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE projects SET status = ? WHERE id = ?",
            (new_status, project_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError("No project found with id %r." % project_id)
    finally:
        conn.close()
