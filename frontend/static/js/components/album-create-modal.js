class AlbumCreateModal {
    constructor(options = {}) {
        this.options = {
            albums: options.albums || null,
            parentAlbumId: options.parentAlbumId || '',
            zIndex: options.zIndex || 1010,
            onCreated: options.onCreated || (() => { }),
            onClose: options.onClose || (() => { }),
            ...options
        };

        this.modal = null;
        this.parentSelect = null;
        this._escapeHandler = null;
        this._isClosing = false;
    }

    async show() {
        // Remove existing modal if any
        const existing = document.getElementById('album-create-modal');
        if (existing) existing.remove();

        this.modal = document.createElement('div');
        this.modal.id = 'album-create-modal';
        this.modal.className = 'modal flex items-center justify-center';
        this.modal.style.display = 'flex';
        this.modal.style.zIndex = this.options.zIndex.toString();

        const noneRootText = window.i18n.t('admin.albums_management.none_root');

        this.modal.innerHTML = `
            <div class="modal-content surface border p-4 max-w-md w-[90%] flex flex-col">
                <div class="flex items-center mb-4 pb-3 border-b">
                    <h3 class="text-base font-bold">${window.i18n.t('admin.albums_management.create_album')}</h3>
                </div>

                <form id="album-picker-create-form">
                    <div class="mb-3">
                        <label class="block text-xs font-bold mb-2">
                            ${window.i18n.t('admin.albums_management.album_name')}
                        </label>
                        <input type="text" id="album-create-name-input" required
                            class="w-full bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary"
                            placeholder="${window.i18n.t('admin.albums_management.album_name_placeholder')}"
                            autocomplete="off">
                    </div>

                    <div class="mb-4" id="album-create-parent-container">
                        <label class="block text-xs font-bold mb-2">
                            ${window.i18n.t('admin.albums_management.parent_album')}
                        </label>
                        <div id="album-create-parent-select" class="custom-select w-full" data-value="${this.options.parentAlbumId || ''}">
                            <button
                                class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors focus:border-primary"
                                type="button">
                                <span class="custom-select-value text">
                                    ${noneRootText}
                                </span>
                                ${window.Icons.selectArrow({ size: 12 })}
                            </button>
                            <div class="custom-select-dropdown bg border border-primary max-h-60 overflow-y-auto shadow-lg">
                                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs selected"
                                    data-value="">${noneRootText}</div>
                            </div>
                        </div>
                    </div>

                    <div class="flex gap-2 justify-end">
                        <button type="submit" id="album-create-submit" class="btn-primary cursor-pointer">
                            ${window.i18n.t('admin.albums_management.create_album')}
                        </button>
                        <button type="button" id="album-create-cancel" class="btn-dark cursor-pointer">
                            ${window.i18n.t('common.cancel')}
                        </button>
                    </div>
                </form>
            </div>
        `;

        document.body.appendChild(this.modal);

        const parentSelectEl = this.modal.querySelector('#album-create-parent-select');
        if (typeof CustomSelect !== 'undefined' && parentSelectEl) {
            this.parentSelect = new CustomSelect(parentSelectEl);
        }

        await this.loadParentAlbums();

        const nameInput = this.modal.querySelector('#album-create-name-input');
        setTimeout(() => nameInput?.focus(), 50);

        this._escapeHandler = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                this.close();
            }
        };
        document.addEventListener('keydown', this._escapeHandler);

        this.modal.querySelector('#album-create-cancel').addEventListener('click', () => this.close());

        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.close();
            }
        });

        this.modal.querySelector('.modal-content').addEventListener('click', (e) => {
            e.stopPropagation();
        });

        const form = this.modal.querySelector('#album-picker-create-form');
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.submit();
        });
    }

    async loadParentAlbums() {
        let albums = this.options.albums;
        if (!albums || albums.length === 0) {
            try {
                const response = await fetch('/api/albums/tree');
                if (response.ok) {
                    const data = await response.json();
                    albums = data.items || [];
                }
            } catch (e) {
                console.error('Error loading albums for parent select:', e);
                albums = [];
            }
        }

        const parentContainer = this.modal?.querySelector('#album-create-parent-container');
        if (!albums || albums.length === 0) {
            if (parentContainer) parentContainer.style.display = 'none';
        } else {
            if (parentContainer) parentContainer.style.display = 'block';
            const noneRootText = window.i18n.t('admin.albums_management.none_root');
            const options = [
                { value: '', text: noneRootText, selected: !this.options.parentAlbumId }
            ];

            for (const album of albums) {
                const isSelected = !!(this.options.parentAlbumId && album.id.toString() === this.options.parentAlbumId.toString());
                options.push({
                    value: album.id.toString(),
                    text: album.name,
                    selected: isSelected
                });
            }

            if (this.parentSelect) {
                this.parentSelect.setOptions(options);
                if (this.options.parentAlbumId) {
                    this.parentSelect.setValue(this.options.parentAlbumId.toString());
                }
            }
        }
    }

    async submit() {
        const nameInput = this.modal?.querySelector('#album-create-name-input');
        const albumName = nameInput ? nameInput.value.trim() : '';

        if (!albumName) {
            app.showNotification(window.i18n.t('notifications.admin.enter_album_name'), 'error');
            return;
        }

        const parentSelectEl = this.modal?.querySelector('#album-create-parent-select');
        const parentId = parentSelectEl ? parentSelectEl.dataset.value : '';

        const albumData = {
            name: albumName,
            parent_album_id: parentId ? parseInt(parentId) : null
        };

        const submitBtn = this.modal?.querySelector('#album-create-submit');
        if (submitBtn) submitBtn.disabled = true;

        try {
            let result = null;

            result = await app.apiCall('/api/albums', {
                method: 'POST',
                body: JSON.stringify(albumData)
            });

            app.showNotification(window.i18n.t('notifications.admin.album_created'), 'success');

            if (typeof this.options.onCreated === 'function') {
                this.options.onCreated(result);
            }

            this.close(result);
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_creating_album'));
        } finally {
            if (submitBtn) submitBtn.disabled = false;
        }
    }

    close(result = null) {
        if (this._isClosing) return;
        this._isClosing = true;

        if (this._escapeHandler) {
            document.removeEventListener('keydown', this._escapeHandler);
            this._escapeHandler = null;
        }

        if (this.parentSelect) {
            this.parentSelect.destroy();
            this.parentSelect = null;
        }

        if (this.modal) {
            this.modal.remove();
            this.modal = null;
        }

        if (typeof this.options.onClose === 'function') {
            this.options.onClose(result);
        }
    }

    static async show(options = {}) {
        return new Promise((resolve) => {
            const modal = new AlbumCreateModal({
                ...options,
                onCreated: (album) => {
                    if (options.onCreated) options.onCreated(album);
                    resolve(album);
                },
                onClose: (result) => {
                    if (options.onClose) options.onClose(result);
                    if (!result) resolve(null);
                }
            });
            modal.show();
        });
    }
}

window.AlbumCreateModal = AlbumCreateModal;
