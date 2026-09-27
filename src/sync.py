"""JSON <-> SQLite import/export for the HR-PM Map.

``export_to_json`` dumps the five entity tables to ``data/*.json`` as plain
JSON arrays (no comments). ``import_from_json`` loads those arrays back into
a database, refusing any record that references a nonexistent entity and
skipping records whose id already exists.

Import order follows the dependency chain:
people -> projects -> milestones -> tasks -> evidence.
"""

import json
import os

from .db import MILESTONE_STATUSES, PERSON_ROLES, TASK_STATUSES, connect, init_db

# (table name, file name) in dependency order.
_TABLES = (
    ("people", "people.json"),
    ("projects", "projects.json"),
    ("milestones", "milestones.json"),
    ("tasks", "tasks.json"),
    ("evidence", "evidence.json"),
)


def _strip_comment_lines(text):
    """Drop ``//`` full-line comments so the JSONC-style seed files in
    ``data/`` can be imported as well as strict exported JSON."""
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//")
    )


def _load_array(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.loads(_strip_comment_lines(f.read()))
    if not isinstance(data, list):
        raise ValueError(
            "Expected a JSON array in %r, got %s."
            % (path, type(data).__name__)
        )
    return data


def _exists(conn, table, record_id):
    return conn.execute(
        "SELECT 1 FROM %s WHERE id = ?" % table, (record_id,)
    ).fetchone() is not None


def _require_id(rec, table):
    rid = rec.get("id")
    if not rid or not isinstance(rid, str):
        raise ValueError(
            "Record in %r is missing a valid string id: %r." % (table, rec)
        )
    return rid


def export_to_json(db_path, out_dir):
    """Dump all entity tables to ``out_dir``/*.json as JSON arrays.

    Creates the database (empty) if it does not exist yet.
    """
    init_db(db_path)
    os.makedirs(out_dir, exist_ok=True)
    conn = connect(db_path)
    try:
        for table, filename in _TABLES:
            rows = conn.execute(
                "SELECT * FROM %s ORDER BY rowid" % table
            ).fetchall()
            records = []
            for row in rows:
                d = dict(row)
                if "active" in d and d["active"] is not None:
                    d["active"] = bool(d["active"])
                records.append(d)
            path = os.path.join(out_dir, filename)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
                f.write("\n")
    finally:
        conn.close()


def import_from_json(db_path, data_dir):
    """Load ``data_dir``/*.json arrays into the database.

    Every record is validated: enum fields must be legal and every foreign
    key must reference an existing entity (in the database or earlier in
    the same import). A record referencing a missing entity is refused with
    ValueError. Records whose id already exists are skipped.
    """
    init_db(db_path)
    payloads = {}
    for table, filename in _TABLES:
        path = os.path.join(data_dir, filename)
        payloads[table] = _load_array(path) if os.path.exists(path) else []

    conn = connect(db_path)
    try:
        _import_people(conn, payloads["people"])
        _import_projects(conn, payloads["projects"])
        _import_milestones(conn, payloads["milestones"])
        _import_tasks(conn, payloads["tasks"])
        _import_evidence(conn, payloads["evidence"])
        conn.commit()
    finally:
        conn.close()


def _import_people(conn, records):
    for rec in records:
        pid = _require_id(rec, "people")
        if _exists(conn, "people", pid):
            continue  # duplicate id: skip
        name = rec.get("name")
        role = rec.get("role")
        if not name or not str(name).strip():
            raise ValueError("Person %r is missing a name." % pid)
        if role not in PERSON_ROLES:
            raise ValueError(
                "Person %r has invalid role %r. Must be one of %s."
                % (pid, role, list(PERSON_ROLES))
            )
        conn.execute(
            "INSERT INTO people (id, name, role, email, active)"
            " VALUES (?, ?, ?, ?, ?)",
            (pid, str(name).strip(), role, rec.get("email"),
             1 if rec.get("active", True) else 0),
        )


def _import_projects(conn, records):
    for rec in records:
        pid = _require_id(rec, "projects")
        if _exists(conn, "projects", pid):
            continue
        name = rec.get("name")
        owner_id = rec.get("owner_id")
        status = rec.get("status", "Proposed")
        if not name or not str(name).strip():
            raise ValueError("Project %r is missing a name." % pid)
        if not owner_id or not _exists(conn, "people", owner_id):
            raise ValueError(
                "Project %r references missing person (owner_id) %r."
                % (pid, owner_id)
            )
        if status not in TASK_STATUSES:
            raise ValueError(
                "Project %r has invalid status %r." % (pid, status)
            )
        conn.execute(
            "INSERT INTO projects (id, name, description, owner_id, status,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, str(name).strip(), rec.get("description"), owner_id,
             status, rec.get("created_at")),
        )


