class AlbumPicker {
    constructor(options = {}) {
        this.options = {
            multiSelect: options.multiSelect !== false, // Default true
            showCreateNew: options.showCreateNew || false,
            onConfirm: options.onConfirm || (() => { }),
            onCancel: options.onCancel || (() => { }),
            preSelected: options.preSelected || [], // Array of album IDs
            title: options.title || window.i18n.t('album_picker.title')
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
            if (!response.ok) throw new Error(window.i18n.t('album_picker.load_error'));

            const data = await response.json();
            this.albums = data.items || [];

            // Build hierarchy information for each album
            const albumMap = new Map();
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
                album.children = [];
                album.parentId = album.parents.length > 0 ? album.parents[album.parents.length - 1].id : null;
                album.isCollapsed = false;
                albumMap.set(album.id, album);
            }

            // Organize into tree
            const roots = [];
            for (const album of this.albums) {
                if (album.parentId && albumMap.has(album.parentId)) {
                    albumMap.get(album.parentId).children.push(album);
                } else {
                    roots.push(album);
                }
            }

            // Flatten recursively into sorted list with tree properties
            this.albums = [];
            const flatten = (albumsList, prefixLines = []) => {
                albumsList.sort((a, b) => a.name.localeCompare(b.name));
                for (let i = 0; i < albumsList.length; i++) {
                    const album = albumsList[i];
                    const isLast = i === albumsList.length - 1;

                    album.prefixLines = [...prefixLines];
                    album.isLastChild = isLast;
                    this.albums.push(album);

                    const nextPrefix = [...prefixLines, isLast ? ' ' : '│'];
                    flatten(album.children, nextPrefix);
                }
            };
            flatten(roots);

        } catch (error) {
            console.error('Error loading albums:', error);
            app.showNotification(window.i18n.t('notifications.album_picker.failed_to_load_albums'), 'error');
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
                <div class="flex items-center mb-4 pb-3 border-b">
                    <h3 class="text-base font-bold">${this.options.title}</h3>
                </div>

                <div class="mb-3">
                    <input type="text" id="album-picker-search" placeholder="${window.i18n.t('common.search_albums_placeholder')}"
                        class="w-full bg px-3 py-2 border text-xs focus:outline-none focus:border-primary">
                </div>

                <div id="album-picker-list" class="flex-1 overflow-y-auto mb-4 bg border" style="min-height: 300px;">
                    <!-- Albums will be rendered here -->
                </div>

                <div id="album-picker-selected-status" class="text-xs text-secondary mb-3">
                    ${window.i18n.t('album_picker.selected_count', { count: 0 })}
                </div>

                <div class="flex gap-2 justify-end">
                    <button id="album-picker-confirm" class="px-4 py-2 bg-primary primary-text hover:bg-primary text-xs transition-colors">${window.i18n.t('common.confirm')}</button>
                    <button id="album-picker-cancel" class="px-4 py-2 border bg hover:border-primary hover:text-primary text text-xs transition-colors">${window.i18n.t('common.cancel')}</button>
                </div>
            </div>
        `;

        document.body.appendChild(this.modal);

        // Event listeners
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
        const isFiltered = !!filteredAlbums;

        let visibleAlbums = filteredAlbums || this.albums;
        if (!isFiltered) {
            const collapsedIds = new Set(this.albums.filter(a => a.isCollapsed).map(a => a.id));
            visibleAlbums = this.albums.filter(album => {
                return !album.parents.some(p => collapsedIds.has(p.id));
            });
        }

        if (visibleAlbums.length === 0) {
            listEl.innerHTML = `<p class="text-secondary text-xs p-4 text-center">${window.i18n.t('album_picker.no_albums')}</p>`;
            return;
        }

        listEl.innerHTML = visibleAlbums.map(album => this.renderAlbumItem(album, isFiltered)).join('');

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

        // Add event listeners to collapse toggles
        listEl.querySelectorAll('.album-toggle-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const albumId = parseInt(btn.dataset.albumId);
                const album = this.albums.find(a => a.id === albumId);
                if (album) {
                    album.isCollapsed = !album.isCollapsed;
                    this.render(filteredAlbums);
                }
            });
        });

        this.updateSelectedCount();
    }

    renderAlbumItem(album, isFiltered) {
        const isSelected = this.selectedAlbumIds.has(album.id);
        const parentPath = album.parents.map(p => p.name).join(' > ');

        let prefixHtml = '';
        let toggleHtml = '';
        if (!isFiltered) {
            let text = '';
            if (album.depth > 0) {
                for (const line of (album.prefixLines || []).slice(1)) {
                    text += line === '│' ? '│&nbsp;&nbsp;&nbsp;' : '&nbsp;&nbsp;&nbsp;&nbsp;';
                }
                text += album.isLastChild ? '└── ' : '├── ';
            }

            const hasChildren = album.children && album.children.length > 0;
            if (hasChildren) {
                const icon = album.isCollapsed ? '▶' : '▼';
                toggleHtml = `<button class="album-toggle-btn text-secondary hover:text-primary px-2 py-3 text-xs" data-album-id="${album.id}">${icon}</button>`;
            }

            if (text) {
                prefixHtml = `<span class="text-secondary font-mono text-xs whitespace-pre select-none">${text}</span>`;
            }
        }

        return `
            <div class="album-picker-item p-2 hover:surface border-b flex items-center gap-2" style="padding-left: 8px;">
                ${prefixHtml}
                <input type="checkbox" 
                       class="w-4 h-4 accent-primary album-checkbox flex-shrink-0" 
                       data-album-id="${album.id}"
                       ${isSelected ? 'checked' : ''}>
                <div class="flex-1 min-w-0">
                    <div class="text-xs font-medium truncate">${album.name}</div>
                    ${parentPath && isFiltered ? `<div class="text-xs text-secondary truncate">${window.i18n.t('album_picker.path', { path: parentPath })}</div>` : ''}
                    <div class="text-xs text-secondary">
                        ${window.i18n.t('common.items_count', { count: album.media_count || 0 })}
                        ${album.depth === 0 ? `<span class="tag meta tag-text text-xs px-1 ml-1">${window.i18n.t('album_picker.root')}</span>` : ''}
                    </div>
                </div>
                ${toggleHtml}
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
        const statusEl = this.modal.querySelector('#album-picker-selected-status');
        if (statusEl) {
            statusEl.textContent = window.i18n.t('album_picker.selected_count', { count: this.selectedAlbumIds.size });
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
