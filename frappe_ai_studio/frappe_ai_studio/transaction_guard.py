# -*- coding: utf-8 -*-
"""Transaction Guard — PILLAR 4: Safe Schema Migration.

Provides dry-run transaction wrappers that:
- Execute changes inside a DB savepoint
- Roll back automatically on exit
- Never persist structural changes unless explicitly published
"""

from __future__ import unicode_literals

import contextlib
import json

import frappe

# ---------------------------------------------------------------------------
# Dry-run context manager
# ---------------------------------------------------------------------------


class DryRunContext:
    """Context manager that wraps database operations in a savepoint.

    Usage:
        with DryRunContext():
            apply_ai_changes(app_name, changes)   # all DB changes rolled back
    """

    def __init__(self, label="ai_studio_dry_run"):
        self.label = label
        self.rolled_back = False

    def __enter__(self):
        # Create a savepoint in the database
        frappe.db.sql("SAVEPOINT {}".format(self.label))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Always roll back to the savepoint, even on error.
        try:
            frappe.db.sql("ROLLBACK TO SAVEPOINT {}".format(self.label))
        finally:
            self.rolled_back = True
        # Do NOT suppress exceptions — a failure inside the block must surface
        # to the caller. Swallowing it previously made failed dry-runs look
        # like they passed.
        return False


# ---------------------------------------------------------------------------
# Migration guard — explicit publish required
# ---------------------------------------------------------------------------


class MigrationGuard:
    """Tracks pending migrations and requires explicit publish.

    This is a higher-level wrapper that stages changes in a "pending"
    state and only applies them when publish() is called.
    """

    def __init__(self, app_name):
        self.app_name = app_name
        self.pending_changes = []
        self.validated = False

    def stage(self, change):
        """Stage a change for later publishing."""
        self.pending_changes.append(change)
        self.validated = False

    def validate(self):
        """Run linting and dry-run on all pending changes."""
        from frappe_ai_studio.frappe_ai_studio.agent_orchestrator import _dry_run_changes, _lint_changes

        if not self.pending_changes:
            return True

        _lint_changes(self.pending_changes, self.app_name)
        _dry_run_changes(self.pending_changes, self.app_name)
        self.validated = True
        return True

    def publish(self):
        """Apply all pending changes for real.

        Must call validate() first.
        """
        if not self.validated:
            raise RuntimeError("Changes must be validated before publishing. Call validate() first.")

        from frappe_ai_studio.frappe_ai_studio.api import apply_ai_changes

        result = apply_ai_changes(self.app_name, json.dumps(self.pending_changes))
        self.pending_changes = []
        self.validated = False
        return result

    def discard(self):
        """Discard all pending changes without applying."""
        self.pending_changes = []
        self.validated = False


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def dry_run():
    """Convenience context manager for dry-run operations.

    Usage:
        with dry_run():
            doc.insert()
            # ... all rolled back on exit
    """
    ctx = DryRunContext()
    try:
        yield ctx
    finally:
        if not ctx.rolled_back:
            frappe.db.sql("ROLLBACK TO SAVEPOINT {}".format(ctx.label))
            ctx.rolled_back = True


def is_dry_run_available():
    """Check if the database supports savepoints (MariaDB 10.3+ / Postgres)."""
    try:
        frappe.db.sql("SAVEPOINT test_savepoint")
        frappe.db.sql("ROLLBACK TO SAVEPOINT test_savepoint")
        return True
    except Exception:
        return False
