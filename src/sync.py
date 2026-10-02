"""JSON <-> SQLite import/export for the HR-PM Map.

``export_to_json`` dumps the entity tables to ``data/*.json`` as plain
JSON arrays (no comments). ``import_from_json`` loads those arrays back
into a database, refusing any record that references a nonexistent entity
and skipping records whose id already exists.

Import order follows the dependency chain:
people -> projects -> intakes -> milestones -> tasks -> evidence -> reviews.
"""

import json
import os

from .db import MILESTONE_STATUSES, PERSON_ROLES, TASK_STATUSES, connect, init_db
from .intake import INTAKE_STATUSES

# (table name, file name) in dependency order.
_TABLES = (
    ("people", "people.json"),
    ("projects", "projects.json"),
    ("intakes", "intakes.json"),
    ("milestones", "milestones.json"),
    ("tasks", "tasks.json"),
    ("evidence", "evidence.json"),
    ("reviews", "reviews.json"),
)

_KNOWN_TABLES = frozenset(name for name, _ in _TABLES)


def _checked_table(table):
    """Return ``table`` if it is a known entity table, else raise."""
    if table not in _KNOWN_TABLES:
        raise ValueError(f"Unknown table {table!r}.")
    return table


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
        raise TypeError(
            f"Expected a JSON array in {path!r}, got {type(data).__name__}."
        )
    return data


def _exists(conn, table, record_id):
    _checked_table(table)
    # nosec B608: `table` is allowlisted by _checked_table above; the
    # value interpolated here can only be a known entity table name.
    return conn.execute(
        f"SELECT 1 FROM {table} WHERE id = ?", (record_id,)  # nosec B608
    ).fetchone() is not None


def _require_id(rec, table):
    rid = rec.get("id")
    if not rid or not isinstance(rid, str):
        raise ValueError(
            f"Record in {table!r} is missing a valid string id: {rec!r}."
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
            # nosec B608: `table` comes from the module-level _TABLES
            # constant; it is never derived from user input.
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY rowid"  # nosec B608
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
        _import_intakes(conn, payloads["intakes"])
        _import_milestones(conn, payloads["milestones"])
        _import_tasks(conn, payloads["tasks"])
        _import_evidence(conn, payloads["evidence"])
        _import_reviews(conn, payloads["reviews"])
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
            raise ValueError(f"Person {pid!r} is missing a name.")
        if role not in PERSON_ROLES:
            raise ValueError(
                f"Person {pid!r} has invalid role {role!r}. Must be one of {list(PERSON_ROLES)}."
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
            raise ValueError(f"Project {pid!r} is missing a name.")
        if not owner_id or not _exists(conn, "people", owner_id):
            raise ValueError(
                f"Project {pid!r} references missing person (owner_id) {owner_id!r}."
            )
        if status not in TASK_STATUSES:
            raise ValueError(
                f"Project {pid!r} has invalid status {status!r}."
            )
        conn.execute(
            "INSERT INTO projects (id, name, description, owner_id, status,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, str(name).strip(), rec.get("description"), owner_id,
             status, rec.get("created_at")),
        )


def _import_intakes(conn, records):
    for rec in records:
        iid = _require_id(rec, "intakes")
        if _exists(conn, "intakes", iid):
            continue
        title = rec.get("title")
        scope = rec.get("scope")
        requester_id = rec.get("requester_id")
        status = rec.get("status", "Pending")
        decided_by = rec.get("decided_by")
        project_id = rec.get("project_id")
        if not title or not str(title).strip():
            raise ValueError(f"Intake {iid!r} is missing a title.")
        if not scope or not str(scope).strip():
            raise ValueError(f"Intake {iid!r} is missing a scope.")
        if not requester_id or not _exists(conn, "people", requester_id):
            raise ValueError(
                f"Intake {iid!r} references missing person (requester_id) {requester_id!r}."
            )
        if status not in INTAKE_STATUSES:
            raise ValueError(
                f"Intake {iid!r} has invalid status {status!r}."
            )
        if decided_by and not _exists(conn, "people", decided_by):
            raise ValueError(
                f"Intake {iid!r} references missing person (decided_by) {decided_by!r}."
            )
        if project_id and not _exists(conn, "projects", project_id):
            raise ValueError(
                f"Intake {iid!r} references missing project {project_id!r}."
            )
        conn.execute(
            "INSERT INTO intakes (id, title, scope, description,"
            " requester_id, status, created_at, decided_by, decided_at,"
            " decision_reason, project_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (iid, str(title).strip(), str(scope).strip(),
             rec.get("description"), requester_id, status,
             rec.get("created_at"), decided_by, rec.get("decided_at"),
             rec.get("decision_reason"), project_id),
        )


