class UpdatePostModalBase {
    constructor(mediaId, currentMedia) {
        this.mediaId = mediaId;
        this.currentMedia = currentMedia;

        this._modal = null;
        this._escapeHandler = null;
        this._fullscreenViewer = null;
    }

    hide() {
        if (this._modal) {
            this._modal.remove();
            this._modal = null;
        }
        if (this._escapeHandler) {
            document.removeEventListener('keydown', this._escapeHandler);
            this._escapeHandler = null;
        }
    }

    _registerEscapeHandler(onEscape) {
        this._escapeHandler = (e) => {
            if (e.key !== 'Escape' || !this._modal) return;
            const overlay = document.getElementById('fullscreen-overlay');
            if (overlay && overlay.classList.contains('active')) return;
            onEscape();
        };
        document.addEventListener('keydown', this._escapeHandler);
    }

    _openFullscreen(src, isVideo = false) {
        if (!this._fullscreenViewer) {
            this._fullscreenViewer = new FullscreenMediaViewer();
        }
        this._fullscreenViewer.open(src, isVideo);
    }

    _checkboxRow(id, label, checked) {
        return `
            <label class="w-full cursor-pointer" for="${id}">
                <input id="${id}" type="checkbox" class="peer hidden" ${checked ? 'checked' : ''}>
                <span class="block w-full p-1 bg border text-xs text-center cursor-pointer hover:border-primary transition-colors select-none peer-checked:bg-primary peer-checked:border-primary peer-checked:text-[var(--primary-text)] peer-checked:hover:bg-[var(--primary-hover)]">
                    ${label}
                </span>
            </label>`;
    }
}
