
class UploadQueueGrid {
    constructor(containerElement, session, options = {}) {
        this.container = containerElement;
        this.session = session;
        this.options = options;
        this.selectedIds = new Set();
        this.activeItemId = null;
        this.lastSelectedId = null;
        this.editor = null;
        this._nearDuplicateCounts = new Map();
        this._nearDuplicateNotified = new Set();
        this.filterNearDuplicatesOnly = false;

        this.init();
    }

    init() {
        const itemsSelectedTemplate = window.i18n.t('common.items_selected', { count: '<span id="upload-selected-count">0</span>' });

        this.container.innerHTML = `
            <div class="upload-queue-gallery">
                <!-- Bulk Actions Toolbar -->
                <div class="surface p-3 mb-4 border text-xs">
                    <p class="mb-2 text-xs">${itemsSelectedTemplate}</p>
                    <div class="flex gap-2 flex-wrap">
                        <button type="button" id="upload-select-all-btn" class="btn-primary px-3 py-1 cursor-pointer text-xs">
                            ${window.i18n.t('gallery.select_all')}
                        </button>
                        <button type="button" id="upload-deselect-all-btn" class="btn px-3 py-1 cursor-pointer text-xs">
                            ${window.i18n.t('gallery.deselect_all')}
                        </button>
                        <button type="button" id="upload-filter-near-duplicates-btn" class="btn px-3 py-1 cursor-pointer text-xs hidden" aria-pressed="false"></button>
                    </div>
                </div>

                <!-- Thumbnail Gallery Grid -->
                <div id="upload-thumbnail-grid" class="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8 max-h-90 overflow-y-auto gap-2 mb-4"></div>

                <!-- Unified Media Editor Container -->
                <div id="upload-media-editor-container" class="mt-3"></div>
            </div>
        `;

        const editorContainer = this.container.querySelector('#upload-media-editor-container');
        this.editor = new UploadMediaEditor(editorContainer, this.session, {
            allAlbums: this.options.allAlbums || [],
            fullscreenViewer: this.options.fullscreenViewer,
            tagInputHelper: this.options.tagInputHelper,
            onItemChanged: (item) => {
                if (item) {
                    this.renderThumbnail(item);
                } else {
                    this.renderGrid();
                }
                if (this.options.onTagsChange) this.options.onTagsChange();
            },
            onSelectItem: (itemId) => this.focusItem(itemId),
            onItemsDeleted: (deletedIds) => {
                (deletedIds || []).forEach(id => this.selectedIds.delete(id));
                let remaining = this.getVisibleItems();
                if (this.filterNearDuplicatesOnly && remaining.length === 0) {
                    this.filterNearDuplicatesOnly = false;
                    remaining = this.getVisibleItems();
                }
                if (this.selectedIds.size === 0 && remaining.length > 0) {
                    this.selectedIds.add(remaining[0].item_id);
                    this.activeItemId = remaining[0].item_id;
                    this.lastSelectedId = remaining[0].item_id;
                } else if (this.selectedIds.size > 0) {
                    this.activeItemId = Array.from(this.selectedIds)[0];
                    this.lastSelectedId = this.activeItemId;
                } else {
                    this.activeItemId = null;
                    this.lastSelectedId = null;
                }
                this.renderGrid();
                this.syncEditor();
                if (this.options.onTagsChange) this.options.onTagsChange();
            }
        });

        this.setupToolbarEvents();
        this.setupSessionListeners();
    }

    setupSessionListeners() {
        this.session.on('itemAdded', (item) => {
            if (this.selectedIds.size === 0) {
                this.selectedIds.add(item.item_id);
                this.activeItemId = item.item_id;
                this.lastSelectedId = item.item_id;
            }
            this.renderGrid();
            this.syncEditor();
        });

        this.session.on('itemUpdated', (item) => {
            this.renderThumbnail(item);
            if (this.selectedIds.has(item.item_id)) {
                if (this.selectedIds.size === 1) {
                    if (document.activeElement.id !== 'editor-single-tags-input') {
                        this.syncEditor(true);
                    }
                } else if (this.selectedIds.size > 1) {
                    if (document.activeElement.id !== 'editor-bulk-tags-input') {
                        this.syncEditor(true);
                    }
                }
            }
        });

        this.session.on('itemRemoved', (itemId) => {
            this.selectedIds.delete(itemId);
            if (this.activeItemId === itemId) {
                let remaining = this.getVisibleItems();
                if (this.filterNearDuplicatesOnly && remaining.length === 0) {
                    this.filterNearDuplicatesOnly = false;
                    remaining = this.getVisibleItems();
                }
                if (this.selectedIds.size > 0) {
                    this.activeItemId = Array.from(this.selectedIds)[0];
                } else if (remaining.length > 0) {
                    this.selectedIds.add(remaining[0].item_id);
                    this.activeItemId = remaining[0].item_id;
                } else {
                    this.activeItemId = null;
                }
            }
            if (this.lastSelectedId === itemId) {
                this.lastSelectedId = this.activeItemId;
            }
            this.renderGrid();
            this.syncEditor();
        });

        this.session.on('sessionCleared', () => {
            this.selectedIds.clear();
            this.activeItemId = null;
            this.lastSelectedId = null;
            this._nearDuplicateCounts = new Map();
            this._nearDuplicateNotified = new Set();
            this.filterNearDuplicatesOnly = false;
            this.renderGrid();
            this.syncEditor();
        });

        this.session.on('nearDuplicatesChanged', () => this.handleNearDuplicatesChanged());
    }

