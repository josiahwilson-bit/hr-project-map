# HR-PM Map — Human-Resource Project Management Map

**Version:** 0.4.0
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
| Project intake         | Present |
| Human review workflow  | Present |
| External integrations  | None    |
| Production deployment  | None    |
| HR automation          | None    |

## Status register — v0.4.0

**IMPLEMENTATION**

| Component         | State       |
|-----------------|-------------|
| Audit events    | IMPLEMENTED |
| Dashboard queries | IMPLEMENTED |
| CLI dashboard   | IMPLEMENTED |
| Project intake  | IMPLEMENTED |
| Human review    | IMPLEMENTED |

**TEST**

| Concern                      | State  |
|------------------------------|--------|
| Audit transition coverage     | TESTED |
| Append-only behavior          | TESTED |
| Invalid transition            | TESTED |
| Dashboard/query behavior      | TESTED |
| Intake validation             | TESTED |
| Review transitions            | TESTED |
| Terminal rejection            | TESTED |
| Rework linkage                | TESTED |

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

> Rejected is a recorded terminal outcome, not an invitation to rewrite
> history. Rework creates a new task and preserves the relationship to the
> original.

This repository is the **source of truth for the information structure** —
v0.4 answers one question: can a real organization submit a piece of work,
have a human review it, and preserve an auditable record of that decision?
Intake stages structured project requests; human review gates submitted work
before completion; every decision is audit-logged. Planned increments:
`v0.5` basic web interface → `v1.0` usable HR/project-management product.

A single source-of-truth map for **people, projects, and obligations** — the
foundational data layer for human-resource and project-management workflows.

## The core idea

Every piece of work in an organization follows one backbone:

```
Intake
  ↓
Person
  ↓
Responsibility
  ↓
Project
  ↓
Milestone
  ↓
Task
  ↓
Deliverable
  ↓
Evidence
  ↓
Review (Under Review → Accepted | Rejected)
  ↓
Verification
  ↓
Completion
```

A structured **Intake** (explicit requester, explicit scope) becomes a
**Project** on approval. A **Person** takes **Responsibility** for the
project, which breaks into **Milestones** and **Tasks**. Each task produces
a **Deliverable**, backed by **Evidence**. Submitted work enters human
**Review**: a named reviewer **Accepts** it (forward to completion) or
**Rejects** it — Rejected is terminal; rework is a new task referencing the
original. Accepted work with evidence reaches **Completion**; independently
verified work reaches **Verification**.

v0.4 models exactly this chain — nothing more. No payroll, no recruiting
automation, no AI orchestration, no cloud services. Just a clean, local,
auditable data map you can run for free.

## Task lifecycle (v0.4)

```
Proposed → Assigned → In Progress → Submitted → Under Review → Accepted → Completed → Verified
                                              ↘ Rejected (TERMINAL)
```

The only backward move allowed is `Assigned → Proposed` (un-assigning work).
`Rejected` has no outgoing transitions: a rejected task can never be
reopened — rework is a new task whose `supersedes_task_id` points at the
original.

### Task state rules

- **Under Review** requires a reviewer: only `Submitted` tasks enter review,
  and the reviewer must be an existing, active person.
- **Accepted / Rejected** require the deciding reviewer to be the one who
  started the review. Rejection additionally requires a recorded reason.
- **Accepted**, **Completed**, and **Verified** are three separate facts:
  acceptance is not completion, and completion is not verification.
- **Completed** requires evidence: a task cannot be marked Completed unless
  at least one evidence record exists for it.
- **Verified** requires evidence + verifier: a task cannot be marked Verified
  unless an evidence record was verified by someone other than the submitter.

### Integrity rules

- No reviewer → no review decision.
- No rejection reason → rejection refused.
- No evidence → cannot become Completed.
- No verifier → cannot become Verified.
- Rejected → cannot be reopened; rework creates a new task.
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

# 5. Submit evidence, review, complete, and verify (all gates enforced)
python3 -c "
from src import people, projects, tasks, evidence, review, completion
mgr = [p for p in people.list_people('hrpm.db') if p['role'] == 'Manager'][0]['id']
worker = [p for p in people.list_people('hrpm.db') if p['role'] == 'Employee'][0]['id']
prj = projects.list_projects('hrpm.db')[0]['id']
t = tasks.list_tasks_by_project('hrpm.db', prj)[0]['id']
e = evidence.submit_evidence('hrpm.db', t, submitted_by=worker,
                             evidence_type='document', url_or_path='docs/checklist-v1.md')
review.start_review('hrpm.db', t, mgr)        # Submitted -> Under Review
review.accept_review('hrpm.db', t, mgr, note='meets spec')  # -> Accepted
completion.complete_task('hrpm.db', t)        # Accepted -> Completed (evidence exists)
evidence.verify_evidence('hrpm.db', e, verified_by=mgr)  # manager != worker
completion.verify_task('hrpm.db', t, mgr)     # Completed -> Verified
print('task verified:', tasks.get_task('hrpm.db', t)['status'])"
```

A cleaner end-to-end script:

```bash
# Run the full lifecycle demo (see tests for the canonical flow)
python3 -m unittest discover -s tests -v
```

## CLI usage (v0.4)

The `hrpm` script (repo root, stdlib only) wraps the common operations.
Default database is `./hrpm.db`; override with `--db PATH`.

```bash
# People are added via Python (no CLI command yet in v0.4)
python3 -c "
from src import db, people
db.init_db('hrpm.db')
print(people.add_person('hrpm.db', 'Jane Doe', 'Manager'))"

