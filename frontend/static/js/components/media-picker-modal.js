/**
 * MediaPickerModal - A reusable media gallery picker modal.
 *
 * Extracted from the relation manager gallery logic so that both
 * the relation manager and the new background picker can share
 * the same search / gallery / pagination UI.
 *
 * Options:
 *   title           {string}    Modal title (default: i18n media_picker.title)
 *   mode            {'single'|'multi'}  Selection mode (default: 'multi')
 *   excludeIds      {number[]}  IDs to hide from results
 *   onSelect        {Function}  Called with array of selected media objects
 *   onCancel        {Function}  Called when modal is closed/cancelled
 *   confirmText     {string}    Confirm button label
 *   cancelText      {string}    Cancel button label
 *   filterFn        {Function}  Extra per-item filter (item) => boolean
 *   getInitialItems {Function}  async () => items[] for the default view
 *   statusHtml      {string}    Optional HTML to show in the status bar
 *   extraButtons    {Array}     Extra action buttons [{id, text, className, onClick}]
 */
class MediaPickerModal {
    constructor(options = {}) {
        this.options = {
            title: options.title || window.i18n.t('media_picker.title'),
            mode: options.mode || 'multi',
            excludeIds: new Set(options.excludeIds || []),
            onSelect: options.onSelect || (() => { }),
            onCancel: options.onCancel || (() => { }),
            confirmText: options.confirmText || window.i18n.t('media_picker.select'),
            cancelText: options.cancelText || window.i18n.t('common.cancel'),
            filterFn: options.filterFn || null,
            getInitialItems: options.getInitialItems || null,
            statusHtml: options.statusHtml || '',
            extraButtons: options.extraButtons || [],
            badgeFn: options.badgeFn || null, // (media) => {text, className} | null
        };

        // Internal state
        this.selectedItems = new Map(); // id -> media object
        this.currentPage = 1;
        this.totalPages = 1;
        this.isSearchMode = false;
        this.searchQuery = '';
        this.isLoading = false;
        this.isOpen = false;

        // ---- Drag & shift-select state (mirrors BaseGallery exactly) ----
        this.dragStartItem = null;
        this.selectionSnapshot = null;
        this.isDragging = false;
        this.suppressClick = false;
        this.dragTargetState = null;
        this.lastSelectedId = null;

        // DOM refs (set in _buildDOM)
        this.root = null;
        this._built = false;
    }

