# -*- coding: utf-8 -*-
"""Unit tests for git snapshot and rollback operations."""

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
        """Helper to create a mock git repo for testing."""
        repo_path = os.path.join(self.tmp_dir, app_name)
        app_dir = os.path.join(repo_path, app_name)
        os.makedirs(app_dir)

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, text=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path, capture_output=True, text=True,
        )

        with open(os.path.join(repo_path, "test.txt"), "w") as f:
            f.write("hello")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, text=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=repo_path, capture_output=True, text=True,
        )

        # Set up frappe mock with correct path
        frappe_mock = type(sys)("frappe")
        frappe_mock._ = lambda x: x
        frappe_mock.get_app_path = lambda app, *parts: os.path.join(
            app_dir, *parts
        )
        sys.modules["frappe"] = frappe_mock
        sys.modules["frappe.utils"] = type(sys)("frappe.utils")

        # Reload writer to pick up new mock
        import frappe_ai_studio.frappe_ai_studio.writer as writer_mod
        importlib.reload(writer_mod)
        self.writer = writer_mod

        return repo_path

    def test_git_snapshot_with_changes(self):
        app_name = "test_app_snapshot"
        repo_path = self._create_git_repo(app_name)

        with open(os.path.join(repo_path, "test.txt"), "w") as f:
            f.write("modified")

        ok, msg = self.writer.git_snapshot(app_name)
        self.assertTrue(ok, "Snapshot failed: {}".format(msg))
        self.assertEqual(msg, "Snapshot committed")

    def test_git_rollback_restores_changes(self):
        app_name = "test_app_rollback"
        repo_path = self._create_git_repo(app_name)

        with open(os.path.join(repo_path, "test.txt"), "w") as f:
            f.write("modified")
        self.writer.git_snapshot(app_name)

        with open(os.path.join(repo_path, "test.txt"), "w") as f:
            f.write("more modified")

        ok, msg = self.writer.git_rollback(app_name)
        self.assertTrue(ok, "Rollback failed: {}".format(msg))

        with open(os.path.join(repo_path, "test.txt")) as f:
            content = f.read()
        self.assertEqual(content, "modified")

    def test_git_snapshot_no_changes(self):
        app_name = "test_app_no_changes"
        self._create_git_repo(app_name)

        ok, msg = self.writer.git_snapshot(app_name)
        self.assertFalse(ok)
        self.assertTrue(
            "failed" in msg.lower() or "nothing" in msg.lower() or "commit" in msg.lower()
        )

    def test_git_rollback_no_repo(self):
        app_name = "test_app_no_repo"
        no_git_dir = os.path.join(self.tmp_dir, "no_git_app", app_name)
        os.makedirs(no_git_dir)

        frappe_mock = type(sys)("frappe")
        frappe_mock.get_app_path = lambda app, *parts: os.path.join(
            no_git_dir, *parts
        )
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
