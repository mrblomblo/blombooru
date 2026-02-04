class AdminPanel {
    constructor() {
        this.aliasCache = new Set();
        this.tagInputHelper = new TagInputHelper();
        this.validationTimeout = null;
        this.themeSelect = null;
        this.languageSelect = null;
        this.statsModule = null;
        window.adminPanel = this;
        this.init();
    }

    async init() {
        await this.checkAuth();

        this.setupTagAutocomplete();
        this.setupEventListeners();
        this.loadSettings();
        this.setupTagManagement();
        this.setupAlbumManagement();
        this.loadTagStats();
        this.loadMediaStats();
        this.loadAlbumStats();
        this.setupCustomSelects();
        this.loadThemes();
        this.loadLanguages();
        this.setupApiKeyManagement();
        this.setupSystemUpdate();
        this.setupStats();
        this.setupTabs();
    }

    // Helper to escape HTML and prevent XSS
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    setupTagAutocomplete() {
        const tagsSearch = document.getElementById('tag-search-input');
        if (tagsSearch && typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(tagsSearch, {
                multipleValues: true
            });
        }
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
    }

    async checkAuth() {
        try {
            const response = await fetch('/api/admin/settings');
            if (response.ok) {
                document.getElementById('settings-section').style.display = 'block';

                app.updateAuthStatus(true);
                await this.enableAdminMode();

                return true;
            } else {
                window.location.href = '/login?return=/admin';
                return false;
            }
        } catch (error) {
            console.error('Error checking auth:', error);
            window.location.href = '/login?return=/admin';
            return false;
        }
    }

    async enableAdminMode() {
        try {
            const response = await fetch('/api/admin/toggle-admin-mode?enabled=true', {
                method: 'POST'
            });

            if (response.ok) {
                app.isAdminMode = true;
                app.updateUI();
            }
        } catch (error) {
            console.error('Error enabling admin mode:', error);
        }
    }

    setupEventListeners() {
        // Settings form
        const settingsForm = document.getElementById('settings-form');
        if (settingsForm) {
            settingsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.saveSettings();
            });
        }

        // Scan media button
        const scanBtn = document.getElementById('scan-media-btn');
        if (scanBtn) {
            scanBtn.addEventListener('click', () => this.scanMedia());
        }

        // Add tags form
        const addTagsForm = document.getElementById('add-tags-form');
        if (addTagsForm) {
            addTagsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.addNewTags();
            });
        }

        // Change password form
        const changePasswordForm = document.getElementById('change-admin-password-form');
        if (changePasswordForm) {
            changePasswordForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.changePassword();
            });
        }

        // Change username form
        const changeUsernameForm = document.getElementById('change-admin-username-form');
        if (changeUsernameForm) {
            changeUsernameForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.changeUsername();
            });
        }

        // Redis settings toggle
        const redisEnabled = document.getElementById('redis-enabled');
        if (redisEnabled) {
            redisEnabled.addEventListener('change', (e) => {
                const container = document.getElementById('redis-settings-container');
                if (container) container.style.display = e.target.checked ? 'block' : 'none';
            });
        }

        // Redis test button
        const testRedisBtn = document.getElementById('test-redis-btn');
        if (testRedisBtn) {
            testRedisBtn.addEventListener('click', () => this.testRedisConnection());
        }
    }

    setupTabs() {
        const tabButtons = document.querySelectorAll('.tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');

        if (tabButtons.length === 0) return;

        const switchTab = (tabId) => {
            tabButtons.forEach(btn => {
                if (btn.dataset.tab === tabId) {
                    btn.classList.add('text-primary', 'border-primary');
                    btn.classList.remove('border-transparent');
                } else {
                    btn.classList.remove('text-primary', 'border-primary');
                    btn.classList.add('border-transparent');
                }
            });

            tabContents.forEach(content => {
                if (content.id === `tab-${tabId}`) {
                    content.classList.remove('hidden');
                } else {
                    content.classList.add('hidden');
                }
            });

            if (tabId === 'stats' && this.statsModule && !this.statsModule.isInitialized) {
                this.statsModule.init();
            }

            localStorage.setItem('admin_active_tab', tabId);
        };

        tabButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                switchTab(btn.dataset.tab);
            });
        });

        // Initialize from local storage or default
        const savedTab = localStorage.getItem('admin_active_tab');
        const defaultTab = 'content';

        if (savedTab && document.querySelector(`.tab-btn[data-tab="${savedTab}"]`)) {
            switchTab(savedTab);
        } else {
            switchTab(defaultTab);
        }

        // If stats tab is active after initialization, ensure it's loaded
        if ((savedTab === 'stats' || defaultTab === 'stats') && this.statsModule) {
            setTimeout(() => {
                if (this.statsModule && !this.statsModule.isInitialized) {
                    this.statsModule.init();
                }
            }, 100);
        }
    }

    setupStats() {
        if (typeof AdminStats !== 'undefined') {
            this.statsModule = new AdminStats();
        }
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

    async changePassword() {
        const newPassword = document.getElementById('new-admin-password').value;
        const statusDiv = document.getElementById('change-password-status');
        const resultDiv = document.getElementById('change-password-result');

        try {
            const result = await app.apiCall('/api/admin/update-admin-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_password: newPassword })
            });

            statusDiv.style.display = 'block';
            resultDiv.className = 'text-success';
            resultDiv.textContent = window.i18n.t('notifications.admin.password_updated');

            // Clear the password field
            document.getElementById('new-admin-password').value = '';

            // Hide success message after 3 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);

        } catch (error) {
            statusDiv.style.display = 'block';
            resultDiv.className = 'text-danger';
            resultDiv.textContent = error.message;
        }
    }

    async changeUsername() {
        const newUsername = document.getElementById('new-admin-username').value;
        const statusDiv = document.getElementById('change-username-status');
        const resultDiv = document.getElementById('change-username-result');

        try {
            const result = await app.apiCall('/api/admin/update-admin-username', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_username: newUsername })
            });

            statusDiv.style.display = 'block';
            resultDiv.className = 'text-success';
            resultDiv.textContent = window.i18n.t('notifications.admin.username_updated', { username: result.new_username });

            // Update displayed username if you show it anywhere
            app.showNotification(window.i18n.t('notifications.admin.username_updated', { username: result.new_username }), 'success');

            // Clear the username field
            document.getElementById('new-admin-username').value = '';

            // Hide success message after 3 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);

        } catch (error) {
            statusDiv.style.display = 'block';
            resultDiv.className = 'text-danger';
            resultDiv.textContent = error.message;
        }
    }

    // Helper methods for tag validation
    parseTagWithCategory(tagString) {
        const prefixes = ['artist:', 'copyright:', 'character:', 'meta:'];
        const normalized = tagString.trim().toLowerCase();

        for (const prefix of prefixes) {
            if (normalized.startsWith(prefix)) {
                const category = prefix.slice(0, -1); // Remove the colon
                const tagName = normalized.slice(prefix.length).trim();
                return { tagName, category };
            }
        }

        // No prefix, default to general
        return { tagName: normalized, category: 'general' };
    }

    async validateAndStyleNewTags() {
        const tagsInput = document.getElementById('new-tags-input');
        if (!tagsInput) return;

        await this.tagInputHelper.validateAndStyleTags(tagsInput, {
            validationCache: this.tagInputHelper.tagValidationCache,
            checkFunction: (tag) => {
                const { tagName } = this.parseTagWithCategory(tag);
                return this.tagInputHelper.checkTagOrAliasExists(tagName);
            },
            invertLogic: true
        });
    }

    setupNewTagsInput() {
        const tagsInput = document.getElementById('new-tags-input');
        if (!tagsInput) return;

        this.tagInputHelper.setupTagInput(tagsInput, 'new-tags-input', {
            onValidate: () => { },
            checkFunction: (tag) => {
                const { tagName } = this.parseTagWithCategory(tag);
                return this.tagInputHelper.checkTagOrAliasExists(tagName);
            },
            invertLogic: true
        });
    }

    async addNewTags() {
        const tagsInput = document.getElementById('new-tags-input');
        const statusDiv = document.getElementById('add-tags-status');
        const resultDiv = document.getElementById('add-tags-result');

        const text = this.tagInputHelper.getPlainTextFromDiv(tagsInput);
        const tagStrings = text.split(/\s+/).filter(t => t.length > 0);

        if (tagStrings.length === 0) {
            app.showNotification(window.i18n.t('notifications.admin.enter_at_least_one_tag'), 'error');
            return;
        }

        // Parse and filter tags
        const tagsToCreate = [];
        const ignoredTags = [];

        for (const tagString of tagStrings) {
            const { tagName, category } = this.parseTagWithCategory(tagString);
            const shouldIgnore = this.tagInputHelper.tagValidationCache.get(tagName);

            if (shouldIgnore) {
                ignoredTags.push(tagString);
            } else {
                tagsToCreate.push({ name: tagName, category });
            }
        }

        if (tagsToCreate.length === 0) {
            app.showNotification(window.i18n.t('notifications.admin.tags_already_exist'), 'error', window.i18n.t('notifications.admin.nothing_to_add'));
            return;
        }

        // Show loading
        statusDiv.style.display = 'block';
        resultDiv.innerHTML = `
            <div class="bg-primary primary-text p-3 mb-2">
                <strong>${window.i18n.t('admin.messages.adding_tags')}</strong>
            </div>
        `;

        try {
            const response = await app.apiCall('/api/admin/bulk-create-tags', {
                method: 'POST',
                body: JSON.stringify({ tags: tagsToCreate })
            });

            let html = `
                <div class="bg-success p-3 mb-2 tag-text">
                    <strong>${window.i18n.t('notifications.admin.tags_added_successfully')}</strong>
                </div>
                <div class="text-secondary space-y-1">
                    <div>${window.i18n.t('notifications.admin.tags_created')} <strong class="text">${response.created}</strong></div>
                    <div>${window.i18n.t('notifications.admin.tags_skipped')} <strong class="text">${response.skipped}</strong></div>
                    <div>${window.i18n.t('notifications.admin.tags_errors')} <strong class="text">${response.errors.length}</strong></div>
                </div>
            `;

            if (ignoredTags.length > 0) {
                html += `
                    <div class="mt-2 p-2 surface-light border text-xs">
                        <strong>${window.i18n.t('notifications.admin.tags_ignored')}</strong><br>
                        ${ignoredTags.join(', ')}
                    </div>
                `;
            }

            if (response.errors.length > 0) {
                html += `
                    <div class="mt-2 p-2 bg-warning tag-text text-xs">
                        <strong>${window.i18n.t('notifications.admin.tags_errors')}</strong><br>
                        ${response.errors.slice(0, 5).map(app.translateError).join('<br>')}
                    </div>
                `;
            }

            resultDiv.innerHTML = html;

            // Clear input and cache
            tagsInput.textContent = '';
            this.tagInputHelper.clearCache();

            // Reload stats
            await this.loadTagStats();

        } catch (error) {
            resultDiv.innerHTML = `
                <div class="bg-danger p-3 tag-text">
                    <strong>Error:</strong> ${error.message}
                </div>
            `;
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
                if (hostInput) hostInput.value = settings.redis.host || 'localhost';

                const portInput = document.getElementById('redis-port');
                if (portInput) portInput.value = settings.redis.port || 6379;

                const dbInput = document.getElementById('redis-db');
                if (dbInput) dbInput.value = settings.redis.db || 0;

                const passwordInput = document.getElementById('redis-password');
                if (passwordInput) passwordInput.value = settings.redis.password || '';
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
            host: document.getElementById('redis-host')?.value || 'localhost',
            port: parseInt(document.getElementById('redis-port')?.value || '6379'),
            db: parseInt(document.getElementById('redis-db')?.value || '0'),
            password: document.getElementById('redis-password')?.value || ''
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
            redis: redisSettings
        };

        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify(settings)
            });

            location.reload();
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_saving_settings'));
        }
    }

    async scanMedia() {
        const scanBtn = document.getElementById('scan-media-btn');
        const originalText = scanBtn.textContent;
        scanBtn.disabled = true;
        scanBtn.textContent = window.i18n.t('admin.actions.scanning');

        try {
            const result = await app.apiCall('/api/admin/scan-media', {
                method: 'POST'
            });

            if (result.new_files === 0) {
                app.showNotification(window.i18n.t('notifications.admin.no_untracked_media'), 'info');
                scanBtn.disabled = false;
                scanBtn.textContent = originalText;
                return;
            }

            // Show loading message
            scanBtn.textContent = window.i18n.t('admin.messages.scan_loading', { count: result.new_files });

            // Get the uploader instance
            const uploader = window.uploaderInstance;
            if (!uploader) {
                app.showNotification(window.i18n.t('notifications.admin.refresh_and_retry'), 'error', window.i18n.t('notifications.admin.uploader_not_initialized'));
                scanBtn.disabled = false;
                scanBtn.textContent = originalText;
                return;
            }

            // Fetch and add each file to the uploader
            let loadedCount = 0;
            let skippedCount = 0;
            let duplicateCount = 0;

            for (const filePath of result.files) {
                try {
                    // Check if file is already in the upload queue
                    if (uploader.isFileQueued(filePath)) {
                        duplicateCount++;
                        continue;
                    }

                    scanBtn.textContent = window.i18n.t('admin.messages.scan_progress', { current: loadedCount + 1, total: result.new_files });

                    // Fetch the file from the server
                    const response = await fetch(`/api/admin/get-untracked-file?path=${encodeURIComponent(filePath)}`);

                    if (!response.ok) {
                        console.error(`Failed to fetch file: ${filePath}`);
                        skippedCount++;
                        continue;
                    }

                    const blob = await response.blob();
                    const filename = filePath.split('/').pop().split('\\').pop(); // Handle both Unix and Windows paths
                    const file = new File([blob], filename, { type: blob.type });

                    // Add to uploader
                    await uploader.addScannedFile(file, filePath);
                    loadedCount++;

                } catch (error) {
                    console.error(`Error loading file ${filePath}:`, error);
                    skippedCount++;
                }
            }

            // Show results
            let message = '';
            if (loadedCount > 0) {
                message = `Loaded ${loadedCount} file(s) into the editor.`;
            }
            if (duplicateCount > 0) {
                message += `${message ? '\n' : ''}${duplicateCount} file(s) already in queue.`;
            }
            if (skippedCount > 0) {
                message += `${message ? '\n' : ''}${skippedCount} file(s) skipped due to errors.`;
            }
            if (loadedCount > 0) {
                message += '\n\nYou can now edit tags and ratings before submitting.';
            }

            const notificationType = loadedCount > 0 ? 'success' : (duplicateCount > 0 ? 'info' : 'warning');
            app.showNotification(message, notificationType);

        } catch (error) {
            console.error('Scan error:', error);
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_scanning_media'));
        } finally {
            scanBtn.disabled = false;
            scanBtn.textContent = originalText;
        }
    }

    setupTagManagement() {
        // Setup new tags input validation
        this.setupNewTagsInput();

        // CSV upload
        const uploadArea = document.getElementById('csv-upload-area');
        const fileInput = document.getElementById('csv-file-input');

        uploadArea?.addEventListener('click', () => fileInput?.click());

        uploadArea?.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.style.backgroundColor = '#334155';
        });

        uploadArea?.addEventListener('dragleave', () => {
            uploadArea.style.backgroundColor = '';
        });

        uploadArea?.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.style.backgroundColor = '';

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.uploadCSV(files[0]);
            }
        });

        fileInput?.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.uploadCSV(e.target.files[0]);
            }
        });

        // Full Backup Import
        const fullImportArea = document.getElementById('full-import-area');
        const fullImportInput = document.getElementById('full-import-input');

        fullImportArea?.addEventListener('click', () => fullImportInput?.click());

        fullImportArea?.addEventListener('dragover', (e) => {
            e.preventDefault();
            fullImportArea.style.backgroundColor = '#334155';
        });

        fullImportArea?.addEventListener('dragleave', () => {
            fullImportArea.style.backgroundColor = '';
        });

        fullImportArea?.addEventListener('drop', (e) => {
            e.preventDefault();
            fullImportArea.style.backgroundColor = '';

            if (e.dataTransfer.files.length > 0) {
                this.uploadFullBackup(e.dataTransfer.files[0]);
            }
        });

        fullImportInput?.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.uploadFullBackup(e.target.files[0]);
            }
        });

        // Tag search
        const searchBtn = document.getElementById('tag-search-btn');
        const searchInput = document.getElementById('tag-search-input');

        searchInput?.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/\s+/g, '_');
        });

        searchInput?.addEventListener('keydown', (e) => {
            if (e.key === ' ') {
                e.preventDefault();
                e.target.value += '_';
            }
        });

        searchBtn?.addEventListener('click', () => this.searchTags());
        searchInput?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.target.value = e.target.value.replace(/\s+/g, '_').trim();
                this.searchTags();
            }
        });

        // Clear tags
        const clearBtn = document.getElementById('clear-tags-btn');
        clearBtn?.addEventListener('click', () => this.clearAllTags());
    }

    async loadTagStats() {
        try {
            const response = await fetch('/api/admin/tag-stats');
            const stats = await response.json();

            const totalTagsEl = document.getElementById('total-tags');
            const totalAliasesEl = document.getElementById('total-aliases');

            if (totalTagsEl) totalTagsEl.textContent = stats.total_tags;
            if (totalAliasesEl) totalAliasesEl.textContent = stats.total_aliases;
        } catch (error) {
            console.error('Error loading tag stats:', error);
        }
    }

    async loadMediaStats() {
        try {
            const response = await fetch('/api/admin/media-stats');
            const stats = await response.json();

            const totalMediaEl = document.getElementById('total-media');
            const totalImagesEl = document.getElementById('total-images');
            const totalGifsEl = document.getElementById('total-gifs');
            const totalVideosEl = document.getElementById('total-videos');

            if (totalMediaEl) totalMediaEl.textContent = stats.total_media;
            if (totalImagesEl) totalImagesEl.textContent = stats.total_images;
            if (totalGifsEl) totalGifsEl.textContent = stats.total_gifs;
            if (totalVideosEl) totalVideosEl.textContent = stats.total_videos;
        } catch (error) {
            console.error('Error loading media stats:', error);
        }
    }

    async uploadCSV(file) {
        const statusDiv = document.getElementById('csv-import-status');
        const progressDiv = document.getElementById('csv-import-progress');

        statusDiv.style.display = 'block';
        progressDiv.innerHTML = `
            <div class="bg-primary primary-text p-3 mb-2">
                <strong>${window.i18n.t('admin.messages.uploading_processing')}</strong><br>
                <span class="text-xs">${window.i18n.t('admin.messages.upload_warning')}</span>
            </div>
        `;

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/admin/import-tags-csv', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const result = await response.json();

            let html = `
                <div class="bg-success p-3 mb-2 tag-text">
                    <strong>${result.message_key ? window.i18n.t(result.message_key) : result.message}</strong>
                </div>
                <div class="text-secondary space-y-1">
                    <div>Rows processed: <strong class="text">${result.rows_processed}</strong></div>
                    <div>Tags created: <strong class="text">${result.tags_created}</strong></div>
                    <div>Tags updated: <strong class="text">${result.tags_updated}</strong></div>
                    <div>Aliases created: <strong class="text">${result.aliases_created}</strong></div>
                </div>
            `;

            if (result.skipped_long_tags > 0 || result.skipped_long_aliases > 0) {
                html += `
                    <div class="pt-2 border-t mt-2">
                        <div class="text-warning">${window.i18n.t('admin.messages.skipped_too_long')}</div>
                        ${result.skipped_long_tags > 0 ? `<div>Tags: <strong class="text">${result.skipped_long_tags}</strong></div>` : ''}
                        ${result.skipped_long_aliases > 0 ? `<div>Aliases: <strong class="text">${result.skipped_long_aliases}</strong></div>` : ''}
                    </div>
                `;
            }

            html += '</div>';

            if (result.errors && result.errors.length > 0) {
                html += `
                    <div class="bg-warning p-3 mt-2 tag-text text-xs">
                        <strong>${window.i18n.t('admin.messages.warnings_total', { total: result.total_errors })}</strong><br>
                        ${result.errors.slice(0, 5).map(app.translateError).join('<br>')}
                    </div>
                `;
            }

            progressDiv.innerHTML = html;

            // Reload stats
            await this.loadTagStats();

        } catch (error) {
            progressDiv.innerHTML = `
                <div class="bg-danger p-3 tag-text">
                    <strong>Error:</strong> ${error.message}
                </div>
            `;
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
            this.loadTagStats();
            this.loadMediaStats();
            this.loadAlbumStats();

        } catch (error) {
            progressDiv.innerHTML = `
                <div class="bg-danger p-3 tag-text">
                    <strong>Error:</strong> ${error.message}
                </div>
                `;
        }
    }

    async searchTags() {
        const query = document.getElementById('tag-search-input').value;
        const resultsDiv = document.getElementById('tag-search-results');

        if (!query) {
            resultsDiv.innerHTML = '';
            return;
        }

        try {
            const response = await fetch(`/api/admin/search-tags?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            if (data.tags.length === 0) {
                resultsDiv.innerHTML = '<p class="text-xs text-secondary p-3">' + window.i18n.t('gallery.no_tags_found') + '</p>';
                return;
            }

            resultsDiv.innerHTML = data.tags.map(tag => `
                <div class="bg p-3 border-b flex justify-between items-center">
                    <div>
                        <button class="delete-tag-btn text-xs bg-danger hover:bg-danger tag-text px-2 py-1 mr-2" data-tag-id="${tag.id}">&#x2715;</button>
                        <a href="/?q=${encodeURIComponent(tag.name)}" class="tag ${tag.category} tag-text">${tag.name}</a>
                        <span class="text-xs text-secondary ml-2">(${tag.post_count} posts)</span>
                    </div>
                    <span class="text-xs text-secondary uppercase">${tag.category}</span>
                </div>
                `).join('');

            // Add event listeners to delete buttons
            resultsDiv.querySelectorAll('.delete-tag-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const tagId = btn.dataset.tagId;
                    this.deleteTag(tagId);
                });
            });

        } catch (error) {
            console.error('Error searching tags:', error);
            resultsDiv.innerHTML = '<p class="text-xs text-danger p-3">Error searching tags</p>';
        }
    }

    async deleteTag(tagId) {
        const modal = new ModalHelper({
            id: 'delete-tag-modal',
            type: 'danger',
            title: window.i18n.t('modal.delete_tag.title'),
            message: window.i18n.t('modal.delete_tag.message'),
            confirmText: window.i18n.t('modal.delete_tag.confirm'),
            cancelText: window.i18n.t('modal.buttons.cancel'),
            confirmId: 'delete-tag-confirm-yes',
            cancelId: 'delete-tag-confirm-no',
            onConfirm: async () => {
                try {
                    const result = await app.apiCall(`/api/admin/tags/${tagId}`, { method: 'DELETE' });
                    app.showNotification(window.i18n.t('notifications.admin.tag_deleted', { tag_name: result.tag_name }), 'success');
                    await this.searchTags();
                    await this.loadTagStats();
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('notifications.admin.error_deleting_tag'));
                }
            }
        });

        modal.show();
    }

    async clearAllTags() {
        const firstModal = new ModalHelper({
            id: 'clear-tags-first-modal',
            type: 'danger',
            title: window.i18n.t('modal.clear_tags.title'),
            message: window.i18n.t('modal.clear_tags.message'),
            confirmText: window.i18n.t('modal.clear_tags.confirm'),
            cancelText: window.i18n.t('modal.buttons.cancel'),
            confirmId: 'clear-tags-first-confirm-yes',
            cancelId: 'clear-tags-first-confirm-no',
            onConfirm: () => {
                // Show second confirmation
                const secondModal = new ModalHelper({
                    id: 'clear-tags-second-modal',
                    type: 'danger',
                    title: window.i18n.t('modal.clear_tags_confirm.title'),
                    message: window.i18n.t('modal.clear_tags_confirm.message'),
                    confirmText: window.i18n.t('modal.clear_tags_confirm.confirm'),
                    cancelText: window.i18n.t('modal.buttons.cancel'),
                    confirmId: 'clear-tags-second-confirm-yes',
                    cancelId: 'clear-tags-second-confirm-no',
                    onConfirm: async () => {
                        try {
                            await app.apiCall('/api/admin/clear-tags', { method: 'DELETE' });
                            app.showNotification(window.i18n.t('notifications.admin.all_tags_cleared'), 'success');
                            await this.loadTagStats();
                            document.getElementById('tag-search-results').innerHTML = '';
                        } catch (error) {
                            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_clearing_tags'));
                        }
                    }
                });
                secondModal.show();
            }
        });

        firstModal.show();
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

    // Album Management Methods

    setupAlbumManagement() {
        // Create album form
        const createAlbumForm = document.getElementById('create-album-form');
        if (createAlbumForm) {
            createAlbumForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.createAlbum();
            });
        }

        // Album search
        const albumSearchBtn = document.getElementById('album-search-btn');
        const albumSearchInput = document.getElementById('album-search-input');

        albumSearchBtn?.addEventListener('click', () => this.searchAlbums());
        albumSearchInput?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.searchAlbums();
            }
        });

        // Setup parent album select
        const parentAlbumSelectElement = document.getElementById('parent-album-select');
        if (parentAlbumSelectElement) {
            this.parentAlbumSelect = new CustomSelect(parentAlbumSelectElement);
        }

        // Load albums for parent select
        this.loadAlbums();
    }

    async loadAlbumStats() {
        try {
            const response = await fetch('/api/albums?limit=1000');
            const data = await response.json();

            const totalAlbumsEl = document.getElementById('total-albums');
            const rootAlbumsEl = document.getElementById('root-albums');

            if (totalAlbumsEl) totalAlbumsEl.textContent = data.total || 0;

            // Count root albums (albums with no parents)
            let rootCount = 0;
            if (data.items) {
                for (const album of data.items) {
                    const parentsResponse = await fetch(`/api/albums/${album.id}/parents`);
                    const parentsData = await parentsResponse.json();
                    if (!parentsData.parents || parentsData.parents.length === 0) {
                        rootCount++;
                    }
                }
            }
            if (rootAlbumsEl) rootAlbumsEl.textContent = rootCount;
        } catch (error) {
            console.error('Error loading album stats:', error);
        }
    }

    async loadAlbums() {
        try {
            const response = await fetch('/api/albums?limit=1000&sort=name&order=asc');
            const data = await response.json();

            // Update parent album select dropdown
            const parentAlbumSelect = document.getElementById('parent-album-select');
            const parentAlbumContainer = document.getElementById('parent-album-container');

            if (parentAlbumSelect && this.parentAlbumSelect) {
                const items = data.items || [];

                if (items.length === 0) {
                    if (parentAlbumContainer) parentAlbumContainer.style.display = 'none';
                } else {
                    if (parentAlbumContainer) parentAlbumContainer.style.display = 'block';

                    const options = [
                        { value: '', text: 'None (Root Album)', selected: true }
                    ];

                    for (const album of items) {
                        options.push({
                            value: album.id.toString(),
                            text: album.name
                        });
                    }

                    this.parentAlbumSelect.setOptions(options);
                }
            }
        } catch (error) {
            console.error('Error loading albums:', error);
        }
    }

    async createAlbum() {
        const nameInput = document.getElementById('album-name-input');
        const parentSelectElement = document.getElementById('parent-album-select');
        const parentId = parentSelectElement?.dataset.value || '';

        const albumName = nameInput.value.trim();
        if (!albumName) {
            app.showNotification(window.i18n.t('notifications.admin.enter_album_name'), 'error');
            return;
        }

        try {
            const albumData = {
                name: albumName,
                parent_album_id: parentId ? parseInt(parentId) : null
            };

            await app.apiCall('/api/albums', {
                method: 'POST',
                body: JSON.stringify(albumData)
            });

            app.showNotification(window.i18n.t('notifications.admin.album_created'), 'success');

            // Clear form
            nameInput.value = '';
            if (this.parentAlbumSelect) {
                this.parentAlbumSelect.setValue('');
            }

            // Reload data
            await this.loadAlbumStats();
            await this.loadAlbums();

        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_creating_album'));
        }
    }

    async searchAlbums() {
        const query = document.getElementById('album-search-input').value;
        const resultsDiv = document.getElementById('album-search-results');

        if (!query) {
            resultsDiv.innerHTML = '';
            return;
        }

        try {
            const response = await fetch('/api/albums?limit=100&sort=name&order=asc');
            const data = await response.json();

            // Filter albums by name
            const filtered = (data.items || []).filter(album =>
                album.name.toLowerCase().includes(query.toLowerCase())
            );

            if (filtered.length === 0) {
                resultsDiv.innerHTML = '<p class="text-xs text-secondary p-3">' + window.i18n.t('album_picker.no_albums') + '</p>';
                return;
            }

            // Build results HTML
            let html = '';
            for (const album of filtered) {
                // Get parent info
                const parentsResponse = await fetch(`/api/albums/${album.id}/parents`);
                const parentsData = await parentsResponse.json();
                const parentChain = parentsData.parents.map(p => p.name).join(' > ');
                const immediateParentId = parentsData.parents.length > 0
                    ? parentsData.parents[parentsData.parents.length - 1].id
                    : null;

                html += `
                    <div class="bg p-3 border-b flex justify-between items-center">
                        <div class="flex-1">
                            <div class="flex items-center gap-2 mb-1">
                                <a href="/album/${album.id}" class="text-sm font-bold hover:text-primary">${this.escapeHtml(album.name)}</a>
                                <span class="text-xs text-secondary">(${album.media_count || 0} media)</span>
                            </div>
                            ${parentChain ? `<div class="text-xs text-secondary">Path: ${this.escapeHtml(parentChain)}</div>` : '<div class="text-xs text-secondary">' + window.i18n.t('albums.root_album') + '</div>'}
                        </div>
                        <div class="flex gap-2">
                            <button class="manage-album-btn text-xs px-3 py-1 bg-primary primary-text hover:bg-primary"
                                data-album-id="${album.id}"
                                data-album-name="${this.escapeHtml(album.name)}"
                                data-parent-id="${immediateParentId || ''}">${window.i18n.t('common.manage')}</button>
                        </div>
                    </div>
                `;
            }

            resultsDiv.innerHTML = html;

            // Add event listeners for Manage buttons
            resultsDiv.querySelectorAll('.manage-album-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const albumId = btn.dataset.albumId;
                    const albumName = btn.dataset.albumName;
                    const parentId = btn.dataset.parentId || null;
                    this.showAlbumManageModal(albumId, albumName, parentId);
                });
            });

        } catch (error) {
            console.error('Error searching albums:', error);
            resultsDiv.innerHTML = '<p class="text-xs text-danger p-3">Error searching albums</p>';
        }
    }

    showAlbumManageModal(albumId, albumName, currentParentId) {
        // Remove existing modal if any
        const existingModal = document.getElementById('album-manage-modal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'album-manage-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full text-center">
                <svg class="mx-auto mb-4" width="48" height="48" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z" fill="var(--primary)"/>
                </svg>
                <h2 class="text-xl font-bold mb-2 text-primary">${window.i18n.t('admin.albums_management.manage_album')}</h2>
                <p class="text-base mb-6 text font-medium">${this.escapeHtml(albumName)}</p>
                <div class="flex flex-col gap-3">
                    <button id="album-manage-rename" class="px-6 py-3 transition-colors surface-light hover:surface text font-bold text-sm flex items-center justify-center gap-2">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                        </svg>
                        ${window.i18n.t('admin.albums_management.rename_album')}
                    </button>
                    <button id="album-manage-parent" class="px-6 py-3 transition-colors surface-light hover:surface text font-bold text-sm flex items-center justify-center gap-2">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/>
                        </svg>
                        ${window.i18n.t('admin.albums_management.change_parent_album')}
                    </button>
                    <button id="album-manage-delete" class="px-6 py-3 transition-colors bg-danger hover:bg-danger tag-text font-bold text-sm flex items-center justify-center gap-2">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                        </svg>
                        ${window.i18n.t('admin.albums_management.delete_album')}
                    </button>
                    <button id="album-manage-cancel" class="px-6 py-3 transition-colors hover:surface text font-bold text-sm flex items-center justify-center gap-2">
                        ${window.i18n.t('common.cancel')}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Event listeners
        document.getElementById('album-manage-rename').addEventListener('click', () => {
            modal.remove();
            this.showRenameAlbumModal(albumId, albumName, currentParentId);
        });

        document.getElementById('album-manage-parent').addEventListener('click', () => {
            modal.remove();
            this.showChangeParentModal(albumId, albumName, currentParentId);
        });

        document.getElementById('album-manage-delete').addEventListener('click', () => {
            modal.remove();
            this.deleteAlbum(albumId, albumName, currentParentId);
        });

        document.getElementById('album-manage-cancel').addEventListener('click', () => {
            modal.remove();
        });

        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });

        // Close on Escape
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                modal.remove();
                document.removeEventListener('keydown', handleEscape);
            }
        };
        document.addEventListener('keydown', handleEscape);
    }

    showRenameAlbumModal(albumId, currentName, currentParentId) {
        // Remove existing modal if any
        const existingModal = document.getElementById('album-rename-modal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'album-rename-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full">
                <h2 class="text-xl font-bold mb-4 text-primary text-center">Rename Album</h2>
                <div class="mb-6">
                    <label class="block text-xs font-bold mb-2">New Name</label>
                    <input type="text" id="new-album-name" value="${this.escapeHtml(currentName)}"
                        class="w-full bg px-3 py-2 border text-sm focus:outline-none focus:border-primary">
                </div>
                <div class="flex gap-4 justify-center">
                    <button id="album-rename-confirm" class="px-6 py-3 transition-colors bg-primary primary-text font-bold text-sm">
                        Save
                    </button>
                    <button id="album-rename-cancel" class="px-6 py-3 transition-colors surface-light text font-bold text-sm">
                        Cancel
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Focus the input and select all text
        const input = document.getElementById('new-album-name');
        input.focus();
        input.select();

        // Event listeners
        const confirmRename = async () => {
            const newName = input.value.trim();
            if (!newName) {
                app.showNotification(window.i18n.t('notifications.admin.enter_name'), 'error');
                return;
            }
            if (newName === currentName) {
                modal.remove();
                this.showAlbumManageModal(albumId, currentName, currentParentId);
                return;
            }

            modal.remove();

            try {
                await app.apiCall(`/api/albums/${albumId}`, {
                    method: 'PUT',
                    body: JSON.stringify({ name: newName })
                });

                app.showNotification(window.i18n.t('notifications.admin.album_renamed'), 'success');
                await this.searchAlbums();
                await this.loadAlbums();
                await this.loadAlbumStats();

                // Return to manage modal with updated name
                this.showAlbumManageModal(albumId, newName, currentParentId);

            } catch (error) {
                app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_renaming_album'));
                // Return to manage modal on error
                this.showAlbumManageModal(albumId, currentName, currentParentId);
            }
        };

        document.getElementById('album-rename-confirm').addEventListener('click', confirmRename);

        document.getElementById('album-rename-cancel').addEventListener('click', () => {
            modal.remove();
            this.showAlbumManageModal(albumId, currentName, currentParentId);
        });

        // Handle Enter key in input
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                confirmRename();
            }
        });

        // Close on outside click - return to manage modal
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
                this.showAlbumManageModal(albumId, currentName, currentParentId);
            }
        });

        // Close on Escape - return to manage modal
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                modal.remove();
                document.removeEventListener('keydown', handleEscape);
                this.showAlbumManageModal(albumId, currentName, currentParentId);
            }
        };
        document.addEventListener('keydown', handleEscape);
    }

    async getAlbumDescendantIds(albumId) {
        const descendantIds = new Set();

        const fetchChildren = async (parentId) => {
            try {
                const response = await fetch(`/api/albums/${parentId}/children`);
                if (!response.ok) return;
                const children = await response.json();

                for (const child of children) {
                    descendantIds.add(child.id.toString());
                    await fetchChildren(child.id);
                }
            } catch (error) {
                console.error('Error fetching children:', error);
            }
        };

        await fetchChildren(albumId);
        return descendantIds;
    }

    async showChangeParentModal(albumId, albumName, currentParentId) {
        // Remove existing modal if any
        const existingModal = document.getElementById('album-parent-modal');
        if (existingModal) {
            existingModal.remove();
        }

        // Load all albums for the dropdown
        let albums = [];
        try {
            const response = await fetch('/api/albums?limit=1000&sort=name&order=asc');
            const data = await response.json();
            albums = data.items || [];
        } catch (error) {
            console.error('Error loading albums:', error);
            app.showNotification(window.i18n.t('notifications.admin.error_loading_albums'), 'error');
            this.showAlbumManageModal(albumId, albumName, currentParentId);
            return;
        }

        // Get all descendant IDs to prevent circular references
        const descendantIds = await this.getAlbumDescendantIds(albumId);

        // Filter out the current album and all its descendants
        const validAlbums = albums.filter(a => {
            const id = a.id.toString();
            return id !== albumId.toString() && !descendantIds.has(id);
        });

        const modal = document.createElement('div');
        modal.id = 'album-parent-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        // Build options HTML for custom select
        let optionsHtml = `
            <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs ${!currentParentId ? 'selected' : ''}"
                data-value="">None (Root Album)</div>
        `;
        for (const album of validAlbums) {
            const isSelected = currentParentId && album.id.toString() === currentParentId.toString();
            optionsHtml += `
                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs ${isSelected ? 'selected' : ''}"
                    data-value="${album.id}">${this.escapeHtml(album.name)}</div>
            `;
        }

        // Determine initial display text
        let initialDisplayText = 'None (Root Album)';
        if (currentParentId) {
            const currentParent = validAlbums.find(a => a.id.toString() === currentParentId.toString());
            if (currentParent) {
                initialDisplayText = currentParent.name;
            }
        }

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full">
                <h2 class="text-xl font-bold mb-2 text-primary text-center">Change Parent Album</h2>
                <p class="text-sm mb-4 text-secondary text-center">Album: <span class="text font-medium">${this.escapeHtml(albumName)}</span></p>
                <div class="mb-6">
                    <label class="block text-xs font-bold mb-2">New Parent Album</label>
                    <div id="change-parent-select" class="custom-select" data-value="${currentParentId || ''}">
                        <button
                            class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 bg border text-xs cursor-pointer focus:outline-none focus:border-primary"
                            type="button">
                            <span class="custom-select-value">${this.escapeHtml(initialDisplayText)}</span>
                            <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary"
                                width="12" height="12" viewBox="0 0 12 12">
                                <path fill="currentColor" d="M6 9L1 4h10z" />
                            </svg>
                        </button>
                        <div class="custom-select-dropdown bg border border-primary max-h-60 overflow-y-auto shadow-lg">
                            ${optionsHtml}
                        </div>
                    </div>
                </div>
                <div class="flex gap-4 justify-center">
                    <button id="album-parent-confirm" class="px-6 py-3 transition-colors bg-primary primary-text font-bold text-sm">
                        Save
                    </button>
                    <button id="album-parent-cancel" class="px-6 py-3 transition-colors surface-light text font-bold text-sm">
                        Cancel
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Initialize the custom select
        const selectElement = document.getElementById('change-parent-select');
        const changeParentSelect = new CustomSelect(selectElement);

        // Event listeners
        document.getElementById('album-parent-confirm').addEventListener('click', async () => {
            const newParentId = selectElement.dataset.value;
            modal.remove();

            // Check if parent actually changed
            const oldParentId = currentParentId || '';
            if (newParentId === oldParentId) {
                this.showAlbumManageModal(albumId, albumName, currentParentId);
                return;
            }

            try {
                await app.apiCall(`/api/albums/${albumId}`, {
                    method: 'PUT',
                    body: JSON.stringify({
                        parent_album_id: newParentId ? parseInt(newParentId) : null
                    })
                });

                app.showNotification(window.i18n.t('notifications.admin.parent_album_updated'), 'success');
                await this.searchAlbums();
                await this.loadAlbums();
                await this.loadAlbumStats();

                // Return to manage modal with updated parent
                this.showAlbumManageModal(albumId, albumName, newParentId || null);

            } catch (error) {
                app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_updating_parent'));
                // Return to manage modal on error
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        });

        document.getElementById('album-parent-cancel').addEventListener('click', () => {
            modal.remove();
            this.showAlbumManageModal(albumId, albumName, currentParentId);
        });

        // Close on outside click - return to manage modal
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        });

        // Close on Escape - return to manage modal
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                modal.remove();
                document.removeEventListener('keydown', handleEscape);
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        };
        document.addEventListener('keydown', handleEscape);
    }

    async deleteAlbum(albumId, albumName, currentParentId) {
        const modal = new ModalHelper({
            id: 'delete-album-modal',
            type: 'danger',
            title: window.i18n.t('modal.delete_album.title'),
            message: window.i18n.t('modal.delete_album.message', { albumName: this.escapeHtml(albumName) }),
            confirmText: window.i18n.t('modal.delete_album.confirm'),
            cancelText: window.i18n.t('modal.buttons.cancel'),
            confirmId: 'delete-album-confirm-yes',
            cancelId: 'delete-album-confirm-no',
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/albums/${albumId}?cascade=false`, {
                        method: 'DELETE'
                    });
                    app.showNotification(window.i18n.t('notifications.admin.album_deleted'), 'success');
                    await this.searchAlbums();
                    await this.loadAlbums();
                    await this.loadAlbumStats();
                    // Don't return to manage modal since album is deleted
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('notifications.admin.error_deleting_album'));
                    // Return to manage modal on error
                    this.showAlbumManageModal(albumId, albumName, currentParentId);
                }
            },
            onCancel: () => {
                // Return to manage modal when cancelled
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        });

        modal.show();
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
            cancelText: window.i18n.t('modal.buttons.cancel'),
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
                    <div class="font-bold text-xs truncate mb-1 text">${this.escapeHtml(key.name || 'Unnamed Key')}</div>
                    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-secondary opacity-80">
                        <span class="font-mono bg surface px-1 border border-primary border-opacity-20">${this.escapeHtml(key.key_prefix)}...</span>
                        <span>Created: <strong>${new Date(key.created_at).toLocaleDateString()}</strong></span>
                        <span>Last used: <strong>${key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}</strong></span>
                    </div>
                </div>
                <div class="flex-shrink-0">
                    <button class="px-3 py-1 bg-danger tag-text text-[10px] uppercase font-bold tracking-wider hover:bg-danger transition-colors" 
                        onclick="window.adminPanel.revokeApiKey(${key.id})">
                        Revoke
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
            cancelText: window.i18n.t('modal.buttons.cancel'),
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
        document.getElementById('btn-update-dev')?.addEventListener('click', () => this.performUpdate('dev'));
        document.getElementById('btn-update-stable')?.addEventListener('click', () => this.performUpdate('stable'));
        document.getElementById('btn-view-changelog')?.addEventListener('click', () => this.showChangelog());

        this.currentChangelog = [];
        this.remoteUrl = null;
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

            loading.style.display = 'none';
            loading.classList.add('hidden');
            statusDiv.style.display = 'block';

            const currentHashEl = document.getElementById('current-version-hash');
            if (currentHashEl) currentHashEl.textContent = status.current_hash.substring(0, 8);

            const currentBranchEl = document.getElementById('current-branch');
            if (currentBranchEl) currentBranchEl.textContent = status.current_branch;

            const latestHashEl = document.getElementById('latest-version-hash');
            if (latestHashEl) latestHashEl.textContent = status.latest_dev_hash.substring(0, 8);

            const latestTagEl = document.getElementById('latest-version-tag');
            if (latestTagEl) latestTagEl.textContent = status.latest_stable_tag || 'main';

            const devBtn = document.getElementById('btn-update-dev');
            if (devBtn) {
                if (status.current_hash === status.latest_dev_hash) {
                    devBtn.disabled = true;
                    devBtn.textContent = window.i18n.t('admin.messages.already_latest');
                }
            }

            const noticesDiv = document.getElementById('update-notices');
            if (noticesDiv) {
                if (status.notices && status.notices.length > 0) {
                    noticesDiv.classList.remove('hidden');
                    noticesDiv.innerHTML = status.notices.map(n => `<div class="bg text-xs p-2 mb-1 border-l-4 border-warning text-warning font-bold">${this.escapeHtml(n)}</div>`).join('');
                } else {
                    noticesDiv.classList.add('hidden');
                }
            }

            // Changelog
            this.currentChangelog = status.changelog || [];
            this.remoteUrl = status.remote_url || null;
            const changelogBtn = document.getElementById('btn-view-changelog');
            if (changelogBtn) {
                if (this.currentChangelog.length > 0) {
                    changelogBtn.style.display = 'block';
                    changelogBtn.textContent = window.i18n.t('admin.messages.view_changelog', { count: this.currentChangelog.length });
                } else {
                    changelogBtn.style.display = 'none';
                }
            }

        } catch (e) {
            console.error(e);
            if (loading) {
                loading.textContent = window.i18n.t('admin.messages.update_error', { error: e.message });
                loading.classList.remove('hidden');
                loading.classList.add('text-danger');
            }
        }
    }

    showChangelog() {
        if (!this.currentChangelog || this.currentChangelog.length === 0) return;

        if (typeof ModalHelper === 'undefined') {
            console.error('ModalHelper not available');
            return;
        }

        const changelogHtml = this.currentChangelog.map(commit => {
            let hashHtml = `<span class="font-mono text-xs bg-primary primary-text px-1">${commit.hash}</span>`;

            if (this.remoteUrl) {
                const baseUrl = this.remoteUrl.endsWith('.git') ? this.remoteUrl.slice(0, -4) : this.remoteUrl;
                const commitUrl = `${baseUrl}/commit/${commit.hash}`;
                hashHtml = `<a href="${commitUrl}" target="_blank" class="font-mono text-xs bg-primary primary-text px-1 cursor-pointer" title="View on Remote">${commit.hash}</a>`;
            }

            return `
            <div class="border-b last:border-0 text-left">
                <div class="flex items-center bg p-2 gap-2">
                    ${hashHtml}
                    <div class="flex flex-col">
                        <span class="font-bold text-sm">${this.escapeHtml(commit.subject)}</span>
                        ${commit.body ? `<div class="text-xs text-secondary whitespace-pre-wrap">${this.escapeHtml(commit.body)}</div>` : ''}
                    </div>
                </div>
            </div>
        `}).join('');

        const modal = new ModalHelper({
            id: 'changelog-modal',
            type: 'info',
            title: window.i18n.t('modal.changelog.title'),
            message: `<div class="max-h-96 overflow-y-auto pr-2 custom-scrollbar">${changelogHtml}</div>`,
            confirmText: window.i18n.t('modal.changelog.confirm'),
            cancelText: '',
            onConfirm: () => {
                modal.destroy();
            }
        });

        modal.show();
    }

    async performUpdate(target) {
        if (typeof ModalHelper === 'undefined') {
            console.error('ModalHelper not available');
            if (!confirm(window.i18n.t('notifications.admin.update_confirm', { target }))) return;
            this._execute_update(target);
            return;
        }

        const modal = new ModalHelper({
            id: 'update-confirm-modal',
            type: 'warning',
            title: window.i18n.t('modal.system_update.title'),
            message: window.i18n.t('modal.system_update.message', { target: target }),
            confirmText: window.i18n.t('modal.system_update.confirm'),
            cancelText: window.i18n.t('modal.buttons.cancel'),
            onConfirm: () => {
                this._execute_update(target);
                modal.destroy();
            },
            onCancel: () => {
                modal.destroy();
            }
        });

        modal.show();
    }

    async _execute_update(target) {
        const resultDiv = document.getElementById('update-result');
        const resultLog = document.getElementById('update-result-log');
        if (resultDiv) resultDiv.classList.remove('hidden');
        if (resultLog) resultLog.textContent = window.i18n.t('admin.messages.update_started');

        try {
            const response = await app.apiCall('/api/system/update/perform', {
                method: 'POST',
                body: JSON.stringify({ target })
            });

            if (resultLog) {
                resultLog.textContent = (response.log || '') + "\n\n" + (response.message || '');
            }

            if (response.success) {
                app.showNotification(window.i18n.t('notifications.admin.update_initiated'), 'success');
            }
        } catch (e) {
            if (resultLog) resultLog.textContent += `\nError: ${e.message}`;
            app.showNotification(window.i18n.t('notifications.admin.update_failed', { error: e.message }), 'error');
        }
    }
}

// Initialize admin panel
if (document.getElementById('admin-panel')) {
    const adminPanel = new AdminPanel();

}
