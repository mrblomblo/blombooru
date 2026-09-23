class UploadMediaEditor {
    constructor(containerElement, session, options = {}) {
        this.container = containerElement;
        this.session = session;
        this.options = options;
        this.selectedIds = new Set();
        this.activeItemId = null;
        this.tagInputHelper = options.tagInputHelper || new TagInputHelper();
        this.fullscreenViewer = options.fullscreenViewer || null;
        this.allAlbums = options.allAlbums || [];
        this.saveTimeout = null;
        this.tagSaveTimeout = null;
        this.bulkTagSaveTimeout = null;
        this.bulkTagUpdateChain = null;
        this.lastBulkTagNames = null;
        this.bulkCommonTagsMap = null;

        this.singleRatingSelect = null;
        this.singleAlbumSelect = null;
        this.singleTagPreview = null;
        this.bulkRatingSelect = null;
        this.bulkAlbumSelect = null;
        this.bulkTagPreview = null;

        this.init();
    }

    init() {
        this.render();
    }

    setSelection(selectedIds, activeItemId = null, force = false) {
        const newSelectedIds = new Set(selectedIds || []);
        const newActiveItemId = activeItemId || (newSelectedIds.size === 1 ? Array.from(newSelectedIds)[0] : null);

        const isSame = this.selectedIds.size === newSelectedIds.size &&
            Array.from(this.selectedIds).every(id => newSelectedIds.has(id)) &&
            this.activeItemId === newActiveItemId;

        this.selectedIds = newSelectedIds;
        this.activeItemId = newActiveItemId;

        if (isSame && this.container.firstElementChild && !force) {
            return;
        }

        this.render();
    }

    setAllAlbums(albums) {
        this.allAlbums = albums || [];
        if (!this.container.firstElementChild) {
            this.render();
        }
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatFileSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    render() {
        clearTimeout(this.bulkTagSaveTimeout);

        const count = this.selectedIds.size;
        if (count === 0) {
            this.renderEmptyState();
            return;
        }

        if (count === 1) {
            const itemId = this.activeItemId || Array.from(this.selectedIds)[0];
            const item = this.session.getItem(itemId);
            if (!item) {
                this.renderEmptyState();
                return;
            }
            this.renderSingleEditor(item);
            return;
        }

        this.renderBulkEditor();
    }

    renderEmptyState() {
        this.container.innerHTML = `
            <div class="surface border p-6 text-center text-secondary text-xs">
                <p>${window.i18n.t('upload.preview.select_hint')}</p>
            </div>
        `;
    }

    renderAlbumBadgesHtml(albumIds) {
        const idSet = new Set(albumIds || []);
        let html = '';
        idSet.forEach(id => {
            const alb = this.allAlbums.find(a => a.id == id);
            if (alb) {
                html += `
                    <div class="bg px-2 py-0.5 border text-xs flex items-center gap-1.5">
                        <span class="font-mono">${this.escapeHtml(alb.name)}</span>
                        <button type="button" class="editor-remove-album-btn text-danger hover:text-danger transition-colors cursor-pointer p-0.5 flex items-center justify-center" data-id="${id}">
                            ${window.Icons.trash({ size: 12, class: 'transition-colors' })}
                        </button>
                    </div>
                `;
            }
        });
        return html;
    }

    getFolderAlbumExcludedIds(item) {
        const ids = new Set();
        if (!item) return ids;

        if (item.suggested_album_segments && Array.isArray(item.suggested_album_segments)) {
            item.suggested_album_segments.forEach(seg => {
                if (seg.existing_id) {
                    ids.add(seg.existing_id);
                }
            });
        }

        if (item.suggested_album_path && this.allAlbums && this.allAlbums.length > 0) {
            const leafName = item.suggested_album_path.split('/').pop().toLowerCase();
            this.allAlbums.forEach(alb => {
                if (alb.name && alb.name.toLowerCase() === leafName) {
                    ids.add(alb.id);
                }
            });
        }

        return ids;
    }

    getCommonFolderAlbumExcludedIds() {
        const items = Array.from(this.selectedIds).map(id => this.session.getItem(id)).filter(Boolean);
        if (items.length === 0) return new Set();

        const sets = items.map(it => this.getFolderAlbumExcludedIds(it));
        const common = new Set(sets[0]);
        for (let i = 1; i < sets.length; i++) {
            for (const id of common) {
                if (!sets[i].has(id)) {
                    common.delete(id);
                }
            }
        }
        return common;
    }

    renderAlbumOptionsHtml(excludedIds = []) {
        const excludeSet = new Set(excludedIds || []);
        const available = this.allAlbums.filter(a => !excludeSet.has(a.id));
        let html = `<div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs selected" data-value="">${window.i18n.t('upload.base_settings.select_album')}</div>`;
        available.forEach(alb => {
            html += `<div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs" data-value="${alb.id}">${this.escapeHtml(alb.name)}</div>`;
        });
        return html;
    }

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
                            ${window.i18n.t('upload.preview.editing')} ${this.escapeHtml(item.filename)}
                        </span>
                        <span class="text-[11px] text-secondary shrink-0 whitespace-nowrap">
                            (${item.width && item.height ? `${item.width}x${item.height}, ` : ''}${this.formatFileSize(item.file_size)})
                        </span>
                        ${item.metadata_source ? `
                        <span class="badge bg-primary primary-text border border-primary text-[10px] px-1.5 py-0.5 shrink-0" title="${this.escapeHtml(item.metadata_source)}">
                            ${this.escapeHtml(item.metadata_source)}
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
                                ${window.Icons.selectArrow({ size: 10, class: 'custom-select-arrow flex-shrink-0 text-secondary' })}
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
                            value="${this.escapeHtml(item.source || '')}"
                            placeholder="https://example.com/source">
                    </div>
                </div>

                <!-- Description -->
                <div class="mb-3">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('common.description')}
                    </label>
                    <textarea id="editor-single-description" rows="2"
                        class="w-full bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                        placeholder="${this.escapeHtml(descPlaceholder)}">${this.escapeHtml(item.description || '')}</textarea>
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
                            <span class="font-mono text-xs truncate" title="${this.escapeHtml(item.suggested_album_path)}">${this.escapeHtml(item.suggested_album_path)}</span>
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
                            ${window.Icons.selectArrow({ size: 10, class: 'custom-select-arrow flex-shrink-0 text-secondary' })}
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
                            style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;">${this.escapeHtml(tagsPlainText)}</div>
                    </div>
                </div>

                <!-- Live Final Tags Display -->
                <div class="mb-1">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('upload.preview.final_tags')}
                    </label>
                    <div id="editor-single-final-tags-chips" class="p-2 bg border min-h-8.5 flex flex-wrap gap-1 text-xs items-center"></div>
                </div>
            </div>
        `;

        this.setupSingleEvents(item);
    }

    getCommonSuggestedAlbumPath() {
        const items = Array.from(this.selectedIds).map(id => this.session.getItem(id)).filter(Boolean);
        if (items.length === 0) return null;
        const firstPath = items[0].suggested_album_path;
        if (!firstPath) return null;
        for (let i = 1; i < items.length; i++) {
            if (items[i].suggested_album_path !== firstPath) return null;
        }
        return firstPath;
    }

    getCommonAlbumIds() {
        const items = Array.from(this.selectedIds).map(id => this.session.getItem(id)).filter(Boolean);
        if (items.length === 0) return [];
        let common = new Set(items[0].album_ids || []);
        for (let i = 1; i < items.length; i++) {
            const curAids = new Set(items[i].album_ids || []);
            common = new Set([...common].filter(id => curAids.has(id)));
        }
        return Array.from(common);
    }

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
    }

    getSharedValues() {
        const items = Array.from(this.selectedIds).map(id => this.session.getItem(id)).filter(Boolean);
        if (items.length === 0) return {};

        let sharedRating = items[0].rating;
        let sharedSource = items[0].source;
        let sharedDescription = items[0].description;

        for (let i = 1; i < items.length; i++) {
            const it = items[i];
            if (sharedRating !== undefined && it.rating !== sharedRating) sharedRating = undefined;
            if (sharedSource !== undefined && it.source !== sharedSource) sharedSource = undefined;
            if (sharedDescription !== undefined && it.description !== sharedDescription) sharedDescription = undefined;
        }

        return {
            rating: sharedRating !== undefined ? sharedRating : '',
            source: sharedSource !== undefined ? sharedSource : '',
            description: sharedDescription !== undefined ? sharedDescription : ''
        };
    }

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
                                ${window.Icons.selectArrow({ size: 10, class: 'custom-select-arrow flex-shrink-0 text-secondary' })}
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
                                value="${this.escapeHtml(shared.source || '')}"
                                placeholder="https://example.com/source">
                            <button type="button" id="editor-bulk-apply-source-btn" class="btn-primary text-xs px-2.5 py-1.5 cursor-pointer shrink-0">
                                ${window.i18n.t('common.apply')}
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Bulk Description -->
                <div class="mb-3">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('common.description')}
                    </label>
                    <div class="flex flex-col gap-1.5">
                        <textarea id="editor-bulk-description" rows="2"
                            class="w-full bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                            placeholder="${this.escapeHtml(descPlaceholder)}">${this.escapeHtml(shared.description || '')}</textarea>
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
                            <span class="font-mono text-xs truncate" title="${this.escapeHtml(commonSuggestedPath)}">${this.escapeHtml(commonSuggestedPath)}</span>
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
                                ${window.Icons.selectArrow({ size: 10, class: 'custom-select-arrow flex-shrink-0 text-secondary' })}
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
                            style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;">${this.escapeHtml(tagsPlainText)}</div>
                    </div>
                </div>

                <!-- Bulk Common Tags Display -->
                <div class="mb-1">
                    <label class="block text-xs font-bold mb-1">
                        ${window.i18n.t('upload.bulk.common_tags')}
                    </label>
                    <div id="editor-bulk-common-tags-chips" class="p-2 bg border min-h-8.5 flex flex-wrap gap-1 text-xs items-center"></div>
                </div>
            </div>
        `;

        this.setupBulkEvents();
    }

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
                if (typeof ModalHelper !== 'undefined') {
                    new ModalHelper({
                        type: 'danger',
                        title: window.i18n.t('modal.bulk_delete.title_single'),
                        message: window.i18n.t('upload.bulk.delete_confirm', { count: itemIds.length }),
                        confirmText: window.i18n.t('common.yes_remove'),
                        onConfirm: () => {
                            itemIds.forEach(id => this.session.deleteItem(id));
                            if (this.options.onItemsDeleted) {
                                this.options.onItemsDeleted(itemIds);
                            }
                        }
                    }).show();
                } else {
                    if (confirm(window.i18n.t('upload.bulk.delete_confirm', { count: itemIds.length }))) {
                        itemIds.forEach(id => this.session.deleteItem(id));
                        if (this.options.onItemsDeleted) {
                            this.options.onItemsDeleted(itemIds);
                        }
                    }
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
        const sourceApplyBtn = this.container.querySelector('#editor-bulk-source-apply-btn');
        const applyBulkSource = async () => {
            const source = sourceInput?.value.trim();
            if (source !== undefined && itemIds.length > 0) {
                await this.session.bulkUpdate(itemIds, { source });
                if (window.app && window.app.showNotification) {
                    window.app.showNotification(window.i18n.t('upload.bulk.source_applied'), 'success');
                }
                if (this.options.onItemChanged) this.options.onItemChanged();
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

        // Bulk Description
        const descInput = this.container.querySelector('#editor-bulk-description');
        const descApplyBtn = this.container.querySelector('#editor-bulk-description-apply-btn');
        const applyBulkDescription = async () => {
            const description = descInput?.value.trim();
            if (description !== undefined && itemIds.length > 0) {
                await this.session.bulkUpdate(itemIds, { description });
                if (window.app && window.app.showNotification) {
                    window.app.showNotification(window.i18n.t('upload.bulk.description_applied'), 'success');
                }
                if (this.options.onItemChanged) this.options.onItemChanged();
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
                    if (window.app && window.app.showNotification) {
                        window.app.showNotification(window.i18n.t('upload.bulk.album_added'), 'success');
                    }
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
    }

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
    }

    refreshBulkCommonTags() {
        if (this.bulkTagPreview) {
            this.bulkTagPreview.setTags(this.getCommonTags());
        }
    }

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
    }

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
    }

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
    }

    setupSingleEvents(item) {
        // Remove single media
        const removeBtn = this.container.querySelector('#editor-remove-single-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', () => {
                const id = item.item_id;
                if (typeof ModalHelper !== 'undefined') {
                    new ModalHelper({
                        type: 'danger',
                        title: window.i18n.t('upload.preview.remove_item_title'),
                        message: window.i18n.t('upload.preview.remove_confirm'),
                        confirmText: window.i18n.t('common.yes'),
                        onConfirm: () => {
                            this.session.deleteItem(id);
                            if (this.options.onItemsDeleted) {
                                this.options.onItemsDeleted([id]);
                            }
                        }
                    }).show();
                } else {
                    if (confirm(window.i18n.t('upload.preview.remove_confirm'))) {
                        this.session.deleteItem(id);
                        if (this.options.onItemsDeleted) {
                            this.options.onItemsDeleted([id]);
                        }
                    }
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

        // Description textarea
        const descInput = this.container.querySelector('#editor-single-description');
        if (descInput) {
            descInput.addEventListener('input', (e) => {
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
    }

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
    }

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
    }

    updateSingleFinalTagsPreview(item, tagsInput) {
        if (!this.singleTagPreview || !tagsInput) return;
        const text = this.tagInputHelper ? this.tagInputHelper.getPlainTextFromDiv(tagsInput) : tagsInput.textContent;
        const tagNames = text.trim().split(/\s+/).filter(Boolean);

        const previewTags = tagNames.map(n => {
            const existing = (item?.tags || []).find(t => t && t.name && t.name.toLowerCase() === n.toLowerCase());
            return existing ? existing : { name: n };
        });

        this.singleTagPreview.setTags(previewTags);
    }

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
    }

    debouncedSave(itemId, data) {
        clearTimeout(this.saveTimeout);
        this.saveTimeout = setTimeout(() => {
            this.session.updateItem(itemId, data, { silent: true });
        }, 500);
    }
}

window.UploadMediaEditor = UploadMediaEditor;
