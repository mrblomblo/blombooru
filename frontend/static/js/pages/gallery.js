class Gallery extends BaseGallery {
    constructor() {
        super({
            gridSelector: '#gallery-grid'
        });

        if (this.elements.grid) {
            this.init();
        }
    }

    init() {
        this.initCommon();

        // Read popular tags settings from server-injected data attributes
        this.popularTagsMode = this.elements.grid?.dataset.popularTagsMode || 'current_page';
        this.popularTagsLimit = parseInt(this.elements.grid?.dataset.popularTagsLimit || '20', 10);

        // Get page from URL
        this.currentPage = parseInt(this.getUrlParam('page', 1));

        this.loadContent();
    }

    async loadContent() {
        if (this.isLoading) return;

        this.isLoading = true;
        this.showLoading();

        // Clear gallery for new page
        this.unloadAllGifs();
        this.elements.grid.innerHTML = '';
        this.tagCounts.clear();

        try {
            // Construct params explicitly to ensure clean API call
            const apiParams = new URLSearchParams();

            // 1. Basic pagination and filters
            apiParams.set('page', this.currentPage);
            if (this.currentRating) {
                apiParams.set('rating', this.currentRating);
            }
            this.appendSortParams(apiParams);

            // 2. Handle Search vs Browse
            const urlParams = new URLSearchParams(window.location.search);
            const searchQuery = urlParams.get('q');

            let endpoint = '/api/media/';

            if (searchQuery) {
                endpoint = '/api/search';
                apiParams.set('q', searchQuery);
            }

            if (this.selectedCustomFilters && this.selectedCustomFilters.size > 0) {
                this.selectedCustomFilters.forEach(cf => apiParams.append('custom_filter', cf));
            }

            console.log('Loading gallery:', endpoint, apiParams.toString());

            const response = await fetch(`${endpoint}?${apiParams.toString()}`, {
                credentials: 'include'
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            const data = await response.json();
            this.totalPages = data.pages || 1;

            if (data.query !== undefined && searchQuery) {
                const searchInput = document.getElementById('search-input');
                const searchInputMobile = document.getElementById('search-input-mobile');
                if (searchInput && document.activeElement !== searchInput) searchInput.value = data.query;
                if (searchInputMobile && document.activeElement !== searchInputMobile) searchInputMobile.value = data.query;
            }

            if (data.items && data.items.length > 0) {
                this.processTagCounts(data.items);
                this.renderItems(data.items);
                await this.refreshTagsSection();
                this.renderPagination();
            } else if (this.currentPage === 1) {
                this.showEmptyState(searchQuery ? window.i18n.t('gallery.no_results_found') : window.i18n.t('gallery.no_media_found'));
            }

        } catch (error) {
            console.error('Error loading gallery:', error);
            this.showError(error.message);
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }

    renderItems(items) {
        items.forEach(item => {
            const element = this.createGalleryItem(item);
            this.elements.grid.appendChild(element);
        });
    }
}

// Initialize
if (document.getElementById('gallery-grid')) {
    window.gallery = new Gallery();
}
