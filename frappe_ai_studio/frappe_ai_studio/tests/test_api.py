# -*- coding: utf-8 -*-
"""Unit tests for the API module."""

from __future__ import unicode_literals

import importlib
import os
import sys
import unittest


class TestAPI(unittest.TestCase):
    """Tests for API helpers."""

    def setUp(self):
        self.frappe_mock = type(sys)("frappe")
        self.frappe_mock.get_app_path = lambda app, *parts: os.path.join("/tmp/apps", app, *parts)
        self.frappe_mock._ = lambda x: x
        self.frappe_mock.ValidationError = Exception
        self.frappe_mock.throw = lambda msg, exc=None: (_ for _ in ()).throw(exc or Exception(msg))
        self.frappe_mock.whitelist = lambda **kw: lambda f: f
        # Minimal db mock: no stored settings, so config falls back to conf.
        db_mod = type(sys)("db")
        db_mod.exists = lambda *a, **k: False
        self.frappe_mock.db = db_mod
        self.frappe_mock.flags = type(sys)("flags")
        sys.modules["frappe"] = self.frappe_mock
        sys.modules["frappe.utils"] = type(sys)("frappe.utils")

        import frappe_ai_studio.frappe_ai_studio.api as api_mod

        importlib.reload(api_mod)
        self.api = api_mod

    def test_get_llm_config_defaults(self):
        self.frappe_mock.conf = {
            "ai_studio_llm_provider": "anthropic",
            "ai_studio_api_key": "test-key",
            "ai_studio_model": "claude-3-5-sonnet-20241022",
            "ai_studio_temperature": 0.2,
        }
        config = self.api._get_llm_config()
        self.assertEqual(config["provider"], "anthropic")
        self.assertEqual(config["api_key"], "test-key")
        self.assertEqual(config["model"], "claude-3-5-sonnet-20241022")
        self.assertEqual(config["temperature"], 0.2)

    def test_get_llm_config_fallback(self):
        # With no site config and no stored settings, the built-in defaults apply.
        self.frappe_mock.conf = {}
        config = self.api._get_llm_config()
        self.assertEqual(config["provider"], "OpenAI")
        self.assertIsNone(config["api_key"])
        self.assertEqual(config["model"], "gpt-4o")
        self.assertEqual(config["temperature"], 0.2)


if __name__ == "__main__":
    unittest.main()