    _buildDOM() {
        if (this._built) return;
        this._built = true;

        const el = document.createElement('div');
        el.className = 'fixed inset-0 z-50 flex items-center justify-center';
        el.style.display = 'none';

        el.innerHTML = `
            <div class="mpicker-backdrop absolute inset-0 bg-black/70"></div>
            <div class="relative surface border shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col mx-4">
                <!-- Header -->
                <div class="flex items-center p-4 border-b">
                    <h2 class="text-lg font-bold">${this._esc(this.options.title)}</h2>
                </div>

                <!-- Status -->
                <div class="mpicker-status px-4 py-3 border-b surface-light"
                     style="${this.options.statusHtml ? '' : 'display:none'}">
                    <div class="mpicker-status-content text-sm">${this.options.statusHtml}</div>
                </div>

                <!-- Search + ID input -->
                <div class="p-4 border-b">
                    <form class="mpicker-search-form">
                        <div class="relative flex gap-2">
                            <input type="text" class="mpicker-search-input
                                w-full bg px-3 py-2 border text text-sm hover:border-primary transition-colors focus:outline-none focus:border-primary"
                                placeholder="${this._esc(window.i18n.t('nav.search_placeholder'))}">
                            <input type="text" inputmode="numeric" pattern="[0-9]*" class="mpicker-id-input hidden sm:block
                                bg px-3 py-2 border text text-sm hover:border-primary transition-colors focus:outline-none focus:border-primary"
                                style="width:120px"
                                placeholder="${this._esc(window.i18n.t('media_picker.media_id_placeholder'))}">
                            <button type="button" class="mpicker-id-go-btn hidden sm:inline-flex btn-primary px-3 py-2 text-sm">
                                ${this._esc(window.i18n.t('common.go'))}
                            </button>
                        </div>
                    </form>
                    <p class="mpicker-search-hint text-xs text-secondary mt-2"></p>
                </div>

                <!-- Gallery -->
                <div class="flex-1 overflow-y-auto p-4 mpicker-gallery-container">
                    <div class="mpicker-gallery grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-2"></div>
                    <div class="mpicker-loading text-center py-8" style="display:none">
                        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                        <p class="text-secondary mt-2">${this._esc(window.i18n.t('common.loading'))}</p>
                    </div>
                    <div class="mpicker-empty text-center py-8 text-secondary" style="display:none">
                        <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto mb-3 opacity-50" width="48" height="48"
                            viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round"
                            stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle>
                            <path d="m21 21-4.35-4.35"></path></svg>
                        <p>${this._esc(window.i18n.t('gallery.no_results_found'))}</p>
                    </div>
                    <div class="mpicker-load-more text-center py-4" style="display:none">
                        <button class="mpicker-load-more-btn btn px-6 py-2 text-sm">
                            ${this._esc(window.i18n.t('common.load_more'))}
                        </button>
                    </div>
                </div>

                <!-- Footer -->
                <div class="mpicker-footer p-4 border-t surface-light">
                    <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                        <div class="mpicker-selection-info">
                            <span class="mpicker-selected-count text-sm font-medium">
                                ${window.i18n.t('common.items_selected', { count: 0 })}
                            </span>
                            <button class="mpicker-clear-btn text-xs text-secondary hover:text-primary ml-2" style="display:none">
                                ${this._esc(window.i18n.t('common.clear_selection'))}
                            </button>
                        </div>
                        <div class="flex flex-wrap gap-2 mpicker-actions">
                            ${this.options.extraButtons.map(b => `
                                <button id="${this._esc(b.id)}" class="${this._esc(b.className || 'btn-primary')} px-4 py-2" style="display:none">
                                    ${this._esc(b.text)}
                                </button>
                            `).join('')}
                            <button class="mpicker-confirm-btn btn-primary px-4 py-2" style="display:none">
                                ${this._esc(this.options.confirmText)}
                            </button>
                            <button class="mpicker-cancel-btn btn-dark px-4 py-2">
                                ${this._esc(this.options.cancelText)}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(el);
        this.root = el;
        this._bindEvents();
    }

    _bindEvents() {
        const root = this.root;

        // Close
        root.querySelector('.mpicker-backdrop').addEventListener('click', () => this.close());
        root.querySelector('.mpicker-cancel-btn').addEventListener('click', () => this.close());

        // Search
        const searchForm = root.querySelector('.mpicker-search-form');
        const searchInput = root.querySelector('.mpicker-search-input');

        searchForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this._performSearch();
        });

        let searchTimeout;
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => this._performSearch(), 300);
        });

        // Tag autocomplete
        if (typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(searchInput, { multipleValues: true });
        }

        // ID input (always visible now)
        const goBtn = root.querySelector('.mpicker-id-go-btn');
        const idInput = root.querySelector('.mpicker-id-input');
        goBtn?.addEventListener('click', () => this._loadById(idInput));
        idInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this._loadById(idInput);
            }
        });

        // Load more
        root.querySelector('.mpicker-load-more-btn').addEventListener('click', () => {
            this.currentPage++;
            this._loadGallery(true);
        });

        // Clear selection
        root.querySelector('.mpicker-clear-btn').addEventListener('click', () => this.clearSelection());

        // Confirm
        root.querySelector('.mpicker-confirm-btn').addEventListener('click', () => {
            const items = [...this.selectedItems.values()];
            this.options.onSelect(items);
            this.close();
        });

        // Extra buttons
        this.options.extraButtons.forEach(b => {
            const btn = root.querySelector(`#${b.id}`);
            if (btn && b.onClick) {
                btn.addEventListener('click', () => b.onClick(this));
            }
        });

        // Escape
        this._escHandler = (e) => {
            if (e.key === 'Escape' && this.isOpen) this.close();
        };
        document.addEventListener('keydown', this._escHandler);

        // Global mouseup to end drag (mirrors BaseGallery)
        this._mouseUpHandler = () => this._handleDragEnd();
        document.addEventListener('mouseup', this._mouseUpHandler);
    }

    // ==================== Drag & Shift Selection (mirrors BaseGallery) ====================

    _getGalleryItems() {
        if (!this.root) return [];
        return Array.from(this.root.querySelectorAll('.mpicker-gallery .gallery-item'));
    }

    _handleMouseDown(item, id) {
        if (this.options.mode !== 'multi') return;
        this.dragStartItem = item;
        // Snapshot the full Map so we can restore it on each drag-enter
        this.selectionSnapshot = new Map(this.selectedItems);
        this.isDragging = false;
        this.suppressClick = false;
    }

    _startDrag() {
        this.isDragging = true;
        this.suppressClick = true;

        const id = parseInt(this.dragStartItem.dataset.id);
        const wasSelected = this.selectionSnapshot.has(id);
        this.dragTargetState = !wasSelected;
        this.lastSelectedId = id;

        this._applySelectionState(id, this.dragTargetState);
        this._updateFooter();
    }

    _handleDragEnter(item, id) {
        if (!this.dragStartItem) return;

        if (!this.isDragging) {
            this._startDrag();
        }

        const rangeIds = this._getRange(this.dragStartItem, item);

        // Reset to snapshot, then apply the drag range on top
        this.selectedItems.clear();
        this.selectionSnapshot.forEach((media, snapId) => this.selectedItems.set(snapId, media));

        rangeIds.forEach(rangeId => {
            if (this.dragTargetState) {
                const itemEl = this.root.querySelector(`.mpicker-gallery .gallery-item[data-id="${rangeId}"]`);
                if (itemEl && itemEl._mediaData) {
                    this.selectedItems.set(rangeId, itemEl._mediaData);
                }
            } else {
                this.selectedItems.delete(rangeId);
            }
        });

        this._updateVisibleSelectionState();
        this._updateFooter();

        this.lastSelectedId = id;
    }

    _handleDragEnd() {
        this.isDragging = false;
        this.dragStartItem = null;
        this.selectionSnapshot = null;
        this.dragTargetState = null;

        setTimeout(() => {
            this.suppressClick = false;
        }, 50);
    }

    _updateVisibleSelectionState() {
        this._getGalleryItems().forEach(item => {
            const id = parseInt(item.dataset.id);
            if (this.selectedItems.has(id)) {
                item.classList.add('selected', 'border-primary');
                const overlay = item.querySelector('.mpicker-overlay');
                if (overlay) overlay.classList.add('opacity-100');
            } else {
                item.classList.remove('selected', 'border-primary');
                const overlay = item.querySelector('.mpicker-overlay');
                if (overlay) overlay.classList.remove('opacity-100');
            }
        });
    }

    _applySelectionState(id, isSelected) {
        const item = this.root?.querySelector(`.mpicker-gallery .gallery-item[data-id="${id}"]`);
        const media = item ? item._mediaData : null;

        if (isSelected && media) {
            this.selectedItems.set(id, media);
            if (item) {
                item.classList.add('selected', 'border-primary');
                const overlay = item.querySelector('.mpicker-overlay');
                if (overlay) overlay.classList.add('opacity-100');
            }
        } else {
            this.selectedItems.delete(id);
            if (item) {
                item.classList.remove('selected', 'border-primary');
                const overlay = item.querySelector('.mpicker-overlay');
                if (overlay) overlay.classList.remove('opacity-100');
            }
        }
    }

    _getRange(itemA, itemB) {
        const allItems = this._getGalleryItems();
        const indexA = allItems.indexOf(itemA);
        const indexB = allItems.indexOf(itemB);

        if (indexA === -1 || indexB === -1) return [];

        const start = Math.min(indexA, indexB);
        const end = Math.max(indexA, indexB);

        return allItems.slice(start, end + 1).map(el => parseInt(el.dataset.id));
    }

    _getRangeFromLast(currentId) {
        if (!this.lastSelectedId) return [currentId];

        const itemA = this.root?.querySelector(`.mpicker-gallery .gallery-item[data-id="${this.lastSelectedId}"]`);
        const itemB = this.root?.querySelector(`.mpicker-gallery .gallery-item[data-id="${currentId}"]`);

        if (!itemA || !itemB) return [currentId];

        return this._getRange(itemA, itemB);
    }

    _toggleItemSelection(media, item, event = null) {
        if (this.suppressClick) return;

        const id = media.id;

        if (this.options.mode === 'single') {
            this._toggleSelection(media, item);
            return;
        }

        // Shift-click range selection (mirrors BaseGallery.toggleItemSelection)
        if (event && event.shiftKey && this.lastSelectedId) {
            const rangeIds = this._getRangeFromLast(id);
            const allSelected = rangeIds.every(rid => this.selectedItems.has(rid));
            const targetState = !allSelected;

            rangeIds.forEach(rid => {
                this._applySelectionState(rid, targetState);
            });

            this.lastSelectedId = id;
        } else {
            if (this.selectedItems.has(id)) {
                this._applySelectionState(id, false);
            } else {
                this._applySelectionState(id, true);
                this.lastSelectedId = id;
            }
        }

        this._updateFooter();
    }

    // ==================== public ====================

    open() {
        this._buildDOM();

        this.selectedItems.clear();
        this.currentPage = 1;
        this.isSearchMode = false;
        this.searchQuery = '';
        this.lastSelectedId = null;

        const searchInput = this.root.querySelector('.mpicker-search-input');
        if (searchInput) searchInput.value = '';

        const idInput = this.root.querySelector('.mpicker-id-input');
        if (idInput) idInput.value = '';

        this.root.style.display = 'flex';
        this.isOpen = true;
        document.body.style.overflow = 'hidden';

        this._updateFooter();
        this._loadGallery();
    }

    close() {
        if (!this.root) return;
        this.root.style.display = 'none';
        this.isOpen = false;
        document.body.style.overflow = '';
        this.options.onCancel();
    }

    destroy() {
        this.close();
        if (this._escHandler) {
            document.removeEventListener('keydown', this._escHandler);
        }
        if (this._mouseUpHandler) {
            document.removeEventListener('mouseup', this._mouseUpHandler);
        }
        if (this.root && this.root.parentNode) {
            this.root.parentNode.removeChild(this.root);
        }
        this.root = null;
        this._built = false;
    }

    clearSelection() {
        this.selectedItems.clear();
        this.lastSelectedId = null;

        if (this.root) {
            this.root.querySelectorAll('.mpicker-gallery .gallery-item').forEach(item => {
                item.classList.remove('selected', 'border-primary');
                const overlay = item.querySelector('.mpicker-overlay');
                if (overlay) overlay.classList.remove('opacity-100');
            });
        }

        this._updateFooter();
    }

    /** Update the status bar HTML (e.g. for the relation manager) */
    setStatusHtml(html) {
        if (!this.root) return;
        const statusDiv = this.root.querySelector('.mpicker-status');
        const statusContent = this.root.querySelector('.mpicker-status-content');
        if (html) {
            statusContent.innerHTML = html;
            statusDiv.style.display = '';
        } else {
            statusDiv.style.display = 'none';
        }
    }

    /** Get an extra-button DOM element by its id */
    getButton(id) {
        return this.root?.querySelector(`#${id}`);
    }

    /** Get the gallery container element */
    getGalleryEl() {
        return this.root?.querySelector('.mpicker-gallery');
    }

    // ==================== private ====================

    _esc(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async _performSearch() {
        const searchInput = this.root.querySelector('.mpicker-search-input');
        const query = searchInput?.value.trim() || '';

        this.searchQuery = query;
        this.isSearchMode = query.length > 0;
        this.currentPage = 1;

        this._loadGallery();
    }

    async _loadById(idInput) {
        const id = parseInt(idInput?.value);
        if (!id || id < 1) return;

        try {
            const res = await fetch(`/api/media/${id}`);
            if (!res.ok) {
                app.showNotification(window.i18n.t('common.media_not_found'), 'error');
                return;
            }
            const media = await res.json();

            if (this.options.mode === 'single') {
                this.selectedItems.clear();
                this.root.querySelectorAll('.mpicker-gallery .gallery-item').forEach(item => {
                    item.classList.remove('selected', 'border-primary');
                    const overlay = item.querySelector('.mpicker-overlay');
                    if (overlay) overlay.classList.remove('opacity-100');
                });
            }

            this.selectedItems.set(media.id, media);
            this._updateFooter();

            // For single mode, immediately confirm
            if (this.options.mode === 'single') {
                this.options.onSelect([media]);
                this.close();
            }
        } catch (e) {
            app.showNotification(e.message, 'error');
        }
    }

    async _loadGallery(append = false) {
        if (this.isLoading) return;
        this.isLoading = true;

        const gallery = this.root.querySelector('.mpicker-gallery');
        const loading = this.root.querySelector('.mpicker-loading');
        const empty = this.root.querySelector('.mpicker-empty');
        const loadMore = this.root.querySelector('.mpicker-load-more');
        const hint = this.root.querySelector('.mpicker-search-hint');

        if (!append) gallery.innerHTML = '';
        loading.style.display = 'block';
        empty.style.display = 'none';
        loadMore.style.display = 'none';

        try {
            let items = [];
            let totalPages = 1;

            if (this.isSearchMode && this.searchQuery) {
                const params = new URLSearchParams({
                    q: this.searchQuery,
                    page: this.currentPage,
                    limit: 24
                });
                const res = await fetch(`/api/search?${params.toString()}`, {
                    credentials: 'include'
                });
                const data = await res.json();
                items = data.items || [];
                totalPages = data.pages || 1;
                if (hint) hint.textContent = window.i18n.t('media.relations.search_results', { query: this.searchQuery });
            } else if (this.options.getInitialItems) {
                items = await this.options.getInitialItems();
                if (hint) hint.textContent = window.i18n.t('media.relations.search_hint');
            } else {
                if (hint) hint.textContent = '';
            }

            // Apply filters
            items = items.filter(item => {
                if (this.options.excludeIds.has(item.id)) return false;
                if (this.options.filterFn && !this.options.filterFn(item)) return false;
                return true;
            });

            this.totalPages = totalPages;

            if (items.length === 0 && !append) {
                empty.style.display = 'block';
            } else {
                items.forEach(media => {
                    const itemEl = this._createGalleryItem(media);
                    gallery.appendChild(itemEl);
                });

                if (this.isSearchMode && this.currentPage < totalPages) {
                    loadMore.style.display = 'block';
                }
            }
        } catch (e) {
            console.error('MediaPickerModal: Error loading gallery:', e);
            empty.style.display = 'block';
            empty.querySelector('p').textContent = window.i18n.t('media.errors.loading_items');
        } finally {
            loading.style.display = 'none';
            this.isLoading = false;
        }
    }

    _createGalleryItem(media) {
        const item = document.createElement('div');
        item.className = 'gallery-item relative cursor-pointer border border-2 group';
        item.dataset.id = media.id;

        // Store media data on element for drag-select access
        item._mediaData = media;

        const isSelected = this.selectedItems.has(media.id);
        if (isSelected) {
            item.classList.add('selected', 'border-primary');
        }

        // Thumbnail
        const img = document.createElement('img');
        img.src = `/api/media/${media.id}/thumbnail${media.hash ? '?v=' + media.hash : ''}`;
        img.alt = media.filename || `Media ${media.id}`;
        img.loading = 'lazy';
        img.className = 'w-full aspect-square object-cover transition-all';
        img.draggable = false;
        img.onerror = () => {
            img.src = '/static/images/no-thumbnail.png';
        };

        // Selection overlay
        const overlay = document.createElement('div');
        overlay.className = 'mpicker-overlay absolute inset-0 bg-primary/30 opacity-0 transition-opacity pointer-events-none';
        if (isSelected) overlay.classList.add('opacity-100');

        // Select indicator
        const indicator = document.createElement('div');
        indicator.className = 'select-indicator';
        indicator.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
        `;

        // Badge (parent/child indicators for relation manager, etc.)
        if (this.options.badgeFn) {
            const badge = this.options.badgeFn(media);
            if (badge) {
                const badgeEl = document.createElement('div');
                badgeEl.className = `absolute top-1 right-1 px-1.5 py-0.5 text-xs font-medium ${badge.className}`;
                badgeEl.textContent = badge.text;
                item.appendChild(badgeEl);
            }
        }

        // Mousedown -- begin potential drag (multi-select only)
        if (this.options.mode === 'multi') {
            item.addEventListener('mousedown', (e) => {
                if (e.button === 0) {
                    e.preventDefault();
                    this._handleMouseDown(item, media.id);
                }
            });
        }

        // Mouseenter -- continue drag
        item.addEventListener('mouseenter', () => {
            if (this.dragStartItem) {
                this._handleDragEnter(item, media.id);
            }
        });

        // Click handler (respects suppressClick from drag)
        item.addEventListener('click', (e) => {
            this._toggleItemSelection(media, item, e);
        });

        item.appendChild(img);
        item.appendChild(overlay);
        item.appendChild(indicator);

        return item;
    }

    _toggleSelection(media, itemElement) {
        const overlay = itemElement.querySelector('.mpicker-overlay');

        if (this.options.mode === 'single') {
            // Deselect everything else first
            if (!this.selectedItems.has(media.id)) {
                this.selectedItems.clear();
                this.root.querySelectorAll('.mpicker-gallery .gallery-item').forEach(el => {
                    el.classList.remove('selected', 'border-primary');
                    const ov = el.querySelector('.mpicker-overlay');
                    if (ov) ov.classList.remove('opacity-100');
                });
            }
        }

        if (this.selectedItems.has(media.id)) {
            this.selectedItems.delete(media.id);
            itemElement.classList.remove('selected', 'border-primary');
            if (overlay) overlay.classList.remove('opacity-100');
        } else {
            this.selectedItems.set(media.id, media);
            itemElement.classList.add('selected', 'border-primary');
            if (overlay) overlay.classList.add('opacity-100');
        }

        this._updateFooter();
    }

    _updateFooter() {
        const count = this.selectedItems.size;
        const countEl = this.root.querySelector('.mpicker-selected-count');
        const clearBtn = this.root.querySelector('.mpicker-clear-btn');
        const confirmBtn = this.root.querySelector('.mpicker-confirm-btn');

        if (countEl) {
            countEl.textContent = window.i18n.t('common.items_selected', { count });
        }
        if (clearBtn) {
            clearBtn.style.display = count > 0 ? 'inline' : 'none';
        }
        if (confirmBtn) {
            confirmBtn.style.display = count > 0 ? 'inline-block' : 'none';
        }

        // Let consumers update extra buttons via the extraButtons[].onClick callback
        // They can use this.getButton(id) and this.selectedItems
    }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MediaPickerModal;
}
