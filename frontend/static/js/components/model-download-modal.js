class ModelDownloadModal {
    constructor(options = {}) {
        this.options = {
            id: 'model-download-modal',
            onSuccess: null,
            onCancel: null,
            onError: null,
            ...options
        };

        this.modal = null;
        this.currentModelName = null;
        this.downloadSizeMb = null;
        this.isCancelled = false;
        this.activeReader = null;
        this.abortController = null;
        this._resolvePromise = null;

        this._unloadHandler = () => this.handleUnload();
        window.addEventListener('beforeunload', this._unloadHandler);
        window.addEventListener('pagehide', this._unloadHandler);
    }

    destroy() {
        window.removeEventListener('beforeunload', this._unloadHandler);
        window.removeEventListener('pagehide', this._unloadHandler);
        if (this.modal) {
            this.modal.destroy();
            this.modal = null;
        }
    }

    cancel() {
        this.isCancelled = true;

        if (this.currentModelName) {
            fetch(`/api/ai-tagger/download/${this.currentModelName}/cancel`, {
                method: 'POST',
                keepalive: true
            }).catch(() => { });
        }

        if (this.activeReader) {
            try {
                this.activeReader.cancel();
            } catch (e) { }
            this.activeReader = null;
        }

        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }

        if (this.modal) {
            this.modal.hide();
        }

        if (this.options.onCancel) {
            this.options.onCancel();
        }

        if (this._resolvePromise) {
            this._resolvePromise(false);
            this._resolvePromise = null;
        }
    }

    handleUnload() {
        this.isCancelled = true;

        if (this.activeReader) {
            try {
                this.activeReader.cancel();
            } catch (e) { }
            this.activeReader = null;
        }

        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    parseSSEEvents(buffer) {
        const events = [];
        const normalized = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        const parts = normalized.split('\n\n');
        const remaining = parts.pop() || '';

        for (const block of parts) {
            for (const line of block.split('\n')) {
                const trimmed = line.trim();
                if (trimmed.startsWith('data:')) {
                    const jsonStr = trimmed.slice(5).trim();
                    try {
                        events.push(JSON.parse(jsonStr));
                    } catch (e) {
                        console.warn('Failed to parse SSE JSON:', jsonStr, e);
                    }
                }
            }
        }

        return { events, remaining };
    }

    handleDownloadStreamEvent(data) {
        const root = this.modal?.modalElement;
        if (!root) return false;

        if (data.type === 'progress') {
            const bar = root.querySelector('.download-progress-bar');
            const bytesText = root.querySelector('.download-bytes-text');
            const speedText = root.querySelector('.download-speed-text');

            const downloadedMB = (data.downloaded_bytes / (1024 * 1024)).toFixed(1);
            const totalMB = data.total_bytes ? (data.total_bytes / (1024 * 1024)).toFixed(1) : (this.downloadSizeMb ? this.downloadSizeMb.toFixed(1) : null);
            const percent = data.percent != null ? data.percent : (totalMB ? Math.round((downloadedMB / totalMB) * 100) : 0);

            if (bar) bar.style.width = `${Math.min(Math.max(percent, 0), 100)}%`;
            if (bytesText) {
                bytesText.textContent = totalMB
                    ? `${downloadedMB} MB / ${totalMB} MB (${percent}%)`
                    : `${downloadedMB} MB`;
            }
            if (speedText && data.speed_bps) {
                const speedMB = (data.speed_bps / (1024 * 1024)).toFixed(1);
                speedText.textContent = `${speedMB} MB/s`;
            }
            return false;
        }

        if (data.type === 'complete') {
            const bar = root.querySelector('.download-progress-bar');
            const bytesText = root.querySelector('.download-bytes-text');
            if (bar) bar.style.width = '100%';
            if (bytesText && this.downloadSizeMb) {
                bytesText.textContent = `${this.downloadSizeMb} MB / ${this.downloadSizeMb} MB (100%)`;
            }
            return true;
        }

        if (data.type === 'cancelled') {
            return false;
        }

        if (data.type === 'error') {
            throw new Error(data.error || 'Failed to download model');
        }

        return false;
    }

    showDownloadingState() {
        const messageHTML = `
            <div class="flex flex-col items-center justify-center text-center">
                <p class="text font-medium mb-1">${window.i18n.t('modal.download_model.download_needed')}</p>
                <p class="text-secondary text-xs mb-4 download-status-text">${window.i18n.t('modal.download_model.download_wait')}</p>
                
                <div class="w-full mb-2">
                    <div class="w-full bg h-2.5 overflow-hidden border border-color">
                        <div class="download-progress-bar h-full bg-primary transition-all duration-150" style="width: 0%;"></div>
                    </div>
                </div>
                
                <div class="w-full flex justify-between text-xs text-secondary mb-2">
                    <span class="download-bytes-text">0 MB / ~${this.downloadSizeMb || 0} MB</span>
                    <span class="download-speed-text">0 MB/s</span>
                </div>
                <p class="text-secondary text-xs mt-2">${window.i18n.t('modal.download_model.model_cached')}</p>
            </div>
        `;

        if (!this.modal) {
            this.modal = new ModalHelper({
                id: this.options.id,
                type: 'primary',
                title: window.i18n.t('modal.download_model.downloading_model'),
                message: messageHTML,
                showIcon: false,
                confirmText: window.i18n.t('common.download'),
                cancelText: window.i18n.t('common.cancel'),
                confirmId: 'download-model-confirm-yes',
                cancelId: 'download-model-confirm-no',
                onCancel: () => this.cancel(),
                closeOnOutsideClick: false
            });
            this.modal.show();
        } else {
            this.modal.updateContent({
                type: 'primary',
                title: window.i18n.t('modal.download_model.downloading_model'),
                message: messageHTML
            });
            this.modal.show();
        }

        // Disable and grey out the confirm button during download
        const confirmBtn = document.getElementById(this.modal.options.confirmId);
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.classList.add('opacity-50', 'cursor-not-allowed', 'pointer-events-none');
        }
    }

    async startDownload() {
        this.showDownloadingState();

        try {
            const response = await fetch(`/api/ai-tagger/download/${this.currentModelName}`, {
                method: 'POST',
                signal: this.abortController ? this.abortController.signal : undefined
            });

            if (this.isCancelled) return;

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || 'Download failed');
            }

            const reader = response.body.getReader();
            this.activeReader = reader;
            const decoder = new TextDecoder();
            let buffer = '';
            let downloadCompleted = false;

            try {
                while (true) {
                    if (this.isCancelled) {
                        try { await reader.cancel(); } catch (e) { }
                        break;
                    }

                    let done, value;
                    try {
                        const res = await reader.read();
                        done = res.done;
                        value = res.value;
                    } catch (e) {
                        break;
                    }

                    if (done) {
                        if (buffer.trim()) {
                            const { events } = this.parseSSEEvents(buffer + '\n\n');
                            for (const data of events) {
                                if (this.handleDownloadStreamEvent(data)) {
                                    downloadCompleted = true;
                                }
                            }
                        }
                        break;
                    }

                    buffer += decoder.decode(value, { stream: true });
                    const { events, remaining } = this.parseSSEEvents(buffer);
                    buffer = remaining;

                    for (const data of events) {
                        if (this.isCancelled) break;
                        const complete = this.handleDownloadStreamEvent(data);
                        if (complete) {
                            downloadCompleted = true;
                            break;
                        }
                    }
                    if (downloadCompleted) break;
                }
            } finally {
                this.activeReader = null;
            }

            if (!this.isCancelled && downloadCompleted) {
                if (this.modal) {
                    this.modal.destroy();
                    this.modal = null;
                }
                if (this.options.onSuccess) {
                    this.options.onSuccess();
                }
                if (this._resolvePromise) {
                    this._resolvePromise(true);
                    this._resolvePromise = null;
                }
            }
        } catch (e) {
            if (e.name === 'AbortError' || this.isCancelled) return;
            console.error('Error downloading model:', e);
            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(window.i18n.t('notifications.media.error_downloading_ai_model', { error: e.message }), 'error');
            }
            if (this.options.onError) {
                this.options.onError(e);
            }
            this.cancel();
        }
    }

    /**
     * Check if a model is ready, showing confirmation/progress modal if needed.
     * @param {string} modelName
     * @returns {Promise<boolean>}
     */
    async ensureModelReady(modelName) {
        this.currentModelName = modelName;
        this.isCancelled = false;
        this.abortController = new AbortController();

        try {
            const response = await fetch(`/api/ai-tagger/model-status/${modelName}`);
            if (response.ok) {
                const status = await response.json();
                this.downloadSizeMb = status.download_size_mb;

                // If already downloaded or loaded, return true without displaying any modal
                if (!status.is_downloading && (status.is_downloaded || status.is_loaded)) {
                    return true;
                }

                if (status.is_downloading) {
                    return new Promise((resolve) => {
                        this._resolvePromise = resolve;
                        this.startDownload();
                    });
                }
            }
        } catch (e) {
            console.warn('Initial model status check failed:', e);
        }

        return new Promise((resolve) => {
            this._resolvePromise = resolve;

            const confirmMessageHTML = `
                <div class="text-center">
                    <p class="text font-medium mb-1">${window.i18n.t('modal.download_model.download_needed')}</p>
                    <p class="text-secondary text-xs mb-4">${window.i18n.t('modal.download_model.download_wait')}</p>
                    <div class="w-full bg-surface-2 border border-color p-3 text-xs text-left mb-2 space-y-1">
                        <div>${window.i18n.t('common.model')}: <strong>${modelName}</strong></div>
                        <div>${window.i18n.t('modal.download_model.size')}: <strong>~${this.downloadSizeMb || 850} MB</strong></div>
                    </div>
                </div>
            `;

            this.modal = new ModalHelper({
                id: this.options.id,
                type: 'primary',
                title: window.i18n.t('modal.download_model.title'),
                message: confirmMessageHTML,
                showIcon: false,
                confirmText: window.i18n.t('common.download'),
                cancelText: window.i18n.t('common.cancel'),
                confirmId: 'download-model-confirm-yes',
                cancelId: 'download-model-confirm-no',
                onConfirm: () => {
                    this.startDownload();
                },
                onCancel: () => {
                    this.cancel();
                },
                closeOnOutsideClick: false
            });

            this.modal.show();
        });
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = ModelDownloadModal;
}
