# -*- coding: utf-8 -*-
"""Customization Bridge — PILLAR 3: Dynamic Fractional Customization.

Provides safe, idempotent wrappers for:
- Custom Field creation / update
- Property Setter creation / update
- Server Script creation / update
- Client Script creation / update
- hooks.py injection (with AST validation + backup)
- Workspace link / shortcut management
"""

from __future__ import unicode_literals

import json
import os
import shutil

import frappe
from frappe import _

from frappe_ai_studio.frappe_ai_studio.ast_sanitizer import validate_code_security


# ---------------------------------------------------------------------------
# Custom Field
# ---------------------------------------------------------------------------


def safe_custom_field(doctype, field_definition):
    """Create or update a Custom Field in an idempotent way.

    If a Custom Field with the same fieldname already exists for the DocType,
    update it. Otherwise create a new one.
    """
    if not doctype or not field_definition:
        raise ValueError("safe_custom_field requires 'doctype' and 'field_definition'")

    fieldname = field_definition.get("fieldname")
    if not fieldname:
        raise ValueError("field_definition must include 'fieldname'")

    existing = frappe.db.get_value(
        "Custom Field", {"dt": doctype, "fieldname": fieldname}, "name"
    )

    if existing:
        doc = frappe.get_doc("Custom Field", existing)
        for key, value in field_definition.items():
            if hasattr(doc, key) and key not in ("name", "doctype"):
                setattr(doc, key, value)
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "updated", "name": doc.name}

    doc = frappe.new_doc("Custom Field")
    doc.dt = doctype
    for key, value in field_definition.items():
        if hasattr(doc, key):
            setattr(doc, key, value)

    try:
        doc.insert(ignore_permissions=True)
    except frappe.ValidationError as e:
        err_msg = str(e)
        if "already exists" in err_msg.lower() or "exists in" in err_msg.lower():
            frappe.msgprint(
                _("Field '{0}' already exists in {1}, skipping.").format(fieldname, doctype)
            )
            return {"status": "skipped", "reason": "already_exists"}
        raise

    frappe.db.commit()
    return {"status": "created", "name": doc.name}


# ---------------------------------------------------------------------------
# Property Setter
# ---------------------------------------------------------------------------


def safe_property_setter(doctype, property_name, value, property_type="Data", for_doctype=False):
    """Create or update a Property Setter in an idempotent way.

    Uses Frappe's built-in make_property_setter for standard fields.
    """
    if not doctype or not property_name:
        raise ValueError("safe_property_setter requires 'doctype' and 'property_name'")

    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    make_property_setter(
        doctype,
        for_doctype=for_doctype,
        property=property_name,
        value=value,
        property_type=property_type,
    )
    frappe.db.commit()
    return {"status": "set", "doctype": doctype, "property": property_name}


# ---------------------------------------------------------------------------
# Server Script
# ---------------------------------------------------------------------------


def safe_server_script(name, script_type, script, reference_doctype=None, enabled=1, event_frequency=None):
    """Create or update a Server Script with AST security validation.

    script_type must be one of: 'Before Insert', 'After Insert', 'Before Validate',
    'After Validate', 'Before Save', 'After Save', 'Before Submit', 'After Submit',
    'Before Cancel', 'After Cancel', 'Before Delete', 'After Delete',
    'Before Update After Submit', 'After Update After Submit',
    'Before Rename', 'After Rename',
    'API', 'Scheduler Event', 'Permission Query'
    """
    if not name or not script_type or not script:
        raise ValueError("safe_server_script requires 'name', 'script_type', and 'script'")

    # AST security check
    ok, msg = validate_code_security(script)
    if not ok:
        raise ValueError("Server Script security check failed: {}".format(msg))

    existing = frappe.db.get_value("Server Script", name, "name")

    if existing:
        doc = frappe.get_doc("Server Script", existing)
        doc.script_type = script_type
        doc.script = script
        doc.enabled = enabled
        if reference_doctype:
            doc.reference_doctype = reference_doctype
        if event_frequency:
            doc.event_frequency = event_frequency
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "updated", "name": doc.name}

    doc = frappe.new_doc("Server Script")
    doc.name = name
    doc.script_type = script_type
    doc.script = script
    doc.enabled = enabled
    if reference_doctype:
        doc.reference_doctype = reference_doctype
    if event_frequency:
        doc.event_frequency = event_frequency
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "created", "name": doc.name}


# ---------------------------------------------------------------------------
# Client Script
# ---------------------------------------------------------------------------


