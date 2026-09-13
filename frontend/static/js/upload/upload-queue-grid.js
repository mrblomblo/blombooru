class UploadQueueGrid {
    constructor(containerElement, session, options = {}) {
        this.container = containerElement;
        this.session = session;
        this.options = options;
        this.selectedIds = new Set();
        this.activeItemId = null;
        this.editor = null;

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
                    </div>
                </div>

                <!-- Thumbnail Gallery Grid -->
                <div id="upload-thumbnail-grid" class="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8 max-h-90 overflow-y-auto gap-2 p-1 mb-4"></div>

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
            onItemsDeleted: (deletedIds) => {
                (deletedIds || []).forEach(id => this.selectedIds.delete(id));
                const remaining = this.session.getAllItems();
                if (this.selectedIds.size === 0 && remaining.length > 0) {
                    this.selectedIds.add(remaining[0].item_id);
                    this.activeItemId = remaining[0].item_id;
                } else if (this.selectedIds.size > 0) {
                    this.activeItemId = Array.from(this.selectedIds)[0];
                } else {
                    this.activeItemId = null;
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
                const remaining = this.session.getAllItems();
                if (this.selectedIds.size > 0) {
                    this.activeItemId = Array.from(this.selectedIds)[0];
                } else if (remaining.length > 0) {
                    this.selectedIds.add(remaining[0].item_id);
                    this.activeItemId = remaining[0].item_id;
                } else {
                    this.activeItemId = null;
                }
            }
            this.renderGrid();
            this.syncEditor();
        });

        this.session.on('sessionCleared', () => {
            this.selectedIds.clear();
            this.activeItemId = null;
            this.renderGrid();
            this.syncEditor();
        });
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    renderGrid() {
        const grid = this.container.querySelector('#upload-thumbnail-grid');
        if (!grid) return;

        const items = this.session.getAllItems();
        if (items.length === 0) {
            grid.innerHTML = '';
            this.updateToolbarCounts();
            return;
        }

        // Auto-select first item if selection is empty and items exist
        if (this.selectedIds.size === 0 && items.length > 0) {
            this.selectedIds.add(items[0].item_id);
            this.activeItemId = items[0].item_id;
        }

        grid.innerHTML = items.map(item => this.renderThumbnailHtml(item)).join('');
        this.setupGridEvents();
        this.updateToolbarCounts();
    }

    renderThumbnailHtml(item) {
        const sessionId = this.session.sessionId;
        const thumbUrl = sessionId ? `/api/uploads/sessions/${sessionId}/items/${item.item_id}/thumbnail` : '';
        const isSelected = this.selectedIds.has(item.item_id);
        const isActive = this.selectedIds.size === 1 && this.activeItemId === item.item_id;

        let selectClasses = 'border';
        if (isActive) {
            selectClasses = 'border-primary ring-2 ring-primary';
        } else if (isSelected) {
            selectClasses = 'border-primary/80 ring-1 ring-primary/80';
        }

        const leafAlbum = item.suggested_album_path ? item.suggested_album_path.split('/').pop() : null;

        return `
            <div class="upload-thumb-card surface relative group flex flex-col cursor-pointer ${selectClasses}"
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

                    <!-- Selection Checkbox (Top-left) -->
                    <div class="absolute top-1 left-1 z-10" onclick="event.stopPropagation();">
                        <input type="checkbox" class="thumb-checkbox w-3.5 h-3.5 accent-primary cursor-pointer" data-id="${item.item_id}" ${isSelected ? 'checked' : ''}>
                    </div>
                </div>

                <!-- Filename Bar -->
                <div class="p-1 border-t text-[10px] truncate font-mono text-secondary flex items-center justify-between gap-1" title="${this.escapeHtml(item.filename)}${leafAlbum ? ` [${this.escapeHtml(item.suggested_album_path)}]` : ''}">
                    <span class="truncate flex-1 min-w-0">${this.escapeHtml(item.filename)}</span>
                    ${leafAlbum ? `
                        <span class="shrink-0 text-secondary flex items-center gap-0.5 max-w-[45%]" title="${this.escapeHtml(item.suggested_album_path)}">
                            ${window.Icons.folder({ size: 10 })}
                            <span class="truncate">${this.escapeHtml(leafAlbum)}</span>
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

    setupCardEvents(card) {
        const itemId = card.dataset.itemId;
        const item = this.session.getItem(itemId);
        if (!item) return;

        // Click card: if already the active item, open fullscreen. Otherwise make it the selected item.
        card.addEventListener('click', () => {
            if (this.selectedIds.size === 1 && this.selectedIds.has(itemId)) {
                this.openFullscreen(item);
            } else {
                this.selectedIds.clear();
                this.selectedIds.add(itemId);
                this.activeItemId = itemId;
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
            checkbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.selectedIds.add(itemId);
                    this.activeItemId = itemId;
                } else {
                    this.selectedIds.delete(itemId);
                    if (this.activeItemId === itemId) {
                        this.activeItemId = this.selectedIds.size > 0 ? Array.from(this.selectedIds)[0] : null;
                    }
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

        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', () => {
                const items = this.session.getAllItems();
                items.forEach(it => this.selectedIds.add(it.item_id));
                if (items.length > 0) {
                    this.activeItemId = items[0].item_id;
                }
                this.updateSelectionVisuals();
                this.syncEditor();
            });
        }

        if (deselectAllBtn) {
            deselectAllBtn.addEventListener('click', () => {
                this.selectedIds.clear();
                this.activeItemId = null;
                this.updateSelectionVisuals();
                this.syncEditor();
            });
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

            card.classList.remove('border-primary', 'ring-2', 'ring-primary', 'border-primary/80', 'ring-1', 'ring-primary/80', 'border');
            if (isSelected) {
                card.classList.add('border-primary', 'ring-2', 'ring-primary');
            } else {
                card.classList.add('border');
            }
        });

        this.updateToolbarCounts();
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
