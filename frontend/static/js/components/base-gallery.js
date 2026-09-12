class BaseGallery {
    constructor(options = {}) {
        this.options = {
            gridSelector: '#gallery-grid',
            loadingSelector: '#loading-indicator',
            popularTagsSelector: '#popular-tags',
            pageNavSelector: '#page-nav',
            sortBySelector: '#sort-by-select',
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
        this.currentRandomSeed = null;

        // Selection state
        this.lastSelectedId = null;
        this.isDragging = false;
        this.dragStartItem = null;
        this.selectionSnapshot = null;
        this.dragTargetState = null;
        this.suppressClick = false;

        // Cache DOM elements
        this.elements = {
            grid: document.querySelector(this.options.gridSelector),
            loading: document.querySelector(this.options.loadingSelector),
            popularTags: document.querySelector(this.options.popularTagsSelector),
            pageNav: document.querySelector(this.options.pageNavSelector),
            sortBy: document.querySelector(this.options.sortBySelector)
        };

        // Current state
        const cookieRating = (function (name) {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return null;
        })('rating_filter');

        const sidebarMode = document.body.dataset.sidebarMode || window.SIDEBAR_FILTER_MODE || 'rating';
        this.sidebarMode = sidebarMode;

        // Rating initialization
        const rawStoredRating = localStorage.getItem('selectedRating') || cookieRating;
        let initialRatings = [];

        if (sidebarMode === 'custom' || sidebarMode === 'off') {
            initialRatings = ['safe', 'questionable', 'explicit'];
        } else if (rawStoredRating) {
            initialRatings = rawStoredRating
                .split(',')
                .map(r => r.trim().toLowerCase())
                .filter(r => ['safe', 'questionable', 'explicit'].includes(r));
        }

        if (initialRatings.length === 0) {
            initialRatings = ['safe'];
        }

        this.selectedRatings = new Set(initialRatings);
        this.currentRating = Array.from(this.selectedRatings).join(',');

        // Custom filters initialization
        const rawCustomFilter = localStorage.getItem('selectedCustomFilter') || '';
        let initialCustomFilters = [];
        if (sidebarMode === 'custom' || sidebarMode === 'both') {
            if (rawCustomFilter) {
                try {
                    const parsed = JSON.parse(rawCustomFilter);
                    if (Array.isArray(parsed)) {
                        initialCustomFilters = parsed;
                    } else if (typeof parsed === 'string' && parsed) {
                        initialCustomFilters = [parsed];
                    }
                } catch {
                    if (typeof rawCustomFilter === 'string' && rawCustomFilter) {
                        initialCustomFilters = [rawCustomFilter];
                    }
                }
            }
        }
        this.selectedCustomFilters = new Set(initialCustomFilters);
        this.currentCustomFilter = Array.from(this.selectedCustomFilters).join(' ');

        const urlParams = new URLSearchParams(window.location.search);
        const sortControls = document.querySelector('.js-sort-controls');
        const defaultOrderFromDom = sortControls?.dataset.defaultOrder || this.options.defaultOrder;

        this.currentSort = urlParams.get('sort') || this.elements.sortBy?.dataset.value || this.options.defaultSort;
        this.currentOrder = urlParams.get('order') || defaultOrderFromDom;
        this.currentRandomSeed = urlParams.get('seed') || null;
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
        this.setupDragSelectionGlobalListeners();
        this.setupKeybindings();
    }

    setupDragSelectionGlobalListeners() {
        // Global mouseup to end drag even if not over an item
        document.addEventListener('mouseup', () => {
            this.dragStartItem = null;
            if (this.isDragging) {
                this.handleDragEnd();
            }
        });

        // Prevent text selection while dragging
        document.addEventListener('selectstart', (e) => {
            if (this.isDragging) {
                e.preventDefault();
            }
        });
    }

    // ==================== Rating Filter ====================

    setupRatingFilter() {
        document.querySelectorAll('.rating-filter-input').forEach(checkbox => {
            // Prevent unchecking the last selected rating
            checkbox.addEventListener('click', (e) => {
                const val = checkbox.value;
                if (this.selectedRatings.has(val) && this.selectedRatings.size === 1) {
                    e.preventDefault();
                    checkbox.checked = true;
                    return;
                }
            });

            checkbox.addEventListener('change', (e) => {
                const val = e.target.value;
                if (e.target.checked) {
                    this.selectedRatings.add(val);
                } else {
                    if (this.selectedRatings.size > 1) {
                        this.selectedRatings.delete(val);
                    } else {
                        e.target.checked = true;
                        return;
                    }
                }
                const ratingStr = Array.from(this.selectedRatings).join(',');
                this.currentRating = ratingStr;
                this.updateRatingFilterLabels();
                localStorage.setItem('selectedRating', ratingStr);
                document.cookie = "rating_filter=" + ratingStr + "; path=/; max-age=31536000";
                this.onRatingChange();
            });
        });

        // Set initial state
        const ratingStr = Array.from(this.selectedRatings).join(',');
        this.currentRating = ratingStr;
        localStorage.setItem('selectedRating', ratingStr);
        document.cookie = "rating_filter=" + ratingStr + "; path=/; max-age=31536000";
        this.updateRatingFilterLabels();

        this.setupCustomFilterButtons();
    }

    setupCustomFilterButtons() {
        document.querySelectorAll('.custom-filter-input').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const val = e.target.value;
                if (e.target.checked) {
                    this.selectedCustomFilters.add(val);
                } else {
                    this.selectedCustomFilters.delete(val);
                }
                const filterArray = Array.from(this.selectedCustomFilters);
                this.currentCustomFilter = filterArray.join(' ');
                this.updateCustomFilterLabels();
                localStorage.setItem('selectedCustomFilter', JSON.stringify(filterArray));
                this.onCustomFilterChange();
            });
        });

        // Set initial state - validate whether buttons for selectedCustomFilters exist
        const availableInputs = document.querySelectorAll('.custom-filter-input');
        if (availableInputs.length > 0) {
            const availableValues = new Set(Array.from(availableInputs).map(input => input.value));
            for (const val of Array.from(this.selectedCustomFilters)) {
                if (!availableValues.has(val)) {
                    this.selectedCustomFilters.delete(val);
                }
            }
        }
        const filterArray = Array.from(this.selectedCustomFilters);
        this.currentCustomFilter = filterArray.join(' ');
        localStorage.setItem('selectedCustomFilter', JSON.stringify(filterArray));
        this.updateCustomFilterLabels();
    }

    updateCustomFilterLabels() {
        document.querySelectorAll('.custom-filter-label').forEach(label => {
            label.classList.remove('checked');
        });

        document.querySelectorAll('.custom-filter-input').forEach(checkbox => {
            const isChecked = this.selectedCustomFilters.has(checkbox.value);
            checkbox.checked = isChecked;
            const label = checkbox.nextElementSibling;
            if (label) {
                if (isChecked) {
                    label.classList.add('checked');
                } else {
                    label.classList.remove('checked');
                }
            }
        });
    }

    onCustomFilterChange() {
        this.loadContent();
    }

    updateRatingFilterLabels() {
        document.querySelectorAll('.rating-filter-label').forEach(label => {
            label.classList.remove('checked');
        });

        document.querySelectorAll('.rating-filter-input').forEach(checkbox => {
            const isChecked = this.selectedRatings.has(checkbox.value);
            checkbox.checked = isChecked;
            const label = checkbox.nextElementSibling;
            if (label) {
                if (isChecked) {
                    label.classList.add('checked');
                } else {
                    label.classList.remove('checked');
                }
            }
        });
    }

    onRatingChange() {
        this.loadContent();
    }

    // ==================== Sorting ====================

    setupSorting() {
        if (typeof CustomSelect === 'undefined') {
            console.warn('CustomSelect not loaded');
            return;
        }

        this.sortBySelects = [];
        this.sortOrderToggles = document.querySelectorAll('.js-sort-order-toggle');
        this.sortRandomRegenBtns = document.querySelectorAll('.js-sort-random-regen');

        const sortByElements = document.querySelectorAll('.js-sort-by-select');
        const params = new URLSearchParams(window.location.search);

        sortByElements.forEach(element => {
            const select = new CustomSelect(element);

            if (params.has('sort')) {
                select.setValue(params.get('sort'));
            }

            element.addEventListener('change', (e) => {
                const newValue = e.detail.value;
                this.sortBySelects.forEach(s => {
                    if (s !== select) s.setValue(newValue, false);
                });
                this.handleSortChange(newValue);
            });

            this.sortBySelects.push(select);
        });

        this.sortBySelect = this.sortBySelects[0];

        this.sortOrderToggles.forEach(btn => {
            btn.addEventListener('click', () => this.toggleSortOrder());
        });

        this.sortRandomRegenBtns.forEach(btn => {
            btn.addEventListener('click', () => this.regenerateRandomSeed());
        });

        if (this.currentSort === 'random' && !this.currentRandomSeed) {
            this.currentRandomSeed = String(Date.now());
            this.syncSortUrlParams();
        }

        this.updateSortControlsVisibility();
        this.updateSortOrderToggleState();
        if (this.currentSort === 'random') {
            this.rollSortRandomDice();
        }
    }

    getSortValue() {
        if (this.sortBySelects && this.sortBySelects.length > 0) {
            return this.sortBySelects[0].getValue();
        }
        return this.currentSort;
    }

    getOrderValue() {
        return this.currentOrder;
    }

    handleSortChange(newSort) {
        const previousSort = this.currentSort;
        this.currentSort = newSort;

        if (newSort === 'random') {
            if (previousSort !== 'random' || !this.currentRandomSeed) {
                this.currentRandomSeed = String(Date.now());
            }
            this.rollSortRandomDice();
        } else {
            this.currentRandomSeed = null;
        }

        this.updateSortControlsVisibility();
        this.syncSortUrlParams();
        this.onSortChange();
    }

    toggleSortOrder() {
        if (this.currentSort === 'random') return;

        this.currentOrder = this.currentOrder === 'asc' ? 'desc' : 'asc';
        this.updateSortOrderToggleState();
        this.syncSortUrlParams();
        this.onSortChange();
    }

    regenerateRandomSeed() {
        if (this.currentSort !== 'random') return;

        this.currentRandomSeed = String(Date.now());
        this.rollSortRandomDice();
        this.syncSortUrlParams();
        this.onSortChange();
    }

    rollSortRandomDice() {
        this.sortRandomRegenBtns.forEach(btn => {
            btn.innerHTML = window.Icons.dice();
        });
    }

    updateSortControlsVisibility() {
        const isRandom = this.currentSort === 'random';

        this.sortOrderToggles.forEach(btn => {
            btn.classList.toggle('hidden', isRandom);
            btn.disabled = isRandom;
        });

        this.sortRandomRegenBtns.forEach(btn => {
            btn.classList.toggle('hidden', !isRandom);
        });
    }

    updateSortOrderToggleState() {
        this.sortOrderToggles.forEach(btn => {
            btn.dataset.order = this.currentOrder;
            btn.classList.remove('asc', 'desc');
            btn.classList.add(this.currentOrder);
        });
    }

    syncSortUrlParams() {
        const params = {
            sort: this.currentSort,
            order: this.currentOrder,
            seed: this.currentSort === 'random' ? this.currentRandomSeed : null
        };
        this.updateUrlParams(params);
    }

    appendSortParams(params) {
        const sort = this.getSortValue();
        params.set('sort', sort);
        params.set('order', this.getOrderValue());
        if (sort === 'random' && this.currentRandomSeed) {
            params.set('seed', this.currentRandomSeed);
        }
    }

    onSortChange() {
        this.loadContent();
    }

    addSortOption(value, label) {
        if (this.sortBySelects) {
            this.sortBySelects.forEach(select => select.addOption(value, label));
        }
    }

    removeSortOption(value) {
        if (this.sortBySelects) {
            this.sortBySelects.forEach(select => select.removeOption(value));
        }
    }

    // ==================== Pagination ====================

    adjustPageIfNeeded(totalPages) {
        this.totalPages = Math.max(1, totalPages || 1);

        if (this.currentPage > this.totalPages) {
            this.currentPage = this.totalPages;
            this.updateUrlParams({ page: this.currentPage });
            return true; // Signal that we need to reload
        }
        return false;
    }

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

    async goToPage(page) {
        const pageTop = document.getElementById('main-scroll');
        if (this.isLoading || page < 1 || page > this.totalPages || page === this.currentPage) return;

        this.currentPage = page;
        this.updateUrlParams({ page });
        await this.loadContent();
        if (pageTop && !this.pendingFocus) {
            pageTop.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }

    renderPagination() {
        if (this.pendingFocus) {
            const target = this.pendingFocus;
            this.pendingFocus = null;
            requestAnimationFrame(() => {
                const links = this.getGalleryItemLinks();
                if (links.length > 0) {
                    const el = target === 'last' ? links[links.length - 1] : links[0];
                    el.focus({ preventScroll: true });
                    el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
                }
            });
        }

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

    getGalleryItemLinks() {
        const subAlbumsGrid = document.getElementById('sub-albums-grid');
        const grids = [];
        if (subAlbumsGrid && subAlbumsGrid.children.length > 0 && subAlbumsGrid.style.display !== 'none' && subAlbumsGrid.parentElement?.style.display !== 'none') {
            grids.push(subAlbumsGrid);
        }
        if (this.elements.grid) {
            grids.push(this.elements.grid);
        }
        if (grids.length === 0) return [];

        const rawLinks = [];
        grids.forEach(grid => {
            rawLinks.push(...grid.querySelectorAll('.gallery-item a, .album-card a, a.gallery-item, a.album-card, a.block'));
        });

        const uniqueLinks = [];
        const seen = new Set();
        for (const link of rawLinks) {
            if (link.classList.contains('select-indicator') || link.closest('.select-indicator')) continue;
            if (!seen.has(link)) {
                seen.add(link);
                uniqueLinks.push(link);
            }
        }
        return uniqueLinks;
    }

    getGridRows(links) {
        const rows = [];
        let currentRow = [];
        let currentTop = null;

        links.forEach(link => {
            const el = link.closest('.gallery-item, .album-card') || link;
            const top = el.offsetTop || 0;
            if (currentTop === null || Math.abs(top - currentTop) < 5) {
                currentRow.push(link);
                currentTop = top;
            } else {
                rows.push(currentRow);
                currentRow = [link];
                currentTop = top;
            }
        });
        if (currentRow.length > 0) rows.push(currentRow);
        return rows;
    }

    setupKeybindings() {
        document.addEventListener('keydown', async (e) => {
            const activeEl = document.activeElement;
            const isTyping = activeEl && (
                activeEl.tagName === 'INPUT' ||
                activeEl.tagName === 'TEXTAREA' ||
                activeEl.isContentEditable ||
                activeEl.closest('.modal') ||
                activeEl.closest('#page-jump-modal')
            );
            if (isTyping) return;

            if (!window.keybindings) return;

            let action = null;
            if (window.keybindings.matches(e, 'gallery_nav_up')) action = 'up';
            else if (window.keybindings.matches(e, 'gallery_nav_down')) action = 'down';
            else if (window.keybindings.matches(e, 'gallery_nav_left')) action = 'left';
            else if (window.keybindings.matches(e, 'gallery_nav_right')) action = 'right';

            if (!action) return;

            const links = this.getGalleryItemLinks();
            if (links.length === 0) return;

            e.preventDefault();

            if (this.isLoading) return;

            const currentFocused = document.activeElement;
            const currentIndex = links.findIndex(link => link === currentFocused || link.contains(currentFocused));

            const focusItem = (item) => {
                if (!item) return;
                item.focus({ preventScroll: true });
                item.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
            };

            if (currentIndex === -1) {
                focusItem(links[0]);
                return;
            }

            const rows = this.getGridRows(links);
            const topRow = rows[0] || [];
            const bottomRow = rows[rows.length - 1] || [];

            let currRowIdx = -1;
            let currColIdx = -1;
            for (let r = 0; r < rows.length; r++) {
                const cIdx = rows[r].findIndex(link => link === currentFocused || link.contains(currentFocused));
                if (cIdx !== -1) {
                    currRowIdx = r;
                    currColIdx = cIdx;
                    break;
                }
            }

            if (action === 'left') {
                if (currentIndex === 0) {
                    if (this.currentPage > 1) {
                        this.pendingFocus = 'last';
                        await this.goToPage(this.currentPage - 1);
                    }
                } else {
                    focusItem(links[currentIndex - 1]);
                }
            } else if (action === 'right') {
                if (currentIndex === links.length - 1) {
                    if (this.currentPage < this.totalPages) {
                        this.pendingFocus = 'first';
                        await this.goToPage(this.currentPage + 1);
                    }
                } else {
                    focusItem(links[currentIndex + 1]);
                }
            } else if (action === 'up') {
                if (currRowIdx === 0 || currRowIdx === -1) {
                    if (currentIndex === 0) {
                        if (this.currentPage > 1) {
                            this.pendingFocus = 'last';
                            await this.goToPage(this.currentPage - 1);
                        }
                    } else {
                        focusItem(topRow[0]);
                    }
                } else if (currRowIdx > 0) {
                    const prevRow = rows[currRowIdx - 1];
                    const targetCol = Math.min(currColIdx, prevRow.length - 1);
                    focusItem(prevRow[targetCol]);
                }
            } else if (action === 'down') {
                if (currRowIdx === rows.length - 1) {
                    if (currentIndex === links.length - 1) {
                        if (this.currentPage < this.totalPages) {
                            this.pendingFocus = 'first';
                            await this.goToPage(this.currentPage + 1);
                        }
                    } else {
                        focusItem(bottomRow[bottomRow.length - 1]);
                    }
                } else if (currRowIdx >= 0 && currRowIdx < rows.length - 1) {
                    const nextRow = rows[currRowIdx + 1];
                    const targetCol = Math.min(currColIdx, nextRow.length - 1);
                    focusItem(nextRow[targetCol]);
                }
            }
        });
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

        return `
            <div class="flex flex-wrap justify-center items-center gap-1.5 select-none">
                ${pages.join('')}
            </div>
        `;
    }

    createPageButton(pageNum, isActive) {
        const baseClass = "min-w-[2rem] h-8 px-2 flex items-center justify-center text-xs font-medium transition-all duration-200";

        if (isActive) {
            return `
                <span class="${baseClass} bg-primary border-primary primary-text hover:bg-primary hover:border-primary cursor-default">
                    ${pageNum}
                </span>`;
        }

        return `
            <a href="#" class="page-link ${baseClass} btn-dark text-secondary cursor-pointer" 
               data-page="${pageNum}">
               ${pageNum}
            </a>`;
    }

    createEllipsis() {
        const dotsIcon = window.Icons.dots({ size: 16 });
        return `
            <a href="#" class="page-ellipsis btn-dark min-w-[2rem] h-8 px-2 flex items-center justify-center transition-all duration-200 text-secondary cursor-pointer" 
               title="${window.i18n.t('gallery.jump_to_page')}">
               ${dotsIcon}
            </a>`;
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
        const bulkManageTagsBtn = document.getElementById('bulk-manage-tags-btn');
        const bulkRatingBtn = document.getElementById('bulk-rating-btn');

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
            bulkRatingBtn.addEventListener('click', () => this.bulkChangeRating());
        }
    }

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
    }

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
    }

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
    }

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
    }

    openBulkManageTagsModal() {
        if (!this.bulkManageTagsModal) {
            this.initBulkManageTagsModal();
        }
        if (this.bulkManageTagsModal) {
            this.bulkManageTagsModal.isOpen = true; // Track state
            this.bulkManageTagsModal.show();
        }
    }

    openBulkManualTagEditorModal() {
        if (!this.bulkManualTagEditorModal) {
            this.initBulkManualTagEditorModal();
        }
        if (this.bulkManualTagEditorModal) {
            this.bulkManualTagEditorModal.show(this.selectedItems);
        }
    }

    openBulkAITagsModal() {
        if (!this.bulkAITagsModal) {
            this.initBulkAITagsModal();
        }
        if (this.bulkAITagsModal) {
            this.bulkAITagsModal.show(this.selectedItems);
        }
    }

    openBulkWDTaggerModal() {
        if (!this.bulkWDTaggerModal) {
            this.initBulkWDTaggerModal();
        }
        if (this.bulkWDTaggerModal) {
            this.bulkWDTaggerModal.show(this.selectedItems);
        }
    }

    // New handler for smart Select All
    async handleSelectAll() {
        if (!app.isAdminMode) return;

        const visibleItems = document.querySelectorAll('.gallery-item');
        const visibleIds = Array.from(visibleItems).map(item => parseInt(item.dataset.id));

        // Check if all visible items are already selected
        const isCurrentPageFull = visibleIds.length > 0 && visibleIds.every(id => this.selectedItems.has(id));

        if (!isCurrentPageFull) {
            // Logic 1: Fill the current page
            visibleItems.forEach(item => {
                const id = parseInt(item.dataset.id);
                const checkbox = item.querySelector('.checkbox, .album-item-checkbox');

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
    }

    // New handler for smart Deselect All
    handleDeselectAll() {
        if (!app.isAdminMode) return;

        const visibleItems = document.querySelectorAll('.gallery-item');
        const visibleIds = Array.from(visibleItems).map(item => parseInt(item.dataset.id));

        // Check if all visible items are selected
        const isCurrentPageFull = visibleIds.length > 0 && visibleIds.every(id => this.selectedItems.has(id));

        if (isCurrentPageFull) {
            // Logic 1: Only deselect items on the current page
            visibleItems.forEach(item => {
                const id = parseInt(item.dataset.id);
                this.selectedItems.delete(id);
                item.classList.remove('selected');
                const checkbox = item.querySelector('.checkbox, .album-item-checkbox');
                if (checkbox) checkbox.checked = false;
            });
        } else {
            // Logic 2: Clear EVERYTHING (global deselect)
            this.clearSelection();
        }
        this.updateBulkActionsUI();
    }

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
            params.set('limit', '100000'); // Fetch "all" (reasonable limit)
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
            document.querySelectorAll('.gallery-item').forEach(item => {
                const id = parseInt(item.dataset.id);
                if (this.selectedItems.has(id)) {
                    item.classList.add('selected');
                    const checkbox = item.querySelector('.checkbox, .album-item-checkbox');
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

        this.updateSelectionModeClass();
    }

    selectAll() {
        document.querySelectorAll('.gallery-item').forEach(item => {
            const id = parseInt(item.dataset.id);
            const checkbox = item.querySelector('.select-checkbox');

            if (!this.selectedItems.has(id)) {
                this.selectedItems.add(id);
                item.classList.add('selected');
                if (checkbox) checkbox.checked = true;
            }
        });
        this.updateBulkActionsUI();
    }

    clearSelection() {
        this.selectedItems.clear();
        document.querySelectorAll('.gallery-item').forEach(item => {
            item.classList.remove('selected');
            const checkbox = item.querySelector('.select-checkbox');
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
    }

    // ==================== Drag & Shift Selection ====================

    handleMouseDown(item, id) {
        if (!app.isAdminMode) return;
        if (!this.isSelectionMode) return;
        this.dragStartItem = item;
        this.selectionSnapshot = new Set(this.selectedItems);
        this.isDragging = false;
        this.suppressClick = false;
    }

    startDrag() {
        this.isDragging = true;
        this.suppressClick = true;

        // Calculate target state based on start item
        const id = parseInt(this.dragStartItem.dataset.id);
        const wasSelected = this.selectionSnapshot.has(id);
        this.dragTargetState = !wasSelected;
        this.lastSelectedId = id;

        // Immediately apply to start item
        this.applySelectionState(id, this.dragTargetState);
        this.updateBulkActionsUI();
    }

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
    }

    handleDragEnd() {
        this.isDragging = false;
        this.dragStartItem = null;
        this.selectionSnapshot = null;
        this.dragTargetState = null;
        this.updateSelectionModeClass();

        setTimeout(() => {
            this.suppressClick = false;
        }, 50);
    }

    updateVisibleSelectionState() {
        document.querySelectorAll('.gallery-item').forEach(item => {
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
    }

    applySelectionState(id, isSelected) {
        const item = document.querySelector(`.gallery-item[data-id="${id}"]`);

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
    }

    getRange(itemA, itemB) {
        const allItems = Array.from(document.querySelectorAll('.gallery-item'));
        const indexA = allItems.indexOf(itemA);
        const indexB = allItems.indexOf(itemB);

        if (indexA === -1 || indexB === -1) return [];

        const start = Math.min(indexA, indexB);
        const end = Math.max(indexA, indexB);

        return allItems.slice(start, end + 1).map(el => parseInt(el.dataset.id));
    }

    getRangeFromLast(currentId) {
        if (!this.lastSelectedId) return [currentId];

        const itemA = document.querySelector(`.gallery-item[data-id="${this.lastSelectedId}"]`);
        const itemB = document.querySelector(`.gallery-item[data-id="${currentId}"]`);

        if (!itemA || !itemB) return [currentId];

        return this.getRange(itemA, itemB);
    }

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
    }

    async bulkRemove() {
        // Override in subclass if needed
    }

    bulkChangeRating() {
        const itemCount = this.selectedItems.size;
        if (itemCount === 0) return;

        if (typeof BulkRatingModal === 'undefined') {
            console.warn('BulkRatingModal not loaded');
            return;
        }

        if (!this.bulkRatingModal) {
            this.bulkRatingModal = new BulkRatingModal({
                onSave: () => {
                    this.clearSelection();
                    this.loadContent();
                }
            });
        }

        this.bulkRatingModal.show(this.selectedItems);
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
                .slice(0, this.popularTagsLimit || 20);
        }

        if (sortedTags.length === 0) {
            this.elements.popularTags.innerHTML = `<p class="text-secondary">${window.i18n.t('gallery.no_tags_found')}</p>`;
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
                    <a href="/?${params.toString()}" class="popular-tag-name tag ${data.category || 'general'} tag-text" 
                       ${isInQuery ? 'style="pointer-events: none;"' : ''}>
                        ${tagName}
                        <span class="popular-tag-count">${data.count}</span>
                    </a>
                </div>
            `;
        }).join('');
    }

    // ==================== Related Tags / Tags Section ====================

    async refreshTagsSection() {
        const urlParams = new URLSearchParams(window.location.search);
        const searchQuery = (urlParams.get('q') || '').trim();
        const useRelated = (this.popularTagsMode === 'search_related') && searchQuery !== '';

        // Update the section title dynamically
        const titleEl = document.getElementById('popular-tags-title');
        if (titleEl) {
            titleEl.textContent = useRelated
                ? window.i18n.t('gallery.related_tags')
                : window.i18n.t('gallery.popular_tags');
        }

        if (useRelated) {
            await this._fetchRelatedTags(searchQuery);
        } else {
            this.renderPopularTags();
        }
    }

    async _fetchRelatedTags(query) {
        if (!this.elements.popularTags) return;

        this.elements.popularTags.innerHTML =
            `<p class="text-secondary">${window.i18n.t('common.loading')}</p>`;

        try {
            const params = new URLSearchParams({
                q: query,
                limit: this.popularTagsLimit || 20,
            });
            if (this.currentRating) {
                params.set('rating', this.currentRating);
            }
            if (this.selectedCustomFilters && this.selectedCustomFilters.size > 0) {
                this.selectedCustomFilters.forEach(cf => params.append('custom_filter', cf));
            }
            const res = await fetch(`/api/tags/search-related?${params.toString()}`, {
                credentials: 'include'
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.renderPopularTags(data);
        } catch (err) {
            console.error('Error fetching related tags:', err);
            // Fallback to current-page tags
            this.renderPopularTags();
        }
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

    // ==================== Selection Mode Helpers ====================

    get isSelectionMode() {
        return this.selectedItems.size > 0;
    }

    updateSelectionModeClass() {
        // Add/remove class on the grid container for CSS styling
        if (this.elements.grid) {
            this.elements.grid.classList.toggle('selection-mode', this.isSelectionMode);
        }
    }

    toggleItemSelection(item, mediaId, event = null) {
        if (this.suppressClick) return;

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
    }

    // ==================== Gallery Item Creation ====================

    createGalleryItem(media, options = {}) {
        const {
            checkboxClass = 'checkbox',
            preserveQueryParams = true,
            linkUrl = null
        } = options;

        const item = document.createElement('div');
        item.className = `gallery-item ${media.file_type}`;
        if (media.parent_id) item.classList.add('child-item');
        if (media.has_children) item.classList.add('parent-item');
        item.dataset.id = media.id;
        item.dataset.rating = media.rating;

        // Hidden checkbox
        let checkbox = null;
        let indicator = null;

        if (app.isAdminMode) {
            checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = `select-checkbox ${checkboxClass}`;
            checkbox.dataset.id = media.id;
            checkbox.tabIndex = -1; // Not focusable

            // Custom visual indicator (the clickable circle)
            indicator = document.createElement('div');
            indicator.className = 'select-indicator primary-text';
            indicator.innerHTML = window.Icons.check({ size: 24 });

            if (this.selectedItems.has(media.id)) {
                checkbox.checked = true;
                item.classList.add('selected');
            }

            indicator.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggleItemSelection(item, media.id, e);
            });
        }

        // ==================== Drag Selection Events ====================

        // Start drag on mousedown
        if (app.isAdminMode) {
            item.addEventListener('mousedown', (e) => {
                if (e.button === 0) {
                    if (this.isSelectionMode) {
                        e.preventDefault();
                        this.handleMouseDown(item, media.id);
                    }
                }
            });
        }

        // Continue drag on mouseenter
        item.addEventListener('mouseenter', (e) => {
            if (this.dragStartItem) {
                this.handleDragEnter(item, media.id);
            }
        });

        // Image
        const img = document.createElement('img');
        img.classList.add('transition-colors');
        img.alt = media.filename;
        img.loading = 'lazy';
        img.draggable = false;

        const markLoaded = () => {
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    img.classList.add('loaded');
                });
            });
        };

        img.onload = () => {
            if (img.decode) {
                img.decode().then(markLoaded).catch(markLoaded);
            } else {
                markLoaded();
            }
        };

        img.onerror = () => {
            img.classList.add('loaded');
            img.src = '/static/images/no-thumbnail.png';
        };

        img.src = `/api/media/${media.id}/thumbnail${media.hash ? '?v=' + media.hash : ''}`;

        if (img.complete && img.naturalWidth > 0) {
            markLoaded();
        }

        // Link
        const link = document.createElement('a');
        const basePath = linkUrl || `/media/${media.id}`;
        if (preserveQueryParams) {
            const params = new URLSearchParams(window.location.search);
            const queryString = params.toString();
            link.href = `${basePath}${queryString ? '?' + queryString : ''}`;
        } else {
            link.href = basePath;
        }
        link.appendChild(img);

        link.addEventListener('click', (e) => {
            if (app.isAdminMode && this.isSelectionMode) {
                e.preventDefault();
                this.toggleItemSelection(item, media.id, e);
            }
        });

        // ==================== Long Press for Mobile ====================
        let longPressTimer = null;
        let longPressTriggered = false;
        const LONG_PRESS_DURATION = 350; // ms

        const startLongPress = (e) => {
            longPressTriggered = false;
            item.classList.add('long-pressing');

            longPressTimer = setTimeout(() => {
                longPressTriggered = true;
                item.classList.remove('long-pressing');
                this.toggleItemSelection(item, media.id);

                if (navigator.vibrate) {
                    navigator.vibrate(50);
                }
            }, LONG_PRESS_DURATION);
        };

        const cancelLongPress = () => {
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
            item.classList.remove('long-pressing');
        };

        const endLongPress = (e) => {
            cancelLongPress();

            if (longPressTriggered) {
                e.preventDefault();
                e.stopPropagation();
                longPressTriggered = false;
            }
        };

        if (app.isAdminMode) {
            item.addEventListener('touchstart', startLongPress, { passive: true });
            item.addEventListener('touchend', endLongPress);
            item.addEventListener('touchcancel', cancelLongPress);
            item.addEventListener('touchmove', cancelLongPress, { passive: true });

            item.addEventListener('contextmenu', (e) => {
                if (longPressTriggered) {
                    e.preventDefault();
                }
            });
        }

        // Tooltip
        if (this.tooltipHelper && media.tags && media.tags.length > 0) {
            const isPrimaryTouch = window.matchMedia('(pointer: coarse)').matches;

            if (!isPrimaryTouch) {
                this.tooltipHelper.addToElement(item, media.tags);
            }
        }

        if (checkbox) item.appendChild(checkbox);
        if (indicator) item.appendChild(indicator);
        item.appendChild(link);

        if (media.is_shared) {
            const shareIcon = document.createElement('div');
            shareIcon.className = 'share-icon w-6 h-6 flex items-center justify-center p-0';
            shareIcon.innerHTML = window.Icons.share({ size: 12 });
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
            <div class="bg-danger tag-text p-4 my-4">
                <strong>${window.i18n.t('gallery.error_label')}</strong> ${message}
                <br><small>${window.i18n.t('gallery.check_console')}</small>
            </div>
        `;
        this.elements.grid.appendChild(errorDiv);
    }

    showEmptyState(message = window.i18n.t('common.no_items_found')) {
        if (!this.elements.grid) return;

        this.elements.grid.innerHTML = `
            <div class="col-span-full text-center py-16 text-secondary">
                <h2 class="text-lg mb-2">${message}</h2>
                ${app.isAuthenticated ? `<a href="/admin" class="btn mt-4 inline-block cursor-pointer">${window.i18n.t('gallery.go_to_admin')}</a>` : ''}
            </div>
        `;
    }

    // ==================== Abstract Methods ====================

    async loadContent() {
        throw new Error('loadContent must be implemented by subclass');
    }
}