def safe_client_script(name, script, doctype=None, enabled=1, view=None):
    """Create or update a Client Script with AST security validation.

    view can be: 'Form', 'List', 'Tree', 'Workspaces', 'Dashboard', 'Calendar',
    'Inbox', 'Kanban', 'Image', 'Map', 'Gantt', 'Dashboard Chart'
    """
    if not name or not script:
        raise ValueError("safe_client_script requires 'name' and 'script'")

    # AST security check (JS is not Python, but we can still scan for obvious issues)
    # For now we just do a basic check — future: use ESLint or Babel AST
    ok, msg = validate_code_security(script)
    if not ok:
        # Client scripts are JS, not Python — AST check may give false positives.
        # We log a warning but don't block. Real JS linting should be added later.
        frappe.logger("ai_studio").warning(
            "Client Script AST check flagged (expected for JS): %s", msg
        )

    existing = frappe.db.get_value("Client Script", name, "name")

    if existing:
        doc = frappe.get_doc("Client Script", existing)
        doc.script = script
        doc.enabled = enabled
        if doctype:
            doc.dt = doctype
        if view:
            doc.view = view
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "updated", "name": doc.name}

    doc = frappe.new_doc("Client Script")
    doc.name = name
    doc.script = script
    doc.enabled = enabled
    if doctype:
        doc.dt = doctype
    if view:
        doc.view = view
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "created", "name": doc.name}


# ---------------------------------------------------------------------------
# hooks.py injection
# ---------------------------------------------------------------------------


def safe_hooks_injection(app_name, hook_name, hook_value, append=True):
    """Safely inject a value into an app's hooks.py.

    - Creates a backup before modifying
    - Validates that hook_value is safe (no exec/eval)
    - Appends or prepends to the existing list/dict value
    """
    if not app_name or not hook_name:
        raise ValueError("safe_hooks_injection requires 'app_name' and 'hook_name'")

    app_path = frappe.get_app_path(app_name)
    hooks_path = os.path.join(app_path, "hooks.py")

    if not os.path.exists(hooks_path):
        raise FileNotFoundError("hooks.py not found for app: {}".format(app_name))

    # Read current hooks.py
    with open(hooks_path, "r", encoding="utf-8") as f:
        original_content = f.read()

    # Backup
    backup_path = hooks_path + ".ai-studio-backup"
    shutil.copy2(hooks_path, backup_path)

    # Validate hook_value if it's a string containing code
    if isinstance(hook_value, str):
        ok, msg = validate_code_security(hook_value)
        if not ok:
            # Restore backup
            shutil.copy2(backup_path, hooks_path)
            raise ValueError("hooks.py injection security check failed: {}".format(msg))

    # Parse existing hook value
    try:
        import ast
        tree = ast.parse(original_content)
    except SyntaxError:
        # hooks.py might have complex syntax; fall back to regex
        tree = None

    new_content = _inject_hook_value(original_content, hook_name, hook_value, append)

    # Validate new content parses
    try:
        ast.parse(new_content)
    except SyntaxError as e:
        # Restore backup
        shutil.copy2(backup_path, hooks_path)
        raise ValueError("Modified hooks.py has syntax error: {}".format(str(e)))

    with open(hooks_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return {"status": "injected", "hook": hook_name, "backup": backup_path}


def _inject_hook_value(content, hook_name, hook_value, append):
    """Inject hook_value into the Python source content.

    Uses a simple regex-based approach for reliability.
    """
    import re

    # Try to find the existing assignment
    pattern = r"(^[ \t]*{}\s*=\s*)(.*?)(?=\n[\w#]|\Z)".format(re.escape(hook_name))
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)

    if match:
        prefix = match.group(1)
        existing = match.group(2).strip()

        if existing.startswith("[") and existing.endswith("]"):
            # List append
            inner = existing[1:-1].strip()
            if inner:
                if append:
                    new_val = "[{}, {}]".format(inner, hook_value)
                else:
                    new_val = "[{}, {}]".format(hook_value, inner)
            else:
                new_val = "[{}]".format(hook_value)
        elif existing.startswith("{") and existing.endswith("}"):
            # Dict append — hook_value should be a dict
            inner = existing[1:-1].strip()
            if isinstance(hook_value, dict):
                kv_pairs = ", ".join("{!r}: {!r}".format(k, v) for k, v in hook_value.items())
                if inner:
                    new_val = "{{{}, {}}}".format(inner, kv_pairs)
                else:
                    new_val = "{{{}}}".format(kv_pairs)
            else:
                # Treat as string key with value
                if inner:
                    new_val = "{{{}, {!r}: {!r}}}".format(inner, hook_value, hook_value)
                else:
                    new_val = "{{{!r}: {!r}}}".format(hook_value, hook_value)
        else:
            # Scalar — convert to list
            if append:
                new_val = "[{}, {}]".format(existing, hook_value)
            else:
                new_val = "[{}, {}]".format(hook_value, existing)

        return content[:match.start()] + prefix + new_val + content[match.end():]
    else:
        # Hook not found — append at end
        new_line = "\n{} = {}\n".format(hook_name, hook_value)
        return content + new_line


