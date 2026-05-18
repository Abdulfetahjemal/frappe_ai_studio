# -*- coding: utf-8 -*-
"""Context Engine — scans the Frappe bench and builds a structured JSON context for the LLM."""

from __future__ import unicode_literals

import json
import os

import frappe


def get_bench_path():
    """Return the absolute path to the bench root."""
    return frappe.utils.get_bench_path()


def get_apps_path():
    """Return the absolute path to the bench apps directory."""
    return os.path.join(get_bench_path(), "apps")


def list_installed_apps():
    """Return a list of app names found in the bench apps directory."""
    apps_dir = get_apps_path()
    if not os.path.isdir(apps_dir):
        return []
    return [
        d
        for d in os.listdir(apps_dir)
        if os.path.isdir(os.path.join(apps_dir, d)) and not d.startswith(".")
    ]


def get_app_metadata(app_name):
    """Return metadata for a single app (hooks, modules, doctypes)."""
    try:
        app_path = frappe.get_app_path(app_name)
    except Exception:
        return {}

    hooks_path = os.path.join(app_path, "hooks.py")
    hooks = {}
    if os.path.isfile(hooks_path):
        try:
            # Safe read — we only need string snippets, not execution
            with open(hooks_path, "r", encoding="utf-8") as f:
                hooks["raw"] = f.read()
        except Exception:
            pass

    modules = []
    modules_txt = os.path.join(os.path.dirname(app_path), "modules.txt")
    if os.path.isfile(modules_txt):
        try:
            with open(modules_txt, "r", encoding="utf-8") as f:
                modules = [line.strip() for line in f if line.strip()]
        except Exception:
            pass

    doctypes = list_doctypes_for_app(app_name)
    apis = list_api_files_for_app(app_name)

    return {
        "app_name": app_name,
        "app_path": app_path,
        "hooks": hooks,
        "modules": modules,
        "doctypes": doctypes,
        "apis": apis,
    }


def list_doctypes_for_app(app_name):
    """List all DocType JSON definitions for an app."""
    doctypes = []
    try:
        doctype_path = frappe.get_app_path(app_name, "doctype")
    except Exception:
        return doctypes

    if not os.path.isdir(doctype_path):
        return doctypes

    for dt_dir in os.listdir(doctype_path):
        dt_json = os.path.join(doctype_path, dt_dir, f"{dt_dir}.json")
        if os.path.isfile(dt_json):
            try:
                with open(dt_json, "r", encoding="utf-8") as f:
                    doctypes.append({"name": dt_dir, "json_path": dt_json, "raw": f.read()})
            except Exception:
                pass
    return doctypes


def list_api_files_for_app(app_name):
    """List api.py files inside an app."""
    apis = []
    try:
        app_path = frappe.get_app_path(app_name)
    except Exception:
        return apis

    for root, _dirs, files in os.walk(app_path):
        for fname in files:
            if fname == "api.py":
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        apis.append({"path": fpath, "raw": f.read()})
                except Exception:
                    pass
    return apis


def build_context(target_app=None):
    """Build a full JSON context of the bench (or a single app)."""
    apps = list_installed_apps()
    context = {"bench_path": get_bench_path(), "apps": {}}

    for app in apps:
        if target_app and app != target_app:
            continue
        context["apps"][app] = get_app_metadata(app)

    return context


def index_all_apps():
    """Scheduled job: rebuild the context cache."""
    context = build_context()
    frappe.cache().set_value("ai_studio_bench_context", json.dumps(context))
    return context


def get_cached_context():
    """Return cached bench context or rebuild if missing."""
    cached = frappe.cache().get_value("ai_studio_bench_context")
    if cached:
        return json.loads(cached)
    return index_all_apps()
