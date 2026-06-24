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
            defaultSortElement.addEventListener('change', () => {
                this.updateDefaultOrderVisibility();
            });
        }

        const defaultOrderElement = document.getElementById('default-order');
        if (defaultOrderElement) {
            this.defaultOrderSelect = new CustomSelect(defaultOrderElement);
        }

        this.updateDefaultOrderVisibility();

        const popularTagsModeElement = document.getElementById('popular-tags-mode');
        if (popularTagsModeElement) {
            this.popularTagsModeSelect = new CustomSelect(popularTagsModeElement);
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
                new TagAutocomplete(el, { multipleValues: true, allowCreate: true });
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

        // Custom background
        this._customBgMediaId = null;
        this._settingsLoaded = false;

        const customBgSizeElement = document.getElementById('custom-bg-size');
        if (customBgSizeElement) {
            this.customBgSizeSelect = new CustomSelect(customBgSizeElement);
            customBgSizeElement.addEventListener('change', () => this._applyBgPreview());
        }

        // Custom themes
        const customThemeIsDarkEl = document.getElementById('custom-theme-is-dark');
        if (customThemeIsDarkEl) {
            this.customThemeIsDarkSelect = new CustomSelect(customThemeIsDarkEl);
        }

        const customThemeBackupEl = document.getElementById('custom-theme-backup');
        if (customThemeBackupEl) {
            this.customThemeBackupSelect = new CustomSelect(customThemeBackupEl);
        }

        const customThemesTbody = document.getElementById('custom-themes-tbody');
        if (customThemesTbody) {
            customThemesTbody.addEventListener('click', (e) => {
                const btn = e.target.closest('button[data-action]');
                if (!btn) return;
                const action = btn.dataset.action;
                const id = btn.dataset.themeId;
                const name = btn.dataset.themeName;
                if (action === 'edit') this.editCustomTheme(id);
                if (action === 'export') this.exportCustomTheme(id, name);
                if (action === 'delete') this.deleteCustomTheme(id, name);
            });
        }

        const addThemeBtn = document.getElementById('custom-theme-add-btn');
        if (addThemeBtn) {
            addThemeBtn.addEventListener('click', () => this.addCustomTheme());
        }

        const importBundleBtn = document.getElementById('custom-theme-import-bundle-btn');
        const importBundleInput = document.getElementById('custom-theme-file-bundle');
        if (importBundleBtn && importBundleInput) {
            importBundleBtn.addEventListener('click', () => importBundleInput.click());
            importBundleInput.addEventListener('change', (e) => {
                if (e.target.files[0]) this.importCustomTheme(e.target.files[0], 'bundle');
                e.target.value = '';
            });
        }

        const importCssBtn = document.getElementById('custom-theme-import-css-btn');
        const importCssInput = document.getElementById('custom-theme-file-css');
        if (importCssBtn && importCssInput) {
            importCssBtn.addEventListener('click', () => importCssInput.click());
            importCssInput.addEventListener('change', (e) => {
                if (e.target.files[0]) this.importCustomTheme(e.target.files[0], 'css');
                e.target.value = '';
            });
        }

        const cancelThemeBtn = document.getElementById('custom-theme-cancel-btn');
        if (cancelThemeBtn) {
            cancelThemeBtn.addEventListener('click', () => this._resetThemeForm());
        }

        // Slider <-> number input sync
        const sliderPairs = [
            ['custom-bg-opacity', 'custom-bg-opacity-val'],
            ['custom-bg-blur', 'custom-bg-blur-val'],
            ['custom-bg-brightness', 'custom-bg-brightness-val'],
            ['custom-bg-saturation', 'custom-bg-saturation-val'],
            ['custom-bg-contrast', 'custom-bg-contrast-val'],
            ['custom-bg-zoom', 'custom-bg-zoom-val'],
            ['custom-bg-position-x', 'custom-bg-position-x-val'],
            ['custom-bg-position-y', 'custom-bg-position-y-val'],
        ];
        sliderPairs.forEach(([sliderId, numId]) => {
            const slider = document.getElementById(sliderId);
            const num = document.getElementById(numId);
            if (!slider || !num) return;
            slider.addEventListener('input', () => { num.value = slider.value; this._applyBgPreview(); });
            num.addEventListener('input', () => {
                let v = parseInt(num.value);
                if (isNaN(v)) return;
                v = Math.max(parseInt(slider.min), Math.min(parseInt(slider.max), v));
                slider.value = v;
                num.value = v;
                this._applyBgPreview();
            });
        });

        // Enable toggle
        const bgEnabled = document.getElementById('custom-bg-enabled');
        const bgOptions = document.getElementById('custom-bg-options');
        if (bgEnabled && bgOptions) {
            bgEnabled.addEventListener('change', () => {
                bgOptions.style.display = bgEnabled.checked ? '' : 'none';
                this._applyBgPreview();
            });
        }

        // Select media button
        const selectBtn = document.getElementById('custom-bg-select-btn');
        if (selectBtn) {
            selectBtn.addEventListener('click', () => this._openBgMediaPicker());
        }

        // Remove media button
        const removeBtn = document.getElementById('custom-bg-remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', () => this._setBgMediaId(null));
        }
    }

    _openBgMediaPicker() {
        if (this._bgPicker) this._bgPicker.destroy();

        this._bgPicker = new MediaPickerModal({
            title: window.i18n.t('admin.settings.custom_background.select_media'),
            mode: 'single',
            getInitialItems: async () => {
                const params = new URLSearchParams({
                    sort: 'uploaded_at',
                    order: 'desc',
                    limit: 24,
                    page: 1,
                });
                const res = await fetch(`/api/search?${params.toString()}`, {
                    credentials: 'include'
                });
                if (!res.ok) return [];
                const data = await res.json();
                return data.items || [];
            },
            onSelect: (items) => {
                if (items.length > 0) {
                    this._setBgMediaId(items[0].id);
                }
            },
        });
        this._bgPicker.open();
    }

    _setBgMediaId(id) {
        this._customBgMediaId = id;
        const previewImg = document.getElementById('custom-bg-preview-img');
        const previewText = document.getElementById('custom-bg-preview-text');
        const removeBtn = document.getElementById('custom-bg-remove-btn');
        const selectBtn = document.getElementById('custom-bg-select-btn');

        if (id) {
            if (previewImg) {
                previewImg.src = `/api/media/${id}/thumbnail`;
                previewImg.style.display = '';
            }
            if (previewText) previewText.style.display = 'none';
            if (removeBtn) removeBtn.style.display = '';
            if (selectBtn) selectBtn.textContent = window.i18n.t('admin.settings.custom_background.change_media');
        } else {
            if (previewImg) { previewImg.src = ''; previewImg.style.display = 'none'; }
            if (previewText) previewText.style.display = '';
            if (removeBtn) removeBtn.style.display = 'none';
            if (selectBtn) selectBtn.textContent = window.i18n.t('admin.settings.custom_background.select_media');
        }

        this._applyBgPreview();
    }

    _applyBgPreview() {
        const bgEnabled = document.getElementById('custom-bg-enabled');
        const enabled = bgEnabled ? bgEnabled.checked : false;

        const el = document.getElementById('custom-background');

        if (!this._settingsLoaded) return;

        if (!enabled || !this._customBgMediaId) {
            if (el) el.style.display = 'none';
            return;
        }

        const get = (id, fallback) => {
            const elem = document.getElementById(id);
            if (!elem) return fallback;
            const val = parseInt(elem.value);
            return isNaN(val) ? fallback : val;
        };

        const opacity = get('custom-bg-opacity', 30);
        const blur = get('custom-bg-blur', 0);
        const brightness = get('custom-bg-brightness', 100);
        const saturation = get('custom-bg-saturation', 100);
        const contrast = get('custom-bg-contrast', 100);
        const zoom = get('custom-bg-zoom', 100);
        const posX = get('custom-bg-position-x', 50);
        const posY = get('custom-bg-position-y', 50);
        const size = this.customBgSizeSelect ? this.customBgSizeSelect.getValue() : 'cover';

        const bgSize = size === 'tile' ? 'auto' : size;
        const bgRepeat = size === 'tile' ? 'repeat' : 'no-repeat';

        // Create the div if it doesn't exist yet (e.g. first time enabling)
        let div = el;
        if (!div) {
            div = document.createElement('div');
            div.id = 'custom-background';
            document.body.insertBefore(div, document.body.firstChild);
        }

        const z = zoom / 100.0;
        const isIntrinsic = size === 'tile' || size === 'auto';
        const invZ = (isIntrinsic && z > 0 && z < 1.0) ? (1.0 / z) : 1.0;

        div.style.display = '';
        div.style.position = 'fixed';
        div.style.width = `${100 * invZ}%`;
        div.style.height = `${100 * invZ}%`;
        div.style.left = `${posX * (1.0 - invZ)}%`;
        div.style.top = `${posY * (1.0 - invZ)}%`;
        div.style.zIndex = '-1';
        div.style.pointerEvents = 'none';
        div.style.backgroundImage = `url('/api/media/${this._customBgMediaId}/file')`;
        div.style.backgroundSize = bgSize;
        div.style.backgroundPosition = `${posX}% ${posY}%`;
        div.style.backgroundRepeat = bgRepeat;
        div.style.transformOrigin = `${posX}% ${posY}%`;
        div.style.transform = `scale(${z})`;
        div.style.opacity = (opacity / 100).toFixed(2);
        div.style.filter = `blur(${blur}px) brightness(${brightness}%) saturate(${saturation}%) contrast(${contrast}%)`;
    }

    updateDefaultOrderVisibility() {
        const orderEl = document.getElementById('default-order');
        if (!orderEl || !this.defaultSortSelect) return;

        const isRandom = this.defaultSortSelect.getValue() === 'random';
        orderEl.classList.toggle('hidden', isRandom);
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
                this.updateDefaultOrderVisibility();
            }

            if (settings.default_order && this.defaultOrderSelect) {
                this.defaultOrderSelect.setValue(settings.default_order);
            }

            if (settings.popular_tags_mode && this.popularTagsModeSelect) {
                this.popularTagsModeSelect.setValue(settings.popular_tags_mode);
            }

            const popularTagsLimitInput = document.getElementById('popular-tags-limit');
            if (popularTagsLimitInput && settings.popular_tags_limit !== undefined) {
                popularTagsLimitInput.value = settings.popular_tags_limit;
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

            // Load custom background settings
            if (settings.custom_background) {
                const bg = settings.custom_background;
                const enabledCb = document.getElementById('custom-bg-enabled');
                if (enabledCb) {
                    enabledCb.checked = !!bg.enabled;
                    const opts = document.getElementById('custom-bg-options');
                    if (opts) opts.style.display = bg.enabled ? '' : 'none';
                }

                if (bg.media_id) {
                    this._setBgMediaId(bg.media_id);
                }

                if (this.customBgSizeSelect && bg.size) {
                    this.customBgSizeSelect.setValue(bg.size);
                }

                const sliderFields = [
                    ['custom-bg-opacity', 'custom-bg-opacity-val', 'opacity'],
                    ['custom-bg-blur', 'custom-bg-blur-val', 'blur'],
                    ['custom-bg-brightness', 'custom-bg-brightness-val', 'brightness'],
                    ['custom-bg-saturation', 'custom-bg-saturation-val', 'saturation'],
                    ['custom-bg-contrast', 'custom-bg-contrast-val', 'contrast'],
                    ['custom-bg-zoom', 'custom-bg-zoom-val', 'zoom'],
                    ['custom-bg-position-x', 'custom-bg-position-x-val', 'position_x'],
                    ['custom-bg-position-y', 'custom-bg-position-y-val', 'position_y'],
                ];
                sliderFields.forEach(([sliderId, numId, key]) => {
                    const val = bg[key];
                    if (val !== undefined && val !== null) {
                        const slider = document.getElementById(sliderId);
                        const num = document.getElementById(numId);
                        if (slider) slider.value = val;
                        if (num) num.value = val;
                    }
                });
            }

            this._settingsLoaded = true;
            this._applyBgPreview();
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
        const popularTagsMode = this.popularTagsModeSelect ? this.popularTagsModeSelect.getValue() : 'current_page';
        const popularTagsLimitRaw = document.getElementById('popular-tags-limit')?.value;
        const popularTagsLimit = popularTagsLimitRaw ? Math.max(1, Math.min(100, parseInt(popularTagsLimitRaw) || 20)) : 20;
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
            popular_tags_mode: popularTagsMode,
            popular_tags_limit: popularTagsLimit,
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
            },
            custom_background: {
                enabled: document.getElementById('custom-bg-enabled')?.checked || false,
                media_id: this._customBgMediaId || null,
                blur: parseInt(document.getElementById('custom-bg-blur')?.value || '0'),
                brightness: parseInt(document.getElementById('custom-bg-brightness')?.value || '100'),
                saturation: parseInt(document.getElementById('custom-bg-saturation')?.value || '100'),
                contrast: parseInt(document.getElementById('custom-bg-contrast')?.value || '100'),
                size: this.customBgSizeSelect ? this.customBgSizeSelect.getValue() : 'cover',
                position_x: parseInt(document.getElementById('custom-bg-position-x')?.value || '50'),
                position_y: parseInt(document.getElementById('custom-bg-position-y')?.value || '50'),
                opacity: parseInt(document.getElementById('custom-bg-opacity')?.value || '30')
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

    async loadCustomThemes() {
        try {
            const builtinData = await app.apiCall('/api/admin/builtin-themes').catch(e => {
                console.error('Failed to load builtin themes:', e);
                return { themes: [] };
            });
            this._builtinThemes = builtinData.themes || [];
            this._refreshBackupThemeDropdown(
                document.getElementById('custom-theme-backup'),
                'default_dark'
            );

            const customData = await app.apiCall('/api/admin/custom-themes').catch(e => {
                console.error('Failed to load custom themes:', e);
                return { themes: [] };
            });
            this._refreshCustomThemesTable(customData.themes || []);
        } catch (e) {
            console.error('Could not load custom themes:', e);
        }
    }

    _refreshBackupThemeDropdown(selectEl, selectedId) {
        if (!selectEl) return;
        const dropdown = selectEl.querySelector('.custom-select-dropdown');
        if (!dropdown) return;

        const themes = this._builtinThemes || [];
        dropdown.innerHTML = themes.map(t =>
            `<div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="${this.app.escapeHtml(t.id)}">${this.app.escapeHtml(t.name)}</div>`
        ).join('');

        // Preserve existing selection if no explicit selectedId passed, otherwise use the provided one
        const effectiveId = selectedId ?? (this.customThemeBackupSelect?.getValue() || 'default_dark');
        selectEl.dataset.value = effectiveId;

        if (this.customThemeBackupSelect && this.customThemeBackupSelect.element === selectEl) {
            this.customThemeBackupSelect.selectedValue = effectiveId;
            this.customThemeBackupSelect.initializeExistingOptions();
        }
    }

    _refreshCustomThemesTable(themes) {
        const tbody = document.getElementById('custom-themes-tbody');
        if (!tbody) return;

        if (!themes.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="3" class="py-4 px-3 text-xs text-secondary text-center">
                        ${window.i18n.t('admin.settings.custom_themes.no_custom_themes')}
                    </td>
                </tr>`;
            return;
        }

        tbody.innerHTML = '';
        for (const theme of themes) {
            const typeBadge = theme.is_dark
                ? `<span class="text-[10px] px-1.5 py-0.5 surface border">${window.i18n.t('admin.settings.custom_themes.type_dark')}</span>`
                : `<span class="text-[10px] px-1.5 py-0.5 surface border">${window.i18n.t('admin.settings.custom_themes.type_light')}</span>`;
            const activeMark = theme.is_active
                ? ' <span class="text-[10px] text-primary">&#9679;</span>' : '';

            const tr = document.createElement('tr');
            tr.className = 'border-b last:border-b-0 hover:surface transition-colors';
            tr.innerHTML = `
                <td class="py-2 px-3 text-xs"></td>
                <td class="py-2 px-3 text-xs">${typeBadge}</td>
                <td class="py-2 px-3 text-xs text-right">
                    <div class="flex justify-end gap-2">
                        <button type="button" class="btn text-xs px-2 py-1"
                            data-action="edit" data-theme-id="${this.app.escapeHtml(theme.id)}"
                            title="${window.i18n.t('admin.settings.custom_themes.edit')}">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                        <button type="button" class="btn text-xs px-2 py-1"
                            data-action="export" data-theme-id="${this.app.escapeHtml(theme.id)}"
                            title="${window.i18n.t('admin.settings.custom_themes.export')}">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        </button>
                        <button type="button" class="btn-danger text-xs px-2 py-1"
                            data-action="delete" data-theme-id="${this.app.escapeHtml(theme.id)}"
                            title="${window.i18n.t('common.delete')}">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                        </button>
                    </div>
                </td>`;

            // Set the name cell via textContent to avoid XSS
            tr.querySelector('td:first-child').textContent = theme.name;
            if (activeMark) {
                tr.querySelector('td:first-child').insertAdjacentHTML('beforeend', activeMark);
            }

            // Attach theme name to buttons via dataset (not eval'd as JS so should be safe)
            for (const btn of tr.querySelectorAll('button[data-action]')) {
                btn.dataset.themeName = theme.name;
            }

            tbody.appendChild(tr);
        }
    }

    async addCustomTheme() {
        const name = document.getElementById('custom-theme-name')?.value.trim();
        const css = document.getElementById('custom-theme-css')?.value.trim();
        const isDark = this.customThemeIsDarkSelect
            ? this.customThemeIsDarkSelect.getValue() === 'true'
            : true;
        const backupThemeId = this.customThemeBackupSelect
            ? this.customThemeBackupSelect.getValue()
            : 'default_dark';

        if (!name) {
            app.showNotification(window.i18n.t('admin.settings.custom_themes.errors.name_required'), 'error');
            return;
        }
        if (!css) {
            app.showNotification(window.i18n.t('admin.settings.custom_themes.css_required'), 'error');
            return;
        }

        const addBtn = document.getElementById('custom-theme-add-btn');
        if (addBtn) { addBtn.disabled = true; }

        try {
            if (this._editingThemeId) {
                // Update existing theme
                await app.apiCall(`/api/admin/custom-themes/${this._editingThemeId}`, {
                    method: 'PUT',
                    body: JSON.stringify({ name, is_dark: isDark, backup_theme_id: backupThemeId, css }),
                });
                app.showNotification(
                    window.i18n.t('admin.settings.custom_themes.theme_updated', { name }),
                    'success'
                );
            } else {
                // Create new theme
                await app.apiCall('/api/admin/custom-themes', {
                    method: 'POST',
                    body: JSON.stringify({ name, is_dark: isDark, css, backup_theme_id: backupThemeId }),
                });
                app.showNotification(
                    window.i18n.t('admin.settings.custom_themes.theme_added', { name }),
                    'success'
                );
            }
            this._resetThemeForm();
            await this.loadCustomThemes();
            await this.loadThemes();
        } catch (e) {
            const detail = e.message || '';
            app.showNotification(
                detail
                    ? window.i18n.t('admin.settings.custom_themes.invalid_css', { error: detail })
                    : window.i18n.t('admin.settings.custom_themes.invalid_css', { error: 'Unknown error' }),
                'error'
            );
        } finally {
            if (addBtn) { addBtn.disabled = false; }
        }
    }

    async importCustomTheme(file, mode) {
        const isBundle = mode === 'bundle';

        if (!isBundle) {
            // CSS import: populate the form so the user can set name, is_dark,
            // backup theme, etc., before proceeding.
            const css = await file.text();
            const suggestedName = file.name.replace(/\.css$/i, '').replace(/[_-]+/g, ' ').trim();

            document.getElementById('custom-theme-name').value = suggestedName;
            document.getElementById('custom-theme-css').value = css;

            document.getElementById('custom-theme-name')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            return;
        }

        // Bundle import: metadata is embedded in theme.json, import immediately.
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/admin/custom-themes/import', {
                method: 'POST',
                body: formData,
                credentials: 'include',
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Import failed' }));
                throw new Error(err.detail || 'Import failed');
            }
            const result = await response.json();
            const importedName = result.theme?.name || 'Unknown Theme';
            app.showNotification(
                window.i18n.t('admin.settings.custom_themes.theme_added', { name: importedName }),
                'success'
            );
            await this.loadCustomThemes();
            await this.loadThemes();
        } catch (e) {
            app.showNotification(e.message || 'Import failed', 'error');
        }
    }

    _resetThemeForm() {
        this._editingThemeId = null;

        document.getElementById('custom-theme-name').value = '';
        const defaultTemplate = `:root {
  --primary-color: 
  --primary-hover: color-mix(in srgb, var(--primary-color) 70%, var(--background));
  --background: 
  --surface: 
  --surface-hover: color-mix(in srgb, var(--surface) 85%, white);
  --surface-light: 
  --surface-light-hover: color-mix(in srgb, var(--surface-light) 85%, white);
  --text: 
  --text-secondary: 
  --text-tertiary: 
  --tag-text: 
  --primary-text: 
  --border: 

  --white: 
  --black: 
  --green: 
  --orange: 
  --red: 
  --blue: 

  --tag-artist: 
  --tag-character: 
  --tag-copyright: 
  --tag-general: 
  --tag-meta: 
}`;
        document.getElementById('custom-theme-css').value = defaultTemplate;

        if (this.customThemeIsDarkSelect) {
            const el = document.getElementById('custom-theme-is-dark');
            if (el) {
                el.dataset.value = 'true';
                this.customThemeIsDarkSelect.selectedValue = 'true';
                this.customThemeIsDarkSelect.initializeExistingOptions();
            }
        }

        const backupEl = document.getElementById('custom-theme-backup');
        if (backupEl) {
            this._refreshBackupThemeDropdown(backupEl, 'default_dark');
        }

        const addBtn = document.getElementById('custom-theme-add-btn');
        if (addBtn) addBtn.textContent = window.i18n.t('admin.settings.custom_themes.add_theme');

        const importBundleBtn = document.getElementById('custom-theme-import-bundle-btn');
        if (importBundleBtn) importBundleBtn.style.display = '';

        const importCssBtn = document.getElementById('custom-theme-import-css-btn');
        if (importCssBtn) importCssBtn.style.display = '';

        const cancelBtn = document.getElementById('custom-theme-cancel-btn');
        if (cancelBtn) cancelBtn.style.display = 'none';
    }

    async editCustomTheme(themeId) {
        let theme = null;
        try {
            const data = await app.apiCall('/api/admin/custom-themes');
            theme = (data.themes || []).find(t => t.id === themeId);
            if (!theme) return;
        } catch (e) {
            console.error('Could not fetch theme data for edit:', e);
            return;
        }

        let css = '';
        try {
            const cssResp = await fetch(`/data/themes/${themeId}.css?_=${Date.now()}`);
            if (cssResp.ok) css = await cssResp.text();
        } catch (e) {
            console.error('Could not fetch CSS for edit:', e);
        }

        this._editingThemeId = themeId;

        document.getElementById('custom-theme-name').value = theme.name;
        document.getElementById('custom-theme-css').value = css;

        const isDarkVal = theme.is_dark ? 'true' : 'false';
        const isDarkEl = document.getElementById('custom-theme-is-dark');
        if (isDarkEl) {
            isDarkEl.dataset.value = isDarkVal;
            if (this.customThemeIsDarkSelect) {
                this.customThemeIsDarkSelect.selectedValue = isDarkVal;
                this.customThemeIsDarkSelect.initializeExistingOptions();
            }
        }

        const backupEl = document.getElementById('custom-theme-backup');
        if (backupEl) {
            this._refreshBackupThemeDropdown(backupEl, theme.backup_theme_id || 'default_dark');
        }

        const addBtn = document.getElementById('custom-theme-add-btn');
        if (addBtn) addBtn.textContent = window.i18n.t('admin.settings.custom_themes.save_theme');

        const importBundleBtn = document.getElementById('custom-theme-import-bundle-btn');
        if (importBundleBtn) importBundleBtn.style.display = 'none';

        const importCssBtn = document.getElementById('custom-theme-import-css-btn');
        if (importCssBtn) importCssBtn.style.display = 'none';

        const cancelBtn = document.getElementById('custom-theme-cancel-btn');
        if (cancelBtn) cancelBtn.style.display = '';

        document.getElementById('custom-theme-name')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    async deleteCustomTheme(themeId, themeName) {
        const modal = new ModalHelper({
            id: 'delete-custom-theme-modal',
            type: 'danger',
            title: window.i18n.t('common.delete'),
            message: window.i18n.t('admin.settings.custom_themes.confirm_delete', { name: themeName }),
            confirmText: window.i18n.t('common.delete'),
            cancelText: window.i18n.t('common.cancel'),
            confirmId: 'delete-custom-theme-confirm',
            cancelId: 'delete-custom-theme-cancel',
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/admin/custom-themes/${themeId}`, { method: 'DELETE' });
                    app.showNotification(
                        window.i18n.t('admin.settings.custom_themes.theme_deleted', { name: themeName }),
                        'success'
                    );
                    // Reset form if theme was being edited
                    if (this._editingThemeId === themeId) this._resetThemeForm();
                    await this.loadCustomThemes();
                    await this.loadThemes();
                } catch (e) {
                    const msg = e.message || '';
                    if (msg.includes('active')) {
                        app.showNotification(window.i18n.t('admin.settings.custom_themes.errors.cannot_delete_active'), 'error');
                    } else {
                        app.showNotification(msg || 'Delete failed', 'error');
                    }
                }
            },
        });
        modal.show();
    }

    async exportCustomTheme(themeId, themeName) {
        try {
            const response = await fetch(`/api/admin/custom-themes/${themeId}/export`, {
                credentials: 'include',
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Export failed' }));
                throw new Error(err.detail || 'Export failed');
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            const safeName = themeName.replace(/[^\w\-]/g, '_');
            a.href = url;
            a.download = `${safeName}.blombooru-theme`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            app.showNotification(e.message || 'Export failed', 'error');
        }
    }
}
