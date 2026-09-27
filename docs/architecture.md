# Architecture — HR-PM Map v0.4

## The backbone

Every unit of organizational work is modeled as a single chain:

```
Intake                  (a staged project request: requester + scope)
  │
  ▼
Person
  │
  ▼
Responsibility          (a person is accountable for a project)
  │
  ▼
Project                 (a scoped body of work with an owner)
  │
  ├── Milestone         (a checkpoint grouping related tasks)
  │
  ▼
Task                    (a unit of work inside a project, with an assignee)
  │
  ▼
Deliverable             (what the task produces — implicit in v0.2)
  │
  ▼
Evidence                (proof the work was done)
  │
  ▼
Review                  (a human accepts or rejects the submitted work)
  │
  ▼
Completion              (accepted, evidence exists: the work happened)
  │
  ▼
Verification            (independent confirmation of the evidence)
```

In v0.4, **Deliverable** is still implicit: it is whatever the task's
evidence describes. **Intake** and **Review** are first-class entities with
JSON Schema (`schema/`) and SQLite tables (`src/db.py`); everything else
carries forward from v0.2/v0.3.

> **The evidence-gated principle.** The system records what happened; it
> does not manufacture evidence that something happened. A task cannot be
> marked `Completed` unless an evidence record exists for it, and cannot be
> marked `Verified` unless that evidence was confirmed by someone other than
> the submitter. Status is derived from records, never typed into existence.

## Entities

### Person
A human participant in the system. Roles:

| Role       | Meaning                                              |
|------------|------------------------------------------------------|
| Employee   | Does assigned work                                   |
| Contractor | Does assigned work under a contract                   |
| Manager    | Owns projects, assigns work, verifies evidence       |
| Client     | External sponsor or stakeholder                      |

Fields: `id`, `name`, `role`, `email`, `active`. Inactive people keep their
history but cannot be assigned new work.

### Responsibility
The accountability link between a Person and a Project. In v0.1 this is
represented by `project.owner_id` — the person answerable for the project's
outcome. Task-level responsibility is `task.assignee_id`.

### Project
A scoped body of work: `id`, `name`, `description`, `owner_id`, `status`,
`created_at`. Status follows the same six-stage lifecycle as tasks but is
managed manually (a project's status is a judgment call by its owner, not
derived from task states in v0.2).

### Milestone
A checkpoint inside a project that groups related tasks: `id`,
`project_id`, `name`, `description`, `status`, `due_date`, `created_at`.
Tasks link to a milestone via the optional `task.milestone_id`; a milestone
must belong to the same project as its tasks.

Milestone lifecycle is simplified and strictly forward-only:

```
Proposed → Assigned → In Progress → Completed
```

No backward moves, no skipping. Unlike tasks, milestones carry **no evidence
gate** — they are planning markers, not proof of work.

### Intake
A staged project request: `id`, `title`, `scope`, `requester_id`,
`description`, `status` (`Pending`/`Approved`/`Rejected`), `project_id`,
`decided_by`, `decision_reason`, `created_at`, `decided_at`. Created via
`src/intake.py`; title, scope, and an active requester are required.
Approval creates exactly one project (`project_id` is filled in and the
intake leaves `Pending`); approving an already-decided intake is refused.
Rejecting an intake requires a reason and creates no project.

### Task
A unit of work inside a project: `id`, `project_id`, `milestone_id`
(optional), `title`, `assignee_id`, `reviewer_id`, `supersedes_task_id`,
`status`, `due_date`.

Status is the heart of the workflow. Transitions are **enforced in code**
(`src/tasks.py`), review decisions in `src/review.py`, and
completion/verification are **evidence-gated** (`src/completion.py`):

```
Proposed → Assigned → In Progress → Submitted → Under Review → Accepted → Completed → Verified
                                              ↘ Rejected (TERMINAL)
```

- Forward movement is one step at a time; skipping stages is rejected.
- The only backward move is `Assigned → Proposed` (withdrawing an assignment).
- `Submitted → Under Review` requires a named, active reviewer, stored on
  the task; only that reviewer may accept or reject it.
- `Under Review → Accepted` emits an audit event recording the reviewer.
- `Under Review → Rejected` requires a recorded reason and is **terminal**:
  no outgoing transitions exist.
- `Accepted → Completed` is refused when the task has no evidence records.
- `Completed → Verified` is refused when no evidence was verified by someone
  other than the submitter.
- Rework is modeled as a *new* task: `rework_task()` copies the rejected
  task's title, project, and milestone, sets `supersedes_task_id` to the
  original, and leaves the original `Rejected`. History is linked, never
  rewritten.
