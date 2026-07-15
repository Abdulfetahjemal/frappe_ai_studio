# -*- coding: utf-8 -*-
"""AST-based code sanitizer — PILLAR 2: Secure Python Execution.

Validates Python code by parsing it into an AST and enforcing:
- Import whitelisting (stdlib + Frappe + ERPNext)
- Function call whitelisting
- No exec/eval/compile/__import__
- No dunder attribute access (e.g., __class__.__bases__)
"""

from __future__ import unicode_literals

import ast
import textwrap

# ---------------------------------------------------------------------------
# Whitelists
# ---------------------------------------------------------------------------

ALLOWED_IMPORTS = {
    # Python stdlib
    "json",
    "os",
    "re",
    "sys",
    "math",
    "random",
    "datetime",
    "time",
    "collections",
    "itertools",
    "functools",
    "typing",
    "hashlib",
    "base64",
    "uuid",
    "inspect",
    "textwrap",
    "string",
    "decimal",
    "statistics",
    "csv",
    "io",
    "pathlib",
    "enum",
    "dataclasses",
    "contextlib",
    "copy",
    "pprint",
    "html",
    "urllib",
    "urllib.parse",
    "urllib.request",
    "urllib.error",
    # Frappe / ERPNext
    "frappe",
    "frappe.utils",
    "frappe.model",
    "frappe.model.document",
    "frappe.model.meta",
    "frappe.model.db_schema",
    "frappe.model.naming",
    "frappe.model.mapper",
    "frappe.model.utils",
    "frappe.core",
    "frappe.core.doctype",
    "erpnext",
    "erpnext.accounts",
    "erpnext.selling",
    "erpnext.buying",
    "erpnext.stock",
    "erpnext.manufacturing",
    "erpnext.projects",
    "erpnext.crm",
    "erpnext.support",
    "erpnext.hr",
    "erpnext.payroll",
    "erpnext.assets",
    "erpnext.utilities",
    "erpnext.setup",
    "erpnext.healthcare",
    "erpnext.education",
    "erpnext.agriculture",
    "erpnext.hospitality",
    "erpnext.non_profit",
    "erpnext.quality_management",
    "erpnext.telephony",
    "erpnext.integrations",
    "erpnext.regional",
    # Google GenAI
    "google",
    "google.genai",
    "google.genai.types",
}

# Allow any function from these modules
ALLOWED_FUNCTION_PREFIXES = {
    "json.",
    "os.path.",
    "re.",
    "math.",
    "random.",
    "datetime.",
    "time.",
    "collections.",
    "itertools.",
    "functools.",
    "typing.",
    "hashlib.",
    "base64.",
    "uuid.",
    "inspect.",
    "textwrap.",
    "string.",
    "decimal.",
    "statistics.",
    "csv.",
    "io.",
    "pathlib.",
    "enum.",
    "dataclasses.",
    "contextlib.",
    "copy.",
    "pprint.",
    "html.",
    "urllib.",
    "frappe.",
    "erpnext.",
    "google.",
    "_",
}

# Forbidden builtins / dangerous calls
FORBIDDEN_CALLS = {
    "exec",
    "eval",
    "compile",
    "__import__",
    "open",
    "input",
    "raw_input",
    "breakpoint",
    "exit",
    "quit",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
    "dir",
    "execfile",
    "reload",
    "memoryview",
}

# Dangerous names that must never be referenced even when not directly called
# (blocks aliasing such as ``f = eval`` and introspection escapes).
FORBIDDEN_NAMES = {
    "__builtins__",
    "__import__",
    "__loader__",
    "__spec__",
    "builtins",
    "subprocess",
    "os_system",
}

# ---------------------------------------------------------------------------
# Visitor
# ---------------------------------------------------------------------------


class SecurityVisitor(ast.NodeVisitor):
    """AST visitor that checks for security violations."""

    def __init__(self):
        self.violations = []

    def visit_Import(self, node):
        for alias in node.names:
            if not self._is_allowed_import(alias.name):
                self.violations.append("Forbidden import: '{}' at line {}".format(alias.name, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            # from X import Y  →  X.Y
            name = "{}.{}".format(module, alias.name) if module else alias.name
            if not self._is_allowed_import(name) and not self._is_allowed_import(module):
                self.violations.append("Forbidden import: '{}' at line {}".format(name, node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node):
        func_name = self._get_call_name(node.func)
        if func_name:
            base = func_name.split("(")[0].split("[")[0]
            if base in FORBIDDEN_CALLS:
                self.violations.append("Forbidden call: '{}' at line {}".format(base, node.lineno))
            elif not self._is_allowed_function(base):
                self.violations.append("Forbidden function call: '{}' at line {}".format(base, node.lineno))
        self.generic_visit(node)

    def visit_Attribute(self, node):
        # Block dunder attribute access chains like obj.__class__.__bases__
        if isinstance(node.attr, str) and node.attr.startswith("__") and node.attr.endswith("__"):
            self.violations.append("Forbidden dunder access: '.{}' at line {}".format(node.attr, node.lineno))
        self.generic_visit(node)

    def visit_Name(self, node):
        # Close the aliasing bypass: `f = eval; f("...")` would otherwise slip
        # past visit_Call because the dangerous builtin is never *called*
        # directly. Flag any reference to a forbidden builtin, in any context.
        if node.id in FORBIDDEN_CALLS or node.id in FORBIDDEN_NAMES:
            self.violations.append("Forbidden reference to '{}' at line {}".format(node.id, node.lineno))
        self.generic_visit(node)

    def _is_allowed_import(self, name):
        """Check if an import name is in the whitelist (exact or prefix match)."""
        if name in ALLOWED_IMPORTS:
            return True
        # Allow submodules of whitelisted packages
        for allowed in ALLOWED_IMPORTS:
            if name.startswith(allowed + "."):
                return True
        return False

    def _is_allowed_function(self, name):
        """Check if a function call is allowed."""
        for prefix in ALLOWED_FUNCTION_PREFIXES:
            if name.startswith(prefix):
                return True
        # Allow bare names that are not forbidden
        if "." not in name and name not in FORBIDDEN_CALLS:
            return True
        return False

    def _get_call_name(self, node):
        """Extract the dotted name of a call expression."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        elif isinstance(node, ast.Subscript):
            return self._get_call_name(node.value)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_code_security(code):
    """Validate Python code for security violations.

    Returns (ok: bool, message: str)
    """
    if not code or not code.strip():
        return True, "Empty code — nothing to validate"

    # Dedent so indented class methods don't break parsing
    code = textwrap.dedent(code)

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, "Syntax error at line {}: {}".format(e.lineno, e.msg)

    visitor = SecurityVisitor()
    visitor.visit(tree)

    if visitor.violations:
        return False, "; ".join(visitor.violations)

    return True, "Code passes security checks"


def is_code_safe(code):
    """Convenience wrapper returning True/False only."""
    ok, _ = validate_code_security(code)
    return ok
