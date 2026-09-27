"""SQLite schema, shared constants, and database helpers for the HR-PM Map.

All entity modules build on top of this module. Only the Python standard
library is used.
"""

import sqlite3
from datetime import datetime, timezone

# Valid roles for a Person.
PERSON_ROLES = ("Employee", "Contractor", "Manager", "Client")

# The six lifecycle stages, shared by projects and tasks.
TASK_STATUSES = (
    "Proposed",
    "Assigned",
    "In Progress",
    "Submitted",
    "Verified",
    "Completed",
)

# Allowed task status transitions. Forward movement is one step at a time;
# the only backward move permitted is Assigned -> Proposed (un-assigning).
ALLOWED_TRANSITIONS = {
    "Proposed": {"Assigned"},
    "Assigned": {"Proposed", "In Progress"},
    "In Progress": {"Submitted"},
    "Submitted": {"Verified"},
    "Verified": {"Completed"},
    "Completed": set(),
}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('Employee','Contractor','Manager','Client')),
    email TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner_id TEXT NOT NULL REFERENCES people(id),
    status TEXT NOT NULL DEFAULT 'Proposed'
        CHECK (status IN ('Proposed','Assigned','In Progress','Submitted','Verified','Completed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    assignee_id TEXT REFERENCES people(id),
    status TEXT NOT NULL DEFAULT 'Proposed'
        CHECK (status IN ('Proposed','Assigned','In Progress','Submitted','Verified','Completed')),
    due_date TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    submitted_by TEXT NOT NULL REFERENCES people(id),
    evidence_type TEXT NOT NULL,
    url_or_path TEXT,
    submitted_at TEXT NOT NULL,
    verified_by TEXT REFERENCES people(id),
    verified_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_evidence_task ON evidence(task_id);
"""


def utcnow():
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def connect(path):
    """Open a SQLite connection with row dicts and foreign keys enabled."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path):
    """Create all HR-PM Map tables. Safe to call on an existing database."""
    conn = connect(path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def validate_transition(current, new):
    """Raise ValueError unless moving from ``current`` to ``new`` is allowed.

    Allowed moves: one step forward along
    Proposed -> Assigned -> In Progress -> Submitted -> Verified -> Completed,
    plus Assigned -> Proposed (un-assigning).
    """
    if new not in TASK_STATUSES:
        raise ValueError(
            "Unknown status %r. Must be one of %s." % (new, list(TASK_STATUSES))
        )
    if new not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(
            "Invalid status transition: %r -> %r." % (current, new)
        )


def row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict, normalizing flags to bool."""
    d = dict(row)
    if "active" in d and d["active"] is not None:
        d["active"] = bool(d["active"])
    return d
