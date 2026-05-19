# -*- coding: utf-8 -*-
"""Tests for Agent Orchestrator (Pillar 1)."""

from __future__ import unicode_literals

import json
import unittest

import frappe

from frappe_ai_studio.frappe_ai_studio.agent_orchestrator import (
    enqueue_generation_task,
    get_generation_task_status,
    _extract_changes,
    _lint_changes,
    STAGE_PENDING,
    STAGE_COMPLETED,
    STAGE_FAILED,
)


class TestAgentOrchestrator(unittest.TestCase):
    def test_extract_changes_from_json_block(self):
        """Extract changes from a markdown JSON block."""
        response = """Here are the changes:
```json
{"changes": [{"type": "write", "relative_path": "test.py", "content": "x=1"}]}
```
"""
        changes = _extract_changes(response)
        self.assertIsInstance(changes, list)
        self.assertEqual(changes[0]["type"], "write")

    def test_extract_changes_from_plain_json(self):
        """Extract changes from plain JSON."""
        response = json.dumps({"changes": [{"type": "custom_field", "doctype": "User"}]})
        changes = _extract_changes(response)
        self.assertIsInstance(changes, list)
        self.assertEqual(changes[0]["type"], "custom_field")

    def test_lint_changes_valid(self):
        """Lint valid changes should not raise."""
        changes = [
            {"type": "write", "relative_path": "test.py", "content": "x = 1"},
            {"type": "custom_field", "doctype": "User", "field": {"fieldname": "test", "fieldtype": "Data"}},
        ]
        _lint_changes(changes, "frappe_ai_studio")  # should not raise

    def test_lint_changes_unknown_type(self):
        """Unknown change type should raise ValueError."""
        changes = [{"type": "hack_the_planet"}]
        with self.assertRaises(ValueError) as ctx:
            _lint_changes(changes, "frappe_ai_studio")
        self.assertIn("Unknown change type", str(ctx.exception))

    def test_lint_changes_security_violation(self):
        """Python code with forbidden imports should raise."""
        changes = [
            {"type": "write", "relative_path": "evil.py", "content": "import os\nos.system('rm -rf /')"},
        ]
        with self.assertRaises(ValueError) as ctx:
            _lint_changes(changes, "frappe_ai_studio")
        self.assertIn("Security violation", str(ctx.exception))

    def test_enqueue_and_get_status(self):
        """Enqueue a task and verify its initial status.
        
        This test requires a running Frappe site with the DocType installed.
        Skip if Frappe is not initialized.
        """
        try:
            import frappe
            frappe.local.site
        except (ImportError, AttributeError):
            self.skipTest("Frappe not initialized")

        task_name = enqueue_generation_task(
            user_prompt="Test prompt for unit testing",
            target_app="frappe_ai_studio",
        )
        self.assertTrue(task_name.startswith("AGT-"))

        status = get_generation_task_status(task_name)
        self.assertEqual(status["task_id"], task_name)
        self.assertIn(status["status"], (STAGE_PENDING, "In Progress", STAGE_COMPLETED, STAGE_FAILED))


if __name__ == "__main__":
    unittest.main()
