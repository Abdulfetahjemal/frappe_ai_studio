# -*- coding: utf-8 -*-
"""Schema Wizard — auto-update tabDocType in MariaDB and generate .json simultaneously."""

from __future__ import unicode_literals

import json
import os

import frappe
from frappe import _


def sync_doctype_from_json(app_name, relative_json_path):
    """Sync a DocType definition from its JSON file to the database."""
    from frappe_ai_studio.frappe_ai_studio.writer import resolve_app_path, safe_read

    file_path = resolve_app_path(app_name, *relative_json_path.strip("/").split("/"))
    raw = safe_read(file_path)
    if raw is None:
        frappe.throw(_("DocType JSON not found: {0}").format(file_path))

    data = json.loads(raw)
    doctype_name = data.get("name")
    if not doctype_name:
        frappe.throw(_("Invalid DocType JSON: missing 'name'"))

    # Ensure the DocType exists in DB
    if not frappe.db.exists("DocType", doctype_name):
        doc = frappe.get_doc({"doctype": "DocType", **data})
        doc.insert(ignore_permissions=True)
    else:
        doc = frappe.get_doc("DocType", doctype_name)
        doc.update(data)
        doc.save(ignore_permissions=True)

    frappe.db.commit()
    return {"doctype": doctype_name, "status": "synced"}


def export_doctype_to_json(doctype_name, app_name):
    """Export a DocType from the database to the app's doctype folder."""
    doc = frappe.get_doc("DocType", doctype_name)
    export_data = doc.as_dict()

    # Strip server-generated fields
    for key in list(export_data.keys()):
        if key.startswith("_"):
            export_data.pop(key)

    app_path = frappe.get_app_path(app_name)
    dt_folder = os.path.join(app_path, "doctype", doctype_name)
    os.makedirs(dt_folder, exist_ok=True)

    json_path = os.path.join(dt_folder, f"{doctype_name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=1, ensure_ascii=False, default=str)

    # Ensure __init__.py exists
    init_path = os.path.join(dt_folder, "__init__.py")
    if not os.path.exists(init_path):
        open(init_path, "a").close()

    return {"path": json_path, "status": "exported"}


def _get_unique_naming_series(prefix, doctype_name):
    """Generate a unique naming series that doesn't conflict with existing ones."""
    # Check existing naming series
    existing = frappe.db.sql_list(
        "SELECT DISTINCT naming_series FROM tabDocType WHERE naming_series IS NOT NULL AND naming_series != ''"
    )
    existing_prefixes = set()
    for series in existing:
        if series:
            # Extract prefix before . or #
            import re

            match = re.match(r"^([A-Za-z0-9_-]+)", series)
            if match:
                existing_prefixes.add(match.group(1))

    # Try the suggested prefix first
    if prefix and prefix not in existing_prefixes:
        return prefix

    # Generate a unique prefix based on doctype name
    base = doctype_name.upper().replace(" ", "-").replace("_", "-")[:10]
    candidate = base + "-"
    if candidate not in existing_prefixes:
        return candidate

    # Add numeric suffix if needed
    for i in range(1, 100):
        candidate = f"{base}-{i}-"
        if candidate not in existing_prefixes:
            return candidate

    return f"{base}-AUTO-"


def create_doctype(app_name, definition):
    """Create a new DocType from a definition dict and sync both JSON and DB."""
    if isinstance(definition, str):
        definition = json.loads(definition)

    doctype_name = definition.get("name")
    if not doctype_name:
        frappe.throw(_("Definition must include 'name'"))

    # Auto-fix naming series to avoid conflicts
    fields = definition.get("fields", [])
    naming_series_field = None
    for field in fields:
        if field.get("fieldname") == "naming_series":
            naming_series_field = field
            break

    if naming_series_field:
        current_options = naming_series_field.get("options", "")
        if current_options:
            # Extract prefix from first series option
            import re

            first_series = current_options.split("\n")[0].strip()
            match = re.match(r"^([A-Za-z0-9_-]+)", first_series)
            if match:
                suggested_prefix = match.group(1) + "-"
                unique_prefix = _get_unique_naming_series(suggested_prefix, doctype_name)
                if unique_prefix != suggested_prefix:
                    # Replace the prefix in all series options
                    new_options = []
                    for opt in current_options.split("\n"):
                        opt = opt.strip()
                        if opt:
                            new_opt = re.sub(r"^([A-Za-z0-9_-]+)", unique_prefix.rstrip("-"), opt)
                            new_options.append(new_opt)
                        else:
                            new_options.append(opt)
                    naming_series_field["options"] = "\n".join(new_options)
                    frappe.msgprint(
                        _("Naming series auto-adjusted from '{0}' to '{1}' to avoid conflicts.").format(
                            suggested_prefix, unique_prefix
                        )
                    )

    # 1. Determine the correct module path
    module_name = definition.get("module", app_name)
    app_path = frappe.get_app_path(app_name)

    # Frappe stores doctypes under app/module/doctype/name/
    # If module is the same as app_name, use app/doctype/name/
    if module_name and module_name != app_name:
        module_path = os.path.join(app_path, frappe.scrub(module_name))
        if os.path.exists(module_path):
            dt_folder = os.path.join(module_path, "doctype", frappe.scrub(doctype_name))
        else:
            dt_folder = os.path.join(app_path, "doctype", frappe.scrub(doctype_name))
    else:
        dt_folder = os.path.join(app_path, "doctype", frappe.scrub(doctype_name))

    os.makedirs(dt_folder, exist_ok=True)

    json_path = os.path.join(dt_folder, f"{frappe.scrub(doctype_name)}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(definition, f, indent=1, ensure_ascii=False, default=str)

    init_path = os.path.join(dt_folder, "__init__.py")
    if not os.path.exists(init_path):
        open(init_path, "a").close()

    # 2. Sync to DB
    rel_path = os.path.relpath(json_path, app_path)
    sync_doctype_from_json(app_name, rel_path)

    return {"doctype": doctype_name, "json_path": json_path, "status": "created"}