    getVisibleItems() {
        const items = this.session.getAllItems();
        if (!this.filterNearDuplicatesOnly) return items;
        return items.filter(it => this.session.getNearDuplicateCount && this.session.getNearDuplicateCount(it.item_id) > 0);
    }

    updateNearDuplicateFilterButton() {
        const btn = this.container.querySelector('#upload-filter-near-duplicates-btn');
        if (!btn) return;
        const ndCount = this._nearDuplicateCounts.size;
        if (ndCount === 0) {
            this.filterNearDuplicatesOnly = false;
            btn.classList.add('hidden');
            btn.classList.remove('btn-primary');
            btn.classList.add('btn');
            btn.setAttribute('aria-pressed', 'false');
            return;
        }
        btn.classList.remove('hidden');
        btn.textContent = window.i18n.t('upload.near_duplicates.filter_only', { count: ndCount });
        btn.classList.toggle('btn-primary', this.filterNearDuplicatesOnly);
        btn.classList.toggle('btn', !this.filterNearDuplicatesOnly);
        btn.setAttribute('aria-pressed', this.filterNearDuplicatesOnly ? 'true' : 'false');
    }

    toggleNearDuplicateFilter() {
        if (this._nearDuplicateCounts.size === 0) return;
        this.filterNearDuplicatesOnly = !this.filterNearDuplicatesOnly;
        this.updateNearDuplicateFilterButton();
        this.pruneSelectionToVisible();
        this.renderGrid();
        this.syncEditor();
    }

    pruneSelectionToVisible() {
        const visible = this.getVisibleItems();
        const visibleIds = new Set(visible.map(it => it.item_id));
        Array.from(this.selectedIds).forEach(id => {
            if (!visibleIds.has(id)) this.selectedIds.delete(id);
        });
        if (this.selectedIds.size === 0 && visible.length > 0) {
            this.selectedIds.add(visible[0].item_id);
            this.activeItemId = visible[0].item_id;
            this.lastSelectedId = visible[0].item_id;
        } else if (this.activeItemId && !visibleIds.has(this.activeItemId)) {
            this.activeItemId = this.selectedIds.size > 0 ? Array.from(this.selectedIds)[0] : null;
            this.lastSelectedId = this.activeItemId;
        }
    }

    handleNearDuplicatesChanged() {
        const previous = this._nearDuplicateCounts;
        const current = new Map();
        this.session.nearDuplicates.forEach((_, itemId) => {
            current.set(itemId, this.session.getNearDuplicateCount(itemId));
        });
        this._nearDuplicateCounts = current;

        const changedIds = new Set();
        let membershipChanged = false;
        current.forEach((count, id) => {
            if (!previous.has(id)) membershipChanged = true;
            if (previous.get(id) !== count) changedIds.add(id);
        });
        previous.forEach((count, id) => {
            if (!current.has(id)) {
                membershipChanged = true;
                changedIds.add(id);
            }
        });

        const wasFiltering = this.filterNearDuplicatesOnly;
        if (current.size === 0 && this.filterNearDuplicatesOnly) {
            this.filterNearDuplicatesOnly = false;
        }
        this.updateNearDuplicateFilterButton();

        if (wasFiltering && (membershipChanged || !this.filterNearDuplicatesOnly)) {
            this.pruneSelectionToVisible();
            this.renderGrid();
            this.syncEditor();
        } else {
            // Only repaint cards whose badge changed
            changedIds.forEach(id => {
                const item = this.session.getItem(id);
                if (item) this.renderThumbnail(item);
            });

            // Refresh the open editor's panel in place
            if (this.editor && changedIds.size > 0 && typeof this.editor.refreshNearDuplicates === 'function') {
                this.editor.refreshNearDuplicates();
            }
        }

        const fresh = [...current.keys()].filter(id => !this._nearDuplicateNotified.has(id));
        if (fresh.length > 0) {
            fresh.forEach(id => this._nearDuplicateNotified.add(id));
            if (window.app && typeof window.app.showNotification === 'function') {
                window.app.showNotification(
                    window.i18n.t('upload.near_duplicates.notice', { count: fresh.length }),
                    'warning'
                );
            }
        }
    }

