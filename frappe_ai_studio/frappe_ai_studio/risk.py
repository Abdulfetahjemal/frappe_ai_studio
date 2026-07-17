# -*- coding: utf-8 -*-
"""Risk classification for AI-generated changes.

Assigns each change a risk level so the pipeline can require explicit user
approval before executing high-impact operations (app scaffolding, bench
commands, permission/role changes, workflow lifecycle, schema DDL, core-app
edits, etc.). Pure logic — no Frappe dependency — so it is unit-testable and
usable on both the server and (mirrored) client.
"""

from __future__ import unicode_literals

LOW = "low"
MEDIUM = "medium"
HIGH = "high"

_ORDER = {LOW: 0, MEDIUM: 1, HIGH: 2}

# Baseline risk by change type.
_BASE_RISK = {
    # Bench / system-level — always high.
    "create_app": HIGH,
    "install_app": HIGH,
    "create_module": HIGH,
    "run_bench": HIGH,
    # Security — always high (grants access / capabilities).
    "role": HIGH,
    "permission": HIGH,
    # Document lifecycle / approvals — high.
    "workflow": HIGH,
    # Schema DDL — medium (structural, but reversible-ish).
    "create_doctype": MEDIUM,
    "sync_doctype": MEDIUM,
    # Server-side code — medium (executes in the ERP).
    "write": MEDIUM,
    "inject_method": MEDIUM,
    "server_script": MEDIUM,
    # Destructive removals — medium.
    "workspace_link_remove": MEDIUM,
    "workspace_shortcut_remove": MEDIUM,
    # Supporting artefacts.
    "workflow_state": LOW,
    "workflow_action": LOW,
    "update_json": MEDIUM,
    "custom_field": LOW,
    "property_setter": LOW,
    "client_script": MEDIUM,
    "create_workspace": LOW,
    "workspace_link": LOW,
    "workspace_shortcut": LOW,
    "report": MEDIUM,
    "notification": LOW,
    "dashboard_chart": LOW,
    "number_card": LOW,
    "print_format": LOW,
    "web_form": MEDIUM,
}

CORE_APPS = ("frappe", "erpnext")


def _bump(level, floor):
    """Return the higher of two risk levels."""
    return level if _ORDER[level] >= _ORDER[floor] else floor


def classify_change_risk(change, app_name=None):
    """Return the risk level ('low'|'medium'|'high') for a single change."""
    ctype = (change or {}).get("type")
    level = _BASE_RISK.get(ctype, MEDIUM)

    # Editing hooks.py rewires the whole app — treat as high.
    rel = (change.get("relative_path") or "") if isinstance(change, dict) else ""
    if ctype in ("write", "inject_method", "update_json") and rel.endswith("hooks.py"):
        level = _bump(level, HIGH)

    # Any change targeting a core app is high-impact.
    target = change.get("app_name") if isinstance(change, dict) else None
    if (app_name in CORE_APPS) or (target in CORE_APPS):
        level = _bump(level, HIGH)

    # Activating a workflow enforces approvals on real documents.
    if ctype == "workflow":
        level = HIGH

    return level


def describe_change(change):
    """Short human label for a change, used in approval summaries."""
    if not isinstance(change, dict):
        return str(change)
    ctype = change.get("type", "change")
    d = change.get("definition") or change
    label = (
        d.get("name")
        or d.get("app_name")
        or d.get("module_name")
        or d.get("relative_path")
        or d.get("title")
        or d.get("label")
        or d.get("role")
        or d.get("command")
        or d.get("document_type")
        or ""
    )
    return "{}{}".format(ctype, ": {}".format(label) if label else "")


def summarize_risk(changes, app_name=None):
    """Summarize risk across a change list.

    Returns:
        {
          "level": "high"|"medium"|"low",       # overall (max)
          "requires_approval": bool,            # any high-risk present
          "counts": {"low": n, "medium": n, "high": n},
          "high_risk": [ {"index", "type", "label", "level"} ... ],
          "items": [ {"index", "type", "label", "level"} ... ],
        }
    """
    changes = changes or []
    counts = {LOW: 0, MEDIUM: 0, HIGH: 0}
    items = []
    for idx, change in enumerate(changes):
        level = classify_change_risk(change, app_name=app_name)
        counts[level] += 1
        items.append(
            {
                "index": idx,
                "type": (change or {}).get("type"),
                "label": describe_change(change),
                "level": level,
            }
        )

    overall = LOW
    for level in (HIGH, MEDIUM, LOW):
        if counts[level]:
            overall = level
            break

    high_risk = [it for it in items if it["level"] == HIGH]
    return {
        "level": overall,
        "requires_approval": bool(high_risk),
        "counts": counts,
        "high_risk": high_risk,
        "items": items,
    }
