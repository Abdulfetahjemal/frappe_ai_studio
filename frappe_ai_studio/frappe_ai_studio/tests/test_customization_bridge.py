# -*- coding: utf-8 -*-
"""Tests for Customization Bridge (Pillar 3)."""

from __future__ import unicode_literals

import unittest

import frappe

from frappe_ai_studio.frappe_ai_studio.customization_bridge import (
    safe_custom_field,
    safe_property_setter,
    safe_server_script,
    safe_client_script,
)


class TestCustomizationBridge(unittest.TestCase):
    def test_safe_custom_field_create_and_update(self):
        """Create a custom field, then update it idempotently."""
        doctype = "User"
        fieldname = "_ai_studio_test_field"

        # Clean up if exists
        existing = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
        if existing:
            frappe.delete_doc("Custom Field", existing, force=True)

        # Create
        result = safe_custom_field(doctype, {
            "fieldname": fieldname,
            "fieldtype": "Data",
            "label": "AI Studio Test Field",
            "insert_after": "full_name",
        })
        self.assertIn(result["status"], ("created", "updated"))

        # Update (idempotent)
        result2 = safe_custom_field(doctype, {
            "fieldname": fieldname,
            "fieldtype": "Data",
            "label": "AI Studio Test Field Updated",
        })
        self.assertEqual(result2["status"], "updated")

        # Verify
        doc = frappe.get_doc("Custom Field", result2["name"])
        self.assertEqual(doc.label, "AI Studio Test Field Updated")

        # Cleanup
        frappe.delete_doc("Custom Field", result2["name"], force=True)

    def test_safe_property_setter(self):
        """Set a property on a DocType."""
        result = safe_property_setter("User", "title_field", "full_name", "Data", for_doctype=True)
        self.assertEqual(result["status"], "set")

    def test_safe_server_script_ast_validation(self):
        """Server Script with forbidden code should be rejected."""
        with self.assertRaises(ValueError) as ctx:
            safe_server_script(
                "_ai_studio_test_script",
                "Before Insert",
                "import os\nos.system('ls')",
                reference_doctype="User",
            )
        self.assertIn("security", str(ctx.exception).lower())

    def test_safe_server_script_valid(self):
        """Server Script with valid code should be created."""
        name = "_ai_studio_test_valid_script"
        # Clean up
        if frappe.db.exists("Server Script", name):
            frappe.delete_doc("Server Script", name, force=True)

        result = safe_server_script(
            name,
            "Before Insert",
            "doc.custom_status = 'Test'",
            reference_doctype="User",
        )
        self.assertIn(result["status"], ("created", "updated"))

        # Cleanup
        frappe.delete_doc("Server Script", result["name"], force=True)

    def test_safe_client_script(self):
        """Create a Client Script."""
        name = "_ai_studio_test_client_script"
        if frappe.db.exists("Client Script", name):
            frappe.delete_doc("Client Script", name, force=True)

        result = safe_client_script(
            name,
            "frappe.ui.form.on('User', { refresh: function(frm) { console.log('test'); } });",
            doctype="User",
        )
        self.assertIn(result["status"], ("created", "updated"))

        # Cleanup
        frappe.delete_doc("Client Script", result["name"], force=True)


if __name__ == "__main__":
    unittest.main()