    /* Select a single queued item */
    focusItem(itemId) {
        if (!this.session.getItem(itemId)) return;
        if (this.filterNearDuplicatesOnly && !(this.session.getNearDuplicateCount && this.session.getNearDuplicateCount(itemId) > 0)) {
            this.filterNearDuplicatesOnly = false;
            this.updateNearDuplicateFilterButton();
            this.renderGrid();
        }
        this.selectedIds.clear();
        this.selectedIds.add(itemId);
        this.activeItemId = itemId;
        this.lastSelectedId = itemId;
        this.updateSelectionVisuals();
        this.syncEditor();
        const card = this.container.querySelector(`.upload-thumb-card[data-item-id="${itemId}"]`);
        if (card && typeof card.scrollIntoView === 'function') {
            card.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        }
    }

    renderGrid() {
        const grid = this.container.querySelector('#upload-thumbnail-grid');
        if (!grid) return;

        this.updateNearDuplicateFilterButton();

        const items = this.getVisibleItems();
        if (items.length === 0) {
            grid.innerHTML = '';
            this.updateToolbarCounts();
            return;
        }

        // Auto-select first item if selection is empty and items exist
        if (this.selectedIds.size === 0 && items.length > 0) {
            this.selectedIds.add(items[0].item_id);
            this.activeItemId = items[0].item_id;
            this.lastSelectedId = items[0].item_id;
        }

        grid.innerHTML = items.map(item => this.renderThumbnailHtml(item)).join('');
        this.setupGridEvents();
        this.updateToolbarCounts();
    }

    renderThumbnailHtml(item) {
        const sessionId = this.session.sessionId;
        const thumbUrl = sessionId ? `/api/uploads/sessions/${sessionId}/items/${item.item_id}/thumbnail` : '';
        const isSelected = this.selectedIds.has(item.item_id);
        const selectClasses = isSelected ? 'border-primary' : '';

        const leafAlbum = item.suggested_album_path ? item.suggested_album_path.split('/').pop() : null;
        const nearDuplicateCount = this.session.getNearDuplicateCount ? this.session.getNearDuplicateCount(item.item_id) : 0;
        const nearDuplicateBadge = nearDuplicateCount > 0 ? `
                    <div class="nd-grid-badge absolute top-1 right-1 z-10 flex items-center gap-0.5 px-1 py-0.5 surface border text-[10px]"
                        title="${escapeHtml(window.i18n.t('upload.near_duplicates.badge_title', { count: nearDuplicateCount }))}">
                        ${window.Icons.merge({ size: 10 })}<span>${nearDuplicateCount}</span>
                    </div>` : '';

        return `
            <div class="upload-thumb-card surface border relative group flex flex-col cursor-pointer transition-colors ${selectClasses}"
                data-item-id="${item.item_id}">
                <!-- Thumbnail Box (Square 1:1, NO zoom animation) -->
                <div class="relative w-full aspect-square bg overflow-hidden flex items-center justify-center">
                    ${thumbUrl ? `
                        <img src="${thumbUrl}" alt="Thumbnail" class="w-full h-full object-cover select-none"
                            onerror="this.style.display='none'; if (this.nextElementSibling) this.nextElementSibling.style.display='flex';">
                        <div class="hidden w-full h-full items-center justify-center text-[10px] text-secondary">
                            ${window.i18n.t('common.none')}
                        </div>
                    ` : `
                        <div class="w-full h-full flex items-center justify-center text-[10px] text-secondary">
                            ${window.i18n.t('common.none')}
                        </div>
                    `}

                    ${nearDuplicateBadge}

                    <!-- Selection Checkbox (Top-left) -->
                    <div class="absolute top-1 left-1 z-10" onclick="event.stopPropagation();">
                        <input type="checkbox" class="thumb-checkbox w-3.5 h-3.5 accent-primary cursor-pointer" data-id="${item.item_id}" ${isSelected ? 'checked' : ''}>
                    </div>
                </div>

                <!-- Filename Bar -->
                <div class="p-1 border-t text-[10px] truncate font-mono text-secondary flex items-center justify-between gap-1" title="${escapeHtml(item.filename)}${leafAlbum ? ` [${escapeHtml(item.suggested_album_path)}]` : ''}">
                    <span class="truncate flex-1 min-w-0">${escapeHtml(item.filename)}</span>
                    ${leafAlbum ? `
                        <span class="shrink-0 text-secondary flex items-center gap-0.5 max-w-[45%]" title="${escapeHtml(item.suggested_album_path)}">
                            ${window.Icons.folder({ size: 10 })}
                            <span class="truncate">${escapeHtml(leafAlbum)}</span>
                        </span>
                    ` : ''}
                </div>
            </div>
        `;
    }

