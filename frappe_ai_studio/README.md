# Frappe AI Studio

A Self-Modifying Developer Agent for the Frappe Framework.

## Features

- **Architect Chat**: Fullscreen Monaco Editor for natural-language prompt-driven development.
- **Automatic Bench Orchestrator**: Trigger `bench migrate`, `restart`, `clear-cache` programmatically.
- **Schema Wizard**: Auto-update `tabDocType` in MariaDB and generate `.json` files simultaneously.
- **Git-Safe Rollback**: Automatic commit before changes; auto-rollback on Internal Server Error.
- **Validation Layer**: Pre-flight syntax checks with `pyflakes` before saving.
- **Global Command Palette**: Floating `Cmd+K` palette accessible from any DocType.

## Installation

```bash
bench get-app https://github.com/your-org/frappe_ai_studio.git
bench --site your-site.local install-app frappe_ai_studio
bench --site your-site.local migrate
```

## Usage

1. Open **AI Studio** from the Awesome Bar.
2. Type a prompt, e.g.:
   > "Create a new app called 'Library' and add a DocType for 'Books' with fields for title, author, and status."
3. Review the diff, confirm, and let the agent apply changes.

## Architecture

| Module | Purpose |
|--------|---------|
| `context_engine.py` | Scans `/apps`, indexes DocTypes, hooks, APIs into JSON context for the LLM. |
| `writer.py` | Handles file paths and AST-based (libcst) code updates. |
| `api.py` | Whitelisted Frappe methods: `execute_prompt`, `read_file`, `write_code`. |
| `ai_studio_page.js` | Vue 3 + Monaco Editor frontend. |
| `ai_studio_global.js` | Floating command palette injected into every DocType. |

## License

MIT
