class AlbumPicker {
    constructor(options = {}) {
        this.options = {
            multiSelect: options.multiSelect !== false, // Default true
            showCreateNew: options.showCreateNew || false,
            onConfirm: options.onConfirm || (() => { }),
            onCancel: options.onCancel || (() => { }),
            preSelected: options.preSelected || [], // Array of album IDs
            title: options.title || 'Select Albums'
        };

        this.albums = [];
        this.selectedAlbumIds = new Set(this.options.preSelected);
        this.modal = null;
        this.searchTimeout = null;
    }

    async show() {
        await this.loadAlbums();
        this.createModal();
        this.render();
    }

    async loadAlbums() {
        try {
            const response = await fetch('/api/albums?limit=1000&sort=name&order=asc');
            if (!response.ok) throw new Error('Failed to load albums');

            const data = await response.json();
            this.albums = data.items || [];

            // Build hierarchy information for each album
            for (const album of this.albums) {
                try {
                    const parentsResponse = await fetch(`/api/albums/${album.id}/parents`);
                    const parentsData = await parentsResponse.json();
                    album.parents = parentsData.parents || [];
                    album.depth = album.parents.length;
                } catch (error) {
                    console.error(`Error loading parents for album ${album.id}:`, error);
                    album.parents = [];
                    album.depth = 0;
                }
            }

            // Sort by name, maintaining hierarchy
            this.albums.sort((a, b) => {
                // If same parent level, sort alphabetically
                if (a.depth === b.depth) {
                    return a.name.localeCompare(b.name);
                }
                return a.depth - b.depth;
            });

        } catch (error) {
            console.error('Error loading albums:', error);
            app.showNotification('Failed to load albums', 'error');
            this.albums = [];
        }
    }

