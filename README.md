# HR-PM Map — Human-Resource Project Management Map

**Version:** 0.3.0
**License:** MIT
**Purpose:** Open-source HR/project-management information architecture

## Implementation status

| Component              | Status  |
|------------------------|---------|
| Repository structure   | Present |
| Data model             | Present |
| JSON schemas           | Present |
| Python modules         | Present |
| Tests                  | Present |
| CLI (`hrpm`)           | Present |
| JSON ↔ SQLite sync     | Present |
| Audit trail            | Present |
| Dashboard queries      | Present |
| External integrations  | None    |
| Production deployment  | None    |
| HR automation          | None    |

## Status register — v0.3.0

**IMPLEMENTATION**

| Component         | State       |
|-----------------|-------------|
| Audit events    | IMPLEMENTED |
| Dashboard queries | IMPLEMENTED |
| CLI dashboard   | IMPLEMENTED |

**TEST**

| Concern                  | State  |
|--------------------------|--------|
| Audit transition coverage | TESTED |
| Append-only behavior      | TESTED |
| Invalid transition        | TESTED |
| Dashboard/query behavior  | TESTED |

| Concern      | State           |
|--------------|-----------------|
| INTEGRATION  | NOT ESTABLISHED |
| RUNTIME      | NOT OBSERVED    |
| EVIDENCE     | NOT ESTABLISHED |
| VERIFICATION | NOT ESTABLISHED |
| DEPLOYMENT   | NONE            |
| PROMOTION    | NONE            |

A passing test demonstrates implemented behavior in the test environment; it
does not establish production deployment or real-world verification.

> The dashboard reports state; the audit trail records the transition;
> neither one creates evidence of an event that did not occur.

This repository is the **source of truth for the information structure** —
v0.3 adds accountability and visibility: every transition is audit-logged,
and read-only dashboards report outstanding, submitted, completed, and
verified work. Planned increments: `v0.4` basic web interface →
`v0.5` human approval and evidence tracking →
`v1.0` usable HR/project-management product.

A single source-of-truth map for **people, projects, and obligations** — the
foundational data layer for human-resource and project-management workflows.

## The core idea

Every piece of work in an organization follows one backbone:

```
Person
  ↓
Responsibility
  ↓
Project
  ↓
Task
  ↓
Deliverable
  ↓
Evidence
  ↓
Verification
  ↓
Completion
```

A **Person** takes **Responsibility** for a **Project**. The project breaks into
**Tasks**. Each task produces a **Deliverable**, backed by **Evidence**, which a
different person **Verifies**. Verified work reaches **Completion**.

v0.2 models exactly this chain — nothing more. No payroll, no recruiting
automation, no AI orchestration, no cloud services. Just a clean, local,
auditable data map you can run for free.

## Task lifecycle (v0.3)

```
Proposed → Assigned → In Progress → Submitted → Completed → Verified
```

The only backward move allowed is `Assigned → Proposed` (un-assigning work).

### Task state rules

- **Completed** requires evidence: a task cannot be marked Completed unless
  at least one evidence record exists for it.
- **Verified** requires evidence + verifier: a task cannot be marked Verified
  unless an evidence record was verified by someone other than the submitter.

### Integrity rules

- No evidence → cannot become Completed.
- No verifier → cannot become Verified.
- Missing referenced entity → operation refused.
- Invalid transition → operation refused.
- No synthetic evidence generation: the system records what happened; it
  does not manufacture evidence that something happened.

See [docs/workflow.md](docs/workflow.md) for who does what at each stage.

## Quickstart

Requires Python 3.8+ — standard library only, no dependencies to install.

