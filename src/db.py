"""SQLite schema, shared constants, and database helpers for the HR-PM Map.

All entity modules build on top of this module. Only the Python standard
library is used.
"""

import sqlite3
from datetime import datetime, timezone

# Valid roles for a Person.
PERSON_ROLES = ("Employee", "Contractor", "Manager", "Client")

# The task lifecycle stages.
#
# v0.4 ordering note: human review is now an explicit step. Submitted work
# goes Under Review; a reviewer then Accepts it (forward to Completed) or
# Rejects it. Rejected is TERMINAL — a rejected task can never be reopened;
# rework is modeled as a new task referencing the original
# (tasks.supersedes_task_id). Accepted, Completed, and Verified remain
# three separate recorded facts.
#
# v0.2 ordering note (still true): Completed comes BEFORE Verified. A task
# is Completed when evidence exists; it is Verified only after that
# evidence was independently verified by someone other than the submitter.
# The system records what happened; it does not manufacture evidence
# that something happened.
TASK_STATUSES = (
    "Proposed",
    "Assigned",
    "In Progress",
    "Submitted",
    "Under Review",
    "Accepted",
    "Rejected",
    "Completed",
    "Verified",
)

# Allowed task status transitions. Forward movement is one step at a time;
# the only backward move permitted is Assigned -> Proposed (un-assigning).
# Rejected is terminal: ALLOWED_TRANSITIONS["Rejected"] is empty, so any
# attempt to move a rejected task is refused. Evidence gates are enforced
# in tasks.update_task_status():
#   -> Completed requires at least one evidence record for the task
#   -> Verified requires independently verified evidence (verifier != submitter)
# Review gates are enforced in review.start_review / accept_review /
# reject_review (reviewer identity required; rejection requires a reason).
ALLOWED_TRANSITIONS = {
    "Proposed": {"Assigned"},
    "Assigned": {"Proposed", "In Progress"},
    "In Progress": {"Submitted"},
    "Submitted": {"Under Review"},
    "Under Review": {"Accepted", "Rejected"},
    "Accepted": {"Completed"},
    "Rejected": set(),  # terminal: no reopening, rework is a new task
    "Completed": {"Verified"},
    "Verified": set(),
}

# Milestone lifecycle: simplified, forward-only. Milestones do NOT require
# evidence — only tasks carry the evidence gate.
MILESTONE_STATUSES = (
    "Proposed",
    "Assigned",
    "In Progress",
    "Completed",
)

MILESTONE_TRANSITIONS = {
    "Proposed": {"Assigned"},
    "Assigned": {"In Progress"},
    "In Progress": {"Completed"},
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
        CHECK (status IN ('Proposed','Assigned','In Progress','Submitted','Completed','Verified')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS milestones (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'Proposed'
        CHECK (status IN ('Proposed','Assigned','In Progress','Completed')),
    due_date TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    milestone_id TEXT REFERENCES milestones(id),
    title TEXT NOT NULL,
    assignee_id TEXT REFERENCES people(id),
    status TEXT NOT NULL DEFAULT 'Proposed'
        CHECK (status IN ('Proposed','Assigned','In Progress','Submitted',
                         'Under Review','Accepted','Rejected',
                         'Completed','Verified')),
    due_date TEXT,
    reviewer_id TEXT REFERENCES people(id),
    supersedes_task_id TEXT REFERENCES tasks(id)
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

-- v0.4: structured project intake. An intake is a staged request
-- (Pending) that becomes a project on approval, or is Rejected.
-- Approval creates exactly one project; decided intake rows are never
-- re-decided (no duplicate projects).
CREATE TABLE IF NOT EXISTS intakes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    scope TEXT NOT NULL,
    description TEXT,
    requester_id TEXT NOT NULL REFERENCES people(id),
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending','Approved','Rejected')),
    created_at TEXT NOT NULL,
    decided_by TEXT REFERENCES people(id),
    decided_at TEXT,
    decision_reason TEXT,
    project_id TEXT REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_intakes_status ON intakes(status);

-- v0.4: human review decisions. One row per review decision on a task.
-- A task gets at most one row in practice: Rejected is terminal and
-- Accepted moves the task forward out of review.
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    reviewer_id TEXT NOT NULL REFERENCES people(id),
    decision TEXT NOT NULL CHECK (decision IN ('Accepted','Rejected')),
    reason TEXT,
    decided_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviews_task ON reviews(task_id);

-- v0.3: append-only audit trail. One row per accepted state transition.
-- There is intentionally no update/delete path for this table in src/audit.py:
-- history cannot be rewritten. actor_id may be NULL when the actor is unknown
-- (system); entity_id is not a foreign key because it may reference tasks,
-- milestones, or projects — src/audit.py validates the reference instead.
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('task','milestone','project')),
    entity_id TEXT NOT NULL,
    prev_state TEXT,
    new_state TEXT NOT NULL,
    actor_id TEXT REFERENCES people(id),
    timestamp TEXT NOT NULL,
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id);
"""

# Indexes that reference v0.2 columns. Created after the v0.1 -> v0.2
# migration in init_db(), because the columns may not exist yet on old DBs.
_INDEX_SQL_V02 = """
CREATE INDEX IF NOT EXISTS idx_tasks_milestone ON tasks(milestone_id);
CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id);
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
    """Create all HR-PM Map tables. Safe to call on an existing database.

    v0.2 migration: databases created by v0.1 lack ``tasks.milestone_id``.
    The column is added in place when missing, so old databases keep working.

    v0.4 migration: databases created before v0.4 lack
    ``tasks.reviewer_id`` and ``tasks.supersedes_task_id``; both are added
    in place when missing. Note: the ``tasks.status`` CHECK constraint
    cannot be altered in place on SQLite, so databases created before v0.4
    must be recreated (fresh ``init_db``) before using the new review
    states (Under Review / Accepted / Rejected).
    """
    conn = connect(path)
    try:
        conn.executescript(_SCHEMA_SQL)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(tasks)")]
        if "milestone_id" not in cols:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN milestone_id"
                " TEXT REFERENCES milestones(id)"
            )
        if "reviewer_id" not in cols:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN reviewer_id"
                " TEXT REFERENCES people(id)"
            )
        if "supersedes_task_id" not in cols:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN supersedes_task_id"
                " TEXT REFERENCES tasks(id)"
            )
        conn.executescript(_INDEX_SQL_V02)
        conn.commit()
    finally:
        conn.close()


def validate_transition(current, new):
    """Raise ValueError unless moving from ``current`` to ``new`` is allowed.

    Allowed moves: one step forward along
    Proposed -> Assigned -> In Progress -> Submitted -> Under Review
      -> Accepted -> Completed -> Verified,
    with Under Review -> Rejected as a TERMINAL branch (Rejected has no
    outgoing transitions — a rejected task can never be reopened),
    plus Assigned -> Proposed (un-assigning).

    The transition table alone does not capture the evidence gates — those
    are enforced by ``tasks.update_task_status`` (a task cannot become
    Completed without evidence, nor Verified without independent
    verification) — nor the review gates, enforced by ``review.*``
    (reviewer identity required; rejection requires a reason).
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
