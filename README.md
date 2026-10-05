# HR-PM Map — Human-Resource Project Management Map

[![CI](https://github.com/josiahwilson-bit/hr-project-map/actions/workflows/ci.yml/badge.svg)](https://github.com/josiahwilson-bit/hr-project-map/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/josiahwilson-bit/hr-project-map/badge)](https://scorecard.dev/viewer/?uri=github.com/josiahwilson-bit/hr-project-map)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Track people, projects, tasks, and evidence in a local SQLite database where nothing can be marked complete without proof — and no decision can be rewritten afterward.**

Standard library only. No dependencies, no cloud, no accounts. Clone it and run.

## Quickstart

Requires Python 3.8+. Copy, paste, run — about two minutes, end to end.

```bash
git clone https://github.com/josiahwilson-bit/hr-project-map.git
cd hr-project-map

# 1. Create the database
python3 -c "from src.db import init_db; init_db('hrpm.db')"

# 2. Add two people (Python — there is no CLI command for people in v0.4)
MGR=$(python3 -c "from src import people; print(people.add_person('hrpm.db', 'Jane Doe', 'Manager'))")
WORKER=$(python3 -c "from src import people; print(people.add_person('hrpm.db', 'Sam Lee', 'Employee'))")

# 3. Create a project and a task
./hrpm project create --name "Onboarding Revamp" --owner $MGR --description "Redesign new-hire onboarding"
PRJ=$(python3 -c "from src import projects; print(projects.list_projects('hrpm.db')[0]['id'])")
./hrpm task create --project $PRJ --title "Draft onboarding checklist" --assignee $WORKER
TASK=$(python3 -c "from src import tasks; print(tasks.list_tasks_by_project('hrpm.db', '$PRJ')[0]['id'])")

# 4. Move the task to In Progress (Python — no CLI command for this transition in v0.4)
python3 -c "from src import tasks; tasks.update_task_status('hrpm.db', '$TASK', 'In Progress')"

# 5. Submit evidence, then run human review
./hrpm evidence add --task $TASK --by $WORKER --type document --ref docs/checklist-v1.md
./hrpm review start --task $TASK --reviewer $MGR
./hrpm review accept --task $TASK --reviewer $MGR --note "meets spec"

# 6. Complete and verify (Python — completion and verification are judgment
#    calls, so they stay out of the CLI in v0.4)
python3 -c "
from src import evidence, completion
evs = evidence.list_evidence_for_task('hrpm.db', '$TASK')
evidence.verify_evidence('hrpm.db', evs[0]['id'], verified_by='$MGR')
completion.complete_task('hrpm.db', '$TASK')
completion.verify_task('hrpm.db', '$TASK', '$MGR')
print('task verified')
"

# 7. See it on the read-only dashboard
./hrpm dashboard verified
```

You just ran the full lifecycle: intake-ready project → assigned task → evidence → human review → completion → independent verification — with every transition audit-logged. Try breaking it: complete a task with no evidence, verify your own evidence, or reopen a rejected task. All three are refused.

Run the test suite any time: `python3 -m unittest discover -s tests -v` (57 tests).

## What it is

A single source-of-truth data model for HR and project-management work:

```
Person → Responsibility → Project → Milestone → Task → Deliverable
→ Evidence → Review → Verification → Completion
```

- **Intake:** structured project requests with an explicit requester and scope. Approval creates exactly one project; rejection requires a reason.
- **Human review:** submitted work goes `Submitted → Under Review → Accepted | Rejected`. The reviewer who starts the review is the only one who can decide it.
- **Evidence gates:** a task cannot become Completed without evidence, and cannot become Verified unless someone *other than the submitter* verified that evidence.
- **Rejected is terminal:** a rejected task can never be reopened. Rework is a new task that references the original — history is preserved, not rewritten.
- **Append-only audit trail:** every accepted state transition emits exactly one audit event (entity, previous state, new state, actor, UTC timestamp). Refused transitions emit nothing. There is no update or delete API for the trail.
- **Read-only dashboards:** `outstanding`, `submitted`, `completed`, `verified`, `rejected` — they report database state and never modify it.

## What it is not

No payroll, no recruiting automation, no web UI, no authentication, no AI agents, no cloud hosting, no paid services, no employee surveillance. A clean, local, auditable data map you can run for free.

## CLI reference (v0.4)

Default database is `./hrpm.db`; override any command with `--db PATH`.

```bash
# Projects
hrpm project create --name NAME --owner OWNER_ID [--description DESC]
hrpm project list
hrpm project show PROJECT_ID

# Tasks
hrpm task create --project PROJECT_ID --title TITLE [--assignee PERSON_ID] [--milestone MILESTONE_ID]
hrpm task list --project PROJECT_ID
hrpm task rework --task TASK_ID [--title TITLE] [--assignee PERSON_ID]

# Evidence (task must be In Progress; moves it to Submitted)
hrpm evidence add --task TASK_ID --by PERSON_ID --type TYPE --ref REF

# Human review (task must be Submitted; reviewer must be an active person)
hrpm review start --task TASK_ID --reviewer PERSON_ID
hrpm review accept --task TASK_ID --reviewer PERSON_ID [--note NOTE]
hrpm review reject --task TASK_ID --reviewer PERSON_ID --reason REASON

# Intake
hrpm intake create --title TITLE --scope SCOPE --requester PERSON_ID [--description DESC]
hrpm intake list [--status Pending|Approved|Rejected]
hrpm intake approve INTAKE_ID --by PERSON_ID
hrpm intake reject INTAKE_ID --by PERSON_ID --reason REASON

# Dashboards (read-only)
hrpm dashboard outstanding|submitted|completed|verified|rejected [--project PROJECT_ID]
```

People are managed via Python (`src/people.py`) — roles are `Employee`, `Contractor`, `Manager`, `Client`. Completion and verification stay in Python (`src/completion.py`) because they are judgment calls. JSON ↔ SQLite sync lives in `src/sync.py` with foreign-key validation on import.

## Project structure

```
hr-project-map/
├── README.md            # this file
├── LICENSE              # MIT
├── hrpm                 # CLI (stdlib only)
├── docs/
│   ├── architecture.md  # entity definitions and data model
│   ├── workflow.md      # lifecycle stages and who does what
│   └── governance.md    # scope, approval, and evidence rules
├── schema/              # JSON Schemas per entity
├── src/                 # Python implementation (stdlib only)
├── tests/               # 57 tests, all passing
└── data/                # seed JSON (empty by default)
```

## Docs

- [Architecture](docs/architecture.md) — entities, relationships, and the data model
- [Workflow](docs/workflow.md) — lifecycle stages, transitions, and responsibilities
- [Governance](docs/governance.md) — who can approve, what counts as evidence, why verification must be independent
- [Contributing](CONTRIBUTING.md) — how to contribute
- [Security](SECURITY.md) — how to report vulnerabilities

## Tester feedback

Tried the demo or the quickstart? Tell us what happened — a short honest
report is the most useful thing you can give us:
[open a tester-feedback issue](https://github.com/josiahwilson-bit/hr-project-map/issues/new?template=tester-feedback.yml)
or post in [Discussions](https://github.com/josiahwilson-bit/hr-project-map/discussions).
Two questions are required ("did it work?", "what happened and what did you
think?"); everything else is optional. Please don't paste credentials, API
keys, proprietary code, or personal data — the demo uses synthetic data.
Stars and forks are appreciated but are never counted as usage evidence.

## Status

**v0.4.0** (current): structured intake, human review workflow, evidence-gated completion, append-only audit trail, read-only dashboards, JSON ↔ SQLite sync. 57 tests passing in CI (Ruff, Bandit, OpenSSF Scorecard).

**Planned:** `v0.5` basic web interface → `v1.0` usable HR/project-management product.

A passing test demonstrates behavior in the test environment; it does not establish production deployment. This is a young project under active development — issues and feedback are welcome.
