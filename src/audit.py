"""Append-only audit trail for HR-PM Map state transitions.

Every accepted state transition on a task, milestone, or project emits
exactly one audit event recording: what entity changed, the previous and
new state, who performed the transition (actor), and when.

Append-only by design: this module exposes ``log_event`` and ``get_events``
only. There is deliberately NO update or delete API for audit rows — history
cannot be rewritten through this module. A transition without an audit
record is not considered recorded.

Core rule: the audit trail records the transition; it never creates
evidence of an event that did not occur.
"""

import uuid

from .db import connect, row_to_dict, utcnow

# Entity kinds that can appear in the audit trail.
ENTITY_TYPES = ("task", "milestone", "project")

_TABLE_BY_ENTITY = {
    "task": "tasks",
    "milestone": "milestones",
    "project": "projects",
}


def log_event(db_path, entity_type, entity_id, prev_state, new_state,
              actor_id=None, note=None):
    """Append one audit event and return its event_id.

    Raises ValueError for an unknown entity_type, a missing referenced
    entity, or an unknown actor. Callers must invoke this only AFTER the
    underlying transition has committed successfully — refused or invalid
    transitions must never reach this function.
    """
    if entity_type not in ENTITY_TYPES:
        raise ValueError(
            "Unknown entity_type %r. Must be one of %s."
            % (entity_type, list(ENTITY_TYPES))
        )
    if not entity_id:
        raise ValueError("entity_id is required")
    if not new_state:
        raise ValueError("new_state is required")
    conn = connect(db_path)
    try:
        table = _TABLE_BY_ENTITY[entity_type]
        exists = conn.execute(
            "SELECT id FROM %s WHERE id = ?" % table, (entity_id,)
        ).fetchone()
        if not exists:
            raise ValueError(
                "Cannot audit %s %r: no such %s."
                % (entity_type, entity_id, entity_type)
            )
        if actor_id is not None:
            person = conn.execute(
                "SELECT id FROM people WHERE id = ?", (actor_id,)
            ).fetchone()
            if not person:
                raise ValueError(
                    "Cannot audit with unknown actor %r." % actor_id
                )
        event_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO audit_events (event_id, entity_type, entity_id,"
            " prev_state, new_state, actor_id, timestamp, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, entity_type, entity_id, prev_state, new_state,
             actor_id, utcnow(), note),
        )
        conn.commit()
    finally:
        conn.close()
    return event_id


def get_events(db_path, entity_type=None, entity_id=None):
    """Return audit events, oldest first.

    Optionally filtered by entity_type and/or entity_id. Read-only.
    """
    if entity_type is not None and entity_type not in ENTITY_TYPES:
        raise ValueError(
            "Unknown entity_type %r. Must be one of %s."
            % (entity_type, list(ENTITY_TYPES))
        )
    conn = connect(db_path)
    try:
        sql = "SELECT * FROM audit_events"
        clauses = []
        params = []
        if entity_type is not None:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp, rowid"
        rows = conn.execute(sql, params).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def count_events(db_path):
    """Return the total number of audit events. Read-only."""
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_events").fetchone()
        return row["n"]
    finally:
        conn.close()
