# Frappe AI Studio

A Self-Modifying Developer Agent for the Frappe Framework.

## Installation

```bash
bench get-app https://github.com/your-org/frappe-ai-studio.git
bench --site your-site.local install-app frappe_ai_studio
bench --site your-site.local migrate
```

## Features

- **Architect Chat**: Fullscreen Monaco Editor for natural-language prompt-driven development.
- **Automatic Bench Orchestrator**: Trigger `bench migrate`, `restart`, `clear-cache` programmatically.
- **Schema Wizard**: Auto-update `tabDocType` in MariaDB and generate `.json` files simultaneously.
- **Git-Safe Rollback**: Automatic commit before changes; auto-rollback on Internal Server Error.
- **Validation Layer**: Pre-flight syntax checks with `pyflakes` before saving.
- **Global Command Palette**: Floating `Cmd+K` palette accessible from any DocType.

See `frappe_ai_studio/README.md` for full documentation.
