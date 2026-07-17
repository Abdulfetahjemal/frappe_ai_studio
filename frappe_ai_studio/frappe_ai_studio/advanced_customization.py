# -*- coding: utf-8 -*-
"""Advanced customization — the senior-ERPNext-developer toolkit.

Idempotent, create-or-update helpers for the higher-level artefacts a senior
Frappe/ERPNext developer builds: Workflows, whole Workspaces, Reports,
Notifications, Dashboards/Charts/Number Cards, Roles, DocType permissions,
Print Formats and Web Forms.

Every helper:
  * is idempotent (create if missing, otherwise update),
  * validates any embedded Python via the AST sanitizer,
  * validates any embedded SQL to be read-only,
  * defers its commit while inside an atomic AI Studio batch.
"""

from __future__ import unicode_literals

import json
import re

import frappe

from frappe_ai_studio.frappe_ai_studio.ast_sanitizer import validate_code_security

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _maybe_commit():
    """Commit unless we are inside an atomic apply batch."""
    if not getattr(frappe.flags, "ai_studio_in_batch", False):
        frappe.db.commit()


# Statements that must never appear in a Query Report's SQL.
_SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|grant|revoke|"
    r"call|load_file|into\s+outfile|into\s+dumpfile)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(query):
    """Return (ok, message). Query Reports must be a single read-only SELECT."""
    if not query or not query.strip():
        return False, "Empty query"
    stripped = query.strip().rstrip(";")
    # Reject multiple statements.
    if ";" in stripped:
        return False, "Multiple SQL statements are not allowed"
    if _SQL_FORBIDDEN.search(stripped):
        return False, "Only read-only SELECT queries are allowed in Query Reports"
    lowered = stripped.lstrip("(").lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return False, "Query must start with SELECT (or WITH)"
    return True, "OK"


def _set_fields(doc, data, skip=("doctype", "name")):
    """Copy known fields from ``data`` onto ``doc``."""
    for key, value in data.items():
        if key in skip:
            continue
        if hasattr(doc, key):
            setattr(doc, key, value)


# ---------------------------------------------------------------------------
# Workflow management
# ---------------------------------------------------------------------------


def ensure_workflow_state(state_name, style="Primary"):
    """Create a Workflow State master if missing."""
    if not frappe.db.exists("Workflow State", state_name):
        doc = frappe.new_doc("Workflow State")
        doc.workflow_state_name = state_name
        doc.style = style or "Primary"
        doc.insert(ignore_permissions=True)
    return state_name


def ensure_workflow_action(action_name):
    """Create a Workflow Action Master if missing."""
    if not frappe.db.exists("Workflow Action Master", action_name):
        doc = frappe.new_doc("Workflow Action Master")
        doc.workflow_action_name = action_name
        doc.insert(ignore_permissions=True)
    return action_name


def safe_workflow(definition):
    """Create or update a Frappe Workflow, wiring up states and transitions.

    definition = {
        "name": "Library Loan Approval",
        "document_type": "Library Loan",
        "workflow_state_field": "workflow_state",
        "is_active": 1,
        "send_email_alert": 0,
        "states": [
            {"state": "Draft", "doc_status": "0", "allow_edit": "Library User",
             "style": "Warning"},
            {"state": "Approved", "doc_status": "1", "allow_edit": "Library Manager",
             "style": "Success"},
        ],
        "transitions": [
            {"state": "Draft", "action": "Approve", "next_state": "Approved",
             "allowed": "Library Manager"},
        ],
    }
    """
    name = definition.get("name")
    document_type = definition.get("document_type")
    states = definition.get("states") or []
    transitions = definition.get("transitions") or []

    if not name or not document_type or not states:
        raise ValueError("workflow requires 'name', 'document_type' and 'states'")
    if not frappe.db.exists("DocType", document_type):
        raise ValueError("DocType '{}' does not exist".format(document_type))

    # Pre-create referenced masters so Frappe validation passes.
    for s in states:
        ensure_workflow_state(s.get("state"), s.get("style", "Primary"))
    for t in transitions:
        ensure_workflow_action(t.get("action"))

    if frappe.db.exists("Workflow", name):
        doc = frappe.get_doc("Workflow", name)
    else:
        doc = frappe.new_doc("Workflow")
        doc.workflow_name = name

    doc.document_type = document_type
    doc.workflow_state_field = definition.get("workflow_state_field", "workflow_state")
    doc.is_active = definition.get("is_active", 1)
    doc.send_email_alert = definition.get("send_email_alert", 0)
    doc.override_status = definition.get("override_status", 0)

    doc.set("states", [])
    for s in states:
        doc.append(
            "states",
            {
                "state": s.get("state"),
                "doc_status": str(s.get("doc_status", "0")),
                "allow_edit": s.get("allow_edit", "System Manager"),
                "style": s.get("style"),
                "update_field": s.get("update_field"),
                "update_value": s.get("update_value"),
            },
        )

    doc.set("transitions", [])
    for t in transitions:
        doc.append(
            "transitions",
            {
                "state": t.get("state"),
                "action": t.get("action"),
                "next_state": t.get("next_state"),
                "allowed": t.get("allowed", "System Manager"),
                "condition": t.get("condition"),
            },
        )

    doc.save(ignore_permissions=True)
    _maybe_commit()
    return {"status": "saved", "workflow": name}


