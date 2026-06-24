class UrlImporter {
    constructor(uploader) {
        this.uploader = uploader;
        this.currentMedia = null;
        this.isFetching = false;
        this.isAdding = false;

        this.container = document.getElementById('url-import-section');
        if (this.container) {
            this.init();
        }
    }

    init() {
        this.urlInput = this.container.querySelector('#url-import-input');
        this.fetchBtn = this.container.querySelector('#url-import-fetch-btn');
        this.previewArea = this.container.querySelector('#url-import-preview-area');
        this.statusArea = this.container.querySelector('#url-import-status');

        if (this.fetchBtn) {
            this.fetchBtn.addEventListener('click', () => this.fetchMedia());
        }

        if (this.urlInput) {
            this.urlInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.fetchMedia();
                }
            });

            this.urlInput.addEventListener('paste', () => {
                setTimeout(() => this.fetchMedia(), 100);
            });
        }
    }

    showStatus(message, type = 'info') {
        if (!this.statusArea) return;
        const colorClass = type === 'error' ? 'text-danger' : type === 'success' ? 'text-success' : 'text-secondary';
        this.statusArea.innerHTML = `<p class="text-xs ${colorClass}">${message}</p>`;
        this.statusArea.style.display = 'block';
    }

    clearStatus() {
        if (!this.statusArea) return;
        this.statusArea.style.display = 'none';
        this.statusArea.innerHTML = '';
    }

    hidePreview() {
        if (this.previewArea) {
            this.previewArea.style.display = 'none';
            this.previewArea.innerHTML = '';
        }
    }

    _t(keyOrString) {
        if (!keyOrString) return '';
        if (keyOrString.includes(':::')) {
            const [key, arg] = keyOrString.split(':::');
            return window.i18n.t(key, { error: arg });
        }
        return window.i18n.t(keyOrString);
    }

    async fetchMedia() {
        const url = this.urlInput?.value?.trim();
        if (!url) return;

        if (this.isFetching) return;
        this.isFetching = true;
        this.clearStatus();
        this.hidePreview();

        this.showStatus(window.i18n.t('admin.media_management.url_import.fetching'), 'info');
        this.fetchBtn.disabled = true;

        try {
            const response = await fetch('/api/media/url-import/fetch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || window.i18n.t('admin.media_management.url_import.fetch_error'));
            }

            this.currentMedia = await response.json();
            this.renderPreview(this.currentMedia);
            this.clearStatus();
        } catch (e) {
            console.error('URL import fetch error:', e);
            this.showStatus(
                window.i18n.t('admin.media_management.url_import.fetch_error') + ': ' + this._t(e.message),
                'error'
            );
        } finally {
            this.isFetching = false;
            this.fetchBtn.disabled = false;
        }
    }

    renderPreview(media) {
        if (!this.previewArea) return;

        const proxyUrl = `/api/media/url-import/proxy?url=${encodeURIComponent(media.file_url)}`;
        const skeletonStyle = "background-image: linear-gradient(90deg, var(--surface) 0%, color-mix(in srgb, var(--surface-light), var(--surface) 40%) 50%, var(--surface) 100%); background-size: 200% 100%; animation: skeleton-wave 2s infinite linear;";
        const clearSkeleton = "this.closest('#url-import-thumb-wrap').style.animation='none'; this.closest('#url-import-thumb-wrap').style.backgroundImage='none';";

        const previewHtml = media.is_video
            ? `<div class="w-32 h-32 surface border relative overflow-hidden" style="${skeletonStyle}" id="url-import-thumb-wrap">
                    <video src="${proxyUrl}" class="w-full h-full object-contain opacity-0 transition-opacity duration-300" muted
                        onloadeddata="this.style.opacity='1'; ${clearSkeleton}"
                        onerror="this.style.display='none'; ${clearSkeleton}"></video>
               </div>`
            : `<div class="w-32 h-32 surface border relative overflow-hidden" style="${skeletonStyle}" id="url-import-thumb-wrap">
                    <img src="${proxyUrl}" alt="Preview" class="w-full h-full object-contain opacity-0 transition-opacity duration-300"
                        onload="this.style.opacity='1'; ${clearSkeleton}"
                        onerror="this.style.display='none'; ${clearSkeleton}">
               </div>`;

        this.previewArea.innerHTML = `
            <div class="bg surface border p-4">
                <div class="flex flex-col sm:flex-row gap-4">
                    <div class="flex-shrink-0">
                        ${previewHtml}
                    </div>
                    <div class="flex-1 min-w-0 text-xs space-y-2">
                        <div><strong>${window.i18n.t('admin.media_management.url_import.filename')}:</strong> ${this.escapeHtml(media.filename)}</div>
                        <div><strong>${window.i18n.t('admin.media_management.url_import.file_type')}:</strong> ${this.escapeHtml(media.content_type)}</div>
                        <div><strong>${window.i18n.t('admin.media_management.url_import.file_size')}:</strong> ${this.formatFileSize(media.file_size)}</div>
                        <div class="break-all"><strong>${window.i18n.t('admin.media_management.url_import.source')}:</strong> ${this.escapeHtml(this.truncateUrl(media.file_url, 80))}</div>
                    </div>
                </div>
                <div class="flex flex-col sm:flex-row gap-2 mt-4">
                    <button id="url-import-cancel-btn" class="btn-danger px-4 py-2 font-medium">
                        ${window.i18n.t('common.cancel')}
                    </button>
                    <button id="url-import-queue-btn" class="btn-primary flex-1 px-4 py-2 font-medium">
                        ${window.i18n.t('admin.media_management.url_import.add_to_queue')}
                    </button>
                </div>
            </div>
        `;

        this.previewArea.style.display = 'block';

        this.previewArea.querySelector('#url-import-cancel-btn')?.addEventListener('click', () => {
            this.hidePreview();
            this.currentMedia = null;
        });

        this.previewArea.querySelector('#url-import-queue-btn')?.addEventListener('click', () => {
            this.addToQueue();
        });

        const previewEl = this.previewArea.querySelector('#url-import-thumb-wrap img, #url-import-thumb-wrap video');
        if (previewEl) {
            previewEl.style.cursor = 'pointer';
            previewEl.addEventListener('click', () => {
                if (this.uploader && this.uploader.fullscreenViewer) {
                    this.uploader.fullscreenViewer.open(proxyUrl, media.is_video);
                }
            });
        }
    }

    async addToQueue() {
        if (!this.currentMedia || !this.uploader || this.isAdding) return;

        const media = this.currentMedia;
        const queueBtn = this.previewArea?.querySelector('#url-import-queue-btn');

        this.isAdding = true;
        if (queueBtn) {
            queueBtn.disabled = true;
            queueBtn.textContent = window.i18n.t('common.loading');
        }

        try {
            const proxyUrl = `/api/media/url-import/proxy?url=${encodeURIComponent(media.file_url)}`;
            const response = await fetch(proxyUrl);

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || window.i18n.t('admin.media_management.url_import.download_error'));
            }

            const blob = await response.blob();
            const mimeType = media.content_type || blob.type;
            const file = new File([blob], media.filename, { type: mimeType });

            if (!this.uploader.isValidFile(file)) {
                throw new Error(window.i18n.t('admin.media_management.url_import.error_unsupported_type'));
            }

            const hash = await this.uploader.computeFileHash(file);
            if (this.uploader.fileHashes.has(hash)) {
                this.showStatus(window.i18n.t('admin.media_management.url_import.already_in_queue'), 'error');
                return;
            }

            await this.uploader.addBooruImport(file, {
                rating: this.uploader.baseRating,
                source: media.file_url,
                tags: [],
            });

            this.showStatus(
                window.i18n.t('admin.media_management.url_import.added_to_queue'),
                'success'
            );

            this.hidePreview();
            this.currentMedia = null;
            if (this.urlInput) this.urlInput.value = '';
        } catch (e) {
            console.error('URL import queue error:', e);
            this.showStatus(this._t(e.message), 'error');
        } finally {
            this.isAdding = false;
            if (queueBtn) {
                queueBtn.disabled = false;
                queueBtn.textContent = window.i18n.t('admin.media_management.url_import.add_to_queue');
            }
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    truncateUrl(url, maxLen = 30) {
        try {
            const parsed = new URL(url);
            const display = parsed.hostname + parsed.pathname;
            return display.length > maxLen ? display.substring(0, maxLen) + '…' : display;
        } catch {
            return url.length > maxLen ? url.substring(0, maxLen) + '…' : url;
        }
    }

    formatFileSize(bytes) {
        if (!bytes) return '—';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }
}

function initUrlImporter() {
    if (document.getElementById('url-import-section')) {
        window.urlImporter = new UrlImporter(window.uploaderInstance);
    }
}

if (document.getElementById('url-import-section')) {
    if (window.uploaderInstance) {
        initUrlImporter();
    } else {
        const checkInterval = setInterval(() => {
            if (window.uploaderInstance) {
                clearInterval(checkInterval);
                initUrlImporter();
            }
        }, 50);
    }
}
