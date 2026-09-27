# HR-PM Map — Human-Resource Project Management Map

**Version:** 0.1.0
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
| External integrations  | None    |
| Production deployment  | None    |
| HR automation          | None    |

This repository is the **source of truth for the information structure** —
v0.1 is the data model, not a working HR platform. Planned increments:
`v0.2` SQLite persistence → `v0.3` project/task API → `v0.4` basic web
interface → `v0.5` human approval and evidence tracking →
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

v0.1 models exactly this chain — nothing more. No payroll, no recruiting
automation, no AI orchestration, no cloud services. Just a clean, local,
auditable data map you can run for free.

## Task lifecycle

```
Proposed → Assigned → In Progress → Submitted → Verified → Completed
```

The only backward move allowed is `Assigned → Proposed` (un-assigning work).
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

# 5. Submit evidence and verify it (verifier must differ from submitter)
python3 -c "
from src import people, projects, tasks, evidence
mgr = [p for p in people.list_people('hrpm.db') if p['role'] == 'Manager'][0]['id']
worker = [p for p in people.list_people('hrpm.db') if p['role'] == 'Employee'][0]['id']
prj = projects.list_projects('hrpm.db')[0]['id']
t = tasks.list_tasks_by_project('hrpm.db', prj)[0]['id']
e = evidence.submit_evidence('hrpm.db', t, submitted_by=worker,
                             evidence_type='document', url_or_path='docs/checklist-v1.md')
evidence.verify_evidence('hrpm.db', e, verified_by=mgr)  # manager != worker
tasks.update_task_status('hrpm.db', t, 'Completed')      # Verified -> Completed
print('task completed:', tasks.get_task('hrpm.db', t)['status'])"
```

A cleaner end-to-end script:

```bash
# Run the full lifecycle demo (see tests for the canonical flow)
python3 -m unittest discover -s tests -v
```

## Project structure

```
hr-project-map/
├── README.md            # This file
├── LICENSE              # MIT
├── .gitignore
├── docs/
│   ├── architecture.md  # Data model and entity definitions
│   ├── workflow.md      # Lifecycle stages and responsibilities
│   └── governance.md    # Scope, approval, and evidence rules
├── schema/              # JSON Schemas for each entity
│   ├── person.schema.json
│   ├── project.schema.json
│   ├── task.schema.json
│   └── evidence.schema.json
├── data/                # Seed JSON files (empty; examples in comments)
│   ├── people.json
│   ├── projects.json
│   ├── tasks.json
│   └── evidence.json
├── src/                 # Python implementation (stdlib only)
│   ├── db.py            # SQLite schema + init_db()
│   ├── people.py        # Person CRUD
│   ├── projects.py      # Project CRUD + status
│   ├── tasks.py         # Task CRUD + enforced status transitions
│   └── evidence.py      # Evidence submission + independent verification
└── tests/
    └── test_workflow.py # Full lifecycle test on a temp database
```

## v0.1 scope

**In scope:**
- Person / Project / Task / Evidence entities with JSON Schemas
- SQLite persistence via `src/db.py`
- Enforced task status transitions
- Evidence submission and independent verification (no self-verification)
- Full lifecycle unit test

**Explicitly out of scope for v0.1:**
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
