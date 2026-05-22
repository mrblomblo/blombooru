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
                if (data.model_name) this.wdModelSelect.setValue(data.model_name);
            }
        } catch (e) {
            console.error('Error loading AI Tagger settings:', e);
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

        const body = {};
        if (generalEl && generalEl.value) body.general_threshold = parseFloat(generalEl.value);
        if (charEl && charEl.value) body.character_threshold = parseFloat(charEl.value);
        if (modelName) body.model_name = modelName;
        body.blacklisted_tags = blacklistedTags;

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

    async generateMissingThumbnails() {
        const btn = document.getElementById('generate-missing-thumbnails-btn');
        const allBtn = document.getElementById('regenerate-all-thumbnails-btn');
        const statusDiv = document.getElementById('thumbnail-regen-status');
        const resultDiv = document.getElementById('thumbnail-regen-result');
        const originalText = btn.textContent;

        btn.disabled = true;
        allBtn.disabled = true;
        btn.textContent = window.i18n.t('admin.media_management.thumbnails.generating');
        statusDiv.style.display = 'block';
        resultDiv.innerHTML = `<div class="bg-primary primary-text p-3"><strong>${window.i18n.t('admin.media_management.thumbnails.generating')}</strong></div>`;

        try {
            const result = await app.apiCall('/api/admin/generate-missing-thumbnails', { method: 'POST' });
            const msg = window.i18n.t('admin.media_management.thumbnails.done_missing', {
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
                btn.textContent = window.i18n.t('admin.media_management.thumbnails.generating');
                statusDiv.style.display = 'block';
                resultDiv.innerHTML = `<div class="bg-primary primary-text p-3"><strong>${window.i18n.t('admin.media_management.thumbnails.generating')}</strong></div>`;

                try {
                    const result = await app.apiCall('/api/admin/regenerate-all-thumbnails', { method: 'POST' });
                    const msg = window.i18n.t('admin.media_management.thumbnails.done_all', {
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
                resultsDiv.innerHTML = '<p class="bg border text-xs text-secondary p-3">' + window.i18n.t('gallery.no_tags_found') + '</p>';
                return;
            }

            resultsDiv.innerHTML = data.tags.map((tag, i, arr) => `
                <div class="bg p-3 ${arr.length === 1 ? 'border' : (i === arr.length - 1 ? '' : 'border-b')} flex justify-between items-center">
                    <div class="flex items-center gap-2">
                        <button class="manage-tag-btn flex items-center justify-center w-7 h-7 bg-primary hover:bg-primary border-primary hover:border-primary transition-colors"
                            data-tag-id="${tag.id}"
                            data-tag-name="${this.app.escapeHtml(tag.name)}"
                            data-tag-category="${tag.category}"
                            title="${window.i18n.t('admin.tags_management.manage_tag')}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="var(--primary-text)">
                                <rect x="3" y="5" width="18" height="2"/>
                                <rect x="3" y="11" width="18" height="2"/>
                                <rect x="3" y="17" width="18" height="2"/>
                            </svg>
                        </button>
                        <a href="/?q=${encodeURIComponent(tag.name)}" class="tag ${tag.category} tag-text">${tag.name}</a>
                        <span class="text-xs text-secondary">(${tag.post_count})</span>
                    </div>
                    <span class="text-xs text-secondary uppercase">${tag.category}</span>
                </div>
                `).join('');

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
                    <button id="tag-manage-edit" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                        </svg>
                        ${window.i18n.t('admin.tags_management.edit_tag')}
                    </button>
                    <button id="tag-manage-delete" class="px-6 py-3 transition-colors bg border border-danger text-danger hover:bg-danger hover:tag-text font-bold text-sm flex items-center justify-center gap-2">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                        </svg>
                        ${window.i18n.t('modal.delete_tag.title')}
                    </button>
                    <button id="tag-manage-cancel" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2">
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

    showTagEditModal(tagId, tagName, tagCategory) {
        const existingModal = document.getElementById('tag-edit-modal');
        if (existingModal) existingModal.remove();

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

                <div class="mb-6">
                    <label class="block text-xs font-bold mb-2">${window.i18n.t('admin.tags_management.tag_category')}</label>
                    <div id="tag-edit-category-select" class="custom-select w-full" data-value="${tagCategory}">
                        <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors focus:border-primary" type="button">
                            <span class="custom-select-value text">${currentCatLabel}</span>
                            <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary" width="12" height="12" viewBox="0 0 12 12">
                                <path fill="currentColor" d="M6 9L1 4h10z" />
                            </svg>
                        </button>
                        <div class="custom-select-dropdown bg border border-primary max-h-60 overflow-y-auto shadow-lg">
                            ${categoryOptions}
                        </div>
                    </div>
                </div>

                <div class="flex gap-3 justify-center">
                    <button id="tag-edit-save" class="btn-primary px-6 py-3 font-bold text-sm flex-1">
                        ${window.i18n.t('common.save')}
                    </button>
                    <button id="tag-edit-cancel" class="btn px-6 py-3 font-bold text-sm flex-1">
                        ${window.i18n.t('common.cancel')}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const categorySelectEl = document.getElementById('tag-edit-category-select');
        const categorySelect = new CustomSelect(categorySelectEl);
        categorySelect.setValue(tagCategory);

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
            const newCategory = categorySelect.getValue();
            closeModal();
            try {
                const result = await app.apiCall(`/api/admin/tags/${tagId}`, {
                    method: 'PUT',
                    body: JSON.stringify({ name: newName, category: newCategory })
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
                resultsDiv.innerHTML = '<p class="bg border text-xs text-secondary p-3">' + window.i18n.t('album_picker.no_albums') + '</p>';
                return;
            }

            // Build results HTML
            let html = '';
            for (let i = 0; i < filtered.length; i++) {
                const album = filtered[i];
                // Get parent info
                const parentsResponse = await fetch(`/api/albums/${album.id}/parents`);
                const parentsData = await parentsResponse.json();
                const parentChain = parentsData.parents.map(p => p.name).join(' > ');
                const immediateParentId = parentsData.parents.length > 0
                    ? parentsData.parents[parentsData.parents.length - 1].id
                    : null;

                const borderClass = filtered.length === 1 ? 'border' : (i === filtered.length - 1 ? '' : 'border-b');

                html += `
                    <div class="bg p-3 ${borderClass} flex justify-between items-center">
                        <div class="flex-1">
                            <div class="flex items-center gap-2 mb-1">
                                <a href="/album/${album.id}" class="text-sm font-bold hover:text-primary">${this.app.escapeHtml(album.name)}</a>
                                <span class="text-xs text-secondary">(${album.media_count || 0} media)</span>
                            </div>
                            ${parentChain ? `<div class="text-xs text-secondary">Path: ${this.app.escapeHtml(parentChain)}</div>` : '<div class="text-xs text-secondary">' + window.i18n.t('albums.root_album') + '</div>'}
                        </div>
                        <div class="flex gap-2">
                            <button class="manage-album-btn btn-primary px-3 py-1"
                                data-album-id="${album.id}"
                                data-album-name="${this.app.escapeHtml(album.name)}"
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
                <p class="text-base mb-6 text font-medium">${this.app.escapeHtml(albumName)}</p>
                <div class="flex flex-col gap-3">
                    <button id="album-manage-rename" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                        </svg>
                        ${window.i18n.t('admin.albums_management.rename_album')}
                    </button>
                    <button id="album-manage-parent" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/>
                        </svg>
                        ${window.i18n.t('admin.albums_management.change_parent_album')}
                    </button>
                    <button id="album-manage-delete" class="px-6 py-3 transition-colors bg border border-danger text-danger hover:bg-danger hover:tag-text font-bold text-sm flex items-center justify-center gap-2">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                        </svg>
                        ${window.i18n.t('common.delete_album')}
                    </button>
                    <button id="album-manage-cancel" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2">
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
                    <button id="album-rename-confirm" class="btn-primary px-6 py-3 font-bold text-sm">
                        Save
                    </button>
                    <button id="album-rename-cancel" class="btn px-6 py-3 font-bold text-sm">
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
                    <button id="album-parent-confirm" class="btn-primary px-6 py-3 font-bold text-sm">
                        Save
                    </button>
                    <button id="album-parent-cancel" class="btn px-6 py-3 font-bold text-sm">
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
