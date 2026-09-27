# Governance — Scope, Approval, Responsibility, Evidence

The map is only useful if its records can be trusted. These are the v0.1
rules. They are enforced in code where possible (`src/tasks.py`,
`src/evidence.py`) and by convention everywhere else.

## 1. Scope

- A **Project** must have a name and an owner (`owner_id`). The owner is
  accountable for everything inside the project.
- A **Task** must belong to exactly one project (`project_id`). Orphan tasks
  are not allowed.
- v0.1 covers *tracking work and proving it was done*. It does not cover
  compensation, hiring/firing, performance ratings, or surveillance. Those are
  explicitly out of scope.

## 2. Approval (who can move work forward)

| Transition              | Who approves / acts                          |
|-------------------------|----------------------------------------------|
| Proposed → Assigned     | Project owner or Manager (assigns a person)   |
| Assigned → Proposed     | Project owner or Manager (withdraws)         |
| Assigned → In Progress  | The assignee (starts work)                   |
| In Progress → Submitted | The assignee (submits evidence)              |
| Submitted → Verified    | Anyone **except** the submitter              |
| Verified → Completed    | Project owner or Manager (closes)            |

## 3. Responsibility

- Every project has exactly one owner. Shared ownership is modeled as a
  project with one accountable owner plus collaborators on tasks.
- Every task in `Assigned` state or later should have an assignee. A task
  with no assignee cannot leave `Proposed`.
- Inactive people (`active = false`) keep their history but cannot be
  assigned new tasks or verify new evidence.

## 4. Evidence (what counts as proof)

Acceptable evidence in v0.1:

- `document` — a file path or URL to the produced document
- `link` — a URL to the work product (repo, ticket, published page)
- `screenshot` — an image path showing the result
- `note` — a written description (weakest form; use only for trivial tasks)

Rules:

- Evidence must reference the task it proves (`task_id`).
- Evidence can only be submitted for a task that is `In Progress` (or to add
  to one already `Submitted`).
- **Verification must be independent.** The verifier's person id must differ
  from the submitter's. `verify_evidence()` raises `ValueError` on
  self-verification — no exceptions.
- A verifier should actually review the evidence before verifying. The system
  enforces *who* may verify, not *how carefully* — that part is human
  judgment.
- Evidence records are never deleted. A mistaken submission is superseded by
  a new one, not erased.

## 5. Auditability

- All state changes go through the `src/` functions, which validate every
  transition.
- Timestamps (`created_at`, `submitted_at`, `verified_at`) are recorded in
  UTC ISO-8601 at the moment of the action.
- The task history is reconstructible: proposed → assigned → … → completed,
  with who did what and when, backed by evidence.