```bash
cd hr-project-map

# 1. Initialize the SQLite database (creates tables)
python3 -c "from src.db import init_db; init_db('hrpm.db')"

# 2. Add a person (Manager)
python3 -c "
from src import people
pid = people.add_person('hrpm.db', name='Jane Doe', role='Manager', email='jane@example.com')
print('person id:', pid)"

# 3. Add a project owned by that person
python3 -c "
from src import people, projects
owner = people.list_people('hrpm.db')[0]['id']
prj = projects.add_project('hrpm.db', name='Onboarding Revamp', description='Redesign new-hire onboarding', owner_id=owner)
print('project id:', prj)"

# 4. Add a task, assign it, and move it through the lifecycle
python3 -c "
from src import projects, tasks, people
prj = projects.list_projects('hrpm.db')[0]['id']
worker = people.add_person('hrpm.db', name='Sam Lee', role='Employee', email='sam@example.com')
t = tasks.add_task('hrpm.db', prj, title='Draft onboarding checklist', due_date='2026-10-15')
tasks.assign_task('hrpm.db', t, worker)                 # Proposed -> Assigned
tasks.update_task_status('hrpm.db', t, 'In Progress')   # Assigned -> In Progress
print('task ready for work:', t)"

# 5. Submit evidence and complete the task (evidence-gated)
python3 -c "
from src import people, projects, tasks, evidence, completion
mgr = [p for p in people.list_people('hrpm.db') if p['role'] == 'Manager'][0]['id']
worker = [p for p in people.list_people('hrpm.db') if p['role'] == 'Employee'][0]['id']
prj = projects.list_projects('hrpm.db')[0]['id']
t = tasks.list_tasks_by_project('hrpm.db', prj)[0]['id']
e = evidence.submit_evidence('hrpm.db', t, submitted_by=worker,
                             evidence_type='document', url_or_path='docs/checklist-v1.md')
completion.complete_task('hrpm.db', t)            # Submitted -> Completed (evidence exists)
evidence.verify_evidence('hrpm.db', e, verified_by=mgr)  # manager != worker
completion.verify_task('hrpm.db', t, mgr)         # Completed -> Verified
print('task verified:', tasks.get_task('hrpm.db', t)['status'])"
```

A cleaner end-to-end script:

```bash
# Run the full lifecycle demo (see tests for the canonical flow)
python3 -m unittest discover -s tests -v
```

## CLI usage (v0.3)

The `hrpm` script (repo root, stdlib only) wraps the common operations.
Default database is `./hrpm.db`; override with `--db PATH`.

```bash
# People are added via Python (no CLI command yet in v0.3)
python3 -c "
from src import db, people
db.init_db('hrpm.db')
print(people.add_person('hrpm.db', 'Jane Doe', 'Manager'))"

# Projects
./hrpm project create --name "Website" --owner <PERSON_ID> --description "New site"
./hrpm project list
./hrpm project show <PROJECT_ID>        # project + its milestones + tasks

# Tasks
./hrpm task create --project <PROJECT_ID> --title "Write copy" --assignee <PERSON_ID>
./hrpm task list --project <PROJECT_ID>

# Evidence (task must be In Progress; moves it to Submitted)
./hrpm evidence add --task <TASK_ID> --by <PERSON_ID> --type document --ref docs/copy.md
```

### Dashboard (v0.3, read-only)

Dashboard commands report database state and never modify it:

```bash
./hrpm dashboard outstanding [--project <PROJECT_ID>]
./hrpm dashboard submitted   [--project <PROJECT_ID>]
./hrpm dashboard completed   [--project <PROJECT_ID>]
./hrpm dashboard verified    [--project <PROJECT_ID>]
```

### Audit trail (v0.3)

Every accepted state transition on a task, milestone, or project emits
exactly one audit event (`audit_events` table): entity, previous state, new
state, actor, and UTC timestamp. Refused or invalid transitions emit no
event. The trail is append-only — `src/audit.py` exposes no update or
delete API, so history cannot be rewritten.

```bash
python3 -c "
from src import audit
for e in audit.get_events('hrpm.db', 'task', '<TASK_ID>'):
    print(e['prev_state'], '->', e['new_state'], 'by', e['actor_id'], e['timestamp'])"
```

