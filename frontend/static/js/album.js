class AlbumViewer extends BaseGallery {
    constructor(albumId) {
        super({
            gridSelector: '#album-contents',
            defaultSort: 'uploaded_at',
            enablePagination: false
        });

        this.albumId = albumId;
        this.album = null;
        this.hasSubAlbums = false;
        this.init();
    }

    async init() {
        this.initCommon();
        await this.loadAlbum();
        await this.loadContent();
        await this.loadPopularTagsFromAPI();
    }

    async loadAlbum() {
        try {
            const response = await fetch(`/api/albums/${this.albumId}`);
            if (!response.ok) throw new Error('Album not found');

            this.album = await response.json();
            document.getElementById('album-name').textContent = this.album.name;
            await this.loadBreadcrumb();
            this.updateDetails();
        } catch (error) {
            console.error('Error loading album:', error);
            document.getElementById('album-name').textContent = 'Error loading album';
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
                breadcrumbEl.textContent = 'Root Album';
            }
        } catch (error) {
            console.error('Error loading breadcrumb:', error);
        }
    }

    updateDetails() {
        const detailsEl = document.getElementById('album-details');
        if (!detailsEl || !this.album) return;

        detailsEl.innerHTML = `
            <div class="mb-2"><strong>Media Count:</strong> ${this.album.media_count || 0}</div>
            <div class="mb-2"><strong>Sub-albums:</strong> ${this.album.children_count || 0}</div>
            <div class="mb-2"><strong>Rating:</strong> ${this.album.rating}</div>
            <div class="mb-2"><strong>Created:</strong> ${new Date(this.album.created_at).toLocaleDateString()}</div>
            <div class="mb-2"><strong>Last Modified:</strong> ${new Date(this.album.last_modified).toLocaleDateString()}</div>
        `;
    }

    async loadContent() {
        this.showLoading();

        try {
            const params = new URLSearchParams({
                page: 1,
                limit: 100,
                rating: this.currentRating,
                sort: this.getSortValue(),
                order: this.getOrderValue()
            });

            const response = await fetch(`/api/albums/${this.albumId}/contents?${params}`);
            if (!response.ok) throw new Error('Failed to load contents');

            const data = await response.json();

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
        } catch (error) {
            console.error('Error loading contents:', error);
            this.showError('Failed to load album contents');
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
                this.elements.popularTags.innerHTML = '<p class="text-secondary">No tags found in this album</p>';
            }
        } catch (error) {
            console.error('Error loading popular tags:', error);
        }
    }

    onRatingChange() {
        super.onRatingChange();
        this.loadPopularTagsFromAPI();
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

        // 1. Process Sub-albums
        const allAlbums = data.albums || [];
        const visibleAlbums = allAlbums.filter(a => (a.media_count > 0 || a.children_count > 0));
        const emptyCount = allAlbums.length - visibleAlbums.length;

        if (visibleAlbums.length > 0) {
            subAlbumsContainer.style.display = 'block';
            subAlbumsGrid.innerHTML = visibleAlbums.map(album => this.createAlbumCard(album)).join('');

            // Update Header with empty count
            if (subAlbumsHeader) {
                if (emptyCount > 0) {
                    subAlbumsHeader.innerHTML = `Sub-albums <span class="text-secondary font-normal text-xs">(+${emptyCount} empty albums)</span>`;
                } else {
                    subAlbumsHeader.textContent = 'Sub-albums';
                }
            }
        } else {
            // If all albums are empty, or no albums exist
            subAlbumsContainer.style.display = 'none';
            mediaHeader.style.display = 'none';
        }

        // 2. Render Media
        if (data.media && data.media.length > 0) {
            mediaContainer.style.display = 'block';
            data.media.forEach(media => {
                const item = this.createGalleryItem(media, {
                    checkboxClass: 'album-item-checkbox checkbox',
                    preserveQueryParams: false
                });
                this.elements.grid.appendChild(item);
            });
        } else {
            mediaContainer.style.display = 'none';
            subAlbumsHeader.style.display = 'none';
        }

        // 3. Empty State (No visible albums AND no media)
        if (visibleAlbums.length === 0 && (!data.media || data.media.length === 0)) {
            mediaContainer.style.display = 'block';
            if (emptyCount > 0) {
                this.elements.grid.innerHTML = `<p class="text-secondary col-span-full text-center py-8">This album contains only empty sub-albums.</p>`;
            } else {
                this.elements.grid.innerHTML = '<p class="text-secondary col-span-full text-center py-8">This album is empty</p>';
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
                <div class="aspect-square bg-surface-light flex items-center justify-center">
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
                        <span>${album.media_count || 0} items</span>
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
            title: 'Remove from Album',
            message: `Are you sure you want to remove ${itemCount} item${itemCount > 1 ? 's' : ''} from this album?`,
            confirmText: 'Yes, Remove',
            cancelText: 'Cancel',
            onConfirm: async () => {
                try {
                    const mediaIds = Array.from(this.selectedItems);
                    await app.apiCall(`/api/albums/${this.albumId}/media`, {
                        method: 'DELETE',
                        body: JSON.stringify({ media_ids: mediaIds })
                    });

                    app.showNotification(`Removed ${itemCount} item(s) from album`, 'success');
                    this.clearSelection();
                    this.loadContent();
                    this.loadAlbum();
                } catch (error) {
                    app.showNotification(error.message, 'error', 'Error removing from album');
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
