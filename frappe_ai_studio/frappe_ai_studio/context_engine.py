# -*- coding: utf-8 -*-
"""Context Engine — scans the Frappe bench and builds a structured JSON context for the LLM."""

from __future__ import unicode_literals

import json
import os

import frappe


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 50000  # Skip files larger than 50KB
MAX_CONTEXT_SIZE = 500000  # Approximate max context chars
BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".ico",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".webm",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".map", ".lock",
}
SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".github", ".vscode", "dist", "build"}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_bench_path():
    """Return the absolute path to the bench root."""
    return frappe.utils.get_bench_path()


def get_apps_path():
    """Return the absolute path to the bench apps directory."""
    return os.path.join(get_bench_path(), "apps")


# ---------------------------------------------------------------------------
# App listing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# File reading helpers
# ---------------------------------------------------------------------------

def _is_binary_file(fname):
    """Check if a file is binary based on extension."""
    ext = os.path.splitext(fname)[1].lower()
    return ext in BINARY_EXTENSIONS


def _safe_read_file(file_path, max_size=MAX_FILE_SIZE):
    """Read a text file, skipping if too large or binary."""
    if not os.path.isfile(file_path):
        return None
    if _is_binary_file(file_path):
        return None
    try:
        size = os.path.getsize(file_path)
        if size > max_size:
            return "[File too large: {} bytes]".format(size)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return None


def _get_file_tree(app_path, max_depth=5):
    """Build a hierarchical file tree for an app."""
    tree = {"name": os.path.basename(app_path), "type": "folder", "children": []}

    for root, dirs, files in os.walk(app_path):
        # Skip unwanted directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

        rel_root = os.path.relpath(root, app_path)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        if depth >= max_depth:
            del dirs[:]
            continue

        # Find or create the node for this directory
        current = tree
        if rel_root != ".":
            parts = rel_root.split(os.sep)
            for part in parts:
                found = None
                for child in current.get("children", []):
                    if child["name"] == part and child["type"] == "folder":
                        found = child
                        break
                if found is None:
                    found = {"name": part, "type": "folder", "children": []}
                    current.setdefault("children", []).append(found)
                current = found

        for fname in sorted(files):
            if fname.startswith(".") or _is_binary_file(fname):
                continue
            current.setdefault("children", []).append({
                "name": fname,
                "type": "file",
            })

    return tree


def _list_files_by_pattern(app_path, pattern_func, max_files=50):
    """List files matching a pattern function."""
    matches = []
    for root, dirs, files in os.walk(app_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, app_path).replace("\\", "/")
            if pattern_func(fname, rel):
                content = _safe_read_file(fpath)
                if content is not None:
                    matches.append({"path": rel, "raw": content})
                if len(matches) >= max_files:
                    return matches
    return matches


# ---------------------------------------------------------------------------
# App metadata
# ---------------------------------------------------------------------------

