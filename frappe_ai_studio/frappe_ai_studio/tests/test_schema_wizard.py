# -*- coding: utf-8 -*-
"""Unit tests for the schema wizard module."""

from __future__ import unicode_literals

import importlib
import json
import os
import sys
import tempfile
import unittest


class TestSchemaWizard(unittest.TestCase):
    """Tests for DocType JSON generation."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

        frappe_mock = type(sys)("frappe")
        frappe_mock.get_app_path = lambda app, *parts: os.path.join(
            self.tmp_dir, app, *parts
        )
        frappe_mock._ = lambda x: x
        frappe_mock.db = type(sys)("db")
        frappe_mock.db.exists = lambda dt, dn: False
        frappe_mock.db.commit = lambda: None

        frappe_mock.core = type(sys)("core")
        frappe_mock.core.doctype = type(sys)("doctype")
        frappe_mock.core.doctype.doctype = type(sys)("doctype")
        frappe_mock.core.doctype.doctype.DocType = type("DocType", (), {})
        frappe_mock.get_doc = lambda *a, **k: None

        sys.modules["frappe"] = frappe_mock
        sys.modules["frappe.utils"] = type(sys)("frappe.utils")
        sys.modules["frappe.core"] = frappe_mock.core
        sys.modules["frappe.core.doctype"] = frappe_mock.core.doctype
        sys.modules["frappe.core.doctype.doctype"] = frappe_mock.core.doctype.doctype
        sys.modules["frappe.core.doctype.doctype.doctype"] = frappe_mock.core.doctype.doctype

        import frappe_ai_studio.frappe_ai_studio.schema_wizard as sw_mod
        importlib.reload(sw_mod)
        self.sw = sw_mod

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_doctype_writes_json(self):
        definition = {
            "name": "TestBook",
            "module": "Test Module",
            "custom": 1,
            "fields": [
                {"fieldname": "title", "fieldtype": "Data", "label": "Title"},
                {"fieldname": "author", "fieldtype": "Data", "label": "Author"},
            ],
        }

        app_path = os.path.join(self.tmp_dir, "test_app")
        os.makedirs(app_path, exist_ok=True)
        sys.modules["frappe"].get_app_path = lambda app, *parts: os.path.join(
            app_path, *parts
        )
        importlib.reload(self.sw)

        dt_folder = os.path.join(app_path, "doctype", "TestBook")
        os.makedirs(dt_folder, exist_ok=True)
        json_path = os.path.join(dt_folder, "TestBook.json")

        with open(json_path, "w") as f:
            json.dump(definition, f, indent=1)

        self.assertTrue(os.path.isfile(json_path))
        with open(json_path) as f:
            data = json.load(f)
        self.assertEqual(data["name"], "TestBook")
        self.assertEqual(len(data["fields"]), 2)

    def test_export_doctype_to_json(self):
        class MockDoc:
            def as_dict(self):
                return {
                    "name": "TestExport",
                    "module": "Test",
                    "fields": [],
                    "_server_field": "should_be_stripped",
                }

        sys.modules["frappe"].get_doc = lambda *a, **k: MockDoc()
        importlib.reload(self.sw)

        result = self.sw.export_doctype_to_json("TestExport", "test_app")
        self.assertEqual(result["status"], "exported")
        self.assertTrue(os.path.isfile(result["path"]))

        with open(result["path"]) as f:
            data = json.load(f)
        self.assertEqual(data["name"], "TestExport")
        self.assertNotIn("_server_field", data)


if __name__ == "__main__":
    unittest.main()
