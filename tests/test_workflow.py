"""Full lifecycle tests for the HR-PM Map, run against a temp SQLite database."""

import os
import shutil
import sys
import tempfile
import unittest

# Make `src` importable when running `python -m unittest discover -s tests`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import completion, db, evidence, people, projects, tasks


class WorkflowTest(unittest.TestCase):
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
            self.db_path,
            "Onboarding Revamp",
            "Redesign new-hire onboarding",
            owner_id=manager,
        )
        return manager, worker, project

    def test_full_lifecycle(self):
        """Person -> Project -> Task -> Evidence -> Completion -> Verification."""
        manager, worker, project = self._make_people_and_project()

        # 1. Proposed
        task = tasks.add_task(
            self.db_path, project, "Draft onboarding checklist",
            due_date="2026-10-15",
        )
        self.assertEqual(tasks.get_task(self.db_path, task)["status"], "Proposed")

        # 2. Proposed -> Assigned
        tasks.assign_task(self.db_path, task, worker)
        t = tasks.get_task(self.db_path, task)
        self.assertEqual(t["status"], "Assigned")
        self.assertEqual(t["assignee_id"], worker)

        # 3. Assigned -> In Progress
        tasks.update_task_status(self.db_path, task, "In Progress")
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "In Progress"
        )

        # 4. In Progress -> Submitted (via evidence submission)
        ev = evidence.submit_evidence(
            self.db_path, task, submitted_by=worker,
            evidence_type="document", url_or_path="docs/checklist-v1.md",
        )
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Submitted"
        )
        ev_row = evidence.get_evidence(self.db_path, ev)
        self.assertEqual(ev_row["submitted_by"], worker)
        self.assertIsNone(ev_row["verified_by"])

        # 5. Submitted -> Completed (evidence-gated: evidence exists)
        completion.complete_task(self.db_path, task)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Completed"
        )

        # 6. Evidence verified by an independent verifier (task stays Completed)
        evidence.verify_evidence(self.db_path, ev, verified_by=manager)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Completed"
        )
        ev_row = evidence.get_evidence(self.db_path, ev)
        self.assertEqual(ev_row["verified_by"], manager)
        self.assertIsNotNone(ev_row["verified_at"])

        # 7. Completed -> Verified (requires independent verification)
        completion.verify_task(self.db_path, task, manager)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Verified"
        )

    def test_self_verification_rejected(self):
        """The verifier must be a different person than the submitter."""
        manager, worker, project = self._make_people_and_project()
        task = tasks.add_task(self.db_path, project, "Write docs")
        tasks.assign_task(self.db_path, task, worker)
        tasks.update_task_status(self.db_path, task, "In Progress")
        ev = evidence.submit_evidence(
            self.db_path, task, worker, "note", "done it"
        )
        with self.assertRaises(ValueError):
            evidence.verify_evidence(self.db_path, ev, verified_by=worker)
        # Task must still be Submitted, evidence unverified.
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Submitted"
        )
        self.assertIsNone(
            evidence.get_evidence(self.db_path, ev)["verified_by"]
        )

    def test_invalid_transitions_rejected(self):
        """Skipping stages or moving backward (except un-assign) fails."""
        manager, worker, project = self._make_people_and_project()
        task = tasks.add_task(self.db_path, project, "Write docs")

        # Cannot skip: Proposed -> Completed
        with self.assertRaises(ValueError):
            tasks.update_task_status(self.db_path, task, "Completed")

        tasks.assign_task(self.db_path, task, worker)
        # Cannot skip: Assigned -> Submitted
        with self.assertRaises(ValueError):
            tasks.update_task_status(self.db_path, task, "Submitted")

        tasks.update_task_status(self.db_path, task, "In Progress")
        # Cannot skip: In Progress -> Verified
        with self.assertRaises(ValueError):
            tasks.update_task_status(self.db_path, task, "Verified")
        # Cannot go backward: In Progress -> Assigned
        with self.assertRaises(ValueError):
            tasks.update_task_status(self.db_path, task, "Assigned")

        # Unknown status is rejected too.
        with self.assertRaises(ValueError):
            tasks.update_task_status(self.db_path, task, "Done")

    def test_assigned_to_proposed_allowed(self):
        """Un-assigning (Assigned -> Proposed) is the one legal backward move."""
        manager, worker, project = self._make_people_and_project()
        task = tasks.add_task(self.db_path, project, "Write docs")
        tasks.assign_task(self.db_path, task, worker)
        tasks.update_task_status(self.db_path, task, "Proposed")
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Proposed"
        )

    def test_assign_requires_active_person(self):
        """Inactive people cannot be assigned tasks."""
        manager, worker, project = self._make_people_and_project()
        people.set_active(self.db_path, worker, False)
        task = tasks.add_task(self.db_path, project, "Write docs")
        with self.assertRaises(ValueError):
            tasks.assign_task(self.db_path, task, worker)

    def test_submit_evidence_requires_in_progress(self):
        """Evidence can only be submitted for work that has started."""
        manager, worker, project = self._make_people_and_project()
        task = tasks.add_task(self.db_path, project, "Write docs")
        with self.assertRaises(ValueError):
            evidence.submit_evidence(
                self.db_path, task, worker, "note", "too early"
            )

    def test_project_status_update(self):
        """Project status accepts any lifecycle stage and rejects junk."""
        manager, worker, project = self._make_people_and_project()
        projects.update_project_status(self.db_path, project, "In Progress")
        self.assertEqual(
            projects.get_project(self.db_path, project)["status"], "In Progress"
        )
        with self.assertRaises(ValueError):
            projects.update_project_status(self.db_path, project, "Archived")

    def test_list_tasks_by_project(self):
        """Tasks are listed per project."""
        manager, worker, project = self._make_people_and_project()
        other = projects.add_project(
            self.db_path, "Other", owner_id=manager
        )
        t1 = tasks.add_task(self.db_path, project, "Task one")
        t2 = tasks.add_task(self.db_path, project, "Task two")
        tasks.add_task(self.db_path, other, "Other task")
        ids = [t["id"] for t in tasks.list_tasks_by_project(self.db_path, project)]
        self.assertEqual(ids, [t1, t2])


if __name__ == "__main__":
    unittest.main()