    renderThumbnail(item) {
        const card = this.container.querySelector(`.upload-thumb-card[data-item-id="${item.item_id}"]`);
        if (card) {
            const temp = document.createElement('div');
            temp.innerHTML = this.renderThumbnailHtml(item);
            const newCard = temp.firstElementChild;
            card.parentNode.replaceChild(newCard, card);
            this.setupCardEvents(newCard);
        }
    }

    setupGridEvents() {
        const cards = this.container.querySelectorAll('.upload-thumb-card');
        cards.forEach(card => this.setupCardEvents(card));
    }

    getRange(idA, idB) {
        const cards = Array.from(this.container.querySelectorAll('.upload-thumb-card'));
        const ids = cards.map(c => c.dataset.itemId);
        const idxA = ids.indexOf(idA);
        const idxB = ids.indexOf(idB);

        if (idxA === -1 || idxB === -1) return [idB];

        const start = Math.min(idxA, idxB);
        const end = Math.max(idxA, idxB);
        return ids.slice(start, end + 1);
    }

    selectItems(itemIds, event = null) {
        const ids = (itemIds || []).filter(Boolean);
        if (ids.length === 0) return;

        const isCtrl = Boolean(event && (event.ctrlKey || event.metaKey));
        const allSelected = ids.every(id => this.selectedIds.has(id));

        if (isCtrl) {
            if (allSelected) {
                ids.forEach(id => this.selectedIds.delete(id));
                if (!this.selectedIds.has(this.activeItemId)) {
                    this.activeItemId = this.selectedIds.size > 0 ? Array.from(this.selectedIds)[0] : null;
                }
            } else {
                ids.forEach(id => this.selectedIds.add(id));
                this.activeItemId = ids[0];
                this.lastSelectedId = ids[ids.length - 1];
            }
        } else {
            if (allSelected) {
                this.selectedIds.clear();
                this.activeItemId = null;
                this.lastSelectedId = null;
            } else {
                this.selectedIds.clear();
                ids.forEach(id => this.selectedIds.add(id));
                this.activeItemId = ids[0];
                this.lastSelectedId = ids[ids.length - 1];
            }
        }

        this.updateSelectionVisuals();
        this.syncEditor();
    }

