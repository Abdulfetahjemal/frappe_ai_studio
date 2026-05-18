/**
 * AI Studio Global Command Palette
 *
 * Injected into every DocType via app_include_js.
 * Provides a floating Cmd+K / Ctrl+K palette to open AI Studio
 * or run quick agent actions from anywhere in the desk.
 */

frappe.provide('frappe.ai_studio');

frappe.ai_studio.GlobalPalette = class GlobalPalette {
    constructor() {
        this.isOpen = false;
        this.init();
    }

    init() {
        document.addEventListener('keydown', (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                this.toggle();
            }
            if (e.key === 'Escape' && this.isOpen) {
                this.close();
            }
        });
    }

    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }

    open() {
        if (this.isOpen) return;
        this.isOpen = true;

        const overlay = document.createElement('div');
        overlay.className = 'ai-studio-palette-overlay';
        overlay.innerHTML = `
            <div class="ai-studio-palette">
                <input type="text" class="ai-studio-palette-input" placeholder="Type a command or 'ask' to prompt the agent..." />
                <div class="ai-studio-palette-results"></div>
            </div>
        `;
        document.body.appendChild(overlay);
        this.overlay = overlay;

        const input = overlay.querySelector('.ai-studio-palette-input');
        input.focus();

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const val = input.value.trim();
                if (!val) return;
                if (val.toLowerCase().startsWith('ask ')) {
                    const prompt = val.slice(4);
                    this.close();
                    this.openStudioWithPrompt(prompt);
                } else if (val.toLowerCase() === 'studio') {
                    this.close();
                    frappe.set_route('ai-studio');
                } else {
                    this.runQuickCommand(val);
                }
            }
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) this.close();
        });
    }

    close() {
        if (!this.isOpen) return;
        this.isOpen = false;
        if (this.overlay) {
            this.overlay.remove();
            this.overlay = null;
        }
    }

    openStudioWithPrompt(prompt) {
        frappe.set_route('ai-studio');
        // After route change, populate the input (best-effort)
        setTimeout(() => {
            const app = frappe.ai_studio && frappe.ai_studio.page;
            if (app && app._instance && app._instance.refs) {
                // Vue 3 exposed refs won't be directly available; rely on global event or next tick
            }
        }, 800);
    }

    runQuickCommand(cmd) {
        frappe.show_alert(`Quick command: ${cmd}`);
        this.close();
    }
};

// Initialise once Frappe is ready
$(document).on('frappe-ready', () => {
    frappe.ai_studio.palette = new frappe.ai_studio.GlobalPalette();
});
