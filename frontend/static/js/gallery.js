class Gallery extends BaseGallery {
    constructor() {
        super({
            gridSelector: '#gallery-grid',
            defaultSort: 'uploaded_at'
        });

        if (this.elements.grid) {
            this.init();
        }
    }

    init() {
        this.initCommon();

        // Get page from URL
        this.currentPage = parseInt(this.getUrlParam('page', 1));

        this.loadContent();
    }

    async loadContent() {
        if (this.isLoading) return;

        this.isLoading = true;
        this.showLoading();

        // Clear gallery for new page
        this.elements.grid.innerHTML = '';
        this.tagCounts.clear();

        try {
            // Construct params explicitly to ensure clean API call
            const apiParams = new URLSearchParams();

            // 1. Basic pagination and filters
            apiParams.set('page', this.currentPage);
            apiParams.set('rating', this.currentRating);
            apiParams.set('sort', this.getSortValue());
            apiParams.set('order', this.getOrderValue());

            // 2. Handle Search vs Browse
            const urlParams = new URLSearchParams(window.location.search);
            const searchQuery = urlParams.get('q');

            let endpoint = '/api/media/';

            // Combine URL search query with custom filter
            let combinedQuery = '';
            if (searchQuery) combinedQuery = searchQuery;
            if (this.currentCustomFilter) {
                combinedQuery = combinedQuery ? `${combinedQuery} ${this.currentCustomFilter}` : this.currentCustomFilter;
            }

            if (combinedQuery) {
                endpoint = '/api/search';
                apiParams.set('q', combinedQuery);
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

            if (data.items && data.items.length > 0) {
                this.processTagCounts(data.items);
                this.renderItems(data.items);
                this.renderPopularTags();
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
