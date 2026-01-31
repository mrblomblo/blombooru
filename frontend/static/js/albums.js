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

        await this.loadContent();
    }


    async loadContent() {
        if (this.isLoading) return;

        this.isLoading = true;
        this.showLoading();

        try {
            const params = new URLSearchParams({
                page: this.currentPage,
                sort: this.getSortValue(),
                order: this.getOrderValue(),
                root_only: 'true',
                rating: this.currentRating
            });

            const response = await fetch(`/api/albums?${params}`);
            if (!response.ok) throw new Error(window.i18n.t('albums.failed_load_list'));

            const data = await response.json();
            this.totalPages = data.pages || 1;

            // Filter empty albums before rendering
            const rawItems = data.items || [];
            const visibleItems = rawItems.filter(album =>
                (album.media_count > 0 || album.children_count > 0)
            );

            this.renderAlbums(visibleItems);
            this.renderPagination();
        } catch (error) {
            console.error('Error loading albums:', error);
            this.showError(window.i18n.t('albums.failed_load_list'));
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }

    renderAlbums(albums) {
        if (!this.elements.grid) return;

        if (albums.length === 0) {
            this.showEmptyState(window.i18n.t('albums.no_visible_albums'));
            return;
        }

        this.elements.grid.innerHTML = albums.map(album => this.createAlbumCard(album)).join('');
    }

    createAlbumCard(album) {
        const thumbnails = album.thumbnail_paths || [];
        let collageHTML;

        if (thumbnails.length >= 4) {
            collageHTML = `
                <div class="grid grid-cols-2 gap-0.5 aspect-square overflow-hidden">
                    ${thumbnails.slice(0, 4).map(thumb => `
                        <div class="relative overflow-hidden">
                            <img src="${thumb}" class="w-full h-full object-cover" loading="lazy"
                                 onerror="this.src='/static/images/no-thumbnail.png'">
                        </div>
                    `).join('')}
                </div>
            `;
        } else if (thumbnails.length > 0) {
            collageHTML = `
                <div class="aspect-square overflow-hidden">
                    <img src="${thumbnails[0]}" class="w-full h-full object-cover" loading="lazy"
                         onerror="this.src='/static/images/no-thumbnail.png'">
                </div>
            `;
        } else {
            collageHTML = `
                <div class="aspect-square bg-surface-light flex items-center justify-center">
                    <img src="/static/images/no-thumbnail.png" class="w-full h-full object-cover" loading="lazy">
                </div>
            `;
        }

        return `
            <a href="/album/${album.id}" class="block surface border hover:border-primary transition-colors">
                ${collageHTML}
                <div class="p-2 border-t">
                    <div class="text-xs font-bold truncate mb-1">${album.name}</div>
                    <div class="flex justify-between items-center text-xs text-secondary">
                        <span>${window.i18n.t('albums.items_count', { count: album.media_count || 0 })}</span>
                        <span>${album.rating[0].toUpperCase()}</span>
                    </div>
                </div>
            </a>
        `;
    }
}

// Initialize
if (document.getElementById('albums-grid')) {
    window.albumsOverview = new AlbumsOverview();
}