def restore_hooks_backup(app_name):
    """Restore hooks.py from its AI Studio backup."""
    app_path = frappe.get_app_path(app_name)
    hooks_path = os.path.join(app_path, "hooks.py")
    backup_path = hooks_path + ".ai-studio-backup"

    if not os.path.exists(backup_path):
        return {"status": "no_backup"}

    shutil.copy2(backup_path, hooks_path)
    return {"status": "restored", "from": backup_path}


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------


def safe_workspace_link(workspace_name, link_definition, append=True):
    """Add or update a link in a Workspace."""
    if not workspace_name or not link_definition:
        raise ValueError("safe_workspace_link requires 'workspace_name' and 'link_definition'")

    workspace = frappe.get_doc("Workspace", workspace_name)
    if not workspace:
        raise ValueError("Workspace '{}' not found".format(workspace_name))

    link_to = link_definition.get("link_to")
    label = link_definition.get("label")

    # Check if link already exists
    existing_idx = None
    for idx, row in enumerate(workspace.links):
        if link_to and row.link_to == link_to:
            existing_idx = idx
            break
        if label and row.label == label:
            existing_idx = idx
            break

    if existing_idx is not None:
        row = workspace.links[existing_idx]
        for key, value in link_definition.items():
            if hasattr(row, key):
                setattr(row, key, value)
    else:
        if append:
            workspace.append("links", link_definition)
        else:
            workspace.insert("links", 0, link_definition)

    workspace.save(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "updated", "workspace": workspace_name}


def safe_workspace_link_remove(workspace_name, link_to=None, label=None):
    """Remove a link from a Workspace by link_to or label."""
    if not workspace_name:
        raise ValueError("safe_workspace_link_remove requires 'workspace_name'")
    if not link_to and not label:
        raise ValueError("Either 'link_to' or 'label' is required")

    workspace = frappe.get_doc("Workspace", workspace_name)
    if not workspace:
        raise ValueError("Workspace '{}' not found".format(workspace_name))

    to_remove = []
    for idx, row in enumerate(workspace.links):
        if link_to and row.link_to == link_to:
            to_remove.append(idx)
        elif label and row.label == label:
            to_remove.append(idx)

    for idx in reversed(to_remove):
        workspace.links.pop(idx)

    if to_remove:
        workspace.save(ignore_permissions=True)
        frappe.db.commit()

    return {"status": "removed", "count": len(to_remove), "workspace": workspace_name}


def safe_workspace_shortcut(workspace_name, shortcut_definition, append=True):
    """Add or update a shortcut in a Workspace."""
    if not workspace_name or not shortcut_definition:
        raise ValueError("safe_workspace_shortcut requires 'workspace_name' and 'shortcut_definition'")

    workspace = frappe.get_doc("Workspace", workspace_name)
    if not workspace:
        raise ValueError("Workspace '{}' not found".format(workspace_name))

    link_to = shortcut_definition.get("link_to")
    label = shortcut_definition.get("label")

    existing_idx = None
    for idx, row in enumerate(workspace.shortcuts):
        if link_to and row.link_to == link_to:
            existing_idx = idx
            break
        if label and row.label == label:
            existing_idx = idx
            break

    if existing_idx is not None:
        row = workspace.shortcuts[existing_idx]
        for key, value in shortcut_definition.items():
            if hasattr(row, key):
                setattr(row, key, value)
    else:
        if append:
            workspace.append("shortcuts", shortcut_definition)
        else:
            workspace.insert("shortcuts", 0, shortcut_definition)

    workspace.save(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "updated", "workspace": workspace_name}


def safe_workspace_shortcut_remove(workspace_name, link_to=None, label=None):
    """Remove a shortcut from a Workspace by link_to or label."""
    if not workspace_name:
        raise ValueError("safe_workspace_shortcut_remove requires 'workspace_name'")
    if not link_to and not label:
        raise ValueError("Either 'link_to' or 'label' is required")

    workspace = frappe.get_doc("Workspace", workspace_name)
    if not workspace:
        raise ValueError("Workspace '{}' not found".format(workspace_name))

    to_remove = []
    for idx, row in enumerate(workspace.shortcuts):
        if link_to and row.link_to == link_to:
            to_remove.append(idx)
        elif label and row.label == label:
            to_remove.append(idx)

    for idx in reversed(to_remove):
        workspace.shortcuts.pop(idx)

    if to_remove:
        workspace.save(ignore_permissions=True)
        frappe.db.commit()

    return {"status": "removed", "count": len(to_remove), "workspace": workspace_name}
