# -*- coding: utf-8 -*-
"""Frappe AI Studio — AI developer agent for the Frappe Framework."""

from __future__ import unicode_literals

app_name = "frappe_ai_studio"
app_title = "Frappe AI Studio"
app_publisher = "Frappe AI Studio"
app_description = "An AI-powered developer agent for the Frappe Framework"
app_email = "ai@codepointcreatives.com"
app_license = "MIT"

# Frappe AI Studio only makes sense on top of the Frappe framework.
required_apps = ["frappe"]

# -----------------------------
# App Includes
# -----------------------------
app_include_js = "/assets/frappe_ai_studio/js/ai_studio_global.js"
app_include_css = "/assets/frappe_ai_studio/css/ai_studio_global.css"

# -----------------------------
# Page & Workspace
# -----------------------------
page_js = {"ai-studio": "public/js/ai_studio_page.js"}
page_css = {"ai-studio": "public/css/ai_studio_page.css"}

# -----------------------------
# Install / migrate hooks
# -----------------------------
after_install = "frappe_ai_studio.frappe_ai_studio.install.after_install"
after_migrate = "frappe_ai_studio.frappe_ai_studio.install.after_migrate"

# -----------------------------
# Scheduled Jobs (context indexing)
# -----------------------------
scheduler_events = {"hourly": ["frappe_ai_studio.frappe_ai_studio.context_engine.index_all_apps"]}

# -----------------------------
# Boot Session
# -----------------------------
on_session_creation = "frappe_ai_studio.frappe_ai_studio.api.on_session_creation"

# -----------------------------
# Fixtures
# -----------------------------
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["dt", "=", "AI Studio Prompt"]],
    },
    # Ship the dedicated role so it is available on every site.
    {
        "dt": "Role",
        "filters": [["role_name", "=", "AI Studio Manager"]],
    },
]
