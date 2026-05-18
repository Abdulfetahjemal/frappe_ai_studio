# -*- coding: utf-8 -*-
"""Schema Wizard — auto-update tabDocType in MariaDB and generate .json simultaneously."""

from __future__ import unicode_literals

import json
import os

import frappe
from frappe import _
from frappe.core.doctype.doctype.doctype import DocType


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


def create_doctype(app_name, definition):
    """Create a new DocType from a definition dict and sync both JSON and DB."""
    if isinstance(definition, str):
        definition = json.loads(definition)

    doctype_name = definition.get("name")
    if not doctype_name:
        frappe.throw(_("Definition must include 'name'"))

    # 1. Write JSON
    app_path = frappe.get_app_path(app_name)
    dt_folder = os.path.join(app_path, "doctype", doctype_name)
    os.makedirs(dt_folder, exist_ok=True)

    json_path = os.path.join(dt_folder, f"{doctype_name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(definition, f, indent=1, ensure_ascii=False, default=str)

    init_path = os.path.join(dt_folder, "__init__.py")
    if not os.path.exists(init_path):
        open(init_path, "a").close()

    # 2. Sync to DB
    sync_doctype_from_json(app_name, f"doctype/{doctype_name}/{doctype_name}.json")

    return {"doctype": doctype_name, "json_path": json_path, "status": "created"}
