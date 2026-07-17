/**
 * AI Studio Page — AI development environment for Frappe.
 *
 * Backend contract is unchanged; this is a UI/UX rewrite that adds a staged
 * progress pipeline, richer message rendering, example prompts, an auto-growing
 * composer and a cleaner, theme-aware, responsive layout.
 */

frappe.provide('frappe.ai_studio');

const AS_STAGES = ['Pending', 'In Progress', 'Linting', 'Testing', 'Completed'];

const AS_EXAMPLES = [
    { icon: 'fa-rocket', text: 'Scaffold a new app "library_management" and install it, with a Library Loan DocType' },
    { icon: 'fa-random', text: 'Add a Draft → Approved → Rejected workflow to Library Loan with a Library Manager role' },
    { icon: 'fa-th-large', text: 'Build a "Library" workspace with shortcuts and a Loans-by-status chart' },
    { icon: 'fa-bar-chart', text: 'Create an "Overdue Loans" query report and a daily due-date notification' },
];

frappe.ai_studio.AIStudioPage = class AIStudioPage {
    constructor(page) {
        this.page = page;
        this.wrapper = page.body;
        this.settings = {};
        this.current_provider = 'OpenAI';
        this.current_model = 'gpt-4o';
        this.temperature = 0.2;
        this.target_app = null;
        this.installed_apps = [];
        this.conversation_history = [];
        this.messages = [];
        this.loading = false;
        this.pollInterval = null;
        this.current_task = null;

        this.setup_page();
        this.load_settings();
        this.load_installed_apps();

        // Pick up a prompt handed over from the global command palette.
        if (frappe.ai_studio && frappe.ai_studio.consume_pending_prompt) {
            frappe.ai_studio.consume_pending_prompt();
        }
    }

    // ---------------------------------------------------------------- layout
    setup_page() {
        this.wrapper.innerHTML = '';

        const providers = [
            'OpenAI', 'Anthropic', 'Google Gemini', 'Moonshot AI (Kimi)', 'DeepSeek',
            'Groq', 'Azure OpenAI', 'Cohere', 'Mistral AI', 'Together AI', 'Perplexity', 'OpenRouter',
        ];
        const provider_options = providers
            .map((p) => `<option value="${p}">${p}</option>`)
            .join('');

        const pipeline = AS_STAGES
            .map(
                (s, i) =>
                    `<div class="as-stage" data-stage="${s}"><span class="as-dot"></span><span>${s}</span></div>` +
                    (i < AS_STAGES.length - 1 ? '<span class="as-sep"></span>' : '')
            )
            .join('');

        const layout = $(`
            <div class="ai-studio-layout">
                <aside class="ai-studio-sidebar">
                    <div class="as-brand"><span class="as-logo"><i class="fa fa-magic"></i></span> AI Studio</div>

                    <div class="as-group">
                        <div class="as-group-title">Model</div>
                        <div class="as-field">
                            <label>Provider</label>
                            <select class="form-control provider-select">${provider_options}</select>
                        </div>
                        <div class="as-field">
                            <label>Model</label>
                            <select class="form-control model-select"></select>
                        </div>
                        <div class="as-field">
                            <label>Target App</label>
                            <select class="form-control target-app-select"><option value="">All Apps</option></select>
                        </div>
                        <div class="as-field">
                            <label>Temperature: <span class="temp-value">0.2</span></label>
                            <input type="range" class="form-control temperature-slider" min="0" max="2" step="0.1" value="0.2">
                        </div>
                    </div>

                    <div class="as-group">
                        <div class="as-group-title">API Key <span class="as-key-status"></span></div>
                        <div class="as-field as-apikey-wrap">
                            <input type="password" class="form-control api-key-input" placeholder="Enter API key…">
                            <button class="as-toggle-key" title="Show/Hide"><i class="fa fa-eye"></i></button>
                        </div>
                        <button class="btn btn-sm btn-primary btn-save-settings" style="width:100%;">Save Settings</button>
                    </div>

                    <div class="as-group as-bench-btns">
                        <div class="as-group-title">Bench</div>
                        <button class="btn btn-sm btn-default btn-migrate"><i class="fa fa-database"></i> migrate</button>
                        <button class="btn btn-sm btn-default btn-restart"><i class="fa fa-refresh"></i> restart</button>
                        <button class="btn btn-sm btn-default btn-clear-cache"><i class="fa fa-eraser"></i> clear-cache</button>
                        <button class="btn btn-sm btn-default btn-build"><i class="fa fa-wrench"></i> build</button>
                    </div>

                    <div class="as-group as-actions">
                        <button class="btn btn-sm btn-default btn-clear-chat"><i class="fa fa-trash-o"></i> Clear conversation</button>
                    </div>
                </aside>

                <section class="ai-studio-main">
                    <div class="as-pipeline">${pipeline}</div>
                    <div class="ai-studio-chat"></div>
                    <div class="ai-studio-composer">
                        <div class="as-composer-row">
                            <textarea class="prompt-input" rows="1" placeholder="Describe what you want to build…"></textarea>
                            <button class="btn btn-primary as-send-btn btn-send"><i class="fa fa-paper-plane"></i></button>
                        </div>
                        <div class="as-composer-hint">Enter to send · Shift+Enter for a new line</div>
                    </div>
                </section>
            </div>
        `).appendTo(this.wrapper);

        this.chat_container = layout.find('.ai-studio-chat');
        this.pipeline_el = layout.find('.as-pipeline');
        this.prompt_input = layout.find('.prompt-input');
        this.send_btn = layout.find('.btn-send');
        this.provider_select = layout.find('.provider-select');
        this.model_select = layout.find('.model-select');
        this.target_app_select = layout.find('.target-app-select');
        this.temp_slider = layout.find('.temperature-slider');
        this.temp_value = layout.find('.temp-value');
        this.api_key_input = layout.find('.api-key-input');
        this.api_key_status = layout.find('.as-key-status');

        this.render_welcome();
        this.update_model_options();
        this.bind_events();
    }

    render_welcome() {
        const examples = AS_EXAMPLES.map(
            (e) =>
                `<button class="as-example" data-prompt="${frappe.utils.escape_html(e.text)}">
                    <i class="fa ${e.icon} as-example-icon"></i>${frappe.utils.escape_html(e.text)}
                </button>`
        ).join('');

        $(`
            <div class="as-welcome">
                <div class="as-welcome-icon"><i class="fa fa-magic"></i></div>
                <h3>What would you like to build?</h3>
                <p>Describe a DocType, field, script or customization in plain English.</p>
                <p>The agent has full context of your bench and stages every change for your review before deploying.</p>
                <div class="as-examples">${examples}</div>
            </div>
        `).appendTo(this.chat_container);

        this.chat_container.find('.as-example').on('click', (e) => {
            this.prompt_input.val($(e.currentTarget).data('prompt'));
            this.autogrow();
            this.prompt_input.focus();
        });
    }

    bind_events() {
        this.send_btn.on('click', () => this.send_prompt());
        this.prompt_input.on('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.send_prompt();
            }
        });
        this.prompt_input.on('input', () => this.autogrow());

        this.wrapper.find('.btn-migrate').on('click', () => this.run_bench('migrate'));
        this.wrapper.find('.btn-restart').on('click', () => this.run_bench('restart'));
        this.wrapper.find('.btn-clear-cache').on('click', () => this.run_bench('clear-cache'));
        this.wrapper.find('.btn-build').on('click', () => this.run_bench('build'));

        this.provider_select.on('change', (e) => {
            this.current_provider = e.target.value;
            this.update_model_options();
            this.current_model = this.model_select.val();
        });
        this.model_select.on('change', (e) => (this.current_model = e.target.value));
        this.target_app_select.on('change', (e) => (this.target_app = e.target.value || null));
        this.temp_slider.on('input', (e) => {
            this.temperature = parseFloat(e.target.value);
            this.temp_value.text(this.temperature.toFixed(1));
        });

        this.wrapper.find('.as-toggle-key').on('click', (e) => {
            e.preventDefault();
            const icon = $(e.currentTarget).find('i');
            if (this.api_key_input.attr('type') === 'password') {
                this.api_key_input.attr('type', 'text');
                icon.removeClass('fa-eye').addClass('fa-eye-slash');
            } else {
                this.api_key_input.attr('type', 'password');
                icon.removeClass('fa-eye-slash').addClass('fa-eye');
            }
        });

        this.wrapper.find('.btn-save-settings').on('click', () => this.save_settings());
        this.wrapper.find('.btn-clear-chat').on('click', () => this.clear_chat());
    }

    autogrow() {
        const el = this.prompt_input[0];
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    }

    // ------------------------------------------------------------- pipeline
    set_pipeline(stage) {
        this.pipeline_el.addClass('active');
        const order = AS_STAGES.indexOf(stage === 'Failed' ? 'Testing' : stage);
        this.pipeline_el.find('.as-stage').each((_, el) => {
            const s = $(el);
            const idx = AS_STAGES.indexOf(s.data('stage'));
            s.removeClass('done active failed');
            if (stage === 'Failed' && idx === order) s.addClass('failed');
            else if (idx < order) s.addClass('done');
            else if (idx === order) s.addClass('active');
        });
    }
    hide_pipeline() {
        this.pipeline_el.removeClass('active');
    }

    // -------------------------------------------------------------- models
    get_provider_models() {
        return {
            OpenAI: [
                { value: 'gpt-4o', label: 'GPT-4o' },
                { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
                { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
                { value: 'gpt-4', label: 'GPT-4' },
                { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
                { value: 'o1-preview', label: 'o1 Preview' },
                { value: 'o1-mini', label: 'o1 Mini' },
                { value: 'o3-mini', label: 'o3 Mini' },
            ],
            Anthropic: [
                { value: 'claude-3-7-sonnet-20250219', label: 'Claude 3.7 Sonnet' },
                { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet' },
                { value: 'claude-3-5-sonnet-latest', label: 'Claude 3.5 Sonnet (Latest)' },
                { value: 'claude-3-opus-20240229', label: 'Claude 3 Opus' },
                { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku' },
            ],
            'Google Gemini': [
                { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
                { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
                { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
                { value: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro' },
                { value: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
            ],
            'Moonshot AI (Kimi)': [
                { value: 'kimi-moonshot-v1-8k', label: 'Kimi v1 8K' },
                { value: 'kimi-moonshot-v1-32k', label: 'Kimi v1 32K' },
                { value: 'kimi-moonshot-v1-128k', label: 'Kimi v1 128K' },
                { value: 'kimi-k1.5', label: 'Kimi K1.5' },
            ],
            DeepSeek: [
                { value: 'deepseek-chat', label: 'DeepSeek Chat' },
                { value: 'deepseek-coder', label: 'DeepSeek Coder' },
                { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner' },
            ],
            Groq: [
                { value: 'groq-llama-3.3-70b-versatile', label: 'Llama 3.3 70B' },
                { value: 'groq-llama-3.1-8b-instant', label: 'Llama 3.1 8B' },
                { value: 'groq-mixtral-8x7b-32768', label: 'Mixtral 8x7B' },
            ],
            'Azure OpenAI': [
                { value: 'azure-gpt-4o', label: 'Azure GPT-4o' },
                { value: 'azure-gpt-4-turbo', label: 'Azure GPT-4 Turbo' },
            ],
            Cohere: [
                { value: 'cohere-command-r', label: 'Command R' },
                { value: 'cohere-command-r-plus', label: 'Command R+' },
            ],
            'Mistral AI': [
                { value: 'mistral-large-latest', label: 'Mistral Large' },
                { value: 'mistral-small-latest', label: 'Mistral Small' },
                { value: 'mistral-codestral-latest', label: 'Codestral' },
            ],
            'Together AI': [
                { value: 'together-llama-3.3-70b', label: 'Llama 3.3 70B' },
                { value: 'together-qwen2.5-72b', label: 'Qwen 2.5 72B' },
            ],
            Perplexity: [
                { value: 'perplexity-sonar', label: 'Sonar' },
                { value: 'perplexity-sonar-pro', label: 'Sonar Pro' },
            ],
            OpenRouter: [
                { value: 'openrouter-anthropic-claude-3.5-sonnet', label: 'Claude 3.5 Sonnet' },
                { value: 'openrouter-meta-llama-3.3-70b', label: 'Llama 3.3 70B' },
            ],
        };
    }

    update_model_options() {
        const models = this.get_provider_models();
        const list = models[this.current_provider] || models['OpenAI'];
        this.model_select.empty();
        list.forEach((m) => {
            this.model_select.append(
                $('<option>').val(m.value).text(m.label)
            );
        });
        const values = list.map((m) => m.value);
        if (this.current_model && !values.includes(this.current_model)) {
            this.model_select.append($('<option>').val(this.current_model).text(this.current_model));
        }
        this.model_select.val(this.current_model);
    }

    // ------------------------------------------------------------- settings
    async load_settings() {
        try {
            const r = await frappe.call({ method: 'frappe_ai_studio.frappe_ai_studio.api.get_ai_studio_settings' });
            if (!r.message) return;
            this.settings = r.message;
            this.current_provider = r.message.default_provider || 'OpenAI';
            this.current_model = r.message.default_model || 'gpt-4o';
            this.temperature = r.message.temperature || 0.2;

            this.provider_select.val(this.current_provider);
            this.update_model_options();
            this.temp_slider.val(this.temperature);
            this.temp_value.text(Number(this.temperature).toFixed(1));

            if (r.message.has_api_key) {
                this.api_key_status.text('· saved').removeClass('missing').addClass('ok');
                this.api_key_input.attr('placeholder', 'Saved — enter new to replace');
            } else {
                this.api_key_status.text('· not set').removeClass('ok').addClass('missing');
            }
        } catch (err) {
            console.warn('AI Studio: could not load settings', err);
        }
    }

    async load_installed_apps() {
        try {
            const r = await frappe.call({ method: 'frappe_ai_studio.frappe_ai_studio.api.get_installed_apps' });
            if (!r.message) return;
            this.installed_apps = r.message;
            this.target_app_select.empty().append($('<option>').val('').text('All Apps'));
            this.installed_apps.forEach((app) =>
                this.target_app_select.append($('<option>').val(app).text(app))
            );
        } catch (err) {
            console.warn('AI Studio: could not load apps', err);
        }
    }

    async save_settings() {
        try {
            const settings = {
                default_provider: this.current_provider,
                default_model: this.current_model,
                temperature: this.temperature,
                api_key: this.api_key_input.val().trim(),
                enabled_models: [],
            };
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.save_ai_studio_settings',
                args: { settings_json: JSON.stringify(settings) },
            });
            if (r.message && r.message.status === 'saved') {
                frappe.show_alert({ message: 'Settings saved', indicator: 'green' });
                this.api_key_input.val('');
                this.load_settings();
            }
        } catch (err) {
            frappe.show_alert({ message: 'Failed to save: ' + (err.message || 'Error'), indicator: 'red' });
        }
    }

    // -------------------------------------------------------------- messages
    append_message(role, text, opts = {}) {
        this.chat_container.find('.as-welcome').remove();
        this.messages.push({ role, text });

        const avatars = { user: 'fa-user', assistant: 'fa-magic', system: 'fa-info' };
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const body = opts.raw ? text : this.format_text(text);

        const el = $(`
            <div class="as-msg ${role}">
                <div class="as-avatar"><i class="fa ${avatars[role] || 'fa-info'}"></i></div>
                <div class="as-bubble">
                    <div class="as-meta">${role} · ${time}</div>
                    <div class="as-content">${body}</div>
                </div>
            </div>
        `).appendTo(this.chat_container);

        this.scroll_bottom();
        return el;
    }

    show_typing() {
        this.remove_typing();
        this.typing_el = $(`
            <div class="as-msg assistant as-typing-row">
                <div class="as-avatar"><i class="fa fa-magic"></i></div>
                <div class="as-bubble"><div class="as-typing"><span></span><span></span><span></span></div></div>
            </div>
        `).appendTo(this.chat_container);
        this.scroll_bottom();
    }
    remove_typing() {
        if (this.typing_el) {
            this.typing_el.remove();
            this.typing_el = null;
        }
    }

    format_text(text) {
        let out = frappe.utils.escape_html(text);
        out = out.replace(/```(\w*)\n?([\s\S]*?)```/g, (m, lang, code) => {
            return '<pre><code>' + code.replace(/\n$/, '') + '</code></pre>';
        });
        out = out.replace(/`([^`\n]+)`/g, '<code>$1</code>');
        out = out.replace(/\n/g, '<br>');
        return out;
    }

    scroll_bottom() {
        this.chat_container.scrollTop(this.chat_container[0].scrollHeight);
    }

    clear_chat() {
        if (this.pollInterval) clearInterval(this.pollInterval);
        this.pollInterval = null;
        this.loading = false;
        this.current_task = null;
        this.messages = [];
        this.conversation_history = [];
        this.wrapper.find('.as-action-bar').remove();
        this.hide_pipeline();
        this.set_send_state(false);
        this.chat_container.empty();
        this.render_welcome();
    }

    set_send_state(loading) {
        this.loading = loading;
        this.send_btn.prop('disabled', loading);
        this.send_btn.html(loading ? '<i class="fa fa-circle-o-notch fa-spin"></i>' : '<i class="fa fa-paper-plane"></i>');
        this.prompt_input.prop('disabled', loading);
    }

    // --------------------------------------------------------------- prompt
    async send_prompt() {
        const text = (this.prompt_input.val() || '').trim();
        if (!text || this.loading) return;

        this.append_message('user', text);
        this.prompt_input.val('');
        this.autogrow();
        this.set_send_state(true);
        this.wrapper.find('.as-action-bar').remove();
        this.show_typing();
        this.set_pipeline('Pending');

        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.execute_prompt_async',
                args: {
                    user_prompt: text,
                    provider: this.current_provider,
                    model: this.current_model,
                    temperature: this.temperature,
                    target_app: this.target_app,
                    conversation_history: JSON.stringify(this.conversation_history),
                },
            });
            if (r.message && r.message.status === 'queued') {
                this.track_task(r.message.task_id, text);
            } else {
                this.fail_turn('Unexpected response from agent.');
            }
        } catch (err) {
            this.fail_turn('Error: ' + (err.message || 'Request failed'));
        }
    }

    fail_turn(msg) {
        this.remove_typing();
        this.set_send_state(false);
        this.hide_pipeline();
        this.append_message('system', msg);
    }

    track_task(taskId, originalPrompt) {
        frappe.realtime.on('ai_generation_progress', (data) => {
            if (data.task_id === taskId) this.update_task_status(data, originalPrompt);
        });
        this.pollInterval = setInterval(() => this.poll_task_status(taskId, originalPrompt), 2500);
    }

    async poll_task_status(taskId, originalPrompt) {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.get_task_status',
                args: { task_name: taskId },
            });
            if (r.message) this.update_task_status(r.message, originalPrompt);
        } catch (err) {
            console.warn('poll error', err);
        }
    }

    stop_polling() {
        if (this.pollInterval) clearInterval(this.pollInterval);
        this.pollInterval = null;
    }

    update_task_status(data, originalPrompt) {
        const status = data.status;
        if (['Pending', 'In Progress', 'Linting', 'Testing'].includes(status)) {
            this.set_pipeline(status);
            return;
        }

        if (status === 'Completed') {
            this.stop_polling();
            this.remove_typing();
            this.set_pipeline('Completed');
            this.set_send_state(false);

            if (data.ai_response) {
                this.append_message('assistant', data.ai_response);
                this.current_task = data;
                const has_changes = !!(data.changes_payload && data.changes_payload !== 'null');
                if (has_changes) {
                    this.show_action_bar(data.task_id);
                } else {
                    this.hide_pipeline();
                }
                if (originalPrompt) {
                    this.conversation_history.push({ role: 'user', content: originalPrompt });
                    this.conversation_history.push({ role: 'assistant', content: data.ai_response });
                    if (this.conversation_history.length > 20) {
                        this.conversation_history = this.conversation_history.slice(-20);
                    }
                }
            }
            setTimeout(() => this.hide_pipeline(), 1200);
        } else if (status === 'Failed') {
            this.stop_polling();
            this.remove_typing();
            this.set_pipeline('Failed');
            this.set_send_state(false);
            const trace = (data.error_trace || 'Unknown error').split('\n').slice(-4).join('\n');
            this.append_message('system', 'Generation failed:\n```\n' + trace + '\n```');
        } else if (status === 'Rolled Back') {
            this.stop_polling();
            this.remove_typing();
            this.set_send_state(false);
            this.hide_pipeline();
            this.append_message('system', 'Changes were rolled back.');
        }
    }

    show_action_bar(taskId) {
        this.wrapper.find('.as-action-bar').remove();
        const bar = $(`
            <div class="as-action-bar">
                <span class="as-ab-label"><i class="fa fa-shield"></i> Changes are staged and validated. Review, then deploy.</span>
                <button class="btn btn-xs btn-default btn-preview"><i class="fa fa-eye"></i> Preview</button>
                <button class="btn btn-xs btn-success btn-approve"><i class="fa fa-rocket"></i> Deploy</button>
                <button class="btn btn-xs btn-danger btn-reject"><i class="fa fa-times"></i> Discard</button>
            </div>
        `).insertBefore(this.wrapper.find('.ai-studio-composer'));

        bar.find('.btn-preview').on('click', () => this.preview_changes());
        bar.find('.btn-approve').on('click', () => {
            this.approve_task(taskId);
            bar.remove();
        });
        bar.find('.btn-reject').on('click', () => {
            this.reject_task(taskId);
            bar.remove();
        });
    }

    // --------------------------------------------------------- deploy/reject
    async approve_task(taskId) {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.approve_task',
                args: { task_name: taskId },
            });
            if (r.message && r.message.status === 'deployed') {
                frappe.show_alert({ message: 'Changes deployed', indicator: 'green' });
                this.append_message('system', 'Changes deployed successfully.');
            }
        } catch (err) {
            this.append_message('system', 'Deploy failed: ' + (err.message || 'Error'));
        }
        this.current_task = null;
    }

    async reject_task(taskId) {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.reject_task',
                args: { task_name: taskId },
            });
            if (r.message && r.message.status === 'rolled_back') {
                frappe.show_alert({ message: 'Changes discarded', indicator: 'orange' });
                this.append_message('system', 'Changes discarded.');
            }
        } catch (err) {
            this.append_message('system', 'Discard failed: ' + (err.message || 'Error'));
        }
        this.current_task = null;
    }

    parse_last_payload() {
        const last = [...this.messages].reverse().find((m) => m.role === 'assistant');
        if (!last) return null;
        try {
            const m = last.text.match(/```json\s*\n?([\s\S]*?)```/);
            return JSON.parse(m ? m[1] : last.text);
        } catch {
            return null;
        }
    }

    async preview_changes() {
        const payload = this.parse_last_payload();
        if (!payload || !payload.app_name || !payload.changes) {
            frappe.show_alert({ message: 'Nothing to preview', indicator: 'orange' });
            return;
        }
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.preview_changes',
                args: { app_name: payload.app_name, changes: JSON.stringify(payload.changes) },
            });
            if (r.message && r.message.status === 'preview') {
                let html = '<div style="max-height:420px;overflow-y:auto;">';
                r.message.preview.forEach((item) => {
                    html +=
                        '<div style="margin-bottom:12px;border:1px solid var(--border-color);border-radius:6px;padding:10px;">' +
                        '<strong>' + frappe.utils.escape_html(item.type) + '</strong> ' +
                        '<span style="color:var(--text-muted);">' + frappe.utils.escape_html(item.relative_path || '') + '</span>' +
                        '<pre style="margin-top:6px;font-size:11px;background:var(--gray-100);padding:8px;border-radius:4px;max-height:220px;overflow:auto;">' +
                        frappe.utils.escape_html(item.preview) + '</pre></div>';
                });
                html += '</div>';
                const d = new frappe.ui.Dialog({
                    title: 'Preview changes — ' + payload.app_name,
                    fields: [{ fieldtype: 'HTML', fieldname: 'preview' }],
                });
                d.fields_dict.preview.$wrapper.html(html);
                d.show();
            }
        } catch (err) {
            frappe.show_alert({ message: 'Preview failed: ' + (err.message || 'Error'), indicator: 'red' });
        }
    }

    // ---------------------------------------------------------------- bench
    async run_bench(cmd) {
        frappe.confirm(`Run <b>bench ${cmd}</b> on this site?`, async () => {
            try {
                const r = await frappe.call({
                    method: 'frappe_ai_studio.frappe_ai_studio.api.run_bench_command',
                    args: { command: cmd },
                });
                this.append_message('system', `bench ${cmd}:\n\`\`\`\n${(r.message && r.message.output) || 'Done'}\n\`\`\``);
            } catch (err) {
                this.append_message('system', `bench ${cmd} failed: ` + (err.message || 'Error'));
            }
        });
    }
};

frappe.pages['ai-studio'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'AI Studio',
        single_column: true,
    });
    frappe.ai_studio.page = new frappe.ai_studio.AIStudioPage(page);
};