Completion and verification stay in Python for v0.2 (they are judgment
calls, not data entry):

```bash
python3 -c "
from src import completion
completion.complete_task('hrpm.db', '<TASK_ID>')   # requires evidence
completion.verify_task('hrpm.db', '<TASK_ID>', '<VERIFIER_ID>')"
```

## JSON <-> SQLite sync (v0.2)

```bash
python3 -c "
from src import sync
sync.export_to_json('hrpm.db', 'data/')   # DB -> data/*.json
sync.import_from_json('hrpm.db', 'data/') # data/*.json -> DB
"
```

Import validates every record: enum fields must be legal and every foreign
key must reference an existing entity, otherwise the record is refused with a
clear error. Records whose id already exists are skipped.

## Project structure

```
hr-project-map/
├── README.md            # This file
├── LICENSE              # MIT
├── .gitignore
├── hrpm                 # CLI: project/task/evidence/dashboard commands (v0.3)
├── docs/
│   ├── architecture.md  # Data model and entity definitions
│   ├── workflow.md      # Lifecycle stages and responsibilities
│   └── governance.md    # Scope, approval, and evidence rules
├── schema/              # JSON Schemas for each entity
│   ├── person.schema.json
│   ├── project.schema.json
│   ├── milestone.schema.json
│   ├── task.schema.json
│   └── evidence.schema.json
├── data/                # Seed JSON files (empty; examples in comments)
│   ├── people.json
│   ├── projects.json
│   ├── milestones.json
│   ├── tasks.json
│   └── evidence.json
├── src/                 # Python implementation (stdlib only)
│   ├── db.py            # SQLite schema + init_db()
│   ├── audit.py         # Append-only audit trail (v0.3)
│   ├── queries.py       # Read-only dashboard queries (v0.3)
│   ├── people.py        # Person CRUD
│   ├── projects.py      # Project CRUD + status
│   ├── milestones.py    # Milestone CRUD + forward-only transitions
│   ├── tasks.py         # Task CRUD + enforced status transitions + evidence gates
│   ├── evidence.py      # Evidence submission + independent verification
│   ├── completion.py    # Evidence-gated complete_task() / verify_task()
│   └── sync.py          # JSON <-> SQLite import/export
└── tests/
    ├── test_workflow.py # Full lifecycle test on a temp database
    ├── test_v02.py      # Evidence gates, milestones, sync, transition order
    └── test_v03.py      # Audit trail + dashboard queries (v0.3)
```

## v0.3 scope

**Added in v0.3:**
- Append-only audit events (`src/audit.py`, `audit_events` table): one event
  per accepted transition — entity, prev/new state, actor, UTC timestamp.
  Refused transitions emit no event; no update/delete API exists.
- Read-only dashboard/query layer (`src/queries.py`): outstanding,
  submitted, completed, verified task views + per-project summary.
- `hrpm dashboard` CLI commands (read-only; report state, never modify it).
- `actor_id` parameter on all transition functions, recorded in the audit
  event.

**In scope (carried from v0.2):**
- Person / Project / Milestone / Task / Evidence entities with JSON Schemas
- SQLite persistence via `src/db.py`
- Enforced task status transitions with evidence gates
- Evidence submission and independent verification (no self-verification)
- `hrpm` CLI for project/task/evidence operations
- JSON ↔ SQLite import/export with FK validation
- Lifecycle unit tests (32 tests, all passing)

**Explicitly out of scope:**
- Payroll, benefits, or recruiting automation
- Web UI or authentication
- AI agents or orchestration
- Cloud hosting or paid services
- Employee surveillance of any kind

## Data model (detail)

See [docs/architecture.md](docs/architecture.md) for entity definitions and
[docs/governance.md](docs/governance.md) for the rules that keep the map
trustworthy: who can approve, what counts as evidence, and why verification
must be independent.
