# Workflow — Task Lifecycle (v0.4)

A task moves through eight stages, with a terminal branch off review.
Each stage has a clear actor and a clear meaning. The transitions are
enforced by `src/tasks.py`, the review protocol by `src/review.py`, and the
evidence-gated completion rules live in `src/completion.py` — see
[architecture.md](architecture.md) for the transition diagram.

```
Proposed → Assigned → In Progress → Submitted → Under Review → Accepted → Completed → Verified
                                              ↘ Rejected (TERMINAL)
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
- **Meaning:** "Here's my work — check it." The task now waits for a human
  reviewer.
- **Next:** A reviewer starts review, moving it to Under Review.

### 5. Under Review
A named human is actively judging the submitted work.

- **Who:** The reviewer, via `review.start_review()` — they must be an
  existing, active person, and their id is recorded on the task.
- **Meaning:** "A specific person is deciding." Only the reviewing reviewer
  may accept or reject this task.
- **Next:** `review.accept_review()` moves it to Accepted (the decision is
  audit-logged), or `review.reject_review()` moves it to Rejected — which
  requires a recorded reason and is terminal.

### 6. Accepted
A human accepted the work. This is judgment, not mechanics.

- **Who:** The reviewing reviewer, via `review.accept_review()`.
- **Meaning:** "The work passes review." Acceptance is a separate fact from
  completion: the work still needs evidence on record to close out.
- **Next:** `completion.complete_task()` moves it to Completed — but only
  because evidence exists. With no evidence records, completion is refused.

### 7. Rejected
A human rejected the work. **Terminal state — no outgoing transitions.**

- **Who:** The reviewing reviewer, via `review.reject_review()` with a
  recorded reason.
- **Meaning:** "The work does not pass review, and this outcome is on
  record." The task keeps its evidence, its review decision, and its audit
  history; it can never be reopened.
- **Next:** Nothing on this task. If the work must be attempted again, a new
  task is created via `tasks.rework_task()` with `supersedes_task_id`
  pointing at the rejected original.

### 8. Completed
The work demonstrably happened: evidence is on record, and a human accepted
it.

- **Who:** The Manager (or whoever closes out the work), via
  `completion.complete_task()`.
- **Meaning:** "The work is done and proven." The gate is mechanical: no
  evidence → no completion. The system records what happened; it never
  manufactures it.
- **Next:** A *different* person verifies the evidence, and
  `completion.verify_task()` moves the task to Verified. (Self-verification
  is rejected.)

### 9. Verified
An independent reviewer confirmed the evidence. Terminal state.

- **Who:** A Manager, or any person other than the submitter, via
  `verify_evidence()` followed by `completion.verify_task()`.
- **Meaning:** "The work checks out, confirmed independently." The
  deliverable is accepted. The record is permanent history.

## Worked example

## Project intake (v0.4)

Before work exists, a request exists. `hrpm intake create` stages a
structured request with an explicit requester, an explicit scope, and
required fields; the request sits in `Pending` until someone decides it.

```
1. Sam asks for a new project: "Portal refresh", scope "Redesign login pages"
2. The request is staged as Pending — no project exists yet
3. Manager Jane runs `hrpm intake approve <ID> --by Jane`  → exactly one project
4. Approving again is refused; rejecting requires a reason and creates nothing
```

Intake is where scope gets written down and named. An approved intake can
never be approved twice; a rejected intake creates no project.

## Worked example

```
1. Manager Jane creates task "Draft onboarding checklist"      → Proposed
2. Jane assigns it to employee Sam                             → Assigned
3. Sam starts writing                                          → In Progress
4. Sam uploads docs/checklist-v1.md as evidence                → Submitted
5. Jane starts review (she is an active person)                → Under Review
6. Jane accepts the work — decision is audit-logged            → Accepted
7. Jane runs complete_task() — evidence exists                 → Completed
8. Jane verifies the evidence (she is not the submitter)       → Verified
```

Note that step 8 *must* be someone other than Sam. If Sam tries to verify his
own evidence, the system raises an error. And step 7 is refused outright if
step 4 never happened — there is no way to mark work complete without proof.

## Rework

Rejected work: use `hrpm task rework --task <REJECTED_ID>`. This creates a
new task ("… (rework)") whose `supersedes_task_id` references the rejected
original, which stays Rejected forever. Rejected is a recorded terminal
outcome, not an invitation to rewrite history.

If verified work turns out to be wrong, do **not** move the task backward.
Create a new task (e.g., "Fix onboarding checklist §3") referencing the old
one. The map is append-only: history is never rewritten, only extended.
