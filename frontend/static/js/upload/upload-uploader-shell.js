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

        if (this.uploadArea) {
            this.init();
        }
    }

    async init() {
        this.setupComponents();
        this.setupDragAndDrop();
        this.setupFileInput();
        this.setupSubmitControls();
        this.loadAlbums();
        this.loadMediaTypeTags();
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
            const response = await fetch('/api/albums?limit=1000&sort=name&order=asc');
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
            });
        }

        const pendingContainer = document.getElementById('upload-pending-container');
        if (pendingContainer) {
            this.pendingPanel = new PendingEntitiesPanel(pendingContainer, this.session, {
                onHighlightItems: (itemIds) => {
                    if (this.queueGrid) {
                        this.queueGrid.selectedIds.clear();
                        (itemIds || []).forEach(id => this.queueGrid.selectedIds.add(id));
                        if (this.queueGrid.selectedIds.size > 0) {
                            this.queueGrid.activeItemId = Array.from(this.queueGrid.selectedIds)[0];
                        }
                        this.queueGrid.updateSelectionVisuals();
                        this.queueGrid.syncEditor();
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

        if (count > 0) {
            if (queueSection) queueSection.style.display = 'block';
            if (submitControls) submitControls.style.display = 'flex';
        } else {
            if (queueSection) queueSection.style.display = 'none';
            if (submitControls) submitControls.style.display = 'none';
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
                file._relativePath = path ? `${path}/${file.name}` : file.name;
                fileEntries.push(file);
            } else if (entry.isDirectory) {
                const reader = entry.createReader();
                const readEntries = async () => {
                    const entries = await new Promise((resolve) => reader.readEntries(resolve));
                    if (entries.length > 0) {
                        for (const child of entries) {
                            await scanEntry(child, path ? `${path}/${entry.name}` : entry.name);
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

    async handleFiles(files) {
        if (this.isProcessingFiles) return;
        this.isProcessingFiles = true;

        const uploadText = this.uploadArea?.querySelector('p');
        const origText = uploadText?.textContent;
        if (uploadText) uploadText.textContent = window.i18n.t('upload.progress.uploading');
        this.uploadArea?.classList.add('opacity-50', 'pointer-events-none');

        try {
            for (const file of files) {
                // Check if archive
                if (window.FormatRegistry.isArchive(file.name)) {
                    await this.handleArchive(file);
                    continue;
                }

                if (this.isValidFile(file)) {
                    await this.session.uploadFile(file, {
                        relativePath: file._relativePath || file.webkitRelativePath || file.name,
                    });
                }
            }
        } catch (e) {
            console.error('Error staging files:', e);
            if (window.app && window.app.showNotification) {
                window.app.showNotification(window.i18n.t(e.message), 'error');
            }
        } finally {
            this.isProcessingFiles = false;
            this.uploadArea?.classList.remove('opacity-50', 'pointer-events-none');
            if (uploadText && origText) uploadText.textContent = origText;
            if (this.fileInput) this.fileInput.value = '';
            if (this.pendingPanel) this.pendingPanel.refresh();
        }
    }

    isValidFile(file) {
        return FormatRegistry.isValidFile(file);
    }

    async handleArchive(archiveFile) {
        const CHUNK_SIZE = 99 * 1024 * 1024;
        const totalChunks = Math.ceil(archiveFile.size / CHUNK_SIZE);
        let uploadId = null;

        for (let i = 0; i < totalChunks; i++) {
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
            });

            if (!chunkResponse.ok) {
                throw new Error(`Failed to upload archive chunk ${i + 1}/${totalChunks}`);
            }

            const chunkData = await chunkResponse.json();
            if (i === 0) uploadId = chunkData.upload_id;
        }

        const extractForm = new FormData();
        extractForm.append('upload_id', uploadId);

        const response = await fetch('/api/media/extract-archive', {
            method: 'POST',
            body: extractForm,
        });

        if (!response.ok) {
            throw new Error('Failed to extract archive');
        }

        const result = await response.json();

        for (const fData of (result.files || [])) {
            const fileUrl = fData.url || `/api/media/archive-file/${uploadId}/${fData.file_id}`;
            const fileResp = await fetch(fileUrl);
            if (!fileResp.ok) {
                console.warn(`Failed to fetch extracted archive file ${fData.filename}`);
                continue;
            }
            const blob = await fileResp.blob();
            const file = new File([blob], fData.filename, { type: fData.mime_type || blob.type });
            file._relativePath = fData.path || fData.filename;

            await this.session.uploadFile(file, {
                relativePath: file._relativePath,
            });
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
        if (typeof ModalHelper !== 'undefined') {
            new ModalHelper({
                type: 'danger',
                title: window.i18n.t('upload.submit.cancel_title'),
                message: window.i18n.t('upload.submit.cancel_confirm'),
                confirmText: window.i18n.t('common.yes'),
                onConfirm: async () => {
                    await this.session.cancelSession();
                }
            }).show();
        } else {
            if (confirm(window.i18n.t('upload.submit.cancel_confirm'))) {
                await this.session.cancelSession();
            }
        }
    }

    // Compatibility methods for untracked scanner and booru import
    async addScannedFile(fileOrPath, originalPath) {
        if (typeof fileOrPath === 'string') {
            await this.session.addUntrackedFile(fileOrPath);
        } else if (originalPath && typeof originalPath === 'string') {
            await this.session.addUntrackedFile(originalPath);
        } else if (fileOrPath && typeof fileOrPath.name === 'string' && this.isValidFile(fileOrPath)) {
            await this.session.uploadFile(fileOrPath, {
                relativePath: originalPath || fileOrPath.name,
            });
        }
    }

    async addBooruImport(file, metadata) {
        await this.session.uploadFile(file, {
            relativePath: file.name,
            baseRating: metadata.rating || 'safe',
            baseSource: metadata.source || '',
            baseTags: (metadata.tags || []).join(' '),
            baseAlbumIds: metadata.album_ids || [],
            baseDescription: metadata.description || '',
            categoryHints: metadata.categoryHints || null,
            userAssignedTags: metadata.userAssignedTags || null,
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