def get_app_metadata(app_name):
    """Return comprehensive metadata for a single app."""
    try:
        app_path = frappe.get_app_path(app_name)
    except Exception:
        return {}

    # hooks.py
    hooks = {}
    hooks_path = os.path.join(app_path, "hooks.py")
    if os.path.isfile(hooks_path):
        content = _safe_read_file(hooks_path)
        if content:
            hooks["raw"] = content

    # modules.txt
    modules = []
    modules_txt = os.path.join(os.path.dirname(app_path), "modules.txt")
    if os.path.isfile(modules_txt):
        try:
            with open(modules_txt, "r", encoding="utf-8") as f:
                modules = [line.strip() for line in f if line.strip()]
        except Exception:
            pass

    # File tree
    file_tree = _get_file_tree(app_path)

    # DocType definitions
    doctypes = list_doctypes_for_app(app_name)

    # API files
    apis = list_api_files_for_app(app_name)

    # Python controllers (doctype .py files)
    controllers = _list_files_by_pattern(
        app_path,
        lambda fname, rel: fname.endswith(".py") and "/doctype/" in rel and not fname.startswith("__"),
        max_files=30
    )

    # JavaScript files
    js_files = _list_files_by_pattern(
        app_path,
        lambda fname, rel: fname.endswith(".js") and "/public/" in rel,
        max_files=30
    )

    # HTML templates
    templates = _list_files_by_pattern(
        app_path,
        lambda fname, rel: fname.endswith(".html") and "/templates/" in rel,
        max_files=20
    )

    # CSS files
    css_files = _list_files_by_pattern(
        app_path,
        lambda fname, rel: fname.endswith(".css") and "/public/" in rel,
        max_files=20
    )

    # Fixtures
    fixtures = []
    fixtures_path = os.path.join(app_path, "fixtures")
    if os.path.isdir(fixtures_path):
        for fname in os.listdir(fixtures_path):
            if fname.endswith(".json"):
                fpath = os.path.join(fixtures_path, fname)
                content = _safe_read_file(fpath)
                if content:
                    fixtures.append({"name": fname, "raw": content})

    # Reports
    reports = _list_files_by_pattern(
        app_path,
        lambda fname, rel: fname == "report" and os.path.isdir(os.path.join(app_path, rel)),
        max_files=10
    )
    # Actually list report JSONs
    report_files = _list_files_by_pattern(
        app_path,
        lambda fname, rel: fname.endswith(".json") and "/report/" in rel,
        max_files=20
    )

    # Pages
    page_files = _list_files_by_pattern(
        app_path,
        lambda fname, rel: fname.endswith(".json") and "/page/" in rel,
        max_files=20
    )

    # Workspaces
    workspace_files = _list_files_by_pattern(
        app_path,
        lambda fname, rel: fname.endswith(".json") and "/workspace/" in rel,
        max_files=20
    )

    # pyproject.toml / setup.py
    project_config = {}
    for cfg_name in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"):
        cfg_path = os.path.join(os.path.dirname(app_path), cfg_name)
        if os.path.isfile(cfg_path):
            content = _safe_read_file(cfg_path)
            if content:
                project_config[cfg_name] = content

    return {
        "app_name": app_name,
        "app_path": app_path,
        "is_core_app": app_name in ("frappe", "erpnext"),
        "hooks": hooks,
        "modules": modules,
        "file_tree": file_tree,
        "doctypes": doctypes,
        "apis": apis,
        "controllers": controllers,
        "js_files": js_files,
        "templates": templates,
        "css_files": css_files,
        "fixtures": fixtures,
        "reports": report_files,
        "pages": page_files,
        "workspaces": workspace_files,
        "project_config": project_config,
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
        dt_json = os.path.join(doctype_path, dt_dir, "{}.json".format(dt_dir))
        if os.path.isfile(dt_json):
            content = _safe_read_file(dt_json)
            if content:
                doctypes.append({"name": dt_dir, "json_path": dt_json, "raw": content})
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
                content = _safe_read_file(fpath)
                if content:
                    apis.append({"path": fpath, "raw": content})
    return apis


# ---------------------------------------------------------------------------
# Site & database context
# ---------------------------------------------------------------------------

def get_site_context():
    """Return site configuration summary."""
    return {
        "site_name": frappe.local.site,
        "developer_mode": bool(frappe.conf.get("developer_mode")),
        "installed_apps": frappe.get_installed_apps(),
        "db_type": frappe.conf.get("db_type", "mariadb"),
        "language": frappe.conf.get("language", "en"),
    }


def get_workspaces():
    """Return a list of available workspace names and titles."""
    try:
        workspaces = frappe.get_all("Workspace", fields=["name", "title", "module"], limit=50)
        return [{"name": w.name, "title": w.title, "module": w.module} for w in workspaces]
    except Exception:
        return []


def get_existing_doctypes():
    """Return a list of all existing DocType names in the system."""
    try:
        return frappe.db.sql_list("SELECT name FROM tabDocType ORDER BY name")
    except Exception:
        return []


def get_db_schema_summary():
    """Return a summary of key database tables and columns."""
    try:
        tables = frappe.db.sql("""
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME
        """, frappe.conf.db_name)

        schema = {}
        for (table_name,) in tables[:50]:  # Limit to 50 tables
            columns = frappe.db.sql("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """, (frappe.conf.db_name, table_name))
            schema[table_name] = [
                {
                    "column": c[0],
                    "type": c[1],
                    "nullable": c[2],
                    "default": c[3],
                }
                for c in columns
            ]
        return schema
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_context(target_app=None):
    """Build a full JSON context of the bench (or a single app)."""
    apps = list_installed_apps()
    context = {
        "bench_path": get_bench_path(),
        "site": get_site_context(),
        "existing_doctypes": get_existing_doctypes(),
        "workspaces": get_workspaces(),
        "apps": {},
    }

    for app in apps:
        if target_app and app != target_app:
            continue
        context["apps"][app] = get_app_metadata(app)

    # Add DB schema only if targeting a specific app (to save tokens)
    if target_app:
        context["db_schema"] = get_db_schema_summary()

    return context


def estimate_context_size(context):
    """Estimate the serialized size of the context."""
    return len(json.dumps(context, indent=2, default=str))


def index_all_apps():
    """Scheduled job: rebuild the context cache."""
    context = build_context()
    frappe.cache().set_value("ai_studio_bench_context", json.dumps(context))
    return context


def get_cached_context(target_app=None):
    """Return cached bench context or rebuild if missing."""
    cached = frappe.cache().get_value("ai_studio_bench_context")
    if cached:
        context = json.loads(cached)
        # If target_app specified, filter the cached context
        if target_app and "apps" in context:
            context["apps"] = {
                k: v for k, v in context["apps"].items()
                if k == target_app
            }
        return context
    return index_all_apps()
