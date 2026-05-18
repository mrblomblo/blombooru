class AdminSystem {
    constructor(adminPanel) {
        this.app = adminPanel;
    }

    setupCustomSelects() {
        const themeSelectElement = document.getElementById('theme-select');
        if (themeSelectElement) {
            this.themeSelect = new CustomSelect(themeSelectElement);
        }

        const languageSelectElement = document.getElementById('language-select');
        if (languageSelectElement) {
            this.languageSelect = new CustomSelect(languageSelectElement);
        }

        const defaultSortElement = document.getElementById('default-sort');
        if (defaultSortElement) {
            this.defaultSortSelect = new CustomSelect(defaultSortElement);
        }

        const defaultOrderElement = document.getElementById('default-order');
        if (defaultOrderElement) {
            this.defaultOrderSelect = new CustomSelect(defaultOrderElement);
        }

        const sidebarFilterModeElement = document.getElementById('sidebar-filter-mode');
        if (sidebarFilterModeElement) {
            this.sidebarFilterModeSelect = new CustomSelect(sidebarFilterModeElement);
            this.customButtons = [];
            this.customButtonInstances = [];

            // Show/hide custom buttons container based on mode
            sidebarFilterModeElement.addEventListener('change', (e) => {
                const container = document.getElementById('custom-buttons-container');
                if (container) {
                    container.style.display = e.detail.value === 'custom' ? 'block' : 'none';
                }
            });
        }

        const addCustomButtonBtn = document.getElementById('add-custom-button-btn');
        if (addCustomButtonBtn) {
            addCustomButtonBtn.addEventListener('click', () => this.addCustomButton());
        }

        // Media type tag inputs
        const mediaTypeTagIds = ['media-type-tags-image', 'media-type-tags-gif', 'media-type-tags-video'];
        mediaTypeTagIds.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            this.app.tagInputHelper.setupTagInput(el, id, { onValidate: () => { } });
            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(el, { multipleValues: true });
            }
        });

        // AI Tagger Blacklisted tags input
        const blacklistedTagsEl = document.getElementById('wd-blacklisted-tags');
        if (blacklistedTagsEl) {
            this.app.tagInputHelper.setupTagInput(blacklistedTagsEl, 'wd-blacklisted-tags', { onValidate: () => { }, allowWildcards: true });
            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(blacklistedTagsEl, { multipleValues: true });
            }
        }
    }

    cleanupCustomButtons() {
        if (this.customButtonInstances) {
            this.customButtonInstances.forEach(instance => {
                if (instance.autocomplete) instance.autocomplete.destroy();
            });
            this.customButtonInstances = [];
        }
    }

    addCustomButton() {
        this.customButtons.push({ title: '', tags: '' });
        this.renderCustomButtons();
    }

    removeCustomButton(index) {
        this.customButtons.splice(index, 1);
        this.renderCustomButtons();
    }

    updateCustomButton(index, field, value) {
        if (this.customButtons[index]) {
            this.customButtons[index][field] = value;
        }
    }

    renderCustomButtons() {
        const container = document.getElementById('custom-buttons-list');
        if (!container) return;

        this.cleanupCustomButtons();
        container.innerHTML = '';

        this.customButtons.forEach((btn, index) => {
            const row = document.createElement('div');
            row.className = 'flex gap-2 items-start mb-3';

            const titleInput = document.createElement('input');
            titleInput.type = 'text';
            titleInput.placeholder = window.i18n.t('admin.settings.button_title');
            titleInput.value = btn.title || '';
            titleInput.className = 'w-1/3 bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary';
            titleInput.addEventListener('change', (e) => {
                this.updateCustomButton(index, 'title', e.target.value);
            });

            const tagContainer = document.createElement('div');
            tagContainer.className = 'flex-1 relative';

            const tagInput = document.createElement('div');
            tagInput.contentEditable = true;
            tagInput.className = 'w-full bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary';
            tagInput.setAttribute('data-placeholder', window.i18n.t('admin.settings.button_tags'));
            tagInput.style.minHeight = '34px';
            tagInput.style.maxHeight = '100px';
            tagInput.style.overflowY = 'auto';
            tagInput.style.whiteSpace = 'pre-wrap';
            tagInput.style.overflowWrap = 'break-word';
            tagInput.textContent = btn.tags || '';

            if (!btn.tags) tagInput.classList.add('empty');

            const instance = { autocomplete: null };

            tagInput.addEventListener('input', () => {
                const text = tagInput.textContent || '';
                this.updateCustomButton(index, 'tags', text);
                if (!text) tagInput.classList.add('empty');
                else tagInput.classList.remove('empty');
            });

            // Prevent Enter key from adding new lines
            tagInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                }
            });

            tagContainer.appendChild(tagInput);

            if (typeof TagAutocomplete !== 'undefined') {
                const autocomplete = new TagAutocomplete(tagInput, {
                    multipleValues: true,
                    containerClasses: 'max-h-40 overflow-y-auto w-full bg border border-primary shadow-lg z-10'
                });
                instance.autocomplete = autocomplete;
            }

            this.customButtonInstances.push(instance);

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'px-3 py-2 bg-danger tag-text text-xs hover:bg-danger transition-colors h-[34px]';
            removeBtn.textContent = '×';
            removeBtn.onclick = () => this.removeCustomButton(index);

            row.appendChild(titleInput);
            row.appendChild(tagContainer);
            row.appendChild(removeBtn);
            container.appendChild(row);
        });
    }

    async testRedisConnection() {
        const btn = document.getElementById('test-redis-btn');
        const resultDiv = document.getElementById('redis-test-result');
        const originalText = btn.textContent;

        const data = {
            host: document.getElementById('redis-host').value,
            port: parseInt(document.getElementById('redis-port').value),
            db: parseInt(document.getElementById('redis-db').value),
            password: document.getElementById('redis-password').value
        };

        btn.disabled = true;
        btn.textContent = window.i18n.t('admin.actions.testing');
        resultDiv.style.display = 'none';

        try {
            const result = await app.apiCall('/api/admin/test-redis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            resultDiv.style.display = 'block';
            if (result.success) {
                resultDiv.className = 'mt-2 text-xs text-success';
                const message = result.message_key ? window.i18n.t(result.message_key) : result.message;
                resultDiv.textContent = message;
            } else {
                resultDiv.className = 'mt-2 text-xs text-danger';
                const message = result.message_key ? window.i18n.t(result.message_key, { error: result.error }) : result.message;
                resultDiv.textContent = message;
            }
        } catch (error) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'mt-2 text-xs text-danger';
            resultDiv.textContent = 'Error: ' + error.message;
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }

    async testSharedTagsConnection() {
        const btn = document.getElementById('test-shared-tags-btn');
        const resultDiv = document.getElementById('shared-tags-test-result');
        const originalText = btn.textContent;

        const data = {
            host: document.getElementById('shared-tags-host').value,
            port: parseInt(document.getElementById('shared-tags-port').value || '5432'),
            name: document.getElementById('shared-tags-name').value,
            user: document.getElementById('shared-tags-user').value,
            password: document.getElementById('shared-tags-password').value
        };

        btn.disabled = true;
        btn.textContent = window.i18n.t('admin.actions.testing');
        resultDiv.style.display = 'none';

        try {
            const result = await app.apiCall('/api/admin/test-shared-tag-db', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            resultDiv.style.display = 'block';
            if (result.success) {
                resultDiv.className = 'mt-2 text-xs text-success';
                resultDiv.textContent = result.message || window.i18n.t('common.connection_successful');
            } else {
                resultDiv.className = 'mt-2 text-xs text-danger';
                resultDiv.textContent = result.message || window.i18n.t('common.connection_failed');
            }
        } catch (error) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'mt-2 text-xs text-danger';
            resultDiv.textContent = 'Error: ' + error.message;
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }

    async syncSharedTags() {
        const btn = document.getElementById('sync-shared-tags-btn');
        const resultDiv = document.getElementById('shared-tags-test-result');
        const originalText = btn.textContent;

        btn.disabled = true;
        btn.textContent = window.i18n.t('admin.shared_tags.syncing');
        resultDiv.style.display = 'none';

        try {
            const result = await app.apiCall('/api/admin/shared-tags/sync', {
                method: 'POST'
            });

            resultDiv.style.display = 'block';
            if (result.success) {
                resultDiv.className = 'mt-2 text-xs text-success';
                resultDiv.innerHTML = `
                    ${window.i18n.t('admin.shared_tags.sync_complete')}<br>
                    ${window.i18n.t('admin.shared_tags.imported_count', { tags: result.tags_imported, aliases: result.aliases_imported })}<br>
                    ${window.i18n.t('admin.shared_tags.exported_count', { tags: result.tags_exported, aliases: result.aliases_exported })}
                `;
            } else {
                resultDiv.className = 'mt-2 text-xs text-danger';
                resultDiv.textContent = result.errors?.join(', ') || window.i18n.t('admin.shared_tags.sync_failed');
            }

            // Refresh status
            this.loadSharedTagsStatus();
        } catch (error) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'mt-2 text-xs text-danger';
            resultDiv.textContent = window.i18n.t('common.error', { error: error.message });
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }

    async loadSharedTagsStatus() {
        try {
            const result = await app.apiCall('/api/admin/shared-tags/status');
            const statusDiv = document.getElementById('shared-tags-status');
            const connectionStatus = document.getElementById('shared-tags-connection-status');
            const counts = document.getElementById('shared-tags-counts');

            if (statusDiv && result.enabled) {
                statusDiv.style.display = 'block';
                if (result.connected) {
                    connectionStatus.innerHTML = `<span class="text-success">● ${window.i18n.t('common.connected')}</span>`;
                    counts.textContent = `${window.i18n.t('admin.shared_tags.shared_count')}: ${result.shared_tags || 0} tags, ${result.shared_aliases || 0} aliases`;
                } else {
                    connectionStatus.innerHTML = `<span class="text-danger">● ${window.i18n.t('common.disconnected')}</span>`;
                    counts.textContent = result.error || '';
                }
            }
        } catch (error) {
            console.error('Error loading shared tags status:', error);
        }
    }

    async loadSettings() {
        try {
            const response = await fetch('/api/admin/settings');

            if (!response.ok) {
                console.log('Not authenticated or settings not available');
                return;
            }

            const settings = await response.json();

            // Populate form fields
            if (settings.app_name) {
                const appNameInput = document.getElementById('app-name');
                if (appNameInput) appNameInput.value = settings.app_name;
            }

            if (settings.items_per_page) {
                const itemsPerPageInput = document.getElementById('items-per-page');
                if (itemsPerPageInput) itemsPerPageInput.value = settings.items_per_page;
            }

            if (settings.external_share_url) {
                const externalShareUrlInput = document.getElementById('external-share-url');
                if (externalShareUrlInput) externalShareUrlInput.value = settings.external_share_url;
            }

            if (settings.default_sort && this.defaultSortSelect) {
                this.defaultSortSelect.setValue(settings.default_sort);
            }

            if (settings.default_order && this.defaultOrderSelect) {
                this.defaultOrderSelect.setValue(settings.default_order);
            }

            if (settings.require_auth !== undefined) {
                const requireAuthCheckbox = document.getElementById('require-auth');
                if (requireAuthCheckbox) requireAuthCheckbox.checked = settings.require_auth;
            }

            if (settings.redis) {
                const redisEnabled = document.getElementById('redis-enabled');
                if (redisEnabled) {
                    redisEnabled.checked = settings.redis.enabled;
                    const container = document.getElementById('redis-settings-container');
                    if (container) container.style.display = settings.redis.enabled ? 'block' : 'none';
                }

                const hostInput = document.getElementById('redis-host');
                if (hostInput) hostInput.value = settings.redis.host || 'redis';

                const portInput = document.getElementById('redis-port');
                if (portInput) portInput.value = settings.redis.port || 6379;

                const dbInput = document.getElementById('redis-db');
                if (dbInput) dbInput.value = settings.redis.db || 0;

                const passwordInput = document.getElementById('redis-password');
                if (passwordInput) passwordInput.value = settings.redis.password || '';
            }

            if (settings.sidebar_filter_mode && this.sidebarFilterModeSelect) {
                this.sidebarFilterModeSelect.setValue(settings.sidebar_filter_mode);
                const container = document.getElementById('custom-buttons-container');
                if (container) container.style.display = settings.sidebar_filter_mode === 'custom' ? 'block' : 'none';
            }

            if (settings.sidebar_custom_buttons) {
                this.customButtons = settings.sidebar_custom_buttons;
                this.renderCustomButtons();
            }

            // Load shared tags settings
            if (settings.shared_tags) {
                const sharedTagsEnabled = document.getElementById('shared-tags-enabled');
                if (sharedTagsEnabled) {
                    sharedTagsEnabled.checked = settings.shared_tags.enabled;
                    const container = document.getElementById('shared-tags-settings-container');
                    if (container) container.style.display = settings.shared_tags.enabled ? 'block' : 'none';
                }

                // Show/hide sync button based on whether shared tags are enabled
                const syncBtn = document.getElementById('sync-shared-tags-btn');
                if (syncBtn) syncBtn.style.display = settings.shared_tags.enabled ? 'inline-block' : 'none';

                const hostInput = document.getElementById('shared-tags-host');
                if (hostInput) hostInput.value = settings.shared_tags.host || 'shared-tag-db';

                const portInput = document.getElementById('shared-tags-port');
                if (portInput) portInput.value = settings.shared_tags.port || 5432;

                const nameInput = document.getElementById('shared-tags-name');
                if (nameInput) nameInput.value = settings.shared_tags.name || 'shared_tags';

                const userInput = document.getElementById('shared-tags-user');
                if (userInput) userInput.value = settings.shared_tags.user || 'postgres';

                const passwordInput = document.getElementById('shared-tags-password');
                if (passwordInput) passwordInput.value = settings.shared_tags.password || '';

                // Load status if enabled
                if (settings.shared_tags.enabled) {
                    this.loadSharedTagsStatus();
                }
            }

            // Load media_type_tags settings
            if (settings.media_type_tags) {
                const types = ['image', 'gif', 'video'];
                types.forEach(type => {
                    const el = document.getElementById(`media-type-tags-${type}`);
                    if (el) {
                        const tags = settings.media_type_tags[type];
                        if (Array.isArray(tags) && tags.length > 0) {
                            el.textContent = tags.join(' ');
                            setTimeout(() => this.app.tagInputHelper.validateAndStyleTags(el), 100);
                        }
                    }
                });
            }
        } catch (error) {
            console.error('Error loading settings:', error);
        }
    }

    async saveSettings() {
        const appName = document.getElementById('app-name').value.trim();
        const themeSelectElement = document.getElementById('theme-select');
        const theme = themeSelectElement?.dataset.value;
        const languageSelectElement = document.getElementById('language-select');
        const language = languageSelectElement?.dataset.value;
        const itemsPerPage = document.getElementById('items-per-page')?.value;
        const externalShareUrl = document.getElementById('external-share-url')?.value;

        if (!appName || !theme || !itemsPerPage) {
            app.showNotification(window.i18n.t('notifications.admin.fill_all_settings'), 'error');
            return;
        }

        if (appName.length < 1 || appName.length > 25) {
            app.showNotification(window.i18n.t('notifications.admin.app_name_length'), 'error');
            return;
        }

        const itemsPerPageNum = parseInt(itemsPerPage);
        if (isNaN(itemsPerPageNum) || itemsPerPageNum < 20 || itemsPerPageNum > 200) {
            app.showNotification(window.i18n.t('notifications.admin.items_per_page_range'), 'error');
            return;
        }

        const defaultSort = this.defaultSortSelect ? this.defaultSortSelect.getValue() : null;
        const defaultOrder = this.defaultOrderSelect ? this.defaultOrderSelect.getValue() : null;
        const requireAuth = document.getElementById('require-auth')?.checked || false;

        const redisSettings = {
            enabled: document.getElementById('redis-enabled')?.checked || false,
            host: document.getElementById('redis-host')?.value || 'redis',
            port: parseInt(document.getElementById('redis-port')?.value || '6379'),
            db: parseInt(document.getElementById('redis-db')?.value || '0'),
            password: document.getElementById('redis-password')?.value || ''
        };

        const sidebarMode = this.sidebarFilterModeSelect ? this.sidebarFilterModeSelect.getValue() : 'rating';

        // Filter out empty buttons (must have both title and tags)
        let validButtons = [];
        if (this.customButtons) {
            validButtons = this.customButtons.filter(btn => {
                const title = (btn.title || '').trim();
                const tags = (btn.tags || '').trim();
                return title.length > 0 && tags.length > 0;
            });
        }

        // Require at least one valid button
        if (sidebarMode === 'custom' && validButtons.length === 0) {
            app.showNotification(window.i18n.t('notifications.admin.error_custom_button_required'), 'error');
            return;
        }

        // Collect media_type_tags
        const getMediaTypeTags = (id) => {
            const el = document.getElementById(id);
            if (!el) return [];
            const text = this.app.tagInputHelper.getPlainTextFromDiv(el);
            return text.split(/\s+/).filter(t => t.length > 0);
        };

        const settings = {
            app_name: appName,
            theme: theme,
            language: language || 'en',
            items_per_page: itemsPerPageNum,
            default_sort: defaultSort,
            default_order: defaultOrder,
            external_share_url: externalShareUrl || null,
            require_auth: requireAuth,
            redis: redisSettings,
            shared_tags: {
                enabled: document.getElementById('shared-tags-enabled')?.checked || false,
                host: document.getElementById('shared-tags-host')?.value || 'shared-tag-db',
                port: parseInt(document.getElementById('shared-tags-port')?.value || '5432'),
                name: document.getElementById('shared-tags-name')?.value || 'shared_tags',
                user: document.getElementById('shared-tags-user')?.value || 'postgres',
                password: document.getElementById('shared-tags-password')?.value || ''
            },
            sidebar_filter_mode: sidebarMode,
            sidebar_custom_buttons: validButtons,
            media_type_tags: {
                image: getMediaTypeTags('media-type-tags-image'),
                gif: getMediaTypeTags('media-type-tags-gif'),
                video: getMediaTypeTags('media-type-tags-video')
            }
        };

        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify(settings)
            });

            // Show/hide sync button based on whether shared tags are enabled
            const syncBtn = document.getElementById('sync-shared-tags-btn');
            if (syncBtn) syncBtn.style.display = settings.shared_tags.enabled ? 'inline-block' : 'none';

            app.showNotification(window.i18n.t('notifications.admin.settings_updated'), 'success');
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_saving_settings'));
        }
    }

    async loadThemes() {
        try {
            const response = await fetch('/api/admin/themes');
            const data = await response.json();

            if (!this.themeSelect) {
                console.error('themeSelect is not initialized!');
                return;
            }

            const options = data.themes.map(theme => {
                const emoji = theme.is_dark ? '🌙 ' : '☀️ ';
                return {
                    value: theme.id,
                    text: emoji + theme.name,
                    selected: theme.id === data.current_theme
                };
            });

            this.themeSelect.setOptions(options);

        } catch (error) {
            console.error('Error loading themes:', error);
        }
    }

    async loadLanguages() {
        try {
            const response = await fetch('/api/admin/languages');
            const data = await response.json();

            if (!this.languageSelect) {
                console.error('languageSelect is not initialized!');
                return;
            }

            const options = data.languages.map(lang => ({
                value: lang.id,
                text: lang.native_name,
                selected: lang.id === data.current_language
            }));

            this.languageSelect.setOptions(options);

        } catch (error) {
            console.error('Error loading languages:', error);
        }
    }

    showApiKeyNameModal() {
        const inputId = 'api-key-name-input';
        const modal = new ModalHelper({
            id: 'api-key-name-modal',
            title: window.i18n.t('modal.api_key_name.title'),
            message: `
                <div class="text-left">
                    <input type="text" id="${inputId}" 
                        class="w-full bg px-3 py-2 mb-4 border text-xs hover:border-primary transition-colors focus:outline-none focus:border-primary"
                        placeholder="${window.i18n.t('modal.api_key_name.placeholder')}"
                        autocomplete="off">
                </div>
            `,
            confirmText: window.i18n.t('modal.api_key_name.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            onConfirm: () => {
                const nameInput = document.getElementById(inputId);
                const name = nameInput ? nameInput.value.trim() : '';
                this.generateApiKey(name);
                modal.destroy();
            },
            onCancel: () => {
                modal.destroy();
            }
        });

        modal.show();

        // Focus and clear input
        const input = document.getElementById(inputId);
        if (input) {
            input.value = '';
            input.focus();
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    modal.confirm();
                }
            });
        }
    }

    setupApiKeyManagement() {
        this.loadApiKeys();

        document.getElementById('generate-api-key-btn')?.addEventListener('click', () => {
            this.showApiKeyNameModal();
        });

        document.getElementById('copy-api-key-btn')?.addEventListener('click', () => {
            const input = document.getElementById('new-api-key-value');
            input.select();
            document.execCommand('copy');
            app.showNotification(window.i18n.t('notifications.admin.api_key_copied'), 'success');
        });
    }

    async loadApiKeys() {
        try {
            const response = await fetch('/api/admin/api-keys');
            if (response.ok) {
                const keys = await response.json();
                this.renderApiKeys(keys);
            }
        } catch (e) { console.error(e); }
    }

    renderApiKeys(keys) {
        const listContainer = document.getElementById('api-keys-list');
        if (!listContainer) return;

        if (keys.length === 0) {
            listContainer.innerHTML = `<div class="bg p-6 text-center text-xs text-secondary opacity-70">${window.i18n.t('notifications.admin.no_active_api_keys')}</div>`;
            return;
        }

        listContainer.innerHTML = keys.map(key => `
            <div class="bg p-4 border-b last:border-b-0 flex justify-between items-center hover:surface transition-colors">
                <div class="flex-1 min-w-0 pr-4">
                    <div class="font-bold text-xs truncate mb-1 text">${this.app.escapeHtml(key.name || 'Unnamed Key')}</div>
                    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-secondary opacity-80">
                        <span class="font-mono bg surface px-1 border border-primary border-opacity-20">${this.app.escapeHtml(key.key_prefix)}...</span>
                        <span> ${window.i18n.t('admin.api_access.created_at')} <strong>${new Date(key.created_at).toLocaleDateString()}</strong></span>
                        <span> ${window.i18n.t('admin.api_access.last_used')} <strong>${key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}</strong></span>
                    </div>
                </div>
                <div class="flex-shrink-0">
                    <button class="btn-danger px-3 py-1 text-[10px] uppercase font-bold tracking-wider" 
                        onclick="window.adminPanel.system.revokeApiKey(${key.id})">
                        ${window.i18n.t('admin.api_access.revoke_key')}
                    </button>
                </div>
            </div>
        `).join('');
    }

    async generateApiKey(name) {
        try {
            const response = await app.apiCall('/api/admin/api-keys', {
                method: 'POST',
                body: JSON.stringify({ name: name })
            });

            // Show result
            const display = document.getElementById('new-api-key-display');
            if (display) display.style.display = 'block';

            const input = document.getElementById('new-api-key-value');
            if (input) input.value = response.key;

            // Reload list
            this.loadApiKeys();

            app.showNotification(window.i18n.t('notifications.admin.api_key_generated'), 'success');
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_generating_api_key'));
        }
    }

    async revokeApiKey(keyId) {
        const modal = new ModalHelper({
            id: 'revoke-api-key-modal',
            type: 'danger',
            title: window.i18n.t('modal.revoke_api_key.title'),
            message: window.i18n.t('modal.revoke_api_key.message'),
            confirmText: window.i18n.t('modal.revoke_api_key.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/admin/api-keys/${keyId}`, {
                        method: 'DELETE'
                    });

                    this.loadApiKeys();
                    app.showNotification(window.i18n.t('notifications.admin.api_key_revoked'), 'success');
                } catch (error) {
                    app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_revoking_api_key'));
                } finally {
                    modal.destroy();
                }
            },
            onCancel: () => {
                modal.destroy();
            }
        });

        modal.show();
    }

    setupSystemUpdate() {
        if (document.getElementById('btn-check-updates')) {
            document.getElementById('btn-check-updates').addEventListener('click', () => this.checkUpdateStatus());
        }
        document.getElementById('btn-update-now')?.addEventListener('click', () => this.performUpdate());
        document.getElementById('btn-view-changelog')?.addEventListener('click', () => this.showChangelog());

        this.updateData = null;
    }

    async checkUpdateStatus() {
        const initialState = document.getElementById('update-initial-state');
        const loading = document.getElementById('update-loading');
        const statusDiv = document.getElementById('update-status');

        if (!loading || !statusDiv) return;

        if (initialState) initialState.classList.add('hidden');
        loading.classList.remove('hidden');
        loading.style.display = 'block';
        statusDiv.style.display = 'none';

        try {
            const response = await fetch('/api/system/update/check');
            if (!response.ok) throw new Error('Failed to check for updates');

            const status = await response.json();
            this.updateData = status;

            loading.style.display = 'none';
            loading.classList.add('hidden');
            statusDiv.style.display = 'block';

            const currentEl = document.getElementById('current-version-display');
            if (currentEl) currentEl.textContent = status.current_version;

            const latestEl = document.getElementById('latest-version-display');
            if (latestEl) latestEl.textContent = status.latest_version;

            const noticesDiv = document.getElementById('update-notices');
            if (noticesDiv) {
                if (status.notices && status.notices.length > 0) {
                    noticesDiv.classList.remove('hidden');
                    noticesDiv.innerHTML = status.notices.map(n => {
                        const translated = window.i18n ? window.i18n.t(n) : n;
                        return `<div class="bg text-xs p-2 mb-1 border-l-4 border-warning text-warning font-bold">${this.app.escapeHtml(translated)}</div>`;
                    }).join('');
                } else {
                    noticesDiv.classList.add('hidden');
                }
            }

            // Update instructions for Docker users
            const instructionsDiv = document.getElementById('update-instructions');
            const commandText = document.getElementById('update-command-text');
            if (instructionsDiv && commandText && status.update_available) {
                if (status.deployment_type === 'ghcr') {
                    instructionsDiv.classList.remove('hidden');
                    commandText.textContent = 'docker compose up -d --pull always';
                } else if (status.deployment_type === 'docker_local') {
                    instructionsDiv.classList.remove('hidden');
                    commandText.textContent = 'docker compose down && docker compose -f docker-compose.dev.yml up --build';
                } else {
                    instructionsDiv.classList.add('hidden');
                }
            } else if (instructionsDiv) {
                instructionsDiv.classList.add('hidden');
            }

            // Config files notice
            const configNotice = document.getElementById('config-files-notice');
            const configMessage = document.getElementById('config-files-message');
            const configLinks = document.getElementById('config-files-links');
            if (configNotice && status.config_files_changed && status.update_available) {
                configNotice.classList.remove('hidden');
                const fileNames = (status.changed_config_files || []).join(', ');
                const msg = window.i18n ? window.i18n.t('admin.update.config_files_changed', { files: fileNames }) : `Configuration files changed: ${fileNames}`;
                if (configMessage) configMessage.textContent = msg;
                if (configLinks) {
                    configLinks.innerHTML = Object.entries(status.asset_urls || {}).map(([name, url]) =>
                        `<a href="${this.app.escapeHtml(url)}" target="_blank" class="btn-dark px-3 py-1 text-[10px]">${this.app.escapeHtml(name)}</a>`
                    ).join('');
                }
            } else if (configNotice) {
                configNotice.classList.add('hidden');
            }

            // Update Now button (only for local/non-Docker)
            const updateBtn = document.getElementById('btn-update-now');
            if (updateBtn) {
                if (status.update_available && status.deployment_type === 'local') {
                    updateBtn.style.display = 'block';
                    updateBtn.disabled = false;
                } else if (!status.update_available && status.deployment_type === 'local') {
                    updateBtn.style.display = 'block';
                    updateBtn.disabled = true;
                    updateBtn.textContent = window.i18n ? window.i18n.t('admin.messages.already_latest') : 'Already up to date';
                } else {
                    updateBtn.style.display = 'none';
                }
            }

            // View Release button
            const releaseBtn = document.getElementById('btn-view-release');
            if (releaseBtn && status.release_url) {
                releaseBtn.style.display = 'inline-block';
                releaseBtn.href = status.release_url;
            }

            // Up to date message
            if (!status.update_available) {
                const noticesDiv2 = document.getElementById('update-notices');
                if (noticesDiv2) {
                    noticesDiv2.classList.remove('hidden');
                    const msg = window.i18n ? window.i18n.t('admin.update.up_to_date') : 'You are running the latest version.';
                    noticesDiv2.innerHTML = `<div class="text-xs tag-text p-2 border border-success bg-success bg-opacity-10">${this.app.escapeHtml(msg)}</div>`;
                }
            }

            // Changelog button
            const changelogBtn = document.getElementById('btn-view-changelog');
            if (changelogBtn) {
                const hasContent = (status.releases && status.releases.length > 0) || (status.commits && status.commits.length > 0);
                if (hasContent && status.update_available) {
                    changelogBtn.style.display = 'block';
                    const count = (status.commits || []).length;
                    changelogBtn.textContent = window.i18n ? window.i18n.t('admin.messages.view_changelog', { count }) : `View Changelog (${count})`;
                } else {
                    changelogBtn.style.display = 'none';
                }
            }

        } catch (e) {
            console.error(e);
            if (loading) {
                loading.textContent = window.i18n ? window.i18n.t('admin.messages.update_error', { error: e.message }) : `Error: ${e.message}`;
                loading.classList.remove('hidden');
                loading.classList.add('text-danger');
            }
        }
    }

    showChangelog() {
        if (!this.updateData) return;
        const { releases, commits, compare_url, current_version, latest_version } = this.updateData;
        if ((!releases || releases.length === 0) && (!commits || commits.length === 0)) return;

        if (typeof ModalHelper === 'undefined') {
            console.error('ModalHelper not available');
            return;
        }

        const t = (key, params) => window.i18n ? window.i18n.t(key, params) : key;

        const extractWhatsChanged = (body) => {
            if (!body) return '';
            const marker = "## What's Changed";
            const idx = body.indexOf(marker);
            if (idx === -1) return '';
            const afterMarker = body.substring(idx + marker.length);
            const nextHeading = afterMarker.indexOf('\n## ');
            let section = nextHeading !== -1 ? afterMarker.substring(0, nextHeading) : afterMarker;
            // Strip the "**Full Changelog**: ..." line
            section = section.replace(/\*\*Full Changelog\*\*:.*$/gm, '').trim();
            return section;
        };

        const parseMarkdownList = (text) => {
            const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
            const listItems = lines.map(line => {
                // Strip leading "* " or "- "
                const cleaned = line.replace(/^[\*\-]\s+/, '');
                return `<li class="mb-1 last:mb-0">${this.app.escapeHtml(cleaned)}</li>`;
            });
            return `<ul class="list-disc list-inside text-xs">${listItems.join('')}</ul>`;
        };

        // What's Changed Tab
        let changesHtml = '';
        if (releases && releases.length > 0) {
            for (const rel of releases) {
                const changes = extractWhatsChanged(rel.body);
                if (!changes) continue;
                changesHtml += `
                <div class="bg p-2 border-b last:border-0 text-left">
                    <div class="mb-2">
                        <a href="${this.app.escapeHtml(rel.url)}" target="_blank" class="font-mono text-xs bg-primary primary-text px-1 hover:bg-primary transition-colors">${this.app.escapeHtml(rel.tag)}</a>
                    </div>
                    ${parseMarkdownList(changes)}
                </div>`;
            }
        }

        // Commits Tab
        let commitsHtml = '';
        if (commits && commits.length > 0) {
            for (const c of commits) {
                commitsHtml += `
                <div class="border-b last:border-0 text-left">
                    <div class="flex items-center bg p-2 gap-2">
                        <a href="https://github.com/mrblomblo/blombooru/commit/${this.app.escapeHtml(c.hash)}" target="_blank" class="font-mono text-xs bg-primary primary-text px-1 hover:bg-primary transition-colors">${this.app.escapeHtml(c.hash)}</a>
                        <span class="text-xs">${this.app.escapeHtml(c.message)}</span>
                    </div>
                </div>`;
            }
        }

        const hasChanges = changesHtml.length > 0;
        const hasCommits = commitsHtml.length > 0;

        const tabLabelChanges = t('admin.update.tab_whats_changed');
        const tabLabelCommits = t('admin.update.tab_commits', { count: (commits || []).length });
        const noReleasesMsg = t('admin.update.no_release_notes');
        const noCommitsMsg = t('admin.update.no_commits');
        const fullChangelogMsg = t('admin.update.view_full_changelog', { current: current_version, latest: latest_version });

        // Build tabbed UI
        const tabsHtml = `
        <div>
            ${(hasChanges && hasCommits) ? `
            <div class="flex border-b mb-3" id="changelog-tabs">
                <button class="px-3 py-1 text-xs font-bold border-b-2 border-primary text-primary" data-tab="changes">${this.app.escapeHtml(tabLabelChanges)}</button>
                <button class="px-3 py-1 text-xs text-secondary hover:text-primary" data-tab="commits">${this.app.escapeHtml(tabLabelCommits)}</button>
            </div>` : ''}
            <div class="max-h-80 overflow-y-auto custom-scrollbar">
                <div id="tab-changes" ${!hasChanges ? 'style="display:none"' : ''}>${changesHtml || `<div class="text-xs text-secondary">${this.app.escapeHtml(noReleasesMsg)}</div>`}</div>
                <div id="tab-commits" style="display:${hasChanges ? 'none' : 'block'}">${commitsHtml || `<div class="text-xs text-secondary">${this.app.escapeHtml(noCommitsMsg)}</div>`}</div>
            </div>
            ${compare_url ? `<div class="mt-3 pt-2 border-t text-center"><a href="${this.app.escapeHtml(compare_url)}" target="_blank" class="text-xs text-primary hover:text-primary transition-colors">${this.app.escapeHtml(fullChangelogMsg)}</a></div>` : ''}
        </div>`;

        const modal = new ModalHelper({
            id: 'changelog-modal',
            type: 'info',
            title: window.i18n ? window.i18n.t('modal.changelog.title') : 'Changelog',
            message: tabsHtml,
            confirmText: window.i18n ? window.i18n.t('common.got_it') : 'Got it',
            cancelText: '',
            onConfirm: () => {
                modal.destroy();
            }
        });

        modal.show();

        // Wire up tab switching
        const tabContainer = document.getElementById('changelog-tabs');
        if (tabContainer) {
            tabContainer.querySelectorAll('button').forEach(btn => {
                btn.addEventListener('click', () => {
                    const tabName = btn.dataset.tab;
                    // Update active tab styles
                    tabContainer.querySelectorAll('button').forEach(b => {
                        b.classList.remove('border-b-2', 'border-primary', 'text-primary');
                        b.classList.add('text-secondary');
                    });
                    btn.classList.add('border-b-2', 'border-primary', 'text-primary');
                    btn.classList.remove('text-secondary');
                    // Show/hide tab content
                    document.getElementById('tab-changes').style.display = tabName === 'changes' ? 'block' : 'none';
                    document.getElementById('tab-commits').style.display = tabName === 'commits' ? 'block' : 'none';
                });
            });
        }
    }

    async performUpdate() {
        if (typeof ModalHelper === 'undefined') {
            console.error('ModalHelper not available');
            if (!confirm(window.i18n ? window.i18n.t('notifications.admin.update_confirm', { target: 'latest' }) : 'Update now?')) return;
            this._execute_update();
            return;
        }

        const modal = new ModalHelper({
            id: 'update-confirm-modal',
            type: 'warning',
            title: window.i18n ? window.i18n.t('common.system_update') : 'System Update',
            message: window.i18n ? window.i18n.t('modal.system_update.message', { target: 'latest' }) : 'Are you sure you want to update?',
            confirmText: window.i18n ? window.i18n.t('modal.system_update.confirm') : 'Update Now',
            cancelText: window.i18n ? window.i18n.t('common.cancel') : 'Cancel',
            onConfirm: () => {
                this._execute_update();
                modal.destroy();
            },
            onCancel: () => {
                modal.destroy();
            }
        });

        modal.show();
    }

    async _execute_update() {
        const resultDiv = document.getElementById('update-result');
        const resultLog = document.getElementById('update-result-log');
        if (resultDiv) resultDiv.classList.remove('hidden');
        if (resultLog) resultLog.textContent = window.i18n ? window.i18n.t('admin.messages.update_started') : 'Starting update...';

        try {
            const response = await app.apiCall('/api/system/update/perform', {
                method: 'POST',
                body: JSON.stringify({ target: 'latest' })
            });

            if (resultLog) {
                resultLog.textContent = (response.log || '') + "\n\n" + (response.message || '');
            }

            if (response.success) {
                app.showNotification(
                    window.i18n ? window.i18n.t('notifications.admin.update_initiated') : 'Update initiated',
                    'success'
                );
            }
        } catch (e) {
            if (resultLog) resultLog.textContent += `\nError: ${e.message}`;
            app.showNotification(
                window.i18n ? window.i18n.t('notifications.admin.update_failed', { error: e.message }) : `Update failed: ${e.message}`,
                'error'
            );
        }
    }

    async uploadFullBackup(file) {
        const statusDiv = document.getElementById('full-import-status');
        const progressDiv = document.getElementById('full-import-progress');

        statusDiv.style.display = 'block';
        progressDiv.innerHTML = `
            <div class="bg-primary primary-text p-3 mb-2">
                <strong>${window.i18n.t('admin.messages.uploading_importing_backup')}</strong><br>
                <div class="loader mt-2"></div>
                <span class="text-xs">${window.i18n.t('admin.messages.upload_warning_strong')}</span>
            </div>
            `;

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/admin/import/full', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Import failed');
            }

            const result = await response.json();

            progressDiv.innerHTML = `
                <div class="bg-success p-3 mb-2 tag-text">
                    <strong>${window.i18n.t('admin.messages.import_completed')}</strong>
                </div>
            `;

            // Reload all stats
            this.app.content.loadTagStats();
            this.app.content.loadMediaStats();
            this.app.content.loadAlbumStats();

        } catch (error) {
            progressDiv.innerHTML = `
                <div class="bg-danger p-3 tag-text">
                    <strong>Error:</strong> ${error.message}
                </div>
                `;
        }
    }

}
