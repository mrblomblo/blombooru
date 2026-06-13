class UpdatePostDeviceUpload extends UpdatePostModalBase {
    constructor(mediaId, currentMedia) {
        super(mediaId, currentMedia);

        this.CHUNK_SIZE = 10 * 1024 * 1024; // 10 MB

        this._deviceFile = null;
        this._isUploading = false;
    }

    build(onBack) {
        this.hide();
        this._deviceFile = null;
        this._onBack = onBack;

        const modal = document.createElement('div');
        modal.id = 'update-post-modal';
        modal.className = 'fixed inset-0 flex items-end sm:items-center justify-center z-50';
        modal.style.background = 'rgba(0, 0, 0, 0.5)';

        modal.innerHTML = `
            <div class="surface w-full h-full sm:h-auto sm:max-h-[85vh] sm:max-w-lg sm:mx-4 flex flex-col border-t sm:border shadow-2xl safe-area-bottom">
                <!-- Header -->
                <div class="flex items-center p-4 border-b border-color flex-shrink-0">
                    <h2 class="text-base sm:text-lg font-bold truncate">${this._t('modal.update_post.from_device')}</h2>
                </div>

                <!-- Body -->
                <div class="flex-1 overflow-auto p-4">
                    <!-- Drop zone -->
                    <div id="upm-drop-zone" class="upload-area bg flex flex-col items-center justify-center gap-2 p-6 mb-3" style="min-height:120px;">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-secondary">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="17 8 12 3 7 8"></polyline>
                            <line x1="12" y1="3" x2="12" y2="15"></line>
                        </svg>
                        <p id="upm-drop-label" class="text-xs text-secondary text-center">
                            ${this._t('modal.update_post.drop_file_here')}
                        </p>
                        <!-- accept restricts to image/video only; no directory selection -->
                        <input id="upm-file-input" type="file" accept="image/*,video/*" style="display:none;">
                    </div>

                    <!-- File preview -->
                    <div id="upm-device-preview" style="display:none;" class="mb-3 flex justify-center">
                        <img id="upm-device-preview-img" src="" alt="Preview"
                            class="max-h-48 max-w-full object-contain surface border cursor-pointer"
                            style="display:none;">
                        <video id="upm-device-preview-video" src="" controls
                            class="max-h-48 max-w-full object-contain surface border cursor-pointer"
                            style="display:none;"></video>
                    </div>

                    <!-- Progress bar -->
                    <div id="upm-device-progress-wrap" style="display:none;" class="mb-3">
                        <div class="w-full bg h-1.5 border overflow-hidden">
                            <div id="upm-device-progress-bar" class="h-full bg-primary transition-all" style="width:0%"></div>
                        </div>
                        <p id="upm-device-progress-text" class="text-xs text-secondary mt-1"></p>
                    </div>
                </div>

                <!-- Footer -->
                <div class="flex-shrink-0 p-4 border-t border-color surface">
                    <div class="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3">
                        <div class="flex gap-2 sm:ml-auto">
                            <button id="upm-device-apply" class="flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn-primary text-sm font-medium" disabled>
                                ${this._t('modal.update_post.apply')}
                            </button>
                            <button id="upm-device-cancel" class="flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn text-sm font-medium">
                                ${this._t('common.cancel')}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this._modal = modal;
        document.body.style.overflow = 'hidden';

        const q = (sel) => modal.querySelector(sel);

        q('#upm-device-cancel').addEventListener('click', () => this._onBack());

        const deviceImg = q('#upm-device-preview-img');
        if (deviceImg) {
            deviceImg.addEventListener('click', () => {
                if (deviceImg.src) this._openFullscreen(deviceImg.src, false);
            });
        }

        const dropZone = q('#upm-drop-zone');
        const fileInput = q('#upm-file-input');

        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            const file = e.dataTransfer?.files?.[0];
            // Reject directories and zip/archive files
            if (file && this._isAcceptableFile(file)) this._setDeviceFile(file);
        });
        fileInput.addEventListener('change', () => {
            const file = fileInput.files?.[0];
            if (file && this._isAcceptableFile(file)) this._setDeviceFile(file);
        });

        q('#upm-device-apply').addEventListener('click', () => this._applyFromDevice());

        this._registerEscapeHandler(() => this._onBack());
    }

    _isAcceptableFile(file) {
        return file.type.startsWith('image/') || file.type.startsWith('video/');
    }

    _setDeviceFile(file) {
        this._deviceFile = file;

        const label = this._modal?.querySelector('#upm-drop-label');
        const apply = this._modal?.querySelector('#upm-device-apply');
        const preview = this._modal?.querySelector('#upm-device-preview');
        const img = this._modal?.querySelector('#upm-device-preview-img');
        const video = this._modal?.querySelector('#upm-device-preview-video');

        if (label) label.textContent = this._t('modal.update_post.file_selected', { name: file.name });
        if (apply) apply.disabled = false;

        if (preview && img && video) {
            const url = URL.createObjectURL(file);
            if (file.type.startsWith('video/')) {
                img.style.display = 'none';
                img.src = '';
                video.src = url;
                video.style.display = '';
            } else {
                video.style.display = 'none';
                video.src = '';
                img.src = url;
                img.style.display = '';
            }
            preview.style.display = '';
        }
    }

    _setProgress(pct, text) {
        const wrap = this._modal?.querySelector('#upm-device-progress-wrap');
        const bar = this._modal?.querySelector('#upm-device-progress-bar');
        const lbl = this._modal?.querySelector('#upm-device-progress-text');
        if (wrap) wrap.style.display = '';
        if (bar) bar.style.width = `${pct}%`;
        if (lbl) lbl.textContent = text;
    }

    async _applyFromDevice() {
        if (this._isUploading || !this._deviceFile) return;

        this._isUploading = true;
        const applyBtn = this._modal?.querySelector('#upm-device-apply');
        if (applyBtn) {
            applyBtn.disabled = true;
            applyBtn.textContent = this._t('modal.update_post.applying');
        }

        const file = this._deviceFile;
        const totalChunks = Math.ceil(file.size / this.CHUNK_SIZE);
        let uploadId = null;

        try {
            for (let i = 0; i < totalChunks; i++) {
                const start = i * this.CHUNK_SIZE;
                const end = Math.min(start + this.CHUNK_SIZE, file.size);
                const chunk = file.slice(start, end);

                const chunkForm = new FormData();
                chunkForm.append('file', chunk, file.name);
                if (uploadId) chunkForm.append('upload_id', uploadId);
                chunkForm.append('chunk_index', i.toString());
                chunkForm.append('total_chunks', totalChunks.toString());
                chunkForm.append('filename', file.name);

                const pct = Math.round(((i + 1) / totalChunks) * 90);
                this._setProgress(pct, `${i + 1} / ${totalChunks}`);

                const chunkRes = await fetch('/api/media/upload-chunk', {
                    method: 'POST',
                    body: chunkForm
                });

                if (!chunkRes.ok) {
                    const err = await chunkRes.json().catch(() => ({ detail: chunkRes.statusText }));
                    throw new Error(`Chunk ${i + 1}/${totalChunks}: ${err.detail || chunkRes.statusText}`);
                }

                const chunkData = await chunkRes.json();
                if (i === 0) uploadId = chunkData.upload_id;
            }

            // Finalize
            this._setProgress(95, this._t('modal.update_post.applying'));

            const finalizeForm = new FormData();
            finalizeForm.append('upload_id', uploadId);

            const finalRes = await fetch(`/api/media/${this.mediaId}/update-file-finalize`, {
                method: 'POST',
                body: finalizeForm
            });

            if (!finalRes.ok) {
                const err = await finalRes.json().catch(() => ({ detail: finalRes.statusText }));
                const detail = err.detail || finalRes.statusText;
                if (finalRes.status === 409) {
                    if (detail.includes('identical')) {
                        throw new Error(this._t('modal.update_post.error_identical_file'));
                    }
                    throw new Error(this._t('modal.update_post.error_duplicate_file'));
                }
                throw new Error(detail);
            }

            this._setProgress(100, '');

            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(this._t('modal.update_post.success'), 'success');
            }

            this.hide();
            document.body.style.overflow = '';
            setTimeout(() => window.location.reload(), 800);
        } catch (e) {
            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(this._t(e.message), 'error');
            }
        } finally {
            this._isUploading = false;
            if (applyBtn) {
                applyBtn.disabled = false;
                applyBtn.textContent = this._t('modal.update_post.apply');
            }
        }
    }
}