def _import_milestones(conn, records):
    for rec in records:
        mid = _require_id(rec, "milestones")
        if _exists(conn, "milestones", mid):
            continue
        name = rec.get("name")
        project_id = rec.get("project_id")
        status = rec.get("status", "Proposed")
        if not name or not str(name).strip():
            raise ValueError("Milestone %r is missing a name." % mid)
        if not project_id or not _exists(conn, "projects", project_id):
            raise ValueError(
                "Milestone %r references missing project %r."
                % (mid, project_id)
            )
        if status not in MILESTONE_STATUSES:
            raise ValueError(
                "Milestone %r has invalid status %r." % (mid, status)
            )
        conn.execute(
            "INSERT INTO milestones (id, project_id, name, description,"
            " status, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mid, project_id, str(name).strip(), rec.get("description"),
             status, rec.get("due_date"), rec.get("created_at")),
        )


def _import_tasks(conn, records):
    for rec in records:
        tid = _require_id(rec, "tasks")
        if _exists(conn, "tasks", tid):
            continue
        title = rec.get("title")
        project_id = rec.get("project_id")
        assignee_id = rec.get("assignee_id")
        milestone_id = rec.get("milestone_id")
        status = rec.get("status", "Proposed")
        if not title or not str(title).strip():
            raise ValueError("Task %r is missing a title." % tid)
        if not project_id or not _exists(conn, "projects", project_id):
            raise ValueError(
                "Task %r references missing project %r." % (tid, project_id)
            )
        if assignee_id and not _exists(conn, "people", assignee_id):
            raise ValueError(
                "Task %r references missing person (assignee_id) %r."
                % (tid, assignee_id)
            )
        if milestone_id:
            ms = conn.execute(
                "SELECT project_id FROM milestones WHERE id = ?",
                (milestone_id,),
            ).fetchone()
            if not ms:
                raise ValueError(
                    "Task %r references missing milestone %r."
                    % (tid, milestone_id)
                )
            if ms["project_id"] != project_id:
                raise ValueError(
                    "Task %r: milestone %r belongs to project %r, not %r."
                    % (tid, milestone_id, ms["project_id"], project_id)
                )
        if status not in TASK_STATUSES:
            raise ValueError("Task %r has invalid status %r." % (tid, status))
        conn.execute(
            "INSERT INTO tasks (id, project_id, milestone_id, title,"
            " assignee_id, status, due_date)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tid, project_id, milestone_id, str(title).strip(),
             assignee_id, status, rec.get("due_date")),
        )


def _import_evidence(conn, records):
    for rec in records:
        eid = _require_id(rec, "evidence")
        if _exists(conn, "evidence", eid):
            continue
        task_id = rec.get("task_id")
        submitted_by = rec.get("submitted_by")
        verified_by = rec.get("verified_by")
        evidence_type = rec.get("evidence_type")
        if not task_id or not _exists(conn, "tasks", task_id):
            raise ValueError(
                "Evidence %r references missing task %r." % (eid, task_id)
            )
        if not submitted_by or not _exists(conn, "people", submitted_by):
            raise ValueError(
                "Evidence %r references missing person (submitted_by) %r."
                % (eid, submitted_by)
            )
        if verified_by and not _exists(conn, "people", verified_by):
            raise ValueError(
                "Evidence %r references missing person (verified_by) %r."
                % (eid, verified_by)
            )
        if not evidence_type or not str(evidence_type).strip():
            raise ValueError("Evidence %r is missing evidence_type." % eid)
        conn.execute(
            "INSERT INTO evidence (id, task_id, submitted_by, evidence_type,"
            " url_or_path, submitted_at, verified_by, verified_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, task_id, submitted_by, str(evidence_type).strip(),
             rec.get("url_or_path"), rec.get("submitted_at"), verified_by,
             rec.get("verified_at")),
        )
