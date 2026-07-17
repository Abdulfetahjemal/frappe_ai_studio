# -*- coding: utf-8 -*-
"""Pure-logic tests for the senior-developer capability guards.

Runs without a live Frappe site (frappe is mocked), covering the safety-
critical validators: app-name validation and read-only SQL enforcement for
Query Reports.
"""

from __future__ import unicode_literals

import importlib
import sys
import tempfile
import unittest


def _install_frappe_mock():
    frappe_mock = type(sys)("frappe")
    frappe_mock._ = lambda x: x
    frappe_mock.whitelist = lambda **kw: lambda f: f
    frappe_mock.flags = type(sys)("flags")
    utils_mod = type(sys)("utils")
    utils_mod.get_bench_path = lambda: tempfile.gettempdir()
    frappe_mock.utils = utils_mod
    sys.modules["frappe"] = frappe_mock
    sys.modules["frappe.utils"] = utils_mod
    return frappe_mock


class TestAppNameValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_frappe_mock()
        import frappe_ai_studio.frappe_ai_studio.builder as builder

        importlib.reload(builder)
        cls.builder = builder

    def test_valid_names(self):
        for name in ("library_management", "hr_addons", "app2"):
            ok, msg = self.builder.validate_app_name(name)
            self.assertTrue(ok, "{} should be valid: {}".format(name, msg))

    def test_reserved_names_blocked(self):
        for name in ("frappe", "erpnext", "bench"):
            ok, _ = self.builder.validate_app_name(name)
            self.assertFalse(ok, "{} must be reserved".format(name))

    def test_invalid_names_blocked(self):
        for name in ("Library", "9app", "my-app", "my app", "", "a", "__proto__"):
            ok, _ = self.builder.validate_app_name(name)
            self.assertFalse(ok, "{} must be rejected".format(name))


class TestReadonlySQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_frappe_mock()
        import frappe_ai_studio.frappe_ai_studio.advanced_customization as adv

        importlib.reload(adv)
        cls.adv = adv

    def test_select_allowed(self):
        ok, msg = self.adv.validate_readonly_sql("SELECT name FROM `tabLibrary Loan`")
        self.assertTrue(ok, msg)

    def test_with_cte_allowed(self):
        ok, _ = self.adv.validate_readonly_sql("WITH x AS (SELECT 1) SELECT * FROM x")
        self.assertTrue(ok)

    def test_write_statements_blocked(self):
        for q in (
            "DELETE FROM `tabLibrary Loan`",
            "UPDATE `tabLibrary Loan` SET status='x'",
            "DROP TABLE `tabLibrary Loan`",
            "INSERT INTO `tabLibrary Loan` VALUES (1)",
            "TRUNCATE `tabLibrary Loan`",
        ):
            ok, _ = self.adv.validate_readonly_sql(q)
            self.assertFalse(ok, "{} must be blocked".format(q))

    def test_multiple_statements_blocked(self):
        ok, _ = self.adv.validate_readonly_sql("SELECT 1; DROP TABLE x")
        self.assertFalse(ok)

    def test_non_select_blocked(self):
        ok, _ = self.adv.validate_readonly_sql("SHOW TABLES")
        self.assertFalse(ok)

    def test_empty_blocked(self):
        ok, _ = self.adv.validate_readonly_sql("")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
