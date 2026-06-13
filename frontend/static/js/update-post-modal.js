class UpdatePostModal extends UpdatePostModalBase {
    constructor(mediaId, currentMedia) {
        super(mediaId, currentMedia);
        this._urlImport = null;
        this._deviceUpload = null;
    }

    show() {
        this._buildSourcePicker();
    }

    // ==================== Layer 1: Source picker ====================

    _buildSourcePicker() {
        this.hide();

        const modal = document.createElement('div');
        modal.id = 'update-post-modal';
        modal.className = 'fixed inset-0 flex items-center justify-center z-50';
        modal.style.background = 'rgba(0, 0, 0, 0.5)';

        modal.innerHTML = `
            <div class="surface p-2 sm:p-6 border shadow-2xl w-full max-w-sm mx-4 relative">
                <div class="flex items-center mb-4 flex-shrink-0">
                    <h2 class="text-base sm:text-lg font-bold truncate">${this._t('media.actions.update_post')}</h2>
                </div>

                <div class="flex flex-col gap-3">
                    <button class="action-btn text-left px-4 py-4 bg hover:border-primary hover:text-primary transition-colors border flex items-center gap-3" data-action="url">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
                            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
                        </svg>
                        <div class="flex-1">
                            <div class="font-bold text-sm">${this._t('modal.update_post.from_url')}</div>
                            <div class="text-xs opacity-70">${this._t('modal.update_post.from_url_desc')}</div>
                        </div>
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="opacity-50">
                            <polyline points="9 18 15 12 9 6"></polyline>
                        </svg>
                    </button>

                    <button class="action-btn text-left px-4 py-4 bg hover:border-primary hover:text-primary transition-colors border flex items-center gap-3" data-action="device">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="17 8 12 3 7 8"></polyline>
                            <line x1="12" y1="3" x2="12" y2="15"></line>
                        </svg>
                        <div class="flex-1">
                            <div class="font-bold text-sm">${this._t('modal.update_post.from_device')}</div>
                            <div class="text-xs opacity-70">${this._t('modal.update_post.from_device_desc')}</div>
                        </div>
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="opacity-50">
                            <polyline points="9 18 15 12 9 6"></polyline>
                        </svg>
                    </button>
                </div>
                <div class="flex gap-2 mt-4">
                    <button class="close-btn flex-1 px-4 py-2 border bg hover:border-primary hover:text-primary text text-xs transition-colors">${this._t('common.close')}</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this._modal = modal;
        document.body.style.overflow = 'hidden';

        modal.addEventListener('click', (e) => {
            if (e.target.closest('.close-btn') || e.target === modal) {
                this.hide();
                document.body.style.overflow = '';
                return;
            }

            const btn = e.target.closest('.action-btn');
            if (btn) {
                const action = btn.dataset.action;
                if (action === 'url') {
                    this._showUrlImport();
                } else if (action === 'device') {
                    this._showDeviceUpload();
                }
            }
        });

        this._registerEscapeHandler(() => {
            this.hide();
            document.body.style.overflow = '';
        });
    }

    // ==================== Layer 2 delegation ====================

    _showUrlImport() {
        if (!this._urlImport) {
            this._urlImport = new UpdatePostUrlImport(this.mediaId, this.currentMedia);
        }
        this._urlImport._fullscreenViewer = this._fullscreenViewer;

        this._urlImport.build(() => {
            this._fullscreenViewer = this._urlImport._fullscreenViewer;
            this._buildSourcePicker();
        });
    }

    _showDeviceUpload() {
        if (!this._deviceUpload) {
            this._deviceUpload = new UpdatePostDeviceUpload(this.mediaId, this.currentMedia);
        }
        this._deviceUpload._fullscreenViewer = this._fullscreenViewer;

        this._deviceUpload.build(() => {
            this._fullscreenViewer = this._deviceUpload._fullscreenViewer;
            this._buildSourcePicker();
        });
    }
}