    createModal() {
        // Remove existing modal if any
        const existing = document.getElementById('album-picker-modal');
        if (existing) existing.remove();

        // Create modal structure
        this.modal = document.createElement('div');
        this.modal.id = 'album-picker-modal';
        this.modal.className = 'modal';
        this.modal.style.display = 'flex';
        this.modal.style.alignItems = 'center';
        this.modal.style.justifyContent = 'center';

        this.modal.innerHTML = `
            <div class="modal-content surface border p-4" style="max-width: 600px; width: 90%; max-height: 80vh; display: flex; flex-direction: column;">
                <div class="flex justify-between items-center mb-4 pb-3 border-b">
                    <h3 class="text-base font-bold">${this.options.title}</h3>
                    <button id="album-picker-close" class="text-secondary hover:text text-xl leading-none">&times;</button>
                </div>

                <div class="mb-3">
                    <input type="text" id="album-picker-search" placeholder="Search albums..."
                        class="w-full bg px-3 py-2 border text-xs focus:outline-none focus:border-primary">
                </div>

                <div id="album-picker-list" class="flex-1 overflow-y-auto mb-4 border" style="min-height: 300px;">
                    <!-- Albums will be rendered here -->
                </div>

                <div class="text-xs text-secondary mb-3">
                    <span id="album-picker-selected-count">0</span> album(s) selected
                </div>

                <div class="flex gap-2 justify-end">
                    <button id="album-picker-cancel" class="px-4 py-2 border hover:surface text-xs">Cancel</button>
                    <button id="album-picker-confirm" class="px-4 py-2 bg-primary primary-text hover:bg-primary text-xs">Confirm</button>
                </div>
            </div>
        `;

        document.body.appendChild(this.modal);

        // Event listeners
        this.modal.querySelector('#album-picker-close').addEventListener('click', () => this.hide());
        this.modal.querySelector('#album-picker-cancel').addEventListener('click', () => this.hide());
        this.modal.querySelector('#album-picker-confirm').addEventListener('click', () => this.confirm());

        const searchInput = this.modal.querySelector('#album-picker-search');
        searchInput.addEventListener('input', (e) => this.handleSearch(e.target.value));

        // Close on outside click
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) this.hide();
        });

        // Prevent modal from closing when clicking inside content
        this.modal.querySelector('.modal-content').addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    render(filteredAlbums = null) {
        const listEl = this.modal.querySelector('#album-picker-list');
        const albumsToRender = filteredAlbums || this.albums;

        if (albumsToRender.length === 0) {
            listEl.innerHTML = '<p class="text-secondary text-xs p-4 text-center">No albums found</p>';
            return;
        }

        listEl.innerHTML = albumsToRender.map(album => this.renderAlbumItem(album)).join('');

        // Add event listeners to checkboxes
        listEl.querySelectorAll('.album-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const albumId = parseInt(e.target.dataset.albumId);
                if (e.target.checked) {
                    if (this.options.multiSelect) {
                        this.selectedAlbumIds.add(albumId);
                    } else {
                        // Single select - clear previous and select this one
                        this.selectedAlbumIds.clear();
                        this.selectedAlbumIds.add(albumId);
                        // Uncheck all others
                        listEl.querySelectorAll('.album-checkbox').forEach(cb => {
                            if (cb !== e.target) cb.checked = false;
                        });
                    }
                } else {
                    this.selectedAlbumIds.delete(albumId);
                }
                this.updateSelectedCount();
            });
        });

        this.updateSelectedCount();
    }

    renderAlbumItem(album) {
        const isSelected = this.selectedAlbumIds.has(album.id);
        const indent = album.depth * 20;
        const parentPath = album.parents.map(p => p.name).join(' > ');

        return `
            <div class="album-picker-item p-2 hover:surface border-b flex items-center gap-2" style="padding-left: ${indent + 8}px;">
                <input type="checkbox" 
                       class="w-4 h-4 accent-primary album-checkbox" 
                       data-album-id="${album.id}"
                       ${isSelected ? 'checked' : ''}>
                <div class="flex-1 min-w-0">
                    <div class="text-xs font-medium truncate">${album.name}</div>
                    ${parentPath ? `<div class="text-xs text-secondary truncate">Path: ${parentPath}</div>` : ''}
                    <div class="text-xs text-secondary">
                        ${album.media_count || 0} items
                        ${album.depth === 0 ? '<span class="tag meta tag-text text-xs px-1 ml-1">Root</span>' : ''}
                    </div>
                </div>
            </div>
        `;
    }

    handleSearch(query) {
        clearTimeout(this.searchTimeout);

        this.searchTimeout = setTimeout(() => {
            const normalizedQuery = query.toLowerCase().trim();

            if (!normalizedQuery) {
                this.render();
                return;
            }

            const filtered = this.albums.filter(album => {
                const nameMatch = album.name.toLowerCase().includes(normalizedQuery);
                const pathMatch = album.parents.some(p =>
                    p.name.toLowerCase().includes(normalizedQuery)
                );
                return nameMatch || pathMatch;
            });

            this.render(filtered);
        }, 300);
    }

    updateSelectedCount() {
        const countEl = this.modal.querySelector('#album-picker-selected-count');
        if (countEl) {
            countEl.textContent = this.selectedAlbumIds.size;
        }
    }

    confirm() {
        const selectedIds = Array.from(this.selectedAlbumIds);
        const selectedAlbums = this.albums.filter(a => selectedIds.includes(a.id));

        this.options.onConfirm(selectedIds, selectedAlbums);
        this.hide();
    }

    hide() {
        if (this.modal) {
            this.modal.remove();
            this.modal = null;
        }
        this.options.onCancel();
    }

    // Static helper method to show picker with promise
    static async pick(options = {}) {
        return new Promise((resolve, reject) => {
            const picker = new AlbumPicker({
                ...options,
                onConfirm: (ids, albums) => resolve({ ids, albums }),
                onCancel: () => resolve(null)
            });
            picker.show().catch(reject);
        });
    }
}
