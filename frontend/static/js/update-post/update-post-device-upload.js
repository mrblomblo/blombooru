class UpdatePostDeviceUpload extends UpdatePostModalBase {
    constructor(mediaId, currentMedia) {
        super(mediaId, currentMedia);

        this.CHUNK_SIZE = 10 * 1024 * 1024; // 10 MB

        this._deviceFile = null;
        this._objectUrl = null;
        this._detectedWidth = null;
        this._detectedHeight = null;
        this._isUploading = false;
    }

    hide() {
        if (this._objectUrl) {
            URL.revokeObjectURL(this._objectUrl);
            this._objectUrl = null;
        }
        super.hide();
    }

    build(onBack) {
        this.hide();
        this._deviceFile = null;
        this._detectedWidth = null;
        this._detectedHeight = null;
        this._onBack = onBack;

        const cw = this.currentMedia?.width ?? 0;
        const ch = this.currentMedia?.height ?? 0;
        const curFilename = this.currentMedia?.filename || '';
        const curSize = formatFileSize(this.currentMedia?.file_size, 'compact');
        const curThumb = `/api/media/${this.mediaId}/thumbnail${this.currentMedia?.hash ? '?v=' + this.currentMedia.hash : ''}`;
        const curFileUrl = `/api/media/${this.mediaId}/file${this.currentMedia?.hash ? '?v=' + this.currentMedia.hash : ''}`;

        const modal = document.createElement('div');
        modal.id = 'update-post-modal';
        modal.className = 'fixed inset-0 flex items-end sm:items-center justify-center z-50';
        modal.style.background = 'rgba(0, 0, 0, 0.5)';

        modal.innerHTML = `
            <div class="surface w-full h-full sm:h-auto sm:max-h-[85vh] sm:max-w-2xl sm:mx-4 flex flex-col border-t sm:border shadow-2xl safe-area-bottom">
                <!-- Header -->
                <div class="flex items-center justify-between p-4 border-b border-color flex-shrink-0">
                    <div class="flex items-center gap-2 min-w-0">
                        <button id="upm-device-back" type="button" class="p-1 hover:text-primary transition-colors cursor-pointer text-secondary flex items-center justify-center" title="${window.i18n.t('common.back')}">
                            ${window.Icons.chevronLeft({ size: 16 })}
                        </button>
                        <h2 class="text-base sm:text-lg font-bold truncate">${window.i18n.t('modal.update_post.from_device')}</h2>
                    </div>
                    <button id="upm-device-close" type="button" class="p-1 hover:text-primary transition-colors cursor-pointer text-secondary flex items-center justify-center" title="${window.i18n.t('common.close')}">
                        ${window.Icons.close({ size: 14 })}
                    </button>
                </div>

                <!-- Body -->
                <div class="flex-1 overflow-auto p-4">
                    <!-- Drop zone and initial card (visible before file selection) -->
                    <div id="upm-initial-view">
                        <!-- Current post summary card -->
                        <div class="bg p-3 border mb-3">
                            <span class="text-xs font-bold text-secondary uppercase tracking-wide block mb-2">
                                ${window.i18n.t('modal.update_post.current_post')}
                            </span>
                            <div class="flex items-center gap-3">
                                <div id="upm-init-current-thumb" class="w-16 h-16 surface border flex items-center justify-center flex-shrink-0 overflow-hidden cursor-pointer" title="${window.i18n.t('common.preview')}">
                                    <img src="${curThumb}" alt="Current" class="w-full h-full object-contain"
                                         onerror="this.src='${curFileUrl}';">
                                </div>
                                <div class="min-w-0 flex-1 text-xs">
                                    <div class="font-bold truncate" title="${escapeHtml(curFilename)}">
                                        ${escapeHtml(curFilename)}
                                    </div>
                                    <div class="text-secondary mt-0.5">
                                        ${cw && ch ? `${cw}×${ch}` : '?'} · ${curSize}
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Drop zone -->
                        <div id="upm-drop-zone" class="upload-area bg flex flex-col items-center justify-center gap-2 p-8 border cursor-pointer hover:border-primary transition-colors mb-3">
                            ${window.Icons.upload({ size: 32, class: 'text-secondary' })}
                            <p id="upm-drop-label" class="text-xs text-secondary">
                                ${window.i18n.t('modal.update_post.drop_file_here')}
                            </p>
                        </div>
                    </div>

                    <!-- Comparison view (visible after file selection) -->
                    <div id="upm-comparison-view" style="display:none;" class="mb-3">
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <!-- Current post column -->
                            <div class="bg p-3 border flex flex-col">
                                <span class="text-xs font-bold text-secondary uppercase tracking-wide block mb-2">
                                    ${window.i18n.t('modal.update_post.current_post')}
                                </span>
                                <div id="upm-current-preview-box" class="w-full h-44 surface border flex items-center justify-center overflow-hidden cursor-pointer relative mb-2" title="${window.i18n.t('common.preview')}">
                                    <img id="upm-current-preview-img" src="${curThumb}" alt="Current" class="max-h-full max-w-full object-contain"
                                         onerror="this.src='${curFileUrl}';">
                                </div>
                                <div class="text-xs flex flex-col gap-1 mt-auto">
                                    <div class="truncate font-medium" title="${escapeHtml(curFilename)}">
                                        <span class="text-secondary">${window.i18n.t('media.info.filename')}:</span>
                                        <span class="font-bold ml-1">${escapeHtml(curFilename)}</span>
                                    </div>
                                    <div>
                                        <span class="text-secondary">${window.i18n.t('media.info.dimensions')}:</span>
                                        <span class="font-medium ml-1">${cw && ch ? `${cw}×${ch}` : '?'}</span>
                                    </div>
                                    <div>
                                        <span class="text-secondary">${window.i18n.t('media.info.size')}:</span>
                                        <span class="font-medium ml-1">${curSize}</span>
                                    </div>
                                </div>
                            </div>

                            <!-- Replacement file column -->
                            <div class="bg p-3 border flex flex-col">
                                <div class="flex items-center justify-between mb-2">
                                    <span class="text-xs font-bold text-secondary uppercase tracking-wide">
                                        ${window.i18n.t('modal.update_post.replacement_file')}
                                    </span>
                                    <button id="upm-device-reselect" type="button" class="text-xs text-primary hover:underline cursor-pointer flex items-center gap-1">
                                        ${window.Icons.upload({ size: 12 })}
                                        ${window.i18n.t('modal.update_post.change_file')}
                                    </button>
                                </div>
                                <div id="upm-device-preview-box" class="w-full h-44 surface border flex items-center justify-center overflow-hidden cursor-pointer relative mb-2" title="${window.i18n.t('common.preview')}">
                                    <img id="upm-device-preview-img" src="" alt="Preview" class="max-h-full max-w-full object-contain" style="display:none;">
                                    <video id="upm-device-preview-video" src="" controls class="max-h-full max-w-full object-contain" style="display:none;"></video>
                                </div>
                                <div class="text-xs flex flex-col gap-1 mt-auto">
                                    <div class="truncate font-medium">
                                        <span class="text-secondary">${window.i18n.t('media.info.filename')}:</span>
                                        <span id="upm-device-file-name" class="font-bold ml-1"></span>
                                    </div>
                                    <div>
                                        <span class="text-secondary">${window.i18n.t('media.info.dimensions')}:</span>
                                        <span id="upm-device-dimensions" class="font-medium ml-1">...</span>
                                        <span id="upm-device-res-badge" class="ml-1 text-xs"></span>
                                    </div>
                                    <div>
                                        <span class="text-secondary">${window.i18n.t('media.info.size')}:</span>
                                        <span id="upm-device-file-size" class="font-medium ml-1"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Update options -->
                        <div class="mt-3 bg p-3 border">
                            <p class="text-xs font-bold text-secondary uppercase tracking-wide mb-2">
                                ${window.i18n.t('modal.update_post.what_to_update')}
                            </p>
                            <div class="w-full">
                                ${this._checkboxRow('upm-device-upd-filename', window.i18n.t('modal.update_post.update_filename'), false)}
                            </div>
                            <p id="upm-device-filename-hint" class="text-[11px] text-secondary mt-2 text-center"></p>
                        </div>
                    </div>

                    <!-- Hidden file input -->
                    <input id="upm-file-input" type="file" accept="image/*,video/*" style="display:none;">

                    <!-- Progress bar -->
                    <div id="upm-device-progress-wrap" style="display:none;" class="mt-3">
                        <div class="w-full bg h-2 border overflow-hidden">
                            <div id="upm-device-progress-bar" class="h-full bg-primary transition-all" style="width:0%"></div>
                        </div>
                        <p id="upm-device-progress-text" class="text-xs text-secondary mt-1.5"></p>
                    </div>
                </div>

                <!-- Footer -->
                <div class="flex-shrink-0 p-4 border-t border-color surface">
                    <div class="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3">
                        <div class="flex gap-2 sm:ml-auto">
                            <button id="upm-device-apply" type="button" class="flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn-primary text-sm font-medium cursor-pointer" disabled>
                                ${window.i18n.t('modal.update_post.apply')}
                            </button>
                            <button id="upm-device-cancel" type="button" class="flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn text-sm font-medium cursor-pointer">
                                ${window.i18n.t('common.cancel')}
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

        // Navigation actions
        q('#upm-device-back').addEventListener('click', () => this._onBack());
        q('#upm-device-cancel').addEventListener('click', () => this._onBack());
        q('#upm-device-close').addEventListener('click', () => {
            this.hide();
            document.body.style.overflow = '';
        });

        // Fullscreen preview triggers
        const openCurrentFullscreen = () => {
            const isVideo = this.currentMedia?.file_type === 'video';
            this._openFullscreen(curFileUrl, isVideo);
        };
        q('#upm-init-current-thumb')?.addEventListener('click', openCurrentFullscreen);
        q('#upm-current-preview-box')?.addEventListener('click', openCurrentFullscreen);

        q('#upm-device-preview-box')?.addEventListener('click', (e) => {
            // Avoid triggering fullscreen when clicking native video controls
            if (e.target.tagName.toLowerCase() === 'video' && e.offsetY > e.target.clientHeight - 40) return;
            if (this._objectUrl && this._deviceFile) {
                const isVideo = this._deviceFile.type.startsWith('video/');
                this._openFullscreen(this._objectUrl, isVideo);
            }
        });

        // File input and drop zone
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
            if (file && this._isAcceptableFile(file)) this._setDeviceFile(file);
        });

        q('#upm-device-reselect').addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', () => {
            const file = fileInput.files?.[0];
            if (file && this._isAcceptableFile(file)) this._setDeviceFile(file);
        });

        // Filename checkbox change
        q('#upm-device-upd-filename').addEventListener('change', () => this._updateFilenameHint());

        // Apply
        q('#upm-device-apply').addEventListener('click', () => this._applyFromDevice());

        this._registerEscapeHandler(() => this._onBack());
    }

    _isAcceptableFile(file) {
        return file.type.startsWith('image/') || file.type.startsWith('video/');
    }

    _setDeviceFile(file) {
        this._deviceFile = file;

        if (this._objectUrl) {
            URL.revokeObjectURL(this._objectUrl);
            this._objectUrl = null;
        }
        this._objectUrl = URL.createObjectURL(file);
        this._detectedWidth = null;
        this._detectedHeight = null;

        const initialView = this._modal?.querySelector('#upm-initial-view');
        const comparisonView = this._modal?.querySelector('#upm-comparison-view');
        const applyBtn = this._modal?.querySelector('#upm-device-apply');
        const fileNameEl = this._modal?.querySelector('#upm-device-file-name');
        const fileSizeEl = this._modal?.querySelector('#upm-device-file-size');
        const img = this._modal?.querySelector('#upm-device-preview-img');
        const video = this._modal?.querySelector('#upm-device-preview-video');

        if (initialView) initialView.style.display = 'none';
        if (comparisonView) comparisonView.style.display = '';
        if (applyBtn) applyBtn.disabled = false;

        if (fileNameEl) {
            fileNameEl.textContent = file.name;
            fileNameEl.title = file.name;
        }
        if (fileSizeEl) fileSizeEl.textContent = formatFileSize(file.size, 'compact');

        this._updateFilenameHint();

        if (img && video) {
            if (file.type.startsWith('video/')) {
                img.style.display = 'none';
                img.src = '';
                video.src = this._objectUrl;
                video.style.display = '';

                const probeVideo = document.createElement('video');
                probeVideo.preload = 'metadata';
                probeVideo.onloadedmetadata = () => {
                    this._detectedWidth = probeVideo.videoWidth;
                    this._detectedHeight = probeVideo.videoHeight;
                    this._updateResolutionBadge();
                };
                probeVideo.src = this._objectUrl;
            } else {
                video.style.display = 'none';
                video.src = '';
                img.src = this._objectUrl;
                img.style.display = '';

                const probeImg = new Image();
                probeImg.onload = () => {
                    this._detectedWidth = probeImg.naturalWidth;
                    this._detectedHeight = probeImg.naturalHeight;
                    this._updateResolutionBadge();
                };
                probeImg.src = this._objectUrl;
            }
        }
    }

    _updateResolutionBadge() {
        const cw = this.currentMedia?.width ?? 0;
        const ch = this.currentMedia?.height ?? 0;
        const nw = this._detectedWidth;
        const nh = this._detectedHeight;
        const dimEl = this._modal?.querySelector('#upm-device-dimensions');
        const badgeEl = this._modal?.querySelector('#upm-device-res-badge');
        if (!dimEl || !badgeEl) return;

        if (nw && nh) {
            dimEl.textContent = `${nw}×${nh}`;
            if (cw && ch) {
                if (nw > cw || nh > ch) {
                    badgeEl.className = 'ml-1 text-xs text-success';
                    badgeEl.textContent = window.i18n.t('modal.update_post.resolution_upgrade', { w: nw, h: nh, cw, ch });
                } else if (nw === cw && nh === ch) {
                    badgeEl.className = 'ml-1 text-xs text-secondary';
                    badgeEl.textContent = window.i18n.t('modal.update_post.resolution_same', { w: nw, h: nh });
                } else {
                    badgeEl.className = 'ml-1 text-xs text-warning';
                    badgeEl.textContent = window.i18n.t('modal.update_post.resolution_smaller', { w: nw, h: nh });
                }
            } else {
                badgeEl.textContent = '';
            }
        } else {
            dimEl.textContent = '?';
            badgeEl.textContent = '';
        }
    }

    _updateFilenameHint() {
        const chk = this._modal?.querySelector('#upm-device-upd-filename');
        const hintEl = this._modal?.querySelector('#upm-device-filename-hint');
        if (!chk || !hintEl) return;

        if (chk.checked) {
            const newName = this._deviceFile?.name || '';
            hintEl.className = 'text-[11px] text-primary mt-2 text-center';
            hintEl.textContent = window.i18n.t('modal.update_post.new_filename_hint', { name: newName });
        } else {
            const curName = this.currentMedia?.filename || '';
            hintEl.className = 'text-[11px] text-secondary mt-2 text-center';
            hintEl.textContent = window.i18n.t('modal.update_post.keep_filename_hint', { name: curName });
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
        const chk = this._modal?.querySelector('#upm-device-upd-filename');
        const updateFilename = chk ? chk.checked : false;

        if (applyBtn) {
            applyBtn.disabled = true;
            applyBtn.textContent = window.i18n.t('modal.update_post.applying');
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
            this._setProgress(95, window.i18n.t('modal.update_post.applying'));

            const finalizeForm = new FormData();
            finalizeForm.append('upload_id', uploadId);
            finalizeForm.append('update_filename', updateFilename ? 'true' : 'false');

            const finalRes = await fetch(`/api/media/${this.mediaId}/update-file-finalize`, {
                method: 'POST',
                body: finalizeForm
            });

            if (!finalRes.ok) {
                const err = await finalRes.json().catch(() => ({ detail: finalRes.statusText }));
                const detail = err.detail || finalRes.statusText;
                if (finalRes.status === 409) {
                    if (detail.includes('identical')) {
                        throw new Error(window.i18n.t('modal.update_post.error_identical_file'));
                    }
                    throw new Error(window.i18n.t('modal.update_post.error_duplicate_file'));
                }
                throw new Error(detail);
            }

            this._setProgress(100, '');

            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(window.i18n.t('modal.update_post.success'), 'success');
            }

            this.hide();
            document.body.style.overflow = '';
            setTimeout(() => window.location.reload(), 800);
        } catch (e) {
            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(window.i18n.t(e.message), 'error');
            }
        } finally {
            this._isUploading = false;
            if (applyBtn) {
                applyBtn.disabled = false;
                applyBtn.textContent = window.i18n.t('modal.update_post.apply');
            }
        }
    }
}
