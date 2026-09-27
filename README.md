# HR-PM Map — Human-Resource Project Management Map

**Version:** 0.2.0
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
| External integrations  | None    |
| Production deployment  | None    |
| HR automation          | None    |

## Status register — v0.2.0

| Concern     | State           |
|-------------|-----------------|
| DESIGN      | IMPLEMENTED     |
| CODE        | IMPLEMENTED     |
| TESTS       | TESTED          |
| INTEGRATION | NOT ESTABLISHED |
| PRODUCTION  | NOT DEPLOYED    |
| RUNTIME     | NOT OBSERVED    |

A passing test demonstrates implemented behavior in the test environment; it
does not establish production deployment or real-world verification.

This repository is the **source of truth for the information structure** —
v0.2 makes the map persistent and queryable. Planned increments:
`v0.3` project/task API → `v0.4` basic web interface →
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

## Task lifecycle (v0.2)

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

## CLI usage (v0.2)

The `hrpm` script (repo root, stdlib only) wraps the common operations.
Default database is `./hrpm.db`; override with `--db PATH`.

```bash
# People are added via Python (no CLI command yet in v0.2)
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
├── hrpm                 # CLI: project/task/evidence commands (v0.2)
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
│   ├── people.py        # Person CRUD
│   ├── projects.py      # Project CRUD + status
│   ├── milestones.py    # Milestone CRUD + forward-only transitions
│   ├── tasks.py         # Task CRUD + enforced status transitions + evidence gates
│   ├── evidence.py      # Evidence submission + independent verification
│   ├── completion.py    # Evidence-gated complete_task() / verify_task()
│   └── sync.py          # JSON <-> SQLite import/export
└── tests/
    ├── test_workflow.py # Full lifecycle test on a temp database
    └── test_v02.py      # Evidence gates, milestones, sync, transition order
```

## v0.2 scope

**Added in v0.2:**
- Milestone entity (project checkpoints, forward-only lifecycle, no evidence gate)
- JSON ↔ SQLite import/export (`src/sync.py`) with FK validation
- `hrpm` CLI for project/task/evidence operations
- Evidence-gated completion: Completed requires evidence, Verified requires
  an independent verifier (`src/completion.py`)

**In scope (carried from v0.1):**
- Person / Project / Milestone / Task / Evidence entities with JSON Schemas
- SQLite persistence via `src/db.py`
- Enforced task status transitions
- Evidence submission and independent verification (no self-verification)
- Lifecycle unit tests (20 tests, all passing)

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
