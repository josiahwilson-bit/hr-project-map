"""Read-only dashboard queries for the HR-PM Map.

This module performs SELECT queries only — it never inserts, updates, or
deletes. The dashboard reports state; it does not modify it.

Status buckets (v0.4):
  * outstanding: Proposed, Assigned, In Progress (work not yet submitted)
  * submitted:   Submitted, Under Review (work awaiting a review decision)
  * completed:   Completed (evidence recorded, not yet verified)
  * verified:    Verified (independently verified work)
  * rejected:    Rejected (terminal review outcome; rework is a new task)
"""

from .db import connect, row_to_dict

# Work that has been started (or proposed) but not yet submitted.
OUTSTANDING_STATUSES = ("Proposed", "Assigned", "In Progress")


def _tasks_by_statuses(db_path, statuses, project_id=None):
    """Return tasks whose status is in ``statuses`` (read-only)."""
    conn = connect(db_path)
    try:
        placeholders = ", ".join("?" for _ in statuses)
        # nosec B608: `placeholders` is a string of "?" bind markers only;
        # the actual values are bound via `params` below. No SQL injection.
        sql = (
            "SELECT t.*, p.name AS project_name FROM tasks t"
            " JOIN projects p ON p.id = t.project_id"
            f" WHERE t.status IN ({placeholders})"  # nosec B608
        )
        params = list(statuses)
        if project_id is not None:
            sql += " AND t.project_id = ?"
            params.append(project_id)
        sql += " ORDER BY t.rowid"
        rows = conn.execute(sql, params).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def outstanding_tasks(db_path, project_id=None):
    """Tasks in Proposed/Assigned/In Progress. Read-only."""
    return _tasks_by_statuses(db_path, OUTSTANDING_STATUSES, project_id)


def submitted_tasks(db_path, project_id=None):
    """Tasks in Submitted or Under Review (awaiting a review decision).

    Read-only.
    """
    return _tasks_by_statuses(
        db_path, ("Submitted", "Under Review"), project_id
    )


def completed_tasks(db_path, project_id=None):
    """Tasks in Completed. Read-only."""
    return _tasks_by_statuses(db_path, ("Completed",), project_id)


def verified_tasks(db_path, project_id=None):
    """Tasks in Verified. Read-only."""
    return _tasks_by_statuses(db_path, ("Verified",), project_id)


def rejected_tasks(db_path, project_id=None):
    """Tasks in Rejected (terminal review outcome). Read-only.

    Rejected tasks are never reopened; any rework appears as a separate
    task whose ``supersedes_task_id`` points at the rejected original.
    """
    return _tasks_by_statuses(db_path, ("Rejected",), project_id)


def project_summary(db_path, project_id):
    """Counts per task status plus milestone count for a project.

    Read-only. Raises ValueError when the project does not exist.
    """
    conn = connect(db_path)
    try:
        project = conn.execute(
            "SELECT id, name, status FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if not project:
            raise ValueError(f"No project found with id {project_id!r}.")
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks"
            " WHERE project_id = ? GROUP BY status",
            (project_id,),
        ).fetchall()
        counts = {r["status"]: r["n"] for r in status_rows}
        ms = conn.execute(
            "SELECT COUNT(*) AS n FROM milestones WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return {
            "project_id": project["id"],
            "project_name": project["name"],
            "project_status": project["status"],
            "task_counts": counts,
            "milestone_count": ms["n"],
            "outstanding": sum(
                counts.get(s, 0) for s in OUTSTANDING_STATUSES
            ),
        }
    finally:
        conn.close()
