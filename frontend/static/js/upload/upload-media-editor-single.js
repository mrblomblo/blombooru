// UploadMediaEditor single-item editor rendering and event handlers
Object.assign(UploadMediaEditor.prototype, {
    renderSingleEditor(item) {
        clearTimeout(this.bulkTagSaveTimeout);

        const allTags = item.tags || [];
        const tagsPlainText = allTags.map(t => t.name).join(' ');
        const hasAlbums = item.album_ids && item.album_ids.length > 0;
        const descPlaceholder = window.i18n.t('media.info.description_placeholder');
        const folderExcluded = Array.from(this.getFolderAlbumExcludedIds(item));
        const singleExcludedIds = Array.from(new Set([...(item.album_ids || []), ...folderExcluded]));

        this.container.innerHTML = `
            <div class="surface border p-4 text-xs">
                <!-- Header -->
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-3 mb-3">
                    <div class="flex items-center gap-1.5 min-w-0 flex-wrap sm:flex-nowrap">
                        <span class="text-xs font-bold truncate min-w-0">
                            ${window.i18n.t('upload.preview.editing')} ${escapeHtml(item.filename)}
                        </span>
                        <span class="text-[11px] text-secondary shrink-0 whitespace-nowrap">
                            (${item.width && item.height ? `${item.width}x${item.height}, ` : ''}${formatFileSize(item.file_size)})
                        </span>
                        ${item.metadata_source ? `
                        <span class="badge bg-primary primary-text border border-primary text-[10px] px-1.5 py-0.5 shrink-0" title="${escapeHtml(item.metadata_source)}">
                            ${escapeHtml(item.metadata_source)}
                        </span>` : ''}
                    </div>

                    <div class="flex items-center gap-2 shrink-0">
                        <!-- Remove Button -->
                        <button type="button" id="editor-remove-single-btn" class="btn-danger text-xs px-2.5 py-1 flex items-center gap-1.5 cursor-pointer" title="${window.i18n.t('common.remove')}">
                            ${window.Icons.trash({ size: 14 })}
                            <span>${window.i18n.t('common.remove')}</span>
                        </button>
                    </div>
                </div>

                <!-- Near-duplicate comparison -->
                <div id="editor-near-duplicates-slot">${this.renderNearDuplicatesHtml(item)}</div>

                <!-- Rating & Source Row -->
                <div class="flex flex-col sm:flex-row gap-3 mb-3">
                    <!-- Rating (Compact Width) -->
                    <div class="w-full sm:w-36 shrink-0">
                        <label class="block text-xs font-bold mb-1">
                            ${window.i18n.t('media.info.rating')}
                        </label>
                        <div id="editor-single-rating" class="custom-select w-full" data-value="${item.rating || 'safe'}">
                            <div class="custom-select-trigger w-full flex items-center justify-between gap-2 px-3 py-1.5 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors">
                                <span class="custom-select-value text capitalize">${item.rating || 'safe'}</span>
                                ${window.Icons.chevronDown({ size: 10, class: 'custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary', style: 'display: block;' })}
                            </div>
                            <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50">
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${item.rating === 'safe' ? 'selected' : ''}" data-value="safe">${window.i18n.t('common.safe')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${item.rating === 'questionable' ? 'selected' : ''}" data-value="questionable">${window.i18n.t('common.questionable')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${item.rating === 'explicit' ? 'selected' : ''}" data-value="explicit">${window.i18n.t('common.explicit')}</div>
                            </div>
                        </div>
                    </div>

                    <!-- Source URL (Fills Remaining Space) -->
                    <div class="flex-1 min-w-0">
                        <label class="block text-xs font-bold mb-1">
                            ${window.i18n.t('media.info.source')}
                        </label>
                        <input type="url" id="editor-single-source"
                            class="w-full bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                            value="${escapeHtml(item.source || '')}"
                            placeholder="https://example.com/source">
                    </div>
                </div>

                <!-- Date Row -->
                <div class="mb-3">
                    <div class="flex items-center justify-between mb-1">
                        <label class="block text-xs font-bold">
                            ${window.i18n.t('media.info.custom_date')}
                        </label>
                        <div id="editor-single-date-badge-container">
                            ${formatCustomDateOriginBadge(item.custom_date_origin)}
                        </div>
                    </div>
                    <input type="datetime-local" id="editor-single-custom-date"
                        class="w-full bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                        value="${toLocalInputDateTime(item.custom_date)}">
                </div>

                <!-- Description -->
                <div class="mb-3">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('common.description')}
                    </label>
                    <textarea id="editor-single-description" rows="2"
                        class="auto-expand-textarea w-full bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                        placeholder="${escapeHtml(descPlaceholder)}">${escapeHtml(item.description || '')}</textarea>
                </div>

                <!-- Folder Album (from folder structure) -->
                ${item.suggested_album_path ? `
                <div class="mb-3" id="editor-single-folder-album">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('upload.preview.folder_album')}
                    </label>
                    <div class="bg px-2 py-1 border text-xs flex items-center justify-between gap-2">
                        <div class="flex items-center gap-1.5 min-w-0">
                            <span class="text-secondary shrink-0">${window.Icons.folder({ size: 12 })}</span>
                            <span class="font-mono text-xs truncate" title="${escapeHtml(item.suggested_album_path)}">${escapeHtml(item.suggested_album_path)}</span>
                        </div>
                        <button type="button" id="editor-single-remove-folder-album-btn" class="text-danger hover:text-danger transition-colors cursor-pointer p-0.5 flex items-center justify-center shrink-0" title="${window.i18n.t('upload.folder.remove_album_path')}">
                            ${window.Icons.trash({ size: 12, class: 'transition-colors' })}
                        </button>
                    </div>
                </div>
                ` : ''}

                <!-- Albums -->
                <div class="mb-3">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('common.albums')}
                    </label>
                    <div id="editor-single-albums-badges" class="flex flex-wrap gap-1.5 mb-1.5" style="${hasAlbums ? '' : 'display: none;'}">
                        ${this.renderAlbumBadgesHtml(item.album_ids || [])}
                    </div>
                    <div id="editor-single-album-select" class="custom-select w-full" data-value="">
                        <div class="custom-select-trigger w-full flex items-center justify-between gap-2 px-3 py-1.5 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors">
                            <span class="custom-select-value text text-secondary">${window.i18n.t('upload.base_settings.select_album')}</span>
                            ${window.Icons.chevronDown({ size: 10, class: 'custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary', style: 'display: block;' })}
                        </div>
                        <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50">
                            ${this.renderAlbumOptionsHtml(singleExcludedIds)}
                        </div>
                    </div>
                </div>

                <!-- Tags Input -->
                <div class="mb-3">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('common.tags')}
                    </label>
                    <div class="relative">
                        <div id="editor-single-tags-input" contenteditable="true" data-placeholder="original highres cat_ears"
                            class="w-full bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors min-h-7.5"
                            style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;">${escapeHtml(tagsPlainText)}</div>
                    </div>
                </div>

                <!-- Live Final Tags Display -->
                <div class="mb-1">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('upload.preview.final_tags')}
                    </label>
                    <div id="editor-single-final-tags-chips" class="p-2 bg border min-h-8.5 flex flex-wrap gap-1 text-xs items-center max-w-full min-w-0"></div>
                </div>
            </div>
        `;

        this.setupSingleEvents(item);
    },

    setupSingleEvents(item) {
        this.bindNearDuplicates(item);

        // Remove single media
        const removeBtn = this.container.querySelector('#editor-remove-single-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', () => {
                const id = item.item_id;
                const doDelete = () => {
                    this.session.deleteItem(id);
                    if (this.options.onItemsDeleted) {
                        this.options.onItemsDeleted([id]);
                    }
                };
                if (typeof ModalHelper !== 'undefined') {
                    new ModalHelper({
                        type: 'danger',
                        title: window.i18n.t('upload.preview.remove_item_title'),
                        message: window.i18n.t('upload.preview.remove_confirm'),
                        confirmText: window.i18n.t('common.yes'),
                        cancelText: window.i18n.t('common.cancel'),
                        onConfirm: doDelete
                    }).show();
                } else {
                    doDelete();
                }
            });
        }

        // Rating select
        const ratingEl = this.container.querySelector('#editor-single-rating');
        if (ratingEl && typeof CustomSelect !== 'undefined') {
            this.singleRatingSelect = new CustomSelect(ratingEl);
            ratingEl.addEventListener('change', (e) => {
                item.rating = e.detail.value;
                this.session.updateItem(item.item_id, { rating: item.rating }, { silent: true });
                if (this.options.onItemChanged) this.options.onItemChanged(item);
            });
        }

        // Source input
        const sourceInput = this.container.querySelector('#editor-single-source');
        if (sourceInput) {
            sourceInput.addEventListener('input', (e) => {
                item.source = e.target.value.trim();
                this.debouncedSave(item.item_id, { source: item.source });
            });
        }

        // Custom Date input
        const singleDateInput = this.container.querySelector('#editor-single-custom-date');
        if (singleDateInput) {
            singleDateInput.addEventListener('change', (e) => {
                const isoStr = parseLocalInputDateTime(e.target.value);
                item.custom_date = isoStr;
                item.custom_date_origin = isoStr ? 'explicit' : null;
                const badgeContainer = this.container.querySelector('#editor-single-date-badge-container');
                if (badgeContainer) {
                    badgeContainer.innerHTML = formatCustomDateOriginBadge(item.custom_date_origin);
                }
                this.debouncedSave(item.item_id, { custom_date: isoStr });
                if (this.options.onItemChanged) this.options.onItemChanged(item);
            });
        }

        // Description textarea
        const descInput = this.container.querySelector('#editor-single-description');
        if (descInput) {
            this.autoResizeTextarea(descInput);
            descInput.addEventListener('input', (e) => {
                this.autoResizeTextarea(e.target);
                item.description = e.target.value.trim();
                this.debouncedSave(item.item_id, { description: item.description });
            });
        }

        // Folder album remove
        const removeFolderAlbumBtn = this.container.querySelector('#editor-single-remove-folder-album-btn');
        if (removeFolderAlbumBtn) {
            removeFolderAlbumBtn.addEventListener('click', async () => {
                item.suggested_album_path = null;
                item.suggested_album_segments = null;
                const updated = await this.session.updateItem(item.item_id, { suggested_album_path: null });
                if (updated) {
                    item.suggested_album_path = updated.suggested_album_path;
                    item.suggested_album_segments = updated.suggested_album_segments;
                }
                this.renderSingleEditor(item);
                if (this.options.onItemChanged) this.options.onItemChanged(item);
            });
        }

        // Album select
        const albumSelectEl = this.container.querySelector('#editor-single-album-select');
        if (albumSelectEl && typeof CustomSelect !== 'undefined') {
            this.singleAlbumSelect = new CustomSelect(albumSelectEl);
            albumSelectEl.addEventListener('change', (e) => {
                const aid = parseInt(e.detail.value);
                if (aid) {
                    const aids = new Set(item.album_ids || []);
                    aids.add(aid);
                    item.album_ids = Array.from(aids);
                    this.session.updateItem(item.item_id, { album_ids: item.album_ids });
                    this.refreshSingleAlbumBadges(item);
                    if (this.options.onItemChanged) this.options.onItemChanged(item);
                }
            });
        }

        this.setupSingleAlbumBadgeEvents(item);

        // Initialize TagPreview component
        const previewEl = this.container.querySelector('#editor-single-final-tags-chips');
        if (previewEl && typeof TagPreview !== 'undefined') {
            this.singleTagPreview = new TagPreview(previewEl, {
                allowCategoryChange: true,
                resolveAliases: false,
                onCategoryChange: async (tag, newCat) => {
                    await this.session.updatePendingTag(tag.name, { category: newCat });
                    // session.updatePendingTag automatically triggers session refresh and events
                    if (this.options.onItemChanged) this.options.onItemChanged(item);
                }
            });
            this.singleTagPreview.setTags(item.tags || []);
        }

        // Tags input
        const tagsInput = this.container.querySelector('#editor-single-tags-input');
        if (tagsInput) {
            this.tagInputHelper.setupTagInput(tagsInput, 'editor-single-tags', {
                validateDelay: 200,
                onValidate: () => {
                    this.handleSingleTagsChanged(item, tagsInput);
                },
            });

            // Validate tags immediately on show
            this.tagInputHelper.validateAndStyleTags(tagsInput);

            tagsInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                }
            });

            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(tagsInput, {
                    multipleValues: true,
                    allowCreate: true,
                    containerClasses: 'surface border border-color shadow-lg z-50',
                    onSelect: () => {
                        setTimeout(() => {
                            this.tagInputHelper.validateAndStyleTags(tagsInput);
                            this.handleSingleTagsChanged(item, tagsInput);
                        }, 100);
                    },
                });
            }
        }
    },

    setupSingleAlbumBadgeEvents(item) {
        const removeBtns = this.container.querySelectorAll('#editor-single-albums-badges .editor-remove-album-btn');
        removeBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = parseInt(btn.dataset.id);
                if (id) {
                    const aids = new Set(item.album_ids || []);
                    aids.delete(id);
                    item.album_ids = Array.from(aids);
                    this.session.updateItem(item.item_id, { album_ids: item.album_ids });
                    this.refreshSingleAlbumBadges(item);
                    if (this.options.onItemChanged) this.options.onItemChanged(item);
                }
            });
        });
    },

    refreshSingleAlbumBadges(item) {
        const badgesContainer = this.container.querySelector('#editor-single-albums-badges');
        if (badgesContainer) {
            badgesContainer.innerHTML = this.renderAlbumBadgesHtml(item.album_ids || []);
            badgesContainer.style.display = (item.album_ids && item.album_ids.length > 0) ? 'flex' : 'none';
            this.setupSingleAlbumBadgeEvents(item);
        }
        if (this.singleAlbumSelect) {
            const folderExcluded = Array.from(this.getFolderAlbumExcludedIds(item));
            const excluded = Array.from(new Set([...(item.album_ids || []), ...folderExcluded]));
            const options = [{ value: '', text: window.i18n.t('upload.base_settings.select_album'), selected: true }];
            this.allAlbums.filter(a => !excluded.includes(a.id)).forEach(alb => {
                options.push({ value: alb.id, text: alb.name });
            });
            this.singleAlbumSelect.setOptions(options);
            this.singleAlbumSelect.setValue('');
        }
    },

    updateSingleFinalTagsPreview(item, tagsInput) {
        if (!this.singleTagPreview || !tagsInput) return;
        const text = this.tagInputHelper ? this.tagInputHelper.getPlainTextFromDiv(tagsInput) : tagsInput.textContent;
        const tagNames = text.trim().split(/\s+/).filter(Boolean);

        const previewTags = tagNames.map(n => {
            const existing = (item?.tags || []).find(t => t && t.name && t.name.toLowerCase() === n.toLowerCase());
            return existing ? existing : { name: n };
        });

        this.singleTagPreview.setTags(previewTags);
    },

    handleSingleTagsChanged(item, tagsInput) {
        const text = this.tagInputHelper ? this.tagInputHelper.getPlainTextFromDiv(tagsInput) : tagsInput.textContent;
        const tagNames = text.trim().split(/\s+/).filter(Boolean);

        const itemTags = tagNames.map(n => {
            const existing = (item.tags || []).find(t => t.name.toLowerCase() === n.toLowerCase());
            return existing ? existing : { name: n };
        });

        // Update preview optimistically with local data immediately
        if (this.singleTagPreview) {
            this.singleTagPreview.setTags(itemTags);
        }

        // Debounce the actual PATCH so rapid keystrokes don't flood the backend
        clearTimeout(this.tagSaveTimeout);
        this.tagSaveTimeout = setTimeout(async () => {
            const updated = await this.session.updateItem(item.item_id, { tags: itemTags }, { silent: true });
            if (updated && updated.tags) {
                item.tags = updated.tags;
                if (this.singleTagPreview) {
                    this.singleTagPreview.setTags(item.tags);
                }
            }
            if (this.options.onItemChanged) this.options.onItemChanged(item);
        }, 500);
    },
});