    setupCardEvents(card) {
        const itemId = card.dataset.itemId;
        const item = this.session.getItem(itemId);
        if (!item) return;

        card.addEventListener('click', (e) => {
            if (e.shiftKey && this.lastSelectedId) {
                const rangeIds = this.getRange(this.lastSelectedId, itemId);
                const allSelected = rangeIds.every(id => this.selectedIds.has(id));
                const targetState = !allSelected;

                rangeIds.forEach(id => {
                    if (targetState) {
                        this.selectedIds.add(id);
                    } else {
                        this.selectedIds.delete(id);
                    }
                });

                this.lastSelectedId = itemId;
                this.activeItemId = itemId;
                this.updateSelectionVisuals();
                this.syncEditor();
                return;
            }

            if (e.ctrlKey || e.metaKey) {
                if (this.selectedIds.has(itemId)) {
                    this.selectedIds.delete(itemId);
                    if (this.activeItemId === itemId) {
                        this.activeItemId = this.selectedIds.size > 0 ? Array.from(this.selectedIds)[0] : null;
                    }
                } else {
                    this.selectedIds.add(itemId);
                    this.activeItemId = itemId;
                }
                this.lastSelectedId = itemId;
                this.updateSelectionVisuals();
                this.syncEditor();
                return;
            }

            if (this.selectedIds.size === 1 && this.selectedIds.has(itemId)) {
                this.openFullscreen(item);
            } else {
                this.selectedIds.clear();
                this.selectedIds.add(itemId);
                this.activeItemId = itemId;
                this.lastSelectedId = itemId;
                this.updateSelectionVisuals();
                this.syncEditor();
            }
        });

        // Double click: always open fullscreen
        card.addEventListener('dblclick', () => {
            this.openFullscreen(item);
        });

        // Checkbox click: toggle selection
        const checkbox = card.querySelector('.thumb-checkbox');
        if (checkbox) {
            checkbox.addEventListener('click', (e) => {
                e.stopPropagation();
                if (e.shiftKey && this.lastSelectedId) {
                    e.preventDefault();
                    const rangeIds = this.getRange(this.lastSelectedId, itemId);
                    const allSelected = rangeIds.every(id => this.selectedIds.has(id));
                    const targetState = !allSelected;

                    rangeIds.forEach(id => {
                        if (targetState) {
                            this.selectedIds.add(id);
                        } else {
                            this.selectedIds.delete(id);
                        }
                    });

                    this.lastSelectedId = itemId;
                    this.activeItemId = itemId;
                    this.updateSelectionVisuals();
                    this.syncEditor();
                    return;
                }
            });

            checkbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.selectedIds.add(itemId);
                    this.activeItemId = itemId;
                    this.lastSelectedId = itemId;
                } else {
                    this.selectedIds.delete(itemId);
                    if (this.activeItemId === itemId) {
                        this.activeItemId = this.selectedIds.size > 0 ? Array.from(this.selectedIds)[0] : null;
                    }
                    this.lastSelectedId = itemId;
                }
                this.updateSelectionVisuals();
                this.syncEditor();
            });
        }
    }

    openFullscreen(item) {
        if (this.options.fullscreenViewer && this.session.sessionId) {
            const isVideo = item.file_type === 'video';
            const fileUrl = `/api/uploads/sessions/${this.session.sessionId}/items/${item.item_id}/file`;
            this.options.fullscreenViewer.open(fileUrl, isVideo);
        }
    }

    setupToolbarEvents() {
        const selectAllBtn = this.container.querySelector('#upload-select-all-btn');
        const deselectAllBtn = this.container.querySelector('#upload-deselect-all-btn');
        const filterNdBtn = this.container.querySelector('#upload-filter-near-duplicates-btn');

        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', () => {
                const items = this.getVisibleItems();
                items.forEach(it => this.selectedIds.add(it.item_id));
                if (items.length > 0) {
                    this.activeItemId = items[0].item_id;
                    this.lastSelectedId = items[items.length - 1].item_id;
                }
                this.updateSelectionVisuals();
                this.syncEditor();
            });
        }

        if (deselectAllBtn) {
            deselectAllBtn.addEventListener('click', () => {
                this.selectedIds.clear();
                this.activeItemId = null;
                this.lastSelectedId = null;
                this.updateSelectionVisuals();
                this.syncEditor();
            });
        }

        if (filterNdBtn) {
            filterNdBtn.addEventListener('click', () => this.toggleNearDuplicateFilter());
        }
    }

    updateSelectionVisuals() {
        const cards = this.container.querySelectorAll('.upload-thumb-card');
        cards.forEach(card => {
            const id = card.dataset.itemId;
            const isSelected = this.selectedIds.has(id);
            const isActive = this.selectedIds.size === 1 && this.activeItemId === id;

            const checkbox = card.querySelector('.thumb-checkbox');
            if (checkbox) {
                checkbox.checked = isSelected;
            }

            card.classList.remove('ring-2', 'ring-primary', 'border-primary/80', 'ring-1', 'ring-primary/80');
            card.classList.add('border');
            card.classList.toggle('border-primary', isSelected);
        });

        this.updateToolbarCounts();

        if (this.options.onSelectionChange) {
            this.options.onSelectionChange(this.selectedIds);
        }
    }

    updateToolbarCounts() {
        const countEl = this.container.querySelector('#upload-selected-count');
        if (countEl) countEl.textContent = this.selectedIds.size.toString();
    }

    syncEditor(force = false) {
        if (this._syncTimeout) clearTimeout(this._syncTimeout);
        this._syncTimeout = setTimeout(() => {
            if (this.editor) {
                this.editor.setSelection(this.selectedIds, this.activeItemId, force);
            }
        }, 50);
    }

    setAllAlbums(albums) {
        this.options.allAlbums = albums || [];
        if (this.editor) {
            this.editor.setAllAlbums(albums);
        }
    }
}

window.UploadQueueGrid = UploadQueueGrid;
