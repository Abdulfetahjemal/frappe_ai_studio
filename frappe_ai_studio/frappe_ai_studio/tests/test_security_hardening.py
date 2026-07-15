# -*- coding: utf-8 -*-
"""Regression tests for the production-hardening security fixes.

These run without a live Frappe site — ``frappe`` is mocked the same way the
other pure-logic test modules do it.
"""

from __future__ import unicode_literals

import importlib
import os
import sys
import tempfile
import unittest


def _install_frappe_mock(base_dir):
    frappe_mock = type(sys)("frappe")
    frappe_mock._ = lambda x: x
    frappe_mock.get_app_path = lambda app, *parts: os.path.join(base_dir, app, *parts)
    frappe_mock.whitelist = lambda **kw: lambda f: f
    frappe_mock.flags = type(sys)("flags")
    sys.modules["frappe"] = frappe_mock
    sys.modules["frappe.utils"] = type(sys)("frappe.utils")
    return frappe_mock


class TestPathTraversal(unittest.TestCase):
    """resolve_app_path must never escape the target app directory."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp_dir, "myapp"), exist_ok=True)
        _install_frappe_mock(self.tmp_dir)
        import frappe_ai_studio.frappe_ai_studio.writer as writer_mod

        importlib.reload(writer_mod)
        self.writer = writer_mod

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_normal_path_ok(self):
        p = self.writer.resolve_app_path("myapp", "doctype", "thing.py")
        self.assertTrue(p.endswith(os.path.join("myapp", "doctype", "thing.py")))

    def test_dotdot_traversal_blocked(self):
        with self.assertRaises(self.writer.PathTraversalError):
            self.writer.resolve_app_path("myapp", "..", "..", "etc", "passwd")

    def test_absolute_path_blocked(self):
        with self.assertRaises(self.writer.PathTraversalError):
            self.writer.resolve_app_path("myapp", "/etc/passwd")

    def test_embedded_traversal_blocked(self):
        # A single component containing traversal segments.
        with self.assertRaises(self.writer.PathTraversalError):
            self.writer.resolve_app_path("myapp", "../../../secret.py")


class TestASTAliasingBypass(unittest.TestCase):
    """The AST sanitizer must catch aliased dangerous builtins."""

    @classmethod
    def setUpClass(cls):
        from frappe_ai_studio.frappe_ai_studio import ast_sanitizer

        cls.mod = ast_sanitizer

    def test_direct_eval_blocked(self):
        ok, _ = self.mod.validate_code_security("eval('1+1')")
        self.assertFalse(ok)

    def test_aliased_eval_blocked(self):
        # Previously bypassed: bind eval to a name, then call the name.
        ok, msg = self.mod.validate_code_security("f = eval\nf('1+1')")
        self.assertFalse(ok, "aliased eval should be rejected")

    def test_aliased_exec_reference_blocked(self):
        ok, _ = self.mod.validate_code_security("danger = exec")
        self.assertFalse(ok)

    def test_builtins_reference_blocked(self):
        ok, _ = self.mod.validate_code_security("x = __builtins__")
        self.assertFalse(ok)

    def test_safe_code_still_passes(self):
        ok, msg = self.mod.validate_code_security("import json\nx = json.dumps({'a': 1})")
        self.assertTrue(ok, msg)


class TestTolerantChangeExtraction(unittest.TestCase):
    """_extract_changes must be tolerant of conversational replies."""

    @classmethod
    def setUpClass(cls):
        _install_frappe_mock(tempfile.mkdtemp())
        import frappe_ai_studio.frappe_ai_studio.agent_orchestrator as orch

        importlib.reload(orch)
        cls.orch = orch

    def extract(self, resp):
        return self.orch._extract_changes(resp)

    def test_fenced_json_block(self):
        resp = 'Sure!\n```json\n{"changes": [{"type": "write"}]}\n```\nDone.'
        changes = self.extract(resp)
        self.assertEqual(changes[0]["type"], "write")

    def test_generic_fence(self):
        resp = '```\n{"changes": [{"type": "custom_field"}]}\n```'
        changes = self.extract(resp)
        self.assertEqual(changes[0]["type"], "custom_field")

    def test_plain_prose_returns_none(self):
        # A conversational answer with no payload must not raise.
        self.assertIsNone(self.extract("Here is how Frappe hooks work: ..."))

    def test_malformed_json_returns_none(self):
        self.assertIsNone(self.extract("```json\n{not valid json}\n```"))

    def test_empty_returns_none(self):
        self.assertIsNone(self.extract(""))


if __name__ == "__main__":
    unittest.main()