- No synthetic evidence is ever generated: the gates only pass when the
  required records already exist.

### Evidence
Proof that a task's work was done: `id`, `task_id`, `submitted_by`,
`evidence_type`, `url_or_path`, `submitted_at`, plus `verified_by` /
`verified_at` once verified.

Submitting evidence moves the task to `Submitted`. Evidence types are free
text in v0.1 (`document`, `screenshot`, `link`, `note`, …) so teams can adopt
their own conventions.

### Verification
Not a separate table — it is the act of a **different person** confirming an
evidence record. `src/evidence.py` rejects self-verification: the verifier's
id must differ from the submitter's id. Verifying evidence stamps the record
but does not move the task; the task advances via `src/completion.py`.

### Review
The human judgment between submission and completion. `src/review.py`
enforces the decision protocol: start (Submitted → Under Review, records the
reviewer), accept (Under Review → Accepted, audited), or reject
(Under Review → Rejected, terminal, reason required). Each accepted review
writes one row to the `reviews` table: task, reviewer, decision, reason,
timestamp. Skipping stages, deciding without a reviewer, rejecting without a
reason, and deciding someone else's review are all refused.

### Completion
A task reaches `Completed` only from `Accepted`, and only when at least one
evidence record exists for it (`completion.complete_task()`). A task reaches
`Verified` only from `Completed`, and only when an evidence record was
verified by someone other than the submitter
(`completion.verify_task()`). Closed tasks are never deleted; the map is
append-only history.

## Design decisions

- **SQLite, local file.** Zero infrastructure cost, zero setup, fully
  portable. The database file is the system of record.
- **Standard library only.** `sqlite3`, `json`, `datetime`, `uuid`,
  `unittest`, `argparse`. No dependencies means no supply-chain risk and no
  install step.
- **JSON Schemas as contracts.** `schema/*.schema.json` define the shape of
  every entity, so a future web API or UI can validate against the same
  contracts the Python layer enforces.
- **Enforcement in code, not just docs.** Status transitions, the evidence
  gates, and the no-self-verification rule raise `ValueError` when violated
  — the rules cannot be silently bypassed by a careless caller.
- **Evidence-gated states.** Completion and verification are derived from
  records, never asserted. This is the architectural principle that makes
  the map trustworthy enough to build on.
- **JSON seed files and sync.** `data/*.json` are empty arrays with commented
  examples; `src/sync.py` exports live database snapshots to the same format
  and imports them back with full foreign-key validation.
- **A small CLI.** `hrpm` covers the daily operations (project/task/evidence)
  without pretending to be a product. v0.3 adds read-only `hrpm dashboard`
  views that report state without modifying it; v0.4 adds
  `hrpm intake create/list/approve/reject`, `hrpm review start/accept/reject`,
  and `hrpm task rework` for the intake and review workflow.

## The audit trail (v0.3)

Every accepted state transition on a task, milestone, or project appends one
row to the `audit_events` table:

| Column       | Meaning                                              |
|--------------|------------------------------------------------------|
| `event_id`   | UUID primary key                                     |
| `entity_type`| `task`, `milestone`, or `project`                    |
| `entity_id`  | id of the entity that changed                        |
| `prev_state` | state before the transition                          |
| `new_state`  | state after the transition                           |
| `actor_id`   | person who performed the transition (NULL if unknown)|
| `timestamp`  | UTC ISO-8601 time of the transition                  |
| `note`       | optional context (e.g. "reassigned to …")            |

The append-only invariant: `src/audit.py` exposes `log_event()` and
`get_events()` only. There is no update or delete path for audit rows, so
history cannot be rewritten through the code. Refused or invalid
transitions emit no event — a transition without an audit record is not
considered recorded.

> The dashboard reports state; the audit trail records the transition;
> neither one creates evidence of an event that did not occur.

## The terminal-Rejected principle (v0.4)

> Rejected is a recorded terminal outcome, not an invitation to rewrite
> history. Rework creates a new task and preserves the relationship to the
> original.

Rejection ends the task's lifecycle. The rejected task keeps its evidence,
its review decision, and its audit history — all queryable via
`hrpm dashboard rejected`. If the work must be attempted again, a new task
is created with `supersedes_task_id` pointing at the rejected one. There is
no transition back, no status edit, and no delete path; the map grows by
adding records, never by altering the past.

## What v0.4 deliberately omits

Authentication, a web UI, payroll, recruiting automation, notifications, AI
agents, and any cloud service. Those are layers *on top of* this map — and
the map must be trustworthy before any of them are built.
