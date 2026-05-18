# -*- coding: utf-8 -*-
"""Unit tests for the context engine module."""

from __future__ import unicode_literals

import importlib
import os
import sys
import tempfile
import unittest


class TestContextEngine(unittest.TestCase):
    """Tests for bench/app context scanning."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.bench_path = os.path.join(self.tmp_dir, "bench")
        self.apps_path = os.path.join(self.bench_path, "apps")
        os.makedirs(self.apps_path)

        for app_name in ["frappe", "erpnext", "test_app"]:
            app_dir = os.path.join(self.apps_path, app_name, app_name)
            os.makedirs(app_dir)
            with open(os.path.join(app_dir, "__init__.py"), "w") as f:
                f.write("")
            with open(os.path.join(app_dir, "hooks.py"), "w") as f:
                f.write('app_name = "{}"\n'.format(app_name))
            with open(os.path.join(self.apps_path, app_name, "modules.txt"), "w") as f:
                f.write("{}\n".format(app_name))

        # Set up frappe mock
        frappe_mock = type(sys)("frappe")
        frappe_mock.get_app_path = lambda app, *parts: os.path.join(
            self.apps_path, app, app, *parts
        )
        utils_mod = type(sys)("utils")
        utils_mod.get_bench_path = lambda: self.bench_path
        frappe_mock.utils = utils_mod
        cache_mod = type(sys)("cache")
        cache_mod.set_value = lambda k, v: None
        cache_mod.get_value = lambda k: None
        frappe_mock.cache = lambda: cache_mod
        sys.modules["frappe"] = frappe_mock
        sys.modules["frappe.utils"] = utils_mod

        # Import after mock is set up
        import frappe_ai_studio.frappe_ai_studio.context_engine as ce_mod
        importlib.reload(ce_mod)
        self.ce = ce_mod

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_list_installed_apps(self):
        apps = self.ce.list_installed_apps()
        self.assertIn("frappe", apps)
        self.assertIn("erpnext", apps)
        self.assertIn("test_app", apps)

    def test_get_app_metadata(self):
        meta = self.ce.get_app_metadata("test_app")
        self.assertEqual(meta["app_name"], "test_app")
        self.assertIn("hooks", meta)
        self.assertIn("modules", meta)
        self.assertIn("doctypes", meta)
        self.assertIn("apis", meta)

    def test_build_context(self):
        context = self.ce.build_context()
        self.assertIn("bench_path", context)
        self.assertIn("apps", context)
        self.assertIn("frappe", context["apps"])
        self.assertIn("erpnext", context["apps"])
        self.assertIn("test_app", context["apps"])

    def test_build_context_target_app(self):
        context = self.ce.build_context(target_app="test_app")
        self.assertIn("apps", context)
        self.assertIn("test_app", context["apps"])
        self.assertNotIn("frappe", context["apps"])


if __name__ == "__main__":
    unittest.main()
