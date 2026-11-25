// BaseGallery drag selection, range selection, and bulk actions/modals
Object.assign(BaseGallery.prototype, {
    setupDragSelectionGlobalListeners() {
        // Global mouseup to end drag even if not over an item
        document.addEventListener('mouseup', () => {
            this.dragStartItem = null;
            if (this.isDragging) {
                this.handleDragEnd();
            }
        });

        // Global mousemove for autoscrolling during drag selection
        document.addEventListener('mousemove', (e) => {
            if (!this.isDragging || !this.dragStartItem) return;

            window.autoScroll?.check(e.clientX, e.clientY, {
                onScroll: (x, y) => {
                    const el = document.elementFromPoint(x, y);
                    const item = el ? el.closest(this.options.itemSelector) : null;
                    if (item && item.dataset && item.dataset.id) {
                        const id = parseInt(item.dataset.id);
                        if (id && id !== this.lastSelectedId) {
                            this.handleDragEnter(item, id);
                        }
                    }
                }
            });
        });

        // Prevent text selection while dragging
        document.addEventListener('selectstart', (e) => {
            if (this.isDragging) {
                e.preventDefault();
            }
        });
    },

    // ==================== Bulk Actions ====================

    setupBulkActions() {
        const selectAllBtn = document.getElementById('select-all-btn');
        const deselectAllBtn = document.getElementById('deselect-all-btn');
        const bulkDeleteBtn = document.getElementById('bulk-delete-btn');
        const bulkAlbumBtn = document.getElementById('bulk-album-btn');
        const bulkRemoveBtn = document.getElementById('bulk-remove-btn');
        const bulkManageTagsBtn = document.getElementById('bulk-manage-tags-btn');
        const bulkRatingBtn = document.getElementById('bulk-rating-btn');
        const bulkCustomDateBtn = document.getElementById('bulk-custom-date-btn');
        const bulkSourceBtn = document.getElementById('bulk-source-btn');

        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', () => this.handleSelectAll());
        }
        if (deselectAllBtn) {
            deselectAllBtn.addEventListener('click', () => this.handleDeselectAll());
        }
        if (bulkDeleteBtn) {
            bulkDeleteBtn.addEventListener('click', () => this.bulkDelete());
        }
        if (bulkAlbumBtn) {
            bulkAlbumBtn.addEventListener('click', () => this.bulkAddToAlbums());
        }
        if (bulkRemoveBtn) {
            bulkRemoveBtn.addEventListener('click', () => this.bulkRemove());
        }
        if (bulkManageTagsBtn) {
            bulkManageTagsBtn.addEventListener('click', () => this.openBulkManageTagsModal());
        }
        if (bulkRatingBtn) {
            bulkRatingBtn.addEventListener('click', () => this.openBulkModal('bulkRatingModal', BulkRatingModal));
        }
        if (bulkCustomDateBtn) {
            bulkCustomDateBtn.addEventListener('click', () => this.openBulkModal('bulkCustomDateModal', BulkCustomDateModal));
        }
        if (bulkSourceBtn) {
            bulkSourceBtn.addEventListener('click', () => this.openBulkModal('bulkSourceModal', BulkSourceModal));
        }
    },

    initBulkManageTagsModal() {
        if (typeof BulkManageTagsModal !== 'undefined' && !this.bulkManageTagsModal) {
            this.bulkManageTagsModal = new BulkManageTagsModal({
                onAction: (action) => {
                    if (action === 'manual') this.openBulkManualTagEditorModal();
                    else if (action === 'ai_tags') this.openBulkAITagsModal();
                    else if (action === 'wd_tagger') this.openBulkWDTaggerModal();
                }
            });
        }
    },

    initBulkManualTagEditorModal() {
        if (typeof BulkManualTagEditorModal !== 'undefined' && !this.bulkManualTagEditorModal) {
            this.bulkManualTagEditorModal = new BulkManualTagEditorModal({
                onSave: () => {
                    this.clearSelection();
                    this.loadContent();
                },
                onClose: () => {
                    // Re-open manager if it was the source
                    if (this.bulkManageTagsModal && this.bulkManageTagsModal.isOpen) {
                        this.bulkManageTagsModal.show();
                    }
                }
            });
        }
    },

    initBulkAITagsModal() {
        if (typeof BulkAITagsModal !== 'undefined' && !this.bulkAITagsModal) {
            this.bulkAITagsModal = new BulkAITagsModal({
                onSave: () => {
                    this.clearSelection();
                    this.loadContent();
                },
                onClose: () => {
                    if (this.bulkManageTagsModal && this.bulkManageTagsModal.isOpen) {
                        this.bulkManageTagsModal.show();
                    }
                }
            });
        }
    },

    initBulkWDTaggerModal() {
        if (typeof BulkWDTaggerModal !== 'undefined' && !this.bulkWDTaggerModal) {
            this.bulkWDTaggerModal = new BulkWDTaggerModal({
                onSave: () => {
                    this.clearSelection();
                    this.loadContent();
                },
                onClose: () => {
                    if (this.bulkManageTagsModal && this.bulkManageTagsModal.isOpen) {
                        this.bulkManageTagsModal.show();
                    }
                }
            });
        }
    },

    openBulkManageTagsModal() {
        if (!this.bulkManageTagsModal) {
            this.initBulkManageTagsModal();
        }
        if (this.bulkManageTagsModal) {
            this.bulkManageTagsModal.isOpen = true; // Track state
            this.bulkManageTagsModal.show();
        }
    },

    openBulkManualTagEditorModal() {
        if (!this.bulkManualTagEditorModal) {
            this.initBulkManualTagEditorModal();
        }
        if (this.bulkManualTagEditorModal) {
            this.bulkManualTagEditorModal.show(this.selectedItems);
        }
    },

    openBulkAITagsModal() {
        if (!this.bulkAITagsModal) {
            this.initBulkAITagsModal();
        }
        if (this.bulkAITagsModal) {
            this.bulkAITagsModal.show(this.selectedItems);
        }
    },

    openBulkWDTaggerModal() {
        if (!this.bulkWDTaggerModal) {
            this.initBulkWDTaggerModal();
        }
        if (this.bulkWDTaggerModal) {
            this.bulkWDTaggerModal.show(this.selectedItems);
        }
    },

    // New handler for smart Select All
    async handleSelectAll() {
        if (!app.isAdminMode) return;

        const visibleItems = document.querySelectorAll(this.options.itemSelector);
        const visibleIds = Array.from(visibleItems).map(item => parseInt(item.dataset.id));

        // Check if all visible items are already selected
        const isCurrentPageFull = visibleIds.length > 0 && visibleIds.every(id => this.selectedItems.has(id));

        if (!isCurrentPageFull) {
            // Logic 1: Fill the current page
            visibleItems.forEach(item => {
                const id = parseInt(item.dataset.id);
                const checkbox = item.querySelector('.select-checkbox, .checkbox, .album-item-checkbox');

                if (checkbox && !checkbox.checked) {
                    checkbox.checked = true;
                    this.selectedItems.add(id);
                    item.classList.add('selected');
                }
            });
            this.updateBulkActionsUI();
        } else {
            // Logic 2: Select all items across ALL pages
            await this.performGlobalSelection();
        }
    },

    // New handler for smart Deselect All
    handleDeselectAll() {
        if (!app.isAdminMode) return;

        const visibleItems = document.querySelectorAll(this.options.itemSelector);
        const visibleIds = Array.from(visibleItems).map(item => parseInt(item.dataset.id));

        // Check if all visible items are selected
        const isCurrentPageFull = visibleIds.length > 0 && visibleIds.every(id => this.selectedItems.has(id));

        if (isCurrentPageFull) {
            // Logic 1: Only deselect items on the current page
            visibleItems.forEach(item => {
                const id = parseInt(item.dataset.id);
                this.selectedItems.delete(id);
                item.classList.remove('selected');
                const checkbox = item.querySelector('.select-checkbox, .checkbox, .album-item-checkbox');
                if (checkbox) checkbox.checked = false;
            });
        } else {
            // Logic 2: Clear EVERYTHING (global deselect)
            this.clearSelection();
        }
        this.updateBulkActionsUI();
    },

    // Helper to fetch all IDs matching current filter
    async performGlobalSelection() {
        const btn = document.getElementById('select-all-btn');
        if (!btn) return;

        const originalText = btn.textContent;
        btn.textContent = window.i18n.t('gallery.selecting_all');
        btn.disabled = true;

        try {
            // Determine endpoint based on current page context
            let endpoint = '/api/search'; // Default
            const path = window.location.pathname;

            const albumId = this.albumId || (path.startsWith('/album/') ? path.split('/')[2] : null);
            if (albumId) {
                endpoint = `/api/albums/${albumId}/contents`;
            } else if (path === '/' || path === '/index.html') {
                endpoint = '/api/search';
            }

            // Build params based on current URL (preserves filters, sorts, etc.)
            const params = new URLSearchParams(window.location.search);
            params.set('limit', '500000'); // Fetch "all" (reasonable limit)
            params.delete('page');

            if (this.options.enableRatingFilter !== false && this.currentRating) {
                params.set('rating', this.currentRating);
            } else {
                params.delete('rating');
            }

            params.delete('custom_filter');
            if (this.selectedCustomFilters && this.selectedCustomFilters.size > 0) {
                this.selectedCustomFilters.forEach(cf => params.append('custom_filter', cf));
            }

            this.appendSortParams(params);

            const res = await fetch(`${endpoint}?${params.toString()}`, {
                credentials: 'include'
            });
            if (!res.ok) throw new Error('Failed to fetch all items');

            const data = await res.json();
            const items = data.items || data.media || []; // Handle different response structures

            if (items.length === 0) {
                app.showNotification(window.i18n.t('notifications.gallery.no_items_to_select'), 'info');
                return;
            }

            let addedCount = 0;
            items.forEach(item => {
                if (!this.selectedItems.has(item.id)) {
                    this.selectedItems.add(item.id);
                    addedCount++;
                }
            });

            // Visually update current page items to ensure they look selected
            document.querySelectorAll(this.options.itemSelector).forEach(item => {
                const id = parseInt(item.dataset.id);
                if (this.selectedItems.has(id)) {
                    item.classList.add('selected');
                    const checkbox = item.querySelector('.select-checkbox, .checkbox, .album-item-checkbox');
                    if (checkbox) checkbox.checked = true;
                }
            });

            this.updateBulkActionsUI();
            app.showNotification(window.i18n.t('notifications.gallery.items_selected', { count: this.selectedItems.size }), 'success');

        } catch (e) {
            console.error('Global selection failed:', e);
            app.showNotification(window.i18n.t('notifications.gallery.failed_to_select_all'), 'error');
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    },

    updateBulkActionsUI() {
        const bulkActions = document.getElementById('bulk-actions');
        if (bulkActions) {
            bulkActions.style.display = this.selectedItems.size > 0 ? 'block' : 'none';
        }

        const count = document.getElementById('selected-count');
        if (count) {
            count.textContent = this.selectedItems.size;
        }

        this.updateSelectionModeClass();
    },

    selectAll() {
        document.querySelectorAll(this.options.itemSelector).forEach(item => {
            const id = parseInt(item.dataset.id);
            const checkbox = item.querySelector('.select-checkbox');

            if (!this.selectedItems.has(id)) {
                this.selectedItems.add(id);
                item.classList.add('selected');
                if (checkbox) checkbox.checked = true;
            }
        });
        this.updateBulkActionsUI();
    },

    clearSelection() {
        this.selectedItems.clear();
        document.querySelectorAll(this.options.itemSelector).forEach(item => {
            item.classList.remove('selected');
            const checkbox = item.querySelector('.select-checkbox, .checkbox, .album-item-checkbox');
            if (checkbox) checkbox.checked = false;
        });
        this.updateBulkActionsUI();
    },

    async bulkDelete() {
        const itemCount = this.selectedItems.size;
        if (itemCount === 0) return;

        const modal = new ModalHelper({
            id: 'bulk-delete-modal',
            type: 'danger',
            title: itemCount > 1 ? window.i18n.t('modal.bulk_delete.title', { count: itemCount }) : window.i18n.t('modal.bulk_delete.title_single'),
            message: window.i18n.t('modal.bulk_delete.message', { count: itemCount }),
            confirmText: window.i18n.t('common.yes_delete'),
            cancelText: window.i18n.t('common.cancel'),
            onConfirm: async () => {
                for (const id of this.selectedItems) {
                    try {
                        await app.apiCall(`/api/media/${id}`, { method: 'DELETE' });
                        const element = document.querySelector(`[data-id="${id}"]`);
                        if (element) element.remove();
                    } catch (error) {
                        console.error(`Error deleting media ${id}:`, error);
                    }
                }
                this.clearSelection();
                this.loadContent();
            }
        });

        modal.show();
    },

    // ==================== Drag & Shift Selection ====================

    handleMouseDown(item, id) {
        if (!app.isAdminMode) return;
        if (!this.isSelectionMode) return;
        this.dragStartItem = item;
        this.selectionSnapshot = new Set(this.selectedItems);
        this.isDragging = false;
        this.suppressClick = false;
    },

    startDrag() {
        this.isDragging = true;
        this.suppressClick = true;
        document.body.classList.add('is-dragging');

        // Calculate target state based on start item
        const id = parseInt(this.dragStartItem.dataset.id);
        const wasSelected = this.selectionSnapshot.has(id);
        this.dragTargetState = !wasSelected;
        this.lastSelectedId = id;

        // Immediately apply to start item
        this.applySelectionState(id, this.dragTargetState);
        this.updateBulkActionsUI();
    },

    handleDragEnter(item, id) {
        if (!this.dragStartItem) return;

        if (!this.isDragging) {
            this.startDrag();
        }

        const rangeIds = this.getRange(this.dragStartItem, item);

        this.selectedItems.clear();
        this.selectionSnapshot.forEach(snapshotId => this.selectedItems.add(snapshotId));

        // Apply target state to everything in the current range
        rangeIds.forEach(rangeId => {
            if (this.dragTargetState) {
                this.selectedItems.add(rangeId);
            } else {
                this.selectedItems.delete(rangeId);
            }
        });

        this.updateVisibleSelectionState();
        this.updateBulkActionsUI();

        this.lastSelectedId = id;
    },

    handleDragEnd() {
        this.isDragging = false;
        this.dragStartItem = null;
        this.selectionSnapshot = null;
        this.dragTargetState = null;
        this.updateSelectionModeClass();
        document.body.classList.remove('is-dragging');
        window.autoScroll?.stop();

        setTimeout(() => {
            this.suppressClick = false;
        }, 50);
    },

    updateVisibleSelectionState() {
        document.querySelectorAll(this.options.itemSelector).forEach(item => {
            const id = parseInt(item.dataset.id);
            const checkbox = item.querySelector('.select-checkbox');

            if (this.selectedItems.has(id)) {
                item.classList.add('selected');
                if (checkbox) checkbox.checked = true;
            } else {
                item.classList.remove('selected');
                if (checkbox) checkbox.checked = false;
            }
        });
    },

    applySelectionState(id, isSelected) {
        const item = document.querySelector(`${this.options.itemSelector}[data-id="${id}"]`);

        if (isSelected) {
            this.selectedItems.add(id);
            if (item) item.classList.add('selected');
            if (item) {
                const cb = item.querySelector('.select-checkbox');
                if (cb) cb.checked = true;
            }
        } else {
            this.selectedItems.delete(id);
            if (item) item.classList.remove('selected');
            if (item) {
                const cb = item.querySelector('.select-checkbox');
                if (cb) cb.checked = false;
            }
        }
    },

    getRange(itemA, itemB) {
        const allItems = Array.from(document.querySelectorAll(this.options.itemSelector));
        const indexA = allItems.indexOf(itemA);
        const indexB = allItems.indexOf(itemB);

        if (indexA === -1 || indexB === -1) return [];

        const start = Math.min(indexA, indexB);
        const end = Math.max(indexA, indexB);

        return allItems.slice(start, end + 1).map(el => parseInt(el.dataset.id));
    },

    getRangeFromLast(currentId) {
        if (!this.lastSelectedId) return [currentId];

        const itemA = document.querySelector(`${this.options.itemSelector}[data-id="${this.lastSelectedId}"]`);
        const itemB = document.querySelector(`${this.options.itemSelector}[data-id="${currentId}"]`);

        if (!itemA || !itemB) return [currentId];

        return this.getRange(itemA, itemB);
    },

    async bulkAddToAlbums() {
        const itemCount = this.selectedItems.size;
        if (itemCount === 0) return;

        try {
            const result = await AlbumPicker.pick({
                title: window.i18n.t('gallery.add_items_to_albums_title', { count: itemCount }),
                multiSelect: true
            });

            if (!result) return;

            const mediaIds = Array.from(this.selectedItems);
            let successCount = 0;

            for (const albumId of result.ids) {
                await app.apiCall(`/api/albums/${albumId}/media`, {
                    method: 'POST',
                    body: JSON.stringify({ media_ids: mediaIds })
                });
                successCount++;
            }

            app.showNotification(window.i18n.t('notifications.gallery.added_to_albums', { itemCount, albumCount: successCount }), 'success');
            this.clearSelection();
        } catch (error) {
            console.error('Error adding to albums:', error);
            app.showNotification(error.message || window.i18n.t('notifications.gallery.error_adding_to_albums'), 'error');
        }
    },

    async bulkRemove() {
        // Override in subclass if needed
    },

    openBulkModal(instanceKey, ModalClass) {
        if (this.selectedItems.size === 0) return;
        if (!this[instanceKey]) {
            this[instanceKey] = new ModalClass({
                onSave: () => {
                    this.clearSelection();
                    this.loadContent();
                }
            });
        }
        this[instanceKey].show(this.selectedItems);
    },

    toggleItemSelection(item, mediaId, event = null) {
        if (this.suppressClick || document.body.classList.contains('reorder-active-mode')) return;

        const checkbox = item.querySelector('.select-checkbox');

        // Handle Shift-Click Range Selection
        if (event && event.shiftKey && this.lastSelectedId) {
            const rangeIds = this.getRangeFromLast(mediaId);
            const allSelected = rangeIds.every(id => this.selectedItems.has(id));
            const targetState = !allSelected;

            rangeIds.forEach(id => {
                this.applySelectionState(id, targetState);
            });

            this.lastSelectedId = mediaId;
        } else {
            // Normal Toggle
            if (this.selectedItems.has(mediaId)) {
                this.applySelectionState(mediaId, false);
            } else {
                this.applySelectionState(mediaId, true);
                this.lastSelectedId = mediaId;
            }
        }

        this.updateBulkActionsUI();
        this.updateSelectionModeClass();
    },
});
