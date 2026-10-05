# Status register — v0.4.0

Implementation status tables formerly shown in the README, preserved here verbatim so the README can stay focused on onboarding.

## Implementation status

| Component | Status |
|------------------------|---------|
| Repository structure | Present |
| Data model | Present |
| JSON schemas | Present |
| Python modules | Present |
| Tests | Present |
| CLI (`hrpm`) | Present |
| JSON ↔ SQLite sync | Present |
| Audit trail | Present |
| Dashboard queries | Present |
| Project intake | Present |
| Human review workflow | Present |
| External integrations | None |
| Production deployment | None |
| HR automation | None |

## Status register — v0.4.0

**IMPLEMENTATION**

| Component | State |
|-----------------|-------------|
| Audit events | IMPLEMENTED |
| Dashboard queries | IMPLEMENTED |
| CLI dashboard | IMPLEMENTED |
| Project intake | IMPLEMENTED |
| Human review | IMPLEMENTED |

**TEST**

| Concern | State |
|------------------------------|--------|
| Audit transition coverage | TESTED |
| Append-only behavior | TESTED |
| Invalid transition | TESTED |
| Dashboard/query behavior | TESTED |
| Intake validation | TESTED |
| Review transitions | TESTED |
| Terminal rejection | TESTED |
| Rework linkage | TESTED |

| Concern | State |
|--------------|-----------------|
| INTEGRATION | NOT ESTABLISHED |
| RUNTIME | NOT OBSERVED |
| EVIDENCE | NOT ESTABLISHED |
| VERIFICATION | NOT ESTABLISHED |
| DEPLOYMENT | NONE |
| PROMOTION | NONE |

A passing test demonstrates implemented behavior in the test environment; it does not establish production deployment or real-world verification.

> Rejected is a recorded terminal outcome, not an invitation to rewrite history. Rework creates a new task and preserves the relationship to the original.

This repository is the **source of truth for the information structure** — v0.4 answers one question: can a real organization submit a piece of work, have a human review it, and preserve an auditable record of that decision?

Intake stages structured project requests; human review gates submitted work before completion; every decision is audit-logged. Planned increments: `v0.5` basic web interface → `v1.0` usable HR/project-management product.

A single source-of-truth map for **people, projects, and obligations** — the foundational data layer for human-resource and project-management workflows.

## v0.4 scope

**Added in v0.4:**

- Structured project intake (`src/intake.py`, `intakes` table): explicit requester, explicit scope, required fields, staged `Pending` state; approval creates exactly one project; re-approval refused; rejection requires a reason.
- Human review workflow (`src/review.py`, `reviews` table): `Submitted → Under Review → Accepted → Completed → Verified`, with `Under Review → Rejected` as a terminal branch.
- Review integrity rules: reviewer required and recorded on the task; only the reviewing reviewer can accept or reject; rejection requires a reason; acceptance emits an audit event; completion requires evidence; verification requires evidence plus an independent verifier.
- Rework as lineage, not rewriting: `tasks.rework_task()` creates a new task whose `supersedes_task_id` references the rejected original, which is left untouched and unreopenable.
- `hrpm intake create/list/approve/reject`, `hrpm review start/accept/reject`, `hrpm task rework`, and `hrpm dashboard rejected`.

**In scope (carried from v0.3):**

- Person / Project / Milestone / Task / Evidence entities with JSON Schemas
- SQLite persistence via `src/db.py`
- Enforced task status transitions with evidence gates
- Evidence submission and independent verification (no self-verification)
- `hrpm` CLI for project/task/evidence operations
- JSON ↔ SQLite import/export with FK validation
- Append-only audit trail and read-only dashboard queries
- Lifecycle unit tests (49 tests, all passing)

**Explicitly out of scope:** (now listed in the README under "What it is not")

- Payroll, benefits, or recruiting automation
- Web UI or authentication
- AI agents or orchestration
- Cloud hosting or paid services
- Employee surveillance of any kind
