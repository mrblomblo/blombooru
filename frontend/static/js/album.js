class AlbumViewer extends BaseGallery {
    constructor(albumId) {
        super({
            gridSelector: '#album-contents',
            defaultSort: 'uploaded_at',
            enablePagination: true
        });

        this.albumId = albumId;
        this.album = null;
        this.hasSubAlbums = false;
        this.init();
    }

    async init() {
        this.initCommon();

        // Get page from URL
        this.currentPage = parseInt(this.getUrlParam('page', '1'));

        await this.loadAlbum();
        await this.loadContent();
        await this.loadPopularTagsFromAPI();
    }

    async loadAlbum() {
        try {
            const response = await fetch(`/api/albums/${this.albumId}`);
            if (!response.ok) throw new Error(window.i18n.t('albums.not_found'));

            this.album = await response.json();
            document.getElementById('album-name').textContent = this.album.name;
            await this.loadBreadcrumb();
            this.updateDetails();
        } catch (error) {
            console.error('Error loading album:', error);
            document.getElementById('album-name').textContent = window.i18n.t('albums.error_loading');
        }
    }

    async loadBreadcrumb() {
        try {
            const response = await fetch(`/api/albums/${this.albumId}/parents`);
            const data = await response.json();

            const breadcrumbEl = document.getElementById('album-breadcrumb');
            if (data.parents && data.parents.length > 0) {
                const crumbs = data.parents.map(p =>
                    `<a href="/album/${p.id}" class="hover:text-primary">${p.name}</a>`
                ).join(' > ');
                breadcrumbEl.innerHTML = `${crumbs} > ${this.album.name}`;
            } else {
                breadcrumbEl.textContent = window.i18n.t('albums.root_album');
            }
        } catch (error) {
            console.error('Error loading breadcrumb:', error);
        }
    }

    updateDetails() {
        const detailsEl = document.getElementById('album-details');
        if (!detailsEl || !this.album) return;

        detailsEl.innerHTML = `
            <div class="mb-2"><strong>${window.i18n.t('albums.media_count')}</strong> ${this.album.media_count || 0}</div>
            <div class="mb-2"><strong>${window.i18n.t('albums.sub_albums_count')}</strong> ${this.album.children_count || 0}</div>
            <div class="mb-2"><strong>${window.i18n.t('albums.rating')}</strong> ${this.album.rating}</div>
            <div class="mb-2"><strong>${window.i18n.t('albums.created')}</strong> ${new Date(this.album.created_at).toLocaleDateString()}</div>
            <div class="mb-2"><strong>${window.i18n.t('albums.last_modified')}</strong> ${new Date(this.album.last_modified).toLocaleDateString()}</div>
        `;
    }

    async loadContent() {
        this.showLoading();

        try {
            const params = new URLSearchParams({
                page: this.currentPage,
                rating: this.currentRating,
                sort: this.getSortValue(),
                order: this.getOrderValue()
            });

            if (this.currentCustomFilter) {
                params.set('q', this.currentCustomFilter);
            }

            const response = await fetch(`/api/albums/${this.albumId}/contents?${params}`);
            if (!response.ok) throw new Error(window.i18n.t('albums.failed_load_contents'));

            const data = await response.json();

            // Check if page adjustment is needed
            if (this.adjustPageIfNeeded(data.pages)) {
                return this.loadContent();
            }

            // Filter out empty albums for logic checks
            const allAlbums = data.albums || [];
            // An album is "visible" if it has media OR it has sub-albums
            const visibleAlbums = allAlbums.filter(a => (a.media_count > 0 || a.children_count > 0));

            // Check if there are visible sub-albums and update sort options
            const hadSubAlbums = this.hasSubAlbums;
            this.hasSubAlbums = visibleAlbums.length > 0;

            if (this.hasSubAlbums && !hadSubAlbums) {
                this.addSortOption('last_modified', 'Last Modified');
            } else if (!this.hasSubAlbums && hadSubAlbums) {
                this.removeSortOption('last_modified');
            }

            this.renderContents(data);

            // Render pagination
            this.renderPagination();

        } catch (error) {
            console.error('Error loading contents:', error);
            this.showError(window.i18n.t('albums.failed_load_album_contents'));
        } finally {
            this.hideLoading();
        }
    }

    async loadPopularTagsFromAPI() {
        try {
            const response = await fetch(`/api/albums/${this.albumId}/tags?limit=20`);
            const data = await response.json();

            if (data.tags && data.tags.length > 0) {
                this.renderPopularTags(data.tags);
            } else {
                this.elements.popularTags.innerHTML = `<p class="text-secondary">${window.i18n.t('albums.no_tags_found')}</p>`;
            }
        } catch (error) {
            console.error('Error loading popular tags:', error);
        }
    }

    onRatingChange() {
        this.loadContent();
        this.loadPopularTagsFromAPI();
    }

    onSortChange() {
        this.currentSort = this.getSortValue();
        this.currentOrder = this.getOrderValue();
        this.updateUrlParams({ sort: this.currentSort, order: this.currentOrder });
        this.loadContent();
    }

    renderContents(data) {
        const subAlbumsContainer = document.getElementById('sub-albums-container');
        const subAlbumsGrid = document.getElementById('sub-albums-grid');
        const mediaContainer = document.getElementById('media-container');
        const subAlbumsHeader = document.getElementById('sub-albums-title');
        const mediaHeader = document.getElementById('media-title');

        if (!subAlbumsGrid || !this.elements.grid) return;

        subAlbumsGrid.innerHTML = '';
        this.elements.grid.innerHTML = '';

        // 1. Process Sub-albums (only show on first page)
        const allAlbums = data.albums || [];
        const visibleAlbums = allAlbums.filter(a => (a.media_count > 0 || a.children_count > 0));
        const emptyCount = allAlbums.length - visibleAlbums.length;

        // Only show sub-albums on first page
        if (this.currentPage === 1 && visibleAlbums.length > 0) {
            subAlbumsContainer.style.display = 'block';
            subAlbumsGrid.innerHTML = visibleAlbums.map(album => this.createAlbumCard(album)).join('');

            if (subAlbumsHeader) {
                if (emptyCount > 0) {
                    subAlbumsHeader.innerHTML = window.i18n.t('albums.sub_albums_with_empty', { count: emptyCount });
                } else {
                    subAlbumsHeader.textContent = window.i18n.t('albums.sub_albums');
                }
            }
        } else {
            subAlbumsContainer.style.display = 'none';
        }

        // 2. Render Media
        if (data.media && data.media.length > 0) {
            mediaContainer.style.display = 'block';

            if (mediaHeader) {
                mediaHeader.style.display = (this.currentPage === 1 && visibleAlbums.length > 0) ? 'block' : 'none';
            }

            data.media.forEach(media => {
                const item = this.createGalleryItem(media, {
                    checkboxClass: 'album-item-checkbox checkbox',
                    preserveQueryParams: false
                });
                this.elements.grid.appendChild(item);
            });
        } else {
            mediaContainer.style.display = 'none';
            if (subAlbumsHeader) {
                subAlbumsHeader.style.display = 'none';
            }
        }

        // 3. Empty State (No visible albums AND no media)
        if (visibleAlbums.length === 0 && (!data.media || data.media.length === 0)) {
            mediaContainer.style.display = 'block';
            if (emptyCount > 0 && this.currentPage === 1) {
                this.elements.grid.innerHTML = `<p class="text-secondary col-span-full text-center py-8">${window.i18n.t('albums.only_empty_subalbums')}</p>`;
            } else if (this.currentPage > 1) {
                this.elements.grid.innerHTML = `<p class="text-secondary col-span-full text-center py-8">${window.i18n.t('albums.no_more_items')}</p>`;
            } else {
                this.elements.grid.innerHTML = `<p class="text-secondary col-span-full text-center py-8">${window.i18n.t('albums.empty_album')}</p>`;
            }
        }
    }

    createAlbumCard(album) {
        const thumbnails = album.thumbnail_paths || [];
        let thumbnailHTML;

        if (thumbnails.length >= 4) {
            thumbnailHTML = `
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
            thumbnailHTML = `
                <div class="aspect-square overflow-hidden">
                    <img src="${thumbnails[0]}" class="w-full h-full object-cover" loading="lazy" 
                         onerror="this.src='/static/images/no-thumbnail.png'">
                </div>
            `;
        } else {
            thumbnailHTML = `
                <div class="aspect-square surface-light flex items-center justify-center">
                    <img src="/static/images/no-thumbnail.png" class="w-full h-full object-cover" loading="lazy">
                </div>
            `;
        }

        return `
            <a href="/album/${album.id}" class="block surface border hover:border-primary transition-colors">
                ${thumbnailHTML}
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

    async bulkRemove() {
        const itemCount = this.selectedItems.size;
        if (itemCount === 0) return;

        const modal = new ModalHelper({
            id: 'bulk-remove-modal',
            type: 'warning',
            title: window.i18n.t('modal.bulk_remove_from_album.title'),
            message: window.i18n.t('modal.bulk_remove_from_album.message', { count: itemCount }),
            confirmText: window.i18n.t('modal.bulk_remove_from_album.confirm'),
            cancelText: window.i18n.t('modal.buttons.cancel'),
            onConfirm: async () => {
                try {
                    const mediaIds = Array.from(this.selectedItems);
                    await app.apiCall(`/api/albums/${this.albumId}/media`, {
                        method: 'DELETE',
                        body: JSON.stringify({ media_ids: mediaIds })
                    });

                    app.showNotification(window.i18n.t('albums.removed_items_success', { count: itemCount }), 'success');
                    this.clearSelection();
                    this.loadContent();
                    this.loadAlbum();
                } catch (error) {
                    app.showNotification(error.message, 'error', window.i18n.t('notifications.media.error_removing_from_album'));
                }
            }
        });

        modal.show();
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const contentsEl = document.getElementById('album-contents');
    if (contentsEl?.dataset.albumId) {
        window.albumViewer = new AlbumViewer(contentsEl.dataset.albumId);
    }
});
