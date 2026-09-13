class PendingEntitiesPanel {
    constructor(containerElement, session, options = {}) {
        this.container = containerElement;
        this.session = session;
        this.options = options;
        this.pendingData = { pending_tags: [], pending_albums: [] };
        this.collapsedPaths = new Set();
        this.isLoading = false;

        this.init();
    }

    init() {
        this.container.innerHTML = `
            <div class="pending-entities-panel surface border p-4 mb-4 text-xs" style="display: none;">
                <div class="flex items-center justify-between border-b pb-2 mb-3">
                    <div class="flex items-center gap-3 w-full">
                        <span class="text-xs font-bold whitespace-nowrap overflow-hidden text-ellipsis">${window.i18n.t('upload.pending.title')}</span>
                    </div>
                </div>
                <p class="text-secondary text-[11px] mb-3">
                    ${window.i18n.t('upload.pending.description')}
                </p>

                <!-- Tags Section -->
                <div id="pending-tags-container" class="mb-3">
                    <h4 class="text-[11px] font-bold text-secondary uppercase tracking-wider mb-2">
                        ${window.i18n.t('upload.pending.new_tags')} (<span id="pending-tags-count">0</span>)
                    </h4>
                    <div id="pending-tags-list" class="flex flex-wrap gap-2 overflow-y-auto max-h-40"></div>
                </div>

                <!-- Albums Section -->
                <div id="pending-albums-container">
                    <h4 class="text-[11px] font-bold text-secondary uppercase tracking-wider mb-2">
                        ${window.i18n.t('upload.pending.new_albums')} (<span id="pending-albums-count">0</span>)
                    </h4>
                    <div id="pending-albums-list" class="bg border overflow-y-auto max-h-60 mb-1"></div>
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
            tagsList.className = 'flex flex-wrap gap-2 overflow-y-auto max-h-40';
            tagsList.innerHTML = tags.map(tag => {
                const cat = tag.category || 'general';
                const grayscaleClass = (!tag.user_assigned) ? 'grayscale' : '';
                return `
                    <div class="pending-tag-item inline-flex items-center gap-1 bg border p-1" data-name="${this.escapeHtml(tag.name)}">
                        <div class="custom-select pending-cat-select inline-block align-middle" data-value="${cat}" data-tag="${this.escapeHtml(tag.name)}">
                            <div class="custom-select-trigger tag-text tag ${cat} ${grayscaleClass} cursor-pointer select-none" style="display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;">
                                <span class="text-xs">${this.escapeHtml(tag.name)}</span>
                                <span class="custom-select-value" style="display: none;"></span>
                                ${window.Icons.chevronDown({ size: 10, class: 'custom-select-arrow flex-shrink-0 transition-transform duration-200', style: 'display: block;' })}
                            </div>
                            <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50 min-w-25">
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'general' ? 'selected' : ''}" data-value="general">${window.i18n.t('common.tag_category_general')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'artist' ? 'selected' : ''}" data-value="artist">${window.i18n.t('common.tag_category_artist')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'character' ? 'selected' : ''}" data-value="character">${window.i18n.t('common.tag_category_character')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'copyright' ? 'selected' : ''}" data-value="copyright">${window.i18n.t('common.tag_category_copyright')}</div>
                                <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'meta' ? 'selected' : ''}" data-value="meta">${window.i18n.t('common.tag_category_meta')}</div>
                            </div>
                        </div>
                        <span class="pending-tag-count-badge text-[10px] text-secondary hover:text-primary cursor-pointer transition-colors"
                            title="${window.i18n.t('upload.pending.used_in_media', { count: tag.used_by.length })}">
                            ${window.i18n.t('upload.pending.media_count', { count: tag.used_by.length })}
                        </span>
                        <button type="button" class="pending-remove-btn text-danger hover:text-danger transition-colors cursor-pointer p-0.5 flex items-center justify-center" title="${window.i18n.t('common.remove')}">
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
    }

    renderAlbumTree(container, albums) {
        // Build hierarchy map
        const albumMap = new Map();
        albums.forEach(alb => {
            alb.children = [];
            // Auto-collapse depth >= 4 on initial encounter
            if (alb.depth >= 4 && !this.collapsedPaths.has(alb.path)) {
                this.collapsedPaths.add(alb.path);
            }
            albumMap.set(alb.path, alb);
        });

        const roots = [];
        albums.forEach(alb => {
            if (alb.parent_path && albumMap.has(alb.parent_path)) {
                albumMap.get(alb.parent_path).children.push(alb);
            } else {
                roots.push(alb);
            }
        });

        const ordered = [];
        const flatten = (list, visibleDepth = 0) => {
            list.sort((a, b) => a.name.localeCompare(b.name));
            for (const alb of list) {
                alb.visibleDepth = visibleDepth;
                ordered.push(alb);
                if (alb.children && alb.children.length > 0) {
                    flatten(alb.children, visibleDepth + 1);
                }
            }
        };
        flatten(roots, 0);

        const anyHasChildren = ordered.some(alb => alb.children && alb.children.length > 0);

        container.innerHTML = ordered.map(alb => {
            const hasChildren = alb.children && alb.children.length > 0;
            const isCollapsed = this.collapsedPaths.has(alb.path);
            const isHidden = this._isAlbumHidden(alb.path, albumMap);

            const indentPx = (alb.visibleDepth || 0) * 20;
            const folderIcon = hasChildren
                ? window.Icons.folderParent({ size: 14, class: 'flex-shrink-0' })
                : window.Icons.folder({ size: 14, class: 'flex-shrink-0' });

            let rightSideChevron = '';
            if (hasChildren) {
                const rotationClass = isCollapsed ? '' : '-rotate-90';
                const chevronIcon = window.Icons.chevronLeft({
                    size: 14,
                    class: `flex-shrink-0 transition-transform duration-200 ${rotationClass}`
                });
                rightSideChevron = `<button type="button" class="pending-album-toggle-btn flex items-center justify-center w-6 h-6 text-secondary hover:text-primary transition-colors shrink-0 cursor-pointer" data-album-path="${this.escapeHtml(alb.path)}">${chevronIcon}</button>`;
            } else if (anyHasChildren) {
                rightSideChevron = `<span class="w-6 shrink-0"></span>`;
            }

            const hiddenClass = isHidden ? ' hidden' : '';

            return `
                <div class="pending-album-item flex items-center gap-2 border-b py-2 pr-2.5 transition-colors cursor-pointer hover:surface${hiddenClass}"
                    data-album-path="${this.escapeHtml(alb.path)}"
                    style="padding-left: ${10 + indentPx}px;">
                    <span class="pending-album-icon shrink-0 text-secondary">${folderIcon}</span>
                    <div class="flex-1 min-w-0 flex items-center gap-2">
                        <div class="pending-album-name-wrapper flex-1 min-w-0">
                            <span class="pending-album-name-text text-xs font-medium truncate block" title="${this.escapeHtml(alb.path)}">${this.escapeHtml(alb.name)}</span>
                        </div>
                        <span class="pending-album-count-badge text-[10px] text-secondary hover:text-primary cursor-pointer transition-colors shrink-0 select-none"
                            title="${window.i18n.t('upload.pending.used_in_media', { count: alb.used_by.length })}">
                            ${window.i18n.t('upload.pending.media_count', { count: alb.used_by.length })}
                        </span>
                    </div>

                    <!-- Inline Actions -->
                    <div class="flex items-center gap-1 shrink-0">
                        <button type="button" class="pending-rename-album-btn text-primary hover:text-primary transition-colors cursor-pointer p-1 flex items-center justify-center" title="${window.i18n.t('upload.pending.rename_album')}">
                            ${window.Icons.edit({ size: 14 })}
                        </button>
                        <button type="button" class="pending-remove-album-btn text-danger hover:text-danger transition-colors cursor-pointer p-1 flex items-center justify-center" title="${window.i18n.t('upload.pending.skip_album')}">
                            ${window.Icons.trash({ size: 14 })}
                        </button>
                    </div>

                    ${rightSideChevron}
                </div>
            `;
        }).join('');

        this.setupAlbumRowEvents(container, albumMap);
    }

    _isAlbumHidden(path, albumMap) {
        let current = albumMap.get(path);
        while (current && current.parent_path) {
            if (this.collapsedPaths.has(current.parent_path)) {
                return true;
            }
            current = albumMap.get(current.parent_path);
        }
        return false;
    }

    setupAlbumRowEvents(container, albumMap) {
        // Toggle collapse/expand chevron
        container.querySelectorAll('.pending-album-toggle-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const path = btn.dataset.albumPath;
                if (!path) return;

                if (this.collapsedPaths.has(path)) {
                    this.collapsedPaths.delete(path);
                } else {
                    this.collapsedPaths.add(path);
                }

                // Update chevron rotation
                const svg = btn.querySelector('svg');
                if (svg) {
                    svg.classList.toggle('-rotate-90', !this.collapsedPaths.has(path));
                }

                // Update visibility of descendants
                container.querySelectorAll('.pending-album-item').forEach(row => {
                    const rowPath = row.dataset.albumPath;
                    if (rowPath && rowPath !== path) {
                        const isHidden = this._isAlbumHidden(rowPath, albumMap);
                        row.classList.toggle('hidden', isHidden);
                    }
                });
            });
        });

        // Row click to select contained media
        container.querySelectorAll('.pending-album-item').forEach(row => {
            row.addEventListener('click', (e) => {
                // Ignore clicks on buttons, chevrons, or input fields
                if (e.target.closest('button') || e.target.closest('input') || e.target.closest('.pending-rename-album-btn') || e.target.closest('.pending-remove-album-btn')) {
                    return;
                }

                const path = row.dataset.albumPath;
                const alb = (this.pendingData.pending_albums || []).find(a => a.path === path);
                if (alb && alb.used_by && this.options.onHighlightItems) {
                    this.options.onHighlightItems(alb.used_by);
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
                    this.options.onHighlightItems(alb.used_by);
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
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const row = btn.closest('.pending-album-item');
                const path = row ? row.dataset.albumPath : null;
                if (path) {
                    await this.session.updatePendingAlbum(path, { remove: true });
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
                    await this.session.updatePendingTag(tagName, { category: newCat });
                });
            }

            // Click badge to highlight referencing cards
            const countBadge = chip.querySelector('.pending-tag-count-badge');
            if (countBadge && tagObj) {
                countBadge.addEventListener('click', () => {
                    if (this.options.onHighlightItems) {
                        this.options.onHighlightItems(tagObj.used_by);
                    }
                });
            }

            // Remove tag from all items
            const removeBtn = chip.querySelector('.pending-remove-btn');
            if (removeBtn) {
                removeBtn.addEventListener('click', async () => {
                    await this.session.updatePendingTag(tagName, { remove: true });
                });
            }
        });
    }
}

window.PendingEntitiesPanel = PendingEntitiesPanel;
