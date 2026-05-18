# -*- coding: utf-8 -*-
"""Unit tests for the writer module (no frappe dependency)."""

from __future__ import unicode_literals

import importlib
import json
import os
import sys
import tempfile
import unittest


class TestWriter(unittest.TestCase):
    """Tests for file I/O and validation utilities."""

    @classmethod
    def setUpClass(cls):
        # Set up frappe mock once before all tests
        frappe_mock = type(sys)("frappe")
        frappe_mock.get_app_path = lambda app, *parts: os.path.join(
            "/tmp/apps", app, *parts
        )
        frappe_mock._ = lambda x: x
        sys.modules["frappe"] = frappe_mock
        sys.modules["frappe.utils"] = type(sys)("frappe.utils")

        # Import after mock is set up
        import frappe_ai_studio.frappe_ai_studio.writer as writer_mod
        importlib.reload(writer_mod)
        cls.writer = writer_mod

    def test_safe_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.txt")
            self.writer.safe_write(path, "hello")
            self.assertEqual(self.writer.safe_read(path), "hello")

    def test_safe_write_creates_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "deep", "test.txt")
            self.writer.safe_write(path, "deep content")
            self.assertEqual(self.writer.safe_read(path), "deep content")

    def test_safe_read_missing_file(self):
        self.assertIsNone(self.writer.safe_read("/nonexistent/path/file.txt"))

    def test_validate_python_syntax_ok(self):
        ok, msg = self.writer.validate_python_syntax("def foo():\n    pass\n")
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_validate_python_syntax_error(self):
        ok, msg = self.writer.validate_python_syntax("def foo(\n")
        self.assertFalse(ok)
        self.assertIn("SyntaxError", msg)

    def test_validate_python_syntax_undefined_name(self):
        ok, msg = self.writer.validate_python_syntax("print(undefined_var)\n")
        self.assertTrue(ok)

    def test_update_json_file_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.json")
            self.writer.update_json_file(path, {"a": 1})
            data = json.loads(self.writer.safe_read(path))
            self.assertEqual(data, {"a": 1})

    def test_update_json_file_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.json")
            self.writer.safe_write(path, json.dumps({"a": 1}))
            self.writer.update_json_file(path, {"b": 2})
            data = json.loads(self.writer.safe_read(path))
            self.assertEqual(data, {"a": 1, "b": 2})

    def test_update_json_file_deep_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.json")
            self.writer.safe_write(path, json.dumps({"a": {"x": 1}}))
            self.writer.update_json_file(path, {"a": {"y": 2}})
            data = json.loads(self.writer.safe_read(path))
            self.assertEqual(data, {"a": {"x": 1, "y": 2}})

    def test_update_json_file_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.json")
            self.writer.safe_write(path, json.dumps({"a": 1}))
            self.writer.update_json_file(path, {"a": 2})
            data = json.loads(self.writer.safe_read(path))
            self.assertEqual(data, {"a": 2})


if __name__ == "__main__":
    unittest.main()
