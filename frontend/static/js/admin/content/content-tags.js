// AdminContent tag creation, CSV import, search, management modals, and tag rules
Object.assign(AdminContent.prototype, {
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
    },

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
    },

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
    },

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
    },

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

        const applyTagRatingsBtn = document.getElementById('apply-tag-ratings-btn');
        applyTagRatingsBtn?.addEventListener('click', () => this.handleApplyTagRatings());

        // Clear tags
        const clearBtn = document.getElementById('clear-tags-btn');
        clearBtn?.addEventListener('click', () => this.clearAllTags());

        // Setup Media Type Tags
        this.setupMediaTypeTags();

        // Setup Automatic AI Metadata Tags
        this.setupAutoApplyAITags();
    },

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
    },

    setupAutoApplyAITags() {
        const autoApplyAITagsForm = document.getElementById('auto-apply-ai-tags-form');
        if (autoApplyAITagsForm) {
            autoApplyAITagsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.saveAutoApplyAITags();
            });
        }
    },

    async saveAutoApplyAITags() {
        const el = document.getElementById('auto-apply-ai-tags');
        const enabled = el ? el.checked : false;

        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify({ auto_apply_ai_tags: enabled })
            });

            app.showNotification(window.i18n.t('notifications.admin.auto_apply_ai_tags_saved') || window.i18n.t('notifications.admin.settings_updated'), 'success');
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_saving_settings'));
        }
    },

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
    },

    async loadTagStats() {
        try {
            const response = await fetch('/api/admin/tag-stats');
            const stats = await response.json();

            const totalTagsEl = document.getElementById('total-tags');
            const totalAliasesEl = document.getElementById('total-aliases');
            const totalImplicationsEl = document.getElementById('total-implications');

            if (totalTagsEl) totalTagsEl.textContent = stats.total_tags;
            if (totalAliasesEl) totalAliasesEl.textContent = stats.total_aliases;
            if (totalImplicationsEl) totalImplicationsEl.textContent = stats.total_implications;
        } catch (error) {
            console.error('Error loading tag stats:', error);
        }
    },

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
    },

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
                const creationDateStr = formatDateTime(tag.created_at);

                const tagRatingVal = tag.rating || 'none';
                const ratingBadgeHtml = (typeof TagRating !== 'undefined')
                    ? TagRating.renderBadge(tagRatingVal)
                    : `<span class="tag rating-${tagRatingVal} tag-text uppercase text-[10px] font-bold tracking-wider px-2 py-0.5 select-none">${tagRatingVal}</span>`;

                return `
                <div class="bg px-2 py-1.5 ${i === arr.length - 1 ? '' : 'border-b'} flex flex-wrap items-center gap-2" data-tag-rating="${tagRatingVal}">
                    <div class="flex items-center gap-2 min-w-0">
                        <button class="manage-tag-btn flex-shrink-0 flex items-center justify-center w-7 h-7 bg-primary primary-text hover:bg-primary border-primary hover:border-primary transition-colors cursor-pointer"
                            data-tag-id="${tag.id}"
                            data-tag-name="${escapeHtml(tag.name)}"
                            data-tag-category="${tag.category}"
                            data-tag-rating="${tagRatingVal}"
                            title="${window.i18n.t('admin.tags_management.manage_tag')}">
                            ${window.Icons.tagMenu({ size: 14 })}
                        </button>
                        <a href="/?q=${encodeURIComponent(tag.name)}" class="tag ${tag.category} tag-text overflow-hidden whitespace-nowrap text-ellipsis" data-tag-rating="${tagRatingVal}">${tag.name}</a>
                    </div>
                    <div class="flex justify-between items-center gap-2 flex-1">
                        <span class="text-xs text-secondary">(${tag.post_count})</span>
                        ${creationDateStr ? `<span class="text-xs text-secondary text-center">${creationDateStr}</span>` : ''}
                        <div class="flex items-center gap-2 ml-auto">
                            <span class="text-xs text-secondary uppercase">${tag.category}</span>
                            ${ratingBadgeHtml}
                        </div>
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
                        btn.dataset.tagCategory,
                        btn.dataset.tagRating
                    );
                });
            });

        } catch (error) {
            if (error.name === 'AbortError') return;
            console.error('Error searching tags:', error);
            resultsDiv.innerHTML = '<p class="text-xs text-danger p-3">Error searching tags</p>';
        }
    },

    async deleteTag(tagId, tagName, tagCategory, tagRating) {
        TagManageModals.remove({
            tagId, tagName, tagCategory, tagRating,
            onCancel: () => this.showTagManageModal(tagId, tagName, tagCategory, tagRating),
            onDeleted: () => this.refreshTagViews()
        });
    },

    async refreshTagViews() {
        await this.searchTags();
        await this.app.content.loadTagStats();
    },

    showTagManageModal(tagId, tagName, tagCategory, tagRating) {
        const existingModal = document.getElementById('tag-manage-modal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'tag-manage-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full text-center">
                <h2 class="text-xl font-bold mb-2 text-primary">${window.i18n.t('admin.tags_management.manage_tag')}</h2>
                <p class="text-base mb-6 text font-medium">${escapeHtml(tagName)}</p>
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
            this.showTagEditModal(tagId, tagName, tagCategory, tagRating);
        });

        document.getElementById('tag-manage-merge').addEventListener('click', () => {
            closeModal();
            this.showTagMergeModal(tagId, tagName, tagCategory, tagRating);
        });

        document.getElementById('tag-manage-delete').addEventListener('click', () => {
            closeModal();
            this.deleteTag(tagId, tagName, tagCategory, tagRating);
        });

        document.getElementById('tag-manage-cancel').addEventListener('click', closeModal);

        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        document.addEventListener('keydown', handleEscape);
    },

    showTagMergeModal(tagId, tagName, tagCategory, tagRating) {
        TagManageModals.merge({
            tagId, tagName,
            onCancel: () => this.showTagManageModal(tagId, tagName, tagCategory, tagRating),
            onMerged: () => this.refreshTagViews()
        });
    },

    async showTagEditModal(tagId, tagName, tagCategory, tagRating) {
        await TagManageModals.edit({
            tagId, tagName, tagCategory, tagRating,
            tagInputHelper: this.app.tagInputHelper,
            onCancel: () => this.showTagManageModal(tagId, tagName, tagCategory, tagRating),
            onSaved: () => this.refreshTagViews()
        });
    },

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
    },

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
    },

    async executeApplyAllAliases() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.start('apply_aliases');
        }
    },

    handleApplyTagRatings() {
        new ModalHelper({
            type: 'warning',
            title: window.i18n.t('common.confirm_1_title'),
            message: window.i18n.t('admin.tags_management.apply_tag_ratings_confirm_msg'),
            confirmText: window.i18n.t('common.yes'),
            cancelText: window.i18n.t('common.no'),
            onConfirm: async () => {
                this.executeApplyTagRatings();
            }
        }).show();
    },

    async executeApplyTagRatings() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.start('apply_tag_ratings');
        }
    },
});
