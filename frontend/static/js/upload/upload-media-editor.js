class UploadMediaEditor {
    constructor(containerElement, session, options = {}) {
        this.container = containerElement;
        this.session = session;
        this.options = options;
        this.selectedIds = new Set();
        this.activeItemId = null;
        this.tagInputHelper = options.tagInputHelper || new TagInputHelper();
        this.fullscreenViewer = options.fullscreenViewer || null;
        this.allAlbums = options.allAlbums || [];
        this.saveTimeout = null;
        this.tagSaveTimeout = null;
        this.bulkTagSaveTimeout = null;
        this.bulkTagUpdateChain = null;
        this.lastBulkTagNames = null;
        this.bulkCommonTagsMap = null;

        this.singleRatingSelect = null;
        this.singleAlbumSelect = null;
        this.singleTagPreview = null;
        this.bulkRatingSelect = null;
        this.bulkAlbumSelect = null;
        this.bulkTagPreview = null;

        this.init();
    }

    init() {
        this.render();
    }

    setSelection(selectedIds, activeItemId = null, force = false) {
        const newSelectedIds = new Set(selectedIds || []);
        const newActiveItemId = activeItemId || (newSelectedIds.size === 1 ? Array.from(newSelectedIds)[0] : null);

        const isSame = this.selectedIds.size === newSelectedIds.size &&
            Array.from(this.selectedIds).every(id => newSelectedIds.has(id)) &&
            this.activeItemId === newActiveItemId;

        this.selectedIds = newSelectedIds;
        this.activeItemId = newActiveItemId;

        if (newSelectedIds.size === 0) {
            clearTimeout(this.saveTimeout);
            clearTimeout(this.tagSaveTimeout);
            clearTimeout(this.bulkTagSaveTimeout);
        }

        if (isSame && this.container.firstElementChild && !force) {
            return;
        }

        this.render();
    }

    setAllAlbums(albums) {
        this.allAlbums = albums || [];
        if (!this.container.firstElementChild) {
            this.render();
        }
    }

    render() {
        clearTimeout(this.bulkTagSaveTimeout);

        const count = this.selectedIds.size;
        if (count === 0) {
            this.renderEmptyState();
            return;
        }

        if (count === 1) {
            const itemId = this.activeItemId || Array.from(this.selectedIds)[0];
            const item = this.session.getItem(itemId);
            if (!item) {
                this.renderEmptyState();
                return;
            }
            this.renderSingleEditor(item);
            return;
        }

        this.renderBulkEditor();
    }

    renderEmptyState() {
        this.container.innerHTML = `
            <div class="surface border p-6 text-center text-secondary text-xs">
                <p>${window.i18n.t('upload.preview.select_hint')}</p>
            </div>
        `;
    }

    renderAlbumBadgesHtml(albumIds) {
        const idSet = new Set(albumIds || []);
        let html = '';
        idSet.forEach(id => {
            const alb = this.allAlbums.find(a => a.id == id);
            if (alb) {
                html += `
                    <div class="bg px-2 py-0.5 border text-xs flex items-center gap-1.5">
                        <span class="font-mono">${escapeHtml(alb.name)}</span>
                        <button type="button" class="editor-remove-album-btn text-danger hover:text-danger transition-colors cursor-pointer p-0.5 flex items-center justify-center" data-id="${id}">
                            ${window.Icons.trash({ size: 12, class: 'transition-colors' })}
                        </button>
                    </div>
                `;
            }
        });
        return html;
    }

    getAlbumFullPath(album, albumMap) {
        if (!album) return '';
        const parts = [album.name];
        let curr = album.parent_id;
        const visited = new Set([album.id]);
        while (curr && albumMap.has(curr) && !visited.has(curr)) {
            visited.add(curr);
            const parent = albumMap.get(curr);
            if (parent && parent.name) {
                parts.unshift(parent.name);
                curr = parent.parent_id;
            } else {
                break;
            }
        }
        return parts.join('/');
    }

    getFolderAlbumExcludedIds(item) {
        const ids = new Set();
        if (!item) return ids;

        if (item.suggested_album_segments && Array.isArray(item.suggested_album_segments)) {
            item.suggested_album_segments.forEach(seg => {
                if (seg.existing_id) {
                    ids.add(seg.existing_id);
                }
            });
        }

        if (item.suggested_album_path && this.allAlbums && this.allAlbums.length > 0) {
            const albumMap = new Map(this.allAlbums.map(a => [a.id, a]));
            const normPath = item.suggested_album_path.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '').toLowerCase();

            this.allAlbums.forEach(alb => {
                const fullPath = this.getAlbumFullPath(alb, albumMap).toLowerCase();
                if (fullPath && fullPath === normPath) {
                    ids.add(alb.id);
                }
            });
        }

        return ids;
    }

    getCommonFolderAlbumExcludedIds() {
        const items = Array.from(this.selectedIds).map(id => this.session.getItem(id)).filter(Boolean);
        if (items.length === 0) return new Set();

        const sets = items.map(it => this.getFolderAlbumExcludedIds(it));
        const common = new Set(sets[0]);
        for (let i = 1; i < sets.length; i++) {
            for (const id of common) {
                if (!sets[i].has(id)) {
                    common.delete(id);
                }
            }
        }
        return common;
    }

    renderAlbumOptionsHtml(excludedIds = []) {
        const excludeSet = new Set(excludedIds || []);
        const available = this.allAlbums.filter(a => !excludeSet.has(a.id));
        let html = `<div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs selected" data-value="">${window.i18n.t('upload.base_settings.select_album')}</div>`;
        available.forEach(alb => {
            html += `<div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs" data-value="${alb.id}">${escapeHtml(alb.name)}</div>`;
        });
        return html;
    }

    debouncedSave(itemId, data) {
        clearTimeout(this.saveTimeout);
        this.saveTimeout = setTimeout(() => {
            this.session.updateItem(itemId, data, { silent: true });
        }, 500);
    }

    autoResizeTextarea(textarea) {
        if (!textarea) return;
        textarea.style.height = 'auto';
        const computed = window.getComputedStyle(textarea);
        let lineHeight = parseFloat(computed.lineHeight);
        if (isNaN(lineHeight)) {
            const fontSize = parseFloat(computed.fontSize) || 12;
            lineHeight = fontSize * 1.4;
        }
        const paddingTop = parseFloat(computed.paddingTop) || 0;
        const paddingBottom = parseFloat(computed.paddingBottom) || 0;
        const borderTop = parseFloat(computed.borderTopWidth) || 0;
        const borderBottom = parseFloat(computed.borderBottomWidth) || 0;
        const verticalPadding = paddingTop + paddingBottom + borderTop + borderBottom;

        const minHeight = (lineHeight * 2) + verticalPadding;
        const maxHeight = (lineHeight * 5) + verticalPadding;

        const scrollHeight = textarea.scrollHeight;
        const targetHeight = Math.min(Math.max(scrollHeight, minHeight), maxHeight);
        textarea.style.height = `${targetHeight}px`;
        textarea.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
    }
}

window.UploadMediaEditor = UploadMediaEditor;