# Intake: stage a structured project request, then decide it
./hrpm intake create --title "Portal refresh" --scope "Redesign login pages" \
    --requester <PERSON_ID> --description "Q4 ask"
./hrpm intake list [--status Pending|Approved|Rejected]
./hrpm intake approve <INTAKE_ID> --by <PERSON_ID>   # creates exactly one project
./hrpm intake reject <INTAKE_ID> --by <PERSON_ID> --reason "Out of scope"

# Projects
./hrpm project create --name "Website" --owner <PERSON_ID> --description "New site"
./hrpm project list
./hrpm project show <PROJECT_ID>        # project + its milestones + tasks

# Tasks
./hrpm task create --project <PROJECT_ID> --title "Write copy" --assignee <PERSON_ID>
./hrpm task list --project <PROJECT_ID>
./hrpm task rework --task <REJECTED_TASK_ID> [--title "New title"] [--assignee <PERSON_ID>]

# Evidence (task must be In Progress; moves it to Submitted)
./hrpm evidence add --task <TASK_ID> --by <PERSON_ID> --type document --ref docs/copy.md

# Human review (task must be Submitted; reviewer must be active)
./hrpm review start  --task <TASK_ID> --reviewer <PERSON_ID>   # -> Under Review
./hrpm review accept --task <TASK_ID> --reviewer <PERSON_ID> [--note "meets spec"]
./hrpm review reject --task <TASK_ID> --reviewer <PERSON_ID> --reason "does not match spec"
```

### Dashboard (v0.4, read-only)

Dashboard commands report database state and never modify it:

```bash
./hrpm dashboard outstanding [--project <PROJECT_ID>]  # Proposed/Assigned/In Progress
./hrpm dashboard submitted   [--project <PROJECT_ID>]  # Submitted/Under Review
./hrpm dashboard completed   [--project <PROJECT_ID>]  # Completed (evidence, unverified)
./hrpm dashboard verified    [--project <PROJECT_ID>]  # Verified (independently verified)
./hrpm dashboard rejected    [--project <PROJECT_ID>]  # Rejected (terminal)
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

Completion and verification stay in Python for v0.4 (they are judgment
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
├── hrpm                 # CLI: intake/review/project/task/evidence/dashboard (v0.4)
├── docs/
│   ├── architecture.md  # Data model and entity definitions
│   ├── workflow.md      # Lifecycle stages and responsibilities
│   └── governance.md    # Scope, approval, and evidence rules
├── schema/              # JSON Schemas for each entity
│   ├── person.schema.json
│   ├── project.schema.json
│   ├── milestone.schema.json
│   ├── task.schema.json
│   ├── evidence.schema.json
│   └── intake.schema.json
├── data/                # Seed JSON files (empty; examples in comments)
│   ├── people.json
│   ├── projects.json
│   ├── milestones.json
│   ├── tasks.json
│   ├── evidence.json
│   └── intakes.json
├── src/                 # Python implementation (stdlib only)
│   ├── db.py            # SQLite schema + init_db()
│   ├── audit.py         # Append-only audit trail (v0.3)
│   ├── queries.py       # Read-only dashboard queries (v0.4)
│   ├── intake.py        # Structured project intake (v0.4)
│   ├── review.py        # Human review workflow (v0.4)
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
    ├── test_v03.py      # Audit trail + dashboard queries (v0.3)
    └── test_v04.py      # Intake + human review workflow (v0.4)
```

## v0.4 scope

**Added in v0.4:**
- Structured project intake (`src/intake.py`, `intakes` table): explicit
  requester, explicit scope, required fields, staged `Pending` state;
  approval creates exactly one project; re-approval refused; rejection
  requires a reason.
- Human review workflow (`src/review.py`, `reviews` table):
  `Submitted → Under Review → Accepted → Completed → Verified`, with
  `Under Review → Rejected` as a terminal branch.
- Review integrity rules: reviewer required and recorded on the task; only
  the reviewing reviewer can accept or reject; rejection requires a reason;
  acceptance emits an audit event; completion requires evidence;
  verification requires evidence plus an independent verifier.
- Rework as lineage, not rewriting: `tasks.rework_task()` creates a new
  task whose `supersedes_task_id` references the rejected original, which
  is left untouched and unreopenable.
- `hrpm intake create/list/approve/reject`, `hrpm review start/accept/reject`,
  `hrpm task rework`, and `hrpm dashboard rejected`.

**In scope (carried from v0.3):**
- Person / Project / Milestone / Task / Evidence entities with JSON Schemas
- SQLite persistence via `src/db.py`
- Enforced task status transitions with evidence gates
- Evidence submission and independent verification (no self-verification)
- `hrpm` CLI for project/task/evidence operations
- JSON ↔ SQLite import/export with FK validation
- Append-only audit trail and read-only dashboard queries
- Lifecycle unit tests (49 tests, all passing)

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
