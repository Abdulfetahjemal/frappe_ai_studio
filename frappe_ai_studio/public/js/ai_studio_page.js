/**
 * AI Studio Page — Full-featured AI development environment for Frappe
 */

frappe.provide('frappe.ai_studio');

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
        this.setup_page();
        this.load_settings();
        this.load_installed_apps();
    }

    setup_page() {
        this.wrapper.innerHTML = '';

        const layout = $(`
            <div class="ai-studio-layout" style="display:flex;height:calc(100vh - 120px);">
                <div class="ai-studio-sidebar" style="width:280px;padding:15px;border-right:1px solid var(--border-color);background:var(--card-bg);overflow-y:auto;">
                    <h5 style="margin-bottom:15px;">AI Studio</h5>
                    
                    <div class="settings-section" style="margin-bottom:20px;">
                        <h6 style="font-size:12px;text-transform:uppercase;color:var(--text-muted);margin-bottom:10px;">Model Settings</h6>
                        
                        <div class="form-group">
                            <label style="font-size:11px;">Provider</label>
                            <select class="form-control provider-select" style="font-size:12px;">
                                <option value="OpenAI">OpenAI</option>
                                <option value="Anthropic">Anthropic</option>
                                <option value="Google Gemini">Google Gemini</option>
                                <option value="Moonshot AI (Kimi)">Moonshot AI (Kimi)</option>
                                <option value="DeepSeek">DeepSeek</option>
                                <option value="Groq">Groq</option>
                                <option value="Azure OpenAI">Azure OpenAI</option>
                                <option value="Cohere">Cohere</option>
                                <option value="Mistral AI">Mistral AI</option>
                                <option value="Together AI">Together AI</option>
                                <option value="Perplexity">Perplexity</option>
                                <option value="OpenRouter">OpenRouter</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label style="font-size:11px;">Model</label>
                            <select class="form-control model-select" style="font-size:12px;"></select>
                        </div>
                        
                        <div class="form-group">
                            <label style="font-size:11px;">Target App</label>
                            <select class="form-control target-app-select" style="font-size:12px;">
                                <option value="">All Apps</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label style="font-size:11px;">Temperature: <span class="temp-value">0.2</span></label>
                            <input type="range" class="form-control temperature-slider" min="0" max="2" step="0.1" value="0.2" style="font-size:12px;">
                        </div>
                        
                        <div class="form-group api-key-group" style="margin-top:10px;">
                            <label style="font-size:11px;">
                                API Key 
                                <span class="api-key-status" style="font-size:10px;color:var(--text-muted);"></span>
                            </label>
                            <div style="position:relative;">
                                <input type="password" class="form-control api-key-input" placeholder="Enter API key..." style="font-size:12px;padding-right:30px;">
                                <button class="btn btn-xs btn-default toggle-api-key" style="position:absolute;right:2px;top:2px;padding:2px 6px;font-size:10px;" title="Show/Hide">
                                    <i class="fa fa-eye"></i>
                                </button>
                            </div>
                            <small class="api-key-hint" style="font-size:10px;color:var(--text-muted);display:block;margin-top:3px;">
                                Key is stored securely in AI Studio Settings
                            </small>
                        </div>
                        
                        <button class="btn btn-sm btn-outline-primary w-100 btn-save-settings" style="margin-top:10px;">Save Settings</button>
                    </div>

                    <div class="file-browser-section" style="margin-bottom:20px;display:none;">
                        <h6 style="font-size:12px;text-transform:uppercase;color:var(--text-muted);margin-bottom:10px;">File Browser</h6>
                        <div class="file-tree" style="font-size:11px;max-height:200px;overflow-y:auto;border:1px solid var(--border-color);border-radius:4px;padding:8px;"></div>
                    </div>

                    <div class="bench-section" style="margin-bottom:20px;">
                        <h6 style="font-size:12px;text-transform:uppercase;color:var(--text-muted);margin-bottom:10px;">Bench Commands</h6>
                        <div class="btn-group-vertical w-100 mb-3">
                            <button class="btn btn-sm btn-outline-secondary btn-migrate">bench migrate</button>
                            <button class="btn btn-sm btn-outline-secondary btn-restart">bench restart</button>
                            <button class="btn btn-sm btn-outline-secondary btn-clear-cache">bench clear-cache</button>
                            <button class="btn btn-sm btn-outline-secondary btn-build">bench build</button>
                        </div>
                    </div>
                    
                    <button class="btn btn-sm btn-primary w-100 btn-apply" disabled>Apply Last Changes</button>
                    <button class="btn btn-sm btn-outline-secondary w-100 btn-preview" style="margin-top:5px;display:none;">Preview Changes</button>
                    <button class="btn btn-sm btn-outline-danger w-100 btn-clear-chat" style="margin-top:5px;">Clear Chat</button>
                </div>
                <div class="ai-studio-main" style="flex:1;display:flex;flex-direction:column;padding:15px;">
                    <div class="ai-studio-chat" style="flex:1;overflow-y:auto;border:1px solid var(--border-color);border-radius:8px;padding:15px;margin-bottom:15px;background:var(--card-bg);">
                        <div class="chat-welcome" style="text-align:center;color:var(--text-muted);padding:40px;">
                            <h4>Welcome to AI Studio</h4>
                            <p>Describe what you want to build and the AI agent will help you.</p>
                            <p style="font-size:12px;">Select your preferred model from the sidebar and start prompting!</p>
                            <p style="font-size:11px;margin-top:10px;">
                                The AI has full context of your Frappe bench including all apps, DocTypes, controllers, JS files, and templates.
                            </p>
                        </div>
                    </div>
                    <div class="ai-studio-input" style="display:flex;gap:10px;">
                        <input type="text" class="form-control prompt-input" placeholder="Describe what you want to build..." />
                        <button class="btn btn-primary btn-send" style="min-width:80px;">Send</button>
                    </div>
                    <div class="ai-studio-editor" style="margin-top:15px;height:200px;border:1px solid var(--border-color);border-radius:8px;">
                        <textarea class="form-control code-editor" style="width:100%;height:100%;font-family:monospace;resize:none;border:none;" placeholder="// Code output will appear here..."></textarea>
                    </div>
                </div>
            </div>
        `).appendTo(this.wrapper);

        this.chat_container = layout.find('.ai-studio-chat');
        this.prompt_input = layout.find('.prompt-input');
        this.send_btn = layout.find('.btn-send');
        this.apply_btn = layout.find('.btn-apply');
        this.preview_btn = layout.find('.btn-preview');
        this.code_editor = layout.find('.code-editor');
        this.provider_select = layout.find('.provider-select');
        this.model_select = layout.find('.model-select');
        this.target_app_select = layout.find('.target-app-select');
        this.temp_slider = layout.find('.temperature-slider');
        this.temp_value = layout.find('.temp-value');
        this.api_key_input = layout.find('.api-key-input');
        this.api_key_status = layout.find('.api-key-status');
        this.file_tree_container = layout.find('.file-tree');
        this.file_browser_section = layout.find('.file-browser-section');

        this.bind_events();
    }

    bind_events() {
        this.send_btn.on('click', () => this.send_prompt());
        this.prompt_input.on('keydown', (e) => {
            if (e.key === 'Enter') this.send_prompt();
        });
        this.apply_btn.on('click', () => this.apply_changes());
        this.preview_btn.on('click', () => this.preview_changes());
        
        this.wrapper.find('.btn-migrate').on('click', () => this.run_bench('migrate'));
        this.wrapper.find('.btn-restart').on('click', () => this.run_bench('restart'));
        this.wrapper.find('.btn-clear-cache').on('click', () => this.run_bench('clear-cache'));
        this.wrapper.find('.btn-build').on('click', () => this.run_bench('build'));
        
        this.provider_select.on('change', (e) => {
            this.current_provider = e.target.value;
            this.update_model_options();
        });
        
        this.model_select.on('change', (e) => {
            this.current_model = e.target.value;
        });
        
        this.target_app_select.on('change', (e) => {
            this.target_app = e.target.value || null;
            if (this.target_app) {
                this.load_file_tree(this.target_app);
            } else {
                this.file_browser_section.hide();
            }
        });
        
        this.temp_slider.on('input', (e) => {
            this.temperature = parseFloat(e.target.value);
            this.temp_value.text(this.temperature.toFixed(1));
        });
        
        this.wrapper.find('.toggle-api-key').on('click', (e) => {
            e.preventDefault();
            const input = this.api_key_input;
            const icon = $(e.currentTarget).find('i');
            if (input.attr('type') === 'password') {
                input.attr('type', 'text');
                icon.removeClass('fa-eye').addClass('fa-eye-slash');
            } else {
                input.attr('type', 'password');
                icon.removeClass('fa-eye-slash').addClass('fa-eye');
            }
        });
        
        this.wrapper.find('.btn-save-settings').on('click', () => this.save_settings());
        this.wrapper.find('.btn-clear-chat').on('click', () => this.clear_chat());
    }

    get_provider_models() {
        return {
            'OpenAI': [
                {value: 'gpt-4o', label: 'GPT-4o'},
                {value: 'gpt-4o-mini', label: 'GPT-4o Mini'},
                {value: 'gpt-4-turbo', label: 'GPT-4 Turbo'},
                {value: 'gpt-4-turbo-preview', label: 'GPT-4 Turbo Preview'},
                {value: 'gpt-4', label: 'GPT-4'},
                {value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo'},
                {value: 'o1-preview', label: 'o1 Preview'},
                {value: 'o1-mini', label: 'o1 Mini'},
                {value: 'o3-mini', label: 'o3 Mini'}
            ],
            'Anthropic': [
                {value: 'claude-3-7-sonnet-20250219', label: 'Claude 3.7 Sonnet'},
                {value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet'},
                {value: 'claude-3-5-sonnet-latest', label: 'Claude 3.5 Sonnet (Latest)'},
                {value: 'claude-3-opus-20240229', label: 'Claude 3 Opus'},
                {value: 'claude-3-sonnet-20240229', label: 'Claude 3 Sonnet'},
                {value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku'}
            ],
            'Google Gemini': [
                {value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro'},
                {value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash'},
                {value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash'},
                {value: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro'},
                {value: 'gemini-1.5-pro-latest', label: 'Gemini 1.5 Pro (Latest)'},
                {value: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash'},
                {value: 'gemini-1.5-flash-latest', label: 'Gemini 1.5 Flash (Latest)'},
                {value: 'gemini-1.0-pro', label: 'Gemini 1.0 Pro'}
            ],
            'Moonshot AI (Kimi)': [
                {value: 'kimi-moonshot-v1-8k', label: 'Kimi Moonshot v1 8K'},
                {value: 'kimi-moonshot-v1-32k', label: 'Kimi Moonshot v1 32K'},
                {value: 'kimi-moonshot-v1-128k', label: 'Kimi Moonshot v1 128K'},
                {value: 'kimi-k1.5', label: 'Kimi K1.5'}
            ],
            'DeepSeek': [
                {value: 'deepseek-chat', label: 'DeepSeek Chat'},
                {value: 'deepseek-chat-v2', label: 'DeepSeek Chat v2'},
                {value: 'deepseek-coder', label: 'DeepSeek Coder'},
                {value: 'deepseek-coder-v2', label: 'DeepSeek Coder v2'},
                {value: 'deepseek-reasoner', label: 'DeepSeek Reasoner'}
            ],
            'Groq': [
                {value: 'groq-llama-3.3-70b-versatile', label: 'Llama 3.3 70B'},
                {value: 'groq-llama-3.1-70b-versatile', label: 'Llama 3.1 70B'},
                {value: 'groq-llama-3.1-8b-instant', label: 'Llama 3.1 8B'},
                {value: 'groq-mixtral-8x7b-32768', label: 'Mixtral 8x7B'},
                {value: 'groq-gemma-2-9b-it', label: 'Gemma 2 9B'}
            ],
            'Azure OpenAI': [
                {value: 'azure-gpt-4o', label: 'Azure GPT-4o'},
                {value: 'azure-gpt-4-turbo', label: 'Azure GPT-4 Turbo'}
            ],
            'Cohere': [
                {value: 'cohere-command-r', label: 'Command R'},
                {value: 'cohere-command-r-plus', label: 'Command R+'},
                {value: 'cohere-aya-23', label: 'Aya 23'}
            ],
            'Mistral AI': [
                {value: 'mistral-large-latest', label: 'Mistral Large'},
                {value: 'mistral-medium-latest', label: 'Mistral Medium'},
                {value: 'mistral-small-latest', label: 'Mistral Small'},
                {value: 'mistral-codestral-latest', label: 'Codestral'}
            ],
            'Together AI': [
                {value: 'together-llama-3.3-70b', label: 'Llama 3.3 70B'},
                {value: 'together-qwen2.5-72b', label: 'Qwen 2.5 72B'},
                {value: 'together-mixtral-8x22b', label: 'Mixtral 8x22B'}
            ],
            'Perplexity': [
                {value: 'perplexity-sonar', label: 'Sonar'},
                {value: 'perplexity-sonar-pro', label: 'Sonar Pro'},
                {value: 'perplexity-sonar-reasoning', label: 'Sonar Reasoning'}
            ],
            'OpenRouter': [
                {value: 'openrouter-anthropic-claude-3.5-sonnet', label: 'Claude 3.5 Sonnet'},
                {value: 'openrouter-meta-llama-3.3-70b', label: 'Llama 3.3 70B'},
                {value: 'openrouter-google-gemini-1.5-pro', label: 'Gemini 1.5 Pro'}
            ]
        };
    }

    update_model_options() {
        const models = this.get_provider_models();
        const provider_models = models[this.current_provider] || models['OpenAI'];
        this.model_select.empty();
        provider_models.forEach(m => {
            this.model_select.append('<option value="' + m.value + '">' + m.label + '</option>');
        });
        // If current model is not in the list, add it as a custom option
        const model_values = provider_models.map(m => m.value);
        if (this.current_model && !model_values.includes(this.current_model)) {
            this.model_select.append('<option value="' + this.current_model + '">' + this.current_model + '</option>');
        }
    }

    async load_settings() {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.get_ai_studio_settings'
            });
            if (r.message) {
                this.settings = r.message;
                this.current_provider = r.message.default_provider || 'OpenAI';
                this.current_model = r.message.default_model || 'gpt-4o';
                this.temperature = r.message.temperature || 0.2;
                
                this.provider_select.val(this.current_provider);
                this.update_model_options();
                this.model_select.val(this.current_model);
                // If model wasn't found in select, it was added as custom option - select it
                if (this.model_select.val() !== this.current_model) {
                    this.model_select.append('<option value="' + this.current_model + '">' + this.current_model + '</option>');
                    this.model_select.val(this.current_model);
                }
                this.temp_slider.val(this.temperature);
                this.temp_value.text(this.temperature.toFixed(1));
                
                // Show API key status
                if (r.message.has_api_key) {
                    this.api_key_status.text('(saved)');
                    this.api_key_status.css('color', 'var(--green-500)');
                    this.api_key_input.attr('placeholder', 'Key saved - enter new to change');
                } else {
                    this.api_key_status.text('(not set)');
                    this.api_key_status.css('color', 'var(--red-500)');
                    this.api_key_input.attr('placeholder', 'Enter API key...');
                }
            }
        } catch (err) {
            console.log('Could not load settings:', err);
        }
    }

    async load_installed_apps() {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.get_installed_apps'
            });
            if (r.message) {
                this.installed_apps = r.message;
                this.target_app_select.empty();
                this.target_app_select.append('<option value="">All Apps</option>');
                this.installed_apps.forEach(app => {
                    this.target_app_select.append('<option value="' + app + '">' + app + '</option>');
                });
            }
        } catch (err) {
            console.log('Could not load installed apps:', err);
        }
    }

    async load_file_tree(app_name) {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.list_app_files',
                args: { app_name: app_name, max_depth: 4 }
            });
            if (r.message && r.message.files) {
                this.file_browser_section.show();
                this.render_file_tree(r.message.files, app_name);
            }
        } catch (err) {
            console.log('Could not load file tree:', err);
        }
    }

    render_file_tree(files, app_name) {
        let html = '<ul style="list-style:none;padding-left:0;margin:0;">';
        files.slice(0, 100).forEach(f => {
            html += '<li style="padding:2px 0;cursor:pointer;" class="file-item" data-path="' + f + '">';
            html += '<i class="fa fa-file-code-o" style="margin-right:4px;color:var(--text-muted);"></i>';
            html += f;
            html += '</li>';
        });
        if (files.length > 100) {
            html += '<li style="padding:2px 0;color:var(--text-muted);">... and ' + (files.length - 100) + ' more files</li>';
        }
        html += '</ul>';
        this.file_tree_container.html(html);
        
        this.file_tree_container.find('.file-item').on('click', (e) => {
            const path = $(e.currentTarget).data('path');
            this.read_file_into_chat(app_name, path);
        });
    }

    async read_file_into_chat(app_name, relative_path) {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.read_file',
                args: { app_name: app_name, relative_path: relative_path }
            });
            if (r.message) {
                this.append_message('system', 'File: ' + relative_path + '\n```\n' + r.message.content + '\n```');
            }
        } catch (err) {
            frappe.show_alert('Could not read file: ' + relative_path);
        }
    }

    async save_settings() {
        try {
            const settings = {
                default_provider: this.current_provider,
                default_model: this.current_model,
                temperature: this.temperature,
                api_key: this.api_key_input.val().trim(),
                enabled_models: []
            };
            
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.save_ai_studio_settings',
                args: { settings_json: JSON.stringify(settings) }
            });
            
            if (r.message && r.message.status === 'saved') {
                frappe.show_alert('Settings saved successfully!');
                this.api_key_input.val('');
                this.load_settings();
            }
        } catch (err) {
            frappe.show_alert('Failed to save settings: ' + (err.message || 'Error'));
        }
    }

    append_message(role, text) {
        const time = new Date().toLocaleTimeString();
        this.messages.push({ role, text, time });

        const colors = {
            user: '#e3f2fd',
            assistant: '#f3e5f5',
            system: '#fff3e0'
        };

        // Format the text: render markdown code blocks, escape HTML otherwise
        let formatted_text = this._format_message_text(text);

        const msg_el = $(`
            <div class="chat-bubble" style="margin-bottom:10px;padding:12px;border-radius:8px;background:${colors[role] || colors.system};">
                <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;text-transform:uppercase;">${role} &middot; ${time}</div>
                <div class="chat-content" style="margin:0;white-space:pre-wrap;word-break:break-word;font-family:inherit;">${formatted_text}</div>
            </div>
        `).appendTo(this.chat_container);

        this.chat_container.scrollTop(this.chat_container[0].scrollHeight);
        this.chat_container.find('.chat-welcome').remove();
    }

    _format_message_text(text) {
        // Escape HTML first
        let escaped = frappe.utils.escape_html(text);
        
        // Render markdown code blocks: ```json ... ```
        escaped = escaped.replace(/```(\w*)\n([\s\S]*?)\n```/g, function(match, lang, code) {
            return '<pre style="background:#282c34;color:#abb2bf;padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;margin:8px 0;"><code>' + code + '</code></pre>';
        });
        
        // Render inline code: `code`
        escaped = escaped.replace(/`([^`]+)`/g, '<code style="background:var(--gray-100);padding:2px 4px;border-radius:3px;font-size:12px;">$1</code>');
        
        // Convert newlines to <br> for non-pre text
        escaped = escaped.replace(/\n/g, '<br>');
        
        return escaped;
    }

    clear_chat() {
        this.chat_container.empty();
        this.messages = [];
        this.conversation_history = [];
        this.apply_btn.prop('disabled', true);
        this.preview_btn.hide();
        this.code_editor.val('');
        
        $(`
            <div class="chat-welcome" style="text-align:center;color:var(--text-muted);padding:40px;">
                <h4>Welcome to AI Studio</h4>
                <p>Describe what you want to build and the AI agent will help you.</p>
                <p style="font-size:12px;">Select your preferred model from the sidebar and start prompting!</p>
            </div>
        `).appendTo(this.chat_container);
    }

    async send_prompt() {
        const text = this.prompt_input.val().trim();
        if (!text || this.loading) return;

        this.append_message('user', text);
        this.prompt_input.val('');
        this.loading = true;
        this.send_btn.prop('disabled', true).text('Queueing...');

        try {
            // Use the async pipeline for production
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.execute_prompt_async',
                args: {
                    user_prompt: text,
                    provider: this.current_provider,
                    model: this.current_model,
                    temperature: this.temperature,
                    target_app: this.target_app,
                    conversation_history: JSON.stringify(this.conversation_history)
                },
            });

            if (r.message && r.message.status === 'queued') {
                const taskId = r.message.task_id;
                this.append_message('system', 'Task queued: ' + taskId + '. Processing in background...');
                this.track_task(taskId, text);
            } else {
                this.append_message('system', 'Unexpected response from agent.');
                this.loading = false;
                this.send_btn.prop('disabled', false).text('Send');
            }
        } catch (err) {
            this.append_message('system', 'Error: ' + (err.message || 'Request failed'));
            this.loading = false;
            this.send_btn.prop('disabled', false).text('Send');
        }
    }

    track_task(taskId, originalPrompt) {
        // Subscribe to realtime events
        frappe.realtime.on('ai_generation_progress', (data) => {
            if (data.task_id !== taskId) return;
            this.update_task_status(data);
        });

        // Fallback polling every 3 seconds
        this.pollInterval = setInterval(() => this.poll_task_status(taskId, originalPrompt), 3000);
    }

    async poll_task_status(taskId, originalPrompt) {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.get_task_status',
                args: { task_name: taskId }
            });
            if (r.message) {
                this.update_task_status(r.message, originalPrompt);
            }
        } catch (err) {
            console.log('Poll error:', err);
        }
    }

    update_task_status(data, originalPrompt) {
        const status = data.status;
        const percent = data.progress_percent || 0;
        const stage = data.current_stage || status;

        // Update the send button to show progress
        this.send_btn.text(stage + ' (' + percent + '%)');

        if (status === 'Completed') {
            this.loading = false;
            this.send_btn.prop('disabled', false).text('Send');
            if (this.pollInterval) {
                clearInterval(this.pollInterval);
                this.pollInterval = null;
            }

            // Show AI response
            if (data.ai_response) {
                this.append_message('assistant', data.ai_response);
                this.apply_btn.prop('disabled', false);
                this.preview_btn.show();
                this.try_extract_payload(data.ai_response);

                // Store task info for approve/reject
                this.current_task = data;

                // Show approve/reject buttons
                this.show_approve_reject(data.task_id);
            }

            // Update conversation history
            if (originalPrompt) {
                this.conversation_history.push({role: 'user', content: originalPrompt});
                this.conversation_history.push({role: 'assistant', content: data.ai_response || ''});
                if (this.conversation_history.length > 20) {
                    this.conversation_history = this.conversation_history.slice(-20);
                }
            }
        } else if (status === 'Failed') {
            this.loading = false;
            this.send_btn.prop('disabled', false).text('Send');
            if (this.pollInterval) {
                clearInterval(this.pollInterval);
                this.pollInterval = null;
            }
            this.append_message('system', 'Task failed: ' + (data.error_trace || 'Unknown error'));
        } else if (status === 'Rolled Back') {
            this.loading = false;
            this.send_btn.prop('disabled', false).text('Send');
            if (this.pollInterval) {
                clearInterval(this.pollInterval);
                this.pollInterval = null;
            }
            this.append_message('system', 'Task was rolled back by user.');
        }
    }

    show_approve_reject(taskId) {
        // Remove any existing approve/reject buttons
        this.wrapper.find('.ai-studio-action-bar').remove();

        const actionBar = $(`
            <div class="ai-studio-action-bar" style="display:flex;gap:10px;margin-top:10px;padding:10px;background:var(--gray-100);border-radius:8px;">
                <span style="flex:1;font-size:12px;color:var(--text-muted);">Changes are staged. Review before deploying.</span>
                <button class="btn btn-sm btn-success btn-approve" data-task="${taskId}">Deploy</button>
                <button class="btn btn-sm btn-danger btn-reject" data-task="${taskId}">Rollback</button>
            </div>
        `).insertAfter(this.chat_container);

        actionBar.find('.btn-approve').on('click', (e) => {
            const tid = $(e.currentTarget).data('task');
            this.approve_task(tid);
            actionBar.remove();
        });

        actionBar.find('.btn-reject').on('click', (e) => {
            const tid = $(e.currentTarget).data('task');
            this.reject_task(tid);
            actionBar.remove();
        });
    }

    async approve_task(taskId) {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.approve_task',
                args: { task_name: taskId }
            });
            if (r.message && r.message.status === 'deployed') {
                frappe.show_alert('Changes deployed successfully.');
                this.append_message('system', 'Changes deployed.');
            }
        } catch (err) {
            this.append_message('system', 'Deploy failed: ' + (err.message || 'Error'));
        }
    }

    async reject_task(taskId) {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.reject_task',
                args: { task_name: taskId }
            });
            if (r.message && r.message.status === 'rolled_back') {
                frappe.show_alert('Changes rolled back.');
                this.append_message('system', 'Changes rolled back.');
            }
        } catch (err) {
            this.append_message('system', 'Rollback failed: ' + (err.message || 'Error'));
        }
    }

    try_extract_payload(response) {
        try {
            const m = response.match(/```json\n([\s\S]*?)\n```/);
            if (m) {
                const payload = JSON.parse(m[1]);
                this.code_editor.val(JSON.stringify(payload, null, 2));
            }
        } catch (e) {
            // Not valid JSON, ignore
        }
    }

    async preview_changes() {
        const last = this.messages[this.messages.length - 1];
        if (!last || last.role !== 'assistant') {
            frappe.show_alert('No AI response to preview.');
            return;
        }

        let payload = null;
        try {
            const m = last.text.match(/```json\n([\s\S]*?)\n```/);
            payload = JSON.parse(m ? m[1] : last.text);
        } catch {
            frappe.show_alert('Could not parse AI response as changes.');
            return;
        }

        if (!payload.app_name || !payload.changes) {
            frappe.show_alert('Invalid change payload.');
            return;
        }

        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.preview_changes',
                args: {
                    app_name: payload.app_name,
                    changes: JSON.stringify(payload.changes),
                },
            });
            if (r.message && r.message.status === 'preview') {
                // Show preview in a dialog
                let preview_html = '<div style="max-height:400px;overflow-y:auto;">';
                r.message.preview.forEach(item => {
                    preview_html += '<div style="margin-bottom:15px;border:1px solid var(--border-color);border-radius:4px;padding:10px;">';
                    preview_html += '<strong>' + item.type + '</strong>: ' + item.relative_path + '<br/>';
                    preview_html += '<pre style="margin-top:5px;font-size:11px;background:var(--gray-100);padding:8px;border-radius:4px;max-height:200px;overflow-y:auto;">' + frappe.utils.escape_html(item.preview) + '</pre>';
                    preview_html += '</div>';
                });
                preview_html += '</div>';
                
                const d = new frappe.ui.Dialog({
                    title: 'Preview Changes',
                    fields: [{fieldtype: 'HTML', fieldname: 'preview_content'}],
                    primary_action_label: 'Apply Changes',
                    primary_action: () => {
                        d.hide();
                        this.apply_changes();
                    }
                });
                d.fields_dict.preview_content.$wrapper.html(preview_html);
                d.show();
            }
        } catch (err) {
            this.append_message('system', 'Preview failed: ' + (err.message || 'Error'));
        }
    }

    async apply_changes() {
        // If we have a current_task from the async pipeline, use that
        if (this.current_task && this.current_task.task_id) {
            this.approve_task(this.current_task.task_id);
            return;
        }

        const last = this.messages[this.messages.length - 1];
        if (!last || last.role !== 'assistant') {
            frappe.show_alert('No AI response to apply.');
            return;
        }

        let payload = null;
        try {
            const m = last.text.match(/```json\n([\s\S]*?)\n```/);
            payload = JSON.parse(m ? m[1] : last.text);
        } catch {
            frappe.show_alert('Could not parse AI response as changes.');
            return;
        }

        if (!payload.app_name || !payload.changes) {
            frappe.show_alert('Invalid change payload.');
            return;
        }

        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.apply_ai_changes',
                args: {
                    app_name: payload.app_name,
                    changes: JSON.stringify(payload.changes),
                },
            });
            if (r.message && r.message.status === 'applied') {
                frappe.show_alert('Changes applied successfully.');
                this.append_message('system', 'Changes applied to ' + payload.app_name + '. ' + (payload.explanation || ''));
            }
        } catch (err) {
            this.append_message('system', 'Apply failed: ' + (err.message || 'Error'));
        }
    }

    async run_bench(cmd) {
        try {
            const r = await frappe.call({
                method: 'frappe_ai_studio.frappe_ai_studio.api.run_bench_command',
                args: { command: cmd },
            });
            this.append_message('system', 'Bench ' + cmd + ':\n' + (r.message.output || 'Done'));
        } catch (err) {
            this.append_message('system', 'Bench ' + cmd + ' failed: ' + (err.message || 'Error'));
        }
    }
};

frappe.pages['ai-studio'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'AI Studio',
        single_column: true
    });
    frappe.ai_studio.page = new frappe.ai_studio.AIStudioPage(page);
};
