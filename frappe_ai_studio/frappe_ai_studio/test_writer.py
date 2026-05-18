# -*- coding: utf-8 -*-
"""Unit tests for the writer and context engine modules (no frappe dependency)."""

from __future__ import unicode_literals

import json
import os
import sys
import tempfile
import unittest

# Allow importing writer without frappe by mocking it
sys.modules["frappe"] = type(sys)("frappe")
sys.modules["frappe.utils"] = type(sys)("frappe.utils")

# Minimal mock for frappe.get_app_path
_app_paths = {}


def _mock_get_app_path(app, *parts):
    base = _app_paths.get(app, os.path.join("/tmp", "apps", app))
    return os.path.join(base, *parts)


sys.modules["frappe"].get_app_path = _mock_get_app_path
sys.modules["frappe"]._ = lambda x: x

from frappe_ai_studio.writer import (
    safe_read,
    safe_write,
    update_json_file,
    validate_python_syntax,
)


class TestWriter(unittest.TestCase):
    def test_safe_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.txt")
            safe_write(path, "hello")
            self.assertEqual(safe_read(path), "hello")

    def test_validate_python_syntax_ok(self):
        ok, msg = validate_python_syntax("def foo():\n    pass\n")
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_validate_python_syntax_error(self):
        ok, msg = validate_python_syntax("def foo(\n")
        self.assertFalse(ok)
        self.assertIn("SyntaxError", msg)

    def test_update_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.json")
            safe_write(path, json.dumps({"a": 1}))
            update_json_file(path, {"b": 2})
            data = json.loads(safe_read(path))
            self.assertEqual(data, {"a": 1, "b": 2})


if __name__ == "__main__":
    unittest.main()
