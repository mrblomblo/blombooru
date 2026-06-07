class Uploader {
    constructor() {
        this.uploadArea = document.getElementById('upload-area');
        this.fileInput = document.getElementById('file-input');
        this.uploadedFiles = [];
        this.selectedFileIndex = null;
        this.baseRating = 'safe';
        this.baseTags = [];
        this.baseAlbumIds = new Set();
        this.allAlbums = [];
        this.baseSource = '';
        this.fileHashes = new Set();
        this.tagInputHelper = new TagInputHelper();
        this.baseRatingSelect = null;
        this.individualRatingSelect = null;
        this.fullscreenViewer = new FullscreenMediaViewer();
        this.mediaTypeTags = { image: [], gif: [], video: [] };

        if (this.uploadArea) {
            this.init();
        }
    }

    init() {
        this.setupDragAndDrop();
        this.setupFileInput();
        this.setupBaseControls();
        this.createPreviewGrid();
        this.createSubmitControls();
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
            // Non-critical: silently fall back to empty auto-tags
        }
    }

    async isAnimatedWebP(file) {
        if (file.type !== 'image/webp' && !file.name.toLowerCase().endsWith('.webp')) {
            return false;
        }

        try {
            const buffer = await file.slice(0, 1024).arrayBuffer();
            const arr = new Uint8Array(buffer);
            if (arr.length < 12) return false;

            // Check RIFF and WEBP headers
            const isRiff = arr[0] === 82 && arr[1] === 73 && arr[2] === 70 && arr[3] === 70;
            const isWebp = arr[8] === 87 && arr[9] === 69 && arr[10] === 66 && arr[11] === 80;

            if (!isRiff || !isWebp) return false;

            // Look for ANIM chunk in the first 1KB
            for (let i = 12; i < arr.length - 3; i++) {
                if (arr[i] === 65 && arr[i + 1] === 78 && arr[i + 2] === 73 && arr[i + 3] === 77) {
                    return true;
                }
            }
            return false;
        } catch (e) {
            console.error('Error checking if WebP is animated:', e);
            return false;
        }
    }

    async getAutoTagsForFile(file) {
        let fileType = 'image';

        if (file.type.startsWith('video/')) {
            fileType = 'video';
        } else if (file.type === 'image/gif') {
            fileType = 'gif';
        } else if (file.type === 'image/webp' || file.name.toLowerCase().endsWith('.webp')) {
            const animated = await this.isAnimatedWebP(file);
            fileType = animated ? 'gif' : 'image';
        } else if (file.type.startsWith('image/')) {
            fileType = 'image';
        } else {
            const ext = file.name.toLowerCase().split('.').pop();
            if (['mp4', 'webm', 'mov', 'avi', 'mkv'].includes(ext)) {
                fileType = 'video';
            } else if (ext === 'gif') {
                fileType = 'gif';
            } else {
                fileType = 'image';
            }
        }

        if (fileType === 'gif') {
            return [...this.mediaTypeTags.gif];
        } else if (fileType === 'video') {
            return [...this.mediaTypeTags.video];
        }
        return [...this.mediaTypeTags.image];
    }

    async loadAlbums() {
        try {
            const response = await fetch('/api/albums?limit=1000&sort=name&order=asc');
            const data = await response.json();
            this.allAlbums = data.items || [];
            this.renderBaseAlbumSelect();
        } catch (error) {
            console.error('Error loading albums:', error);
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    renderBaseAlbumSelect() {
        if (!this.baseAlbumSelect) return;

        const availableAlbums = this.allAlbums.filter(album => !this.baseAlbumIds.has(album.id));
        const options = [{ value: '', text: window.i18n.t('upload.base_settings.select_album'), selected: true }];
        availableAlbums.forEach(album => {
            options.push({ value: album.id, text: album.name });
        });

        this.baseAlbumSelect.setOptions(options);
    }

    renderBaseAlbumBadges() {
        const container = document.getElementById('base-albums-list');
        if (!container) return;

        container.innerHTML = '';
        this.baseAlbumIds.forEach(id => {
            const album = this.allAlbums.find(a => a.id == id);
            if (album) {
                const badge = document.createElement('div');
                badge.className = 'surface px-2 py-1 border text-xs flex items-center gap-2';
                badge.innerHTML = `
                    <span>${this.escapeHtml(album.name)}</span>
                    <button class="bg-danger tag-text px-1 hover:bg-danger transition-colors" data-id="${id}">×</button>
                `;
                badge.querySelector('button').addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.baseAlbumIds.delete(parseInt(id));
                    this.renderBaseAlbumBadges();
                    this.renderBaseAlbumSelect();
                    // Update individual select if visible, as this album is now available again
                    if (this.selectedFileIndex !== null && typeof this.renderIndividualAlbumSelect === 'function') {
                        this.renderIndividualAlbumSelect();
                    }
                });
                container.appendChild(badge);
            }
        });

        if (container.children.length === 0) {
            container.classList.add('hidden');
        } else {
            container.classList.remove('hidden');
        }
    }

    renderIndividualAlbumSelect() {
        if (this.selectedFileIndex === null) return;
        const selectEl = document.getElementById('individual-album-select');
        if (!selectEl) return;

        if (!this.individualAlbumSelect) return;

        const fileData = this.uploadedFiles[this.selectedFileIndex];
        if (!fileData) return;

        const availableAlbums = this.allAlbums.filter(album =>
            !this.baseAlbumIds.has(album.id) &&
            !fileData.individualAlbumIds.has(album.id)
        );

        const options = [{ value: '', text: window.i18n.t('upload.base_settings.select_album'), selected: true }];
        availableAlbums.forEach(album => {
            options.push({ value: album.id, text: album.name });
        });

        this.individualAlbumSelect.setOptions(options);
    }

    renderIndividualAlbumBadges() {
        const container = document.getElementById('individual-albums-list');
        if (!container || this.selectedFileIndex === null) return;

        const fileData = this.uploadedFiles[this.selectedFileIndex];
        if (!fileData) return;

        container.innerHTML = '';

        this.baseAlbumIds.forEach(id => {
            const album = this.allAlbums.find(a => a.id == id);
            if (album) {
                const badge = document.createElement('div');
                badge.className = 'surface px-2 py-1 border text-xs flex items-center gap-2 opacity-70';
                badge.innerHTML = `
                    <span>${this.escapeHtml(album.name)}</span>
                    <span class="text-[10px] text-secondary">${window.i18n.t('upload.base_settings.base_badge')}</span>
                `;
                container.appendChild(badge);
            }
        });

        // Show individual albums
        fileData.individualAlbumIds.forEach(id => {
            const album = this.allAlbums.find(a => a.id == id);
            if (album) {
                const badge = document.createElement('div');
                badge.className = 'surface px-2 py-1 border text-xs flex items-center gap-2';
                badge.innerHTML = `
                    <span>${this.escapeHtml(album.name)}</span>
                    <button class="bg-danger tag-text px-1 hover:bg-danger transition-colors" data-id="${id}">×</button>
                `;
                badge.querySelector('button').addEventListener('click', (e) => {
                    e.stopPropagation();
                    fileData.individualAlbumIds.delete(parseInt(id));
                    this.renderIndividualAlbumBadges();
                    this.renderIndividualAlbumSelect();
                });
                container.appendChild(badge);
            }
        });
    }

    setupDragAndDrop() {
        this.uploadArea.addEventListener('click', () => {
            if (this.isProcessingFiles) return;
            this.fileInput.click();
        });

        this.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (!this.isProcessingFiles) {
                this.uploadArea.classList.add('drag-over');
            }
        });

        this.uploadArea.addEventListener('dragleave', () => {
            this.uploadArea.classList.remove('drag-over');
        });

        this.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            this.uploadArea.classList.remove('drag-over');
            if (this.isProcessingFiles) return;

            const files = Array.from(e.dataTransfer.files);
            this.handleFiles(files);
        });
    }

    setupFileInput() {
        this.fileInput.addEventListener('change', (e) => {
            if (this.isProcessingFiles) return;
            const files = Array.from(e.target.files);
            this.handleFiles(files);
        });
    }

    setupBaseControls() {
        // Create base controls container
        const controlsDiv = document.createElement('div');
        controlsDiv.id = 'base-controls';
        controlsDiv.className = 'bg p-4 border my-4';
        controlsDiv.style.display = 'none';
        controlsDiv.innerHTML = `
            <h3 class="text-sm font-bold mb-3">${window.i18n.t('upload.base_settings.title')}</h3>
            
            <div class="mb-4">
                <label class="block text-xs font-bold mb-2">${window.i18n.t('upload.base_settings.base_rating')}</label>
                <div id="base-rating" class="custom-select" data-value="safe">
                    <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 surface border text-xs cursor-pointer focus:outline-none focus:border-primary" type="button">
                        <span class="custom-select-value text">${window.i18n.t('upload.base_settings.safe')}</span>
                        <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary" width="12" height="12" viewBox="0 0 12 12">
                            <path fill="currentColor" d="M6 9L1 4h10z"/>
                        </svg>
                    </button>
                    <div class="custom-select-dropdown surface border border-primary max-h-60 overflow-y-auto shadow-lg">
                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs selected" data-value="safe">${window.i18n.t('common.safe')}</div>
                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs" data-value="questionable">${window.i18n.t('common.questionable')}</div>
                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs" data-value="explicit">${window.i18n.t('common.explicit')}</div>
                    </div>
                </div>
            </div>

            <div class="mb-4">
                <label class="block text-xs font-bold mb-2">${window.i18n.t('upload.base_settings.base_albums')}</label>
                <div class="flex flex-wrap gap-2 mb-2 hidden" id="base-albums-list"></div>
                <div id="base-album-select" class="custom-select" data-value="">
                    <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 surface border text-xs cursor-pointer focus:outline-none focus:border-primary" type="button">
                        <span class="custom-select-value text">${window.i18n.t('upload.base_settings.select_album')}</span>
                        <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary" width="12" height="12" viewBox="0 0 12 12">
                            <path fill="currentColor" d="M6 9L1 4h10z"/>
                        </svg>
                    </button>
                    <div class="custom-select-dropdown surface border border-primary max-h-60 overflow-y-auto shadow-lg">
                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs selected" data-value="">${window.i18n.t('upload.base_settings.select_album')}</div>
                    </div>
                </div>
            </div>
            
            <div class="mb-4">
                <label class="block text-xs font-bold mb-2">${window.i18n.t('upload.base_settings.base_source')}</label>
                <input type="url" id="base-source" placeholder="https://example.com/source" class="w-full surface px-3 py-2 border text-xs focus:outline-none focus:border-primary">
            </div>
            
            <div>
                <label class="block text-xs font-bold mb-2">${window.i18n.t('upload.base_settings.base_tags')}</label>
                <div style="position: relative;">
                    <div id="base-tags" contenteditable="true" data-placeholder="original highres cat_ears" class="tag-input w-full surface px-3 py-2 border text-xs focus:outline-none focus:border-primary" style="min-height: 1.5rem; white-space: pre-wrap; overflow-wrap: break-word;"></div>
                </div>
            </div>
        `;

        this.uploadArea.parentNode.insertBefore(controlsDiv, this.uploadArea.nextSibling);

        // Initialize custom select for base rating
        const baseRatingElement = document.getElementById('base-rating');
        if (baseRatingElement) {
            this.baseRatingSelect = new CustomSelect(baseRatingElement);

            // Listen for change events
            baseRatingElement.addEventListener('change', (e) => {
                this.baseRating = e.detail.value;
                this.updateAllMediaRatings();
            });
        }

        // Initialize custom select for base albums
        const baseAlbumElement = document.getElementById('base-album-select');
        if (baseAlbumElement) {
            this.baseAlbumSelect = new CustomSelect(baseAlbumElement);
            this.baseAlbumSelect.element.addEventListener('change', (e) => {
                const albumId = parseInt(e.detail.value);
                if (albumId) {
                    this.baseAlbumIds.add(albumId);
                    this.renderBaseAlbumBadges();
                    this.renderBaseAlbumSelect();

                    if (this.selectedFileIndex !== null && typeof this.renderIndividualAlbumSelect === 'function') {
                        this.renderIndividualAlbumSelect();
                    }
                }
            });
        }

        document.getElementById('base-source').addEventListener('input', (e) => {
            this.baseSource = e.target.value.trim();
            this.updateAllMediaSources();
        });

        const baseTagsInput = document.getElementById('base-tags');
        baseTagsInput.addEventListener('input', (e) => {
            this.baseTags = this.tagInputHelper.getValidTagsFromInput(e.target);
            this.updateAllMediaTags();
        });

        // Setup tag validation
        this.tagInputHelper.setupTagInput(baseTagsInput, 'base-tags', {
            onValidate: () => {
                this.baseTags = this.tagInputHelper.getValidTagsFromInput(baseTagsInput);
                this.updateAllMediaTags();
            }
        });

        // Initialize tag autocomplete if available
        if (typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(baseTagsInput, {
                multipleValues: true,
                allowCreate: true,
                onSelect: () => {
                    setTimeout(() => {
                        this.tagInputHelper.validateAndStyleTags(baseTagsInput);
                        this.baseTags = this.tagInputHelper.getValidTagsFromInput(baseTagsInput);
                        this.updateAllMediaTags();
                    }, 100);
                }
            });
        }
    }

    createPreviewGrid() {
        const gridDiv = document.createElement('div');
        gridDiv.id = 'preview-grid';
        gridDiv.style.display = 'none';
        gridDiv.innerHTML = `
            <div class="bg p-4 border mb-4">
                <h3 class="text-sm font-bold mb-3">${window.i18n.t('upload.preview.title')}</h3>
                <div id="preview-thumbnails" class="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-2 mb-4"></div>
                
                <div id="individual-controls" style="display: none;" class="border-t pt-4">
                    <h4 class="text-xs font-bold mb-3">${window.i18n.t('upload.preview.editing')}<span id="current-filename"></span></h4>
                    
                    <div class="mb-3">
                        <label class="block text-xs font-bold mb-2">${window.i18n.t('upload.preview.individual_rating')}</label>
                        <div id="individual-rating" class="custom-select" data-value="safe">
                            <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 surface border text-xs cursor-pointer focus:outline-none focus:border-primary" type="button">
                                <span class="custom-select-value text">${window.i18n.t('upload.base_settings.safe')}</span>
                                <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary" width="12" height="12" viewBox="0 0 12 12">
                                    <path fill="currentColor" d="M6 9L1 4h10z"/>
                                </svg>
                            </button>
                            <div class="custom-select-dropdown surface border border-primary max-h-60 overflow-y-auto shadow-lg">
                                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs selected" data-value="safe">${window.i18n.t('common.safe')}</div>
                                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs" data-value="questionable">${window.i18n.t('common.questionable')}</div>
                                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs" data-value="explicit">${window.i18n.t('common.explicit')}</div>
                            </div>
                        </div>
                    </div>

                    <div class="mb-4">
                        <label class="block text-xs font-bold mb-2">${window.i18n.t('upload.preview.individual_albums')}</label>
                        <div class="flex flex-wrap gap-2 mb-2" id="individual-albums-list"></div>
                        <div id="individual-album-select" class="custom-select" data-value="">
                            <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 surface border text-xs cursor-pointer focus:outline-none focus:border-primary" type="button">
                                <span class="custom-select-value text">${window.i18n.t('upload.base_settings.select_album')}</span>
                                <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary" width="12" height="12" viewBox="0 0 12 12">
                                    <path fill="currentColor" d="M6 9L1 4h10z"/>
                                </svg>
                            </button>
                            <div class="custom-select-dropdown surface border border-primary max-h-60 overflow-y-auto shadow-lg">
                                <!-- Options populated dynamically -->
                            </div>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label class="block text-xs font-bold mb-2">${window.i18n.t('upload.preview.individual_source')}</label>
                        <input type="url" id="individual-source" placeholder="https://example.com/source" class="w-full surface px-3 py-2 border text-xs focus:outline-none focus:border-primary">
                    </div>
                    
                    <div class="mb-3">
                        <label class="block text-xs font-bold mb-2">${window.i18n.t('upload.preview.additional_tags')}</label>
                        <div style="position: relative;">
                            <div id="individual-tags" contenteditable="true" data-placeholder="solo long_hair" class="tag-input w-full surface px-3 py-2 border text-xs focus:outline-none focus:border-primary" style="min-height: 1.5rem; white-space: pre-wrap; overflow-wrap: break-word;"></div>
                        </div>
                    </div>
                    
                    <div class="text-xs text-secondary mb-2">
                        ${window.i18n.t('upload.preview.final_tags')}<span id="final-tags-preview" class="text"></span>
                    </div>
                    
                    <button id="remove-media-btn" class="btn-danger px-3 py-2">${window.i18n.t('upload.preview.remove_media')}</button>
                </div>
            </div>
        `;

        document.getElementById('base-controls').parentNode.insertBefore(gridDiv, document.getElementById('base-controls').nextSibling);

        // Initialize custom select for individual rating
        const individualRatingElement = document.getElementById('individual-rating');
        if (individualRatingElement) {
            this.individualRatingSelect = new CustomSelect(individualRatingElement);

            // Listen for change events
            individualRatingElement.addEventListener('change', (e) => {
                if (this.selectedFileIndex !== null) {
                    this.uploadedFiles[this.selectedFileIndex].rating = e.detail.value;
                    this.updateThumbnailIndicator(this.selectedFileIndex);
                }
            });
        }

        // Initialize custom select for individual albums
        const individualAlbumElement = document.getElementById('individual-album-select');
        if (individualAlbumElement) {
            this.individualAlbumSelect = new CustomSelect(individualAlbumElement);
            this.individualAlbumSelect.element.addEventListener('change', (e) => {
                const albumId = parseInt(e.detail.value);
                if (albumId && this.selectedFileIndex !== null) {
                    this.uploadedFiles[this.selectedFileIndex].individualAlbumIds.add(albumId);
                    this.renderIndividualAlbumBadges();
                    this.renderIndividualAlbumSelect();
                }
            });
        }

        document.getElementById('individual-source').addEventListener('input', (e) => {
            if (this.selectedFileIndex !== null) {
                this.uploadedFiles[this.selectedFileIndex].source = e.target.value.trim();
            }
        });

        const individualTagsInput = document.getElementById('individual-tags');
        individualTagsInput.addEventListener('input', (e) => {
            if (this.selectedFileIndex !== null) {
                this.uploadedFiles[this.selectedFileIndex].additionalTags =
                    this.tagInputHelper.getValidTagsFromInput(e.target);
                this.updateFinalTagsPreview();
                this.updateThumbnailIndicator(this.selectedFileIndex);
            }
        });

        // Setup tag validation for individual tags
        this.tagInputHelper.setupTagInput(individualTagsInput, 'individual-tags', {
            onValidate: () => {
                if (this.selectedFileIndex !== null) {
                    this.uploadedFiles[this.selectedFileIndex].additionalTags =
                        this.tagInputHelper.getValidTagsFromInput(individualTagsInput);
                    this.updateFinalTagsPreview();
                    this.updateThumbnailIndicator(this.selectedFileIndex);
                }
            }
        });

        document.getElementById('remove-media-btn').addEventListener('click', () => {
            if (this.selectedFileIndex !== null) {
                this.removeMedia(this.selectedFileIndex);
            }
        });

        // Initialize tag autocomplete for individual tags
        if (typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(individualTagsInput, {
                multipleValues: true,
                allowCreate: true,
                onSelect: () => {
                    setTimeout(() => {
                        this.tagInputHelper.validateAndStyleTags(individualTagsInput);
                        if (this.selectedFileIndex !== null) {
                            this.uploadedFiles[this.selectedFileIndex].additionalTags =
                                this.tagInputHelper.getValidTagsFromInput(individualTagsInput);
                            this.updateFinalTagsPreview();
                            this.updateThumbnailIndicator(this.selectedFileIndex);
                        }
                    }, 100);
                }
            });
        }
    }

    createSubmitControls() {
        const submitDiv = document.createElement('div');
        submitDiv.id = 'submit-controls';
        submitDiv.style.display = 'none';
        submitDiv.className = 'flex gap-2';
        submitDiv.innerHTML = `
            <button id="cancel-all-btn" class="btn flex-1">${window.i18n.t('upload.submit.cancel_all')}</button>
            <button id="submit-all-btn" class="btn-primary flex-1 font-bold">${window.i18n.t('upload.submit.submit_all')}</button>
        `;

        document.getElementById('preview-grid').parentNode.insertBefore(submitDiv, document.getElementById('preview-grid').nextSibling);

        document.getElementById('submit-all-btn').addEventListener('click', () => {
            this.submitAll();
        });

        document.getElementById('cancel-all-btn').addEventListener('click', () => {
            this.cancelAll();
        });
    }

    async computeFileHash(file) {
        // Sample small slices from the file instead of reading the entire thing
        // into memory. This keeps usage under 200 KB even for multi-GiB files.
        // The hash is only used for client-side queue deduplication; the server
        // computes its own hash for real duplicate detection.
        const SAMPLE_SIZE = 65536; // 64 KB per sample
        const slices = [
            file.slice(0, SAMPLE_SIZE),
        ];
        if (file.size > SAMPLE_SIZE * 2) {
            const mid = Math.floor(file.size / 2);
            slices.push(file.slice(mid, mid + SAMPLE_SIZE));
        }
        if (file.size > SAMPLE_SIZE) {
            slices.push(file.slice(file.size - SAMPLE_SIZE, file.size));
        }

        const metaString = `${file.name}|${file.size}|${file.lastModified}|${file.type}`;
        const metaBytes = new TextEncoder().encode(metaString);

        // Read all slices
        const sampleBuffers = await Promise.all(slices.map(s => s.arrayBuffer()));
        const totalLen = metaBytes.length + sampleBuffers.reduce((a, b) => a + b.byteLength, 0);
        const combined = new Uint8Array(totalLen);
        let offset = 0;
        combined.set(metaBytes, offset); offset += metaBytes.length;
        for (const buf of sampleBuffers) {
            combined.set(new Uint8Array(buf), offset);
            offset += buf.byteLength;
        }

        // Use crypto.subtle if available, otherwise fall back to a simple hash
        if (window.crypto && window.crypto.subtle) {
            try {
                const hashBuffer = await crypto.subtle.digest('SHA-256', combined);
                const hashArray = Array.from(new Uint8Array(hashBuffer));
                return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
            } catch (error) {
                console.warn('crypto.subtle failed, falling back to simple hash:', error);
            }
        }

        // Simple numeric hash fallback
        let hash = 0;
        for (let i = 0; i < combined.length; i++) {
            hash = ((hash << 5) - hash) + combined[i];
            hash = hash & hash;
        }

        // Convert to hex string
        return Math.abs(hash).toString(16).padStart(8, '0');
    }

    async handleFiles(files) {
        if (this.isProcessingFiles) return;
        this.isProcessingFiles = true;

        // Show loading state on the upload area
        const originalContent = this.uploadArea.innerHTML;
        const uploadAreaText = this.uploadArea.querySelector('p');
        if (uploadAreaText) {
            uploadAreaText.dataset.originalText = uploadAreaText.textContent;
            uploadAreaText.textContent = window.i18n.t('upload.progress.processing_files') || 'Processing files...';
        }
        this.uploadArea.classList.add('opacity-50', 'pointer-events-none');

        try {
            for (const file of files) {
                // Check if it's a zip or tar.gz file
                if (file.name.endsWith('.zip') || file.name.endsWith('.tar.gz') || file.name.endsWith('.tgz')) {
                    await this.handleArchive(file);
                    continue;
                }

                if (this.isValidFile(file)) {
                    // Compute hash for duplicate detection
                    const hash = await this.computeFileHash(file);

                    // Silently ignore duplicates
                    if (this.fileHashes.has(hash)) {
                        continue;
                    }

                    this.fileHashes.add(hash);

                    const fileData = {
                        file: file,
                        hash: hash,
                        rating: this.baseRating,
                        source: this.baseSource,
                        additionalTags: await this.getAutoTagsForFile(file),
                        individualAlbumIds: new Set(),
                        preview: null,
                        scannedPath: null
                    };

                    this.uploadedFiles.push(fileData);
                    this.createPreview(fileData, this.uploadedFiles.length - 1);
                }
            }

            if (this.uploadedFiles.length > 0) {
                document.getElementById('base-controls').style.display = 'block';
                document.getElementById('preview-grid').style.display = 'block';
                document.getElementById('submit-controls').style.display = 'flex';
            }
        } finally {
            this.isProcessingFiles = false;
            this.uploadArea.classList.remove('opacity-50', 'pointer-events-none');
            if (uploadAreaText && uploadAreaText.dataset.originalText) {
                uploadAreaText.textContent = uploadAreaText.dataset.originalText;
                delete uploadAreaText.dataset.originalText;
            }
        }
    }

    async handleArchive(archiveFile) {
        // Show loading indicator
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'bg-primary primary-text p-2 mb-2 text-xs';
        loadingDiv.textContent = window.i18n.t('upload.progress.extracting', { filename: archiveFile.name });
        this.uploadArea.parentNode.insertBefore(loadingDiv, this.uploadArea.nextSibling);

        try {
            const CHUNK_SIZE = 99 * 1024 * 1024; // 99MB per chunk
            const totalChunks = Math.ceil(archiveFile.size / CHUNK_SIZE);
            let uploadId = null;

            // Upload chunks sequentially with the upload_id that's assigned by the server
            for (let i = 0; i < totalChunks; i++) {
                const start = i * CHUNK_SIZE;
                const end = Math.min(start + CHUNK_SIZE, archiveFile.size);
                const chunk = archiveFile.slice(start, end);

                loadingDiv.textContent = window.i18n.t('upload.progress.extracting', { filename: archiveFile.name })
                    + ` (${i + 1}/${totalChunks})`;

                const chunkForm = new FormData();
                chunkForm.append('file', chunk, archiveFile.name);
                if (uploadId) chunkForm.append('upload_id', uploadId);
                chunkForm.append('chunk_index', i.toString());
                chunkForm.append('total_chunks', totalChunks.toString());
                chunkForm.append('filename', archiveFile.name);

                const chunkResponse = await fetch('/api/media/archive-chunk', {
                    method: 'POST',
                    body: chunkForm
                });

                if (!chunkResponse.ok) {
                    const errorData = await chunkResponse.json().catch(() => null);
                    const detail = errorData?.detail || chunkResponse.statusText;
                    throw new Error(`Failed to upload chunk ${i + 1}/${totalChunks}: ${detail}`);
                }

                const chunkData = await chunkResponse.json();
                if (i === 0) uploadId = chunkData.upload_id;
            }

            // Trigger extraction
            loadingDiv.textContent = window.i18n.t('upload.progress.extracting', { filename: archiveFile.name });

            const extractForm = new FormData();
            extractForm.append('upload_id', uploadId);

            const response = await fetch('/api/media/extract-archive', {
                method: 'POST',
                body: extractForm
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => null);
                const detail = errorData?.detail || response.statusText;
                throw new Error(`Failed to extract archive: ${detail}`);
            }

            const result = await response.json();

            // Fetch each extracted file individually
            for (let i = 0; i < result.files.length; i++) {
                const extractedFileData = result.files[i];

                loadingDiv.textContent = window.i18n.t('upload.progress.extracting', { filename: archiveFile.name })
                    + ` (${i + 1}/${result.files.length})`;

                const fileResponse = await fetch(`/api/media/archive-file/${result.upload_id}/${extractedFileData.file_id}`);
                if (!fileResponse.ok) {
                    console.warn(`Failed to fetch extracted file: ${extractedFileData.filename}`);
                    continue;
                }

                const blob = await fileResponse.blob();
                const file = new File([blob], extractedFileData.filename, { type: extractedFileData.mime_type });

                if (this.isValidFile(file)) {
                    const hash = await this.computeFileHash(file);

                    if (this.fileHashes.has(hash)) {
                        continue;
                    }

                    this.fileHashes.add(hash);

                    const fileData = {
                        file: file,
                        hash: hash,
                        rating: this.baseRating,
                        source: this.baseSource,
                        additionalTags: await this.getAutoTagsForFile(file),
                        individualAlbumIds: new Set(),
                        preview: null,
                        scannedPath: null
                    };

                    this.uploadedFiles.push(fileData);
                    this.createPreview(fileData, this.uploadedFiles.length - 1);
                }
            }

            // Clean up extracted files on the server
            fetch(`/api/media/archive-cleanup/${result.upload_id}`, { method: 'DELETE' }).catch(() => { });

            loadingDiv.textContent = window.i18n.t('upload.progress.extracted_success', { count: result.files.length, filename: archiveFile.name });
            setTimeout(() => loadingDiv.remove(), 3000);

        } catch (error) {
            console.error('Archive extraction error:', error);
            loadingDiv.className = 'bg-danger tag-text p-2 mb-2 text-xs';
            loadingDiv.textContent = window.i18n.t('upload.progress.extracted_error', { filename: archiveFile.name, error: error.message });
            setTimeout(() => loadingDiv.remove(), 5000);
        }
    }

    isValidFile(file) {
        const validTypes = [
            'image/jpeg', 'image/png', 'image/gif', 'image/webp',
            'video/mp4', 'video/webm'
        ];
        return validTypes.includes(file.type);
    }

    createPreview(fileData, index) {
        const container = document.getElementById('preview-thumbnails');
        const thumbnailDiv = document.createElement('div');
        thumbnailDiv.className = 'relative cursor-pointer border-2 hover:border-primary transition-colors';
        thumbnailDiv.dataset.index = index;

        const isVideo = fileData.file.type.startsWith('video/');

        // Scanned files are zero-byte stubs so use the server URL for preview
        const previewSrc = fileData.scannedPath
            ? `/api/admin/get-untracked-file?path=${encodeURIComponent(fileData.scannedPath)}`
            : URL.createObjectURL(fileData.file);

        if (isVideo) {
            const video = document.createElement('video');
            video.className = 'w-full h-24 object-cover';
            video.src = previewSrc;
            video.muted = true;
            thumbnailDiv.appendChild(video);
        } else {
            const img = document.createElement('img');
            img.className = 'w-full h-24 object-cover';
            img.src = previewSrc;
            thumbnailDiv.appendChild(img);
        }

        // Add indicator overlay
        const indicator = document.createElement('div');
        indicator.className = 'absolute top-0 right-0 surface bg-opacity-75 px-1 text-xs';
        indicator.innerHTML = `<span class="rating-indicator">${fileData.rating[0].toUpperCase()}</span>`;
        thumbnailDiv.appendChild(indicator);

        // Add tags indicator
        const tagsIndicator = document.createElement('div');
        tagsIndicator.className = 'absolute bottom-0 left-0 right-0 surface bg-opacity-75 px-1 text-xs truncate tags-indicator';
        tagsIndicator.textContent = this.getFullTags(fileData).join(' ') || window.i18n.t('common.no_tags');
        thumbnailDiv.appendChild(tagsIndicator);

        thumbnailDiv.addEventListener('click', (e) => {
            const clickedIndex = parseInt(e.currentTarget.dataset.index);
            if (this.selectedFileIndex === clickedIndex) {
                const fileData = this.uploadedFiles[clickedIndex];
                if (fileData && fileData.file) {
                    const src = fileData.scannedPath
                        ? `/api/admin/get-untracked-file?path=${encodeURIComponent(fileData.scannedPath)}`
                        : URL.createObjectURL(fileData.file);
                    const isVideo = fileData.file.type.startsWith('video/');
                    this.fullscreenViewer.open(src, isVideo);
                }
            } else {
                this.selectMedia(clickedIndex);
            }
        });

        container.appendChild(thumbnailDiv);
    }

    selectMedia(index) {
        this.selectedFileIndex = index;
        const fileData = this.uploadedFiles[index];

        // Safety check
        if (!fileData) {
            console.error('No file data at index', index);
            return;
        }

        // Update UI
        document.querySelectorAll('#preview-thumbnails > div').forEach((div, i) => {
            if (i === index) {
                div.classList.add('border-primary');
                div.classList.remove('border');
            } else {
                div.classList.remove('border-primary');
                div.classList.add('border');
            }
        });

        // Show individual controls
        document.getElementById('individual-controls').style.display = 'block';
        document.getElementById('current-filename').textContent = fileData.file.name;

        // Update individual rating select
        if (this.individualRatingSelect) {
            this.individualRatingSelect.setValue(fileData.rating);
        }

        document.getElementById('individual-source').value = fileData.source || '';
        const individualTagsInput = document.getElementById('individual-tags');
        individualTagsInput.textContent = fileData.additionalTags.join(' ');

        // Validate existing tags
        setTimeout(() => this.tagInputHelper.validateAndStyleTags(individualTagsInput), 100);

        this.updateFinalTagsPreview();
        this.renderIndividualAlbumBadges();
        this.renderIndividualAlbumSelect();
    }

    updateFinalTagsPreview() {
        if (this.selectedFileIndex !== null) {
            const fileData = this.uploadedFiles[this.selectedFileIndex];
            const finalTags = this.getFullTags(fileData);
            document.getElementById('final-tags-preview').textContent = finalTags.join(' ') || window.i18n.t('common.none');
        }
    }

    getFullTags(fileData) {
        return [...this.baseTags, ...fileData.additionalTags];
    }

    updateAllMediaRatings() {
        this.uploadedFiles.forEach((fileData, index) => {
            fileData.rating = this.baseRating;
            this.updateThumbnailIndicator(index);
        });

        if (this.selectedFileIndex !== null && this.individualRatingSelect) {
            this.individualRatingSelect.setValue(this.baseRating);
        }
    }

    updateAllMediaSources() {
        this.uploadedFiles.forEach((fileData) => {
            fileData.source = this.baseSource;
        });

        if (this.selectedFileIndex !== null) {
            document.getElementById('individual-source').value = this.baseSource;
        }
    }

    updateAllMediaTags() {
        // Update all thumbnails
        this.uploadedFiles.forEach((fileData, index) => {
            this.updateThumbnailIndicator(index);
        });

        // Update preview if media is selected
        if (this.selectedFileIndex !== null) {
            this.updateFinalTagsPreview();
        }
    }

    updateThumbnailIndicator(index) {
        const thumbnail = document.querySelector(`#preview-thumbnails > div[data-index="${index}"]`);
        if (thumbnail) {
            const fileData = this.uploadedFiles[index];
            const ratingIndicator = thumbnail.querySelector('.rating-indicator');
            const tagsIndicator = thumbnail.querySelector('.tags-indicator');

            if (ratingIndicator) {
                ratingIndicator.textContent = fileData.rating[0].toUpperCase();
            }

            if (tagsIndicator) {
                const fullTags = this.getFullTags(fileData);
                tagsIndicator.textContent = fullTags.join(' ') || window.i18n.t('common.no_tags');
            }
        }
    }

    removeMedia(index) {
        // If only one file left, cancel all
        if (this.uploadedFiles.length === 1) {
            this.cancelAll();
            return;
        }

        // Remove file hash from set
        const fileData = this.uploadedFiles[index];
        this.fileHashes.delete(fileData.hash);

        // Remove thumbnail
        const thumbnail = document.querySelector(`#preview-thumbnails > div[data-index="${index}"]`);
        if (thumbnail) {
            thumbnail.remove();
        }

        // Remove from array
        this.uploadedFiles.splice(index, 1);

        // Update remaining thumbnail indices
        document.querySelectorAll('#preview-thumbnails > div').forEach((div, i) => {
            div.dataset.index = i;
        });

        // Select the media to the left, or first item if we removed the first
        const newIndex = Math.min(index > 0 ? index - 1 : 0, this.uploadedFiles.length - 1);
        if (this.uploadedFiles.length > 0) {
            this.selectMedia(newIndex);
        }
    }

    async submitAll() {
        if (this.uploadedFiles.length === 0) return;

        const submitBtn = document.getElementById('submit-all-btn');
        const cancelBtn = document.getElementById('cancel-all-btn');
        const originalText = submitBtn.textContent;

        submitBtn.disabled = true;
        cancelBtn.disabled = true;
        submitBtn.textContent = window.i18n.t('upload.progress.uploading');

        // Lock all controls to prevent edits during upload
        const baseControls = document.getElementById('base-controls');
        const previewGrid = document.getElementById('preview-grid');
        if (baseControls) baseControls.classList.add('opacity-50', 'pointer-events-none');
        if (previewGrid) previewGrid.classList.add('opacity-50', 'pointer-events-none');
        this.uploadArea.classList.add('opacity-50', 'pointer-events-none');

        let successCount = 0;
        let failCount = 0;
        let duplicateCount = 0;

        try {
            for (let i = 0; i < this.uploadedFiles.length; i++) {
                const fileData = this.uploadedFiles[i];
                submitBtn.textContent = window.i18n.t('upload.progress.uploading_progress', { current: i + 1, total: this.uploadedFiles.length });

                try {
                    await this.uploadFile(fileData);
                    successCount++;
                } catch (error) {
                    console.error('Upload error:', error);

                    // Check if it's a duplicate error (409 status)
                    if (error.message.includes('409') || error.message.includes('already exists')) {
                        duplicateCount++;
                    } else {
                        failCount++;
                    }
                }
            }
        } finally {
            // Unlock controls
            if (baseControls) baseControls.classList.remove('opacity-50', 'pointer-events-none');
            if (previewGrid) previewGrid.classList.remove('opacity-50', 'pointer-events-none');
            this.uploadArea.classList.remove('opacity-50', 'pointer-events-none');
        }

        // Show results
        let message = window.i18n.t('upload.progress.upload_success', { count: successCount });
        if (duplicateCount > 0) {
            message += ` ${window.i18n.t('upload.progress.duplicates_skipped', { count: duplicateCount })}`;
        }
        if (failCount > 0) {
            message += ` ${window.i18n.t('upload.progress.failed', { count: failCount })}`;
        }

        app.showNotification(message, 'success');

        // Reset
        this.cancelAll();

        // Reload gallery if on gallery page
        if (window.gallery) {
            window.location.reload();
        }
    }

    async uploadFile(fileData) {
        const CHUNK_SIZE = 99 * 1024 * 1024; // 99MB (should always be the same as backend MAX_CHUNK_SIZE)
        const allTags = [...this.baseTags, ...fileData.additionalTags];
        const uniqueTags = [...new Set(allTags)];
        const allAlbumIds = new Set([...this.baseAlbumIds, ...(fileData.individualAlbumIds || [])]);

        // Use chunked upload for large files, single POST for small ones
        if (!fileData.scannedPath && fileData.file && fileData.file.size > CHUNK_SIZE) {
            return await this._uploadFileChunked(fileData, uniqueTags, allAlbumIds, CHUNK_SIZE);
        }

        const formData = new FormData();
        if (fileData.scannedPath) {
            formData.append('scanned_path', fileData.scannedPath);
        } else {
            formData.append('file', fileData.file);
        }

        formData.append('rating', fileData.rating);
        formData.append('tags', uniqueTags.join(' '));

        if (allAlbumIds.size > 0) {
            formData.append('album_ids', Array.from(allAlbumIds).join(','));
        }

        if (fileData.source) {
            formData.append('source', fileData.source);
        }

        if (fileData.autoCreateTags && fileData.categoryHints) {
            formData.append('category_hints', JSON.stringify(fileData.categoryHints));
        }

        const response = await fetch('/api/media/', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(`Upload failed (${response.status}): ${error.detail || response.statusText}`);
        }

        return await response.json();
    }

    async _uploadFileChunked(fileData, uniqueTags, allAlbumIds, chunkSize) {
        const file = fileData.file;
        const totalChunks = Math.ceil(file.size / chunkSize);
        let uploadId = null;

        // Upload chunks sequentially with the upload_id that's assigned by the server
        for (let i = 0; i < totalChunks; i++) {
            const start = i * chunkSize;
            const end = Math.min(start + chunkSize, file.size);
            const chunk = file.slice(start, end);

            const chunkForm = new FormData();
            chunkForm.append('file', chunk, file.name);
            if (uploadId) chunkForm.append('upload_id', uploadId);
            chunkForm.append('chunk_index', i.toString());
            chunkForm.append('total_chunks', totalChunks.toString());
            chunkForm.append('filename', file.name);

            const chunkResponse = await fetch('/api/media/upload-chunk', {
                method: 'POST',
                body: chunkForm
            });

            if (!chunkResponse.ok) {
                const errorData = await chunkResponse.json().catch(() => null);
                const detail = errorData?.detail || chunkResponse.statusText;
                throw new Error(`Failed to upload chunk ${i + 1}/${totalChunks}: ${detail}`);
            }

            const chunkData = await chunkResponse.json();
            if (i === 0) uploadId = chunkData.upload_id;
        }

        // Reassemble and process
        const finalizeForm = new FormData();
        finalizeForm.append('upload_id', uploadId);
        finalizeForm.append('rating', fileData.rating);
        finalizeForm.append('tags', uniqueTags.join(' '));

        if (allAlbumIds.size > 0) {
            finalizeForm.append('album_ids', Array.from(allAlbumIds).join(','));
        }

        if (fileData.source) {
            finalizeForm.append('source', fileData.source);
        }

        if (fileData.autoCreateTags && fileData.categoryHints) {
            finalizeForm.append('category_hints', JSON.stringify(fileData.categoryHints));
        }

        const response = await fetch('/api/media/upload-finalize', {
            method: 'POST',
            body: finalizeForm
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(`Upload failed (${response.status}): ${error.detail || response.statusText}`);
        }

        return await response.json();
    }

    cancelAll() {
        // Clear all data
        this.uploadedFiles = [];
        this.selectedFileIndex = null;
        this.baseTags = [];
        this.baseRating = 'safe';
        this.baseSource = '';
        this.baseAlbumIds = new Set();
        this.fileHashes.clear();

        // Clear UI
        document.getElementById('preview-thumbnails').innerHTML = '';
        const baseTagsInput = document.getElementById('base-tags');
        const individualTagsInput = document.getElementById('individual-tags');
        if (baseTagsInput) baseTagsInput.textContent = '';
        if (individualTagsInput) individualTagsInput.textContent = '';

        this.renderBaseAlbumBadges();
        this.renderBaseAlbumSelect();

        // Reset custom selects
        if (this.baseRatingSelect) {
            this.baseRatingSelect.setValue('safe');
        }
        if (this.individualRatingSelect) {
            this.individualRatingSelect.setValue('safe');
        }

        document.getElementById('base-source').value = '';
        document.getElementById('individual-controls').style.display = 'none';

        // Hide sections
        document.getElementById('base-controls').style.display = 'none';
        document.getElementById('preview-grid').style.display = 'none';
        document.getElementById('submit-controls').style.display = 'none';

        // Clear helper cache
        this.tagInputHelper.clearCache();
        this.tagInputHelper.clearTimeouts();

        // Reset file input
        this.fileInput.value = '';
    }

    async addScannedFile(file, originalPath) {
        if (this.isValidFile(file)) {
            const realSize = file._scannedSize ?? file.size;
            const metaString = `${file.name}|${realSize}|${file.type}|${originalPath}`;
            const metaBytes = new TextEncoder().encode(metaString);
            let hash;
            if (window.crypto && window.crypto.subtle) {
                try {
                    const hashBuffer = await crypto.subtle.digest('SHA-256', metaBytes);
                    hash = Array.from(new Uint8Array(hashBuffer))
                        .map(b => b.toString(16).padStart(2, '0')).join('');
                } catch (_) {
                    hash = originalPath; // fallback: path is already unique
                }
            } else {
                hash = originalPath;
            }

            // Silently ignore duplicates
            if (this.fileHashes.has(hash)) {
                return;
            }

            this.fileHashes.add(hash);

            const fileData = {
                file: file,
                hash: hash,
                rating: this.baseRating,
                source: this.baseSource,
                additionalTags: await this.getAutoTagsForFile(file),
                individualAlbumIds: new Set(),
                preview: null,
                scannedPath: originalPath
            };

            this.uploadedFiles.push(fileData);
            this.createPreview(fileData, this.uploadedFiles.length - 1);

            // Show UI sections if not already visible
            if (this.uploadedFiles.length === 1) {
                document.getElementById('base-controls').style.display = 'block';
                document.getElementById('preview-grid').style.display = 'block';
                document.getElementById('submit-controls').style.display = 'flex';
            }
        }
    }

    async addBooruImport(file, metadata) {
        const hash = await this.computeFileHash(file);

        if (this.fileHashes.has(hash)) {
            return;
        }

        this.fileHashes.add(hash);

        const fileData = {
            file: file,
            hash: hash,
            rating: metadata.rating || this.baseRating,
            source: metadata.source || this.baseSource,
            additionalTags: metadata.tags || [],
            individualAlbumIds: new Set(),
            preview: null,
            scannedPath: null,
            categoryHints: metadata.categoryHints || null,
            autoCreateTags: metadata.autoCreateTags || false,
        };

        this.uploadedFiles.push(fileData);
        this.createPreview(fileData, this.uploadedFiles.length - 1);

        document.getElementById('base-controls').style.display = 'block';
        document.getElementById('preview-grid').style.display = 'block';
        document.getElementById('submit-controls').style.display = 'flex';
    }

    isFileQueued(filePath) {
        if (this.uploadedFiles.some(f => f.scannedPath === filePath)) {
            return true;
        }

        const filename = filePath.split('/').pop().split('\\').pop();
        return this.uploadedFiles.some(f => f.file.name === filename);
    }
}

// Initialize uploader if upload area exists
if (document.getElementById('upload-area')) {
    window.uploaderInstance = new Uploader();
}
