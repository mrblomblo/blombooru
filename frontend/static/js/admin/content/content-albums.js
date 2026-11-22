// AdminContent album management, hierarchy editing, and maintenance
Object.assign(AdminContent.prototype, {
    setupAlbumManagement() {
        // Create album form
        const createAlbumForm = document.getElementById('create-album-form');
        if (createAlbumForm) {
            createAlbumForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.createAlbum();
            });
        }

        // Album search
        const albumSearchInput = document.getElementById('album-search-input');

        albumSearchInput?.addEventListener('input', () => {
            this.searchAlbums();
        });

        albumSearchInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.searchAlbums();
            }
        });

        // Setup Album Tree for search
        const resultsDiv = document.getElementById('album-search-results');
        if (resultsDiv && typeof window.AlbumTree !== 'undefined') {
            this.albumTree = new window.AlbumTree({
                container: resultsDiv,
                isSelectable: false,
                expandOnRowClick: true,
                renderExtraActions: (album) => {
                    let dateStr = '';
                    const dateVal = album.created_at || album.last_modified;
                    if (dateVal) {
                        const d = new Date(dateVal);
                        if (!isNaN(d.getTime())) {
                            dateStr = `${new Intl.DateTimeFormat(undefined, { dateStyle: "short" }).format(d)} ${new Intl.DateTimeFormat(undefined, { timeStyle: "short", hour12: false }).format(d)}`;
                        }
                    }
                    const parentId = album.parents && album.parents.length > 0 ? album.parents[album.parents.length - 1].id : '';

                    return `
                        <div class="flex items-center gap-2">
                            ${dateStr ? `<span class="text-xs text-secondary text-center hidden sm:block">${dateStr}</span>` : ''}
                            <button class="manage-album-btn flex-shrink-0 flex items-center justify-center w-7 h-7 bg-primary primary-text hover:bg-primary border-primary hover:border-primary transition-colors cursor-pointer"
                                data-album-id="${album.id}"
                                data-album-name="${escapeHtml(album.name)}"
                                data-parent-id="${parentId}"
                                title="${window.i18n.t('admin.albums_management.manage_album')}">
                                ${window.Icons.tagMenu({ size: 14 })}
                            </button>
                        </div>
                    `;
                }
            });

            // Event delegation for manage buttons
            resultsDiv.addEventListener('click', (e) => {
                const btn = e.target.closest('.manage-album-btn');
                if (btn) {
                    const albumId = btn.dataset.albumId;
                    const albumName = btn.dataset.albumName;
                    const parentId = btn.dataset.parentId || null;
                    this.showAlbumManageModal(albumId, albumName, parentId);
                }
            });

            // Initial load
            this.albumTree.loadAlbums().then(() => this.albumTree.render());
        }

        // Setup parent album select
        const parentAlbumSelectElement = document.getElementById('parent-album-select');
        if (parentAlbumSelectElement) {
            this.parentAlbumSelect = new CustomSelect(parentAlbumSelectElement);
        }

        // Recalculate album metrics button
        const recalculateBtn = document.getElementById('recalculate-album-metrics-btn');
        recalculateBtn?.addEventListener('click', () => this.recalculateAlbumMetrics());

        // Prune albums button
        const pruneBtn = document.getElementById('prune-albums-btn');
        pruneBtn?.addEventListener('click', () => this.pruneAlbums());

        // Load albums for parent select
        this.loadAlbums();
    },

    async recalculateAlbumMetrics() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.start('recalculate_album_metrics');
        }
    },

    pruneAlbums() {
        const btn = document.getElementById('prune-albums-btn');
        if (!btn) return;

        const modal = new ModalHelper({
            id: 'prune-albums-modal',
            type: 'warning',
            title: window.i18n.t('common.confirm_1_title'),
            message: window.i18n.t('admin.albums_management.maintenance.prune_albums_description'),
            confirmText: window.i18n.t('common.yes'),
            cancelText: window.i18n.t('common.no'),
            confirmId: 'prune-albums-confirm-yes',
            cancelId: 'prune-albums-confirm-no',
            onConfirm: async () => {
                if (window.maintenanceJobRunner) {
                    await window.maintenanceJobRunner.start('prune_albums');
                }
            }
        });
        modal.show();
    },

    async loadAlbumStats() {
        try {
            const response = await fetch('/api/albums/stats');
            const data = await response.json();

            const totalAlbumsEl = document.getElementById('total-albums');
            const rootAlbumsEl = document.getElementById('root-albums');

            if (totalAlbumsEl) totalAlbumsEl.textContent = data.total_albums || 0;
            if (rootAlbumsEl) rootAlbumsEl.textContent = data.root_albums || 0;
        } catch (error) {
            console.error('Error loading album stats:', error);
        }
    },

    async loadAlbums() {
        try {
            const response = await fetch('/api/albums/tree');
            const data = await response.json();

            // Update parent album select dropdown
            const parentAlbumSelect = document.getElementById('parent-album-select');
            const parentAlbumContainer = document.getElementById('parent-album-container');

            if (parentAlbumSelect && this.parentAlbumSelect) {
                const items = data.items || [];

                if (items.length === 0) {
                    if (parentAlbumContainer) parentAlbumContainer.style.display = 'none';
                } else {
                    if (parentAlbumContainer) parentAlbumContainer.style.display = 'block';

                    const options = [
                        { value: '', text: window.i18n.t('admin.albums_management.none_root'), selected: true }
                    ];

                    for (const album of items) {
                        options.push({
                            value: album.id.toString(),
                            text: album.name
                        });
                    }

                    this.parentAlbumSelect.setOptions(options);
                }
            }
        } catch (error) {
            console.error('Error loading albums:', error);
        }
    },

    async createAlbum() {
        const nameInput = document.getElementById('album-name-input');
        const parentSelectElement = document.getElementById('parent-album-select');
        const parentId = parentSelectElement?.dataset.value || '';

        const albumName = nameInput.value.trim();
        if (!albumName) {
            app.showNotification(window.i18n.t('notifications.admin.enter_album_name'), 'error');
            return;
        }

        try {
            const albumData = {
                name: albumName,
                parent_album_id: parentId ? parseInt(parentId) : null
            };

            await app.apiCall('/api/albums', {
                method: 'POST',
                body: JSON.stringify(albumData)
            });

            app.showNotification(window.i18n.t('notifications.admin.album_created'), 'success');

            // Clear form
            nameInput.value = '';
            if (this.parentAlbumSelect) {
                this.parentAlbumSelect.setValue('');
            }

            // Reload data
            await this.refreshAlbumTree();
            await this.app.content.loadAlbumStats();
            await this.loadAlbums();

        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_creating_album'));
        }
    },

    async searchAlbums() {
        const searchInput = document.getElementById('album-search-input');
        const query = searchInput ? searchInput.value.trim() : '';
        if (this.albumTree) {
            this.albumTree.handleSearch(query);
        }
    },

    async refreshAlbumTree() {
        if (this.albumTree) {
            await this.albumTree.loadAlbums();
            const searchInput = document.getElementById('album-search-input');
            const query = searchInput ? searchInput.value.trim() : '';
            if (query) {
                this.albumTree.handleSearch(query);
            } else {
                this.albumTree.render();
            }
        }
    },

    showAlbumManageModal(albumId, albumName, currentParentId) {
        // Remove existing modal if any
        const existingModal = document.getElementById('album-manage-modal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'album-manage-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full text-center">
                ${window.Icons.folder({ size: 48, class: 'mx-auto mb-4 text-primary' })}
                <h2 class="text-xl font-bold mb-2 text-primary">${window.i18n.t('admin.albums_management.manage_album')}</h2>
                <p class="text-base mb-6 text font-medium">${escapeHtml(albumName)}</p>
                <div class="flex flex-col gap-3">
                    <button id="album-manage-rename" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.Icons.edit({ size: 16 })}
                        ${window.i18n.t('admin.albums_management.rename_album')}
                    </button>
                    <button id="album-manage-parent" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.Icons.folderParent({ size: 16 })}
                        ${window.i18n.t('admin.albums_management.change_parent_album')}
                    </button>
                    <button id="album-manage-delete" class="px-6 py-3 transition-colors bg border border-danger text-danger hover:bg-danger hover:tag-text font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.Icons.trash({ size: 16 })}
                        ${window.i18n.t('common.delete_album')}
                    </button>
                    <button id="album-manage-cancel" class="btn-dark px-6 py-3 font-bold text-sm flex items-center justify-center gap-2 cursor-pointer">
                        ${window.i18n.t('common.close')}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Event listeners setup
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
            }
        };

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
        };

        document.getElementById('album-manage-rename').addEventListener('click', () => {
            closeModal();
            this.showRenameAlbumModal(albumId, albumName, currentParentId);
        });

        document.getElementById('album-manage-parent').addEventListener('click', () => {
            closeModal();
            this.showChangeParentModal(albumId, albumName, currentParentId);
        });

        document.getElementById('album-manage-delete').addEventListener('click', () => {
            closeModal();
            this.deleteAlbum(albumId, albumName, currentParentId);
        });

        document.getElementById('album-manage-cancel').addEventListener('click', closeModal);

        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        document.addEventListener('keydown', handleEscape);
    },

    showRenameAlbumModal(albumId, currentName, currentParentId) {
        // Remove existing modal if any
        const existingModal = document.getElementById('album-rename-modal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'album-rename-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full">
                <h2 class="text-xl font-bold mb-4 text-primary text-center">Rename Album</h2>
                <div class="mb-6">
                    <label class="block text-xs font-bold mb-2">New Name</label>
                    <input type="text" id="new-album-name" value="${escapeHtml(currentName)}"
                        class="w-full bg px-3 py-2 border text-sm focus:outline-none focus:border-primary">
                </div>
                <div class="flex gap-4 justify-center">
                    <button id="album-rename-confirm" class="btn-primary px-6 py-3 font-bold text-sm cursor-pointer">
                        Save
                    </button>
                    <button id="album-rename-cancel" class="btn px-6 py-3 font-bold text-sm cursor-pointer">
                        Cancel
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Focus the input and select all text
        const input = document.getElementById('new-album-name');
        input.focus();
        input.select();

        // Event listeners
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                this.showAlbumManageModal(albumId, currentName, currentParentId);
            }
        };

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
        };

        const confirmRename = async () => {
            const newName = input.value.trim();
            if (!newName) {
                app.showNotification(window.i18n.t('notifications.admin.enter_name'), 'error');
                return;
            }
            if (newName === currentName) {
                closeModal();
                this.showAlbumManageModal(albumId, currentName, currentParentId);
                return;
            }

            closeModal();

            try {
                await app.apiCall(`/api/albums/${albumId}`, {
                    method: 'PUT',
                    body: JSON.stringify({ name: newName })
                });

                app.showNotification(window.i18n.t('notifications.admin.album_renamed'), 'success');
                await this.refreshAlbumTree();
                await this.loadAlbums();
                await this.app.content.loadAlbumStats();

                // Return to manage modal with updated name
                this.showAlbumManageModal(albumId, newName, currentParentId);

            } catch (error) {
                app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_renaming_album'));
                // Return to manage modal on error
                this.showAlbumManageModal(albumId, currentName, currentParentId);
            }
        };

        document.getElementById('album-rename-confirm').addEventListener('click', confirmRename);

        document.getElementById('album-rename-cancel').addEventListener('click', () => {
            closeModal();
            this.showAlbumManageModal(albumId, currentName, currentParentId);
        });

        // Handle Enter key in input
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                confirmRename();
            }
        });

        // Close on outside click - return to manage modal
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal();
                this.showAlbumManageModal(albumId, currentName, currentParentId);
            }
        });

        document.addEventListener('keydown', handleEscape);
    },

    async getAlbumDescendantIds(albumId, allAlbums = null) {
        if (!allAlbums) {
            try {
                const response = await fetch('/api/albums/tree');
                if (response.ok) {
                    const data = await response.json();
                    allAlbums = data.items || [];
                }
            } catch (e) {
                console.error('Error fetching albums tree:', e);
                allAlbums = [];
            }
        }

        const childMap = new Map();
        for (const a of (allAlbums || [])) {
            if (a.parent_id) {
                const pid = a.parent_id.toString();
                if (!childMap.has(pid)) childMap.set(pid, []);
                childMap.get(pid).push(a.id.toString());
            }
        }

        const descendantIds = new Set();
        const stack = [albumId.toString()];
        while (stack.length > 0) {
            const curr = stack.pop();
            const children = childMap.get(curr) || [];
            for (const cid of children) {
                if (!descendantIds.has(cid)) {
                    descendantIds.add(cid);
                    stack.push(cid);
                }
            }
        }
        return descendantIds;
    },

    async showChangeParentModal(albumId, albumName, currentParentId) {
        // Remove existing modal if any
        const existingModal = document.getElementById('album-parent-modal');
        if (existingModal) {
            existingModal.remove();
        }

        // Load all albums for the dropdown
        let albums = [];
        try {
            const response = await fetch('/api/albums/tree');
            const data = await response.json();
            albums = data.items || [];
        } catch (error) {
            console.error('Error loading albums:', error);
            app.showNotification(window.i18n.t('notifications.admin.error_loading_albums'), 'error');
            this.showAlbumManageModal(albumId, albumName, currentParentId);
            return;
        }

        // Get all descendant IDs to prevent circular references
        const descendantIds = await this.getAlbumDescendantIds(albumId, albums);

        // Filter out the current album and all its descendants
        const validAlbums = albums.filter(a => {
            const id = a.id.toString();
            return id !== albumId.toString() && !descendantIds.has(id);
        });

        const modal = document.createElement('div');
        modal.id = 'album-parent-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        // Build options HTML for custom select
        let optionsHtml = `
            <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs ${!currentParentId ? 'selected' : ''}"
                data-value="">${window.i18n.t('admin.albums_management.none_root')}</div>
        `;
        for (const album of validAlbums) {
            const isSelected = currentParentId && album.id.toString() === currentParentId.toString();
            optionsHtml += `
                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs ${isSelected ? 'selected' : ''}"
                    data-value="${album.id}">${escapeHtml(album.name)}</div>
            `;
        }

        // Determine initial display text
        let initialDisplayText = window.i18n.t('admin.albums_management.none_root');
        if (currentParentId) {
            const currentParent = validAlbums.find(a => a.id.toString() === currentParentId.toString());
            if (currentParent) {
                initialDisplayText = currentParent.name;
            }
        }

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full">
                <h2 class="text-xl font-bold mb-2 text-primary text-center">Change Parent Album</h2>
                <p class="text-sm mb-4 text-secondary text-center">Album: <span class="text font-medium">${escapeHtml(albumName)}</span></p>
                <div class="mb-6">
                    <label class="block text-xs font-bold mb-2">New Parent Album</label>
                    <div id="change-parent-select" class="custom-select" data-value="${currentParentId || ''}">
                        <button
                            class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 bg border text-xs cursor-pointer focus:outline-none focus:border-primary"
                            type="button">
                            <span class="custom-select-value text">${escapeHtml(initialDisplayText)}</span>
                            ${window.Icons.selectArrow({ size: 12 })}
                        </button>
                        <div class="custom-select-dropdown bg border border-primary max-h-60 overflow-y-auto shadow-lg">
                            ${optionsHtml}
                        </div>
                    </div>
                </div>
                <div class="flex gap-4 justify-center">
                    <button id="album-parent-confirm" class="btn-primary px-6 py-3 font-bold text-sm cursor-pointer">
                        Save
                    </button>
                    <button id="album-parent-cancel" class="btn px-6 py-3 font-bold text-sm cursor-pointer">
                        Cancel
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Initialize the custom select
        const selectElement = document.getElementById('change-parent-select');
        const changeParentSelect = new CustomSelect(selectElement);

        // Event listeners
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        };

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
        };

        document.getElementById('album-parent-confirm').addEventListener('click', async () => {
            const newParentId = selectElement.dataset.value;
            closeModal();

            // Check if parent actually changed
            const oldParentId = currentParentId || '';
            if (newParentId === oldParentId) {
                this.showAlbumManageModal(albumId, albumName, currentParentId);
                return;
            }

            try {
                await app.apiCall(`/api/albums/${albumId}`, {
                    method: 'PUT',
                    body: JSON.stringify({
                        parent_album_id: newParentId ? parseInt(newParentId) : null
                    })
                });

                app.showNotification(window.i18n.t('notifications.admin.parent_album_updated'), 'success');
                await this.refreshAlbumTree();
                await this.loadAlbums();
                await this.app.content.loadAlbumStats();

                // Return to manage modal with updated parent
                this.showAlbumManageModal(albumId, albumName, newParentId || null);

            } catch (error) {
                app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_updating_parent'));
                // Return to manage modal on error
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        });

        document.getElementById('album-parent-cancel').addEventListener('click', () => {
            closeModal();
            this.showAlbumManageModal(albumId, albumName, currentParentId);
        });

        // Close on outside click - return to manage modal
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal();
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        });

        document.addEventListener('keydown', handleEscape);
    },

    async deleteAlbum(albumId, albumName, currentParentId) {
        const modal = new ModalHelper({
            id: 'delete-album-modal',
            type: 'danger',
            title: window.i18n.t('common.delete_album'),
            message: window.i18n.t('modal.delete_album.message', { albumName: escapeHtml(albumName) }),
            confirmText: window.i18n.t('common.yes_delete'),
            cancelText: window.i18n.t('common.cancel'),
            confirmId: 'delete-album-confirm-yes',
            cancelId: 'delete-album-confirm-no',
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/albums/${albumId}?cascade=false`, {
                        method: 'DELETE'
                    });
                    app.showNotification(window.i18n.t('notifications.admin.album_deleted'), 'success');
                    await this.refreshAlbumTree();
                    await this.loadAlbums();
                    await this.app.content.loadAlbumStats();
                    // Don't return to manage modal since album is deleted
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('notifications.admin.error_deleting_album'));
                    // Return to manage modal on error
                    this.showAlbumManageModal(albumId, albumName, currentParentId);
                }
            },
            onCancel: () => {
                // Return to manage modal when cancelled
                this.showAlbumManageModal(albumId, albumName, currentParentId);
            }
        });

        modal.show();
    },
});
