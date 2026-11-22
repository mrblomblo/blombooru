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
            itemSelector: '.gallery-item',
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
        this.savedRandomSeed = null;
        this.loadedGifs = new Set();

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
        const cookieRating = window.getCookie('rating_filter');

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
        this.savedRandomSeed = this.currentRandomSeed;

        const urlFallbackSort = urlParams.get('fallback_sort');
        const urlFallbackOrder = urlParams.get('fallback_order');
        if (this.currentSort !== 'manual') {
            this.lastNonManualSort = this.currentSort;
            this.lastNonManualOrder = this.currentOrder;
        } else {
            this.lastNonManualSort = urlFallbackSort || this.options.defaultSort || 'uploaded_at';
            this.lastNonManualOrder = urlFallbackOrder || defaultOrderFromDom || this.options.defaultOrder || 'desc';
        }
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

    initManualReorder(options = {}) {
        if (typeof ManualReorder === 'undefined') return null;

        const defaultCallbacks = {
            onActivate: () => {
                this.freezeFiltersForReorder();
                if (typeof options.onActivate === 'function') options.onActivate();
            },
            onSaveSuccess: () => {
                this.currentSort = 'manual';
                this.currentOrder = 'asc';
                this.syncSortUrlParams();
                this.updateSortControlsVisibility();
                if (this.restoreFiltersAfterReorder()) {
                    this.loadContent();
                }
                if (typeof options.onSaveSuccess === 'function') options.onSaveSuccess();
            },
            onClearSuccess: () => {
                this.restoreFiltersAfterReorder();
                this.loadContent();
                if (typeof options.onClearSuccess === 'function') options.onClearSuccess();
            },
            onCancel: () => {
                if (this.restoreFiltersAfterReorder()) {
                    this.loadContent();
                }
                if (typeof options.onCancel === 'function') options.onCancel();
            }
        };

        this.manualReorder = new ManualReorder({
            ...options,
            ...defaultCallbacks
        });

        document.querySelectorAll('.js-sort-edit-order').forEach(btn => {
            btn.addEventListener('click', () => {
                this.manualReorder.activate();
            });
        });

        return this.manualReorder;
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

    // ==================== GIF Preview Helpers ====================

    unloadAllGifs() {
        if (window.unloadAllGifs) {
            window.unloadAllGifs(this.loadedGifs, this.elements.grid);
        }
    }

    // ==================== Abstract Methods ====================

    async loadContent() {
        throw new Error('loadContent must be implemented by subclass');
    }
}
