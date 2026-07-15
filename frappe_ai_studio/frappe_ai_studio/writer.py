# -*- coding: utf-8 -*-
"""Writer — secure file-system bridge and AST-based code updates via libcst."""

from __future__ import unicode_literals

import ast
import io
import json
import os
import subprocess

import frappe

# Optional libcst import with graceful fallback
try:
    import libcst as cst

    HAS_LIBCST = True
except Exception:
    cst = None
    HAS_LIBCST = False


class PathTraversalError(Exception):
    """Raised when a resolved path escapes its app directory."""


def resolve_app_path(app_name, *rel_path):
    """Return an absolute path inside an app, guaranteed to stay within it.

    Any attempt to escape the app directory (e.g. via ``..`` segments or an
    absolute path) raises :class:`PathTraversalError`. This is a security
    boundary: user/LLM-supplied ``relative_path`` values must never be able to
    read or write files outside the target app.
    """
    base = os.path.realpath(frappe.get_app_path(app_name))
    # Reject absolute-path components outright before joining.
    for part in rel_path:
        if part and os.path.isabs(part):
            raise PathTraversalError("Absolute paths are not allowed: {}".format(part))
    target = os.path.realpath(os.path.join(base, *rel_path))
    if target != base and not target.startswith(base + os.sep):
        raise PathTraversalError("Path '{}' escapes app directory '{}'".format(target, base))
    return target


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


def _app_repo_and_pathspec(app_name):
    """Return (repo_path, pathspec) for the app's source subtree.

    ``pathspec`` scopes git operations to the app's own files so we never
    touch unrelated changes elsewhere in the repository.
    """
    app_path = os.path.realpath(frappe.get_app_path(app_name))
    repo_path = os.path.dirname(app_path)
    pathspec = os.path.relpath(app_path, repo_path)
    return repo_path, pathspec


def git_snapshot(app_name):
    """Commit the target app's current state before applying changes.

    Only the app's own subtree is staged and committed, so unrelated
    uncommitted work elsewhere in the repo is left untouched.
    """
    repo_path, pathspec = _app_repo_and_pathspec(app_name)
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        return True, "No git repository found — skipping snapshot"

    try:
        # Only look at changes within the app subtree.
        status_result = subprocess.run(
            ["git", "-C", repo_path, "status", "--porcelain", "--", pathspec],
            check=True,
            capture_output=True,
            text=True,
        )
        if not status_result.stdout.strip():
            return True, "Working tree clean — no snapshot needed"

        subprocess.run(
            ["git", "-C", repo_path, "add", "--", pathspec],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                repo_path,
                "commit",
                "-m",
                "ai-studio: pre-change snapshot",
                "--no-verify",
                "--",
                pathspec,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, "Snapshot committed"
    except subprocess.CalledProcessError as e:
        return False, e.stderr or "Git commit failed"


def git_rollback(app_name):
    """Restore the target app's subtree to the last snapshot/commit.

    Uses a scoped checkout + clean rather than a repo-wide ``reset --hard`` so
    that uncommitted work outside the app subtree is never discarded.
    """
    repo_path, pathspec = _app_repo_and_pathspec(app_name)
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        return False, "No git repository found"

    try:
        # Restore tracked files within the app subtree to HEAD.
        subprocess.run(
            ["git", "-C", repo_path, "checkout", "HEAD", "--", pathspec],
            check=True,
            capture_output=True,
            text=True,
        )
        # Remove any newly-created (untracked) files within the app subtree.
        subprocess.run(
            ["git", "-C", repo_path, "clean", "-fd", "--", pathspec],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, "Rolled back app changes"
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
                return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))
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
