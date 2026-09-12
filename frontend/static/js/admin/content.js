class AdminContent {
    constructor(adminPanel) {
        this.app = adminPanel;
    }

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

        await this.app.tagInputHelper.validateAndStyleTags(tagsInput, {
            validationCache: this.app.tagInputHelper.tagValidationCache,
            checkFunction: (tag) => {
                const { tagName } = this.parseTagWithCategory(tag);
                return this.app.tagInputHelper.checkTagOrAliasExists(tagName);
            },
            invertLogic: true
        });
    }

    setupNewTagsInput() {
        const tagsInput = document.getElementById('new-tags-input');
        if (!tagsInput) return;

        this.app.tagInputHelper.setupTagInput(tagsInput, 'new-tags-input', {
            onValidate: () => { },
            checkFunction: (tag) => {
                const { tagName } = this.parseTagWithCategory(tag);
                return this.app.tagInputHelper.checkTagOrAliasExists(tagName);
            },
            invertLogic: true
        });
    }

    async addNewTags() {
        const tagsInput = document.getElementById('new-tags-input');
        const statusDiv = document.getElementById('add-tags-status');
        const resultDiv = document.getElementById('add-tags-result');

        const text = this.app.tagInputHelper.getPlainTextFromDiv(tagsInput);
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
            const shouldIgnore = this.app.tagInputHelper.tagValidationCache.get(tagName);

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
            this.app.tagInputHelper.clearCache();

            // Reload stats
            await this.app.content.loadTagStats();

        } catch (error) {
            resultDiv.innerHTML = `
                <div class="bg-danger p-3 tag-text">
                    <strong>Error:</strong> ${error.message}
                </div>
            `;
        }
    }

    async loadAITaggerSettings() {
        try {
            const res = await fetch('/api/ai-tagger/settings');
            if (!res.ok) return;
            const data = await res.json();

            const generalEl = document.getElementById('wd-general-threshold');
            if (generalEl && data.general_threshold != null) generalEl.value = data.general_threshold;

            const charEl = document.getElementById('wd-character-threshold');
            if (charEl && data.character_threshold != null) charEl.value = data.character_threshold;

            const blacklistEl = document.getElementById('wd-blacklisted-tags');
            if (blacklistEl && data.blacklisted_tags) {
                blacklistEl.textContent = data.blacklisted_tags.join(' ');
                setTimeout(() => this.app.tagInputHelper.validateAndStyleTags(blacklistEl), 100);
            }

            // Init blacklisted category buttons
            const blacklistedCategories = new Set(data.blacklisted_categories || []);
            document.querySelectorAll('.wd-category-btn').forEach(btn => {
                const cat = btn.dataset.category;
                const isBlacklisted = blacklistedCategories.has(cat);
                this.setCategoryButtonState(btn, isBlacklisted);
                if (!btn.dataset.bound) {
                    btn.dataset.bound = 'true';
                    btn.addEventListener('click', () => {
                        const nowBlacklisted = !btn.classList.contains('bg-danger');
                        this.setCategoryButtonState(btn, nowBlacklisted);
                    });
                }
            });

            // Populate model dropdown
            const dropdown = document.getElementById('wd-model-dropdown');
            if (dropdown && data.available_models) {
                dropdown.innerHTML = '';
                data.available_models.forEach(model => {
                    const opt = document.createElement('div');
                    opt.className = 'custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs';
                    opt.dataset.value = model;
                    opt.textContent = model;
                    dropdown.appendChild(opt);
                });
            }

            // Init custom select for model
            const modelSelectEl = document.getElementById('wd-model-select');
            if (modelSelectEl) {
                this.wdModelSelect = new CustomSelect(modelSelectEl);
                modelSelectEl.addEventListener('change', (e) => {
                    this.updateWDModelActionBtn(e.detail?.value || this.wdModelSelect.getValue());
                });
                if (data.model_name) this.wdModelSelect.setValue(data.model_name);
            }

            const actionBtn = document.getElementById('wd-model-action-btn');
            if (actionBtn && !this.wdModelActionBtnBound) {
                this.wdModelActionBtnBound = true;
                actionBtn.addEventListener('click', () => this.handleWDModelAction());
            }

            const initialModel = data.model_name || (this.wdModelSelect ? this.wdModelSelect.getValue() : null);
            if (initialModel) {
                await this.updateWDModelActionBtn(initialModel);
            }
        } catch (e) {
            console.error('Error loading AI Tagger settings:', e);
        }
    }

    setCategoryButtonState(btn, isBlacklisted) {
        if (isBlacklisted) {
            btn.classList.remove('bg', 'hover:border-primary');
            btn.classList.add('bg-danger', 'border-danger', 'tag-text', 'hover:bg-danger');
        } else {
            btn.classList.remove('bg-danger', 'border-danger', 'tag-text', 'hover:bg-danger');
            btn.classList.add('bg', 'hover:border-primary');
        }
    }

    async updateWDModelActionBtn(modelName) {
        const btn = document.getElementById('wd-model-action-btn');
        if (!btn) return;

        if (!modelName) {
            btn.style.display = 'none';
            this.wdModelActionState = null;
            return;
        }

        try {
            const res = await fetch(`/api/ai-tagger/model-status/${encodeURIComponent(modelName)}`);
            if (!res.ok) {
                btn.style.display = 'none';
                this.wdModelActionState = null;
                return;
            }
            const status = await res.json();
            const isDownloaded = Boolean(status.is_downloaded);
            this.wdModelActionState = { modelName, isDownloaded };

            btn.style.display = 'flex';
            if (isDownloaded) {
                btn.className = 'btn-danger p-2 flex items-center justify-center flex-shrink-0 text-xs';
                btn.title = window.i18n.t('common.delete');
                btn.innerHTML = window.Icons.trash({ size: 14 });
            } else {
                btn.className = 'btn-primary p-2 flex items-center justify-center flex-shrink-0 text-xs';
                btn.title = window.i18n.t('common.download');
                btn.innerHTML = window.Icons.download({ size: 14 });
            }
        } catch (e) {
            console.error('Error checking model status:', e);
            btn.style.display = 'none';
            this.wdModelActionState = null;
        }
    }

    async handleWDModelAction() {
        if (!this.wdModelActionState || !this.wdModelActionState.modelName) return;
        const { modelName, isDownloaded } = this.wdModelActionState;

        if (isDownloaded) {
            const modal = new ModalHelper({
                id: 'delete-model-modal',
                type: 'danger',
                title: window.i18n.t('modal.delete_model.title'),
                message: window.i18n.t('modal.delete_model.message', { modelName }),
                confirmText: window.i18n.t('common.delete'),
                cancelText: window.i18n.t('common.cancel'),
                confirmId: 'delete-model-confirm-yes',
                cancelId: 'delete-model-confirm-no',
                onConfirm: async () => {
                    const btn = document.getElementById('wd-model-action-btn');
                    if (btn) btn.disabled = true;
                    try {
                        const res = await fetch(`/api/ai-tagger/model/${encodeURIComponent(modelName)}`, {
                            method: 'DELETE'
                        });
                        if (!res.ok) {
                            const err = await res.json();
                            throw new Error(err.detail || 'Failed to delete model');
                        }
                        app.showNotification(window.i18n.t('notifications.admin.model_deleted'), 'success');
                        await this.updateWDModelActionBtn(modelName);
                    } catch (e) {
                        app.showNotification(e.message, 'error');
                    } finally {
                        if (btn) btn.disabled = false;
                    }
                }
            });
            modal.show();
        } else {
            const downloadModal = new ModelDownloadModal();
            const isReady = await downloadModal.ensureModelReady(modelName);
            if (isReady) {
                await this.updateWDModelActionBtn(modelName);
            }
        }
    }

    async saveAITaggerSettings() {
        const btn = document.getElementById('save-ai-tagger-btn');
        const originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = window.i18n.t('admin.actions.testing');

        const generalEl = document.getElementById('wd-general-threshold');
        const charEl = document.getElementById('wd-character-threshold');
        const modelName = this.wdModelSelect ? this.wdModelSelect.getValue() : null;

        let blacklistedTags = [];
        const blacklistEl = document.getElementById('wd-blacklisted-tags');
        if (blacklistEl) {
            const text = this.app.tagInputHelper.getPlainTextFromDiv(blacklistEl);
            blacklistedTags = text.split(/\s+/).filter(t => t.length > 0);
        }

        const blacklistedCategories = [];
        document.querySelectorAll('.wd-category-btn').forEach(btn => {
            if (btn.classList.contains('bg-danger') && btn.dataset.category) {
                blacklistedCategories.push(btn.dataset.category);
            }
        });

        const body = {};
        if (generalEl && generalEl.value) body.general_threshold = parseFloat(generalEl.value);
        if (charEl && charEl.value) body.character_threshold = parseFloat(charEl.value);
        if (modelName) body.model_name = modelName;
        body.blacklisted_tags = blacklistedTags;
        body.blacklisted_categories = blacklistedCategories;

        try {
            const res = await fetch('/api/ai-tagger/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to save settings');
            }

            app.showNotification(window.i18n.t('admin.ai_tagger.settings_saved'), 'success');
        } catch (e) {
            app.showNotification(e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
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

                    // Add to uploader
                    await uploader.addScannedFile(filePath);
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

    async generateMissingThumbnails() {
        const btn = document.getElementById('generate-missing-thumbnails-btn');
        const allBtn = document.getElementById('regenerate-all-thumbnails-btn');
        const statusDiv = document.getElementById('thumbnail-regen-status');
        const resultDiv = document.getElementById('thumbnail-regen-result');
        const originalText = btn.textContent;

        btn.disabled = true;
        allBtn.disabled = true;
        btn.textContent = window.i18n.t('admin.media_management.maintenance.thumbnails.generating');
        statusDiv.style.display = 'block';
        resultDiv.innerHTML = `<div class="bg-primary primary-text p-3"><strong>${window.i18n.t('admin.media_management.maintenance.thumbnails.generating')}</strong></div>`;

        try {
            const result = await app.apiCall('/api/admin/generate-missing-thumbnails', { method: 'POST' });
            const msg = window.i18n.t('admin.media_management.maintenance.thumbnails.done_missing', {
                orphans_deleted: result.orphans_deleted,
                generated: result.generated,
                skipped: result.skipped,
                failed: result.failed,
            });
            resultDiv.innerHTML = `<div class="bg-success p-3 tag-text"><strong>${msg}</strong></div>`;
        } catch (error) {
            resultDiv.innerHTML = `<div class="bg-danger p-3 tag-text"><strong>Error:</strong> ${error.message}</div>`;
        } finally {
            btn.disabled = false;
            allBtn.disabled = false;
            btn.textContent = originalText;
        }
    }

    async regenerateAllThumbnails() {
        const modal = new ModalHelper({
            id: 'regenerate-thumbnails-modal',
            type: 'danger',
            title: window.i18n.t('modal.regenerate_thumbnails.title'),
            message: window.i18n.t('modal.regenerate_thumbnails.message'),
            confirmText: window.i18n.t('modal.regenerate_thumbnails.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            confirmId: 'regenerate-thumbnails-confirm-yes',
            cancelId: 'regenerate-thumbnails-confirm-no',
            onConfirm: async () => {
                const btn = document.getElementById('regenerate-all-thumbnails-btn');
                const missingBtn = document.getElementById('generate-missing-thumbnails-btn');
                const statusDiv = document.getElementById('thumbnail-regen-status');
                const resultDiv = document.getElementById('thumbnail-regen-result');
                const originalText = btn.textContent;

                btn.disabled = true;
                missingBtn.disabled = true;
                btn.textContent = window.i18n.t('admin.media_management.maintenance.thumbnails.generating');
                statusDiv.style.display = 'block';
                resultDiv.innerHTML = `<div class="bg-primary primary-text p-3"><strong>${window.i18n.t('admin.media_management.maintenance.thumbnails.generating')}</strong></div>`;

                try {
                    const result = await app.apiCall('/api/admin/regenerate-all-thumbnails', { method: 'POST' });
                    const msg = window.i18n.t('admin.media_management.maintenance.thumbnails.done_all', {
                        deleted: result.deleted,
                        generated: result.generated,
                        failed: result.failed,
                    });
                    resultDiv.innerHTML = `<div class="bg-success p-3 tag-text"><strong>${msg}</strong></div>`;
                } catch (error) {
                    resultDiv.innerHTML = `<div class="bg-danger p-3 tag-text"><strong>Error:</strong> ${error.message}</div>`;
                } finally {
                    btn.disabled = false;
                    missingBtn.disabled = false;
                    btn.textContent = originalText;
                }
            }
        });

        modal.show();
    }

    async relinkMedia() {
        const btn = document.getElementById('relink-media-btn');
        if (!btn) return;
        const originalText = btn.textContent;

        btn.disabled = true;
        btn.textContent = window.i18n.t('admin.media_management.maintenance.relink.relinking');

        try {
            const result = await app.apiCall('/api/admin/relink-media', { method: 'POST' });
            let msg = '';

            if (result.relinked > 0) {
                msg = window.i18n.t('admin.media_management.maintenance.relink.done_relinked', { count: result.relinked });
            } else {
                msg = window.i18n.t('admin.media_management.maintenance.relink.done_none');
            }

            if (result.unresolved > 0) {
                const unresolvedMsg = window.i18n.t('admin.media_management.maintenance.relink.unresolved_warning', { count: result.unresolved });
                msg += ` ${unresolvedMsg}`;
            }

            if (result.relinked > 0) {
                app.showNotification(msg, 'success');
                await this.loadMediaStats();
            } else {
                app.showNotification(msg, result.unresolved > 0 ? 'warning' : 'info');
            }
        } catch (error) {
            app.showNotification(error.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
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
            uploadArea.classList.add('drag-over');
        });

        uploadArea?.addEventListener('dragleave', () => {
            uploadArea.classList.remove('drag-over');
        });

        uploadArea?.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');

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
            fullImportArea.classList.add('drag-over');
        });

        fullImportArea?.addEventListener('dragleave', () => {
            fullImportArea.classList.remove('drag-over');
        });

        fullImportArea?.addEventListener('drop', (e) => {
            e.preventDefault();
            fullImportArea.classList.remove('drag-over');

            if (e.dataTransfer.files.length > 0) {
                this.app.system.uploadFullBackup(e.dataTransfer.files[0]);
            }
        });

        fullImportInput?.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.app.system.uploadFullBackup(e.target.files[0]);
            }
        });

        // Tag search
        const searchInput = document.getElementById('tag-search-input');

        searchInput?.addEventListener('input', (e) => {
            const start = e.target.selectionStart;
            const end = e.target.selectionEnd;
            const normalized = e.target.value.replace(/\s+/g, '_');
            if (e.target.value !== normalized) {
                e.target.value = normalized;
                if (start !== null && end !== null) {
                    e.target.setSelectionRange(start, end);
                }
            }
            this.searchTags();
        });

        searchInput?.addEventListener('keydown', (e) => {
            if (e.key === ' ') {
                e.preventDefault();
                const start = e.target.selectionStart;
                const end = e.target.selectionEnd;
                e.target.setRangeText('_', start, end, 'end');
                this.searchTags();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                this.searchTags();
            }
        });

        const applyAliasesBtn = document.getElementById('apply-aliases-btn');
        applyAliasesBtn?.addEventListener('click', () => this.handleApplyAllAliases());

        // Clear tags
        const clearBtn = document.getElementById('clear-tags-btn');
        clearBtn?.addEventListener('click', () => this.clearAllTags());

        // Setup Media Type Tags
        this.setupMediaTypeTags();
    }

    setupMediaTypeTags() {
        const mediaTypeTagIds = ['media-type-tags-image', 'media-type-tags-gif', 'media-type-tags-video'];
        mediaTypeTagIds.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            this.app.tagInputHelper.setupTagInput(el, id, { onValidate: () => { } });
            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(el, { multipleValues: true, allowCreate: true });
            }
        });

        const mediaTypeTagsForm = document.getElementById('media-type-tags-form');
        if (mediaTypeTagsForm) {
            mediaTypeTagsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.saveMediaTypeTags();
            });
        }
    }

    async saveMediaTypeTags() {
        const getMediaTypeTags = (id) => {
            const el = document.getElementById(id);
            if (!el) return [];
            const text = this.app.tagInputHelper.getPlainTextFromDiv(el);
            return text.split(/\s+/).filter(t => t.length > 0);
        };

        const mediaTypeTags = {
            image: getMediaTypeTags('media-type-tags-image'),
            gif: getMediaTypeTags('media-type-tags-gif'),
            video: getMediaTypeTags('media-type-tags-video')
        };

        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify({ media_type_tags: mediaTypeTags })
            });

            app.showNotification(window.i18n.t('notifications.admin.media_type_tags_saved') || window.i18n.t('notifications.admin.settings_updated'), 'success');
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_saving_settings'));
        }
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
            await this.app.content.loadTagStats();

        } catch (error) {
            progressDiv.innerHTML = `
                <div class="bg-danger p-3 tag-text">
                    <strong>Error:</strong> ${error.message}
                </div>
            `;
        }
    }

    async searchTags() {
        const searchInput = document.getElementById('tag-search-input');
        const query = searchInput ? searchInput.value.trim() : '';
        const resultsDiv = document.getElementById('tag-search-results');

        if (this._tagSearchAbortController) {
            this._tagSearchAbortController.abort();
            this._tagSearchAbortController = null;
        }

        if (!query) {
            if (resultsDiv) resultsDiv.innerHTML = '';
            return;
        }

        const abortController = new AbortController();
        this._tagSearchAbortController = abortController;

        try {
            const response = await fetch(`/api/admin/search-tags?q=${encodeURIComponent(query)}`, {
                signal: abortController.signal
            });
            if (!response.ok) return;
            const data = await response.json();

            // Guard against stale response if query changed in the meantime
            const currentQuery = document.getElementById('tag-search-input')?.value.trim();
            if (!currentQuery) {
                if (resultsDiv) resultsDiv.innerHTML = '';
                return;
            }

            if (data.tags.length === 0) {
                resultsDiv.innerHTML = '<p class="bg text-xs text-secondary p-3">' + window.i18n.t('gallery.no_tags_found') + '</p>';
                resultsDiv.scrollTop = 0;
                return;
            }

            resultsDiv.innerHTML = data.tags.map((tag, i, arr) => {
                let creationDateStr = '';
                if (tag.created_at) {
                    const d = new Date(tag.created_at);
                    if (!isNaN(d.getTime())) {
                        creationDateStr = `${new Intl.DateTimeFormat(undefined, { dateStyle: "short" }).format(d)} ${new Intl.DateTimeFormat(undefined, { timeStyle: "short", hour12: false }).format(d)}`;
                    }
                }

                return `
                <div class="bg px-2 py-1.5 ${i === arr.length - 1 ? '' : 'border-b'} flex flex-wrap items-center gap-2">
                    <div class="flex items-center gap-2 min-w-0">
                        <button class="manage-tag-btn flex-shrink-0 flex items-center justify-center w-7 h-7 bg-primary primary-text hover:bg-primary border-primary hover:border-primary transition-colors cursor-pointer"
                            data-tag-id="${tag.id}"
                            data-tag-name="${this.app.escapeHtml(tag.name)}"
                            data-tag-category="${tag.category}"
                            title="${window.i18n.t('admin.tags_management.manage_tag')}">
                            ${window.Icons.tagMenu({ size: 14 })}
                        </button>
                        <a href="/?q=${encodeURIComponent(tag.name)}" class="tag ${tag.category} tag-text overflow-hidden whitespace-nowrap text-ellipsis">${tag.name}</a>
                    </div>
                    <div class="flex justify-between items-center gap-2 flex-1">
                        <span class="text-xs text-secondary">(${tag.post_count})</span>
                        ${creationDateStr ? `<span class="text-xs text-secondary text-center">${creationDateStr}</span>` : ''}
                        <span class="text-xs text-secondary uppercase flex-1 text-right">${tag.category}</span>
                    </div>
                </div>
                `;
            }).join('');
            resultsDiv.scrollTop = 0;

            resultsDiv.querySelectorAll('.manage-tag-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    this.showTagManageModal(
                        btn.dataset.tagId,
                        btn.dataset.tagName,
                        btn.dataset.tagCategory
                    );
                });
            });

        } catch (error) {
            if (error.name === 'AbortError') return;
            console.error('Error searching tags:', error);
            resultsDiv.innerHTML = '<p class="text-xs text-danger p-3">Error searching tags</p>';
        }
    }

    async deleteTag(tagId, tagName, tagCategory) {
        const modal = new ModalHelper({
            id: 'delete-tag-modal',
            type: 'danger',
            title: window.i18n.t('modal.delete_tag.title'),
            message: window.i18n.t('modal.delete_tag.message'),
            confirmText: window.i18n.t('common.yes_delete'),
            cancelText: window.i18n.t('common.cancel'),
            confirmId: 'delete-tag-confirm-yes',
            cancelId: 'delete-tag-confirm-no',
            onConfirm: async () => {
                try {
                    const result = await app.apiCall(`/api/admin/tags/${tagId}`, { method: 'DELETE' });
                    app.showNotification(window.i18n.t('notifications.admin.tag_deleted', { tag_name: result.tag_name }), 'success');
                    await this.searchTags();
                    await this.app.content.loadTagStats();
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('notifications.admin.error_deleting_tag'));
                }
            },
            onCancel: () => {
                if (tagName && tagCategory) {
                    this.showTagManageModal(tagId, tagName, tagCategory);
                }
            }
        });

        modal.show();
    }

    showTagManageModal(tagId, tagName, tagCategory) {
        const existingModal = document.getElementById('tag-manage-modal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'tag-manage-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full text-center">
                <h2 class="text-xl font-bold mb-2 text-primary">${window.i18n.t('admin.tags_management.manage_tag')}</h2>
                <p class="text-base mb-6 text font-medium">${this.app.escapeHtml(tagName)}</p>
                <div class="flex flex-col gap-3">
                    <button id="tag-manage-edit" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.Icons.edit({ size: 16 })}
                        ${window.i18n.t('admin.tags_management.edit_tag')}
                    </button>
                    <button id="tag-manage-merge" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.Icons.merge({ size: 16 })}
                        ${window.i18n.t('admin.tags_management.merge_tag')}
                    </button>
                    <button id="tag-manage-delete" class="px-6 py-3 transition-colors bg border border-danger text-danger hover:bg-danger hover:tag-text font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.Icons.trash({ size: 16 })}
                        ${window.i18n.t('modal.delete_tag.title')}
                    </button>
                    <button id="tag-manage-cancel" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.i18n.t('common.cancel')}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const handleEscape = (e) => {
            if (e.key === 'Escape') closeModal();
        };

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
        };

        document.getElementById('tag-manage-edit').addEventListener('click', () => {
            closeModal();
            this.showTagEditModal(tagId, tagName, tagCategory);
        });

        document.getElementById('tag-manage-merge').addEventListener('click', () => {
            closeModal();
            this.showTagMergeModal(tagId, tagName, tagCategory);
        });

        document.getElementById('tag-manage-delete').addEventListener('click', () => {
            closeModal();
            this.deleteTag(tagId, tagName, tagCategory);
        });

        document.getElementById('tag-manage-cancel').addEventListener('click', closeModal);

        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        document.addEventListener('keydown', handleEscape);
    }

    showTagMergeModal(tagId, tagName, tagCategory) {
        const existingModal = document.getElementById('tag-merge-modal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'tag-merge-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full text-left">
                <h2 class="text-xl font-bold mb-6 text-primary text-center">
                    ${window.i18n.t('admin.tags_management.merge_tag')}
                </h2>

                <div class="relative mb-6">
                    <label class="block text-xs font-bold mb-2">
                        ${window.i18n.t('admin.tags_management.target_tag_name')}
                    </label>
                    <input type="text" id="tag-merge-target-input"
                        class="w-full bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary"
                        placeholder="cat_ears" autocomplete="off" spellcheck="false">
                    <p id="tag-merge-target-error" class="text-xs text-danger mt-1" style="display:none;"></p>
                </div>

                <div class="flex gap-3 justify-center">
                    <button id="tag-merge-submit" class="btn-primary px-6 py-3 font-bold text-sm flex-1 cursor-pointer">
                        ${window.i18n.t('admin.tags_management.merge_into')}
                    </button>
                    <button id="tag-merge-cancel" class="btn px-6 py-3 font-bold text-sm flex-1 cursor-pointer">
                        ${window.i18n.t('common.cancel')}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const input = document.getElementById('tag-merge-target-input');
        const errorEl = document.getElementById('tag-merge-target-error');

        const validateTargetTag = () => {
            const val = input.value.trim().toLowerCase().replace(/\s+/g, '_');
            if (!val) {
                input.classList.add('border-danger');
                errorEl.textContent = window.i18n.t('admin.tags_management.target_tag_name');
                errorEl.style.display = '';
                return false;
            }
            if (val === tagName.toLowerCase()) {
                input.classList.add('border-danger');
                errorEl.textContent = window.i18n.t('notifications.admin.cannot_merge_self');
                errorEl.style.display = '';
                return false;
            }
            input.classList.remove('border-danger');
            errorEl.style.display = 'none';
            return true;
        };

        if (typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(input, {
                multipleValues: false,
                appendSpace: false,
                allowCreate: false,
                onSelect: () => {
                    validateTargetTag();
                }
            });
        }

        input.addEventListener('input', () => {
            const pos = input.selectionStart;
            input.value = input.value.replace(/ /g, '_');
            input.setSelectionRange(pos, pos);
            validateTargetTag();
        });

        input.focus();

        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                this.showTagManageModal(tagId, tagName, tagCategory);
            }
        };

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
        };

        document.getElementById('tag-merge-cancel').addEventListener('click', () => {
            closeModal();
            this.showTagManageModal(tagId, tagName, tagCategory);
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal();
                this.showTagManageModal(tagId, tagName, tagCategory);
            }
        });

        document.addEventListener('keydown', handleEscape);

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.getElementById('tag-merge-submit').click();
            }
        });

        document.getElementById('tag-merge-submit').addEventListener('click', async () => {
            if (!validateTargetTag()) return;
            const targetTag = input.value.trim().toLowerCase().replace(/\s+/g, '_');

            closeModal();

            const tagParams = {
                source_tag: this.app.escapeHtml(tagName),
                target_tag: this.app.escapeHtml(targetTag)
            };

            const subtitle = window.i18n.t('admin.tags_management.confirm_merge_subtitle', tagParams);
            const applyAction = window.i18n.t('admin.tags_management.confirm_merge_apply', tagParams);
            const deleteAction = window.i18n.t('admin.tags_management.confirm_merge_delete', tagParams);
            const aliasAction = window.i18n.t('admin.tags_management.confirm_merge_alias', tagParams);

            const messageHTML = `
                <div class="text-base font-semibold text mb-2">${subtitle}</div>
                <ul class="text-left text-sm space-y-2 text list-disc px-6">
                    <li>${applyAction}</li>
                    <li>${deleteAction}</li>
                    <li>${aliasAction}</li>
                </ul>
            `;

            const confirmModal = new ModalHelper({
                id: 'confirm-merge-tag-modal',
                type: 'warning',
                title: window.i18n.t('admin.tags_management.confirm_merge_title'),
                message: messageHTML,
                confirmText: window.i18n.t('admin.tags_management.merge_tag'),
                cancelText: window.i18n.t('common.cancel'),
                confirmId: 'confirm-merge-yes',
                cancelId: 'confirm-merge-no',
                onConfirm: async () => {
                    try {
                        const result = await app.apiCall(`/api/admin/tags/${tagId}/merge-into`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ target_tag_name: targetTag })
                        });
                        app.showNotification(
                            window.i18n.t('notifications.admin.tag_merged', {
                                source_tag: result.source_tag_name,
                                target_tag: result.target_tag_name
                            }),
                            'success'
                        );
                        await this.searchTags();
                        await this.app.content.loadTagStats();
                    } catch (e) {
                        app.showNotification(e.message, 'error', window.i18n.t('notifications.admin.error_merging_tag'));
                    }
                },
                onCancel: () => {
                    this.showTagManageModal(tagId, tagName, tagCategory);
                }
            });

            confirmModal.show();
        });
    }


    async showTagEditModal(tagId, tagName, tagCategory) {
        const existingModal = document.getElementById('tag-edit-modal');
        if (existingModal) existingModal.remove();

        // Fetch tag details including aliases
        let currentAliases = [];
        try {
            const res = await fetch(`/api/admin/tags/${tagId}`);
            if (res.ok) {
                const data = await res.json();
                if (Array.isArray(data.aliases)) {
                    currentAliases = data.aliases;
                }
            }
        } catch (e) {
            console.error('Error fetching tag details:', e);
        }

        const categories = [
            { value: 'general', label: window.i18n.t('common.tag_category_general') },
            { value: 'artist', label: window.i18n.t('common.tag_category_artist') },
            { value: 'character', label: window.i18n.t('common.tag_category_character') },
            { value: 'copyright', label: window.i18n.t('common.tag_category_copyright') },
            { value: 'meta', label: window.i18n.t('common.tag_category_meta') },
        ];

        const categoryOptions = categories.map(c =>
            `<div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="${c.value}">${c.label}</div>`
        ).join('');

        const currentCatLabel = (categories.find(c => c.value === tagCategory) || categories[0]).label;

        const modal = document.createElement('div');
        modal.id = 'tag-edit-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full">
                <h2 class="text-xl font-bold mb-6 text-primary text-center">${window.i18n.t('admin.tags_management.edit_tag')}</h2>

                <div class="mb-4">
                    <label class="block text-xs font-bold mb-2">${window.i18n.t('admin.tags_management.tag_name')}</label>
                    <input type="text" id="tag-edit-name" value="${this.app.escapeHtml(tagName)}"
                        class="w-full bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary"
                        autocomplete="off" spellcheck="false">
                    <p id="tag-edit-name-error" class="text-xs text-danger mt-1" style="display:none;"></p>
                </div>

                <div class="mb-4">
                    <label class="block text-xs font-bold mb-2">${window.i18n.t('admin.tags_management.tag_category')}</label>
                    <div id="tag-edit-category-select" class="custom-select w-full" data-value="${tagCategory}">
                        <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors focus:border-primary" type="button">
                            <span class="custom-select-value text">${currentCatLabel}</span>
                            ${window.Icons.selectArrow({ size: 12 })}
                        </button>
                        <div class="custom-select-dropdown bg border border-primary max-h-60 overflow-y-auto shadow-lg">
                            ${categoryOptions}
                        </div>
                    </div>
                </div>

                <div class="mb-6">
                    <label class="block text-xs font-bold mb-2">${window.i18n.t('admin.tags_management.tag_aliases')}</label>
                    <div id="tag-edit-aliases" contenteditable="true" spellcheck="false"
                        class="w-full bg px-3 py-2 border text-xs min-h-[60px] max-h-[120px] overflow-y-auto focus:outline-none hover:border-primary transition-colors focus:border-primary"></div>
                    <p class="text-xs text-secondary mt-1">${window.i18n.t('admin.tags_management.tag_aliases_hint')}</p>
                </div>

                <div class="flex gap-3 justify-center">
                    <button id="tag-edit-save" class="btn-primary px-6 py-3 font-bold text-sm flex-1 cursor-pointer">
                        ${window.i18n.t('common.save')}
                    </button>
                    <button id="tag-edit-cancel" class="btn px-6 py-3 font-bold text-sm flex-1 cursor-pointer">
                        ${window.i18n.t('common.cancel')}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const categorySelectEl = document.getElementById('tag-edit-category-select');
        const categorySelect = new CustomSelect(categorySelectEl);
        categorySelect.setValue(tagCategory);

        const aliasesInput = document.getElementById('tag-edit-aliases');
        const currentAliasSet = new Set(currentAliases.map(a => a.toLowerCase()));

        // Prepopulate aliases input
        if (currentAliases.length > 0) {
            aliasesInput.textContent = currentAliases.join(' ') + ' ';
        }

        // Setup alias validation using TagInputHelper in inverted mode
        const aliasValidationCache = new Map();
        const checkAliasConflict = async (alias) => {
            const normalized = alias.toLowerCase().trim();
            // If it's one of this tag's own aliases or the tag's current/new name, it's not a conflict
            if (currentAliasSet.has(normalized) || normalized === tagName.toLowerCase()) {
                return false;
            }
            return await this.app.tagInputHelper.checkTagOrAliasExists(normalized);
        };

        if (this.app.tagInputHelper) {
            this.app.tagInputHelper.setupTagInput(aliasesInput, 'tag-edit-aliases', {
                validationCache: aliasValidationCache,
                checkFunction: checkAliasConflict,
                invertLogic: true,
                expandImplications: false
            });
            // Initial styling pass
            await this.app.tagInputHelper.validateAndStyleTags(aliasesInput, {
                validationCache: aliasValidationCache,
                checkFunction: checkAliasConflict,
                invertLogic: true
            });
        }

        // Inverse validation with current tag's own name seeded as "not a conflict"
        const nameInput = document.getElementById('tag-edit-name');
        const nameError = document.getElementById('tag-edit-name-error');
        let nameConflict = false;
        let validationTimer = null;

        const validateName = async () => {
            const val = nameInput.value.trim().toLowerCase().replace(/\s+/g, '_');
            if (!val || val === tagName.toLowerCase()) {
                nameConflict = false;
                nameInput.classList.remove('border-danger');
                nameError.style.display = 'none';
                return;
            }
            // Check if name conflicts with an existing tag or alias
            try {
                const res = await fetch(`/api/tags/${encodeURIComponent(val)}`);
                if (res.ok) {
                    nameConflict = true;
                    nameInput.classList.add('border-danger');
                    nameError.textContent = window.i18n.t('notifications.admin.tag_name_conflict');
                    nameError.style.display = '';
                    return;
                }
                const aliasRes = await fetch(`/api/admin/check-alias?name=${encodeURIComponent(val)}`);
                if (aliasRes.ok) {
                    const aliasData = await aliasRes.json();
                    if (aliasData.exists) {
                        nameConflict = true;
                        nameInput.classList.add('border-danger');
                        nameError.textContent = window.i18n.t('notifications.admin.tag_name_conflict');
                        nameError.style.display = '';
                        return;
                    }
                }
            } catch (e) { /* network error: allow save */ }
            nameConflict = false;
            nameInput.classList.remove('border-danger');
            nameError.style.display = 'none';
        };

        nameInput.addEventListener('input', () => {
            // Replace spaces with underscores as user types
            const pos = nameInput.selectionStart;
            nameInput.value = nameInput.value.replace(/ /g, '_');
            nameInput.setSelectionRange(pos, pos);
            clearTimeout(validationTimer);
            validationTimer = setTimeout(validateName, 400);
        });

        nameInput.focus();
        nameInput.select();

        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                this.showTagManageModal(tagId, tagName, tagCategory);
            }
        };

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
        };

        const doSave = async () => {
            const newName = nameInput.value.trim().toLowerCase().replace(/\s+/g, '_');
            if (!newName) {
                nameInput.classList.add('border-danger');
                nameError.textContent = window.i18n.t('admin.tags_management.tag_name');
                nameError.style.display = '';
                return;
            }
            if (nameConflict) {
                nameInput.focus();
                return;
            }

            // Collect non-conflicting aliases from aliasesInput
            const aliasText = this.app.tagInputHelper ? this.app.tagInputHelper.getPlainTextFromDiv(aliasesInput) : (aliasesInput.textContent || '');
            const rawAliasTokens = aliasText.split(/\s+/).filter(t => t.length > 0);
            const validAliases = [];
            let aliasConflictFound = false;

            for (const token of rawAliasTokens) {
                const norm = token.toLowerCase().trim();
                // Check if marked invalid in cache
                if (aliasValidationCache.get(norm) === true) {
                    // In invertLogic, true means exists (conflict)
                    aliasConflictFound = true;
                } else {
                    validAliases.push(norm);
                }
            }

            if (aliasConflictFound) {
                aliasesInput.focus();
                app.showNotification(window.i18n.t('notifications.admin.tag_name_conflict') || 'Some aliases conflict with existing tags or aliases', 'error');
                return;
            }

            const newCategory = categorySelect.getValue();
            closeModal();
            try {
                const result = await app.apiCall(`/api/admin/tags/${tagId}`, {
                    method: 'PUT',
                    body: JSON.stringify({ name: newName, category: newCategory, aliases: validAliases })
                });
                app.showNotification(
                    window.i18n.t('notifications.admin.tag_updated', { old_name: result.old_name }),
                    'success'
                );
                await this.searchTags();
                await this.app.content.loadTagStats();
            } catch (e) {
                app.showNotification(e.message, 'error', window.i18n.t('notifications.admin.error_updating_tag'));
            }
        };

        document.getElementById('tag-edit-save').addEventListener('click', doSave);
        document.getElementById('tag-edit-cancel').addEventListener('click', () => {
            closeModal();
            this.showTagManageModal(tagId, tagName, tagCategory);
        });

        nameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); doSave(); }
        });

        document.addEventListener('keydown', handleEscape);
    }

    async clearAllTags() {
        const firstModal = new ModalHelper({
            id: 'clear-tags-first-modal',
            type: 'danger',
            title: window.i18n.t('modal.clear_tags.title'),
            message: window.i18n.t('modal.clear_tags.message'),
            confirmText: window.i18n.t('modal.clear_tags.confirm'),
            cancelText: window.i18n.t('common.cancel'),
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
                    cancelText: window.i18n.t('common.cancel'),
                    confirmId: 'clear-tags-second-confirm-yes',
                    cancelId: 'clear-tags-second-confirm-no',
                    onConfirm: async () => {
                        try {
                            await app.apiCall('/api/admin/clear-tags', { method: 'DELETE' });
                            app.showNotification(window.i18n.t('common.all_tags_cleared'), 'success');
                            await this.app.content.loadTagStats();
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

    handleApplyAllAliases() {
        new ModalHelper({
            type: 'warning',
            title: window.i18n.t('common.confirm_1_title'),
            message: window.i18n.t('admin.tags_management.apply_aliases_confirm_1_msg'),
            confirmText: window.i18n.t('common.yes'),
            cancelText: window.i18n.t('common.no'),
            onConfirm: async () => {
                this.executeApplyAllAliases();
            }
        }).show();
    }

    async executeApplyAllAliases() {
        const applyBtn = document.getElementById('apply-aliases-btn');
        if (applyBtn) {
            applyBtn.disabled = true;
        }

        if (typeof app !== 'undefined' && app.showNotification) {
            app.showNotification(window.i18n.t('admin.tags_management.apply_aliases_processing'), 'info');
        }

        try {
            const response = await fetch('/api/admin/simulate-apply-aliases', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to apply aliases');
            }

            const data = await response.json();
            const affectedMedia = data.affected_media || [];

            if (affectedMedia.length === 0) {
                if (typeof app !== 'undefined' && app.showNotification) {
                    app.showNotification(window.i18n.t('admin.tags_management.apply_aliases_no_affected'), 'info');
                }
            } else if (typeof BulkManualTagEditorModal !== 'undefined') {
                const affectedIds = affectedMedia.map(m => m.media_id);
                const prefillTags = {};
                const removeTags = {};
                affectedMedia.forEach(m => {
                    if (m.added_tags && m.added_tags.length) {
                        prefillTags[m.media_id] = m.added_tags;
                    }
                    if (m.removed_tags && m.removed_tags.length) {
                        removeTags[m.media_id] = m.removed_tags;
                    }
                });

                const modal = new BulkManualTagEditorModal({
                    prefillTags,
                    removeTags,
                    onSave: async () => {
                        try {
                            await fetch('/api/admin/cleanup-aliased-tags', { method: 'POST' });
                        } catch (e) {
                            console.error('Error cleaning up aliased tags:', e);
                        }
                    }
                });
                modal.show(affectedIds);
            } else {
                console.error('BulkManualTagEditorModal is not loaded');
            }
        } catch (e) {
            console.error('Error applying tag aliases:', e);
            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(e.message, 'error');
            }
        } finally {
            if (applyBtn) {
                applyBtn.disabled = false;
            }
        }
    }

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
        const albumSearchInput = document.getElementById('album-search-input');

        albumSearchInput?.addEventListener('input', () => {
            this.searchAlbums();
        });

        albumSearchInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
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
                        { value: '', text: window.i18n.t('admin.albums_management.none_root'), selected: true }
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
            await this.app.content.loadAlbumStats();
            await this.loadAlbums();

        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_creating_album'));
        }
    }

    async searchAlbums() {
        const searchInput = document.getElementById('album-search-input');
        const query = searchInput ? searchInput.value.trim() : '';
        const resultsDiv = document.getElementById('album-search-results');

        if (this._albumSearchAbortController) {
            this._albumSearchAbortController.abort();
            this._albumSearchAbortController = null;
        }

        if (!query) {
            if (resultsDiv) resultsDiv.innerHTML = '';
            return;
        }

        const abortController = new AbortController();
        this._albumSearchAbortController = abortController;

        try {
            const response = await fetch('/api/albums?limit=100&sort=name&order=asc', {
                signal: abortController.signal
            });
            if (!response.ok) return;
            const data = await response.json();

            // Guard against stale response if query changed in the meantime
            const currentQuery = document.getElementById('album-search-input')?.value.trim();
            if (!currentQuery) {
                if (resultsDiv) resultsDiv.innerHTML = '';
                return;
            }

            // Filter albums by name
            const filtered = (data.items || []).filter(album =>
                album.name.toLowerCase().includes(query.toLowerCase())
            );

            if (filtered.length === 0) {
                resultsDiv.innerHTML = '<p class="bg text-xs text-secondary p-3">' + window.i18n.t('album_picker.no_albums') + '</p>';
                resultsDiv.scrollTop = 0;
                return;
            }

            // Fetch parent chains in parallel with abort signal
            const albumItems = await Promise.all(
                filtered.map(async (album) => {
                    try {
                        const parentsResponse = await fetch(`/api/albums/${album.id}/parents`, {
                            signal: abortController.signal
                        });
                        if (parentsResponse.ok) {
                            const parentsData = await parentsResponse.json();
                            const parentChain = (parentsData.parents || []).map(p => p.name).join(' > ');
                            const immediateParentId = parentsData.parents && parentsData.parents.length > 0
                                ? parentsData.parents[parentsData.parents.length - 1].id
                                : null;
                            return { album, parentChain, immediateParentId };
                        }
                    } catch (e) {
                        if (e.name === 'AbortError') throw e;
                    }
                    return { album, parentChain: '', immediateParentId: null };
                })
            );

            resultsDiv.innerHTML = albumItems.map((item, i, arr) => {
                const { album, parentChain, immediateParentId } = item;
                let dateStr = '';
                const dateVal = album.created_at || album.last_modified;
                if (dateVal) {
                    const d = new Date(dateVal);
                    if (!isNaN(d.getTime())) {
                        dateStr = `${new Intl.DateTimeFormat(undefined, { dateStyle: "short" }).format(d)} ${new Intl.DateTimeFormat(undefined, { timeStyle: "short", hour12: false }).format(d)}`;
                    }
                }

                const pathDisplay = parentChain || window.i18n.t('albums.root_album');

                return `
                <div class="bg px-2 py-1.5 ${i === arr.length - 1 ? '' : 'border-b'} flex flex-wrap items-center gap-2">
                    <div class="flex items-center gap-2 min-w-0">
                        <button class="manage-album-btn flex-shrink-0 flex items-center justify-center w-7 h-7 bg-primary primary-text hover:bg-primary border-primary hover:border-primary transition-colors cursor-pointer"
                            data-album-id="${album.id}"
                            data-album-name="${this.app.escapeHtml(album.name)}"
                            data-parent-id="${immediateParentId || ''}"
                            title="${window.i18n.t('admin.albums_management.manage_album')}">
                            ${window.Icons.tagMenu({ size: 14 })}
                        </button>
                        <a href="/album/${album.id}" class="tag general tag-text overflow-hidden whitespace-nowrap text-ellipsis">${this.app.escapeHtml(album.name)}</a>
                    </div>
                    <div class="flex justify-between items-center gap-2 flex-1">
                        <span class="text-xs text-secondary">(${album.media_count || 0})</span>
                        ${dateStr ? `<span class="text-xs text-secondary text-center">${dateStr}</span>` : ''}
                        <span class="text-xs text-secondary uppercase flex-1 text-right truncate" title="${this.app.escapeHtml(pathDisplay)}">${this.app.escapeHtml(pathDisplay)}</span>
                    </div>
                </div>
                `;
            }).join('');
            resultsDiv.scrollTop = 0;

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
            if (error.name === 'AbortError') return;
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
                ${window.Icons.folder({ size: 48, class: 'mx-auto mb-4 text-primary' })}
                <h2 class="text-xl font-bold mb-2 text-primary">${window.i18n.t('admin.albums_management.manage_album')}</h2>
                <p class="text-base mb-6 text font-medium">${this.app.escapeHtml(albumName)}</p>
                <div class="flex flex-col gap-3">
                    <button id="album-manage-rename" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.Icons.edit({ size: 16 })}
                        ${window.i18n.t('admin.albums_management.rename_album')}
                    </button>
                    <button id="album-manage-parent" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.Icons.folderParent({ size: 16 })}
                        ${window.i18n.t('admin.albums_management.change_parent_album')}
                    </button>
                    <button id="album-manage-delete" class="px-6 py-3 transition-colors bg border border-danger text-danger hover:bg-danger hover:tag-text font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.Icons.trash({ size: 16 })}
                        ${window.i18n.t('common.delete_album')}
                    </button>
                    <button id="album-manage-cancel" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.i18n.t('common.close')}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Event listeners setup
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
            }
        };

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
        };

        document.getElementById('album-manage-rename').addEventListener('click', () => {
            closeModal();
            this.showRenameAlbumModal(albumId, albumName, currentParentId);
        });

        document.getElementById('album-manage-parent').addEventListener('click', () => {
            closeModal();
            this.showChangeParentModal(albumId, albumName, currentParentId);
        });

        document.getElementById('album-manage-delete').addEventListener('click', () => {
            closeModal();
            this.deleteAlbum(albumId, albumName, currentParentId);
        });

        document.getElementById('album-manage-cancel').addEventListener('click', closeModal);

        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

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
                    <input type="text" id="new-album-name" value="${this.app.escapeHtml(currentName)}"
                        class="w-full bg px-3 py-2 border text-sm focus:outline-none focus:border-primary">
                </div>
                <div class="flex gap-4 justify-center">
                    <button id="album-rename-confirm" class="btn-primary px-6 py-3 font-bold text-sm cursor-pointer">
                        Save
                    </button>
                    <button id="album-rename-cancel" class="btn px-6 py-3 font-bold text-sm cursor-pointer">
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
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                this.showAlbumManageModal(albumId, currentName, currentParentId);
            }
        };

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
        };

        const confirmRename = async () => {
            const newName = input.value.trim();
            if (!newName) {
                app.showNotification(window.i18n.t('notifications.admin.enter_name'), 'error');
                return;
            }
            if (newName === currentName) {
                closeModal();
                this.showAlbumManageModal(albumId, currentName, currentParentId);
                return;
            }

            closeModal();

            try {
                await app.apiCall(`/api/albums/${albumId}`, {
                    method: 'PUT',
                    body: JSON.stringify({ name: newName })
                });

                app.showNotification(window.i18n.t('notifications.admin.album_renamed'), 'success');
                await this.searchAlbums();
                await this.loadAlbums();
                await this.app.content.loadAlbumStats();

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
            closeModal();
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
                closeModal();
                this.showAlbumManageModal(albumId, currentName, currentParentId);
            }
        });

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
                data-value="">${window.i18n.t('admin.albums_management.none_root')}</div>
        `;
        for (const album of validAlbums) {
            const isSelected = currentParentId && album.id.toString() === currentParentId.toString();
            optionsHtml += `
                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs ${isSelected ? 'selected' : ''}"
                    data-value="${album.id}">${this.app.escapeHtml(album.name)}</div>
            `;
        }

        // Determine initial display text
        let initialDisplayText = window.i18n.t('admin.albums_management.none_root');
        if (currentParentId) {
            const currentParent = validAlbums.find(a => a.id.toString() === currentParentId.toString());
            if (currentParent) {
                initialDisplayText = currentParent.name;
            }
        }

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full">
                <h2 class="text-xl font-bold mb-2 text-primary text-center">Change Parent Album</h2>
                <p class="text-sm mb-4 text-secondary text-center">Album: <span class="text font-medium">${this.app.escapeHtml(albumName)}</span></p>
                <div class="mb-6">
                    <label class="block text-xs font-bold mb-2">New Parent Album</label>
                    <div id="change-parent-select" class="custom-select" data-value="${currentParentId || ''}">
                        <button
                            class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 bg border text-xs cursor-pointer focus:outline-none focus:border-primary"
                            type="button">
                            <span class="custom-select-value text">${this.app.escapeHtml(initialDisplayText)}</span>
                            ${window.Icons.selectArrow({ size: 12 })}
                        </button>
                        <div class="custom-select-dropdown bg border border-primary max-h-60 overflow-y-auto shadow-lg">
                            ${optionsHtml}
                        </div>
                    </div>
                </div>
                <div class="flex gap-4 justify-center">
                    <button id="album-parent-confirm" class="btn-primary px-6 py-3 font-bold text-sm cursor-pointer">
                        Save
                    </button>
                    <button id="album-parent-cancel" class="btn px-6 py-3 font-bold text-sm cursor-pointer">
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
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        };

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
        };

        document.getElementById('album-parent-confirm').addEventListener('click', async () => {
            const newParentId = selectElement.dataset.value;
            closeModal();

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
                await this.app.content.loadAlbumStats();

                // Return to manage modal with updated parent
                this.showAlbumManageModal(albumId, albumName, newParentId || null);

            } catch (error) {
                app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_updating_parent'));
                // Return to manage modal on error
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        });

        document.getElementById('album-parent-cancel').addEventListener('click', () => {
            closeModal();
            this.showAlbumManageModal(albumId, albumName, currentParentId);
        });

        // Close on outside click - return to manage modal
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal();
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        });

        document.addEventListener('keydown', handleEscape);
    }

    async deleteAlbum(albumId, albumName, currentParentId) {
        const modal = new ModalHelper({
            id: 'delete-album-modal',
            type: 'danger',
            title: window.i18n.t('common.delete_album'),
            message: window.i18n.t('modal.delete_album.message', { albumName: this.app.escapeHtml(albumName) }),
            confirmText: window.i18n.t('common.yes_delete'),
            cancelText: window.i18n.t('common.cancel'),
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
                    await this.app.content.loadAlbumStats();
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

}