# ---------------------------------------------------------------------------
# Workspace (full creation, beyond link/shortcut tweaks)
# ---------------------------------------------------------------------------


def _default_workspace_content(shortcuts, links):
    """Build a minimal valid Workspace ``content`` layout."""
    blocks = []
    if shortcuts:
        blocks.append(
            {"id": "sc_header", "type": "header", "data": {"text": "<span>Shortcuts</span>", "col": 12}}
        )
        for sc in shortcuts:
            blocks.append(
                {
                    "id": "sc_" + frappe.scrub(sc.get("label", "x")),
                    "type": "shortcut",
                    "data": {"shortcut_name": sc.get("label"), "col": 3},
                }
            )
    if links:
        blocks.append(
            {
                "id": "ln_header",
                "type": "header",
                "data": {"text": "<span>Reports & Masters</span>", "col": 12},
            }
        )
        blocks.append({"id": "card_all", "type": "card", "data": {"card_name": "Documents", "col": 4}})
    return json.dumps(blocks)


def safe_workspace_create(definition):
    """Create or update a full Workspace with links, shortcuts, charts and cards.

    definition = {
        "title": "Library",
        "label": "Library",
        "icon": "book",
        "module": "Library Management",
        "public": 1,
        "links": [{"label": "Library Loan", "link_to": "Library Loan", "link_type": "DocType",
                   "type": "Link"}],
        "shortcuts": [{"label": "New Loan", "link_to": "Library Loan", "type": "DocType",
                       "color": "Blue"}],
        "charts": [{"chart_name": "Loans by Status", "label": "Loans by Status"}],
        "number_cards": [{"number_card_name": "Open Loans", "label": "Open Loans"}],
    }
    """
    title = definition.get("title") or definition.get("label")
    if not title:
        raise ValueError("workspace requires 'title'")

    if frappe.db.exists("Workspace", title):
        doc = frappe.get_doc("Workspace", title)
    else:
        doc = frappe.new_doc("Workspace")
        doc.title = title

    doc.label = definition.get("label", title)
    doc.module = definition.get("module")
    doc.icon = definition.get("icon", "list")
    doc.public = definition.get("public", 1)
    if definition.get("parent_page"):
        doc.parent_page = definition.get("parent_page")

    links = definition.get("links") or []
    shortcuts = definition.get("shortcuts") or []
    charts = definition.get("charts") or []
    number_cards = definition.get("number_cards") or []

    doc.set("links", [])
    for link in links:
        doc.append(
            "links",
            {
                "type": link.get("type", "Link"),
                "label": link.get("label"),
                "link_type": link.get("link_type", "DocType"),
                "link_to": link.get("link_to"),
                "onboard": link.get("onboard", 0),
            },
        )

    doc.set("shortcuts", [])
    for sc in shortcuts:
        doc.append(
            "shortcuts",
            {
                "label": sc.get("label"),
                "type": sc.get("type", "DocType"),
                "link_to": sc.get("link_to"),
                "color": sc.get("color"),
            },
        )

    if hasattr(doc, "charts"):
        doc.set("charts", [])
        for ch in charts:
            doc.append("charts", {"chart_name": ch.get("chart_name"), "label": ch.get("label")})

    if hasattr(doc, "number_cards"):
        doc.set("number_cards", [])
        for nc in number_cards:
            doc.append(
                "number_cards",
                {"number_card_name": nc.get("number_card_name"), "label": nc.get("label")},
            )

    doc.content = definition.get("content") or _default_workspace_content(shortcuts, links)

    doc.save(ignore_permissions=True)
    _maybe_commit()
    return {"status": "saved", "workspace": title}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def safe_report(definition):
    """Create or update a Query Report or Script Report.

    definition = {
        "name": "Overdue Loans",
        "ref_doctype": "Library Loan",
        "report_type": "Query Report",   # or "Script Report" / "Report Builder"
        "query": "SELECT name, member FROM `tabLibrary Loan` WHERE status='Overdue'",
        "report_script": "result = [...]",   # for Script Report
        "roles": ["Library Manager", "System Manager"],
        "is_standard": "No",
    }
    """
    name = definition.get("name")
    ref_doctype = definition.get("ref_doctype")
    report_type = definition.get("report_type", "Query Report")
    if not name or not ref_doctype:
        raise ValueError("report requires 'name' and 'ref_doctype'")

    if report_type == "Query Report":
        ok, msg = validate_readonly_sql(definition.get("query", ""))
        if not ok:
            raise ValueError("Query Report SQL rejected: {}".format(msg))
    if report_type == "Script Report":
        ok, msg = validate_code_security(definition.get("report_script", ""))
        if not ok:
            raise ValueError("Script Report code rejected: {}".format(msg))

    if frappe.db.exists("Report", name):
        doc = frappe.get_doc("Report", name)
    else:
        doc = frappe.new_doc("Report")
        doc.report_name = name

    doc.ref_doctype = ref_doctype
    doc.report_type = report_type
    doc.is_standard = definition.get("is_standard", "No")
    if report_type == "Query Report":
        doc.query = definition.get("query")
    if report_type == "Script Report":
        doc.report_script = definition.get("report_script")
    if definition.get("javascript"):
        doc.javascript = definition.get("javascript")

    roles = definition.get("roles") or []
    if roles:
        doc.set("roles", [])
        for role in roles:
            doc.append("roles", {"role": role})

    doc.save(ignore_permissions=True)
    _maybe_commit()
    return {"status": "saved", "report": name}


