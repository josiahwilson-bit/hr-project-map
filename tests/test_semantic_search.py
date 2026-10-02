"""Tests for queries.semantic_search: structured filter dict -> parameterized SQL.

Covers the Issue 3 acceptance criteria: allowlisted keys, unknown-key
rejection, empty filters, None -> IS NULL, and injection strings treated
as data. Temp SQLite database; stdlib unittest only.
"""

import os
import shutil
import sys
import tempfile
import unittest

# Make `src` importable when running `python -m unittest discover -s tests`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import db, people, projects, queries, tasks


class SemanticSearchTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        db.init_db(self.db_path)
        self.alice = people.add_person(
            self.db_path, "Alice", "Employee", "alice@example.com"
        )
        self.bob = people.add_person(
            self.db_path, "Bob", "Employee", "bob@example.com"
        )
        self.owner = people.add_person(
            self.db_path, "Owner", "Manager", "owner@example.com"
        )
        self.proj_a = projects.add_project(
            self.db_path, "Alpha", owner_id=self.owner
        )
        self.proj_b = projects.add_project(
            self.db_path, "Beta", owner_id=self.owner
        )
        # Seed via the API, then set exact statuses directly (test DB only).
        self.t1 = tasks.add_task(
            self.db_path, self.proj_a, "Write spec", assignee_id=self.alice
        )
        self.t2 = tasks.add_task(self.db_path, self.proj_a, "Fix bug")
        self.t3 = tasks.add_task(
            self.db_path, self.proj_b, "Deploy", assignee_id=self.bob
        )
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                ("Verified", self.t1),
            )
            conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                ("In Progress", self.t3),
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_filters_returns_all(self):
        rows = queries.semantic_search(self.db_path, {})
        self.assertEqual(len(rows), 3)

    def test_status_filter(self):
        rows = queries.semantic_search(self.db_path, {"status": "Verified"})
        self.assertEqual([r["id"] for r in rows], [self.t1])

    def test_project_id_filter(self):
        rows = queries.semantic_search(
            self.db_path, {"project_id": self.proj_b}
        )
        self.assertEqual([r["id"] for r in rows], [self.t3])

    def test_assignee_filter_and_none(self):
        rows = queries.semantic_search(
            self.db_path, {"assignee_id": self.alice}
        )
        self.assertEqual([r["id"] for r in rows], [self.t1])
        # None becomes IS NULL: only the unassigned task matches.
        rows = queries.semantic_search(self.db_path, {"assignee_id": None})
        self.assertEqual([r["id"] for r in rows], [self.t2])

    def test_combined_filters(self):
        rows = queries.semantic_search(
            self.db_path,
            {"project_id": self.proj_a, "status": "Proposed"},
        )
        self.assertEqual([r["id"] for r in rows], [self.t2])

    def test_unknown_key_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            queries.semantic_search(self.db_path, {"bogus": "x"})
        self.assertIn("bogus", str(ctx.exception))

    def test_injection_string_treated_as_data(self):
        rows = queries.semantic_search(
            self.db_path, {"status": "x' OR '1'='1"}
        )
        self.assertEqual(rows, [])

    def test_no_match_returns_empty_list(self):
        rows = queries.semantic_search(
            self.db_path, {"status": "Nonexistent"}
        )
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
