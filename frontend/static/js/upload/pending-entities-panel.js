class PendingEntitiesPanel {
    constructor(containerElement, session, options = {}) {
        this.container = containerElement;
        this.session = session;
        this.options = options;
        this.pendingData = { pending_tags: [], pending_albums: [] };
        this.collapsedPaths = new Set();
        this.currentSelectedIds = new Set();
        this.isLoading = false;

        this.init();
    }

    init() {
        this.container.innerHTML = `
            <div class="pending-entities-panel surface border p-4 mb-4 text-xs max-w-full" style="display: none;">
                <div class="flex items-center justify-between border-b pb-2 mb-3">
                    <div class="flex items-center gap-3 w-full">
                        <span class="text-xs font-bold whitespace-nowrap overflow-hidden text-ellipsis">${window.i18n.t('upload.pending.title')}</span>
                    </div>
                </div>
                <p class="text-secondary text-[11px] mb-3">
                    ${window.i18n.t('upload.pending.description')}
                </p>

                <!-- Tags Section -->
                <div id="pending-tags-container" class="mb-3 max-w-full min-w-0">
                    <h4 class="text-[11px] font-bold text-secondary uppercase tracking-wider mb-2">
                        ${window.i18n.t('upload.pending.new_tags')} (<span id="pending-tags-count">0</span>)
                    </h4>
                    <div id="pending-tags-list" class="flex flex-wrap gap-2 max-w-full min-w-0"></div>
                </div>

                <!-- Albums Section -->
                <div id="pending-albums-container">
                    <h4 class="text-[11px] font-bold text-secondary uppercase tracking-wider mb-2">
                        ${window.i18n.t('upload.pending.new_albums')} (<span id="pending-albums-count">0</span>)
                    </h4>
                    <div id="pending-albums-list" class="bg border mb-1"></div>
                </div>
            </div>
        `;

        this.setupSessionListeners();
    }

    setupSessionListeners() {
        this.session.on('itemAdded', () => this.debouncedRefresh());
        this.session.on('itemUpdated', () => this.debouncedRefresh());
        this.session.on('itemRemoved', () => this.debouncedRefresh());
        this.session.on('sessionCleared', () => {
            this.pendingData = { pending_tags: [], pending_albums: [] };
            this.collapsedPaths.clear();
            this.currentSelectedIds.clear();
            this.render();
        });
    }

    debouncedRefresh() {
        clearTimeout(this.refreshTimeout);
        this.refreshTimeout = setTimeout(() => this.refresh(), 300);
    }

    async refresh() {
        if (!this.session.sessionId) {
            this.pendingData = { pending_tags: [], pending_albums: [] };
            this.render();
            return;
        }
        this.isLoading = true;

        try {
            this.pendingData = await this.session.fetchPendingEntities();
            this.render();
        } catch (e) {
            console.error('Error refreshing pending entities:', e);
        } finally {
            this.isLoading = false;
        }
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    render() {
        const panel = this.container.querySelector('.pending-entities-panel');
        const tags = this.pendingData.pending_tags || [];
        const albums = this.pendingData.pending_albums || [];
        const total = tags.length + albums.length;

        // Hide completely if empty
        if (!panel) return;
        if (total === 0) {
            panel.style.display = 'none';
            return;
        }
        panel.style.display = 'block';

        const tagsCount = this.container.querySelector('#pending-tags-count');
        const albumsCount = this.container.querySelector('#pending-albums-count');
        const tagsList = this.container.querySelector('#pending-tags-list');
        const albumsList = this.container.querySelector('#pending-albums-list');
        const tagsContainer = this.container.querySelector('#pending-tags-container');
        const albumsContainer = this.container.querySelector('#pending-albums-container');

        if (tagsCount) tagsCount.textContent = tags.length.toString();
        if (albumsCount) albumsCount.textContent = albums.length.toString();

        // Render Pending Tags as style-conforming pills with category selector
        if (tagsContainer) {
            tagsContainer.style.display = tags.length > 0 ? 'block' : 'none';
        }
        if (tagsList && tags.length > 0) {
            tagsList.className = 'flex flex-wrap gap-2 max-w-full min-w-0';
            tagsList.innerHTML = tags.map(tag => {
                const cat = tag.category || 'general';
                const grayscaleClass = (!tag.user_assigned) ? 'grayscale' : '';
                return `
                    <div class="pending-tag-item inline-flex items-center gap-1 bg border p-1 transition-colors max-w-full min-w-0" data-name="${this.escapeHtml(tag.name)}">
                        <div class="custom-select pending-cat-select max-w-full min-w-0 inline-flex shrink" data-value="${cat}" data-tag="${this.escapeHtml(tag.name)}">
                            <div class="custom-select-trigger tag-text tag ${cat} ${grayscaleClass} cursor-pointer select-none max-w-full min-w-0 !inline-flex items-center gap-1 flex-nowrap" style="white-space: nowrap; display: inline-flex;">
                                <span class="text-xs truncate min-w-0" title="${this.escapeHtml(tag.name)}">${this.escapeHtml(tag.name)}</span>
                                <span class="custom-select-value" style="display: none;"></span>
                                ${window.Icons.chevronDown({ size: 10, class: 'custom-select-arrow shrink-0 transition-transform duration-200' })}
                            </div>
                            <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50 min-w-25">
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'general' ? 'selected' : ''}" data-value="general">${window.i18n.t('common.tag_category_general')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'artist' ? 'selected' : ''}" data-value="artist">${window.i18n.t('common.tag_category_artist')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'character' ? 'selected' : ''}" data-value="character">${window.i18n.t('common.tag_category_character')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'copyright' ? 'selected' : ''}" data-value="copyright">${window.i18n.t('common.tag_category_copyright')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'meta' ? 'selected' : ''}" data-value="meta">${window.i18n.t('common.tag_category_meta')}</div>
                            </div>
                        </div>
                        <span class="pending-tag-count-badge text-[10px] text-secondary hover:text-primary cursor-pointer transition-colors shrink-0 select-none"
                            title="${window.i18n.t('upload.pending.used_in_media', { count: tag.used_by.length })}">
                            ${window.i18n.t('upload.pending.media_count', { count: tag.used_by.length })}
                        </span>
                        <button type="button" class="pending-remove-btn text-danger hover:text-danger transition-colors cursor-pointer p-0.5 flex items-center justify-center shrink-0" title="${window.i18n.t('common.remove')}">
                            ${window.Icons.trash({ size: 12, class: 'transition-colors' })}
                        </button>
                    </div>
                `;
            }).join('');

            this.setupTagRowEvents();
        }

        // Render Pending Albums
        if (albumsContainer) {
            albumsContainer.style.display = albums.length > 0 ? 'block' : 'none';
        }
        if (albumsList && albums.length > 0) {
            this.renderAlbumTree(albumsList, albums);
        }

        this.updateSelectionHighlight(this.currentSelectedIds);
    }

    renderAlbumTree(container, albums) {
        const albumMap = new Map();
        albums.forEach(alb => {
            albumMap.set(alb.path, alb);
        });

        const sorted = this._sortAlbumsLogically(albums, albumMap);

        container.innerHTML = sorted.map(alb => {
            const hasChildren = albums.some(a => a.parent_path === alb.path);
            const folderIcon = hasChildren
                ? window.Icons.folderParent({ size: 14, class: 'flex-shrink-0' })
                : window.Icons.folder({ size: 14, class: 'flex-shrink-0' });

            let parentPathHtml = '';
            if (alb.parent_path) {
                const parentAlb = albumMap.get(alb.parent_path);
                const parentName = parentAlb ? parentAlb.name : alb.parent_path.split('/').filter(Boolean).pop();
                if (parentName) {
                    parentPathHtml = `<span class="text-[10px] text-secondary truncate block" title="${this.escapeHtml(alb.path)}">${this.escapeHtml(parentName)}</span>`;
                }
            }

            return `
                <div class="pending-album-item flex items-center gap-2 border-b py-2 px-2.5 transition-colors cursor-pointer hover:surface"
                    data-album-path="${this.escapeHtml(alb.path)}">
                    <span class="pending-album-icon shrink-0 text-secondary">${folderIcon}</span>
                    <div class="pending-album-name-wrapper flex-1 min-w-0">
                        <span class="pending-album-name-text text-xs font-medium truncate block" title="${this.escapeHtml(alb.path)}">${this.escapeHtml(alb.name)}</span>
                        ${parentPathHtml}
                    </div>
                    <div class="flex items-center gap-1 shrink-0">
                        <span class="pending-album-count-badge text-[10px] text-secondary hover:text-primary cursor-pointer transition-colors select-none"
                            title="${window.i18n.t('upload.pending.used_in_media', { count: alb.used_by.length })}">
                            ${window.i18n.t('upload.pending.media_count', { count: alb.used_by.length })}
                        </span>
                        <button type="button" class="pending-rename-album-btn text-primary hover:text-primary transition-colors cursor-pointer p-1 flex items-center justify-center" title="${window.i18n.t('upload.pending.rename_album')}">
                            ${window.Icons.edit({ size: 14 })}
                        </button>
                        <button type="button" class="pending-remove-album-btn text-danger hover:text-danger transition-colors cursor-pointer p-1 flex items-center justify-center" title="${window.i18n.t('common.remove')}">
                            ${window.Icons.trash({ size: 14 })}
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        this.setupAlbumRowEvents(container, albumMap);
    }

    _sortAlbumsLogically(albums, albumMap) {
        if (!albums || albums.length <= 1) return albums || [];

        if (!albumMap) {
            albumMap = new Map();
            albums.forEach(alb => albumMap.set(alb.path, alb));
        }

        const childrenMap = new Map();
        const roots = [];

        albums.forEach(alb => {
            if (alb.parent_path && albumMap.has(alb.parent_path)) {
                if (!childrenMap.has(alb.parent_path)) {
                    childrenMap.set(alb.parent_path, []);
                }
                childrenMap.get(alb.parent_path).push(alb);
            } else {
                roots.push(alb);
            }
        });

        const compareByName = (a, b) => {
            const nameA = a.name || a.path || '';
            const nameB = b.name || b.path || '';
            return nameA.localeCompare(nameB, undefined, { sensitivity: 'base', numeric: true });
        };

        const compareRoots = (a, b) => {
            const pathA = a.path || a.name || '';
            const pathB = b.path || b.name || '';
            return pathA.localeCompare(pathB, undefined, { sensitivity: 'base', numeric: true });
        };

        roots.sort(compareRoots);

        for (const children of childrenMap.values()) {
            children.sort(compareByName);
        }

        const result = [];
        const visited = new Set();

        const traverse = (alb) => {
            if (visited.has(alb.path)) return;
            visited.add(alb.path);
            result.push(alb);

            const children = childrenMap.get(alb.path) || [];
            for (const child of children) {
                traverse(child);
            }
        };

        for (const root of roots) {
            traverse(root);
        }

        // Fallback for any disconnected albums
        for (const alb of albums) {
            if (!visited.has(alb.path)) {
                result.push(alb);
            }
        }

        return result;
    }

    setupAlbumRowEvents(container, albumMap) {
        // Row click to select contained media
        container.querySelectorAll('.pending-album-item').forEach(row => {
            row.addEventListener('click', (e) => {
                // Ignore clicks on buttons or input fields
                if (e.target.closest('button') || e.target.closest('input')) {
                    return;
                }

                const path = row.dataset.albumPath;
                const alb = (this.pendingData.pending_albums || []).find(a => a.path === path);
                if (alb && alb.used_by && this.options.onHighlightItems) {
                    this.options.onHighlightItems(alb.used_by, e);
                }
            });
        });

        // Item count badge click to select contained media
        container.querySelectorAll('.pending-album-count-badge').forEach(badge => {
            badge.addEventListener('click', (e) => {
                e.stopPropagation();
                const row = badge.closest('.pending-album-item');
                const path = row ? row.dataset.albumPath : null;
                const alb = (this.pendingData.pending_albums || []).find(a => a.path === path);
                if (alb && alb.used_by && this.options.onHighlightItems) {
                    this.options.onHighlightItems(alb.used_by, e);
                }
            });
        });

        // Rename button
        container.querySelectorAll('.pending-rename-album-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const row = btn.closest('.pending-album-item');
                const path = row ? row.dataset.albumPath : null;
                const alb = (this.pendingData.pending_albums || []).find(a => a.path === path);
                if (!alb || !row) return;

                const wrapper = row.querySelector('.pending-album-name-wrapper');
                if (!wrapper || wrapper.querySelector('input')) return;

                const currentName = alb.name;
                wrapper.innerHTML = `
                    <input type="text" class="pending-rename-input w-full bg px-1.5 py-0.5 border text-xs focus:outline-none focus:border-primary"
                        value="${this.escapeHtml(currentName)}">
                `;

                const input = wrapper.querySelector('.pending-rename-input');
                if (input) {
                    input.focus();
                    input.select();

                    const saveRename = async () => {
                        const newName = input.value.trim();
                        if (newName && newName !== currentName) {
                            await this.session.updatePendingAlbum(alb.path, { new_name: newName });
                        } else {
                            wrapper.innerHTML = `<span class="pending-album-name-text text-xs font-medium truncate block" title="${this.escapeHtml(alb.path)}">${this.escapeHtml(currentName)}</span>`;
                        }
                    };

                    input.addEventListener('keydown', (ke) => {
                        if (ke.key === 'Enter') {
                            ke.preventDefault();
                            input.blur();
                        } else if (ke.key === 'Escape') {
                            wrapper.innerHTML = `<span class="pending-album-name-text text-xs font-medium truncate block" title="${this.escapeHtml(alb.path)}">${this.escapeHtml(currentName)}</span>`;
                        }
                    });

                    input.addEventListener('blur', saveRename, { once: true });
                }
            });
        });

        // Trash / skip album button
        container.querySelectorAll('.pending-remove-album-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const row = btn.closest('.pending-album-item');
                const path = row ? row.dataset.albumPath : null;
                if (!path) return;
                const alb = (this.pendingData.pending_albums || []).find(a => a.path === path);
                const displayName = alb ? (alb.name || alb.title || path) : path;
                const doRemove = async () => {
                    await this.session.updatePendingAlbum(path, { remove: true });
                };
                if (typeof ModalHelper !== 'undefined') {
                    new ModalHelper({
                        type: 'danger',
                        title: window.i18n.t('common.confirm'),
                        message: window.i18n.t('upload.pending.remove_album_confirm', { album: displayName }),
                        confirmText: window.i18n.t('common.yes_remove'),
                        cancelText: window.i18n.t('common.cancel'),
                        onConfirm: doRemove
                    }).show();
                } else {
                    doRemove();
                }
            });
        });
    }

    setupTagRowEvents() {
        const chips = this.container.querySelectorAll('.pending-tag-item');
        chips.forEach(chip => {
            const tagName = chip.dataset.name;
            const tagObj = (this.pendingData.pending_tags || []).find(t => t.name.toLowerCase() === tagName.toLowerCase());

            // Category select
            const catSelectEl = chip.querySelector('.pending-cat-select');
            if (catSelectEl && typeof CustomSelect !== 'undefined') {
                new CustomSelect(catSelectEl);
                catSelectEl.addEventListener('change', async (e) => {
                    const newCat = e.detail.value;
                    const trigger = catSelectEl.querySelector('.custom-select-trigger');
                    if (trigger) {
                        ['general', 'artist', 'character', 'copyright', 'meta'].forEach(c => trigger.classList.remove(c));
                        trigger.classList.add(newCat);
                    }
                    if (tagObj) {
                        tagObj.category = newCat;
                    }
                    await this.session.updatePendingTag(tagName, { category: newCat });
                });
            }

            // Click badge to highlight referencing cards
            const countBadge = chip.querySelector('.pending-tag-count-badge');
            if (countBadge && tagObj) {
                countBadge.addEventListener('click', (e) => {
                    if (this.options.onHighlightItems) {
                        this.options.onHighlightItems(tagObj.used_by, e);
                    }
                });
            }

            // Remove tag from all items
            const removeBtn = chip.querySelector('.pending-remove-btn');
            if (removeBtn) {
                removeBtn.addEventListener('click', () => {
                    const doRemove = async () => {
                        await this.session.updatePendingTag(tagName, { remove: true });
                    };
                    if (typeof ModalHelper !== 'undefined') {
                        new ModalHelper({
                            type: 'danger',
                            title: window.i18n.t('common.confirm'),
                            message: window.i18n.t('upload.pending.remove_tag_confirm', { tag: tagName }),
                            confirmText: window.i18n.t('common.yes_remove'),
                            cancelText: window.i18n.t('common.cancel'),
                            onConfirm: doRemove
                        }).show();
                    } else {
                        doRemove();
                    }
                });
            }
        });
    }

    updateSelectionHighlight(selectedIds) {
        this.currentSelectedIds = new Set(selectedIds || []);

        const chips = this.container.querySelectorAll('.pending-tag-item');
        chips.forEach(chip => {
            const tagName = chip.dataset.name;
            const tagObj = (this.pendingData.pending_tags || []).find(t => t.name.toLowerCase() === (tagName || '').toLowerCase());
            const allSelected = Boolean(tagObj && tagObj.used_by && tagObj.used_by.length > 0 && tagObj.used_by.every(id => this.currentSelectedIds.has(id)));

            chip.classList.toggle('border-primary', allSelected);
            chip.classList.toggle('bg-primary/5', allSelected);
            chip.classList.remove('ring-1', 'ring-primary');

            const countBadge = chip.querySelector('.pending-tag-count-badge');
            if (countBadge) {
                countBadge.classList.toggle('text-primary', allSelected);
                countBadge.classList.toggle('text-secondary', !allSelected);
            }
        });

        const rows = this.container.querySelectorAll('.pending-album-item');
        rows.forEach(row => {
            const path = row.dataset.albumPath;
            const alb = (this.pendingData.pending_albums || []).find(a => a.path === path);
            const allSelected = Boolean(alb && alb.used_by && alb.used_by.length > 0 && alb.used_by.every(id => this.currentSelectedIds.has(id)));

            row.classList.toggle('is-all-selected', allSelected);
            row.classList.toggle('bg-primary/5', allSelected);
            row.classList.remove('border-primary', 'border-l-4', 'border-l-primary');

            const countBadge = row.querySelector('.pending-album-count-badge');
            if (countBadge) {
                countBadge.classList.toggle('text-primary', allSelected);
                countBadge.classList.toggle('text-secondary', !allSelected);
            }
        });
    }
}

window.PendingEntitiesPanel = PendingEntitiesPanel;
