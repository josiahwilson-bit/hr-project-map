# Architecture — HR-PM Map v0.1

## The backbone

Every unit of organizational work is modeled as a single chain:

```
Person
  │
  ▼
Responsibility          (a person is accountable for a project)
  │
  ▼
Project                 (a scoped body of work with an owner)
  │
  ▼
Task                    (a unit of work inside a project, with an assignee)
  │
  ▼
Deliverable             (what the task produces — implicit in v0.1)
  │
  ▼
Evidence                (proof the work was done)
  │
  ▼
Verification            (independent confirmation of the evidence)
  │
  ▼
Completion              (verified work, closed)
```

In v0.1, **Deliverable** is implicit: it is whatever the task's evidence
describes. A future version may promote it to its own entity. Everything else
is a first-class entity with a JSON Schema (`schema/`) and a SQLite table
(`src/db.py`).

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
derived from task states in v0.1).

### Task
A unit of work inside a project: `id`, `project_id`, `title`,
`assignee_id`, `status`, `due_date`.

Status is the heart of the workflow. Transitions are **enforced in code**
(`src/tasks.py`):

```
Proposed → Assigned → In Progress → Submitted → Verified → Completed
              ↑________|
              (un-assign only)
```

- Forward movement is one step at a time; skipping stages is rejected.
- The only backward move is `Assigned → Proposed` (withdrawing an assignment).
- Nothing moves backward out of `In Progress` or later — rework is modeled
  as a *new* task, preserving the audit trail.

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
id must differ from the submitter's id. Verification moves the task to
`Verified`.

### Completion
The terminal state. A task reaches `Completed` only from `Verified`. Closed
tasks are never deleted; the map is append-only history.

## Design decisions

- **SQLite, local file.** Zero infrastructure cost, zero setup, fully
  portable. The database file is the system of record.
- **Standard library only.** `sqlite3`, `json`, `datetime`, `uuid`,
  `unittest`. No dependencies means no supply-chain risk and no install step.
- **JSON Schemas as contracts.** `schema/*.schema.json` define the shape of
  every entity, so a future web API or UI can validate against the same
  contracts the Python layer enforces.
- **Enforcement in code, not just docs.** Status transitions and the
  no-self-verification rule raise `ValueError` when violated — the rules
  cannot be silently bypassed by a careless caller.
- **JSON seed files.** `data/*.json` are empty arrays with commented examples,
  ready to hold exported snapshots of the map.

## What v0.1 deliberately omits

Authentication, a web UI, payroll, recruiting automation, notifications, and
any cloud service. Those are layers *on top of* this map — and the map must
be trustworthy before any of them are built.
