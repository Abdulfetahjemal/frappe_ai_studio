# -*- coding: utf-8 -*-
"""Controller for AI Generation Task DocType."""

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class AIGenerationTask(Document):
    def before_insert(self):
        """Set initial state before creation."""
        if not self.status:
            self.status = "Pending"
        if not self.progress_percent:
            self.progress_percent = 0

    def on_update(self):
        """Publish realtime events on status changes."""
        self._publish_progress()

    def _publish_progress(self):
        """Stream progress to connected clients via Socketio."""
        try:
            frappe.publish_realtime(
                "ai_generation_progress",
                {
                    "task_id": self.name,
                    "status": self.status,
                    "progress_percent": self.progress_percent,
                    "current_stage": self.current_stage,
                    "error_trace": self.error_trace,
                    "completed_at": str(self.completed_at) if self.completed_at else None,
                },
                user=self.owner,
            )
        except Exception:
            # Socketio may not be available in all environments
            pass

    def set_stage(self, stage, percent):
        """Update stage and progress atomically."""
        self.current_stage = stage
        self.progress_percent = percent
        self.status = (
            stage
            if stage in ("Pending", "In Progress", "Linting", "Testing", "Completed", "Failed", "Rolled Back")
            else self.status
        )
        self.save(ignore_permissions=True)
        frappe.db.commit()

    def set_success(self, ai_response, changes_payload):
        """Mark task as completed successfully."""
        self.status = "Completed"
        self.progress_percent = 100
        self.current_stage = "Completed"
        self.ai_response = ai_response
        self.changes_payload = changes_payload
        self.completed_at = frappe.utils.now()
        if self.started_at:
            self.duration_seconds = (
                frappe.utils.get_datetime(self.completed_at) - frappe.utils.get_datetime(self.started_at)
            ).total_seconds()
        self.save(ignore_permissions=True)
        frappe.db.commit()

    def set_failed(self, error_trace):
        """Mark task as failed."""
        self.status = "Failed"
        self.progress_percent = 0
        self.current_stage = "Failed"
        self.error_trace = error_trace
        self.completed_at = frappe.utils.now()
        if self.started_at:
            self.duration_seconds = (
                frappe.utils.get_datetime(self.completed_at) - frappe.utils.get_datetime(self.started_at)
            ).total_seconds()
        self.save(ignore_permissions=True)
        frappe.db.commit()

    def set_rolled_back(self):
        """Mark task as rolled back."""
        self.status = "Rolled Back"
        self.current_stage = "Rolled Back"
        self.completed_at = frappe.utils.now()
        self.save(ignore_permissions=True)
        frappe.db.commit()
