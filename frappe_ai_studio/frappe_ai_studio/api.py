# -*- coding: utf-8 -*-
"""API — whitelisted Frappe methods for the AI Studio agent."""

from __future__ import unicode_literals

import json
import os
import subprocess

import frappe
from frappe import _

from frappe_ai_studio.frappe_ai_studio.ast_sanitizer import validate_code_security
from frappe_ai_studio.frappe_ai_studio.context_engine import (
    build_context,
    get_cached_context,
)
from frappe_ai_studio.frappe_ai_studio.writer import (
    git_rollback,
    git_snapshot,
    inject_method_to_class,
    resolve_app_path,
    safe_read,
    safe_write,
    update_json_file,
    validate_python_syntax,
)

# ---------------------------------------------------------------------------
# Provider / model registry
# ---------------------------------------------------------------------------

PROVIDER_ENDPOINTS = {
    "OpenAI": "https://api.openai.com/v1/chat/completions",
    "Anthropic": "https://api.anthropic.com/v1/messages",
    "Google Gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "Moonshot AI (Kimi)": "https://api.moonshot.cn/v1/chat/completions",
    "DeepSeek": "https://api.deepseek.com/chat/completions",
    "Groq": "https://api.groq.com/openai/v1/chat/completions",
    "Azure OpenAI": None,  # Set via custom api_base_url
    "Cohere": "https://api.cohere.ai/v1/chat",
    "Mistral AI": "https://api.mistral.ai/v1/chat/completions",
    "Together AI": "https://api.together.xyz/v1/chat/completions",
    "Perplexity": "https://api.perplexity.ai/chat/completions",
    "OpenRouter": "https://openrouter.ai/api/v1/chat/completions",
}

PROVIDER_API_KEY_ENV = {
    "OpenAI": "OPENAI_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
    "Google Gemini": "GEMINI_API_KEY",
    "Moonshot AI (Kimi)": "KIMI_API_KEY",
    "DeepSeek": "DEEPSEEK_API_KEY",
    "Groq": "GROQ_API_KEY",
    "Azure OpenAI": "AZURE_OPENAI_API_KEY",
    "Cohere": "COHERE_API_KEY",
    "Mistral AI": "MISTRAL_API_KEY",
    "Together AI": "TOGETHER_API_KEY",
    "Perplexity": "PERPLEXITY_API_KEY",
    "OpenRouter": "OPENROUTER_API_KEY",
}

# Model-to-provider mapping
MODEL_PROVIDER_MAP = {
    # OpenAI
    "gpt-4o": "OpenAI",
    "gpt-4o-mini": "OpenAI",
    "gpt-4-turbo": "OpenAI",
    "gpt-4-turbo-preview": "OpenAI",
    "gpt-4": "OpenAI",
    "gpt-3.5-turbo": "OpenAI",
    "o1-preview": "OpenAI",
    "o1-mini": "OpenAI",
    "o3-mini": "OpenAI",
    # Anthropic
    "claude-3-5-sonnet-20241022": "Anthropic",
    "claude-3-5-sonnet-latest": "Anthropic",
    "claude-3-opus-20240229": "Anthropic",
    "claude-3-sonnet-20240229": "Anthropic",
    "claude-3-haiku-20240307": "Anthropic",
    "claude-3-7-sonnet-20250219": "Anthropic",
    # Google Gemini
    "gemini-2.5-pro": "Google Gemini",
    "gemini-2.5-flash": "Google Gemini",
    "gemini-2.0-flash": "Google Gemini",
    "gemini-1.5-pro": "Google Gemini",
    "gemini-1.5-pro-latest": "Google Gemini",
    "gemini-1.5-flash": "Google Gemini",
    "gemini-1.5-flash-latest": "Google Gemini",
    "gemini-1.0-pro": "Google Gemini",
    # Moonshot AI (Kimi)
    "kimi-moonshot-v1-8k": "Moonshot AI (Kimi)",
    "kimi-moonshot-v1-32k": "Moonshot AI (Kimi)",
    "kimi-moonshot-v1-128k": "Moonshot AI (Kimi)",
    "kimi-k1.5": "Moonshot AI (Kimi)",
    # DeepSeek
    "deepseek-chat": "DeepSeek",
    "deepseek-chat-v2": "DeepSeek",
    "deepseek-coder": "DeepSeek",
    "deepseek-coder-v2": "DeepSeek",
    "deepseek-reasoner": "DeepSeek",
    # Groq
    "groq-llama-3.3-70b-versatile": "Groq",
    "groq-llama-3.1-70b-versatile": "Groq",
    "groq-llama-3.1-8b-instant": "Groq",
    "groq-mixtral-8x7b-32768": "Groq",
    "groq-gemma-2-9b-it": "Groq",
    # Azure OpenAI
    "azure-gpt-4o": "Azure OpenAI",
    "azure-gpt-4-turbo": "Azure OpenAI",
    # Cohere
    "cohere-command-r": "Cohere",
    "cohere-command-r-plus": "Cohere",
    "cohere-aya-23": "Cohere",
    # Mistral AI
    "mistral-large-latest": "Mistral AI",
    "mistral-medium-latest": "Mistral AI",
    "mistral-small-latest": "Mistral AI",
    "mistral-codestral-latest": "Mistral AI",
    # Together AI
    "together-llama-3.3-70b": "Together AI",
    "together-qwen2.5-72b": "Together AI",
    "together-mixtral-8x22b": "Together AI",
    # Perplexity
    "perplexity-sonar": "Perplexity",
    "perplexity-sonar-pro": "Perplexity",
    "perplexity-sonar-reasoning": "Perplexity",
    # OpenRouter
    "openrouter-anthropic-claude-3.5-sonnet": "OpenRouter",
    "openrouter-meta-llama-3.3-70b": "OpenRouter",
    "openrouter-google-gemini-1.5-pro": "OpenRouter",
}


def _get_active_settings():
    """Return the AI Studio Settings single doc (or None)."""
    if frappe.db.exists("AI Studio Settings", "AI Studio Settings"):
        return frappe.get_doc("AI Studio Settings", "AI Studio Settings")
    return None


def _get_llm_config(provider=None, model=None, temperature=None):
    """Read LLM settings from AI Studio Settings or site config."""
    settings = _get_active_settings()

    cfg = {
        "provider": provider or frappe.conf.get("ai_studio_llm_provider", "OpenAI"),
        "api_key": frappe.conf.get("ai_studio_api_key"),
        "model": model or frappe.conf.get("ai_studio_model", "gpt-4o"),
        "temperature": temperature
        if temperature is not None
        else frappe.conf.get("ai_studio_temperature", 0.2),
        "api_base_url": None,
    }

    if settings:
        cfg["provider"] = provider or settings.default_provider or cfg["provider"]
        cfg["model"] = model or settings.default_model or cfg["model"]
        cfg["temperature"] = (
            temperature if temperature is not None else (settings.temperature or cfg["temperature"])
        )
        cfg["api_key"] = settings.get_password("api_key") or cfg["api_key"]

    return cfg


def _resolve_provider_from_model(model):
    """Guess provider from model id."""
    return MODEL_PROVIDER_MAP.get(model, "OpenAI")


# ---------------------------------------------------------------------------
# Access control, auditing & limits
# ---------------------------------------------------------------------------

# AI Studio can write code, run bench commands and mutate schema. Every
# endpoint below is therefore restricted to trusted roles. "AI Studio Manager"
# is shipped as a fixture so access can be granted without full System Manager.
AI_STUDIO_ROLES = ["System Manager", "AI Studio Manager"]

# Guard against runaway prompts / payloads.
MAX_PROMPT_CHARS = 100000
MAX_CHANGES_PER_REQUEST = 100


def _guard(roles=None):
    """Enforce that the current user holds an AI Studio role.

    Defensive against unit-test frappe mocks that omit ``only_for``.
    """
    only_for = getattr(frappe, "only_for", None)
    if callable(only_for):
        only_for(roles or AI_STUDIO_ROLES)


def _audit(action, **details):
    """Record a structured audit entry for a mutating action."""
    session = getattr(frappe, "session", None)
    user = getattr(session, "user", None) if session else None
    try:
        frappe.logger("ai_studio").info(
            "audit user=%s action=%s details=%s",
            user,
            action,
            json.dumps(details, default=str)[:2000],
        )
    except Exception:
        pass