# ---------------------------------------------------------------------------
# Notifications (alerts)
# ---------------------------------------------------------------------------


def safe_notification(definition):
    """Create or update a Notification (email/system alert)."""
    name = definition.get("name")
    document_type = definition.get("document_type")
    if not name or not document_type:
        raise ValueError("notification requires 'name' and 'document_type'")

    if frappe.db.exists("Notification", name):
        doc = frappe.get_doc("Notification", name)
    else:
        doc = frappe.new_doc("Notification")
        doc.name = name

    doc.subject = definition.get("subject", name)
    doc.document_type = document_type
    doc.event = definition.get("event", "New")
    doc.channel = definition.get("channel", "Email")
    doc.enabled = definition.get("enabled", 1)
    doc.message = definition.get("message", "")
    if definition.get("condition"):
        doc.condition = definition.get("condition")
    if definition.get("days_in_advance") is not None:
        doc.days_in_advance = definition.get("days_in_advance")
    if definition.get("date_changed"):
        doc.date_changed = definition.get("date_changed")

    recipients = definition.get("recipients") or []
    if recipients:
        doc.set("recipients", [])
        for r in recipients:
            if isinstance(r, dict):
                doc.append("recipients", r)
            else:
                doc.append("recipients", {"receiver_by_document_field": r})

    doc.save(ignore_permissions=True)
    _maybe_commit()
    return {"status": "saved", "notification": name}


# ---------------------------------------------------------------------------
# Dashboards / Charts / Number Cards
# ---------------------------------------------------------------------------


def safe_dashboard_chart(definition):
    """Create or update a Dashboard Chart."""
    name = definition.get("name") or definition.get("chart_name")
    document_type = definition.get("document_type")
    if not name or not document_type:
        raise ValueError("dashboard_chart requires 'name' and 'document_type'")

    if frappe.db.exists("Dashboard Chart", name):
        doc = frappe.get_doc("Dashboard Chart", name)
    else:
        doc = frappe.new_doc("Dashboard Chart")
        doc.chart_name = name

    doc.chart_type = definition.get("chart_type", "Count")
    doc.document_type = document_type
    doc.type = definition.get("type", "Bar")
    doc.timeseries = definition.get("timeseries", 0)
    if definition.get("based_on"):
        doc.based_on = definition.get("based_on")
    if definition.get("group_by_based_on"):
        doc.group_by_based_on = definition.get("group_by_based_on")
    if definition.get("aggregate_function_based_on"):
        doc.aggregate_function_based_on = definition.get("aggregate_function_based_on")
    if definition.get("value_based_on"):
        doc.value_based_on = definition.get("value_based_on")
    if definition.get("filters_json"):
        doc.filters_json = definition.get("filters_json")
    doc.is_public = definition.get("is_public", 1)

    doc.save(ignore_permissions=True)
    _maybe_commit()
    return {"status": "saved", "dashboard_chart": name}


def safe_number_card(definition):
    """Create or update a Number Card."""
    name = definition.get("name") or definition.get("label")
    document_type = definition.get("document_type")
    if not name or not document_type:
        raise ValueError("number_card requires 'name' and 'document_type'")

    if frappe.db.exists("Number Card", name):
        doc = frappe.get_doc("Number Card", name)
    else:
        doc = frappe.new_doc("Number Card")
        doc.label = name

    doc.document_type = document_type
    doc.function = definition.get("function", "Count")
    if definition.get("aggregate_function_based_on"):
        doc.aggregate_function_based_on = definition.get("aggregate_function_based_on")
    if definition.get("filters_json"):
        doc.filters_json = definition.get("filters_json")
    doc.is_public = definition.get("is_public", 1)

    doc.save(ignore_permissions=True)
    _maybe_commit()
    return {"status": "saved", "number_card": name}


