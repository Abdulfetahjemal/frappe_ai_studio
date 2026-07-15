/**
 * AI Studio Global Command Palette
 *
 * Injected into the desk via app_include_js. A floating Cmd/Ctrl+K palette to
 * jump into AI Studio or hand a prompt straight to the agent from anywhere.
 */

frappe.provide('frappe.ai_studio');

frappe.ai_studio.PENDING_PROMPT_KEY = 'ai_studio_pending_prompt';

frappe.ai_studio.GlobalPalette = class GlobalPalette {
    constructor() {
        this.isOpen = false;
        this.init();
    }

    init() {
        document.addEventListener('keydown', (e) => {
            const key = (e.key || '').toLowerCase();
            if ((e.metaKey || e.ctrlKey) && key === 'k') {
                // Don't hijack when the user is typing in an input/textarea.
                const tag = (document.activeElement && document.activeElement.tagName) || '';
                if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;
                e.preventDefault();
                this.toggle();
            }
            if (key === 'escape' && this.isOpen) this.close();
        });
    }

    toggle() {
        this.isOpen ? this.close() : this.open();
    }

    open() {
        if (this.isOpen) return;
        this.isOpen = true;

        const overlay = document.createElement('div');
        overlay.className = 'ai-studio-palette-overlay';
        overlay.innerHTML = `
            <div class="ai-studio-palette" role="dialog" aria-label="AI Studio command palette">
                <div class="ai-studio-palette-head">
                    <i class="fa fa-magic"></i>
                    <input type="text" class="ai-studio-palette-input"
                        placeholder="Ask the agent, or type 'studio' to open AI Studio…" />
                </div>
                <div class="ai-studio-palette-hint">
                    Press <kbd>Enter</kbd> to send · <kbd>Esc</kbd> to close
                </div>
            </div>`;
        document.body.appendChild(overlay);
        this.overlay = overlay;

        const input = overlay.querySelector('.ai-studio-palette-input');
        input.focus();

        input.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;
            const val = input.value.trim();
            if (!val) return;
            if (val.toLowerCase() === 'studio') {
                this.close();
                frappe.set_route('ai-studio');
            } else {
                const prompt = val.toLowerCase().startsWith('ask ') ? val.slice(4) : val;
                this.openStudioWithPrompt(prompt);
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
        // Stash the prompt so the AI Studio page can pick it up on load.
        try {
            sessionStorage.setItem(frappe.ai_studio.PENDING_PROMPT_KEY, prompt);
        } catch (e) {
            // sessionStorage may be unavailable; fall back to an in-memory value.
            frappe.ai_studio._pending_prompt = prompt;
        }
        this.close();

        // If the studio is already open, populate immediately.
        if (frappe.get_route_str() === 'ai-studio' && frappe.ai_studio.page) {
            frappe.ai_studio.consume_pending_prompt();
        } else {
            frappe.set_route('ai-studio');
        }
    }
};

// Called by the AI Studio page once it has initialised.
frappe.ai_studio.consume_pending_prompt = function () {
    let prompt = frappe.ai_studio._pending_prompt || null;
    try {
        prompt = prompt || sessionStorage.getItem(frappe.ai_studio.PENDING_PROMPT_KEY);
        sessionStorage.removeItem(frappe.ai_studio.PENDING_PROMPT_KEY);
    } catch (e) {
        /* ignore */
    }
    frappe.ai_studio._pending_prompt = null;

    const page = frappe.ai_studio.page;
    if (prompt && page && page.prompt_input) {
        page.prompt_input.val(prompt);
        if (page.autogrow) page.autogrow();
        page.prompt_input.focus();
    }
};

$(document).on('frappe-ready', () => {
    frappe.ai_studio.palette = new frappe.ai_studio.GlobalPalette();
});
