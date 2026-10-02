"""v0.4 tests: structured project intake and the human review workflow.

Covers the v0.4 acceptance boundary:
  INTAKE  — required fields, explicit requester, staged request,
            approval creates exactly one project, no duplicate projects.
  REVIEW  — Submitted -> Under Review -> Accepted -> Completed -> Verified,
            with Under Review -> Rejected as a TERMINAL branch.
  RULES   — reviewer required, rejection reason required, acceptance emits
            an audit event, Rejected cannot be reopened, rework creates a
            new task referencing the original, evidence/verifier gates hold,
            audit history stays append-only.

Temp SQLite database; stdlib unittest only.
"""

import os
import shutil
import sys
import tempfile
import unittest

# Make `src` importable when running `python -m unittest discover -s tests`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import (
    audit,
    completion,
    db,
    evidence,
    intake,
    people,
    projects,
    queries,
    review,
    tasks,
)


class IntakeTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        db.init_db(self.db_path)
        self.manager = people.add_person(
            self.db_path, "Jane Doe", "Manager", "jane@example.com"
        )
        self.worker = people.add_person(
            self.db_path, "Sam Lee", "Employee", "sam@example.com"
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_intake_creation_and_required_fields(self):
        iid = intake.create_intake(
            self.db_path, "Portal refresh", "Redesign the login pages",
            self.manager, description="Q4 ask",
        )
        row = intake.get_intake(self.db_path, iid)
        self.assertEqual(row["title"], "Portal refresh")
        self.assertEqual(row["scope"], "Redesign the login pages")
        self.assertEqual(row["requester_id"], self.manager)
        self.assertEqual(row["status"], "Pending")
        self.assertIsNone(row["project_id"])

        # Required-field validation: nothing is created on failure.
        for kwargs in (
            {"title": "", "scope": "s", "requester_id": self.manager},
            {"title": "t", "scope": "  ", "requester_id": self.manager},
            {"title": "t", "scope": "s", "requester_id": None},
            {"title": "t", "scope": "s",
             "requester_id": "no-such-person"},
        ):
            with self.assertRaises(ValueError):
                intake.create_intake(self.db_path, **kwargs)
        self.assertEqual(len(intake.list_intakes(self.db_path)), 1)

    def test_intake_rejects_inactive_requester(self):
        people.set_active(self.db_path, self.worker, False)
        with self.assertRaises(ValueError):
            intake.create_intake(
                self.db_path, "Ghost project", "No scope", self.worker
            )

    def test_approval_creates_exactly_one_project(self):
        iid = intake.create_intake(
            self.db_path, "Portal refresh", "Redesign the login pages",
            self.worker,
        )
        before = len(projects.list_projects(self.db_path))
        pid = intake.approve_intake(self.db_path, iid, self.manager)
        self.assertEqual(len(projects.list_projects(self.db_path)),
                         before + 1)
        proj = projects.get_project(self.db_path, pid)
        self.assertEqual(proj["name"], "Portal refresh")
        self.assertEqual(proj["description"], "Redesign the login pages")
        self.assertEqual(proj["owner_id"], self.worker)
        row = intake.get_intake(self.db_path, iid)
        self.assertEqual(row["status"], "Approved")
        self.assertEqual(row["decided_by"], self.manager)
        self.assertEqual(row["project_id"], pid)
        self.assertIsNotNone(row["decided_at"])

    def test_approved_intake_cannot_be_approved_again(self):
        iid = intake.create_intake(
            self.db_path, "Portal refresh", "Redesign the login pages",
            self.worker,
        )
        intake.approve_intake(self.db_path, iid, self.manager)
        n_projects = len(projects.list_projects(self.db_path))
        with self.assertRaises(ValueError):
            intake.approve_intake(self.db_path, iid, self.manager)
        # Still exactly one project: no duplicates.
        self.assertEqual(len(projects.list_projects(self.db_path)),
                         n_projects)

    def test_reject_intake_requires_reason(self):
        iid = intake.create_intake(
            self.db_path, "Risky idea", "Unscoped moonshot", self.worker
        )
        with self.assertRaises(ValueError):
            intake.reject_intake(self.db_path, iid, self.manager, "  ")
        intake.reject_intake(
            self.db_path, iid, self.manager, "Out of scope for Q4"
        )
        row = intake.get_intake(self.db_path, iid)
        self.assertEqual(row["status"], "Rejected")
        self.assertEqual(row["decision_reason"], "Out of scope for Q4")
        self.assertIsNone(row["project_id"])
        # A rejected intake cannot then be approved.
        with self.assertRaises(ValueError):
            intake.approve_intake(self.db_path, iid, self.manager)

    def test_intake_list_filter(self):
        i1 = intake.create_intake(
            self.db_path, "A", "scope a", self.worker)
        i2 = intake.create_intake(
            self.db_path, "B", "scope b", self.worker)
        intake.approve_intake(self.db_path, i1, self.manager)
        self.assertEqual(
            [r["id"] for r in intake.list_intakes(self.db_path, "Pending")],
            [i2],
        )
        self.assertEqual(
            [r["id"] for r in intake.list_intakes(self.db_path, "Approved")],
            [i1],
        )


class ReviewWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        db.init_db(self.db_path)
        self.manager = people.add_person(
            self.db_path, "Jane Doe", "Manager", "jane@example.com"
        )
        self.worker = people.add_person(
            self.db_path, "Sam Lee", "Employee", "sam@example.com"
        )
        self.project = projects.add_project(
            self.db_path, "Onboarding Revamp", owner_id=self.manager
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _submitted_task_with_evidence(self, title="Write docs"):
        task = tasks.add_task(self.db_path, self.project, title)
        tasks.assign_task(self.db_path, task, self.worker,
                          actor_id=self.manager)
        tasks.update_task_status(self.db_path, task, "In Progress",
                                 actor_id=self.worker)
        eid = evidence.submit_evidence(
            self.db_path, task, submitted_by=self.worker,
            evidence_type="document", url_or_path="/tmp/docs.pdf",
        )
        return task, eid

    def test_valid_review_transitions_full_path(self):
        """Submitted -> Under Review -> Accepted -> Completed -> Verified."""
        task, eid = self._submitted_task_with_evidence()
        review.start_review(self.db_path, task, self.manager)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Under Review"
        )
        review.accept_review(self.db_path, task, self.manager,
                             note="meets the spec")
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Accepted"
        )
        completion.complete_task(self.db_path, task, actor_id=self.worker)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Completed"
        )
        evidence.verify_evidence(self.db_path, eid,
                                 verified_by=self.manager)
        completion.verify_task(self.db_path, task, self.manager)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Verified"
        )
        decisions = review.get_reviews(self.db_path, task)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["decision"], "Accepted")
        self.assertEqual(decisions[0]["reviewer_id"], self.manager)

    def test_invalid_review_transitions(self):
        task, _eid = self._submitted_task_with_evidence()
        # Cannot accept without starting review.
        with self.assertRaises(ValueError):
            review.accept_review(self.db_path, task, self.manager)
        # Cannot reject without starting review.
        with self.assertRaises(ValueError):
            review.reject_review(
                self.db_path, task, self.manager, "too early")
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Submitted"
        )
        review.start_review(self.db_path, task, self.manager)
        # Cannot start review twice.
        with self.assertRaises(ValueError):
            review.start_review(self.db_path, task, self.manager)
        # A different reviewer cannot decide someone else's review.
        with self.assertRaises(ValueError):
            review.accept_review(self.db_path, task, self.worker)

    def test_reviewer_required(self):
        task, _eid = self._submitted_task_with_evidence()
        with self.assertRaises(ValueError):
            review.start_review(self.db_path, task, None)
        with self.assertRaises(ValueError):
            review.start_review(self.db_path, task, "no-such-person")
        people.set_active(self.db_path, self.worker, False)
        with self.assertRaises(ValueError):
            review.start_review(self.db_path, task, self.worker)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Submitted"
        )

    def test_rejection_reason_required(self):
        task, _eid = self._submitted_task_with_evidence()
        review.start_review(self.db_path, task, self.manager)
        for bad_reason in ("", "   ", None):
            with self.assertRaises(ValueError):
                review.reject_review(
                    self.db_path, task, self.manager, bad_reason)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Under Review"
        )

    def test_rejected_is_terminal_cannot_reopen(self):
        task, _eid = self._submitted_task_with_evidence()
        review.start_review(self.db_path, task, self.manager)
        review.reject_review(
            self.db_path, task, self.manager, "does not match the spec")
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Rejected"
        )
        decisions = review.get_reviews(self.db_path, task)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["decision"], "Rejected")
        self.assertEqual(decisions[0]["reason"], "does not match the spec")
        # No outgoing transition exists: every attempt is refused.
        for target in ("Proposed", "Assigned", "In Progress", "Submitted",
                       "Under Review", "Accepted", "Completed", "Verified"):
            with self.assertRaises(ValueError):
                tasks.update_task_status(self.db_path, task, target)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Rejected"
        )

    def test_rework_creates_new_task_referencing_original(self):
        task, _eid = self._submitted_task_with_evidence()
        review.start_review(self.db_path, task, self.manager)
        review.reject_review(
            self.db_path, task, self.manager, "needs another pass")
        new_id = tasks.rework_task(
            self.db_path, task, assignee_id=self.worker)
        new_task = tasks.get_task(self.db_path, new_id)
        self.assertNotEqual(new_id, task)
        self.assertEqual(new_task["status"], "Assigned")
        self.assertEqual(new_task["assignee_id"], self.worker)
        self.assertEqual(new_task["supersedes_task_id"], task)
        self.assertTrue(new_task["title"].endswith("(rework)"))
        # The original stays Rejected: history is preserved, not rewritten.
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Rejected"
        )
        # Rework of a non-rejected task is refused.
        other, _e2 = self._submitted_task_with_evidence("Other work")
        with self.assertRaises(ValueError):
            tasks.rework_task(self.db_path, other)

    def test_acceptance_generates_audit_event(self):
        task, _eid = self._submitted_task_with_evidence()
        review.start_review(self.db_path, task, self.manager)
        before = audit.count_events(self.db_path)
        review.accept_review(self.db_path, task, self.manager)
        events = audit.get_events(self.db_path, "task", task)
        self.assertEqual(audit.count_events(self.db_path), before + 1)
        last = events[-1]
        self.assertEqual(last["prev_state"], "Under Review")
        self.assertEqual(last["new_state"], "Accepted")
        self.assertEqual(last["actor_id"], self.manager)
        # Refused review actions emit no event.
        n = audit.count_events(self.db_path)
        with self.assertRaises(ValueError):
            review.reject_review(self.db_path, task, self.manager, "late")
        self.assertEqual(audit.count_events(self.db_path), n)

    def test_completion_still_requires_evidence(self):
        task = tasks.add_task(self.db_path, self.project, "No evidence")
        tasks.assign_task(self.db_path, task, self.worker)
        tasks.update_task_status(self.db_path, task, "In Progress")
        # Submitted is unreachable without evidence via the public API, so
        # force Accepted directly to isolate the completion gate.
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE tasks SET status = 'Accepted' WHERE id = ?", (task,)
            )
            conn.commit()
        finally:
            conn.close()
        with self.assertRaisesRegex(ValueError, "without evidence"):
            completion.complete_task(self.db_path, task)

    def test_verification_still_requires_evidence_and_verifier(self):
        task, eid = self._submitted_task_with_evidence()
        review.start_review(self.db_path, task, self.manager)
        review.accept_review(self.db_path, task, self.manager)
        completion.complete_task(self.db_path, task)
        # No verification yet: refused.
        with self.assertRaises(ValueError):
            completion.verify_task(self.db_path, task, self.manager)
        # Self-verified evidence is not independent: still refused.
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE evidence SET verified_by = submitted_by,"
                " verified_at = ? WHERE id = ?",
                (db.utcnow(), eid),
            )
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(ValueError):
            completion.verify_task(self.db_path, task, self.worker)
        # Independent verification works.
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE evidence SET verified_by = ?, verified_at = ?"
                " WHERE id = ?",
                (self.manager, db.utcnow(), eid),
            )
            conn.commit()
        finally:
            conn.close()
        completion.verify_task(self.db_path, task, self.manager)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Verified"
        )

    def test_audit_history_remains_append_only(self):
        task, _eid = self._submitted_task_with_evidence()
        review.start_review(self.db_path, task, self.manager)
        review.accept_review(self.db_path, task, self.manager)
        events = audit.get_events(self.db_path, "task", task)
        states = [(e["prev_state"], e["new_state"]) for e in events]
        self.assertIn(("Submitted", "Under Review"), states)
        self.assertIn(("Under Review", "Accepted"), states)
        # No mutation API exists on the audit module.
        for forbidden in ("update_event", "delete_event", "remove_event",
                          "clear_events", "modify_event"):
            self.assertFalse(hasattr(audit, forbidden),
                             f"audit module must not expose {forbidden!r}")

    def test_dashboard_rejected_bucket(self):
        task, _eid = self._submitted_task_with_evidence("Doomed work")
        review.start_review(self.db_path, task, self.manager)
        review.reject_review(
            self.db_path, task, self.manager, "wrong direction")
        rows = queries.rejected_tasks(self.db_path)
        self.assertEqual([r["id"] for r in rows], [task])
        # Rejected tasks appear in neither outstanding nor submitted.
        self.assertEqual(queries.outstanding_tasks(self.db_path), [])
        self.assertEqual(
            [r["id"] for r in queries.submitted_tasks(self.db_path)], []
        )
        # Read-only: dashboard leaves state and audit log untouched.
        n_before = audit.count_events(self.db_path)
        queries.rejected_tasks(self.db_path, self.project)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Rejected"
        )
        self.assertEqual(audit.count_events(self.db_path), n_before)


if __name__ == "__main__":
    unittest.main()
