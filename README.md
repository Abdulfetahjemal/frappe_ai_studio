# Frappe AI Studio

An AI-powered developer agent for the [Frappe Framework](https://frappeframework.com). Use natural language to create DocTypes, write code, customize existing apps, and orchestrate your bench — with built-in validation, git safety, and multi-provider LLM support.

![Frappe Version](https://img.shields.io/badge/Frappe-v15+-blue)
![ERPNext Version](https://img.shields.io/badge/ERPNext-v15+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Natural Language Development** — Describe what you want in plain English and let the AI generate DocTypes, controllers, client scripts, and more.
- **Multi-Provider LLM Support** — Works with OpenAI, Anthropic, Google Gemini, DeepSeek, Groq, Azure OpenAI, Cohere, Mistral, Together AI, Perplexity, OpenRouter, and Moonshot AI (Kimi).
- **Core App Customization** — Safely customize Frappe and ERPNext using Custom Fields and Property Setters without modifying core files.
- **Git-Safe Changes** — Automatic snapshot before file changes; one-click rollback if something goes wrong.
- **Schema Wizard** — Create and sync DocTypes with automatic JSON generation and database migration.
- **Syntax Validation** — Pre-flight Python syntax checks with `pyflakes` before saving any code.
- **Interactive File Browser** — Browse your app's file tree and inspect files directly in the chat interface.
- **Conversation History** — Multi-turn chat with the AI, keeping context across your development session.
- **Global Command Palette** — Quick-access floating palette (`Cmd+K`) from any DocType page.

## Installation

```bash
bench get-app https://github.com/your-org/frappe-ai-studio.git
bench --site your-site.local install-app frappe_ai_studio
bench --site your-site.local migrate
```

## Setup

1. Go to **AI Studio Settings** (search from the Awesome Bar).
2. Select your preferred LLM provider and enter your API key.
3. Choose a default model (e.g., `gpt-4o`, `claude-3-7-sonnet`, `gemini-2.5-pro`).
4. Save and open **AI Studio** from the Awesome Bar.

## Usage

1. **Select a target app** from the dropdown (e.g., your custom app or `erpnext` for core customizations).
2. **Type a prompt**, e.g.:
   > "Create a DocType called Library Member with fields for name, email, phone, and membership status"
3. **Review the diff** — The AI generates a preview of all changes before applying.
4. **Confirm** — Click Apply to execute changes. For custom apps, a git snapshot is taken automatically.

### Customizing Core Apps

When targeting `frappe` or `erpnext`, the AI automatically uses safe customization patterns:
- **Custom Fields** — Add new fields to existing DocTypes
- **Property Setters** — Modify labels, defaults, visibility, etc.
- **Server Scripts** — Inject custom business logic

Core app files are never modified directly.

## Architecture

| Module | Purpose |
|--------|---------|
| `api.py` | Whitelisted Frappe API methods: `execute_prompt`, `apply_ai_changes`, `preview_changes` |
| `context_engine.py` | Scans bench apps, indexes DocTypes, hooks, APIs into JSON context for the LLM |
| `writer.py` | Secure file I/O, AST-based code injection, git snapshot/rollback |
| `schema_wizard.py` | DocType JSON generation, database sync, bench orchestration |
| `ai_studio_page.js` | Interactive frontend with chat, file browser, diff preview |
| `ai_studio_global.js` | Floating command palette injected into every DocType |

## Supported LLM Providers

- OpenAI (GPT-4o, o3-mini, etc.)
- Anthropic (Claude 3.7 Sonnet, etc.)
- Google Gemini (2.5 Pro, 2.5 Flash, etc.)
- DeepSeek (Chat, Coder, Reasoner)
- Groq (Llama, Mixtral, Gemma)
- Azure OpenAI
- Cohere
- Mistral AI
- Together AI
- Perplexity
- OpenRouter
- Moonshot AI (Kimi)

## Testing

```bash
cd frappe_ai_studio
python -m unittest discover -s frappe_ai_studio/tests -p "test_*.py" -v
```

## License

MIT
