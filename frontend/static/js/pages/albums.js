class AlbumsOverview extends BaseGallery {
    constructor() {
        super({
            gridSelector: '#albums-grid',
            defaultSort: 'uploaded_at',
            enableTooltips: false
        });

        if (this.elements.grid) {
            this.init();
        }
    }

    async init() {
        this.initCommon();
        this.currentPage = parseInt(this.getUrlParam('page', 1));
        this.addSortOption('last_modified', window.i18n.t('albums.sort_last_modified'));

        this.setupManualReorder();
        await this.loadContent();
    }


    async loadContent() {
        if (this.isLoading) return;

        this.isLoading = true;
        this.showLoading();

        try {
            const params = new URLSearchParams({
                page: this.currentPage,
                root_only: 'true'
            });
            if (this.currentRating) {
                params.set('rating', this.currentRating);
            }
            if (this.selectedCustomFilters && this.selectedCustomFilters.size > 0) {
                this.selectedCustomFilters.forEach(cf => params.append('custom_filter', cf));
            }
            this.appendSortParams(params);

            const response = await fetch(`/api/albums?${params}`);
            if (!response.ok) throw new Error(window.i18n.t('albums.failed_load_list'));

            const data = await response.json();
            this.totalPages = data.pages || 1;

            if (this.adjustPageIfNeeded(data.pages)) {
                this.isLoading = false;
                return await this.loadContent();
            }

            // Filter empty albums before rendering
            const rawItems = data.items || [];
            const visibleItems = rawItems.filter(album =>
                (album.media_count > 0 || album.children_count > 0)
            );

            this.renderAlbums(visibleItems, data.unfiltered_total);
            this.renderPagination();
        } catch (error) {
            console.error('Error loading albums:', error);
            this.showError(window.i18n.t('albums.failed_load_list'));
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }

    renderAlbums(albums, unfilteredTotal = 0) {
        if (!this.elements.grid) return;

        if (albums.length === 0) {
            if (unfilteredTotal > 0) {
                const msg = unfilteredTotal === 1
                    ? window.i18n.t('albums.album_hidden_by_filters')
                    : window.i18n.t('albums.albums_hidden_by_filters', { count: unfilteredTotal });
                this.showEmptyState(msg);
            } else {
                this.showEmptyState(window.i18n.t('albums.no_visible_albums'));
            }
            return;
        }

        this.elements.grid.innerHTML = albums.map(album => this.createAlbumCard(album)).join('');
    }

    setupManualReorder() {
        if (typeof ManualReorder === 'undefined') return;

        this.initManualReorder({
            grid: this.elements.grid,
            itemSelector: '.album-card',
            idExtractor: (el) => parseInt(el.dataset.id || el.href.split('/album/')[1]),
            saveEndpoint: '/api/albums/reorder',
            savePayloadKey: 'album_ids',
            fetchChunk: async (page, limit) => {
                const params = new URLSearchParams({
                    root_only: 'true',
                    page
                });
                if (limit) params.set('limit', limit);
                if (this.currentRating) params.set('rating', this.currentRating);
                if (this.selectedCustomFilters && this.selectedCustomFilters.size > 0) {
                    this.selectedCustomFilters.forEach(cf => params.append('custom_filter', cf));
                }
                this.appendSortParams(params);
                const res = await fetch(`/api/albums?${params}`);
                if (!res.ok) return null;
                const data = await res.json();
                const items = data.items || [];
                if (page === 1) this.elements.grid.innerHTML = '';
                const newIds = [];
                items.forEach(album => {
                    const temp = document.createElement('div');
                    temp.innerHTML = this.createAlbumCard(album).trim();
                    this.elements.grid.appendChild(temp.firstChild);
                    newIds.push(album.id);
                });
                return {
                    newIds,
                    total: data.total || 0,
                    totalPages: data.pages || 1,
                    limit: data.limit
                };
            }
        });
    }
}

// Initialize
if (document.getElementById('albums-grid')) {
    window.albumsOverview = new AlbumsOverview();
}
