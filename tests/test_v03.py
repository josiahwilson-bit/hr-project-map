"""v0.3 tests: append-only audit events and the read-only dashboard/query
layer. Temp SQLite database; stdlib unittest only.

Core invariant under test: every accepted transition has an audit record;
without an audit record, the transition is not considered recorded.
Refused/invalid transitions emit no event. The dashboard reports state;
it never modifies it.
"""

import os
import shutil
import sys
import tempfile
import unittest

# Make `src` importable when running `python -m unittest discover -s tests`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import audit, completion, db, evidence, milestones, people, projects, queries, tasks


class AuditTrailTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        db.init_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_people_and_project(self):
        manager = people.add_person(
            self.db_path, "Jane Doe", "Manager", "jane@example.com"
        )
        worker = people.add_person(
            self.db_path, "Sam Lee", "Employee", "sam@example.com"
        )
        project = projects.add_project(
            self.db_path, "Onboarding Revamp", owner_id=manager
        )
        return manager, worker, project

    def _task_submitted_with_evidence(self, project, worker, verifier):
        """Drive a task Proposed -> Submitted with evidence, returning ids."""
        task = tasks.add_task(self.db_path, project, "Write docs")
        tasks.assign_task(self.db_path, task, worker, actor_id=worker)
        tasks.update_task_status(self.db_path, task, "In Progress",
                                 actor_id=worker)
        eid = evidence.submit_evidence(
            self.db_path, task, submitted_by=worker,
            evidence_type="document", url_or_path="/tmp/docs.pdf",
        )
        return task, eid

    def test_accepted_transition_emits_audit_event(self):
        manager, worker, project = self._make_people_and_project()
        task = tasks.add_task(self.db_path, project, "Write docs")
        self.assertEqual(audit.count_events(self.db_path), 0)
        tasks.assign_task(self.db_path, task, worker, actor_id=manager)
        events = audit.get_events(self.db_path, "task", task)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["entity_type"], "task")
        self.assertEqual(ev["entity_id"], task)
        self.assertEqual(ev["prev_state"], "Proposed")
        self.assertEqual(ev["new_state"], "Assigned")
        self.assertEqual(ev["actor_id"], manager)
        self.assertTrue(ev["timestamp"])
        self.assertTrue(ev["event_id"])

    def test_invalid_transition_emits_no_event(self):
        manager, worker, project = self._make_people_and_project()
        task = tasks.add_task(self.db_path, project, "Write docs")
        # Proposed -> In Progress is not allowed (must go via Assigned).
        with self.assertRaises(ValueError):
            tasks.update_task_status(self.db_path, task, "In Progress",
                                     actor_id=worker)
        self.assertEqual(tasks.get_task(self.db_path, task)["status"],
                         "Proposed")
        self.assertEqual(audit.count_events(self.db_path), 0)

    def test_audit_log_is_append_only(self):
        manager, worker, project = self._make_people_and_project()
        task = tasks.add_task(self.db_path, project, "Write docs")
        tasks.assign_task(self.db_path, task, worker, actor_id=manager)
        tasks.update_task_status(self.db_path, task, "In Progress",
                                 actor_id=worker)
        events = audit.get_events(self.db_path, "task", task)
        self.assertEqual(len(events), 2)
        # Oldest first.
        self.assertEqual(events[0]["new_state"], "Assigned")
        self.assertEqual(events[1]["new_state"], "In Progress")
        # The audit module exposes no mutation API: append-only by design.
        for forbidden in ("update_event", "delete_event", "remove_event",
                          "clear_events", "modify_event"):
            self.assertFalse(hasattr(audit, forbidden),
                             "audit module must not expose %r" % forbidden)

    def test_refused_completion_emits_no_event(self):
        manager, worker, project = self._make_people_and_project()
        task = tasks.add_task(self.db_path, project, "Write docs")
        tasks.assign_task(self.db_path, task, worker, actor_id=worker)
        tasks.update_task_status(self.db_path, task, "In Progress",
                                 actor_id=worker)
        eid = evidence.submit_evidence(
            self.db_path, task, submitted_by=worker,
            evidence_type="document", url_or_path="/tmp/docs.pdf",
        )
        before = audit.count_events(self.db_path)
        # Submitted -> Completed is fine (evidence exists)...
        completion.complete_task(self.db_path, task, actor_id=worker)
        self.assertEqual(audit.count_events(self.db_path), before + 1)
        # ...but a fresh task with no evidence path must refuse AND log nothing.
        task2 = tasks.add_task(self.db_path, project, "No evidence task")
        tasks.assign_task(self.db_path, task2, worker, actor_id=worker)
        tasks.update_task_status(self.db_path, task2, "In Progress",
                                 actor_id=worker)
        evidence.submit_evidence(
            self.db_path, task2, submitted_by=worker,
            evidence_type="document", url_or_path="/tmp/x.pdf",
        )
        # Corrupt the DB directly: Submitted with the evidence row removed.
        conn = db.connect(self.db_path)
        try:
            conn.execute("DELETE FROM evidence WHERE task_id = ?", (task2,))
            conn.commit()
        finally:
            conn.close()
        n_before = audit.count_events(self.db_path)
        with self.assertRaises(ValueError):
            completion.complete_task(self.db_path, task2, actor_id=worker)
        self.assertEqual(tasks.get_task(self.db_path, task2)["status"],
                         "Submitted")
        self.assertEqual(audit.count_events(self.db_path), n_before)

    def test_milestone_and_project_transitions_are_audited(self):
        manager, worker, project = self._make_people_and_project()
        ms = milestones.add_milestone(self.db_path, project, "Phase 1")
        milestones.update_milestone_status(self.db_path, ms, "Assigned",
                                          actor_id=manager)
        events = audit.get_events(self.db_path, "milestone", ms)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["prev_state"], "Proposed")
        self.assertEqual(events[0]["new_state"], "Assigned")
        projects.update_project_status(self.db_path, project, "In Progress",
                                       actor_id=manager)
        pevents = audit.get_events(self.db_path, "project", project)
        self.assertEqual(len(pevents), 1)
        self.assertEqual(pevents[0]["new_state"], "In Progress")


