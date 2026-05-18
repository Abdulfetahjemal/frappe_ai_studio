# -*- coding: utf-8 -*-
"""Frappe AI Studio — Self-Modifying Developer Agent."""

from __future__ import unicode_literals

app_name = "frappe_ai_studio"
app_title = "Frappe AI Studio"
app_publisher = "Frappe AI Studio"
app_description = "A Self-Modifying Developer Agent for the Frappe Framework"
app_email = "ai@example.com"
app_license = "MIT"

# -----------------------------
# App Includes
# -----------------------------
app_include_js = "/assets/frappe_ai_studio/js/ai_studio_global.js"
app_include_css = "/assets/frappe_ai_studio/css/ai_studio_global.css"

# -----------------------------
# Website Context
# -----------------------------
website_context = {
    "favicon": "/assets/frappe_ai_studio/images/favicon.png",
    "splash_image": "/assets/frappe_ai_studio/images/splash.png",
}

# -----------------------------
# Page & Workspace
# -----------------------------
page_js = {"ai-studio": "public/js/ai_studio_page.js"}
page_css = {"ai-studio": "public/css/ai_studio_page.css"}

# -----------------------------
# Scheduled Jobs (optional indexing)
# -----------------------------
scheduler_events = {
    "hourly": [
        "frappe_ai_studio.frappe_ai_studio.context_engine.index_all_apps"
    ]
}

# -----------------------------
# Doc Events
# -----------------------------
# doc_events = {
#     "*": {
#         "on_update": "frappe_ai_studio.frappe_ai_studio.events.on_doc_update"
#     }
# }

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
    }
]
