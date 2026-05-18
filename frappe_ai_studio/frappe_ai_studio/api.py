# -*- coding: utf-8 -*-
"""API — whitelisted Frappe methods for the AI Studio agent."""

from __future__ import unicode_literals

import json
import os

import frappe
from frappe import _

from frappe_ai_studio.frappe_ai_studio.context_engine import (
    build_context,
    get_cached_context,
)
from frappe_ai_studio.frappe_ai_studio.writer import (
    git_snapshot,
    git_rollback,
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
    # Anthropic
    "claude-3-5-sonnet-20241022": "Anthropic",
    "claude-3-5-sonnet-latest": "Anthropic",
    "claude-3-opus-20240229": "Anthropic",
    "claude-3-sonnet-20240229": "Anthropic",
    "claude-3-haiku-20240307": "Anthropic",
    # Google Gemini
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
    if not frappe.db.table_exists("AI Studio Settings"):
        return None
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
        "temperature": temperature if temperature is not None else frappe.conf.get("ai_studio_temperature", 0.2),
        "api_base_url": None,
    }

    if settings:
        cfg["provider"] = provider or settings.default_provider or cfg["provider"]
        cfg["model"] = model or settings.default_model or cfg["model"]
        cfg["temperature"] = temperature if temperature is not None else (settings.temperature or cfg["temperature"])
        cfg["api_key"] = settings.get_password("api_key") or cfg["api_key"]

    return cfg


def _resolve_provider_from_model(model):
    """Guess provider from model id."""
    return MODEL_PROVIDER_MAP.get(model, "OpenAI")


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
    import requests

    if not api_key:
        raise frappe.ValidationError(_("Gemini API key not configured"))

    base = (api_base_url or PROVIDER_ENDPOINTS["Google Gemini"]).rstrip("/")
    url = "{}/{}:generateContent?key={}".format(base, model, api_key)

    # Convert OpenAI-style messages to Gemini contents
    contents = []
    system_text = ""
    for m in messages:
        if m.get("role") == "system":
            system_text = m.get("content", "")
        else:
            role = "user" if m.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}

    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


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
    return get_cached_context()


@frappe.whitelist()
def get_llm_providers():
    """Return list of supported LLM providers and their models."""
    providers = []
    for name, endpoint in PROVIDER_ENDPOINTS.items():
        providers.append({
            "name": name,
            "endpoint": endpoint,
            "env_var": PROVIDER_API_KEY_ENV.get(name),
        })
    return providers


@frappe.whitelist()
def get_ai_studio_settings():
    """Return current AI Studio settings (safe, no API key)."""
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
    if isinstance(settings_json, str):
        settings_json = json.loads(settings_json)

    doc = frappe.get_doc("AI Studio Settings", "AI Studio Settings") \
        if frappe.db.exists("AI Studio Settings", "AI Studio Settings") \
        else frappe.new_doc("AI Studio Settings")

    doc.default_provider = settings_json.get("default_provider", "OpenAI")
    doc.default_model = settings_json.get("default_model", "gpt-4o")
    doc.temperature = settings_json.get("temperature", 0.2)
    if settings_json.get("api_key"):
        doc.api_key = settings_json.get("api_key")

    # Handle enabled models table
    doc.set("enabled_models", [])
    for m in settings_json.get("enabled_models", []):
        doc.append("enabled_models", {
            "provider": m.get("provider"),
            "model_name": m.get("model_name"),
            "model_id": m.get("model_id"),
            "enabled": m.get("enabled", 1),
            "api_base_url": m.get("api_base_url"),
        })

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "saved"}


@frappe.whitelist()
def read_file(app_name, relative_path):
    """Read a file inside an app."""
    file_path = resolve_app_path(app_name, *relative_path.strip("/").split("/"))
    content = safe_read(file_path)
    if content is None:
        frappe.throw(_("File not found: {0}").format(file_path))
    return {"path": file_path, "content": content}


