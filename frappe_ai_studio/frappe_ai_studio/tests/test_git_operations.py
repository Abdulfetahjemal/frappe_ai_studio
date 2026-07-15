# -*- coding: utf-8 -*-
"""Unit tests for git snapshot and rollback operations.

These exercise the *scoped* git behaviour: snapshot/rollback only ever touch
the target app's own subtree, never the wider repository.
"""

from __future__ import unicode_literals

import importlib
import os
import subprocess
import sys
import tempfile
import unittest


class TestGitOperations(unittest.TestCase):
    """Tests for git snapshot and rollback functionality."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_git_repo(self, app_name):
        """Create a mock repo laid out like a Frappe app.

        Structure:  <repo>/<app_name>/   <- the app subtree (get_app_path)
        A tracked file lives *inside* the app subtree, matching real usage
        where AI Studio only ever writes within the app.
        """
        repo_path = os.path.join(self.tmp_dir, app_name)
        app_dir = os.path.join(repo_path, app_name)
        os.makedirs(app_dir)

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, text=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Tracked file inside the app subtree.
        with open(os.path.join(app_dir, "module.py"), "w") as f:
            f.write("value = 1\n")
        # An unrelated tracked file at repo root (must never be touched).
        with open(os.path.join(repo_path, "unrelated.txt"), "w") as f:
            f.write("keep me\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, text=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        frappe_mock = type(sys)("frappe")
        frappe_mock._ = lambda x: x
        frappe_mock.get_app_path = lambda app, *parts: os.path.join(app_dir, *parts)
        sys.modules["frappe"] = frappe_mock
        sys.modules["frappe.utils"] = type(sys)("frappe.utils")

        import frappe_ai_studio.frappe_ai_studio.writer as writer_mod

        importlib.reload(writer_mod)
        self.writer = writer_mod

        return repo_path, app_dir

    def test_git_snapshot_with_changes(self):
        app_name = "test_app_snapshot"
        _, app_dir = self._create_git_repo(app_name)

        with open(os.path.join(app_dir, "module.py"), "w") as f:
            f.write("value = 2\n")

        ok, msg = self.writer.git_snapshot(app_name)
        self.assertTrue(ok, "Snapshot failed: {}".format(msg))
        self.assertEqual(msg, "Snapshot committed")

    def test_git_snapshot_no_changes(self):
        app_name = "test_app_no_changes"
        self._create_git_repo(app_name)

        ok, msg = self.writer.git_snapshot(app_name)
        # Clean subtree: snapshot is a no-op but still successful.
        self.assertTrue(ok)
        self.assertIn("no snapshot needed", msg.lower())

    def test_git_rollback_restores_tracked_changes(self):
        app_name = "test_app_rollback"
        repo_path, app_dir = self._create_git_repo(app_name)

        # Snapshot a first modification...
        with open(os.path.join(app_dir, "module.py"), "w") as f:
            f.write("value = 2\n")
        self.writer.git_snapshot(app_name)

        # ...then make a further (unwanted) change and roll it back.
        with open(os.path.join(app_dir, "module.py"), "w") as f:
            f.write("value = 999\n")

        ok, msg = self.writer.git_rollback(app_name)
        self.assertTrue(ok, "Rollback failed: {}".format(msg))
        with open(os.path.join(app_dir, "module.py")) as f:
            self.assertEqual(f.read(), "value = 2\n")

    def test_git_rollback_removes_new_files(self):
        app_name = "test_app_rollback_new"
        repo_path, app_dir = self._create_git_repo(app_name)

        # A brand-new (untracked) file created by a failed apply.
        new_file = os.path.join(app_dir, "generated.py")
        with open(new_file, "w") as f:
            f.write("x = 1\n")

        ok, msg = self.writer.git_rollback(app_name)
        self.assertTrue(ok, "Rollback failed: {}".format(msg))
        self.assertFalse(os.path.exists(new_file), "Untracked file should be cleaned")

    def test_git_rollback_leaves_unrelated_files(self):
        app_name = "test_app_scope"
        repo_path, app_dir = self._create_git_repo(app_name)

        # Modify an unrelated repo-root file (outside the app subtree).
        unrelated = os.path.join(repo_path, "unrelated.txt")
        with open(unrelated, "w") as f:
            f.write("locally edited\n")

        self.writer.git_rollback(app_name)

        # The unrelated change must survive — rollback is scoped to the app.
        with open(unrelated) as f:
            self.assertEqual(f.read(), "locally edited\n")

    def test_git_rollback_no_repo(self):
        app_name = "test_app_no_repo"
        no_git_dir = os.path.join(self.tmp_dir, "no_git_app", app_name)
        os.makedirs(no_git_dir)

        frappe_mock = type(sys)("frappe")
        frappe_mock.get_app_path = lambda app, *parts: os.path.join(no_git_dir, *parts)
        frappe_mock._ = lambda x: x
        sys.modules["frappe"] = frappe_mock
        sys.modules["frappe.utils"] = type(sys)("frappe.utils")

        import frappe_ai_studio.frappe_ai_studio.writer as writer_mod

        importlib.reload(writer_mod)

        ok, msg = writer_mod.git_rollback(app_name)
        self.assertFalse(ok)
        self.assertIn("No git repository", msg)


if __name__ == "__main__":
    unittest.main()
