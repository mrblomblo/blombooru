class AlbumTree {
    constructor(options = {}) {
        this.options = {
            container: options.container,
            onRowClick: options.onRowClick || null,
            renderExtraActions: options.renderExtraActions || null,
            isSelectable: options.isSelectable || false,
            expandOnRowClick: options.expandOnRowClick || false,
            selectedIds: options.selectedIds || new Set(),
            multiSelect: options.multiSelect || false,
            emptyMessage: options.emptyMessage || window.i18n.t('album_picker.no_albums')
        };
        this.albums = [];
        this.searchTimeout = null;
    }

    async loadAlbums() {
        if (this.options.container) {
            this.options.container.innerHTML = `
                <div class="h-full min-h-75 flex flex-col items-center justify-center text-secondary">
                    <div class="spinner"></div>
                    <p class="text-secondary mt-2 text-xs">${window.i18n.t('common.loading')}</p>
                </div>
            `;
        }
        try {
            const response = await fetch('/api/albums/tree');
            if (!response.ok) throw new Error(window.i18n.t('album_picker.load_error'));

            const data = await response.json();
            const rawAlbums = data.items || [];

            const albumMap = new Map();
            for (const album of rawAlbums) {
                album.children = [];
                album.parents = [];
                album.parentId = album.parent_id || null;
                album.isCollapsed = false;
                albumMap.set(album.id, album);
            }

            for (const album of rawAlbums) {
                if (album.parentId && albumMap.has(album.parentId)) {
                    albumMap.get(album.parentId).children.push(album);
                    let curr = albumMap.get(album.parentId);
                    const chain = [];
                    while (curr) {
                        chain.unshift({ id: curr.id, name: curr.name });
                        curr = curr.parentId ? albumMap.get(curr.parentId) : null;
                    }
                    album.parents = chain;
                }
                album.depth = album.parents.length;
            }

            const roots = [];
            for (const album of rawAlbums) {
                if (!album.parentId || !albumMap.has(album.parentId)) {
                    roots.push(album);
                }
            }

            // Flatten recursively into sorted list
            this.albums = [];
            const flatten = (albumsList) => {
                albumsList.sort((a, b) => a.name.localeCompare(b.name));
                for (const album of albumsList) {
                    this.albums.push(album);
                    flatten(album.children);
                }
            };
            flatten(roots);

        } catch (error) {
            console.error('Error loading albums:', error);
            if (window.app && window.app.showNotification) {
                window.app.showNotification(window.i18n.t('notifications.album_picker.failed_to_load_albums'), 'error');
            }
            this.albums = [];
        }
    }

    setAlbums(albums) {
        this.albums = albums;
    }

    render(filteredAlbums = null) {
        if (!this.options.container) return;

        const isFiltered = !!filteredAlbums;
        const albumsToRender = isFiltered ? filteredAlbums : this.albums;

        if (albumsToRender.length === 0) {
            this.options.container.innerHTML = `<p class="text-secondary text-xs p-4 text-center">${this.options.emptyMessage}</p>`;
            return;
        }

        const collapsedIds = new Set(this.albums.filter(a => a.isCollapsed).map(a => a.id));

        this.options.container.innerHTML = albumsToRender.map(album => {
            const isHidden = !isFiltered && album.parents.some(p => collapsedIds.has(p.id));
            return this.renderAlbumItem(album, isFiltered, isHidden);
        }).join('');

        // Row click to toggle selection, expand/collapse, or trigger callback
        this.options.container.querySelectorAll('.album-picker-item').forEach(row => {
            row.addEventListener('click', (e) => {
                // Ignore clicks on action buttons (like manage hamburger button) or links
                if (e.target.closest('.manage-album-btn') || e.target.closest('a')) return;
                if (!this.options.expandOnRowClick && e.target.closest('button')) return;

                const albumId = parseInt(row.dataset.albumId);
                const album = this.albums.find(a => a.id === albumId);

                if (this.options.expandOnRowClick) {
                    this.toggleCollapse(albumId);
                } else if (this.options.isSelectable) {
                    this._toggleSelection(albumId);
                }
                if (this.options.onRowClick && album) {
                    this.options.onRowClick(album, e);
                }
            });
        });

        // Chevron button to expand/collapse with animation (solely an indicator when expandOnRowClick)
        this.options.container.querySelectorAll('.album-toggle-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const albumId = parseInt(btn.dataset.albumId);
                this.toggleCollapse(albumId);
            });
        });
    }

    toggleCollapse(albumId) {
        const album = this.albums.find(a => a.id === albumId);
        if (!album || !album.children || album.children.length === 0) return;

        album.isCollapsed = !album.isCollapsed;

        // Animate the chevron rotation on the clicked row
        const row = this.options.container.querySelector(`.album-picker-item[data-album-id="${albumId}"]`);
        if (row) {
            const svg = row.querySelector('.album-toggle-btn svg, .album-toggle-icon svg');
            if (svg) {
                svg.classList.toggle('-rotate-90', !album.isCollapsed);
            }
        }

        this._updateVisibility();
    }

    _updateVisibility() {
        const collapsedIds = new Set(this.albums.filter(a => a.isCollapsed).map(a => a.id));
        this.options.container.querySelectorAll('.album-picker-item').forEach(row => {
            const id = parseInt(row.dataset.albumId);
            const album = this.albums.find(a => a.id === id);
            if (album) {
                const isHidden = album.parents.some(p => collapsedIds.has(p.id));
                row.classList.toggle('hidden', isHidden);
            }
        });
    }

    _toggleSelection(albumId) {
        if (this.options.selectedIds.has(albumId)) {
            this.options.selectedIds.delete(albumId);
        } else {
            if (!this.options.multiSelect) {
                this.options.selectedIds.clear();
                this.options.container.querySelectorAll('.album-picker-item').forEach(r => {
                    r.classList.remove('bg-primary/10', 'hover:bg-primary/15');
                    r.classList.add('hover:surface');
                    const icon = r.querySelector('.album-picker-item__icon');
                    if (icon) {
                        icon.classList.remove('text-primary');
                        icon.classList.add('text-secondary');
                    }
                });
            }
            this.options.selectedIds.add(albumId);
        }

        // Update visual state of the clicked row
        const row = this.options.container.querySelector(`.album-picker-item[data-album-id="${albumId}"]`);
        if (row) {
            const isSelected = this.options.selectedIds.has(albumId);
            row.classList.toggle('bg-primary/10', isSelected);
            row.classList.toggle('hover:bg-primary/15', isSelected);
            row.classList.toggle('hover:surface', !isSelected);

            const icon = row.querySelector('.album-picker-item__icon');
            if (icon) {
                icon.classList.toggle('text-primary', isSelected);
                icon.classList.toggle('text-secondary', !isSelected);
            }
        }

        // Dispatch an event so the parent container can know selection changed
        this.options.container.dispatchEvent(new CustomEvent('selectionchange', {
            detail: { selectedIds: new Set(this.options.selectedIds) }
        }));
    }

    renderAlbumItem(album, isFiltered, isHidden = false) {
        const isSelected = this.options.isSelectable && this.options.selectedIds.has(album.id);
        const parentPath = album.parents.map(p => p.name).join(' > ');
        const hasChildren = album.children && album.children.length > 0;
        const indentPx = isFiltered ? 0 : album.depth * 20;

        const folderIcon = hasChildren
            ? window.Icons.folderParent({ size: 14, class: 'flex-shrink-0' })
            : window.Icons.folder({ size: 14, class: 'flex-shrink-0' });

        let rightSideChevron = '';
        if (!isFiltered && hasChildren) {
            const rotationClass = album.isCollapsed ? '' : '-rotate-90';
            const chevronIcon = window.Icons.chevronLeft({
                size: 14,
                class: `flex-shrink-0 transition-transform duration-200 ${rotationClass}`
            });
            if (this.options.expandOnRowClick) {
                rightSideChevron = `<span class="album-toggle-icon flex items-center justify-center w-6 h-6 text-secondary shrink-0">${chevronIcon}</span>`;
            } else {
                rightSideChevron = `<button class="album-toggle-btn flex items-center justify-center w-6 h-6 text-secondary hover:text-primary transition-colors shrink-0 cursor-pointer" data-album-id="${album.id}" title="">${chevronIcon}</button>`;
            }
        } else if (!isFiltered) {
            rightSideChevron = `<span class="w-6 shrink-0"></span>`;
        }

        const extraActionsHtml = this.options.renderExtraActions ? this.options.renderExtraActions(album) : '';

        const selectClasses = (this.options.isSelectable || this.options.expandOnRowClick) ? 'cursor-pointer ' : '';
        const stateClasses = isSelected ? 'bg-primary/10 hover:bg-primary/15' : 'hover:surface';
        const hiddenClass = isHidden ? ' hidden' : '';

        return `
            <div class="album-picker-item flex items-center gap-2 border-b py-2 pr-2.5 transition-colors ${selectClasses}${stateClasses}${hiddenClass}"
                 data-album-id="${album.id}"
                 style="padding-left: ${10 + indentPx}px;">
                <span class="album-picker-item__icon shrink-0 transition-colors ${isSelected ? 'text-primary' : 'text-secondary'}">${folderIcon}</span>
                <div class="flex-1 min-w-0">
                    <div class="text-xs font-medium truncate">${album.name}</div>
                    ${parentPath && isFiltered ? `<div class="text-xs text-secondary truncate">${window.i18n.t('album_picker.path', { path: parentPath })}</div>` : ''}
                    <div class="text-xs text-secondary">
                        ${window.i18n.t('common.items_count', { count: album.media_count || 0 })}
                    </div>
                </div>
                ${extraActionsHtml}
                ${rightSideChevron}
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
}

window.AlbumTree = AlbumTree;
