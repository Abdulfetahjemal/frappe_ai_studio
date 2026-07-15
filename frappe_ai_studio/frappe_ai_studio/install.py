# -*- coding: utf-8 -*-
"""Install / migrate hooks for Frappe AI Studio.

Ensures the dedicated ``AI Studio Manager`` role exists so administrators can
grant access to the (powerful) AI Studio endpoints without handing out full
System Manager rights.
"""

from __future__ import unicode_literals

import frappe

AI_STUDIO_ROLE = "AI Studio Manager"


def _ensure_role():
    """Create the AI Studio Manager role if it does not already exist."""
    if not frappe.db.exists("Role", AI_STUDIO_ROLE):
        role = frappe.new_doc("Role")
        role.role_name = AI_STUDIO_ROLE
        role.desk_access = 1
        role.insert(ignore_permissions=True)
        frappe.db.commit()


def after_install():
    _ensure_role()


def after_migrate():
    # Idempotent — safe to run on every migrate.
    _ensure_role()