def _parse_changes(changes):
    """Normalise a ``changes`` argument into a validated list of dicts."""
    if isinstance(changes, str):
        changes = json.loads(changes)
    if not isinstance(changes, list):
        frappe.throw(_("Changes must be a list"))
    if len(changes) > MAX_CHANGES_PER_REQUEST:
        frappe.throw(_("Too many changes in one request (max {0})").format(MAX_CHANGES_PER_REQUEST))
    return changes


def _in_batch():
    flags = getattr(frappe, "flags", None)
    return bool(getattr(flags, "ai_studio_in_batch", False)) if flags else False


def _maybe_commit():
    """Commit unless we are inside an atomic batch (committed once at the end)."""
    if not _in_batch():
        frappe.db.commit()


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """You are an expert Frappe/ERPNext developer and system architect. You have deep knowledge of:
- Frappe Framework v15 architecture (DocTypes, controllers, hooks, whitelisted APIs, server/client scripts)
- ERPNext v15 modules (Accounting, Stock, CRM, HR, Manufacturing, etc.)
- Python, JavaScript, MariaDB, Jinja2 templating
- Frappe app structure, bench commands, and deployment

Your goal is to help users build, customize, and maintain Frappe/ERPNext applications.

## PROJECT CONTEXT
You will receive a JSON context containing:
- The bench path and installed apps
- For each app: hooks.py, modules, DocType definitions, API files, controllers, JS files, templates, CSS, fixtures, reports, pages
- Site configuration (developer_mode, installed apps)
- Database schema summary

## OUTPUT FORMAT
For general questions or when NO code changes are needed, respond in plain natural language.

When the user asks you to create or modify code, respond with a JSON payload wrapped in ```json blocks:

```json
{
  "app_name": "target_app_name",
  "changes": [
    {
      "type": "write",
      "relative_path": "path/relative/to/app/root.py",
      "content": "full file content",
      "action": "overwrite"
    },
    {
      "type": "inject_method",
      "relative_path": "path/to/file.py",
      "class_name": "ClassName",
      "method_code": "def new_method(self):\\n    pass"
    },
    {
      "type": "update_json",
      "relative_path": "doctype/MyDoc/MyDoc.json",
      "updates": {"fieldname": "new_value"}
    },
    {
      "type": "create_doctype",
      "definition": {"name": "NewDoc", "module": "My Module", "fields": [...]}
    },
    {
      "type": "sync_doctype",
      "relative_path": "doctype/MyDoc/MyDoc.json"
    },
    {
      "type": "run_bench",
      "command": "migrate"
    }
  ],
  "explanation": "Human-readable explanation of what was changed and why"
}
```

## CHANGE TYPES
- **write**: Write or overwrite a file. Use action "overwrite" or "append".
- **inject_method**: Inject a method into an existing Python class (requires libcst).
- **update_json**: Deep-merge updates into a JSON file (great for DocType modifications).
- **create_doctype**: Create a new DocType from a JSON definition (writes JSON + syncs to DB).
- **sync_doctype**: Sync an existing DocType JSON to the database.
- **run_bench**: Run a bench command (migrate, restart, clear-cache, build).
- **workspace_link**: Add a DocType link to a Workspace so users can find it in the sidebar.
  ```json
  {"type": "workspace_link", "workspace": "CRM", "label": "SMS Sent To Customers", "link_type": "DocType", "link_to": "SMS Sent To Customers"}
  ```

## BEST PRACTICES
1. Always use frappe.get_doc(), frappe.db.sql(), frappe.throw() following Frappe conventions
2. Whitelist API methods with @frappe.whitelist()
3. Use proper DocType naming (PascalCase for DocType names, snake_case for fieldnames)
4. Include proper permissions in DocType definitions
5. For JS files, use frappe.provide() and follow Frappe's JS patterns
6. For hooks, use the correct event names (doc_events, scheduler_events, etc.)
7. When modifying existing files, prefer update_json or inject_method over full overwrite
8. Always explain your changes in the "explanation" field
9. If you need to see a specific file not in context, ask the user to use the "Read File" feature

## CRITICAL: NAMING SERIES CONFLICTS
When creating DocTypes that use naming_series, ALWAYS check the existing_docTypes list in the context.
- NEVER use a naming series prefix that conflicts with existing DocTypes (e.g., "TASK-" is used by ERPNext's "Task" DocType)
- Use UNIQUE naming series like "AST-" for "AI Studio Task", "ASTK-" for "AI Studio Task", or "AI-STUDIO-TASK-"
- When in doubt, use the DocType name as prefix: "AI-STUDIO-TASK-.####"
- The context includes a list of existing_docTypes - check it before creating new ones

## CRITICAL: WORKSPACE CUSTOMIZATION
You have FULL control over Workspaces. You can add, update, and REMOVE links, shortcuts, and cards.
- Use `workspace_link` to ADD or UPDATE a link in a workspace
- Use `workspace_link_remove` to REMOVE a link from a workspace
- Use `workspace_shortcut` to ADD or UPDATE a shortcut in a workspace
- Use `workspace_shortcut_remove` to REMOVE a shortcut from a workspace
- The workspace name is the workspace's title (e.g., "CRM", "Selling", "Stock", "Others")

## CRITICAL: CORE APP CUSTOMIZATION
The context includes an "app_metadata" section that tells you if an app is a "core" app.
- **Core apps** (frappe, erpnext) should NOT be modified directly via file writes (no `write`, `inject_method`, `update_json`).
- For core apps, use these customization change types: `custom_field`, `property_setter`, `server_script`, `client_script`, `workspace_link`, `workspace_link_remove`, `workspace_shortcut`, `workspace_shortcut_remove`
- These customizations are stored in the database and survive updates.

## CRITICAL: CREATING DOCTYPES IN CORE APPS
When creating a new DocType that belongs in a core app like ERPNext:
- Set `app_name` to the CORE app (e.g., `"erpnext"`) — NOT a custom app
- The `module` field in the DocType definition determines the submodule (e.g., `"CRM"`, "Selling", "Stock")
- Use `create_doctype` change type — this is ALLOWED for core apps because it uses Frappe's DocType API
- Example: Creating a DocType in ERPNext's CRM module: `{"app_name": "erpnext", "changes": [{"type": "create_doctype", "definition": {"name": "My Doc", "module": "CRM", ...}}]}`

## CUSTOMIZATION CHANGE TYPES (for core apps like frappe/erpnext)
- **custom_field**: Add a custom field to an existing DocType
  ```json
  {"type": "custom_field", "doctype": "Sales Invoice", "field": {"fieldname": "custom_notes", "fieldtype": "Text", "label": "Notes"}}
  ```
- **property_setter**: Change a property of an existing DocType/field
  ```json
  {"type": "property_setter", "doctype": "Sales Invoice", "fieldname": "customer", "property": "label", "value": "Client"}
  ```
- **server_script**: Create a Server Script for business logic
  ```json
  {"type": "server_script", "name": "My Script", "script_type": "DocType Event", "doctype": "Sales Invoice", "event": "before_submit", "script": "doc.custom_status = 'Submitted'"}
  ```
- **client_script**: Create a Client Script for UI behavior
  ```json
  {"type": "client_script", "name": "My Client Script", "dt": "Sales Invoice", "script": "frappe.ui.form.on('Sales Invoice', { refresh: function(frm) { ... } })"}
  ```
- **workspace_link**: ADD or UPDATE a link in a Workspace
  ```json
  {"type": "workspace_link", "workspace": "CRM", "label": "SMS Sent To Customers", "link_type": "DocType", "link_to": "SMS Sent To Customers"}
  ```
- **workspace_link_remove**: REMOVE a link from a Workspace (use `link_to` or `label` to identify the link)
  ```json
  {"type": "workspace_link_remove", "workspace": "CRM", "link_to": "Warranty Claim"}
  ```
- **workspace_shortcut**: ADD or UPDATE a shortcut in a Workspace
  ```json
  {"type": "workspace_shortcut", "workspace": "CRM", "label": "My Shortcut", "link_to": "Customer", "type": "DocType"}
  ```
- **workspace_shortcut_remove**: REMOVE a shortcut from a Workspace (use `link_to` or `label` to identify the shortcut)
  ```json
  {"type": "workspace_shortcut_remove", "workspace": "CRM", "link_to": "Customer"}
  ```

## CRITICAL: DOCTYPE NAMING RULE VALID VALUES
The "naming_rule" field in DocType JSON MUST be exactly one of these:
- "" (empty string)
- "Set by user"
- "Autoincrement"
- "By fieldname"
- "By \"Naming Series\" field"  (EXACTLY this with quotes)
- "Expression"
- "Expression (old style)"
- "Random"
- "By script"

If using naming_series field, set naming_rule to: "By \"Naming Series\" field"
If using autoname like "AI-STUDIO-TASK-.####", set naming_rule to: "By \"Naming Series\" field"

## SENIOR DEVELOPER CAPABILITIES
You operate like a senior ERPNext developer and can drive the FULL project lifecycle
end-to-end: scaffold a new app, model DocTypes, wire business logic, design workflows,
build reports/dashboards, secure it with roles & permissions, and surface everything in a
polished Workspace. Choose the right building block for each requirement and sequence changes
correctly (create the app → create modules/DocTypes → scripts → workflows → reports/dashboards →
permissions → workspace). For a brand-new solution, prefer scaffolding a dedicated custom app
rather than writing into an existing one.

### BENCH-LEVEL CHANGE TYPES
- **create_app**: Scaffold a brand-new Frappe app (runs `bench new-app`). Use snake_case.
  ```json
  {"type": "create_app", "app_name": "library_management", "app_title": "Library Management",
   "app_description": "Library circulation & membership", "app_publisher": "Acme", "install": true}
  ```
- **install_app**: Install an existing app on the current site.
  ```json
  {"type": "install_app", "app_name": "library_management"}
  ```
- **create_module**: Create a Module Def (+ on-disk folder) inside an app.
  ```json
  {"type": "create_module", "app_name": "library_management", "module_name": "Circulation"}
  ```

### WORKFLOW MANAGEMENT
- **workflow**: Create/update a full Frappe Workflow. Referenced Workflow States and Actions are
  auto-created. Set `workflow_state_field` (usually "workflow_state").
  ```json
  {"type": "workflow", "name": "Loan Approval", "document_type": "Library Loan",
   "workflow_state_field": "workflow_state", "is_active": 1,
   "states": [
     {"state": "Draft", "doc_status": "0", "allow_edit": "Library User", "style": "Warning"},
     {"state": "Approved", "doc_status": "1", "allow_edit": "Library Manager", "style": "Success"}],
   "transitions": [
     {"state": "Draft", "action": "Approve", "next_state": "Approved", "allowed": "Library Manager"}]}
  ```
- **workflow_state** / **workflow_action**: Create a single state/action master when needed.

### WORKSPACE (full page, not just links)
- **create_workspace**: Create/update a whole Workspace with links, shortcuts, charts and number cards.
  ```json
  {"type": "create_workspace", "title": "Library", "icon": "book", "module": "Circulation", "public": 1,
   "shortcuts": [{"label": "New Loan", "link_to": "Library Loan", "type": "DocType", "color": "Blue"}],
   "links": [{"label": "Library Loan", "link_to": "Library Loan", "link_type": "DocType", "type": "Link"}]}
  ```
  (Use `workspace_link` / `workspace_shortcut` for incremental edits to an EXISTING workspace.)

### REPORTS, DASHBOARDS & ALERTS
- **report**: Query Report (read-only SELECT only) or Script Report (sandboxed Python).
  ```json
  {"type": "report", "name": "Overdue Loans", "ref_doctype": "Library Loan", "report_type": "Query Report",
   "query": "SELECT name, member, due_date FROM `tabLibrary Loan` WHERE status = 'Overdue'",
   "roles": ["Library Manager"]}
  ```
- **dashboard_chart**: `{"type": "dashboard_chart", "name": "Loans by Status", "document_type": "Library Loan", "chart_type": "Group By", "group_by_based_on": "status", "type": "Donut"}`
- **number_card**: `{"type": "number_card", "name": "Open Loans", "document_type": "Library Loan", "function": "Count", "filters_json": "{\\"status\\":\\"Open\\"}"}`
- **notification**: `{"type": "notification", "name": "Loan Due", "document_type": "Library Loan", "event": "Days Before", "date_changed": "due_date", "days_in_advance": 2, "channel": "Email", "subject": "Loan due soon", "message": "..."}`

### SECURITY (roles & permissions)
- **role**: `{"type": "role", "name": "Library Manager", "desk_access": 1}`
- **permission**: Grant a role rights on a DocType.
  ```json
  {"type": "permission", "doctype": "Library Loan", "role": "Library Manager",
   "permlevel": 0, "read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1, "delete": 0}
  ```

### PRESENTATION
- **print_format**: `{"type": "print_format", "name": "Loan Slip", "doctype": "Library Loan", "print_format_type": "Jinja", "html": "<div>{{ doc.name }}</div>"}`
- **web_form**: `{"type": "web_form", "route": "apply-for-loan", "doctype": "Library Loan", "title": "Apply for a Loan", "published": 1, "login_required": 1, "web_form_fields": [{"fieldname": "member", "fieldtype": "Link", "label": "Member", "options": "Library Member", "reqd": 1}]}`

### SEQUENCING RULE
When a request needs multiple artefacts, emit them as ONE ordered `changes` array so they apply
atomically in dependency order. Never reference a DocType/role/workspace before the change that
creates it. Query Reports must be read-only SELECTs; all server-side Python is AST-sanitized.

## SAFETY
- Git snapshots are taken automatically before changes
- Changes are rolled back automatically if any step fails
- Python syntax is validated before writing .py files
- All Python code is scanned by an AST-based security validator (import/function whitelisting)
- Database changes run through a dry-run transaction before deployment

## ASYNC PIPELINE
When the user submits a request, it is processed asynchronously:
1. **Pending** — task queued
2. **In Progress** — LLM call in progress
3. **Linting** — AST security scan + change validation
4. **Testing** — dry-run in a database savepoint (rolled back automatically)
5. **Completed** — changes staged, waiting for user approval
6. **Failed** — pipeline halted, error trace available
7. **Rolled Back** — user rejected the changes

The user must explicitly approve (Deploy) or reject (Rollback) the changes.
"""


