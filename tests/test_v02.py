"""v0.2 tests: evidence-gated completion, milestones, sync, and the
v0.4-era lifecycle
(Submitted -> Under Review -> Accepted -> Completed -> Verified).
Temp SQLite database; stdlib unittest only."""

import json
import os
import shutil
import sys
import tempfile
import unittest

# Make `src` importable when running `python -m unittest discover -s tests`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import completion, db, evidence, milestones, people, projects, review, sync, tasks


class EvidenceGatesTest(unittest.TestCase):
    """The core v0.2 integrity rule: the system records what happened; it
    does not manufacture evidence that something happened."""

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

    def _task_in_progress(self, project, worker):
        task = tasks.add_task(self.db_path, project, "Write docs")
        tasks.assign_task(self.db_path, task, worker)
        tasks.update_task_status(self.db_path, task, "In Progress")
        return task

    def _force_accepted_without_evidence(self, task):
        """Simulate a corrupt import or direct-DB edit: Accepted with no
        evidence rows. The gates must still hold."""
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE tasks SET status = 'Accepted' WHERE id = ?", (task,)
            )
            conn.commit()
        finally:
            conn.close()

    def _drive_to_accepted(self, task, worker, verifier):
        """Submitted -> Under Review -> Accepted via the review workflow."""
        review.start_review(self.db_path, task, verifier)
        review.accept_review(self.db_path, task, verifier)

    def test_task_cannot_complete_without_evidence(self):
        manager, worker, project = self._make_people_and_project()
        task = self._task_in_progress(project, worker)
        self._force_accepted_without_evidence(task)

        with self.assertRaisesRegex(ValueError, "without evidence"):
            completion.complete_task(self.db_path, task)
        with self.assertRaisesRegex(ValueError, "without evidence"):
            tasks.update_task_status(self.db_path, task, "Completed")
        # Task must remain Accepted.
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Accepted"
        )

    def test_task_can_complete_with_evidence(self):
        manager, worker, project = self._make_people_and_project()
        task = self._task_in_progress(project, worker)
        evidence.submit_evidence(
            self.db_path, task, submitted_by=worker,
            evidence_type="document", url_or_path="docs/draft.md",
        )
        self._drive_to_accepted(task, worker, manager)
        completion.complete_task(self.db_path, task)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Completed"
        )

    def test_task_cannot_verify_without_verifier(self):
        manager, worker, project = self._make_people_and_project()
        task = self._task_in_progress(project, worker)
        evidence.submit_evidence(
            self.db_path, task, submitted_by=worker,
            evidence_type="note", url_or_path="done",
        )
        self._drive_to_accepted(task, worker, manager)
        completion.complete_task(self.db_path, task)

        # Evidence exists but nobody verified it: both paths must refuse.
        with self.assertRaises(ValueError):
            completion.verify_task(self.db_path, task, manager)
        with self.assertRaises(ValueError):
            tasks.update_task_status(self.db_path, task, "Verified")
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Completed"
        )

    def test_task_can_verify_with_evidence_and_verifier(self):
        manager, worker, project = self._make_people_and_project()
        task = self._task_in_progress(project, worker)
        ev = evidence.submit_evidence(
            self.db_path, task, submitted_by=worker,
            evidence_type="document", url_or_path="docs/draft.md",
        )
        self._drive_to_accepted(task, worker, manager)
        completion.complete_task(self.db_path, task)
        evidence.verify_evidence(self.db_path, ev, verified_by=manager)
        completion.verify_task(self.db_path, task, manager)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Verified"
        )

    def test_verify_task_rejects_self_verified_evidence(self):
        """Even a verified evidence record is not enough when the verifier
        is the submitter (defense in depth alongside verify_evidence)."""
        manager, worker, project = self._make_people_and_project()
        task = self._task_in_progress(project, worker)
        ev = evidence.submit_evidence(
            self.db_path, task, submitted_by=worker,
            evidence_type="note", url_or_path="done",
        )
        self._drive_to_accepted(task, worker, manager)
        completion.complete_task(self.db_path, task)
        # verify_evidence itself rejects self-verification; force the stamp
        # directly to test verify_task's own guard.
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE evidence SET verified_by = ?, verified_at = ?"
                " WHERE id = ?",
                (worker, db.utcnow(), ev),
            )
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(ValueError):
            completion.verify_task(self.db_path, task, worker)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Completed"
        )


class MilestoneTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        db.init_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_milestone_crud_and_forward_only_transitions(self):
        manager = people.add_person(self.db_path, "Jane Doe", "Manager")
        project = projects.add_project(
            self.db_path, "Website", owner_id=manager
        )
        mid = milestones.add_milestone(
            self.db_path, project, "Beta launch",
            description="Feature-complete beta", due_date="2026-11-30",
        )
        m = milestones.get_milestone(self.db_path, mid)
        self.assertEqual(m["name"], "Beta launch")
        self.assertEqual(m["status"], "Proposed")

        listed = milestones.list_milestones_by_project(self.db_path, project)
        self.assertEqual([x["id"] for x in listed], [mid])

        milestones.update_milestone_status(self.db_path, mid, "Assigned")
        milestones.update_milestone_status(self.db_path, mid, "In Progress")
        milestones.update_milestone_status(self.db_path, mid, "Completed")
        self.assertEqual(
            milestones.get_milestone(self.db_path, mid)["status"], "Completed"
        )

        # No backward moves, no skipping.
        with self.assertRaises(ValueError):
            milestones.update_milestone_status(self.db_path, mid, "Proposed")
        with self.assertRaises(ValueError):
            milestones.update_milestone_status(self.db_path, mid, "Done")

    def test_milestone_requires_existing_project(self):
        with self.assertRaises(ValueError):
            milestones.add_milestone(
                self.db_path, "no-such-project", "Ghost milestone"
            )

    def test_task_milestone_linking(self):
        manager = people.add_person(self.db_path, "Jane Doe", "Manager")
        project = projects.add_project(
            self.db_path, "Website", owner_id=manager
        )
        other = projects.add_project(self.db_path, "Other", owner_id=manager)
        mid = milestones.add_milestone(self.db_path, project, "Beta launch")

        tid = tasks.add_task(
            self.db_path, project, "Write copy", milestone_id=mid
        )
        self.assertEqual(
            tasks.get_task(self.db_path, tid)["milestone_id"], mid
        )

        # A milestone from another project is refused.
        with self.assertRaises(ValueError):
            tasks.add_task(
                self.db_path, other, "Wrong milestone", milestone_id=mid
            )
        # A nonexistent milestone is refused.
        with self.assertRaises(ValueError):
            tasks.add_task(
                self.db_path, project, "Ghost milestone",
                milestone_id="no-such-milestone",
            )


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.export_dir = os.path.join(self.tmpdir, "export")
        db.init_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _seed(self):
        manager = people.add_person(
            self.db_path, "Jane Doe", "Manager", "jane@example.com"
        )
        worker = people.add_person(self.db_path, "Sam Lee", "Employee")
        project = projects.add_project(
            self.db_path, "Website", "New site", owner_id=manager
        )
        mid = milestones.add_milestone(self.db_path, project, "Beta launch")
        task = tasks.add_task(
            self.db_path, project, "Write copy", assignee_id=worker,
            milestone_id=mid,
        )
        tasks.update_task_status(self.db_path, task, "In Progress")
        evidence.submit_evidence(
            self.db_path, task, submitted_by=worker,
            evidence_type="document", url_or_path="docs/copy.md",
        )
        return {
            "people": 2, "projects": 1, "milestones": 1,
            "tasks": 1, "evidence": 1,
        }

    def test_export_import_round_trip(self):
        counts = self._seed()
        sync.export_to_json(self.db_path, self.export_dir)

        for table, filename in (
            ("people", "people.json"), ("projects", "projects.json"),
            ("milestones", "milestones.json"), ("tasks", "tasks.json"),
            ("evidence", "evidence.json"),
        ):
            path = os.path.join(self.export_dir, filename)
            with open(path, encoding="utf-8") as f:
                records = json.load(f)  # strict JSON: no comments allowed
            self.assertEqual(len(records), counts[table])

        # Import into a fresh database and compare.
        db2 = os.path.join(self.tmpdir, "test2.db")
        sync.import_from_json(db2, self.export_dir)
        conn = db.connect(self.db_path)
        conn2 = db.connect(db2)
        try:
            for table in ("people", "projects", "milestones", "tasks",
                          "evidence"):
                n1 = conn.execute(
                    "SELECT COUNT(*) AS n FROM %s" % table
                ).fetchone()["n"]
                n2 = conn2.execute(
                    "SELECT COUNT(*) AS n FROM %s" % table
                ).fetchone()["n"]
                self.assertEqual(n1, n2, "row count mismatch for %s" % table)
            # Spot-check a linked record survived the round trip.
            t1 = conn.execute(
                "SELECT title, milestone_id FROM tasks"
            ).fetchone()
            t2 = conn2.execute(
                "SELECT title, milestone_id FROM tasks"
            ).fetchone()
            self.assertEqual(t1["title"], t2["title"])
            self.assertEqual(t1["milestone_id"], t2["milestone_id"])
        finally:
            conn.close()
            conn2.close()

    def test_import_refuses_missing_foreign_key(self):
        bad_dir = os.path.join(self.tmpdir, "bad")
        os.makedirs(bad_dir)
        for filename in ("people.json", "projects.json", "milestones.json",
                         "evidence.json"):
            with open(os.path.join(bad_dir, filename), "w") as f:
                json.dump([], f)
        with open(os.path.join(bad_dir, "tasks.json"), "w") as f:
            json.dump([{
                "id": "t1", "project_id": "no-such-project",
                "title": "Orphan task", "status": "Proposed",
            }], f)
        with self.assertRaisesRegex(ValueError, "missing project"):
            sync.import_from_json(
                os.path.join(self.tmpdir, "bad.db"), bad_dir
            )

    def test_import_skips_duplicate_ids(self):
        self._seed()
        sync.export_to_json(self.db_path, self.export_dir)
        # Importing into the SAME database must not duplicate or fail.
        sync.import_from_json(self.db_path, self.export_dir)
        conn = db.connect(self.db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM tasks"
            ).fetchone()["n"]
            self.assertEqual(n, 1)
        finally:
            conn.close()


