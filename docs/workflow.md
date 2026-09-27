# Workflow — Task Lifecycle

A task moves through six stages. Each stage has a clear actor and a clear
meaning. The transitions are enforced by `src/tasks.py` — see
[architecture.md](architecture.md) for the transition diagram.

## Stages

### 1. Proposed
The task exists but nobody owns it yet.

- **Who:** A Manager (or the project owner) creates the task with a title and
  optional due date.
- **Meaning:** "This work needs doing." No commitment yet.
- **Next:** `assign_task()` moves it to Assigned.

### 2. Assigned
A specific person is accountable.

- **Who:** The Manager assigns the task to an Employee or Contractor.
- **Meaning:** "Sam owns this." The assignee is expected to start.
- **Next:** `update_task_status(..., 'In Progress')` when work begins, or back
  to `Proposed` if the assignment is withdrawn (the only backward move).

### 3. In Progress
Work is actively being done.

- **Who:** The assignee.
- **Meaning:** "Work is underway." This is the only stage where effort is
  expected.
- **Next:** The assignee submits evidence, moving the task to Submitted.

### 4. Submitted
The assignee claims the work is done and attaches proof.

- **Who:** The assignee, via `submit_evidence()`.
- **Meaning:** "Here's my work — check it." The task now waits for review.
- **Next:** A *different* person verifies the evidence, moving the task to
  Verified. (Self-verification is rejected.)

### 5. Verified
An independent reviewer confirmed the evidence.

- **Who:** A Manager, or any person other than the submitter, via
  `verify_evidence()`.
- **Meaning:** "The work checks out." The deliverable is accepted.
- **Next:** `update_task_status(..., 'Completed')` closes the task.

### 6. Completed
Terminal state. The work is done, proven, and accepted.

- **Who:** The Manager (or whoever closes out the project).
- **Meaning:** "Done." The record is permanent history.

## Worked example

```
1. Manager Jane creates task "Draft onboarding checklist"      → Proposed
2. Jane assigns it to employee Sam                             → Assigned
3. Sam starts writing                                          → In Progress
4. Sam uploads docs/checklist-v1.md as evidence                → Submitted
5. Jane reviews the document and verifies it                   → Verified
6. Jane closes the task                                        → Completed
```

Note that step 5 *must* be someone other than Sam. If Sam tries to verify his
own evidence, the system raises an error.

## Rework

If verified work turns out to be wrong, do **not** move the task backward.
Create a new task (e.g., "Fix onboarding checklist §3") referencing the old
one. The map is append-only: history is never rewritten, only extended.