# ---------------------------------------------------------------------------
# LLM call implementations
# ---------------------------------------------------------------------------


def _call_openai_compatible(url, headers, payload):
    import requests

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_openai(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    if not api_key:
        raise frappe.ValidationError(_("OpenAI API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["OpenAI"]
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _call_openai_compatible(url, headers, payload)


def _call_anthropic(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    import requests

    if not api_key:
        raise frappe.ValidationError(_("Anthropic API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["Anthropic"]
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    system = ""
    user_messages = []
    for m in messages:
        if m.get("role") == "system":
            system = m.get("content", "")
        else:
            user_messages.append(m)

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": user_messages,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]


def _call_gemini(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    """Call Gemini API using the official Google GenAI SDK."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise frappe.ValidationError(_("Google GenAI SDK not installed. Run: pip install google-genai"))

    if not api_key:
        raise frappe.ValidationError(_("Gemini API key not configured"))

    client = genai.Client(api_key=api_key)

    system_text = ""
    contents = []

    for m in messages:
        if m.get("role") == "system":
            system_text = m.get("content", "")
        elif m.get("role") == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=m.get("content", ""))]))
        elif m.get("role") == "assistant":
            contents.append(types.Content(role="model", parts=[types.Part(text=m.get("content", ""))]))

    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
    )

    if system_text:
        config.system_instruction = system_text

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    return response.text


def _call_kimi(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    if not api_key:
        raise frappe.ValidationError(_("Kimi API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["Moonshot AI (Kimi)"]
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _call_openai_compatible(url, headers, payload)


def _call_deepseek(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    if not api_key:
        raise frappe.ValidationError(_("DeepSeek API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["DeepSeek"]
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _call_openai_compatible(url, headers, payload)


def _call_groq(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    if not api_key:
        raise frappe.ValidationError(_("Groq API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["Groq"]
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "content-type": "application/json",
    }
    # Groq uses OpenAI-compatible format but strip the groq- prefix
    actual_model = model.replace("groq-", "")
    payload = {
        "model": actual_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _call_openai_compatible(url, headers, payload)


def _call_azure_openai(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    if not api_key:
        raise frappe.ValidationError(_("Azure OpenAI API key not configured"))
    if not api_base_url:
        raise frappe.ValidationError(_("Azure OpenAI requires a custom API base URL"))

    url = "{}/chat/completions?api-version=2024-06-01".format(api_base_url.rstrip("/"))
    headers = {
        "api-key": api_key,
        "content-type": "application/json",
    }
    actual_model = model.replace("azure-", "")
    payload = {
        "model": actual_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _call_openai_compatible(url, headers, payload)


def _call_cohere(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    import requests

    if not api_key:
        raise frappe.ValidationError(_("Cohere API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["Cohere"]
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "content-type": "application/json",
    }

    # Convert messages to Cohere format
    message = ""
    preamble = ""
    for m in messages:
        if m.get("role") == "system":
            preamble = m.get("content", "")
        else:
            message += m.get("content", "") + "\n"

    payload = {
        "model": model.replace("cohere-", ""),
        "message": message.strip(),
        "temperature": temperature,
    }
    if preamble:
        payload["preamble"] = preamble

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["text"]


def _call_mistral(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    if not api_key:
        raise frappe.ValidationError(_("Mistral API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["Mistral AI"]
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _call_openai_compatible(url, headers, payload)


def _call_together(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    if not api_key:
        raise frappe.ValidationError(_("Together AI API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["Together AI"]
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "content-type": "application/json",
    }
    payload = {
        "model": model.replace("together-", ""),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _call_openai_compatible(url, headers, payload)


def _call_perplexity(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    if not api_key:
        raise frappe.ValidationError(_("Perplexity API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["Perplexity"]
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "content-type": "application/json",
    }
    payload = {
        "model": model.replace("perplexity-", ""),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _call_openai_compatible(url, headers, payload)


def _call_openrouter(messages, model, temperature, api_key, api_base_url=None, max_tokens=4096):
    if not api_key:
        raise frappe.ValidationError(_("OpenRouter API key not configured"))

    url = api_base_url or PROVIDER_ENDPOINTS["OpenRouter"]
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "content-type": "application/json",
        "HTTP-Referer": frappe.utils.get_url(),
        "X-Title": "Frappe AI Studio",
    }
    payload = {
        "model": model.replace("openrouter-", "").replace("-", "/"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return _call_openai_compatible(url, headers, payload)


# ---------------------------------------------------------------------------
# Unified LLM runner
# ---------------------------------------------------------------------------


def _run_llm(messages, provider=None, model=None, temperature=None):
    cfg = _get_llm_config(provider=provider, model=model, temperature=temperature)
    provider = cfg["provider"]
    model = cfg["model"]
    temperature = cfg["temperature"]
    api_key = cfg["api_key"]
    api_base_url = cfg["api_base_url"]

    if not api_key:
        raise frappe.ValidationError(_("API key not configured for {}").format(provider))

    dispatch = {
        "OpenAI": _call_openai,
        "Anthropic": _call_anthropic,
        "Google Gemini": _call_gemini,
        "Moonshot AI (Kimi)": _call_kimi,
        "DeepSeek": _call_deepseek,
        "Groq": _call_groq,
        "Azure OpenAI": _call_azure_openai,
        "Cohere": _call_cohere,
        "Mistral AI": _call_mistral,
        "Together AI": _call_together,
        "Perplexity": _call_perplexity,
        "OpenRouter": _call_openrouter,
    }

    fn = dispatch.get(provider, _call_openai)
    return fn(messages, model, temperature, api_key, api_base_url=api_base_url)


# ---------------------------------------------------------------------------
# Whitelisted API methods
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_context(target_app=None):
    """Return the current bench context (cached)."""
    _guard()
    return get_cached_context(target_app=target_app)


@frappe.whitelist()
def get_llm_providers():
    """Return list of supported LLM providers and their models."""
    _guard()
    providers = []
    for name, endpoint in PROVIDER_ENDPOINTS.items():
        providers.append(
            {
                "name": name,
                "endpoint": endpoint,
                "env_var": PROVIDER_API_KEY_ENV.get(name),
            }
        )
    return providers


@frappe.whitelist()
def get_installed_apps():
    """Return list of installed apps in the bench."""
    _guard()
    from frappe_ai_studio.frappe_ai_studio.context_engine import list_installed_apps

    return list_installed_apps()


@frappe.whitelist()
def get_ai_studio_settings():
    """Return current AI Studio settings (safe, no API key)."""
    _guard()
    settings = _get_active_settings()
    if not settings:
        return {
            "default_provider": "OpenAI",
            "default_model": "gpt-4o",
            "temperature": 0.2,
            "has_api_key": bool(frappe.conf.get("ai_studio_api_key")),
        }
    return {
        "default_provider": settings.default_provider,
        "default_model": settings.default_model,
        "temperature": settings.temperature,
        "has_api_key": bool(settings.get_password("api_key")),
    }


@frappe.whitelist()
def save_ai_studio_settings(settings_json):
    """Save AI Studio settings."""
    _guard()
    if isinstance(settings_json, str):
        settings_json = json.loads(settings_json)

    doc = (
        frappe.get_doc("AI Studio Settings", "AI Studio Settings")
        if frappe.db.exists("AI Studio Settings", "AI Studio Settings")
        else frappe.new_doc("AI Studio Settings")
    )

    doc.default_provider = settings_json.get("default_provider", "OpenAI")
    doc.default_model = settings_json.get("default_model", "gpt-4o")
    doc.temperature = settings_json.get("temperature", 0.2)
    if settings_json.get("api_key"):
        doc.api_key = settings_json.get("api_key")

    # Handle enabled models table
    doc.set("enabled_models", [])
    for m in settings_json.get("enabled_models", []):
        doc.append(
            "enabled_models",
            {
                "provider": m.get("provider"),
                "model_name": m.get("model_name"),
                "model_id": m.get("model_id"),
                "enabled": m.get("enabled", 1),
                "api_base_url": m.get("api_base_url"),
            },
        )

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    _audit("save_settings", provider=doc.default_provider, model=doc.default_model)
    return {"status": "saved"}


@frappe.whitelist()
def read_file(app_name, relative_path):
    """Read a file inside an app."""
    _guard()
    file_path = resolve_app_path(app_name, *relative_path.strip("/").split("/"))
    content = safe_read(file_path)
    if content is None:
        frappe.throw(_("File not found: {0}").format(file_path))
    return {"path": file_path, "content": content}


@frappe.whitelist()
def list_app_files(app_name, max_depth=4):
    """List all files in an app up to a certain depth."""
    _guard()
    try:
        max_depth = int(max_depth)
    except (ValueError, TypeError):
        max_depth = 4
    try:
        app_path = frappe.get_app_path(app_name)
    except Exception:
        return {"files": [], "tree": {}}

    files = []

    # Build file list
    for root, dirs, filenames in os.walk(app_path):
        # Skip hidden dirs, __pycache__, node_modules, .git
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules")]

        rel_root = os.path.relpath(root, app_path)
        depth = rel_root.count(os.sep)
        if depth > max_depth:
            del dirs[:]
            continue

        for fname in filenames:
            if fname.startswith("."):
                continue
            rel_path = os.path.join(rel_root, fname) if rel_root != "." else fname
            files.append(rel_path.replace("\\", "/"))

    return {"files": files, "app_path": app_path}


def _assert_not_core_file_write(app_name):
    """Core apps must never be modified via direct file writes."""
    if app_name in ("frappe", "erpnext"):
        frappe.throw(
            _(
                "Direct file writes to core app '{0}' are not allowed. "
                "Use custom fields, property setters or scripts instead."
            ).format(app_name)
        )


@frappe.whitelist()
def write_code(app_name, relative_path, content, action="overwrite"):
    """Write code to a file with pre-flight syntax + security validation."""
    _guard()
    _assert_not_core_file_write(app_name)
    file_path = resolve_app_path(app_name, *relative_path.strip("/").split("/"))

    if file_path.endswith(".py"):
        ok, msg = validate_python_syntax(content)
        if not ok:
            frappe.throw(_("Validation failed: {0}").format(msg))
        # Security scan applies to every path that writes Python, not just the
        # async pipeline — this is a hard boundary, not a convenience check.
        sec_ok, sec_msg = validate_code_security(content)
        if not sec_ok:
            frappe.throw(_("Security check failed: {0}").format(sec_msg))

    if action == "overwrite":
        safe_write(file_path, content)
    elif action == "append":
        existing = safe_read(file_path) or ""
        safe_write(file_path, existing + content)
    else:
        frappe.throw(_("Unknown action: {0}").format(action))

    _audit("write_code", app=app_name, path=relative_path, action=action)
    return {"path": file_path, "status": "saved"}


@frappe.whitelist()
def inject_method(app_name, relative_path, class_name, method_code):
    """Surgically inject a method into a class via libcst."""
    _guard()
    _assert_not_core_file_write(app_name)
    sec_ok, sec_msg = validate_code_security(method_code)
    if not sec_ok:
        frappe.throw(_("Security check failed: {0}").format(sec_msg))
    file_path = resolve_app_path(app_name, *relative_path.strip("/").split("/"))
    inject_method_to_class(file_path, class_name, method_code)
    _audit("inject_method", app=app_name, path=relative_path, cls=class_name)
    return {"path": file_path, "status": "injected"}


@frappe.whitelist()
def update_json(app_name, relative_path, updates):
    """Merge JSON updates into a file."""
    _guard()
    _assert_not_core_file_write(app_name)
    file_path = resolve_app_path(app_name, *relative_path.strip("/").split("/"))
    if isinstance(updates, str):
        updates = json.loads(updates)
    update_json_file(file_path, updates)
    _audit("update_json", app=app_name, path=relative_path)
    return {"path": file_path, "status": "updated"}


@frappe.whitelist()
def snapshot_app(app_name):
    """Git-commit the target app before changes."""
    _guard()
    ok, msg = git_snapshot(app_name)
    if not ok:
        frappe.throw(msg)
    return {"status": "snapshotted", "message": msg}


@frappe.whitelist()
def rollback_app(app_name):
    """Rollback the target app to the last commit."""
    _guard()
    ok, msg = git_rollback(app_name)
    if not ok:
        frappe.throw(msg)
    _audit("rollback_app", app=app_name)
    return {"status": "rolled_back", "message": msg}


@frappe.whitelist()
def run_bench_command(command):
    """Run an allowed bench command."""
    _guard()
    allowed = {"migrate", "restart", "clear-cache", "build", "watch", "build --app frappe_ai_studio"}
    if command not in allowed:
        frappe.throw(_("Command '{0}' is not allowed").format(command))
    _audit("run_bench_command", command=command)

    bench_path = frappe.utils.get_bench_path()
    site = frappe.local.site

    try:
        result = subprocess.run(
            ["bench", "--site", site, command],
            cwd=bench_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return {"status": "success", "output": result.stdout}
    except subprocess.CalledProcessError as e:
        frappe.throw(_("Bench command failed: {0}").format(e.stderr or e.stdout))


@frappe.whitelist()
def execute_prompt(
    prompt_name,
    user_prompt=None,
    target_app=None,
    provider=None,
    model=None,
    temperature=None,
    conversation_history=None,
):
    """Execute a stored prompt against the LLM and return the response.

    This is the SYNCHRONOUS version. For production use, prefer
    execute_prompt_async() which runs the full pipeline (lint, dry-run, approve).
    """
    _guard()
    if user_prompt and len(user_prompt) > MAX_PROMPT_CHARS:
        frappe.throw(_("Prompt exceeds maximum length of {0} characters").format(MAX_PROMPT_CHARS))
    if prompt_name == "__direct__":
        system = DEFAULT_SYSTEM_PROMPT
        user = user_prompt or ""
        cfg = _get_llm_config(provider=provider, model=model, temperature=temperature)
        model = model or cfg["model"]
        temperature = temperature if temperature is not None else cfg["temperature"]
        provider = provider or cfg["provider"]
    else:
        prompt_doc = frappe.get_doc("AI Studio Prompt", prompt_name)
        system = prompt_doc.system_prompt or DEFAULT_SYSTEM_PROMPT
        user = user_prompt or prompt_doc.user_prompt or ""
        model = model or prompt_doc.model or _get_llm_config()["model"]
        temperature = (
            temperature
            if temperature is not None
            else (prompt_doc.temperature or _get_llm_config()["temperature"])
        )
        provider = provider or prompt_doc.provider or _resolve_provider_from_model(model)

    app = target_app

    # Build context
    context = build_context(target_app=app)
    context_json = json.dumps(context, indent=2, default=str)

    # Build messages with conversation history
    messages = [{"role": "system", "content": system}]

    # Add conversation history if provided
    if conversation_history:
        if isinstance(conversation_history, str):
            conversation_history = json.loads(conversation_history)
        for msg in conversation_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append(
        {
            "role": "user",
            "content": "Bench Context:\n```json\n{}```\n\nUser Request:\n{}".format(context_json, user),
        }
    )

    log = frappe.get_doc(
        {
            "doctype": "AI Studio Log",
            "prompt": prompt_name,
            "status": "Pending",
            "input_payload": json.dumps(messages),
        }
    )
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    try:
        response = _run_llm(messages, provider=provider, model=model, temperature=temperature)
        log.status = "Success"
        log.output_payload = response
        log.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "response": response, "log": log.name}
    except Exception as e:
        log.status = "Failed"
        log.error_trace = frappe.get_traceback()
        log.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw(_("LLM call failed: {0}").format(str(e)))


@frappe.whitelist()
def execute_prompt_async(
    user_prompt, target_app=None, provider=None, model=None, temperature=None, conversation_history=None
):
    """Enqueue an AI generation task and return the task ID immediately.

    The frontend should listen for 'ai_generation_progress' realtime events
    or poll get_generation_task_status().
    """
    _guard()
    if user_prompt and len(user_prompt) > MAX_PROMPT_CHARS:
        frappe.throw(_("Prompt exceeds maximum length of {0} characters").format(MAX_PROMPT_CHARS))
    from frappe_ai_studio.frappe_ai_studio.agent_orchestrator import enqueue_generation_task

    task_name = enqueue_generation_task(
        user_prompt=user_prompt,
        target_app=target_app,
        provider=provider,
        model=model,
        temperature=temperature,
        conversation_history=conversation_history,
    )
    return {"status": "queued", "task_id": task_name}


@frappe.whitelist()
def apply_ai_changes(app_name, changes):
    """Apply a list of AI-generated changes atomically.

    File-based changes are guarded by a git snapshot (rolled back on failure);
    database changes run in a single transaction that is rolled back on any
    error so partial application cannot leave the system half-changed.
    """
    _guard()
    changes = _parse_changes(changes)

    # Determine if any change requires file system access (needs snapshot)
    file_based_types = {"write", "inject_method", "update_json", "create_doctype", "sync_doctype"}
    needs_snapshot = any(c.get("type") in file_based_types for c in changes)
    is_core_app = app_name in ("frappe", "erpnext")

    # An app being scaffolded in this same batch doesn't exist on disk yet, so
    # there is nothing to snapshot up front (create_app git-inits it itself).
    app_on_disk = True
    try:
        app_on_disk = bool(app_name) and os.path.isdir(frappe.get_app_path(app_name))
    except Exception:
        app_on_disk = False

    # Pre-flight: snapshot only for file-based changes in existing non-core apps.
    if needs_snapshot and not is_core_app and app_on_disk:
        snapshot_app(app_name)

    # Open an atomic batch: helpers defer their commits so the whole batch
    # commits once at the end (or rolls back together on failure).
    flags = getattr(frappe, "flags", None)
    if flags is not None:
        flags.ai_studio_in_batch = True

    applied = []
    try:
        for change in changes:
            ctype = change.get("type")
            rel = change.get("relative_path")

            if ctype == "write":
                write_code(app_name, rel, change["content"], action=change.get("action", "overwrite"))
            elif ctype == "inject_method":
                inject_method(app_name, rel, change["class_name"], change["method_code"])
            elif ctype == "update_json":
                update_json(app_name, rel, change["updates"])
            elif ctype == "create_doctype":
                from frappe_ai_studio.frappe_ai_studio.schema_wizard import create_doctype

                definition = change.get("definition") or change.get("updates")
                create_doctype(app_name, definition)
            elif ctype == "sync_doctype":
                from frappe_ai_studio.frappe_ai_studio.schema_wizard import sync_doctype_from_json

                sync_doctype_from_json(app_name, rel)
            elif ctype == "run_bench":
                run_bench_command(change["command"])
            elif ctype == "custom_field":
                _apply_custom_field(change)
            elif ctype == "property_setter":
                _apply_property_setter(change)
            elif ctype == "server_script":
                _apply_server_script(change)
            elif ctype == "client_script":
                _apply_client_script(change)
            elif ctype == "workspace_link":
                _apply_workspace_link(change)
            elif ctype == "workspace_link_remove":
                _apply_workspace_link_remove(change)
            elif ctype == "workspace_shortcut":
                _apply_workspace_shortcut(change)
            elif ctype == "workspace_shortcut_remove":
                _apply_workspace_shortcut_remove(change)
            elif ctype in _ADVANCED_TYPES:
                _apply_advanced_change(ctype, change)
            elif ctype in ("create_app", "install_app", "create_module"):
                _apply_bench_change(ctype, change)
            else:
                raise ValueError("Unknown change type: {}".format(ctype))
            applied.append(change)

        # Commit the whole batch atomically.
        if flags is not None:
            flags.ai_studio_in_batch = False
        frappe.db.commit()
        _audit("apply_ai_changes", app=app_name, count=len(applied), types=[c.get("type") for c in applied])
        return {"status": "applied", "changes": applied}
    except Exception as e:
        # Roll back any uncommitted DB work from this batch.
        if flags is not None:
            flags.ai_studio_in_batch = False
        try:
            frappe.db.rollback()
        except Exception:
            pass
        # Auto-rollback file changes (only for non-core apps we snapshotted).
        if needs_snapshot and not is_core_app:
            rollback_app(app_name)
        _audit("apply_ai_changes_failed", app=app_name, error=str(e))
        frappe.throw(_("Changes caused an error: {0}").format(str(e)))


@frappe.whitelist()
def apply_ai_changes_dry_run(app_name, changes):
    """Validate changes without any side effects.

    The previous implementation ran the real ``apply_ai_changes`` inside a DB
    savepoint, but savepoints do not roll back filesystem writes, DDL, or bench
    commands — so a "dry run" mutated the app on disk. This now performs static
    validation only: nothing is written, executed, or committed.
    """
    _guard()
    changes = _parse_changes(changes)
    report = validate_changes(app_name, changes)
    return {"status": "dry_run", "result": report}


@frappe.whitelist()
def validate_changes(app_name, changes):
    """Statically validate a change list. Side-effect free.

    Verifies structural completeness, Python syntax + security, safe path
    resolution and that referenced targets (DocTypes, workspaces) exist.
    Returns a report; raises on the first hard failure so the caller can mark
    the task failed.
    """
    _guard()
    changes = _parse_changes(changes)
    is_core_app = app_name in ("frappe", "erpnext")
    report = []

    for idx, change in enumerate(changes):
        ctype = change.get("type")
        issues = []

        if ctype in ("write", "inject_method", "update_json"):
            rel = change.get("relative_path")
            if not rel:
                issues.append("missing 'relative_path'")
            else:
                # Path containment check (raises on traversal).
                resolve_app_path(app_name, *rel.strip("/").split("/"))
            if is_core_app:
                issues.append("file writes are not allowed on core app '{}'".format(app_name))

        if ctype == "write" and (change.get("relative_path", "") or "").endswith(".py"):
            code = change.get("content", "")
            ok, msg = validate_python_syntax(code)
            if not ok:
                issues.append("syntax: {}".format(msg))
            ok, msg = validate_code_security(code)
            if not ok:
                issues.append("security: {}".format(msg))

        if ctype == "inject_method":
            ok, msg = validate_code_security(change.get("method_code", ""))
            if not ok:
                issues.append("security: {}".format(msg))
            if not change.get("class_name"):
                issues.append("missing 'class_name'")

        if ctype in ("server_script", "client_script"):
            ok, msg = validate_code_security(change.get("script", ""))
            if ctype == "server_script" and not ok:
                issues.append("security: {}".format(msg))
            if not change.get("name") or not change.get("script"):
                issues.append("missing 'name' or 'script'")

        if ctype == "custom_field":
            if not change.get("doctype"):
                issues.append("missing 'doctype'")
            elif not frappe.db.exists("DocType", change.get("doctype")):
                issues.append("DocType '{}' does not exist".format(change.get("doctype")))

        if ctype == "property_setter":
            if not change.get("doctype") or not change.get("property"):
                issues.append("missing 'doctype' or 'property'")

        if ctype in (
            "workspace_link",
            "workspace_link_remove",
            "workspace_shortcut",
            "workspace_shortcut_remove",
        ):
            if not change.get("workspace"):
                issues.append("missing 'workspace'")

        if ctype == "create_doctype":
            definition = change.get("definition") or change.get("updates") or {}
            if not definition.get("name"):
                issues.append("create_doctype missing definition.name")

        if ctype in ("create_app", "install_app"):
            from frappe_ai_studio.frappe_ai_studio.builder import validate_app_name

            ok, msg = validate_app_name(change.get("app_name") or change.get("name"))
            if not ok:
                issues.append(msg)

        if ctype == "create_module":
            if not change.get("app_name") or not (change.get("module_name") or change.get("name")):
                issues.append("create_module requires 'app_name' and 'module_name'")

        if ctype == "workflow":
            d = change.get("definition") or change
            if not d.get("name") or not d.get("document_type") or not d.get("states"):
                issues.append("workflow requires 'name', 'document_type' and 'states'")
            elif not frappe.db.exists("DocType", d.get("document_type")):
                issues.append("DocType '{}' does not exist".format(d.get("document_type")))

        if ctype == "create_workspace":
            d = change.get("definition") or change
            if not (d.get("title") or d.get("label")):
                issues.append("workspace requires 'title'")

        if ctype == "report":
            from frappe_ai_studio.frappe_ai_studio.advanced_customization import validate_readonly_sql

            d = change.get("definition") or change
            if not d.get("name") or not d.get("ref_doctype"):
                issues.append("report requires 'name' and 'ref_doctype'")
            if d.get("report_type") == "Query Report":
                ok, msg = validate_readonly_sql(d.get("query", ""))
                if not ok:
                    issues.append("query: {}".format(msg))
            if d.get("report_type") == "Script Report":
                ok, msg = validate_code_security(d.get("report_script", ""))
                if not ok:
                    issues.append("script: {}".format(msg))

        if ctype in ("notification", "dashboard_chart", "number_card"):
            d = change.get("definition") or change
            if not d.get("document_type"):
                issues.append("{} requires 'document_type'".format(ctype))

        if ctype == "permission":
            d = change.get("definition") or change
            if not d.get("doctype") or not d.get("role"):
                issues.append("permission requires 'doctype' and 'role'")

        report.append({"index": idx, "type": ctype, "ok": not issues, "issues": issues})

    failures = [r for r in report if not r["ok"]]
    if failures:
        summary = "; ".join(
            "change[{}] ({}): {}".format(r["index"], r["type"], ", ".join(r["issues"])) for r in failures
        )
        raise ValueError("Validation failed: {}".format(summary))

    return report


@frappe.whitelist()
def preview_changes(app_name, changes):
    """Preview changes without applying them. Returns a diff-like view."""
    if isinstance(changes, str):
        changes = json.loads(changes)

    preview = []
    for change in changes:
        ctype = change.get("type")
        rel = change.get("relative_path")
        item = {"type": ctype, "relative_path": rel, "preview": ""}

        if ctype == "write":
            file_path = resolve_app_path(app_name, *rel.strip("/").split("/"))
            existing = safe_read(file_path) or ""
            if existing:
                item["preview"] = "--- existing\n+++ new\n" + _simple_diff(existing, change["content"])
            else:
                item["preview"] = "+++ new file\n" + change["content"]
        elif ctype == "inject_method":
            item["preview"] = "Inject method into class '{}' in {}".format(change["class_name"], rel)
        elif ctype == "update_json":
            item["preview"] = "Update JSON: {}".format(json.dumps(change["updates"], indent=2))
        elif ctype == "create_doctype":
            item["preview"] = "Create DocType: {}".format(change.get("definition", {}).get("name", "unknown"))
        elif ctype == "sync_doctype":
            item["preview"] = "Sync DocType from JSON: {}".format(rel)
        elif ctype == "run_bench":
            item["preview"] = "Run bench command: {}".format(change["command"])
        elif ctype == "custom_field":
            item["preview"] = "Add custom field '{}' to DocType '{}'".format(
                change.get("field", {}).get("fieldname", "unknown"), change.get("doctype", "unknown")
            )
        elif ctype == "property_setter":
            item["preview"] = "Set property '{}' = '{}' on '{}.{}'".format(
                change.get("property"),
                change.get("value"),
                change.get("doctype"),
                change.get("fieldname", "_doc"),
            )
        elif ctype == "server_script":
            item["preview"] = "Server Script '{}': {} event on '{}'".format(
                change.get("name"), change.get("event"), change.get("doctype")
            )
        elif ctype == "client_script":
            item["preview"] = "Client Script '{}' for '{}'".format(
                change.get("name"), change.get("dt") or change.get("doctype")
            )
        elif ctype == "workspace_link":
            item["preview"] = "Add link '{}' -> '{}' to Workspace '{}'".format(
                change.get("label"), change.get("link_to"), change.get("workspace")
            )
        elif ctype == "workspace_link_remove":
            item["preview"] = "REMOVE link '{}' from Workspace '{}'".format(
                change.get("link_to"), change.get("workspace")
            )
        elif ctype == "workspace_shortcut":
            item["preview"] = "Add shortcut '{}' -> '{}' to Workspace '{}'".format(
                change.get("label"), change.get("link_to"), change.get("workspace")
            )
        elif ctype == "workspace_shortcut_remove":
            item["preview"] = "REMOVE shortcut '{}' from Workspace '{}'".format(
                change.get("link_to"), change.get("workspace")
            )
        elif ctype == "create_app":
            item["preview"] = "Scaffold new app '{}'{}".format(
                change.get("app_name") or change.get("name"),
                " and install on site" if change.get("install") else "",
            )
        elif ctype == "install_app":
            item["preview"] = "Install app '{}' on the current site".format(
                change.get("app_name") or change.get("name")
            )
        elif ctype == "create_module":
            item["preview"] = "Create module '{}' in app '{}'".format(
                change.get("module_name") or change.get("name"), change.get("app_name")
            )
        elif ctype == "workflow":
            d = change.get("definition") or change
            item["preview"] = "Workflow '{}' on '{}' — {} state(s), {} transition(s)".format(
                d.get("name"),
                d.get("document_type"),
                len(d.get("states") or []),
                len(d.get("transitions") or []),
            )
        elif ctype == "create_workspace":
            d = change.get("definition") or change
            item["preview"] = "Create/Update Workspace '{}' ({} links, {} shortcuts)".format(
                d.get("title") or d.get("label"),
                len(d.get("links") or []),
                len(d.get("shortcuts") or []),
            )
        elif ctype == "report":
            d = change.get("definition") or change
            item["preview"] = "{} '{}' on '{}'".format(
                d.get("report_type", "Report"), d.get("name"), d.get("ref_doctype")
            )
        elif ctype in (
            "notification",
            "dashboard_chart",
            "number_card",
            "role",
            "permission",
            "print_format",
            "web_form",
            "workflow_state",
            "workflow_action",
        ):
            d = change.get("definition") or change
            label = (
                d.get("name")
                or d.get("label")
                or d.get("role")
                or d.get("state")
                or d.get("action")
                or d.get("route")
            )
            item["preview"] = "{}: '{}'{}".format(
                ctype.replace("_", " ").title(),
                label,
                " on '{}'".format(d.get("document_type") or d.get("doctype"))
                if (d.get("document_type") or d.get("doctype"))
                else "",
            )

        preview.append(item)

    return {"status": "preview", "preview": preview}


def _simple_diff(old, new):
    """Generate a simple line-based diff."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    result = []
    max_len = max(len(old_lines), len(new_lines))
    for i in range(max_len):
        if i < len(old_lines) and i < len(new_lines):
            if old_lines[i] != new_lines[i]:
                result.append("- " + old_lines[i])
                result.append("+ " + new_lines[i])
            else:
                result.append("  " + old_lines[i])
        elif i < len(old_lines):
            result.append("- " + old_lines[i])
        else:
            result.append("+ " + new_lines[i])
    return "\n".join(result)


# ---------------------------------------------------------------------------
# Customization helpers (for core apps like frappe/erpnext)
# ---------------------------------------------------------------------------


# Advanced (senior-developer) change types handled by advanced_customization.
_ADVANCED_TYPES = {
    "workflow",
    "workflow_state",
    "workflow_action",
    "create_workspace",
    "report",
    "notification",
    "dashboard_chart",
    "number_card",
    "role",
    "permission",
    "print_format",
    "web_form",
}


def _apply_advanced_change(ctype, change):
    """Dispatch a senior-developer change to advanced_customization."""
    from frappe_ai_studio.frappe_ai_studio import advanced_customization as adv

    definition = change.get("definition") or change

    if ctype == "workflow":
        return adv.safe_workflow(definition)
    if ctype == "workflow_state":
        adv.ensure_workflow_state(change.get("state") or change.get("name"), change.get("style", "Primary"))
        _maybe_commit()
        return {"status": "saved"}
    if ctype == "workflow_action":
        adv.ensure_workflow_action(change.get("action") or change.get("name"))
        _maybe_commit()
        return {"status": "saved"}
    if ctype == "create_workspace":
        return adv.safe_workspace_create(definition)
    if ctype == "report":
        return adv.safe_report(definition)
    if ctype == "notification":
        return adv.safe_notification(definition)
    if ctype == "dashboard_chart":
        return adv.safe_dashboard_chart(definition)
    if ctype == "number_card":
        return adv.safe_number_card(definition)
    if ctype == "role":
        return adv.safe_role(definition)
    if ctype == "permission":
        return adv.safe_permission(definition)
    if ctype == "print_format":
        return adv.safe_print_format(definition)
    if ctype == "web_form":
        return adv.safe_web_form(definition)
    raise ValueError("Unhandled advanced change type: {}".format(ctype))


def _apply_bench_change(ctype, change):
    """Dispatch a bench-level change (app scaffolding / install / module)."""
    from frappe_ai_studio.frappe_ai_studio import builder

    if ctype == "create_app":
        result = builder.scaffold_app(
            app_name=change.get("app_name") or change.get("name"),
            app_title=change.get("app_title") or change.get("title"),
            app_description=change.get("app_description") or change.get("description"),
            app_publisher=change.get("app_publisher") or change.get("publisher"),
            app_email=change.get("app_email") or change.get("email"),
            app_license=change.get("app_license", "mit"),
            install=change.get("install", False),
        )
        _audit("create_app", app=change.get("app_name") or change.get("name"))
        return result
    if ctype == "install_app":
        result = builder.install_app(change.get("app_name") or change.get("name"))
        _audit("install_app", app=change.get("app_name") or change.get("name"))
        return result
    if ctype == "create_module":
        return builder.create_module(change.get("app_name"), change.get("module_name") or change.get("name"))
    raise ValueError("Unhandled bench change type: {}".format(ctype))


def _apply_custom_field(change):
    """Add a custom field to an existing DocType."""
    doctype = change.get("doctype")
    field = change.get("field") or change.get("definition")
    if not doctype or not field:
        raise ValueError("custom_field requires 'doctype' and 'field'")

    fieldname = field.get("fieldname")
    if fieldname:
        # Check if field already exists as a custom field
        existing = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
        if existing:
            # Update existing custom field instead of creating
            doc = frappe.get_doc("Custom Field", existing)
            for key, value in field.items():
                if hasattr(doc, key) and key not in ("name", "doctype"):
                    setattr(doc, key, value)
            doc.save(ignore_permissions=True)
            _maybe_commit()
            return

    # Create new custom field directly
    doc = frappe.new_doc("Custom Field")
    doc.dt = doctype
    for key, value in field.items():
        if hasattr(doc, key):
            setattr(doc, key, value)

    try:
        doc.insert(ignore_permissions=True)
    except frappe.ValidationError as e:
        err_msg = str(e)
        # If the field already exists (as standard field or previously created), skip silently
        if "already exists" in err_msg.lower() or "exists in" in err_msg.lower():
            frappe.msgprint(_("Field '{0}' already exists in {1}, skipping.").format(fieldname, doctype))
            return
        raise

    _maybe_commit()


def _apply_property_setter(change):
    """Change a property of an existing DocType or field."""
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    doctype = change.get("doctype")
    fieldname = change.get("fieldname")
    property_name = change.get("property")
    value = change.get("value")
    property_type = change.get("property_type", "Data")
    if not doctype or not property_name or value is None:
        raise ValueError("property_setter requires 'doctype', 'property', and 'value'")

    # Check if property setter already exists
    existing = frappe.db.get_value(
        "Property Setter",
        {"doc_type": doctype, "field_name": fieldname or "", "property": property_name},
        "name",
    )
    if existing:
        # Update existing property setter
        doc = frappe.get_doc("Property Setter", existing)
        doc.value = value
        doc.property_type = property_type
        doc.save(ignore_permissions=True)
        _maybe_commit()
        return

    make_property_setter(doctype, fieldname, property_name, value, property_type)
    _maybe_commit()


def _apply_server_script(change):
    """Create or update a Server Script."""
    name = change.get("name")
    script_type = change.get("script_type", "DocType Event")
    doctype = change.get("doctype")
    event = change.get("event", "before_insert")
    script = change.get("script")
    enabled = change.get("enabled", 1)

    if not name or not script:
        raise ValueError("server_script requires 'name' and 'script'")

    if frappe.db.exists("Server Script", name):
        doc = frappe.get_doc("Server Script", name)
    else:
        doc = frappe.new_doc("Server Script")
        doc.name = name

    doc.script_type = script_type
    doc.doctype_event = doctype if script_type == "DocType Event" else None
    doc.event = event if script_type == "DocType Event" else None
    doc.script = script
    doc.enabled = enabled
    doc.save(ignore_permissions=True)
    _maybe_commit()


def _apply_client_script(change):
    """Create or update a Client Script."""
    name = change.get("name")
    dt = change.get("dt") or change.get("doctype")
    script = change.get("script")
    enabled = change.get("enabled", 1)
    view = change.get("view", "Form")

    if not name or not dt or not script:
        raise ValueError("client_script requires 'name', 'dt' (doctype), and 'script'")

    if frappe.db.exists("Client Script", name):
        doc = frappe.get_doc("Client Script", name)
    else:
        doc = frappe.new_doc("Client Script")
        doc.name = name

    doc.dt = dt
    doc.script = script
    doc.enabled = enabled
    doc.view = view
    doc.save(ignore_permissions=True)
    _maybe_commit()


def _resolve_workspace(workspace_name):
    """Find a workspace by title or name."""
    ws_list = frappe.get_all("Workspace", filters={"title": workspace_name}, fields=["name"])
    if ws_list:
        return ws_list[0].name
    ws_list = frappe.get_all("Workspace", filters={"name": workspace_name}, fields=["name"])
    if ws_list:
        return ws_list[0].name
    ws_list = frappe.get_all("Workspace", filters={"name": ["like", f"%{workspace_name}%"]}, fields=["name"])
    if ws_list:
        return ws_list[0].name
    raise ValueError("Workspace '{}' not found".format(workspace_name))


def _apply_workspace_link(change):
    """Add or update a DocType link in a Workspace."""
    workspace_name = change.get("workspace")
    label = change.get("label")
    link_type = change.get("link_type", "DocType")
    link_to = change.get("link_to")

    if not workspace_name or not label or not link_to:
        raise ValueError("workspace_link requires 'workspace', 'label', and 'link_to'")

    ws_name = _resolve_workspace(workspace_name)
    ws = frappe.get_doc("Workspace", ws_name)

    # Check if link already exists
    for link in ws.links:
        if link.link_to == link_to and link.link_type == link_type:
            link.label = label
            ws.save(ignore_permissions=True)
            _maybe_commit()
            return

    ws.append(
        "links",
        {
            "type": "Link",
            "label": label,
            "link_type": link_type,
            "link_to": link_to,
        },
    )
    ws.save(ignore_permissions=True)
    _maybe_commit()


def _apply_workspace_link_remove(change):
    """Remove a link from a Workspace."""
    workspace_name = change.get("workspace")
    link_to = change.get("link_to") or change.get("label")

    if not workspace_name or not link_to:
        raise ValueError("workspace_link_remove requires 'workspace' and 'link_to' (or 'label')")

    ws_name = _resolve_workspace(workspace_name)
    ws = frappe.get_doc("Workspace", ws_name)

    removed = False
    new_links = []
    for link in ws.links:
        if link.link_to == link_to or link.label == link_to:
            removed = True
            continue
        new_links.append(link)

    if not removed:
        frappe.msgprint(
            _("Link '{}' not found in workspace '{}' — nothing to remove.").format(link_to, workspace_name)
        )
        return

    ws.links = new_links
    ws.save(ignore_permissions=True)
    _maybe_commit()
    frappe.msgprint(_("Removed link '{}' from workspace '{}'.").format(link_to, workspace_name))


def _apply_workspace_shortcut(change):
    """Add or update a shortcut in a Workspace."""
    workspace_name = change.get("workspace")
    label = change.get("label")
    link_to = change.get("link_to")
    shortcut_type = change.get("type", "DocType")

    if not workspace_name or not label or not link_to:
        raise ValueError("workspace_shortcut requires 'workspace', 'label', and 'link_to'")

    ws_name = _resolve_workspace(workspace_name)
    ws = frappe.get_doc("Workspace", ws_name)

    for shortcut in ws.shortcuts:
        if shortcut.link_to == link_to:
            shortcut.label = label
            shortcut.type = shortcut_type
            ws.save(ignore_permissions=True)
            _maybe_commit()
            return

    ws.append(
        "shortcuts",
        {
            "label": label,
            "type": shortcut_type,
            "link_to": link_to,
        },
    )
    ws.save(ignore_permissions=True)
    _maybe_commit()


def _apply_workspace_shortcut_remove(change):
    """Remove a shortcut from a Workspace."""
    workspace_name = change.get("workspace")
    link_to = change.get("link_to") or change.get("label")

    if not workspace_name or not link_to:
        raise ValueError("workspace_shortcut_remove requires 'workspace' and 'link_to' (or 'label')")

    ws_name = _resolve_workspace(workspace_name)
    ws = frappe.get_doc("Workspace", ws_name)

    removed = False
    new_shortcuts = []
    for shortcut in ws.shortcuts:
        if shortcut.link_to == link_to or shortcut.label == link_to:
            removed = True
            continue
        new_shortcuts.append(shortcut)

    if not removed:
        frappe.msgprint(
            _("Shortcut '{}' not found in workspace '{}' — nothing to remove.").format(
                link_to, workspace_name
            )
        )
        return

    ws.shortcuts = new_shortcuts
    ws.save(ignore_permissions=True)
    _maybe_commit()
    frappe.msgprint(_("Removed shortcut '{}' from workspace '{}'.").format(link_to, workspace_name))


# ---------------------------------------------------------------------------
# Async task delegation (proxies to agent_orchestrator)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def approve_task(task_name):
    """Approve and deploy a completed AI Generation Task."""
    _guard()
    _audit("approve_task", task=task_name)
    from frappe_ai_studio.frappe_ai_studio.agent_orchestrator import approve_and_deploy

    return approve_and_deploy(task_name)


@frappe.whitelist()
def reject_task(task_name):
    """Reject and roll back a completed AI Generation Task."""
    _guard()
    _audit("reject_task", task=task_name)
    from frappe_ai_studio.frappe_ai_studio.agent_orchestrator import reject_and_rollback

    return reject_and_rollback(task_name)


@frappe.whitelist()
def get_task_status(task_name):
    """Get the current status of an AI Generation Task."""
    _guard()
    from frappe_ai_studio.frappe_ai_studio.agent_orchestrator import get_generation_task_status

    return get_generation_task_status(task_name)


# ---------------------------------------------------------------------------
# Security / validation helpers
# ---------------------------------------------------------------------------


@frappe.whitelist()
def validate_code(code):
    """Run AST security validation on Python code. Returns {ok, message}."""
    _guard()
    ok, msg = validate_code_security(code)
    return {"ok": ok, "message": msg}


# ---------------------------------------------------------------------------
# Boot hook
# ---------------------------------------------------------------------------


def on_session_creation():
    """Inject AI Studio settings into bootinfo."""
    if hasattr(frappe.local, "boot") and frappe.local.boot:
        frappe.local.boot.ai_studio_enabled = True
