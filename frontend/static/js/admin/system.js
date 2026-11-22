class AdminSystem {
    constructor(adminPanel) {
        this.app = adminPanel;
        this._currentThemeId = null;
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
                this.updateDefaultOrderState();
            });
        }

        const defaultOrderElement = document.getElementById('default-order');
        if (defaultOrderElement) {
            this.defaultOrderSelect = new CustomSelect(defaultOrderElement);
        }

        this.updateDefaultOrderState();

        const popularTagsModeElement = document.getElementById('popular-tags-mode');
        if (popularTagsModeElement) {
            this.popularTagsModeSelect = new CustomSelect(popularTagsModeElement);
        }

        const sidebarFilterModeElement = document.getElementById('sidebar-filter-mode');
        if (sidebarFilterModeElement) {
            this.sidebarFilterModeSelect = new CustomSelect(sidebarFilterModeElement);
            this.customButtons = [];
            this.customButtonInstances = [];

            sidebarFilterModeElement.addEventListener('change', () => {
                this.updateSidebarFilterState();
            });
        }

        this.updateSidebarFilterState();

        const addCustomButtonBtn = document.getElementById('add-custom-button-btn');
        if (addCustomButtonBtn) {
            addCustomButtonBtn.addEventListener('click', () => this.addCustomButton());
        }


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
                if (!bgEnabled.checked) {
                    this.saveCustomBackground();
                }
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

        // Similarity weights input constraints
        const simCats = ['artist', 'character', 'general', 'copyright', 'meta'];
        simCats.forEach(cat => {
            const el = document.getElementById(`sim-weight-${cat}`);
            if (!el) return;

            el.addEventListener('keydown', (e) => {
                if (['e', 'E', '+', '-'].includes(e.key)) {
                    e.preventDefault();
                }
            });

            el.addEventListener('input', () => {
                let val = el.value;
                if (val === '') return;
                const parts = val.split('.');
                if (parts[0].length > 2) {
                    parts[0] = parts[0].slice(0, 2);
                }
                if (parts.length > 1 && parts[1].length > 2) {
                    parts[1] = parts[1].slice(0, 2);
                }
                const newVal = parts.join('.');
                if (newVal !== val) {
                    el.value = newVal;
                }
                if (parseFloat(el.value) > 99.99) {
                    el.value = '99.99';
                }
            });

            el.addEventListener('blur', () => {
                if (el.value === '') return;
                const num = parseFloat(el.value);
                if (isNaN(num)) {
                    el.value = '';
                } else {
                    const clamped = Math.min(99.99, Math.max(0, num));
                    el.value = parseFloat(clamped.toFixed(2)).toString();
                }
            });
        });
    }

    updateDefaultOrderState() {
        if (!this.defaultOrderSelect) return;

        const isRandom = this.defaultSortSelect?.getValue() === 'random';
        this.defaultOrderSelect.setDisabled(isRandom);
    }

    updateSidebarFilterState() {
        if (!this.sidebarFilterModeSelect) return;

        const mode = this.sidebarFilterModeSelect.getValue();
        const isCustom = mode === 'custom' || mode === 'both';

        const customContainer = document.getElementById('custom-buttons-container');
        if (customContainer) {
            customContainer.style.display = isCustom ? 'block' : 'none';
        }
    }

    async loadSettings() {
        try {
            const response = await fetch('/api/admin/settings');

            if (!response.ok) {
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
                this.updateDefaultOrderState();
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

            if (settings.blur_explicit_thumbnails !== undefined) {
                const blurExplicitCheckbox = document.getElementById('blur-explicit-thumbnails');
                if (blurExplicitCheckbox) blurExplicitCheckbox.checked = settings.blur_explicit_thumbnails;
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
            }

            this.updateSidebarFilterState();

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

            // Load similarity weights
            const simCats = ['artist', 'character', 'general', 'copyright', 'meta'];
            if (settings.similarity_weights) {
                simCats.forEach(cat => {
                    const el = document.getElementById(`sim-weight-${cat}`);
                    if (el && settings.similarity_weights[cat] !== undefined) {
                        el.value = settings.similarity_weights[cat];
                    }
                });
            }

            // Load booru proxy setting
            if (settings.booru_proxy_url !== undefined) {
                const proxyInput = document.getElementById('booru-proxy-url');
                if (proxyInput) proxyInput.value = settings.booru_proxy_url || '';
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

            // Load auto_apply_ai_tags settings
            if (settings.auto_apply_ai_tags !== undefined) {
                const autoApplyAiTagsCheckbox = document.getElementById('auto-apply-ai-tags');
                if (autoApplyAiTagsCheckbox) {
                    autoApplyAiTagsCheckbox.checked = !!settings.auto_apply_ai_tags;
                }
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
        const blurExplicitThumbnails = document.getElementById('blur-explicit-thumbnails')?.checked || false;

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
        if ((sidebarMode === 'custom' || sidebarMode === 'both') && validButtons.length === 0) {
            app.showNotification(window.i18n.t('notifications.admin.error_custom_button_required'), 'error');
            return;
        }

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
            blur_explicit_thumbnails: blurExplicitThumbnails,
            sidebar_filter_mode: sidebarMode,
            sidebar_custom_buttons: validButtons
        };

        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify(settings)
            });

            const headerLogoTitle = document.getElementById('header-logo-title');
            if (headerLogoTitle) {
                headerLogoTitle.textContent = appName;
            }
            const headerLogoImg = document.getElementById('header-logo-img');
            if (headerLogoImg) {
                headerLogoImg.setAttribute('alt', appName);
            }
            const footerAppName = document.getElementById('footer-app-name');
            if (footerAppName) {
                footerAppName.textContent = appName;
            }
            if (document.title.includes(' - ')) {
                const parts = document.title.split(' - ');
                parts[parts.length - 1] = appName;
                document.title = parts.join(' - ');
            } else if (document.title === window._appName) {
                document.title = appName;
            }
            window._appName = appName;

            if (this._currentThemeId !== theme) {
                let themes = this._themes || [];
                let targetTheme = themes.find(t => t.id === theme);
                if (!targetTheme) {
                    try {
                        const themeResp = await fetch('/api/admin/themes');
                        if (themeResp.ok) {
                            const themeData = await themeResp.json();
                            this._themes = themeData.themes || [];
                            targetTheme = this._themes.find(t => t.id === theme);
                        }
                    } catch (e) {
                        console.error('Error fetching themes for on-the-fly update:', e);
                    }
                }
                if (targetTheme && targetTheme.css_path) {
                    const themeLink = document.getElementById('theme-stylesheet');
                    if (themeLink) {
                        themeLink.href = `${targetTheme.css_path}?v=${Date.now()}`;
                    }
                }
                this._currentThemeId = theme;
            }
            await this.loadThemes();

            app.showNotification(window.i18n.t('notifications.admin.settings_updated'), 'success');
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_saving_settings'));
        }
    }

    async loadThemes() {
        try {
            const response = await fetch('/api/admin/themes');
            const data = await response.json();
            this._themes = data.themes || [];
            if (data.current_theme) {
                this._currentThemeId = data.current_theme;
            }

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
}
