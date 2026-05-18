# -*- coding: utf-8 -*-
"""Writer — secure file-system bridge and AST-based code updates via libcst."""

from __future__ import unicode_literals

import ast
import io
import json
import os
import subprocess

import frappe
from frappe import _

# Optional libcst import with graceful fallback
try:
    import libcst as cst
    HAS_LIBCST = True
except Exception:
    cst = None
    HAS_LIBCST = False


def resolve_app_path(app_name, *rel_path):
    """Return an absolute path inside an app using Frappe's helper."""
    base = frappe.get_app_path(app_name)
    return os.path.join(base, *rel_path)


def safe_read(file_path, mode="r"):
    """Read a file and return its contents."""
    if not os.path.isfile(file_path):
        return None
    with io.open(file_path, mode, encoding="utf-8") as f:
        return f.read()


def safe_write(file_path, content, mode="w"):
    """Atomically write content to a file."""
    dir_name = os.path.dirname(file_path)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name)
    tmp_path = file_path + ".tmp"
    with io.open(tmp_path, mode, encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, file_path)
    return file_path


def validate_python_syntax(code):
    """Run ast.parse and pyflakes if available. Returns (ok, message)."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"

    try:
        import pyflakes.api
        import pyflakes.checker
        from pyflakes import messages

        tree = ast.parse(code)
        w = pyflakes.checker.Checker(tree, "<ai-generated>")
        errs = [m for m in w.messages if isinstance(m, messages.Message)]
        if errs:
            return False, "; ".join(str(m) for m in errs)
    except Exception:
        pass

    return True, "OK"


def git_snapshot(app_name):
    """Create a git commit in the target app repo before changes."""
    app_path = frappe.get_app_path(app_name)
    repo_path = os.path.dirname(app_path)
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        return True, "No git repository found — skipping snapshot"

    try:
        # Check if there are any changes to commit
        status_result = subprocess.run(
            ["git", "-C", repo_path, "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
        if not status_result.stdout.strip():
            # Working tree clean — nothing to snapshot
            return True, "Working tree clean — no snapshot needed"

        subprocess.run(
            ["git", "-C", repo_path, "add", "-A"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", repo_path, "commit", "-m", "ai-studio: pre-change snapshot", "--no-verify"],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, "Snapshot committed"
    except subprocess.CalledProcessError as e:
        return False, e.stderr or "Git commit failed"


def git_rollback(app_name):
    """Rollback the target app repo to the last commit."""
    app_path = frappe.get_app_path(app_name)
    repo_path = os.path.dirname(app_path)
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        return False, "No git repository found"

    try:
        subprocess.run(
            ["git", "-C", repo_path, "reset", "--hard", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, "Rolled back to HEAD"
    except subprocess.CalledProcessError as e:
        return False, e.stderr or "Git rollback failed"


# ---------------------------------------------------------------------------
# libcst helpers
# ---------------------------------------------------------------------------

def _get_method_injector():
    """Return the MethodInjector class lazily to avoid import-time errors."""
    if not HAS_LIBCST:
        raise RuntimeError("libcst is not installed")

    class _MethodInjector(cst.CSTTransformer):
        """Inject a method into a class by name."""

        def __init__(self, class_name, method_node):
            self.class_name = class_name
            self.method_node = method_node
            self.done = False

        def leave_ClassDef(self, original_node, updated_node):
            if original_node.name.value == self.class_name and not self.done:
                self.done = True
                new_body = list(updated_node.body.body) + [self.method_node]
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=new_body)
                )
            return updated_node

    return _MethodInjector


def inject_method_to_class(file_path, class_name, method_code):
    """Surgically inject a method into a class using libcst."""
    if not HAS_LIBCST:
        raise RuntimeError("libcst is not installed")

    source = safe_read(file_path)
    if source is None:
        raise FileNotFoundError(file_path)

    module = cst.parse_module(source)
    method_node = cst.parse_statement(method_code)
    if not isinstance(method_node, cst.FunctionDef):
        raise ValueError("method_code must be a function definition")

    injector_cls = _get_method_injector()
    transformer = injector_cls(class_name, method_node)
    new_module = module.visit(transformer)

    if not transformer.done:
        raise ValueError(f"Class '{class_name}' not found in {file_path}")

    new_code = new_module.code
    ok, msg = validate_python_syntax(new_code)
    if not ok:
        raise SyntaxError(msg)

    safe_write(file_path, new_code)
    return file_path


def update_json_file(file_path, updates):
    """Merge updates into a JSON file atomically."""
    data = {}
    if os.path.isfile(file_path):
        with io.open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    if not isinstance(updates, dict):
        raise TypeError("updates must be a dict")

    _deep_merge(data, updates)
    safe_write(file_path, json.dumps(data, indent=1, ensure_ascii=False))
    return file_path


def _deep_merge(base, updates):
    """Recursively merge updates into base."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
