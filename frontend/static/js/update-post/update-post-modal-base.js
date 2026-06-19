class UpdatePostModalBase {
    constructor(mediaId, currentMedia) {
        this.mediaId = mediaId;
        this.currentMedia = currentMedia;

        this._modal = null;
        this._escapeHandler = null;
        this._fullscreenViewer = null;
    }

    _t(keyOrString, vars) {
        if (!window.i18n || !keyOrString) return keyOrString || '';
        if (typeof keyOrString === 'string' && keyOrString.includes(':::')) {
            const [key, arg] = keyOrString.split(':::');
            return window.i18n.t(key, { error: arg });
        }
        return window.i18n.t(keyOrString, vars);
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

    _escapeHtml(str) {
        if (str === null || str === undefined) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    _checkboxRow(id, label, checked) {
        return `
            <label class="flex items-center gap-2 cursor-pointer text-sm" for="${id}">
                <input id="${id}" type="checkbox" class="w-4 h-4 accent-primary" ${checked ? 'checked' : ''}>
                ${label}
            </label>`;
    }

    _formatFileSize(bytes) {
        if (!bytes) return '...';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }
}
