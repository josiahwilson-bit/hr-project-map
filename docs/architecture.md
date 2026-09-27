# Architecture — HR-PM Map v0.2

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
Completion              (evidence exists: the work happened)
  │
  ▼
Verification            (independent confirmation of the evidence)
```

In v0.2, **Deliverable** is still implicit: it is whatever the task's
evidence describes. Everything else is a first-class entity with a JSON
Schema (`schema/`) and a SQLite table (`src/db.py`).

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

### Task
A unit of work inside a project: `id`, `project_id`, `milestone_id`
(optional), `title`, `assignee_id`, `status`, `due_date`.

Status is the heart of the workflow. Transitions are **enforced in code**
(`src/tasks.py`), and completion/verification are **evidence-gated**
(`src/completion.py`):

```
Proposed → Assigned → In Progress → Submitted → Completed → Verified
              ↑________|                              ↑          ↑
              (un-assign only)                  (requires   (requires
                                                 evidence)   evidence +
                                                             verifier)
```

- Forward movement is one step at a time; skipping stages is rejected.
- The only backward move is `Assigned → Proposed` (withdrawing an assignment).
- Nothing moves backward out of `In Progress` or later — rework is modeled
  as a *new* task, preserving the audit trail.
- `Submitted → Completed` is refused when the task has no evidence records.
- `Completed → Verified` is refused when no evidence was verified by someone
  other than the submitter.
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

### Completion
A task reaches `Completed` only from `Submitted`, and only when at least one
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
  without pretending to be a product.

## What v0.2 deliberately omits

Authentication, a web UI, payroll, recruiting automation, notifications, AI
agents, and any cloud service. Those are layers *on top of* this map — and
the map must be trustworthy before any of them are built.
