# -*- coding: utf-8 -*-
"""Integration tests for Frappe AI Studio end-to-end workflows."""

from __future__ import unicode_literals

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest


class TestIntegration(unittest.TestCase):
    """End-to-end tests simulating AI agent workflows."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.bench_path = os.path.join(self.tmp_dir, "bench")
        self.apps_path = os.path.join(self.bench_path, "apps")
        os.makedirs(self.apps_path)

        self.target_app = "test_library"
        app_dir = os.path.join(self.apps_path, self.target_app, self.target_app)
        os.makedirs(app_dir)
        with open(os.path.join(app_dir, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(app_dir, "hooks.py"), "w") as f:
            f.write('app_name = "{}"\n'.format(self.target_app))
        with open(os.path.join(self.apps_path, self.target_app, "modules.txt"), "w") as f:
            f.write("{}\n".format(self.target_app))

        subprocess.run(
            ["git", "init"], cwd=os.path.join(self.apps_path, self.target_app), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=os.path.join(self.apps_path, self.target_app),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=os.path.join(self.apps_path, self.target_app),
            capture_output=True,
        )
        with open(os.path.join(self.apps_path, self.target_app, "README.md"), "w") as f:
            f.write("# Test App")
        subprocess.run(
            ["git", "add", "."],
            cwd=os.path.join(self.apps_path, self.target_app),
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=os.path.join(self.apps_path, self.target_app),
            capture_output=True,
        )

        frappe_mock = type(sys)("frappe")
        frappe_mock._ = lambda x: x
        utils_mod = type(sys)("utils")
        utils_mod.get_bench_path = lambda: self.bench_path
        frappe_mock.utils = utils_mod
        cache_mod = type(sys)("cache")
        cache_mod.set_value = lambda k, v: None
        cache_mod.get_value = lambda k: None
        frappe_mock.cache = lambda: cache_mod
        frappe_mock.get_app_path = lambda app, *parts: os.path.join(
            self.apps_path, app, app, *parts
        )

        sys.modules["frappe"] = frappe_mock
        sys.modules["frappe.utils"] = utils_mod

        import frappe_ai_studio.frappe_ai_studio.writer as writer_mod
        import frappe_ai_studio.frappe_ai_studio.context_engine as ce_mod
        importlib.reload(writer_mod)
        importlib.reload(ce_mod)
        self.writer = writer_mod
        self.ce = ce_mod

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_full_workflow_write_validate_snapshot(self):
        code = "class Book:\n    def __init__(self, title):\n        self.title = title\n"
        file_path = os.path.join(
            self.apps_path, self.target_app, self.target_app, "book.py"
        )
        self.writer.safe_write(file_path, code)

        ok, msg = self.writer.validate_python_syntax(code)
        self.assertTrue(ok, msg)

        ok, msg = self.writer.git_snapshot(self.target_app)
        self.assertTrue(ok, msg)

        self.assertTrue(os.path.isfile(file_path))
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=os.path.join(self.apps_path, self.target_app),
            capture_output=True, text=True,
        )
        self.assertIn("ai-studio: pre-change snapshot", result.stdout)

    def test_full_workflow_bad_code_rejected(self):
        bad_code = "class Book(\n"
        ok, msg = self.writer.validate_python_syntax(bad_code)
        self.assertFalse(ok)
        self.assertIn("SyntaxError", msg)

    def test_full_workflow_json_doctype_creation(self):
        doctype_def = {
            "name": "LibraryBook",
            "module": self.target_app,
            "custom": 1,
            "fields": [
                {"fieldname": "title", "fieldtype": "Data", "label": "Title", "reqd": 1},
                {"fieldname": "author", "fieldtype": "Data", "label": "Author"},
                {"fieldname": "isbn", "fieldtype": "Data", "label": "ISBN"},
                {"fieldname": "status", "fieldtype": "Select", "label": "Status",
                 "options": "Available\nIssued\nLost", "default": "Available"},
            ],
        }

        dt_folder = os.path.join(
            self.apps_path, self.target_app, self.target_app, "doctype", "LibraryBook"
        )
        os.makedirs(dt_folder, exist_ok=True)
        json_path = os.path.join(dt_folder, "LibraryBook.json")

        with open(json_path, "w") as f:
            json.dump(doctype_def, f, indent=1)

        with open(json_path) as f:
            data = json.load(f)
        self.assertEqual(data["name"], "LibraryBook")
        self.assertEqual(len(data["fields"]), 4)

        self.writer.update_json_file(json_path, {"fields": data["fields"] + [
            {"fieldname": "published_date", "fieldtype": "Date", "label": "Published Date"}
        ]})

        with open(json_path) as f:
            updated = json.load(f)
        self.assertEqual(len(updated["fields"]), 5)

    def test_context_building_for_llm(self):
        context = self.ce.build_context(target_app=self.target_app)
        self.assertIn("apps", context)
        self.assertIn(self.target_app, context["apps"])
        meta = context["apps"][self.target_app]
        self.assertIn("hooks", meta)
        self.assertIn("modules", meta)


if __name__ == "__main__":
    unittest.main()
