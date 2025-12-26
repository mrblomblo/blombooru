class BaseGallery {
    constructor(options = {}) {
        this.options = {
            gridSelector: '#gallery-grid',
            loadingSelector: '#loading-indicator',
            popularTagsSelector: '#popular-tags',
            pageNavSelector: '#page-nav-top',
            sortBySelector: '#sort-by-select',
            sortOrderSelector: '#sort-order-select',
            enableTooltips: true,
            enablePagination: true,
            enableRatingFilter: true,
            enableSorting: true,
            defaultRating: 'explicit',
            defaultSort: 'uploaded_at',
            defaultOrder: 'desc',
            ...options
        };

        this.currentPage = 1;
        this.totalPages = 1;
        this.isLoading = false;
        this.selectedItems = new Set();
        this.tagCounts = new Map();
        this.tooltipHelper = null;
        this.sortBySelect = null;
        this.sortOrderSelect = null;

        // Cache DOM elements
        this.elements = {
            grid: document.querySelector(this.options.gridSelector),
            loading: document.querySelector(this.options.loadingSelector),
            popularTags: document.querySelector(this.options.popularTagsSelector),
            pageNav: document.querySelector(this.options.pageNavSelector),
            sortBy: document.querySelector(this.options.sortBySelector),
            sortOrder: document.querySelector(this.options.sortOrderSelector)
        };

        // Current state
        this.currentRating = localStorage.getItem('selectedRating') || this.options.defaultRating;
        this.currentSort = this.options.defaultSort;
        this.currentOrder = this.options.defaultOrder;
    }

    /**
     * Initialize common features
     */
    initCommon() {
        if (this.options.enableRatingFilter) {
            this.setupRatingFilter();
        }
        if (this.options.enableSorting) {
            this.setupSorting();
        }
        if (this.options.enablePagination) {
            this.setupPageJumpModal();
        }
        if (this.options.enableTooltips) {
            this.initTooltip();
        }
        this.setupBulkActions();
    }

    // ==================== Rating Filter ====================

    setupRatingFilter() {
        document.querySelectorAll('.rating-filter-input').forEach(radio => {
            radio.addEventListener('change', (e) => {
                this.currentRating = e.target.value;
                this.updateRatingFilterLabels(this.currentRating);
                localStorage.setItem('selectedRating', this.currentRating);
                this.onRatingChange();
            });
        });

        // Set initial state
        const savedRadio = document.querySelector(`.rating-filter-input[value="${this.currentRating}"]`);
        if (savedRadio) {
            savedRadio.checked = true;
            this.updateRatingFilterLabels(this.currentRating);
        }
    }

    updateRatingFilterLabels(selectedValue) {
        document.querySelectorAll('.rating-filter-label').forEach(label => {
            label.classList.remove('checked');
        });

        document.querySelectorAll(`.rating-filter-input[value="${selectedValue}"]`).forEach(radio => {
            radio.checked = true;
            const label = radio.nextElementSibling;
            if (label) {
                label.classList.add('checked');
            }
        });
    }

    onRatingChange() {
        this.currentPage = 1;
        this.loadContent();
    }

    // ==================== Sorting ====================

    setupSorting() {
        if (typeof CustomSelect === 'undefined') {
            console.warn('CustomSelect not loaded');
            return;
        }

        if (this.elements.sortBy) {
            this.sortBySelect = new CustomSelect(this.elements.sortBy);

            // Set initial value from URL
            const params = new URLSearchParams(window.location.search);
            if (params.has('sort')) {
                this.sortBySelect.setValue(params.get('sort'));
            }

            this.elements.sortBy.addEventListener('change', () => this.onSortChange());
        }

        if (this.elements.sortOrder) {
            this.sortOrderSelect = new CustomSelect(this.elements.sortOrder);

            const params = new URLSearchParams(window.location.search);
            if (params.has('order')) {
                this.sortOrderSelect.setValue(params.get('order'));
            }

            this.elements.sortOrder.addEventListener('change', () => this.onSortChange());
        }
    }

    getSortValue() {
        return this.elements.sortBy?.dataset.value || this.currentSort;
    }

    getOrderValue() {
        return this.elements.sortOrder?.dataset.value || this.currentOrder;
    }

    onSortChange() {
        this.currentSort = this.getSortValue();
        this.currentOrder = this.getOrderValue();
        this.updateUrlParams({ sort: this.currentSort, order: this.currentOrder });
        this.loadContent();
    }

    addSortOption(value, label) {
        if (this.sortBySelect) {
            this.sortBySelect.addOption(value, label);
        }
    }

    removeSortOption(value) {
        if (this.sortBySelect) {
            this.sortBySelect.removeOption(value);
        }
    }

    // ==================== Pagination ====================

    setupPageJumpModal() {
        const modal = document.getElementById('page-jump-modal');
        const input = document.getElementById('page-jump-input');
        const goBtn = document.getElementById('page-jump-go');
        const cancelBtn = document.getElementById('page-jump-cancel');

        if (!modal || !input || !goBtn || !cancelBtn) return;

        goBtn.addEventListener('click', () => {
            const page = parseInt(input.value);
            if (page >= 1 && page <= this.totalPages) {
                modal.style.display = 'none';
                this.goToPage(page);
            }
        });

        cancelBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });

        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                goBtn.click();
            }
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    }

    showPageJumpModal() {
        const modal = document.getElementById('page-jump-modal');
        const input = document.getElementById('page-jump-input');

        if (!modal || !input) return;

        input.max = this.totalPages;
        input.value = this.currentPage;
        modal.style.display = 'flex';
        input.focus();
        input.select();
    }

    goToPage(page) {
        if (page < 1 || page > this.totalPages || page === this.currentPage) return;

        this.currentPage = page;
        this.updateUrlParams({ page });
        this.loadContent();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    renderPagination() {
        if (!this.elements.pageNav) return;

        if (this.totalPages <= 1) {
            this.elements.pageNav.style.display = 'none';
            return;
        }

        const paginationHTML = this.generatePaginationHTML();
        const container = this.elements.pageNav.querySelector('div');
        if (container) {
            container.innerHTML = paginationHTML;
        }
        this.elements.pageNav.style.display = 'block';
        this.setupPaginationHandlers();
    }

    generatePaginationHTML() {
        const pages = [];
        const current = this.currentPage;
        const total = this.totalPages;

        // Always show first page
        pages.push(this.createPageButton(1, current === 1));

        if (total <= 7) {
            for (let i = 2; i <= total; i++) {
                pages.push(this.createPageButton(i, current === i));
            }
        } else {
            if (current <= 4) {
                for (let i = 2; i <= 5; i++) {
                    pages.push(this.createPageButton(i, current === i));
                }
                pages.push(this.createEllipsis());
                pages.push(this.createPageButton(total, false));
            } else if (current >= total - 3) {
                pages.push(this.createEllipsis());
                for (let i = total - 4; i <= total; i++) {
                    pages.push(this.createPageButton(i, current === i));
                }
            } else {
                pages.push(this.createEllipsis());
                for (let i = current - 1; i <= current + 1; i++) {
                    pages.push(this.createPageButton(i, current === i));
                }
                pages.push(this.createEllipsis());
                pages.push(this.createPageButton(total, false));
            }
        }

        return pages.join(' <span class="text-secondary">|</span> ');
    }

    createPageButton(pageNum, isActive) {
        if (isActive) {
            return `<span class="px-2 py-1 font-bold text-primary">${pageNum}</span>`;
        }
        return `<a href="#" class="px-2 py-1 hover:text-primary page-link" data-page="${pageNum}">${pageNum}</a>`;
    }

    createEllipsis() {
        return `<a href="#" class="px-2 py-1 hover:text-primary page-ellipsis">...</a>`;
    }

    setupPaginationHandlers() {
        if (!this.elements.pageNav) return;

        this.elements.pageNav.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                this.goToPage(page);
            });
        });

        this.elements.pageNav.querySelectorAll('.page-ellipsis').forEach(ellipsis => {
            ellipsis.addEventListener('click', (e) => {
                e.preventDefault();
                this.showPageJumpModal();
            });
        });
    }

    // ==================== Bulk Actions ====================

    setupBulkActions() {
        const selectAllBtn = document.getElementById('select-all-btn');
        const deselectAllBtn = document.getElementById('deselect-all-btn');
        const bulkDeleteBtn = document.getElementById('bulk-delete-btn');
        const bulkAlbumBtn = document.getElementById('bulk-album-btn');
        const bulkRemoveBtn = document.getElementById('bulk-remove-btn');

        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', () => this.selectAll());
        }
        if (deselectAllBtn) {
            deselectAllBtn.addEventListener('click', () => this.clearSelection());
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
    }

    updateBulkActionsUI() {
        const bulkActions = document.getElementById('bulk-actions');
        if (bulkActions) {
            bulkActions.style.display = this.selectedItems.size > 0 ? 'block' : 'none';
        }

        const count = document.getElementById('selected-count');
        if (count) {
            count.textContent = this.selectedItems.size;
        }
    }

    selectAll() {
        document.querySelectorAll('.gallery-item').forEach(item => {
            const id = parseInt(item.dataset.id);
            const checkbox = item.querySelector('.checkbox, .album-item-checkbox');

            if (checkbox && !checkbox.checked) {
                checkbox.checked = true;
                this.selectedItems.add(id);
                item.classList.add('selected');
            }
        });
        this.updateBulkActionsUI();
    }

    clearSelection() {
        this.selectedItems.clear();
        document.querySelectorAll('.gallery-item').forEach(item => {
            item.classList.remove('selected');
            const checkbox = item.querySelector('.checkbox, .album-item-checkbox');
            if (checkbox) checkbox.checked = false;
        });
        this.updateBulkActionsUI();
    }

    async bulkDelete() {
        const itemCount = this.selectedItems.size;
        if (itemCount === 0) return;

        const modal = new ModalHelper({
            id: 'bulk-delete-modal',
            type: 'danger',
            title: `Delete ${itemCount > 1 ? 'Multiple Items' : 'Item'}`,
            message: `Are you sure you want to delete ${itemCount} item${itemCount > 1 ? 's' : ''}? This action cannot be undone.`,
            confirmText: 'Yes, Delete',
            cancelText: 'Cancel',
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
    }

    async bulkAddToAlbums() {
        const itemCount = this.selectedItems.size;
        if (itemCount === 0) return;

        try {
            const result = await AlbumPicker.pick({
                title: `Add ${itemCount} Item${itemCount > 1 ? 's' : ''} to Albums`,
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

            app.showNotification(`Added ${itemCount} item(s) to ${successCount} album(s)`, 'success');
            this.clearSelection();
        } catch (error) {
            console.error('Error adding to albums:', error);
            app.showNotification(error.message || 'Error adding to albums', 'error');
        }
    }

    async bulkRemove() {
        // Override in subclass if needed
    }

    // ==================== Tooltip ====================

    initTooltip() {
        if (typeof TooltipHelper === 'undefined') {
            console.warn('TooltipHelper not loaded');
            return;
        }

        this.tooltipHelper = new TooltipHelper({
            id: `${this.constructor.name.toLowerCase()}-tooltip`,
            delay: 300
        });
    }

    // ==================== Popular Tags ====================

    processTagCounts(items) {
        items.forEach(item => {
            if (item.tags && Array.isArray(item.tags)) {
                item.tags.forEach(tag => {
                    const currentCount = this.tagCounts.get(tag.name) || { count: 0, category: tag.category };
                    this.tagCounts.set(tag.name, {
                        count: currentCount.count + 1,
                        category: tag.category
                    });
                });
            }
        });
    }

    renderPopularTags(tags = null) {
        if (!this.elements.popularTags) return;

        let sortedTags;

        if (tags) {
            // Handle both array of objects and array of [name, data] tuples
            if (Array.isArray(tags) && tags.length > 0) {
                if (Array.isArray(tags[0])) {
                    // Already in tuple format: [[name, {count, category}], ...]
                    sortedTags = tags;
                } else {
                    // Object format: [{name, count/post_count, category}, ...]
                    sortedTags = tags.map(t => [
                        t.name,
                        { count: t.count || t.post_count || 0, category: t.category || 'general' }
                    ]);
                }
            } else {
                sortedTags = [];
            }
        } else {
            sortedTags = Array.from(this.tagCounts.entries())
                .sort((a, b) => b[1].count - a[1].count)
                .slice(0, 20);
        }

        if (sortedTags.length === 0) {
            this.elements.popularTags.innerHTML = '<p class="text-secondary">No tags found</p>';
            return;
        }

        const currentParams = new URLSearchParams(window.location.search);
        const currentQuery = currentParams.get('q') || '';
        const currentTags = currentQuery.split(/\s+/).filter(t => t.length > 0);

        this.elements.popularTags.innerHTML = sortedTags.map(([tagName, data]) => {
            const isInQuery = currentTags.includes(tagName);
            const newQuery = isInQuery ? currentQuery :
                (currentQuery ? `${currentQuery} ${tagName}` : tagName);

            const params = new URLSearchParams(window.location.search);
            params.set('q', newQuery);
            params.delete('page');

            return `
                <div class="${isInQuery ? 'popular-tag-item opacity-50' : 'popular-tag-item'}">
                    <a href="/?${params.toString()}" 
                       class="popular-tag-name tag ${data.category || 'general'} tag-text" 
                       ${isInQuery ? 'style="pointer-events: none;"' : ''}>
                        ${tagName}
                    </a>
                    <span class="popular-tag-count">${data.count}</span>
                </div>
            `;
        }).join('');
    }

    // ==================== Loading State ====================

    showLoading() {
        if (this.elements.loading) {
            this.elements.loading.style.display = 'block';
        }
    }

    hideLoading() {
        if (this.elements.loading) {
            this.elements.loading.style.display = 'none';
        }
    }

    // ==================== Gallery Item Creation ====================

    createGalleryItem(media, options = {}) {
        const {
            checkboxClass = 'checkbox',
            preserveQueryParams = true
        } = options;

        const item = document.createElement('div');
        item.className = `gallery-item ${media.file_type}`;
        item.dataset.id = media.id;
        item.dataset.rating = media.rating;

        // Checkbox
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = checkboxClass;
        checkbox.dataset.id = media.id;

        if (this.selectedItems.has(media.id)) {
            checkbox.checked = true;
            item.classList.add('selected');
        }

        checkbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                this.selectedItems.add(media.id);
                item.classList.add('selected');
            } else {
                this.selectedItems.delete(media.id);
                item.classList.remove('selected');
            }
            this.updateBulkActionsUI();
        });

        // Image
        const img = document.createElement('img');
        img.src = `/api/media/${media.id}/thumbnail`;
        img.alt = media.filename;
        img.loading = 'lazy';
        img.className = 'transition-colors';
        img.onerror = () => {
            img.src = '/static/images/no-thumbnail.png';
        };

        // Link
        const link = document.createElement('a');
        if (preserveQueryParams) {
            const params = new URLSearchParams(window.location.search);
            const queryString = params.toString();
            link.href = `/media/${media.id}${queryString ? '?' + queryString : ''}`;
        } else {
            link.href = `/media/${media.id}`;
        }
        link.appendChild(img);

        // Tooltip
        if (this.tooltipHelper && media.tags && media.tags.length > 0) {
            this.tooltipHelper.addToElement(item, media.tags);
        }

        item.appendChild(checkbox);
        item.appendChild(link);

        // Share indicator
        if (media.is_shared) {
            const shareIcon = document.createElement('div');
            shareIcon.className = 'share-icon';
            shareIcon.textContent = 'SHARED';
            item.appendChild(shareIcon);
        }

        return item;
    }

    // ==================== URL Helpers ====================

    updateUrlParams(params) {
        const url = new URL(window.location);
        Object.entries(params).forEach(([key, value]) => {
            if (value !== null && value !== undefined) {
                url.searchParams.set(key, value);
            } else {
                url.searchParams.delete(key);
            }
        });
        window.history.pushState({}, '', url);
    }

    getUrlParam(key, defaultValue = null) {
        const params = new URLSearchParams(window.location.search);
        return params.get(key) || defaultValue;
    }

    // ==================== Error Handling ====================

    showError(message) {
        if (!this.elements.grid) return;

        const errorDiv = document.createElement('div');
        errorDiv.className = 'col-span-full';
        errorDiv.innerHTML = `
            <div class="bg-danger text-white p-4 my-4">
                <strong>Error:</strong> ${message}
                <br><small>Check the browser console for more details</small>
            </div>
        `;
        this.elements.grid.appendChild(errorDiv);
    }

    showEmptyState(message = 'No items found') {
        if (!this.elements.grid) return;

        this.elements.grid.innerHTML = `
            <div class="col-span-full text-center py-16 text-secondary">
                <h2 class="text-lg mb-2">${message}</h2>
                ${app.isAuthenticated ? '<a href="/admin" class="btn mt-4 inline-block">Go to Admin Panel</a>' : ''}
            </div>
        `;
    }

    // ==================== Abstract Methods ====================

    async loadContent() {
        throw new Error('loadContent must be implemented by subclass');
    }
}