# ---------------------------------------------------------------------------
# Roles & permissions
# ---------------------------------------------------------------------------


def safe_role(definition):
    """Create or update a Role."""
    name = definition.get("name") or definition.get("role_name")
    if not name:
        raise ValueError("role requires 'name'")

    if frappe.db.exists("Role", name):
        doc = frappe.get_doc("Role", name)
    else:
        doc = frappe.new_doc("Role")
        doc.role_name = name

    doc.desk_access = definition.get("desk_access", 1)
    doc.disabled = definition.get("disabled", 0)
    if definition.get("home_page"):
        doc.home_page = definition.get("home_page")

    doc.save(ignore_permissions=True)
    _maybe_commit()
    return {"status": "saved", "role": name}


# Permission levels supported on a DocPerm row.
_PERM_RIGHTS = (
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "import",
    "share",
    "print",
    "email",
    "select",
)


def safe_permission(definition):
    """Add or update a DocType permission rule for a role.

    definition = {
        "doctype": "Library Loan",
        "role": "Library Manager",
        "permlevel": 0,
        "read": 1, "write": 1, "create": 1, "delete": 0, "submit": 1, ...
    }
    """
    doctype = definition.get("doctype")
    role = definition.get("role")
    if not doctype or not role:
        raise ValueError("permission requires 'doctype' and 'role'")
    if not frappe.db.exists("DocType", doctype):
        raise ValueError("DocType '{}' does not exist".format(doctype))
    if not frappe.db.exists("Role", role):
        safe_role({"name": role})

    permlevel = definition.get("permlevel", 0)

    # Use Frappe's helper so the change is tracked as a Custom DocPerm.
    from frappe.permissions import add_permission, update_permission_property

    add_permission(doctype, role, ptype="read", permlevel=permlevel)
    for right in _PERM_RIGHTS:
        if right in definition:
            update_permission_property(doctype, role, permlevel, right, 1 if definition.get(right) else 0)

    _maybe_commit()
    return {"status": "saved", "doctype": doctype, "role": role, "permlevel": permlevel}


# ---------------------------------------------------------------------------
# Print Formats & Web Forms
# ---------------------------------------------------------------------------


def safe_print_format(definition):
    """Create or update a Print Format."""
    name = definition.get("name")
    doctype = definition.get("doctype") or definition.get("document_type")
    if not name or not doctype:
        raise ValueError("print_format requires 'name' and 'doctype'")

    if frappe.db.exists("Print Format", name):
        doc = frappe.get_doc("Print Format", name)
    else:
        doc = frappe.new_doc("Print Format")
        doc.name = name

    doc.doc_type = doctype
    doc.print_format_type = definition.get("print_format_type", "Jinja")
    doc.standard = definition.get("standard", "No")
    if definition.get("html") is not None:
        doc.html = definition.get("html")
    doc.disabled = definition.get("disabled", 0)

    doc.save(ignore_permissions=True)
    _maybe_commit()
    return {"status": "saved", "print_format": name}


def safe_web_form(definition):
    """Create or update a Web Form."""
    route = definition.get("route") or definition.get("name")
    doctype = definition.get("doctype") or definition.get("doc_type")
    title = definition.get("title") or route
    if not route or not doctype:
        raise ValueError("web_form requires 'route'/'name' and 'doctype'")

    existing = frappe.db.get_value("Web Form", {"route": route}, "name")
    if existing:
        doc = frappe.get_doc("Web Form", existing)
    else:
        doc = frappe.new_doc("Web Form")
        doc.route = route

    doc.title = title
    doc.doc_type = doctype
    doc.published = definition.get("published", 1)
    doc.login_required = definition.get("login_required", 1)
    doc.allow_edit = definition.get("allow_edit", 1)
    doc.allow_multiple = definition.get("allow_multiple", 0)

    fields = definition.get("web_form_fields") or definition.get("fields") or []
    if fields:
        doc.set("web_form_fields", [])
        for f in fields:
            doc.append(
                "web_form_fields",
                {
                    "fieldname": f.get("fieldname"),
                    "fieldtype": f.get("fieldtype", "Data"),
                    "label": f.get("label"),
                    "reqd": f.get("reqd", 0),
                    "options": f.get("options"),
                },
            )

    doc.save(ignore_permissions=True)
    _maybe_commit()
    return {"status": "saved", "web_form": route}
