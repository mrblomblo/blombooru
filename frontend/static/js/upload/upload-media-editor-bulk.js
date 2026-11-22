// UploadMediaEditor bulk-item editor rendering, shared value computation, and event handlers
Object.assign(UploadMediaEditor.prototype, {
    getCommonSuggestedAlbumPath() {
        const items = Array.from(this.selectedIds).map(id => this.session.getItem(id)).filter(Boolean);
        if (items.length === 0) return null;
        const firstPath = items[0].suggested_album_path;
        if (!firstPath) return null;
        for (let i = 1; i < items.length; i++) {
            if (items[i].suggested_album_path !== firstPath) return null;
        }
        return firstPath;
    },

    getCommonAlbumIds() {
        const items = Array.from(this.selectedIds).map(id => this.session.getItem(id)).filter(Boolean);
        if (items.length === 0) return [];
        let common = new Set(items[0].album_ids || []);
        for (let i = 1; i < items.length; i++) {
            const curAids = new Set(items[i].album_ids || []);
            common = new Set([...common].filter(id => curAids.has(id)));
        }
        return Array.from(common);
    },

    getCommonTags() {
        const items = Array.from(this.selectedIds).map(id => this.session.getItem(id)).filter(Boolean);
        if (items.length === 0) return [];
        let commonMap = new Map();
        (items[0].tags || []).forEach(t => {
            if (t && t.name) {
                commonMap.set(t.name.toLowerCase(), t);
            }
        });

        for (let i = 1; i < items.length; i++) {
            const curNames = new Set((items[i].tags || []).filter(t => t && t.name).map(t => t.name.toLowerCase()));
            for (const name of commonMap.keys()) {
                if (!curNames.has(name)) {
                    commonMap.delete(name);
                }
            }
        }

        return Array.from(commonMap.values());
    },

    getSharedValues() {
        const items = Array.from(this.selectedIds).map(id => this.session.getItem(id)).filter(Boolean);
        if (items.length === 0) return {};

        let sharedRating = items[0].rating;
        let sharedSource = items[0].source;
        let sharedDescription = items[0].description;
        let sharedDate = items[0].custom_date;

        for (let i = 1; i < items.length; i++) {
            const it = items[i];
            if (sharedRating !== undefined && it.rating !== sharedRating) sharedRating = undefined;
            if (sharedSource !== undefined && it.source !== sharedSource) sharedSource = undefined;
            if (sharedDescription !== undefined && it.description !== sharedDescription) sharedDescription = undefined;
            if (sharedDate !== undefined && it.custom_date !== sharedDate) sharedDate = undefined;
        }

        return {
            rating: sharedRating !== undefined ? sharedRating : '',
            source: sharedSource !== undefined ? sharedSource : '',
            description: sharedDescription !== undefined ? sharedDescription : '',
            custom_date: sharedDate !== undefined ? sharedDate : ''
        };
    },

    renderBulkEditor() {
        clearTimeout(this.bulkTagSaveTimeout);

        const count = this.selectedIds.size;
        const shared = this.getSharedValues();
        const commonSuggestedPath = this.getCommonSuggestedAlbumPath();
        const commonAlbumIds = this.getCommonAlbumIds();
        const commonFolderExcluded = Array.from(this.getCommonFolderAlbumExcludedIds());
        const bulkExcludedIds = Array.from(new Set([...commonAlbumIds, ...commonFolderExcluded]));
        const commonTags = this.getCommonTags();
        const tagsPlainText = commonTags.map(t => t.name).join(' ');
        const descPlaceholder = window.i18n.t('media.info.description_placeholder');

        this.container.innerHTML = `
            <div class="surface border p-4 text-xs">
                <!-- Header -->
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-3 mb-3">
                    <div class="flex items-center gap-2 min-w-0">
                        <h4 class="text-xs font-bold text">
                            ${window.i18n.t('upload.bulk.editing_selected', { count })}
                        </h4>
                    </div>

                    <div class="flex items-center gap-2 shrink-0">
                        <!-- Bulk Delete Button -->
                        <button type="button" id="editor-remove-bulk-btn" class="btn-danger text-xs px-2.5 py-1 flex items-center gap-1.5 cursor-pointer">
                            ${window.Icons.trash({ size: 12 })}
                            <span>${window.i18n.t('upload.bulk.remove_selected', { count })}</span>
                        </button>
                    </div>
                </div>

                <!-- Bulk Rating & Source Row -->
                <div class="flex flex-col sm:flex-row gap-3 mb-3">
                    <!-- Bulk Rating (Compact Width) -->
                    <div class="w-full sm:w-36 shrink-0">
                        <label class="block text-xs font-bold mb-1">
                            ${window.i18n.t('media.info.rating')}
                        </label>
                        <div id="editor-bulk-rating" class="custom-select w-full" data-value="${shared.rating || ''}">
                            <div class="custom-select-trigger w-full flex items-center justify-between gap-2 px-3 py-1.5 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors">
                                <span class="custom-select-value text ${shared.rating ? 'capitalize' : 'text-secondary'}">${shared.rating ? shared.rating : (window.i18n.t('upload.bulk.choose_rating'))}</span>
                                ${window.Icons.chevronDown({ size: 10, class: 'custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary', style: 'display: block;' })}
                            </div>
                            <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50">
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${!shared.rating ? 'selected' : ''}" data-value="">${window.i18n.t('upload.bulk.choose_rating')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${shared.rating === 'safe' ? 'selected' : ''}" data-value="safe">${window.i18n.t('common.safe')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${shared.rating === 'questionable' ? 'selected' : ''}" data-value="questionable">${window.i18n.t('common.questionable')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${shared.rating === 'explicit' ? 'selected' : ''}" data-value="explicit">${window.i18n.t('common.explicit')}</div>
                            </div>
                        </div>
                    </div>

                    <!-- Bulk Source (Fills Remaining Space) -->
                    <div class="flex-1 min-w-0">
                        <label class="block text-xs font-bold mb-1">
                            ${window.i18n.t('media.info.source')}
                        </label>
                        <div class="flex items-center gap-1.5">
                            <input type="url" id="editor-bulk-source"
                                class="flex-1 bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                                value="${escapeHtml(shared.source || '')}"
                                placeholder="https://example.com/source">
                            <button type="button" id="editor-bulk-apply-source-btn" class="btn-primary text-xs px-2.5 py-1.5 cursor-pointer shrink-0">
                                ${window.i18n.t('common.apply')}
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Bulk Date -->
                <div class="mb-3">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('media.info.custom_date')}
                    </label>
                    <div class="flex items-center gap-1.5">
                        <input type="datetime-local" id="editor-bulk-custom-date"
                            class="flex-1 bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                            value="${toLocalInputDateTime(shared.custom_date)}">
                        <button type="button" id="editor-bulk-apply-date-btn" class="btn-primary text-xs px-2.5 py-1.5 cursor-pointer shrink-0">
                            ${window.i18n.t('common.apply')}
                        </button>
                    </div>
                </div>

                <!-- Bulk Description -->
                <div class="mb-3">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('common.description')}
                    </label>
                    <div class="flex flex-col gap-1.5">
                        <textarea id="editor-bulk-description" rows="2"
                            class="auto-expand-textarea w-full bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                            placeholder="${escapeHtml(descPlaceholder)}">${escapeHtml(shared.description || '')}</textarea>
                        <div class="flex justify-end">
                            <button type="button" id="editor-bulk-apply-desc-btn" class="btn-primary text-xs px-2.5 py-1 cursor-pointer">
                                ${window.i18n.t('common.apply')}
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Common Folder Album -->
                ${commonSuggestedPath ? `
                <div class="mb-3" id="editor-bulk-folder-album">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('upload.bulk.common_folder_album')}
                    </label>
                    <div class="bg px-2 py-1 border text-xs flex items-center justify-between gap-2">
                        <div class="flex items-center gap-1.5 min-w-0">
                            <span class="text-secondary shrink-0">${window.Icons.folder({ size: 12 })}</span>
                            <span class="font-mono text-xs truncate" title="${escapeHtml(commonSuggestedPath)}">${escapeHtml(commonSuggestedPath)}</span>
                        </div>
                        <button type="button" id="editor-bulk-remove-folder-album-btn" class="text-danger hover:text-danger transition-colors cursor-pointer p-0.5 flex items-center justify-center shrink-0" title="${window.i18n.t('upload.folder.remove_album_path')}">
                            ${window.Icons.trash({ size: 12, class: 'transition-colors' })}
                        </button>
                    </div>
                </div>
                ` : ''}

                <!-- Bulk Albums -->
                <div class="mb-3">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('common.albums')}
                    </label>
                    <div id="editor-bulk-albums-badges" class="flex flex-wrap gap-1.5 mb-1.5" style="${commonAlbumIds.length > 0 ? '' : 'display: none;'}">
                        ${this.renderAlbumBadgesHtml(commonAlbumIds)}
                    </div>
                    <div class="flex items-center gap-1.5">
                        <div id="editor-bulk-album-select" class="custom-select flex-1" data-value="">
                            <div class="custom-select-trigger w-full flex items-center justify-between gap-2 px-3 py-1.5 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors">
                                <span class="custom-select-value text text-secondary">${window.i18n.t('upload.base_settings.select_album')}</span>
                                ${window.Icons.chevronDown({ size: 10, class: 'custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary', style: 'display: block;' })}
                            </div>
                            <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50">
                                ${this.renderAlbumOptionsHtml(bulkExcludedIds)}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Tags Input -->
                <div class="mb-3">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('common.tags')}
                    </label>
                    <div class="relative">
                        <div id="editor-bulk-tags-input" contenteditable="true" data-placeholder="original highres cat_ears"
                            class="w-full bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors min-h-7.5"
                            style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;">${escapeHtml(tagsPlainText)}</div>
                    </div>
                </div>

                <!-- Bulk Common Tags Display -->
                <div class="mb-1">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('upload.bulk.common_tags')}
                    </label>
                    <div id="editor-bulk-common-tags-chips" class="p-2 bg border min-h-8.5 flex flex-wrap gap-1 text-xs items-center max-w-full min-w-0"></div>
                </div>
            </div>
        `;

        this.setupBulkEvents();
    },

    setupBulkEvents() {
        const itemIds = Array.from(this.selectedIds);

        // Baseline tracking to diff the tag input
        const commonTags = this.getCommonTags();
        this.lastBulkTagNames = new Set(commonTags.map(t => t.name.toLowerCase()));
        this.bulkCommonTagsMap = new Map(commonTags.map(t => [t.name.toLowerCase(), t]));
        this.bulkTagUpdateChain = Promise.resolve();

        // Bulk Delete
        const removeBulkBtn = this.container.querySelector('#editor-remove-bulk-btn');
        if (removeBulkBtn) {
            removeBulkBtn.addEventListener('click', () => {
                if (itemIds.length === 0) return;
                const doDelete = () => {
                    itemIds.forEach(id => this.session.deleteItem(id));
                    if (this.options.onItemsDeleted) {
                        this.options.onItemsDeleted(itemIds);
                    }
                };
                if (typeof ModalHelper !== 'undefined') {
                    new ModalHelper({
                        type: 'danger',
                        title: window.i18n.t('modal.bulk_delete.title_single'),
                        message: window.i18n.t('upload.bulk.delete_confirm', { count: itemIds.length }),
                        confirmText: window.i18n.t('common.yes_remove'),
                        cancelText: window.i18n.t('common.cancel'),
                        onConfirm: doDelete
                    }).show();
                } else {
                    doDelete();
                }
            });
        }

        // Bulk Rating
        const ratingEl = this.container.querySelector('#editor-bulk-rating');
        if (ratingEl && typeof CustomSelect !== 'undefined') {
            this.bulkRatingSelect = new CustomSelect(ratingEl);
            ratingEl.addEventListener('change', async (e) => {
                const rating = e.detail.value;
                if (rating && itemIds.length > 0) {
                    await this.session.bulkUpdate(itemIds, { rating });
                    if (this.options.onItemChanged) this.options.onItemChanged();
                }
            });
        }

        // Bulk Source
        const sourceInput = this.container.querySelector('#editor-bulk-source');
        const sourceApplyBtn = this.container.querySelector('#editor-bulk-apply-source-btn');
        const applyBulkSource = async () => {
            const source = sourceInput?.value.trim();
            if (source !== undefined && itemIds.length > 0) {
                try {
                    await this.session.bulkUpdate(itemIds, { source });
                    window.app.showNotification(window.i18n.t('upload.bulk.source_applied'), 'success');
                    if (this.options.onItemChanged) this.options.onItemChanged();
                } catch (e) {
                    console.error('Failed to bulk update source:', e);
                    window.app.showNotification(e.message, 'error');
                }
            }
        };
        if (sourceApplyBtn) sourceApplyBtn.addEventListener('click', applyBulkSource);
        if (sourceInput) {
            sourceInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    applyBulkSource();
                }
            });
        }

        // Bulk Custom Date
        const bulkDateInput = this.container.querySelector('#editor-bulk-custom-date');
        const bulkDateApplyBtn = this.container.querySelector('#editor-bulk-apply-date-btn');
        const applyBulkDate = async () => {
            const isoStr = parseLocalInputDateTime(bulkDateInput?.value);
            if (itemIds.length > 0) {
                try {
                    await this.session.bulkUpdate(itemIds, { custom_date: isoStr });
                    window.app.showNotification(window.i18n.t('upload.bulk.date_applied'), 'success');
                    if (this.options.onItemChanged) this.options.onItemChanged();
                } catch (e) {
                    console.error('Failed to bulk update date:', e);
                    window.app.showNotification(e.message, 'error');
                }
            }
        };
        if (bulkDateApplyBtn) bulkDateApplyBtn.addEventListener('click', applyBulkDate);
        if (bulkDateInput) {
            bulkDateInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    applyBulkDate();
                }
            });
        }

        // Bulk Description
        const descInput = this.container.querySelector('#editor-bulk-description');
        if (descInput) {
            this.autoResizeTextarea(descInput);
            descInput.addEventListener('input', (e) => {
                this.autoResizeTextarea(e.target);
            });
            descInput.addEventListener('keydown', (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault();
                    applyBulkDescription();
                }
            });
        }
        const descApplyBtn = this.container.querySelector('#editor-bulk-apply-desc-btn');
        const applyBulkDescription = async () => {
            const description = descInput?.value.trim();
            if (description !== undefined && itemIds.length > 0) {
                try {
                    await this.session.bulkUpdate(itemIds, { description });
                    window.app.showNotification(window.i18n.t('upload.bulk.description_applied'), 'success');
                    if (this.options.onItemChanged) this.options.onItemChanged();
                } catch (e) {
                    console.error('Failed to bulk update description:', e);
                    window.app.showNotification(e.message, 'error');
                }
            }
        };
        if (descApplyBtn) descApplyBtn.addEventListener('click', applyBulkDescription);

        // Bulk Folder Album remove
        const bulkRemoveFolderAlbumBtn = this.container.querySelector('#editor-bulk-remove-folder-album-btn');
        if (bulkRemoveFolderAlbumBtn) {
            bulkRemoveFolderAlbumBtn.addEventListener('click', async () => {
                itemIds.forEach(id => {
                    const it = this.session.getItem(id);
                    if (it) {
                        it.suggested_album_path = null;
                        it.suggested_album_segments = null;
                    }
                });
                await this.session.bulkUpdate(itemIds, { suggested_album_path: null });
                this.renderBulkEditor();
                if (this.options.onItemChanged) this.options.onItemChanged();
            });
        }

        // Bulk Album Badges
        this.setupBulkAlbumBadgeEvents(itemIds);

        // Bulk Album Select
        const albumEl = this.container.querySelector('#editor-bulk-album-select');
        if (albumEl && typeof CustomSelect !== 'undefined') {
            this.bulkAlbumSelect = new CustomSelect(albumEl);
            albumEl.addEventListener('change', async (e) => {
                const aid = parseInt(e.detail.value);
                if (aid && itemIds.length > 0) {
                    await this.session.bulkUpdate(itemIds, { add_album_ids: [aid] });
                    this.refreshBulkAlbumBadges();
                    window.app.showNotification(window.i18n.t('upload.bulk.album_added'), 'success');
                    if (this.options.onItemChanged) this.options.onItemChanged();
                }
            });
        }

        // Common Tags Preview Component
        const commonTagsContainer = this.container.querySelector('#editor-bulk-common-tags-chips');
        if (commonTagsContainer && typeof TagPreview !== 'undefined') {
            this.bulkTagPreview = new TagPreview(commonTagsContainer, {
                allowCategoryChange: true,
                resolveAliases: false,
                onCategoryChange: async (tag, newCat) => {
                    await this.session.updatePendingTag(tag.name, { category: newCat });
                    if (this.options.onItemChanged) this.options.onItemChanged();
                }
            });
            this.bulkTagPreview.setTags(commonTags);
        }

        // Bulk Tags Input
        const bulkTagsInput = this.container.querySelector('#editor-bulk-tags-input');
        if (bulkTagsInput) {
            this.tagInputHelper.setupTagInput(bulkTagsInput, 'editor-bulk-tags', {
                validateDelay: 200,
                onValidate: () => {
                    this.handleBulkTagsChanged(itemIds, bulkTagsInput);
                },
            });

            this.tagInputHelper.validateAndStyleTags(bulkTagsInput);

            bulkTagsInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                }
            });

            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(bulkTagsInput, {
                    multipleValues: true,
                    allowCreate: true,
                    containerClasses: 'surface border border-color shadow-lg z-50',
                    onSelect: () => {
                        setTimeout(() => {
                            this.tagInputHelper.validateAndStyleTags(bulkTagsInput);
                            this.handleBulkTagsChanged(itemIds, bulkTagsInput);
                        }, 100);
                    },
                });
            }
        }
    },

    refreshBulkAlbumBadges() {
        const commonIds = this.getCommonAlbumIds();
        const commonFolderExcluded = Array.from(this.getCommonFolderAlbumExcludedIds());
        const excluded = Array.from(new Set([...commonIds, ...commonFolderExcluded]));
        const badgesContainer = this.container.querySelector('#editor-bulk-albums-badges');
        if (badgesContainer) {
            badgesContainer.innerHTML = this.renderAlbumBadgesHtml(commonIds);
            badgesContainer.style.display = commonIds.length > 0 ? 'flex' : 'none';
            this.setupBulkAlbumBadgeEvents(Array.from(this.selectedIds));
        }
        if (this.bulkAlbumSelect) {
            const options = [{ value: '', text: window.i18n.t('upload.base_settings.select_album'), selected: true }];
            this.allAlbums.filter(a => !excluded.includes(a.id)).forEach(alb => {
                options.push({ value: alb.id, text: alb.name });
            });
            this.bulkAlbumSelect.setOptions(options);
            this.bulkAlbumSelect.setValue('');
        }
    },

    refreshBulkCommonTags() {
        if (this.bulkTagPreview) {
            this.bulkTagPreview.setTags(this.getCommonTags());
        }
    },

    handleBulkTagsChanged(itemIds, bulkTagsInput) {
        const text = this.tagInputHelper ? this.tagInputHelper.getPlainTextFromDiv(bulkTagsInput) : bulkTagsInput.textContent;
        const tagNames = text.trim().split(/\s+/).filter(Boolean);

        // Update the preview optimistically with whatever's in the input right now
        const previewTags = tagNames.map(n => {
            const existing = this.bulkCommonTagsMap ? this.bulkCommonTagsMap.get(n.toLowerCase()) : null;
            return existing ? existing : { name: n };
        });
        if (this.bulkTagPreview) {
            this.bulkTagPreview.setTags(previewTags);
        }

        // Debounce the actual bulk sync so rapid keystrokes don't flood the backend.
        clearTimeout(this.bulkTagSaveTimeout);
        this.bulkTagSaveTimeout = setTimeout(() => {
            this.bulkTagUpdateChain = (this.bulkTagUpdateChain || Promise.resolve())
                .then(() => this.commitBulkTagsChange(itemIds, bulkTagsInput))
                .catch(() => { });
        }, 500);
    },

    async commitBulkTagsChange(itemIds, bulkTagsInput) {
        const readNames = () => {
            const text = this.tagInputHelper ? this.tagInputHelper.getPlainTextFromDiv(bulkTagsInput) : bulkTagsInput.textContent;
            return text.trim().split(/\s+/).filter(Boolean);
        };

        const tagNames = readNames();
        const currentNames = new Set(tagNames.map(n => n.toLowerCase()));
        const previousNames = this.lastBulkTagNames || new Set();

        const toAdd = tagNames.filter(n => !previousNames.has(n.toLowerCase()));
        const toRemove = Array.from(previousNames).filter(n => !currentNames.has(n));

        if (itemIds.length === 0 || (toAdd.length === 0 && toRemove.length === 0)) {
            return;
        }

        const payload = {};
        if (toAdd.length > 0) payload.add_tags = toAdd;
        if (toRemove.length > 0) payload.remove_tag_names = toRemove;

        await this.session.bulkUpdate(itemIds, payload, { silent: true });

        // Refresh baseline tracking against the server-confirmed state.
        const updatedCommonTags = this.getCommonTags();
        this.lastBulkTagNames = new Set(updatedCommonTags.map(t => t.name.toLowerCase()));
        this.bulkCommonTagsMap = new Map(updatedCommonTags.map(t => [t.name.toLowerCase(), t]));

        // Reconcile the preview with server-confirmed category colors
        if (this.bulkTagPreview) {
            const liveNames = readNames();
            const reconciled = liveNames.map(n => {
                const found = this.bulkCommonTagsMap.get(n.toLowerCase());
                return found ? found : { name: n };
            });
            this.bulkTagPreview.setTags(reconciled);
        }

        if (this.options.onItemChanged) this.options.onItemChanged();
    },

    setupBulkAlbumBadgeEvents(itemIds) {
        const removeBtns = this.container.querySelectorAll('#editor-bulk-albums-badges .editor-remove-album-btn');
        removeBtns.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = parseInt(btn.dataset.id);
                if (id && itemIds.length > 0) {
                    await this.session.bulkUpdate(itemIds, { remove_album_ids: [id] });
                    this.refreshBulkAlbumBadges();
                    if (this.options.onItemChanged) this.options.onItemChanged();
                }
            });
        });
    },
});
