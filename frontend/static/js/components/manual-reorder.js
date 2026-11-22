class ManualReorder {
    constructor(options = {}) {
        if (options.sections && Array.isArray(options.sections)) {
            this.sections = options.sections;
        } else if (options.grid) {
            this.sections = [{
                grid: options.grid,
                itemSelector: options.itemSelector || '.gallery-item',
                idExtractor: options.idExtractor || ((el) => parseInt(el.dataset.id || el.dataset.mediaId)),
                fetchChunk: options.fetchChunk || null,
                chunkLimit: options.chunkLimit || null,
                fetchAll: options.fetchAll || null,
                saveEndpoint: options.saveEndpoint,
                savePayloadKey: options.savePayloadKey || 'album_ids',
                clearEndpoint: options.clearEndpoint || options.saveEndpoint
            }];
        } else {
            this.sections = [];
        }

        this.onSaveSuccess = options.onSaveSuccess || (() => { });
        this.onClearSuccess = options.onClearSuccess || (() => { });
        this.onCancel = options.onCancel || (() => { });
        this.onActivate = options.onActivate || (() => { });
        this.dragClasses = Array.isArray(options.dragClasses)
            ? options.dragClasses
            : ['opacity-30', 'ring-2', 'ring-primary'];

        this.isActive = false;
        this.activeSections = [];
        this.initialSectionIds = new Map();
        this.draggedItem = null;
        this.currentSection = null;
        this.actionBar = null;
        this._rafId = null;
        this._lastInsertTarget = null;

        this._touchTimer = null;
        this._touchStartPos = null;
        this._touchSection = null;
        this._touchCandidateItem = null;
        this._touchDraggedItem = null;
        this._touchJustDragged = false;

        this._boundDragStart = this._handleDragStart.bind(this);
        this._boundDragOver = this._handleDragOver.bind(this);
        this._boundDragEnter = this._handleDragEnter.bind(this);
        this._boundDragLeave = this._handleDragLeave.bind(this);
        this._boundDrop = this._handleDrop.bind(this);
        this._boundGridDragOver = this._handleGridDragOver.bind(this);
        this._boundGridDrop = this._handleDrop.bind(this);
        this._boundDragEnd = this._handleDragEnd.bind(this);
        this._boundPreventClick = this._handlePreventClick.bind(this);
        this._boundContextMenu = this._handleContextMenu.bind(this);

        this._boundTouchStart = this._handleTouchStart.bind(this);
        this._boundTouchMove = this._handleTouchMove.bind(this);
        this._boundTouchEnd = this._handleTouchEnd.bind(this);
    }

    async activate() {
        if (this.isActive) return;

        if (typeof this.onActivate === 'function') {
            await this.onActivate();
        }

        this.activeSections = [];
        this.initialSectionIds.clear();

        for (const section of this.sections) {
            const gridEl = typeof section.grid === 'function' ? section.grid() : section.grid;
            if (!gridEl) continue;
            if (typeof section.enabled === 'function' && !section.enabled()) continue;
            if (typeof section.enabled === 'boolean' && !section.enabled) continue;

            const secObj = {
                ...section,
                grid: gridEl,
                itemSelector: section.itemSelector || '.gallery-item',
                idExtractor: section.idExtractor || ((el) => parseInt(el.dataset.id || el.dataset.mediaId))
            };

            const hadFetchChunk = typeof secObj.fetchChunk === 'function';
            const hadFetchAll = typeof secObj.fetchAll === 'function';

            if (hadFetchChunk) {
                secObj.preFetchHtml = secObj.grid.innerHTML;
                secObj.chunkPage = 1;
                secObj.chunkLimit = secObj.chunkLimit || null;
                const result = await secObj.fetchChunk(1, secObj.chunkLimit);
                if (result) {
                    secObj.totalItems = result.total !== undefined ? result.total : 0;
                    secObj.totalPages = result.totalPages !== undefined ? result.totalPages : 1;
                    if (result.limit && !secObj.chunkLimit) {
                        secObj.chunkLimit = result.limit;
                    }
                }
            } else if (hadFetchAll) {
                secObj.preFetchHtml = secObj.grid.innerHTML;
                await secObj.fetchAll(secObj);
            }

            const items = secObj.grid.querySelectorAll(secObj.itemSelector);
            if (items.length > 0) {
                secObj.originalHtml = secObj.grid.innerHTML;
                this.activeSections.push(secObj);
                this.initialSectionIds.set(secObj, this.getItemIds(secObj));
            }

            if (hadFetchChunk) {
                this.renderSectionLoadMore(secObj);
            }
        }

        if (this.activeSections.length === 0) return;

        this.isActive = true;
        document.body.classList.add('reorder-active-mode');

        const pageNav = document.getElementById('page-nav');
        if (pageNav) {
            this._prevPageNavDisplay = pageNav.style.display;
            pageNav.style.display = 'none';
        }

        for (const section of this.activeSections) {
            this.setupSectionItems(section);
        }

        this.createActionBar();
    }

    deactivate() {
        if (!this.isActive) return;
        window.autoScroll?.stop();
        this.isActive = false;
        document.body.classList.remove('reorder-active-mode', 'is-dragging');

        this.removeAllLoadMoreContainers();

        const pageNav = document.getElementById('page-nav');
        if (pageNav && this._prevPageNavDisplay !== undefined) {
            pageNav.style.display = this._prevPageNavDisplay;
        }

        for (const section of this.activeSections) {
            this.teardownSectionItems(section);
        }
        this.activeSections = [];
        this.initialSectionIds.clear();
        this.removeActionBar();
    }

    renderSectionLoadMore(section) {
        this.removeSectionLoadMore(section);

        if (!section || !section.grid) return;
        const loadedCount = section.grid.querySelectorAll(section.itemSelector).length;
        if (section.totalItems && loadedCount >= section.totalItems) return;
        if (section.totalPages && (section.chunkPage || 1) >= section.totalPages) return;

        const container = document.createElement('div');
        container.className = 'reorder-load-more col-span-full py-4 text-center';

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn px-6 py-2 text-sm cursor-pointer font-medium hover:border-primary transition-colors';
        const totalText = section.totalItems ? ` (${loadedCount}/${section.totalItems})` : '';
        btn.textContent = `${window.i18n.t('common.load_more')}${totalText}`;

        btn.addEventListener('click', async () => {
            btn.disabled = true;
            btn.textContent = '...';

            try {
                section.chunkPage = (section.chunkPage || 1) + 1;
                const result = await section.fetchChunk(section.chunkPage, section.chunkLimit || null);
                if (!result) throw new Error('Failed to load chunk');

                if (result.total !== undefined) {
                    section.totalItems = result.total;
                }
                if (result.totalPages !== undefined) {
                    section.totalPages = result.totalPages;
                }
                if (result.limit && !section.chunkLimit) {
                    section.chunkLimit = result.limit;
                }

                this.setupSectionItems(section);

                if (result.newIds && result.newIds.length > 0) {
                    const initial = this.initialSectionIds.get(section);
                    if (initial) {
                        initial.push(...result.newIds);
                    }
                }

                const currentLoaded = section.grid.querySelectorAll(section.itemSelector).length;
                const hasMorePages = section.totalPages ? section.chunkPage < section.totalPages : true;
                const hasMoreItems = section.totalItems ? currentLoaded < section.totalItems : (result.newIds && result.newIds.length > 0);

                if (hasMorePages && hasMoreItems) {
                    btn.disabled = false;
                    const nextTotalText = section.totalItems ? ` (${currentLoaded}/${section.totalItems})` : '';
                    btn.textContent = `${window.i18n.t('common.load_more')}${nextTotalText}`;
                } else {
                    container.remove();
                    section.loadMoreContainer = null;
                }
            } catch (err) {
                console.error('Error loading more items for reorder:', err);
                btn.disabled = false;
                const retryTotalText = section.totalItems ? ` (${loadedCount}/${section.totalItems})` : '';
                btn.textContent = `${window.i18n.t('common.load_more')}${retryTotalText}`;
            }
        });

        container.appendChild(btn);
        section.loadMoreContainer = container;
        if (section.grid.nextSibling) {
            section.grid.parentNode.insertBefore(container, section.grid.nextSibling);
        } else {
            section.grid.parentNode.appendChild(container);
        }
    }

    removeSectionLoadMore(section) {
        if (section?.loadMoreContainer) {
            section.loadMoreContainer.remove();
            section.loadMoreContainer = null;
        }
    }

    removeAllLoadMoreContainers() {
        for (const section of this.sections) {
            this.removeSectionLoadMore(section);
        }
        for (const section of this.activeSections) {
            this.removeSectionLoadMore(section);
        }
        document.querySelectorAll('.reorder-load-more, #album-reorder-load-more, #albums-reorder-load-more').forEach(el => el.remove());
    }

    hasOrderChanged() {
        for (const section of this.activeSections) {
            const initial = this.initialSectionIds.get(section) || [];
            const current = this.getItemIds(section);
            if (initial.length !== current.length) return true;
            for (let i = 0; i < initial.length; i++) {
                if (initial[i] !== current[i]) return true;
            }
        }
        return false;
    }

    getItemIds(section) {
        if (!section || !section.grid) return [];
        const items = Array.from(section.grid.querySelectorAll(section.itemSelector));
        const extractor = section.idExtractor || ((el) => parseInt(el.dataset.id || el.dataset.mediaId));
        return items.map(extractor).filter(id => !isNaN(id) && id !== null);
    }

    _bindItemEvents(item) {
        item.setAttribute('draggable', 'true');
        item.classList.add('reorder-active-item', 'cursor-grab', 'active:cursor-grabbing', 'select-none', 'relative');

        item.removeEventListener('dragstart', this._boundDragStart);
        item.removeEventListener('dragover', this._boundDragOver);
        item.removeEventListener('dragenter', this._boundDragEnter);
        item.removeEventListener('dragleave', this._boundDragLeave);
        item.removeEventListener('drop', this._boundDrop);
        item.removeEventListener('dragend', this._boundDragEnd);
        item.removeEventListener('click', this._boundPreventClick, true);
        item.removeEventListener('contextmenu', this._boundContextMenu);
        item.removeEventListener('touchstart', this._boundTouchStart);
        item.removeEventListener('touchmove', this._boundTouchMove);
        item.removeEventListener('touchend', this._boundTouchEnd);
        item.removeEventListener('touchcancel', this._boundTouchEnd);

        item.addEventListener('dragstart', this._boundDragStart);
        item.addEventListener('dragover', this._boundDragOver);
        item.addEventListener('dragenter', this._boundDragEnter);
        item.addEventListener('dragleave', this._boundDragLeave);
        item.addEventListener('drop', this._boundDrop);
        item.addEventListener('dragend', this._boundDragEnd);
        item.addEventListener('click', this._boundPreventClick, true);
        item.addEventListener('contextmenu', this._boundContextMenu);
        item.addEventListener('touchstart', this._boundTouchStart, { passive: true });
        item.addEventListener('touchmove', this._boundTouchMove, { passive: false });
        item.addEventListener('touchend', this._boundTouchEnd);
        item.addEventListener('touchcancel', this._boundTouchEnd);
    }

    setupSectionItems(section) {
        if (!section || !section.grid) return;
        section.grid.removeEventListener('dragover', this._boundGridDragOver);
        section.grid.removeEventListener('drop', this._boundGridDrop);
        section.grid.addEventListener('dragover', this._boundGridDragOver);
        section.grid.addEventListener('drop', this._boundGridDrop);

        const items = section.grid.querySelectorAll(section.itemSelector);
        items.forEach((item, index) => {
            this._bindItemEvents(item);

            let badge = item.querySelector('.reorder-badge');
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'reorder-badge absolute top-1 left-1 bg-primary primary-text text-[10px] font-bold px-1.5 py-0.5 pointer-events-none z-20';
                item.appendChild(badge);
            }
            badge.textContent = `#${index + 1}`;
        });
    }

    teardownSectionItems(section) {
        if (!section || !section.grid) return;
        section.grid.removeEventListener('dragover', this._boundGridDragOver);
        section.grid.removeEventListener('drop', this._boundGridDrop);

        const items = section.grid.querySelectorAll(section.itemSelector);
        items.forEach(item => {
            item.removeAttribute('draggable');
            item.classList.remove(
                'reorder-active-item',
                'cursor-grab',
                'active:cursor-grabbing',
                'select-none',
                'relative',
                ...this.dragClasses
            );

            const badge = item.querySelector('.reorder-badge');
            if (badge) badge.remove();

            item.removeEventListener('dragstart', this._boundDragStart);
            item.removeEventListener('dragover', this._boundDragOver);
            item.removeEventListener('dragenter', this._boundDragEnter);
            item.removeEventListener('dragleave', this._boundDragLeave);
            item.removeEventListener('drop', this._boundDrop);
            item.removeEventListener('dragend', this._boundDragEnd);
            item.removeEventListener('click', this._boundPreventClick, true);
            item.removeEventListener('contextmenu', this._boundContextMenu);
            item.removeEventListener('touchstart', this._boundTouchStart);
            item.removeEventListener('touchmove', this._boundTouchMove);
            item.removeEventListener('touchend', this._boundTouchEnd);
            item.removeEventListener('touchcancel', this._boundTouchEnd);
        });
    }

    updateSectionBadges(section) {
        if (!section || !section.grid) return;
        const items = section.grid.querySelectorAll(section.itemSelector);
        items.forEach((item, index) => {
            const badge = item.querySelector('.reorder-badge');
            if (badge) {
                badge.textContent = `#${index + 1}`;
            }
        });
    }

    _getSectionForElement(element) {
        if (!element) return null;
        return this.activeSections.find(s => s.grid && s.grid.contains(element));
    }

    _handleContextMenu(e) {
        if (this.isActive) {
            e.preventDefault();
        }
    }

    _handlePreventClick(e) {
        if (this.isActive || this._touchJustDragged) {
            e.preventDefault();
            e.stopPropagation();
        }
    }

    _handleDragStart(e) {
        const section = this._getSectionForElement(e.target);
        if (!section) return;

        const item = e.target.closest(section.itemSelector);
        if (!item) return;

        this.draggedItem = item;
        this.currentSection = section;
        this._lastInsertTarget = null;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', '');

        document.body.classList.add('is-dragging');

        setTimeout(() => {
            if (this.draggedItem) {
                this.draggedItem.classList.add(...this.dragClasses);
            }
        }, 0);
    }

    _handleGridDragOver(e) {
        if (!this.draggedItem || !this.currentSection) return;
        const section = this._getSectionForElement(e.target);
        if (section !== this.currentSection) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    }

    _handleDragOver(e) {
        e.preventDefault();
        const section = this._getSectionForElement(e.target);
        if (!section || section !== this.currentSection || !this.draggedItem) return;

        e.dataTransfer.dropEffect = 'move';

        window.autoScroll?.check(e.clientX, e.clientY, {
            bottomElement: this.actionBar,
            onScroll: (x, y) => this._updateDragDropTarget(x, y)
        });
        this._updateDragDropTarget(e.clientX, e.clientY);
    }

    _handleDragEnter(e) {
        e.preventDefault();
    }

    _handleDragLeave(e) {
        e.preventDefault();
    }

    _handleDrop(e) {
        e.preventDefault();
        window.autoScroll?.stop();
    }

    _handleDragEnd() {
        window.autoScroll?.stop();

        document.body.classList.remove('is-dragging');

        if (this._rafId) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }
        this._lastInsertTarget = null;

        if (this.draggedItem) {
            this.draggedItem.classList.remove(...this.dragClasses);
            this.draggedItem = null;
        }

        if (this.currentSection) {
            const items = this.currentSection.grid.querySelectorAll(this.currentSection.itemSelector);
            items.forEach(item => item.classList.remove(...this.dragClasses));
            this.updateSectionBadges(this.currentSection);
            this.currentSection = null;
        }
    }


    _updateDragDropTarget(clientX, clientY) {
        if (!this.draggedItem || !this.currentSection) return;
        const elem = document.elementFromPoint(clientX, clientY);
        const target = elem?.closest(this.currentSection.itemSelector);
        if (!target || target === this.draggedItem || !this.currentSection.grid.contains(target)) return;

        const rect = target.getBoundingClientRect();
        const nextTarget = (clientX - rect.left) > (rect.width / 2) ? target.nextSibling : target;
        if (nextTarget === this.draggedItem || nextTarget === this._lastInsertTarget) return;

        this._lastInsertTarget = nextTarget;
        this.currentSection.grid.insertBefore(this.draggedItem, this._lastInsertTarget);
    }

    _updateTouchDropTarget(clientX, clientY) {
        if (!this._touchDraggedItem || !this._touchSection) return;

        const elem = document.elementFromPoint(clientX, clientY);
        const target = elem?.closest(this._touchSection.itemSelector);
        if (!target || target === this._touchDraggedItem || !this._touchSection.grid.contains(target)) return;

        const rect = target.getBoundingClientRect();
        const nextTarget = (clientX - rect.left) > (rect.width / 2) ? target.nextSibling : target;
        if (nextTarget === this._touchDraggedItem || nextTarget === this._lastInsertTarget) return;

        this._lastInsertTarget = nextTarget;
        this._touchSection.grid.insertBefore(this._touchDraggedItem, this._lastInsertTarget);
    }

    // ==================== Touch Handlers ====================

    _handleTouchStart(e) {
        if (!this.isActive) return;
        const section = this._getSectionForElement(e.target);
        if (!section) return;

        const item = e.target.closest(section.itemSelector);
        if (!item) return;

        const touch = e.touches[0];
        this._touchStartPos = { x: touch.clientX, y: touch.clientY };
        this._touchSection = section;
        this._touchCandidateItem = item;

        if (this._touchTimer) clearTimeout(this._touchTimer);

        this._touchTimer = setTimeout(() => {
            this._touchTimer = null;
            this._touchDraggedItem = item;
            this.currentSection = section;
            document.body.classList.add('is-dragging');
            item.classList.add(...this.dragClasses);
            if (navigator.vibrate) {
                navigator.vibrate(50);
            }
        }, 220);
    }

    _handleTouchMove(e) {
        const touch = e.touches[0];

        if (this._touchTimer && this._touchStartPos) {
            const dx = Math.abs(touch.clientX - this._touchStartPos.x);
            const dy = Math.abs(touch.clientY - this._touchStartPos.y);
            if (dx > 8 || dy > 8) {
                clearTimeout(this._touchTimer);
                this._touchTimer = null;
                return;
            }
        }

        if (!this._touchDraggedItem || !this._touchSection) return;

        e.preventDefault();

        window.autoScroll?.check(touch.clientX, touch.clientY, {
            bottomElement: this.actionBar,
            onScroll: (x, y) => this._updateTouchDropTarget(x, y)
        });
        this._updateTouchDropTarget(touch.clientX, touch.clientY);
    }

    _handleTouchEnd(e) {
        window.autoScroll?.stop();

        if (this._touchTimer) {
            clearTimeout(this._touchTimer);
            this._touchTimer = null;
        }

        if (this._rafId) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }
        this._lastInsertTarget = null;

        document.body.classList.remove('is-dragging');

        if (this._touchDraggedItem) {
            e.preventDefault();
            this._touchDraggedItem.classList.remove(...this.dragClasses);
            this.updateSectionBadges(this._touchSection);

            this._touchJustDragged = true;
            setTimeout(() => {
                this._touchJustDragged = false;
            }, 300);

            this._touchDraggedItem = null;
            this.currentSection = null;
        }
        this._touchCandidateItem = null;
        this._touchSection = null;
        this._touchStartPos = null;
    }

    // ==================== Action Bar & Persistence ====================

    createActionBar() {
        this.removeActionBar();

        const bar = document.createElement('div');
        bar.className = 'manual-reorder-bar fixed bottom-0 sm:bottom-6 left-1/2 -translate-x-1/2 z-50 surface border-t sm:border p-3 flex items-center justify-center gap-3 w-[100vw] sm:w-auto';

        const saveText = window.i18n.t('common.save');
        const clearText = window.i18n.t('gallery.sort_clear_order');
        const cancelText = window.i18n.t('common.cancel');

        bar.innerHTML = `
            <button type="button" class="btn-save-order btn-primary">
                ${saveText}
            </button>
            <button type="button" class="btn-clear-order btn-danger">
                ${clearText}
            </button>
            <button type="button" class="btn-cancel-order btn-dark">
                ${cancelText}
            </button>
        `;

        bar.querySelector('.btn-save-order').addEventListener('click', () => this.save());
        bar.querySelector('.btn-clear-order').addEventListener('click', () => this.clear());
        bar.querySelector('.btn-cancel-order').addEventListener('click', () => this.cancel());

        document.body.appendChild(bar);
        this.actionBar = bar;
    }

    removeActionBar() {
        if (this.actionBar) {
            this.actionBar.remove();
            this.actionBar = null;
        }
    }

    _showNotification(message, type = 'info', title = null) {
        const appInstance = window.app || (typeof app !== 'undefined' ? app : null);
        if (appInstance && typeof appInstance.showNotification === 'function') {
            appInstance.showNotification(message, type, title);
        } else if (type === 'error') {
            console.error(message);
        } else {
            console.warn(message);
        }
    }

    async save() {
        if (!this.activeSections.length) return;

        const saveBtn = this.actionBar?.querySelector('.btn-save-order');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = '...';
        }

        const failedSections = [];
        const succeededSections = [];

        try {
            for (const section of this.activeSections) {
                const ids = this.getItemIds(section);
                if (!ids.length) continue;

                try {
                    const response = await fetch(section.saveEndpoint, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ [section.savePayloadKey || 'album_ids']: ids })
                    });

                    if (!response.ok) {
                        const err = await response.json().catch(() => ({}));
                        failedSections.push({ section, error: err.detail || window.i18n.t('gallery.sort_order_save_failed') });
                    } else {
                        succeededSections.push(section);
                        section.originalHtml = section.grid.innerHTML;
                        this.initialSectionIds.set(section, [...ids]);
                    }
                } catch (networkErr) {
                    failedSections.push({ section, error: networkErr.message || window.i18n.t('gallery.sort_order_save_failed') });
                }
            }

            if (failedSections.length === 0) {
                this.deactivate();
                this._showNotification(window.i18n.t('gallery.sort_order_saved'), 'success');
                if (typeof this.onSaveSuccess === 'function') {
                    this.onSaveSuccess();
                }
            } else if (succeededSections.length > 0) {
                const failedNames = failedSections.map(f => f.section.name || f.section.savePayloadKey || 'section').join(', ');
                const errorMsg = window.i18n.t('gallery.sort_order_save_partial', { sections: failedNames });
                this._showNotification(errorMsg, 'warning');
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = window.i18n.t('common.save');
                }
            } else {
                const firstErr = failedSections[0]?.error || window.i18n.t('gallery.sort_order_save_failed');
                this._showNotification(firstErr, 'error');
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = window.i18n.t('common.save');
                }
            }
        } catch (error) {
            console.error('Error saving manual order:', error);
            this._showNotification(error.message || window.i18n.t('gallery.sort_order_save_failed'), 'error');
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.textContent = window.i18n.t('common.save');
            }
        }
    }

    clear() {
        if (typeof ModalHelper === 'undefined') {
            this.executeClear();
            return;
        }

        new ModalHelper({
            id: 'clear-manual-order-modal',
            type: 'warning',
            title: window.i18n.t('gallery.sort_clear_order'),
            message: window.i18n.t('gallery.sort_clear_confirm'),
            confirmText: window.i18n.t('common.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            onConfirm: () => this.executeClear()
        }).show();
    }

    async executeClear() {
        const clearBtn = this.actionBar?.querySelector('.btn-clear-order');
        if (clearBtn) {
            clearBtn.disabled = true;
        }

        const failedSections = [];
        const succeededSections = [];

        try {
            for (const section of this.activeSections) {
                const endpoint = section.clearEndpoint || section.saveEndpoint;
                try {
                    const response = await fetch(endpoint, {
                        method: 'DELETE'
                    });

                    if (!response.ok) {
                        const err = await response.json().catch(() => ({}));
                        failedSections.push({ section, error: err.detail || window.i18n.t('gallery.sort_order_clear_failed') });
                    } else {
                        succeededSections.push(section);
                    }
                } catch (networkErr) {
                    failedSections.push({ section, error: networkErr.message || window.i18n.t('gallery.sort_order_clear_failed') });
                }
            }

            if (failedSections.length === 0) {
                this.deactivate();
                this._showNotification(window.i18n.t('gallery.sort_order_cleared'), 'info');
                if (typeof this.onClearSuccess === 'function') {
                    this.onClearSuccess();
                }
            } else {
                const firstErr = failedSections[0]?.error || window.i18n.t('gallery.sort_order_clear_failed');
                this._showNotification(firstErr, 'error');
                if (clearBtn) {
                    clearBtn.disabled = false;
                }
            }
        } catch (error) {
            console.error('Error clearing manual order:', error);
            this._showNotification(error.message || window.i18n.t('gallery.sort_order_clear_failed'), 'error');
            if (clearBtn) {
                clearBtn.disabled = false;
            }
        }
    }

    cancel() {
        if (this.hasOrderChanged()) {
            if (typeof ModalHelper !== 'undefined') {
                new ModalHelper({
                    id: 'cancel-manual-order-modal',
                    type: 'warning',
                    title: window.i18n.t('common.discard_changes'),
                    message: window.i18n.t('gallery.sort_cancel_confirm'),
                    confirmText: window.i18n.t('common.discard'),
                    cancelText: window.i18n.t('common.cancel'),
                    onConfirm: () => this.executeCancel()
                }).show();
                return;
            }
        }
        this.executeCancel();
    }

    executeCancel() {
        for (const section of this.activeSections) {
            if (section.preFetchHtml && section.grid) {
                section.grid.innerHTML = section.preFetchHtml;
            } else if (section.originalHtml && section.grid) {
                section.grid.innerHTML = section.originalHtml;
            }
        }
        this.deactivate();
        if (typeof this.onCancel === 'function') {
            this.onCancel();
        }
    }
}

window.ManualReorder = ManualReorder;
