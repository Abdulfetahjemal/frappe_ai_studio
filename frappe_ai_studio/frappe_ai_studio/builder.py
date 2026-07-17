# -*- coding: utf-8 -*-
"""Builder — bench-level orchestration (app scaffolding & installation).

This is the "senior developer" surface: creating whole new Frappe apps,
installing them onto the site, and creating modules — the things a human
developer would do at the bench/CLI before any DocType exists.
"""

from __future__ import unicode_literals

import os
import re
import subprocess

import frappe
from frappe import _

# A valid Frappe app / module_name must be a python-identifier-ish slug.
APP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,49}$")

# Reserved names we must never let the agent scaffold over.
RESERVED_APP_NAMES = {"frappe", "erpnext", "bench", "test", "assets", "sites", "apps"}


def validate_app_name(app_name):
    """Return (ok, message). Enforces a safe snake_case app name."""
    if not app_name:
        return False, "App name is required"
    if not APP_NAME_RE.match(app_name):
        return False, (
            "Invalid app name '{}'. Use lowercase letters, digits and "
            "underscores, starting with a letter (2-50 chars).".format(app_name)
        )
    if app_name in RESERVED_APP_NAMES:
        return False, "'{}' is a reserved name".format(app_name)
    return True, "OK"


def _bench_path():
    return frappe.utils.get_bench_path()


def app_exists(app_name):
    """True if the app already exists in the bench apps directory."""
    return os.path.isdir(os.path.join(_bench_path(), "apps", app_name))


def scaffold_app(
    app_name,
    app_title=None,
    app_description=None,
    app_publisher=None,
    app_email=None,
    app_license="mit",
    install=False,
    site=None,
):
    """Create a new Frappe app via ``bench new-app`` (non-interactive).

    Optionally installs it onto the current site. Returns a status dict.
    Raises frappe.ValidationError on invalid input or command failure.
    """
    ok, msg = validate_app_name(app_name)
    if not ok:
        frappe.throw(_(msg))

    bench_path = _bench_path()

    if app_exists(app_name):
        result = {"app": app_name, "status": "exists"}
    else:
        title = app_title or app_name.replace("_", " ").title()
        description = app_description or "{} app".format(title)
        publisher = app_publisher or "AI Studio"
        email = app_email or (frappe.session.user if frappe.session else "ai@example.com")

        cmd = [
            "bench",
            "new-app",
            app_name,
            "--title",
            title,
            "--description",
            description,
            "--publisher",
            publisher,
            "--email",
            email,
            "--license",
            app_license,
            "--no-git",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=bench_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            )
        except subprocess.CalledProcessError as e:
            # Older bench may not support all flags — surface the real error.
            frappe.throw(_("bench new-app failed: {0}").format(e.stderr or e.stdout))
        except subprocess.TimeoutExpired:
            frappe.throw(_("bench new-app timed out"))

        # Initialise git so snapshot/rollback safety works for future changes.
        _git_init(os.path.join(bench_path, "apps", app_name))
        result = {"app": app_name, "status": "created", "output": (proc.stdout or "")[-2000:]}

    if install:
        install_result = install_app(app_name, site=site)
        result["install"] = install_result

    return result


def _git_init(repo_path):
    """Best-effort git init + initial commit for a freshly scaffolded app."""
    try:
        if os.path.isdir(os.path.join(repo_path, ".git")):
            return
        subprocess.run(["git", "-C", repo_path, "init"], capture_output=True, text=True, check=True)
        subprocess.run(["git", "-C", repo_path, "add", "-A"], capture_output=True, text=True, check=True)
        subprocess.run(
            ["git", "-C", repo_path, "commit", "-m", "ai-studio: initial scaffold", "--no-verify"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        # git may be unavailable or already configured differently; non-fatal.
        pass


def install_app(app_name, site=None):
    """Install an existing app onto the current (or given) site."""
    ok, msg = validate_app_name(app_name)
    if not ok:
        frappe.throw(_(msg))
    if not app_exists(app_name):
        frappe.throw(_("App '{0}' does not exist in the bench").format(app_name))

    site = site or frappe.local.site
    try:
        proc = subprocess.run(
            ["bench", "--site", site, "install-app", app_name],
            cwd=_bench_path(),
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )
        return {"status": "installed", "output": (proc.stdout or "")[-2000:]}
    except subprocess.CalledProcessError as e:
        out = (e.stderr or "") + (e.stdout or "")
        if "already installed" in out.lower():
            return {"status": "already_installed"}
        frappe.throw(_("install-app failed: {0}").format(out))
    except subprocess.TimeoutExpired:
        frappe.throw(_("install-app timed out"))


def create_module(app_name, module_name):
    """Create a Module Def and its on-disk folder inside an app."""
    if not app_name or not module_name:
        frappe.throw(_("create_module requires 'app_name' and 'module_name'"))

    if not frappe.db.exists("Module Def", module_name):
        doc = frappe.new_doc("Module Def")
        doc.module_name = module_name
        doc.app_name = app_name
        doc.custom = 0
        doc.insert(ignore_permissions=True)

    # Ensure the on-disk module folder exists with an __init__.py.
    app_path = frappe.get_app_path(app_name)
    module_path = os.path.join(app_path, frappe.scrub(module_name))
    os.makedirs(module_path, exist_ok=True)
    init_file = os.path.join(module_path, "__init__.py")
    if not os.path.exists(init_file):
        open(init_file, "a").close()

    return {"status": "created", "module": module_name, "app": app_name}