class DashboardTest(unittest.TestCase):
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
        # One task per bucket, driven through real transitions.
        self.t_outstanding = tasks.add_task(
            self.db_path, self.project, "Outstanding work")
        tasks.assign_task(self.db_path, self.t_outstanding, self.worker)

        self.t_submitted = tasks.add_task(
            self.db_path, self.project, "Submitted work")
        tasks.assign_task(self.db_path, self.t_submitted, self.worker)
        tasks.update_task_status(self.db_path, self.t_submitted, "In Progress")
        evidence.submit_evidence(
            self.db_path, self.t_submitted, submitted_by=self.worker,
            evidence_type="document", url_or_path="/tmp/s.pdf")

        self.t_completed = tasks.add_task(
            self.db_path, self.project, "Completed work")
        tasks.assign_task(self.db_path, self.t_completed, self.worker)
        tasks.update_task_status(self.db_path, self.t_completed, "In Progress")
        evidence.submit_evidence(
            self.db_path, self.t_completed, submitted_by=self.worker,
            evidence_type="document", url_or_path="/tmp/c.pdf")
        completion.complete_task(self.db_path, self.t_completed)

        self.t_verified = tasks.add_task(
            self.db_path, self.project, "Verified work")
        tasks.assign_task(self.db_path, self.t_verified, self.worker)
        tasks.update_task_status(self.db_path, self.t_verified, "In Progress")
        eid = evidence.submit_evidence(
            self.db_path, self.t_verified, submitted_by=self.worker,
            evidence_type="document", url_or_path="/tmp/v.pdf")
        evidence.verify_evidence(self.db_path, eid, verified_by=self.manager)
        completion.complete_task(self.db_path, self.t_verified)
        completion.verify_task(self.db_path, self.t_verified, self.manager)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _ids(self, rows):
        return sorted(r["id"] for r in rows)

    def test_dashboard_outstanding(self):
        rows = queries.outstanding_tasks(self.db_path)
        self.assertEqual(self._ids(rows), [self.t_outstanding])

    def test_dashboard_submitted(self):
        rows = queries.submitted_tasks(self.db_path)
        self.assertEqual(self._ids(rows), [self.t_submitted])

    def test_dashboard_completed(self):
        rows = queries.completed_tasks(self.db_path)
        self.assertEqual(self._ids(rows), [self.t_completed])

    def test_dashboard_verified(self):
        rows = queries.verified_tasks(self.db_path)
        self.assertEqual(self._ids(rows), [self.t_verified])

    def test_dashboard_project_filter(self):
        other = projects.add_project(self.db_path, "Other",
                                     owner_id=self.manager)
        t_other = tasks.add_task(self.db_path, other, "Other task")
        rows = queries.outstanding_tasks(self.db_path, self.project)
        self.assertEqual(self._ids(rows), [self.t_outstanding])
        rows = queries.outstanding_tasks(self.db_path, other)
        self.assertEqual(self._ids(rows), [t_other])

    def test_project_summary(self):
        s = queries.project_summary(self.db_path, self.project)
        self.assertEqual(s["project_name"], "Onboarding Revamp")
        self.assertEqual(s["task_counts"].get("Assigned"), 1)
        self.assertEqual(s["task_counts"].get("Submitted"), 1)
        self.assertEqual(s["task_counts"].get("Completed"), 1)
        self.assertEqual(s["task_counts"].get("Verified"), 1)
        self.assertEqual(s["outstanding"], 1)
        with self.assertRaises(ValueError):
            queries.project_summary(self.db_path, "no-such-project")

    def test_dashboard_is_read_only(self):
        states_before = {
            t["id"]: t["status"]
            for t in tasks.list_tasks_by_project(self.db_path, self.project)
        }
        n_events_before = audit.count_events(self.db_path)
        queries.outstanding_tasks(self.db_path)
        queries.submitted_tasks(self.db_path)
        queries.completed_tasks(self.db_path)
        queries.verified_tasks(self.db_path)
        queries.outstanding_tasks(self.db_path, self.project)
        queries.project_summary(self.db_path, self.project)
        states_after = {
            t["id"]: t["status"]
            for t in tasks.list_tasks_by_project(self.db_path, self.project)
        }
        self.assertEqual(states_before, states_after)
        self.assertEqual(audit.count_events(self.db_path), n_events_before)


if __name__ == "__main__":
    unittest.main()