def _import_reviews(conn, records):
    for rec in records:
        rid = _require_id(rec, "reviews")
        if _exists(conn, "reviews", rid):
            continue
        task_id = rec.get("task_id")
        reviewer_id = rec.get("reviewer_id")
        decision = rec.get("decision")
        if not task_id or not _exists(conn, "tasks", task_id):
            raise ValueError(
                f"Review {rid!r} references missing task {task_id!r}."
            )
        if not reviewer_id or not _exists(conn, "people", reviewer_id):
            raise ValueError(
                f"Review {rid!r} references missing person (reviewer_id) {reviewer_id!r}."
            )
        if decision not in ("Accepted", "Rejected"):
            raise ValueError(
                f"Review {rid!r} has invalid decision {decision!r}."
            )
        conn.execute(
            "INSERT INTO reviews (id, task_id, reviewer_id, decision,"
            " reason, decided_at) VALUES (?, ?, ?, ?, ?, ?)",
            (rid, task_id, reviewer_id, decision, rec.get("reason"),
             rec.get("decided_at")),
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
            raise ValueError(f"Milestone {mid!r} is missing a name.")
        if not project_id or not _exists(conn, "projects", project_id):
            raise ValueError(
                f"Milestone {mid!r} references missing project {project_id!r}."
            )
        if status not in MILESTONE_STATUSES:
            raise ValueError(
                f"Milestone {mid!r} has invalid status {status!r}."
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
            raise ValueError(f"Task {tid!r} is missing a title.")
        if not project_id or not _exists(conn, "projects", project_id):
            raise ValueError(
                f"Task {tid!r} references missing project {project_id!r}."
            )
        if assignee_id and not _exists(conn, "people", assignee_id):
            raise ValueError(
                f"Task {tid!r} references missing person (assignee_id) {assignee_id!r}."
            )
        if milestone_id:
            ms = conn.execute(
                "SELECT project_id FROM milestones WHERE id = ?",
                (milestone_id,),
            ).fetchone()
            if not ms:
                raise ValueError(
                    f"Task {tid!r} references missing milestone {milestone_id!r}."
                )
            if ms["project_id"] != project_id:
                raise ValueError(
                    "Task {!r}: milestone {!r} belongs to project {!r}, not {!r}.".format(tid, milestone_id, ms["project_id"], project_id)
                )
        if status not in TASK_STATUSES:
            raise ValueError(f"Task {tid!r} has invalid status {status!r}.")
        reviewer_id = rec.get("reviewer_id")
        if reviewer_id and not _exists(conn, "people", reviewer_id):
            raise ValueError(
                f"Task {tid!r} references missing person (reviewer_id) {reviewer_id!r}."
            )
        supersedes_task_id = rec.get("supersedes_task_id")
        if supersedes_task_id and not _exists(conn, "tasks",
                                              supersedes_task_id):
            raise ValueError(
                f"Task {tid!r} references missing task (supersedes_task_id) {supersedes_task_id!r}."
            )
        conn.execute(
            "INSERT INTO tasks (id, project_id, milestone_id, title,"
            " assignee_id, status, due_date, reviewer_id,"
            " supersedes_task_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tid, project_id, milestone_id, str(title).strip(),
             assignee_id, status, rec.get("due_date"), reviewer_id,
             supersedes_task_id),
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
                f"Evidence {eid!r} references missing task {task_id!r}."
            )
        if not submitted_by or not _exists(conn, "people", submitted_by):
            raise ValueError(
                f"Evidence {eid!r} references missing person (submitted_by) {submitted_by!r}."
            )
        if verified_by and not _exists(conn, "people", verified_by):
            raise ValueError(
                f"Evidence {eid!r} references missing person (verified_by) {verified_by!r}."
            )
        if not evidence_type or not str(evidence_type).strip():
            raise ValueError(f"Evidence {eid!r} is missing evidence_type.")
        conn.execute(
            "INSERT INTO evidence (id, task_id, submitted_by, evidence_type,"
            " url_or_path, submitted_at, verified_by, verified_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, task_id, submitted_by, str(evidence_type).strip(),
             rec.get("url_or_path"), rec.get("submitted_at"), verified_by,
             rec.get("verified_at")),
        )