@frappe.whitelist()
def write_code(app_name, relative_path, content, action="overwrite"):
    """Write code to a file with pre-flight validation."""
    file_path = resolve_app_path(app_name, *relative_path.strip("/").split("/"))

    if file_path.endswith(".py"):
        ok, msg = validate_python_syntax(content)
        if not ok:
            frappe.throw(_("Validation failed: {0}").format(msg))

    if action == "overwrite":
        safe_write(file_path, content)
    elif action == "append":
        existing = safe_read(file_path) or ""
        safe_write(file_path, existing + content)
    else:
        frappe.throw(_("Unknown action: {0}").format(action))

    return {"path": file_path, "status": "saved"}


@frappe.whitelist()
def inject_method(app_name, relative_path, class_name, method_code):
    """Surgically inject a method into a class via libcst."""
    file_path = resolve_app_path(app_name, *relative_path.strip("/").split("/"))
    inject_method_to_class(file_path, class_name, method_code)
    return {"path": file_path, "status": "injected"}


@frappe.whitelist()
def update_json(app_name, relative_path, updates):
    """Merge JSON updates into a file."""
    file_path = resolve_app_path(app_name, *relative_path.strip("/").split("/"))
    if isinstance(updates, str):
        updates = json.loads(updates)
    update_json_file(file_path, updates)
    return {"path": file_path, "status": "updated"}


@frappe.whitelist()
def snapshot_app(app_name):
    """Git-commit the target app before changes."""
    ok, msg = git_snapshot(app_name)
    if not ok:
        frappe.throw(msg)
    return {"status": "snapshotted", "message": msg}


@frappe.whitelist()
def rollback_app(app_name):
    """Rollback the target app to the last commit."""
    ok, msg = git_rollback(app_name)
    if not ok:
        frappe.throw(msg)
    return {"status": "rolled_back", "message": msg}


@frappe.whitelist()
def run_bench_command(command):
    """Run an allowed bench command."""
    allowed = {"migrate", "restart", "clear-cache", "build", "watch"}
    if command not in allowed:
        frappe.throw(_("Command '{0}' is not allowed").format(command))

    import subprocess

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
def execute_prompt(prompt_name, user_prompt=None, target_app=None, provider=None, model=None, temperature=None):
    """Execute a stored prompt against the LLM and return the response."""
    if prompt_name == "__direct__":
        # Direct execution without a stored prompt doc
        system = "You are an expert Frappe/ERPNext developer. Help build features and fix bugs."
        user = user_prompt or ""
        cfg = _get_llm_config(provider=provider, model=model, temperature=temperature)
        model = model or cfg["model"]
        temperature = temperature if temperature is not None else cfg["temperature"]
        provider = provider or cfg["provider"]
    else:
        prompt_doc = frappe.get_doc("AI Studio Prompt", prompt_name)
        system = prompt_doc.system_prompt or ""
        user = user_prompt or prompt_doc.user_prompt or ""
        model = model or prompt_doc.model or _get_llm_config()["model"]
        temperature = temperature if temperature is not None else (prompt_doc.temperature or _get_llm_config()["temperature"])
        provider = provider or prompt_doc.provider or _resolve_provider_from_model(model)

    app = target_app

    # Build context
    context = build_context(target_app=app)
    context_json = json.dumps(context, indent=2, default=str)

    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": "Bench Context:\n```json\n{}```\n\nUser Request:\n{}".format(context_json, user),
        },
    ]

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
def apply_ai_changes(app_name, changes):
    """Apply a list of AI-generated file changes atomically with snapshot + rollback."""
    if isinstance(changes, str):
        changes = json.loads(changes)

    # Pre-flight: snapshot
    snapshot_app(app_name)

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
            else:
                raise ValueError("Unknown change type: {}".format(ctype))
            applied.append(change)

        return {"status": "applied", "changes": applied}
    except Exception:
        # Auto-rollback on failure
        rollback_app(app_name)
        frappe.throw(_("Changes caused an error; rolled back to last snapshot."))


# ---------------------------------------------------------------------------
# Boot hook
# ---------------------------------------------------------------------------

def on_session_creation():
    """Inject AI Studio settings into bootinfo."""
    if hasattr(frappe.local, "boot") and frappe.local.boot:
        frappe.local.boot.ai_studio_enabled = True
