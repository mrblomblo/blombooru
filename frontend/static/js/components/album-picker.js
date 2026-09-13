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

        this.modal = null;
        this.tree = null;
    }

    async show() {
        this.createModal();

        this.tree = new window.AlbumTree({
            container: this.modal.querySelector('#album-picker-list'),
            isSelectable: true,
            selectedIds: new Set(this.options.preSelected),
            multiSelect: this.options.multiSelect,
            onRowClick: (album) => {
                const countEl = this.modal.querySelector('#album-picker-selected-status');
                if (countEl) {
                    countEl.textContent = window.i18n.t('album_picker.selected_count', { count: this.tree.options.selectedIds.size });
                }
            }
        });

        await this.tree.loadAlbums();
        this.tree.render();

        const searchInput = this.modal.querySelector('#album-picker-search');
        searchInput.addEventListener('input', (e) => this.tree.handleSearch(e.target.value));
    }

    createModal() {
        // Remove existing modal if any
        const existing = document.getElementById('album-picker-modal');
        if (existing) existing.remove();

        // Create modal structure
        this.modal = document.createElement('div');
        this.modal.id = 'album-picker-modal';
        this.modal.className = 'modal flex items-center justify-center';
        this.modal.style.display = 'flex';

        this.modal.innerHTML = `
            <div class="modal-content surface border p-4 max-w-150 w-[90%] max-h-[80vh] flex flex-col">
                <div class="flex items-center mb-4 pb-3 border-b">
                    <h3 class="text-base font-bold">${this.options.title}</h3>
                </div>

                <div class="mb-3">
                    <input type="text" id="album-picker-search" placeholder="${window.i18n.t('common.search_albums_placeholder')}"
                        class="w-full bg px-3 py-2 border text-xs focus:outline-none focus:border-primary">
                </div>

                <div id="album-picker-list" class="flex-1 overflow-y-auto mb-4 bg border min-h-75">
                    <div class="h-full min-h-75 flex flex-col items-center justify-center text-secondary">
                        <div class="spinner"></div>
                        <p class="text-secondary mt-2 text-xs">${window.i18n.t('common.loading')}</p>
                    </div>
                </div>

                <div id="album-picker-selected-status" class="text-xs text-secondary mb-3">
                    ${window.i18n.t('album_picker.selected_count', { count: this.options.preSelected.length })}
                </div>

                <div class="flex gap-2 justify-end">
                    <button id="album-picker-confirm" class="btn-primary cursor-pointer">${window.i18n.t('common.confirm')}</button>
                    <button id="album-picker-cancel" class="btn-dark cursor-pointer">${window.i18n.t('common.cancel')}</button>
                </div>
            </div>
        `;

        document.body.appendChild(this.modal);

        // Event listeners
        this.modal.querySelector('#album-picker-cancel').addEventListener('click', () => this.hide());
        this.modal.querySelector('#album-picker-confirm').addEventListener('click', () => this.confirm());

        // Close on outside click
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) this.hide();
        });

        // Prevent modal from closing when clicking inside content
        this.modal.querySelector('.modal-content').addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    confirm() {
        const selectedIds = Array.from(this.tree.options.selectedIds);
        const selectedAlbums = this.tree.albums.filter(a => selectedIds.includes(a.id));

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

window.AlbumPicker = AlbumPicker;
