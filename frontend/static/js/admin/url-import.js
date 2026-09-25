class UrlImporter {
    constructor(uploader) {
        this.uploader = uploader;
        this.isFetching = false;
        this.abortController = null;

        this.container = document.getElementById('url-import-section');
        if (this.container) {
            this.init();
        }
    }

    init() {
        this.urlInput = this.container.querySelector('#url-import-input');
        this.fetchBtn = this.container.querySelector('#url-import-fetch-btn');
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

    cancel() {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
        this.isFetching = false;
        if (this.fetchBtn) this.fetchBtn.disabled = false;
        this.clearStatus();
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

    async importSingleUrl(url, signal = null) {
        const fetchSignal = signal || this.abortController?.signal || this.uploader?.uploadAbortController?.signal;

        const response = await fetch('/api/media/url-import/fetch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
            signal: fetchSignal,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            if (response.status === 403 || (error.detail && error.detail.includes('403'))) {
                throw new Error('errors.error_403');
            }
            throw new Error(error.detail || 'admin.media_management.url_import.fetch_error');
        }

        const media = await response.json();
        await this.addToQueue(media, fetchSignal);
    }

    async fetchMedia() {
        const url = this.urlInput?.value?.trim();
        if (!url) return;

        if (this.isFetching) return;
        this.isFetching = true;
        this.clearStatus();

        this.abortController = new AbortController();
        const signal = this.abortController.signal;

        this.showStatus(window.i18n.t('admin.media_management.url_import.fetching'), 'info');
        this.fetchBtn.disabled = true;

        try {
            await this.importSingleUrl(url, signal);
            if (signal.aborted || this.uploader?.isAborted?.()) {
                this.clearStatus();
                return;
            }
            this.showStatus(window.i18n.t('admin.media_management.url_import.added_to_queue'), 'success');
            if (this.urlInput) this.urlInput.value = '';

        } catch (e) {
            if (e.name === 'AbortError' || signal.aborted || this.uploader?.isAborted?.()) {
                this.clearStatus();
                return;
            }
            console.error('URL import fetch error:', e);
            // Some errors are just simple strings, others are translation keys
            let errorMsg = e.message;
            if (errorMsg.includes('.') && !errorMsg.includes(' ')) {
                errorMsg = window.i18n.t(errorMsg) || errorMsg;
            } else if (errorMsg && errorMsg !== '') {
                // Might be literal error from API, try translating it if possible, else use literal
                errorMsg = window.i18n.t(errorMsg) === errorMsg ? errorMsg : window.i18n.t(errorMsg);
            }
            this.showStatus(errorMsg, 'error');
        } finally {
            this.isFetching = false;
            if (this.fetchBtn) this.fetchBtn.disabled = false;
            this.abortController = null;
        }
    }

    async importFromTextFile(file, externalSignal = null) {
        if (!file) return;
        if (this.isFetching) return;
        this.isFetching = true;
        this.clearStatus();
        if (this.fetchBtn) this.fetchBtn.disabled = true;

        this.abortController = new AbortController();
        const signal = externalSignal || this.abortController.signal;

        try {
            const content = await file.text();
            if (signal.aborted || this.uploader?.isAborted?.()) return;

            const lines = content.split(/\r?\n/)
                .map(line => line.trim())
                .filter(line => line && !line.startsWith('#'));

            if (lines.length === 0) {
                return;
            }

            let successCount = 0;
            let failedCount = 0;
            const total = lines.length;

            for (let i = 0; i < total; i++) {
                if (signal.aborted || this.uploader?.isAborted?.()) {
                    break;
                }
                const url = lines[i];
                this.showStatus(`${window.i18n.t('admin.media_management.url_import.fetching')} (${i + 1}/${total})`, 'info');
                try {
                    await this.importSingleUrl(url, signal);
                    successCount++;
                } catch (e) {
                    if (e.name === 'AbortError' || signal.aborted || this.uploader?.isAborted?.()) {
                        break;
                    }
                    console.error(`Failed to import URL from batch: ${url}`, e);
                    failedCount++;
                }
            }

            if (signal.aborted || this.uploader?.isAborted?.()) {
                this.clearStatus();
                return;
            }

            if (successCount > 0) {
                this.showStatus(window.i18n.t('admin.media_management.url_import.added_to_queue'), 'success');
            } else {
                this.clearStatus();
            }

            if (failedCount > 0) {
                if (window.app && window.app.showNotification) {
                    window.app.showNotification(
                        window.i18n.t('admin.media_management.url_import.batch_failed', { count: failedCount }),
                        'error'
                    );
                }
            }
        } catch (e) {
            if (e.name === 'AbortError' || signal.aborted || this.uploader?.isAborted?.()) {
                this.clearStatus();
                return;
            }
            console.error('Error processing batch URL file:', e);
            if (window.app && window.app.showNotification) {
                window.app.showNotification(
                    window.i18n.t('admin.media_management.url_import.batch_failed', { count: 1 }),
                    'error'
                );
            }
        } finally {
            this.isFetching = false;
            if (this.fetchBtn) this.fetchBtn.disabled = false;
            this.abortController = null;
        }
    }

    async addToQueue(media, signal = null) {
        if (!media || !this.uploader) return;
        const fetchSignal = signal || this.abortController?.signal || this.uploader?.uploadAbortController?.signal;

        const proxyUrl = `/api/media/url-import/proxy?url=${encodeURIComponent(media.file_url)}`;
        const response = await fetch(proxyUrl, { signal: fetchSignal });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'admin.media_management.url_import.download_error');
        }

        const blob = await response.blob();
        const mimeType = media.content_type || blob.type || "application/octet-stream";
        let filename = media.filename || "downloaded_media";
        const file = new File([blob], filename, { type: mimeType });

        if (!this.uploader.isValidFile(file)) {
            throw new Error('admin.media_management.url_import.error_unsupported_type');
        }

        let importOptions = {
            rating: this.uploader.baseRating,
            source: media.file_url,
            tags: [],
        };

        if (media.is_booru_post) {
            const tags = [];
            const categoryHints = {};
            if (media.tags) {
                for (const t of media.tags) {
                    tags.push(t.name);
                    categoryHints[t.name.toLowerCase()] = t.category;
                }
            }

            importOptions = {
                rating: media.rating,
                source: media.source || media.booru_url,
                description: media.description,
                tags: tags,
                categoryHints: categoryHints,
                userAssignedTags: [],
                autoCreateTags: false,
            };
        }

        await this.uploader.addBooruImport(file, importOptions, { signal: fetchSignal });
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
