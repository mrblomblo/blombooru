class UploadUploaderShell {
    constructor() {
        this.uploadArea = document.getElementById('upload-area');
        this.fileInput = document.getElementById('file-input');
        this.session = new UploadSession();

        this.allAlbums = [];
        this.mediaTypeTags = { image: [], gif: [], video: [] };

        this.tagInputHelper = new TagInputHelper();
        this.fullscreenViewer = new FullscreenMediaViewer();

        this.queueGrid = null;
        this.pendingPanel = null;
        this.isProcessingFiles = false;
        this.uploadAbortController = null;
        this._currentArchiveUploadId = null;
        this._originalUploadText = null;

        if (this.uploadArea) {
            this.init();
        }
    }

    async init() {
        this.setupComponents();
        this.setupDragAndDrop();
        this.setupFileInput();
        this.setupFolderMappingControls();
        this.setupSubmitControls();
        this.loadAlbums();
        this.loadMediaTypeTags();
    }

    setupFolderMappingControls() {
        this.folderMappingBar = document.getElementById('folder-mapping-bar');
        this.folderMappingToggle = document.getElementById('folder-mapping-toggle');
        this.folderRootOptions = document.getElementById('folder-mapping-root-options');
        this.folderRootModeButtons = document.querySelectorAll('.folder-root-mode-btn');
        this.folderRootModeLabelRoot = document.getElementById('folder-root-mode-label-root');
        this.currentFolderRootMode = 'use_root';

        if (this.folderMappingToggle) {
            this.folderMappingToggle.addEventListener('change', async () => {
                const enabled = this.folderMappingToggle.checked;
                if (this.folderRootOptions) {
                    this.folderRootOptions.style.display = enabled ? '' : 'none';
                }
                const rootMode = this.getFolderMappingMode();
                await this.session.setFolderMapping(enabled, rootMode);
            });
        }

        if (this.folderRootModeButtons) {
            this.folderRootModeButtons.forEach(btn => {
                btn.addEventListener('click', async () => {
                    const mode = btn.dataset.mode;
                    if (this.currentFolderRootMode === mode) return;
                    this.setFolderRootModeButtonState(mode);
                    const enabled = this.folderMappingToggle ? this.folderMappingToggle.checked : true;
                    await this.session.setFolderMapping(enabled, mode);
                });
            });
            this.setFolderRootModeButtonState(this.currentFolderRootMode);
        }
    }

    setFolderRootModeButtonState(activeMode) {
        this.currentFolderRootMode = activeMode;
        if (!this.folderRootModeButtons) return;
        this.folderRootModeButtons.forEach(btn => {
            const isActive = btn.dataset.mode === activeMode;
            if (isActive) {
                btn.classList.remove('bg', 'hover:border-primary');
                btn.classList.add('bg-primary', 'border-primary', 'primary-text', 'hover:bg-primary');
            } else {
                btn.classList.remove('bg-primary', 'border-primary', 'primary-text', 'hover:bg-primary');
                btn.classList.add('bg', 'hover:border-primary');
            }
        });
    }

    getFolderMappingMode() {
        if (this.folderMappingToggle && !this.folderMappingToggle.checked) {
            return 'flatten';
        }
        return this.currentFolderRootMode || 'use_root';
    }

    async loadMediaTypeTags() {
        try {
            const response = await fetch('/api/admin/settings');
            if (response.ok) {
                const data = await response.json();
                if (data.media_type_tags) {
                    this.mediaTypeTags = {
                        image: data.media_type_tags.image || [],
                        gif: data.media_type_tags.gif || [],
                        video: data.media_type_tags.video || []
                    };
                }
            }
        } catch (error) {
            // Silently fall back to empty auto tags
        }
    }

    async loadAlbums() {
        try {
            const response = await fetch('/api/albums/tree');
            const data = await response.json();
            this.allAlbums = data.items || [];
            if (this.queueGrid) {
                this.queueGrid.setAllAlbums(this.allAlbums);
            }
        } catch (error) {
            console.error('Error loading albums:', error);
        }
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    setupComponents() {
        const queueContainer = document.getElementById('upload-queue-container');
        if (queueContainer) {
            this.queueGrid = new UploadQueueGrid(queueContainer, this.session, {
                allAlbums: this.allAlbums,
                fullscreenViewer: this.fullscreenViewer,
                tagInputHelper: this.tagInputHelper,
                onTagsChange: () => {
                    if (this.pendingPanel) this.pendingPanel.refresh();
                },
                onSelectionChange: (selectedIds) => {
                    if (this.pendingPanel) {
                        this.pendingPanel.updateSelectionHighlight(selectedIds);
                    }
                },
            });
        }

        const pendingContainer = document.getElementById('upload-pending-container');
        if (pendingContainer) {
            this.pendingPanel = new PendingEntitiesPanel(pendingContainer, this.session, {
                onHighlightItems: (itemIds, event) => {
                    if (this.queueGrid) {
                        this.queueGrid.selectItems(itemIds, event);
                    }
                }
            });
        }

        this.session.on('itemAdded', () => this.updateUIState());
        this.session.on('itemRemoved', () => this.updateUIState());
        this.session.on('sessionCleared', () => this.updateUIState());
    }

    updateUIState() {
        const count = this.session.getItemCount();
        const queueSection = document.getElementById('upload-review-section');
        const submitControls = document.getElementById('submit-controls');
        const submitBtn = document.getElementById('upload-submit-btn');

        if (count > 0 || this.isProcessingFiles) {
            if (queueSection) queueSection.style.display = 'block';
            if (submitControls) submitControls.style.display = 'flex';
            if (submitBtn) {
                submitBtn.disabled = this.session.isCommitting || count === 0;
            }

            // Check if folder mapping controls should be displayed
            const items = this.session.getAllItems();
            const hasFolders = items.some(it => it.relative_path && it.relative_path.includes('/'));
            if (this.folderMappingBar) {
                this.folderMappingBar.style.display = hasFolders ? 'block' : 'none';
            }

            if (hasFolders && this.folderRootModeLabelRoot) {
                const sampleItem = items.find(it => it.relative_path && it.relative_path.includes('/'));
                const rootName = sampleItem ? sampleItem.relative_path.split('/')[0] : 'root';
                this.folderRootModeLabelRoot.textContent = window.i18n.t('upload.folder.root_mode_root', { root: rootName });
            }
        } else {
            if (queueSection) queueSection.style.display = 'none';
            if (submitControls) submitControls.style.display = 'none';
            if (this.folderMappingBar) this.folderMappingBar.style.display = 'none';
        }
    }

    setupDragAndDrop() {
        if (!this.uploadArea) return;

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            this.uploadArea.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            this.uploadArea.addEventListener(eventName, () => {
                this.uploadArea.classList.add('border-primary', 'bg-primary/5');
            });
        });

        ['dragleave', 'drop'].forEach(eventName => {
            this.uploadArea.addEventListener(eventName, () => {
                this.uploadArea.classList.remove('border-primary', 'bg-primary/5');
            });
        });

        this.uploadArea.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const items = dt.items;

            if (items && items.length > 0) {
                this.handleDataTransferItems(items);
            } else if (dt.files && dt.files.length > 0) {
                this.handleFiles(Array.from(dt.files));
            }
        });

        this.uploadArea.addEventListener('click', (e) => {
            if (e.target.tagName !== 'INPUT' && this.fileInput) {
                this.fileInput.click();
            }
        });
    }

    setupFileInput() {
        if (!this.fileInput) return;
        this.fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                this.handleFiles(Array.from(e.target.files));
            }
        });
    }

    async handleDataTransferItems(items) {
        const fileEntries = [];

        const scanEntry = async (entry, path = '') => {
            if (entry.isFile) {
                const file = await new Promise((resolve) => entry.file(resolve));
                const fullPath = (path ? `${path}/${file.name}` : file.name).replace(/^\/+/, '');
                file._relativePath = fullPath;
                fileEntries.push(file);
            } else if (entry.isDirectory) {
                const reader = entry.createReader();
                const readEntries = async () => {
                    const entries = await new Promise((resolve) => {
                        reader.readEntries(resolve, (err) => {
                            console.warn('Error reading directory entries:', err);
                            resolve([]);
                        });
                    });
                    if (entries && entries.length > 0) {
                        for (const child of entries) {
                            const childPath = (path ? `${path}/${entry.name}` : entry.name).replace(/^\/+/, '');
                            await scanEntry(child, childPath);
                        }
                        await readEntries();
                    }
                };
                await readEntries();
            }
        };

        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
            if (entry) {
                await scanEntry(entry);
            } else if (item.kind === 'file') {
                const f = item.getAsFile();
                if (f) fileEntries.push(f);
            }
        }

        if (fileEntries.length > 0) {
            await this.handleFiles(fileEntries);
        }
    }

    isSidecarFile(file) {
        if (!file || !file.name) return false;
        const lower = file.name.toLowerCase();
        return lower.endsWith('.json') || lower.endsWith('.xmp');
    }

    findMatchingSidecar(file, relPath, sidecarFiles) {
        const lowerRel = relPath.toLowerCase();
        const lowerName = file.name.toLowerCase();
        const stemRel = lowerRel.includes('.') ? lowerRel.substring(0, lowerRel.lastIndexOf('.')) : lowerRel;
        const stemName = lowerName.includes('.') ? lowerName.substring(0, lowerName.lastIndexOf('.')) : lowerName;

        // Exact media filename with extension: file.png.json or file.png.xmp
        if (sidecarFiles.has(`${lowerRel}.json`)) return sidecarFiles.get(`${lowerRel}.json`);
        if (sidecarFiles.has(`${lowerName}.json`)) return sidecarFiles.get(`${lowerName}.json`);
        if (sidecarFiles.has(`${lowerRel}.xmp`)) return sidecarFiles.get(`${lowerRel}.xmp`);
        if (sidecarFiles.has(`${lowerName}.xmp`)) return sidecarFiles.get(`${lowerName}.xmp`);

        // Media stem without extension: file.json or file.xmp
        if (sidecarFiles.has(`${stemRel}.json`)) return sidecarFiles.get(`${stemRel}.json`);
        if (sidecarFiles.has(`${stemName}.json`)) return sidecarFiles.get(`${stemName}.json`);
        if (sidecarFiles.has(`${stemRel}.xmp`)) return sidecarFiles.get(`${stemRel}.xmp`);
        if (sidecarFiles.has(`${stemName}.xmp`)) return sidecarFiles.get(`${stemName}.xmp`);

        return null;
    }

    isAborted() {
        return this.uploadAbortController ? this.uploadAbortController.signal.aborted : false;
    }

    abortAllUploads() {
        if (this.uploadAbortController) {
            this.uploadAbortController.abort();
            this.uploadAbortController = null;
        }
        if (window.urlImporter && typeof window.urlImporter.cancel === 'function') {
            window.urlImporter.cancel();
        }
        if (window.adminPanel?.content?.cancelScan) {
            window.adminPanel.content.cancelScan();
        }
        if (this.session) {
            this.session.abortPendingOperations();
        }
        if (this._currentArchiveUploadId) {
            this.cleanupArchive(this._currentArchiveUploadId);
            this._currentArchiveUploadId = null;
        }
        this.isProcessingFiles = false;
        const uploadText = this.uploadArea?.querySelector('p');
        this.uploadArea?.classList.remove('opacity-50', 'pointer-events-none');
        if (uploadText && this._originalUploadText) {
            uploadText.textContent = this._originalUploadText;
        }
        if (this.fileInput) this.fileInput.value = '';
        this.updateUIState();
    }

    cleanupArchive(uploadId) {
        if (!uploadId) return;
        fetch(`/api/media/archive-cleanup/${uploadId}`, {
            method: 'DELETE',
            keepalive: true
        }).catch(() => {});
    }

    async handleFiles(files) {
        if (this.isProcessingFiles) return;
        this.isProcessingFiles = true;

        if (this.uploadAbortController) {
            this.uploadAbortController.abort();
        }
        this.uploadAbortController = new AbortController();
        const signal = this.uploadAbortController.signal;

        const uploadText = this.uploadArea?.querySelector('p');
        const origText = uploadText?.textContent;
        this._originalUploadText = origText;
        if (uploadText) uploadText.textContent = window.i18n.t('upload.progress.uploading');
        this.uploadArea?.classList.add('opacity-50', 'pointer-events-none');
        this.updateUIState();

        try {
            const folderMappingMode = this.getFolderMappingMode();
            const mediaFiles = [];
            const sidecarFiles = new Map();
            const archiveFiles = [];
            const textFiles = [];

            for (const file of files) {
                if (window.FormatRegistry.isArchive(file.name)) {
                    archiveFiles.push(file);
                } else if (this.isTextUrlListFile(file)) {
                    textFiles.push(file);
                } else if (this.isValidFile(file)) {
                    mediaFiles.push(file);
                } else if (this.isSidecarFile(file)) {
                    const relPath = (file._relativePath || file.webkitRelativePath || file.name).replace(/\\/g, '/');
                    sidecarFiles.set(relPath.toLowerCase(), file);
                    sidecarFiles.set(file.name.toLowerCase(), file);
                }
            }

            for (const archiveFile of archiveFiles) {
                if (signal.aborted) break;
                await this.handleArchive(archiveFile, signal);
            }

            for (const textFile of textFiles) {
                if (signal.aborted) break;
                if (!window.urlImporter && typeof UrlImporter !== 'undefined') {
                    window.urlImporter = new UrlImporter(this);
                }
                if (window.urlImporter && typeof window.urlImporter.importFromTextFile === 'function') {
                    await window.urlImporter.importFromTextFile(textFile, signal);
                }
            }

            for (const file of mediaFiles) {
                if (signal.aborted) break;
                const relPath = (file._relativePath || file.webkitRelativePath || file.name).replace(/\\/g, '/');
                const matchedSidecar = this.findMatchingSidecar(file, relPath, sidecarFiles);

                await this.session.uploadFile(file, {
                    relativePath: relPath,
                    folderMappingMode: folderMappingMode,
                    sidecar: matchedSidecar,
                    signal: signal,
                });
            }
        } catch (e) {
            if (e.name === 'AbortError' || signal.aborted) {
                return;
            }
            console.error('Error staging files:', e);
            if (window.app && window.app.showNotification) {
                window.app.showNotification(window.i18n.t(e.message), 'error');
            }
        } finally {
            this.isProcessingFiles = false;
            this.uploadArea?.classList.remove('opacity-50', 'pointer-events-none');
            if (uploadText && origText) uploadText.textContent = origText;
            if (this.fileInput) this.fileInput.value = '';
            this.updateUIState();
            if (this.pendingPanel) this.pendingPanel.refresh();
        }
    }

    isTextUrlListFile(file) {
        if (!file || !file.name) return false;
        const lower = file.name.toLowerCase();
        return lower.endsWith('.txt') || file.type === 'text/plain';
    }

    isValidFile(file) {
        return FormatRegistry.isValidFile(file);
    }

    async handleArchive(archiveFile, signal = null) {
        const CHUNK_SIZE = 99 * 1024 * 1024;
        const totalChunks = Math.ceil(archiveFile.size / CHUNK_SIZE);
        let uploadId = null;

        for (let i = 0; i < totalChunks; i++) {
            if (signal?.aborted) {
                if (uploadId) this.cleanupArchive(uploadId);
                return;
            }
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, archiveFile.size);
            const chunk = archiveFile.slice(start, end);

            const chunkForm = new FormData();
            chunkForm.append('file', chunk, archiveFile.name);
            if (uploadId) chunkForm.append('upload_id', uploadId);
            chunkForm.append('chunk_index', i.toString());
            chunkForm.append('total_chunks', totalChunks.toString());
            chunkForm.append('filename', archiveFile.name);

            const chunkResponse = await fetch('/api/media/archive-chunk', {
                method: 'POST',
                body: chunkForm,
                signal: signal,
            });

            if (!chunkResponse.ok) {
                throw new Error(`Failed to upload archive chunk ${i + 1}/${totalChunks}`);
            }

            const chunkData = await chunkResponse.json();
            if (i === 0) {
                uploadId = chunkData.upload_id;
                this._currentArchiveUploadId = uploadId;
            }
        }

        if (signal?.aborted) {
            if (uploadId) this.cleanupArchive(uploadId);
            return;
        }

        const extractForm = new FormData();
        extractForm.append('upload_id', uploadId);

        const response = await fetch('/api/media/extract-archive', {
            method: 'POST',
            body: extractForm,
            signal: signal,
        });

        if (!response.ok) {
            throw new Error('Failed to extract archive');
        }

        const result = await response.json();

        for (const fData of (result.files || [])) {
            if (signal?.aborted) {
                if (uploadId) this.cleanupArchive(uploadId);
                return;
            }
            const fileUrl = fData.url || `/api/media/archive-file/${uploadId}/${fData.file_id}`;
            const fileResp = await fetch(fileUrl, { signal: signal });
            if (!fileResp.ok) {
                console.warn(`Failed to fetch extracted archive file ${fData.filename}`);
                continue;
            }
            const blob = await fileResp.blob();
            const file = new File([blob], fData.filename, { type: fData.mime_type || blob.type });
            file._relativePath = fData.path || fData.filename;

            let sidecarFile = null;
            if (fData.sidecar_url) {
                try {
                    const sidecarResp = await fetch(fData.sidecar_url, { signal: signal });
                    if (sidecarResp.ok) {
                        const sidecarBlob = await sidecarResp.blob();
                        sidecarFile = new File([sidecarBlob], fData.sidecar_filename || `${fData.filename}.json`, {
                            type: 'application/octet-stream'
                        });
                    }
                } catch (e) {
                    if (e.name === 'AbortError' || signal?.aborted) throw e;
                    console.warn(`Failed to fetch archive sidecar for ${fData.filename}:`, e);
                }
            }

            if (signal?.aborted) {
                if (uploadId) this.cleanupArchive(uploadId);
                return;
            }

            await this.session.uploadFile(file, {
                relativePath: file._relativePath,
                sidecar: sidecarFile,
                signal: signal,
            });
        }

        if (uploadId) {
            this.cleanupArchive(uploadId);
            if (this._currentArchiveUploadId === uploadId) {
                this._currentArchiveUploadId = null;
            }
        }
    }

    setupSubmitControls() {
        const submitBtn = document.getElementById('upload-submit-btn');
        const cancelBtn = document.getElementById('upload-cancel-btn');

        if (submitBtn) {
            submitBtn.addEventListener('click', () => this.submitAll());
        }
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.cancelAll());
        }
    }

    async submitAll() {
        if (this.session.isCommitting || this.session.getItemCount() === 0) return;

        const submitBtn = document.getElementById('upload-submit-btn');
        const cancelBtn = document.getElementById('upload-cancel-btn');
        const originalText = submitBtn ? submitBtn.textContent : 'Commit';

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = window.i18n.t('upload.progress.uploading');
        }
        if (cancelBtn) cancelBtn.disabled = true;

        try {
            const result = await this.session.commit();

            if (window.app && window.app.showNotification) {
                window.app.showNotification(window.i18n.t('upload.progress.upload_success', { count: result.total_created }), 'success');
            }

            // Refresh media statistics if available
            if (window.loadMediaStats) {
                window.loadMediaStats();
            }
        } catch (e) {
            console.error('Error committing upload session:', e);
            if (window.app && window.app.showNotification) {
                window.app.showNotification(e.message, 'error');
            }
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }
            if (cancelBtn) cancelBtn.disabled = false;
        }
    }

    async cancelAll() {
        const cancelBtn = document.getElementById('upload-cancel-btn');
        const doCancel = async () => {
            if (cancelBtn) cancelBtn.disabled = true;
            try {
                this.abortAllUploads();
                await this.session.cancelSession();
            } finally {
                if (cancelBtn) cancelBtn.disabled = false;
            }
        };
        if (typeof ModalHelper !== 'undefined') {
            new ModalHelper({
                type: 'danger',
                title: window.i18n.t('upload.submit.cancel_title'),
                message: window.i18n.t('upload.submit.cancel_confirm'),
                confirmText: window.i18n.t('common.yes'),
                cancelText: window.i18n.t('common.cancel'),
                onConfirm: doCancel
            }).show();
        } else {
            await doCancel();
        }
    }

    // Compatibility methods for untracked scanner and booru import
    async addScannedFile(fileOrPath, originalPath, options = {}) {
        if (this.isAborted()) {
            return null;
        }
        const signal = options.signal || this.uploadAbortController?.signal;
        if (typeof fileOrPath === 'string') {
            await this.session.addUntrackedFile(fileOrPath, { ...options, signal });
        } else if (originalPath && typeof originalPath === 'string') {
            await this.session.addUntrackedFile(originalPath, { ...options, signal });
        } else if (fileOrPath && typeof fileOrPath.name === 'string' && this.isValidFile(fileOrPath)) {
            await this.session.uploadFile(fileOrPath, {
                relativePath: originalPath || fileOrPath.name,
                ...options,
                signal,
            });
        }
    }

    async addBooruImport(file, metadata, options = {}) {
        if (this.isAborted()) {
            return null;
        }
        const signal = options.signal || this.uploadAbortController?.signal;
        await this.session.uploadFile(file, {
            relativePath: file.name,
            baseRating: metadata.rating || 'safe',
            baseSource: metadata.source || '',
            baseTags: (metadata.tags || []).join(' '),
            baseAlbumIds: metadata.album_ids || [],
            baseDescription: metadata.description || '',
            categoryHints: metadata.categoryHints || null,
            userAssignedTags: metadata.userAssignedTags || null,
            ...options,
            signal,
        });
    }

    isFileQueued(filePath) {
        const filename = filePath.split('/').pop().split('\\').pop();
        return this.session.getAllItems().some(it =>
            it.filename === filename ||
            it.relative_path === filePath ||
            it.source_path === filePath
        );
    }
}

window.UploadUploaderShell = UploadUploaderShell;
