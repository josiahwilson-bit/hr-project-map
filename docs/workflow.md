# Workflow — Task Lifecycle (v0.3)

A task moves through six stages. Each stage has a clear actor and a clear
meaning. The transitions are enforced by `src/tasks.py` and the
evidence-gated completion rules live in `src/completion.py` — see
[architecture.md](architecture.md) for the transition diagram.

```
Proposed → Assigned → In Progress → Submitted → Completed → Verified
```

The governing principle: **the system records what happened; it does not
manufacture evidence that something happened.** A task's status is derived
from records that already exist — it can never be typed into existence.

**Audit logging (v0.3):** every accepted transition on a task, milestone, or
project appends one row to the `audit_events` table recording the entity,
previous state, new state, actor, and UTC timestamp. Refused transitions
emit no event, and the trail is append-only — history cannot be rewritten.
Without an audit record, the transition is not considered recorded.

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
- **Next:** `complete_task()` moves it to Completed — but only because
  evidence now exists. With no evidence records, completion is refused.

### 5. Completed
The work demonstrably happened: evidence is on record.

- **Who:** The Manager (or whoever closes out the work), via
  `completion.complete_task()`.
- **Meaning:** "The work is done and proven." The gate is mechanical: no
  evidence → no completion. The system records what happened; it never
  manufactures it.
- **Next:** A *different* person verifies the evidence, and
  `completion.verify_task()` moves the task to Verified. (Self-verification
  is rejected.)

### 6. Verified
An independent reviewer confirmed the evidence. Terminal state.

- **Who:** A Manager, or any person other than the submitter, via
  `verify_evidence()` followed by `completion.verify_task()`.
- **Meaning:** "The work checks out, confirmed independently." The
  deliverable is accepted. The record is permanent history.

## Worked example

```
1. Manager Jane creates task "Draft onboarding checklist"      → Proposed
2. Jane assigns it to employee Sam                             → Assigned
3. Sam starts writing                                          → In Progress
4. Sam uploads docs/checklist-v1.md as evidence                → Submitted
5. Jane runs complete_task() — evidence exists                 → Completed
6. Jane verifies the evidence (she is not the submitter)       → Verified
```

Note that step 6 *must* be someone other than Sam. If Sam tries to verify his
own evidence, the system raises an error. And step 5 is refused outright if
step 4 never happened — there is no way to mark work complete without proof.

## Rework

If verified work turns out to be wrong, do **not** move the task backward.
Create a new task (e.g., "Fix onboarding checklist §3") referencing the old
one. The map is append-only: history is never rewritten, only extended.
