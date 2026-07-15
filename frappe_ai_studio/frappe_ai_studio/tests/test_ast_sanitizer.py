# -*- coding: utf-8 -*-
"""Tests for AST Sanitizer (Pillar 2)."""

from __future__ import unicode_literals

import unittest

from frappe_ai_studio.frappe_ai_studio.ast_sanitizer import (
    is_code_safe,
    validate_code_security,
)


class TestASTSanitizer(unittest.TestCase):
    def test_safe_code_passes(self):
        code = """
import json
import frappe

def hello():
    data = json.dumps({"key": "value"})
    return data
"""
        ok, msg = validate_code_security(code)
        self.assertTrue(ok, msg)

    def test_forbidden_import_blocked(self):
        code = "import subprocess\n"
        ok, msg = validate_code_security(code)
        self.assertFalse(ok)
        self.assertIn("Forbidden import", msg)

    def test_forbidden_call_blocked(self):
        code = "eval('1 + 1')\n"
        ok, msg = validate_code_security(code)
        self.assertFalse(ok)
        self.assertIn("Forbidden call", msg)

    def test_exec_blocked(self):
        code = "exec('print(1)')\n"
        ok, msg = validate_code_security(code)
        self.assertFalse(ok)
        self.assertIn("Forbidden call", msg)

    def test_dunder_access_blocked(self):
        code = "obj.__class__.__bases__\n"
        ok, msg = validate_code_security(code)
        self.assertFalse(ok)
        self.assertIn("Forbidden dunder access", msg)

    def test_frappe_utils_allowed(self):
        code = """
from frappe.utils import now
import frappe

def process():
    return frappe.utils.now()
"""
        ok, msg = validate_code_security(code)
        self.assertTrue(ok, msg)

    def test_empty_code(self):
        ok, msg = validate_code_security("")
        self.assertTrue(ok)

    def test_syntax_error(self):
        code = "def foo(\n"
        ok, msg = validate_code_security(code)
        self.assertFalse(ok)
        self.assertIn("Syntax error", msg)

    def test_is_code_safe_convenience(self):
        self.assertTrue(is_code_safe("x = 1 + 1"))
        self.assertFalse(is_code_safe("import os; os.system('ls')"))


if __name__ == "__main__":
    unittest.main()
