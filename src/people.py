"""Person records: add, get, list, deactivate."""

import uuid

from .db import PERSON_ROLES, connect, row_to_dict


def add_person(db_path, name, role, email=None, active=True):
    """Add a person and return their id.

    ``role`` must be one of Employee, Contractor, Manager, Client.
    """
    if not name or not name.strip():
        raise ValueError("name is required")
    if role not in PERSON_ROLES:
        raise ValueError(
            f"Invalid role {role!r}. Must be one of {list(PERSON_ROLES)}."
        )
    person_id = uuid.uuid4().hex
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO people (id, name, role, email, active)"
            " VALUES (?, ?, ?, ?, ?)",
            (person_id, name.strip(), role, email, 1 if active else 0),
        )
        conn.commit()
    finally:
        conn.close()
    return person_id


def get_person(db_path, person_id):
    """Return the person dict for ``person_id``, or None if not found."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_people(db_path, active_only=False):
    """Return all people, optionally only active ones, ordered by name."""
    conn = connect(db_path)
    try:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM people WHERE active = 1 ORDER BY name"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM people ORDER BY name").fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def set_active(db_path, person_id, active):
    """Activate or deactivate a person. Inactive people keep history but get
    no new assignments and cannot verify evidence."""
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE people SET active = ? WHERE id = ?",
            (1 if active else 0, person_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError(f"No person found with id {person_id!r}.")
    finally:
        conn.close()