class TransitionOrderTest(unittest.TestCase):
    """v0.4 lifecycle: Submitted -> Under Review -> Accepted -> Completed
    -> Verified. Review is mandatory — Submitted can no longer jump to
    Completed or Verified."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        db.init_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_submitted_cannot_jump_to_verified(self):
        manager = people.add_person(self.db_path, "Jane Doe", "Manager")
        worker = people.add_person(self.db_path, "Sam Lee", "Employee")
        project = projects.add_project(
            self.db_path, "Website", owner_id=manager
        )
        task = tasks.add_task(self.db_path, project, "Write copy")
        tasks.assign_task(self.db_path, task, worker)
        tasks.update_task_status(self.db_path, task, "In Progress")
        ev = evidence.submit_evidence(
            self.db_path, task, submitted_by=worker,
            evidence_type="note", url_or_path="done",
        )
        evidence.verify_evidence(self.db_path, ev, verified_by=manager)

        # Verified evidence alone does not move the task anymore.
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Submitted"
        )
        # Submitted -> Verified and Submitted -> Completed are both refused.
        with self.assertRaises(ValueError):
            tasks.update_task_status(self.db_path, task, "Verified")
        with self.assertRaises(ValueError):
            tasks.update_task_status(self.db_path, task, "Completed")
        with self.assertRaises(ValueError):
            completion.complete_task(self.db_path, task)
        # The legal path works:
        # Submitted -> Under Review -> Accepted -> Completed -> Verified.
        review.start_review(self.db_path, task, manager)
        review.accept_review(self.db_path, task, manager)
        completion.complete_task(self.db_path, task)
        completion.verify_task(self.db_path, task, manager)
        self.assertEqual(
            tasks.get_task(self.db_path, task)["status"], "Verified"
        )


if __name__ == "__main__":
    unittest.main()
