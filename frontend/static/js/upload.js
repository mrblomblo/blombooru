class Uploader {
    constructor() {
        this.uploadArea = document.getElementById('upload-area');
        this.fileInput = document.getElementById('file-input');
        this.uploadedFiles = [];
        this.selectedFileIndex = null;
        this.baseRating = 'safe';
        this.baseTags = [];
        this.baseSource = '';
        this.fileHashes = new Set();
        this.tagInputHelper = new TagInputHelper();
        this.baseRatingSelect = null;
        this.individualRatingSelect = null;
        this.fullscreenViewer = new FullscreenMediaViewer();

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
    }

    setupDragAndDrop() {
        this.uploadArea.addEventListener('click', () => {
            this.fileInput.click();
        });

        this.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.uploadArea.classList.add('drag-over');
        });

        this.uploadArea.addEventListener('dragleave', () => {
            this.uploadArea.classList.remove('drag-over');
        });

        this.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            this.uploadArea.classList.remove('drag-over');

            const files = Array.from(e.dataTransfer.files);
            this.handleFiles(files);
        });
    }

    setupFileInput() {
        this.fileInput.addEventListener('change', (e) => {
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
            <h3 class="text-sm font-bold mb-3">Base Settings (applies to all media)</h3>
            
            <div class="mb-4">
                <label class="block text-xs font-bold mb-2">Base Rating</label>
                <div id="base-rating" class="custom-select" data-value="safe">
                    <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 surface border text-xs cursor-pointer focus:outline-none focus:border-primary" type="button">
                        <span class="custom-select-value text-secondary">Safe</span>
                        <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary" width="12" height="12" viewBox="0 0 12 12">
                            <path fill="currentColor" d="M6 9L1 4h10z"/>
                        </svg>
                    </button>
                    <div class="custom-select-dropdown surface border border-primary max-h-60 overflow-y-auto shadow-lg">
                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs selected" data-value="safe">Safe</div>
                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs" data-value="questionable">Questionable</div>
                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs" data-value="explicit">Explicit</div>
                    </div>
                </div>
            </div>
            
            <div class="mb-4">
                <label class="block text-xs font-bold mb-2">Base Source URL (optional)</label>
                <input type="url" id="base-source" placeholder="https://example.com/source" class="w-full surface px-3 py-2 border text-xs focus:outline-none focus:border-primary">
            </div>
            
            <div>
                <label class="block text-xs font-bold mb-2">Base Tags (prefixed to all media)</label>
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
                <h3 class="text-sm font-bold mb-3">Uploaded Media (click to edit individual rating, source, and tags)</h3>
                <div id="preview-thumbnails" class="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-2 mb-4"></div>
                
                <div id="individual-controls" style="display: none;" class="border-t pt-4">
                    <h4 class="text-xs font-bold mb-3">Editing: <span id="current-filename"></span></h4>
                    
                    <div class="mb-3">
                        <label class="block text-xs font-bold mb-2">Individual Rating</label>
                        <div id="individual-rating" class="custom-select" data-value="safe">
                            <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 surface border text-xs cursor-pointer focus:outline-none focus:border-primary" type="button">
                                <span class="custom-select-value text-secondary">Safe</span>
                                <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary" width="12" height="12" viewBox="0 0 12 12">
                                    <path fill="currentColor" d="M6 9L1 4h10z"/>
                                </svg>
                            </button>
                            <div class="custom-select-dropdown surface border border-primary max-h-60 overflow-y-auto shadow-lg">
                                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs selected" data-value="safe">Safe</div>
                                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs" data-value="questionable">Questionable</div>
                                <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs" data-value="explicit">Explicit</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label class="block text-xs font-bold mb-2">Individual Source URL (optional)</label>
                        <input type="url" id="individual-source" placeholder="https://example.com/source" class="w-full surface px-3 py-2 border text-xs focus:outline-none focus:border-primary">
                    </div>
                    
                    <div class="mb-3">
                        <label class="block text-xs font-bold mb-2">Additional Tags (base tags are prefixed automatically)</label>
                        <div style="position: relative;">
                            <div id="individual-tags" contenteditable="true" data-placeholder="solo long_hair" class="tag-input w-full surface px-3 py-2 border text-xs focus:outline-none focus:border-primary" style="min-height: 1.5rem; white-space: pre-wrap; overflow-wrap: break-word;"></div>
                        </div>
                    </div>
                    
                    <div class="text-xs text-secondary mb-2">
                        Final tags: <span id="final-tags-preview" class="text"></span>
                    </div>
                    
                    <button id="remove-media-btn" class="px-3 py-2 bg-danger transition-colors hover:bg-danger tag-text text-xs">Remove This Media</button>
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
            <button id="cancel-all-btn" class="flex-1 px-4 py-2 surface-light transition-colors hover:surface-light text text-xs">Cancel & Clear All</button>
            <button id="submit-all-btn" class="flex-1 px-4 py-2 bg-primary primary-text transition-colors hover:bg-primary text-xs font-bold">Submit All Media</button>
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
        // Check if crypto.subtle is available (HTTPS or localhost)
        if (window.crypto && window.crypto.subtle) {
            try {
                const arrayBuffer = await file.arrayBuffer();
                const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
                const hashArray = Array.from(new Uint8Array(hashBuffer));
                const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
                return hashHex;
            } catch (error) {
                console.warn('crypto.subtle failed, falling back to simple hash:', error);
            }
        }

        // Fallback: Use a simple hash based on file properties and content sample
        const arrayBuffer = await file.arrayBuffer();
        const bytes = new Uint8Array(arrayBuffer);

        // Create a hash from file metadata and content sample
        let hash = 0;
        const str = `${file.name}-${file.size}-${file.lastModified}-${file.type}`;

        // Hash the metadata string
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32bit integer
        }

        // Sample bytes from the file (beginning, middle, end)
        const sampleSize = Math.min(1000, bytes.length);
        const step = Math.max(1, Math.floor(bytes.length / sampleSize));

        for (let i = 0; i < bytes.length; i += step) {
            hash = ((hash << 5) - hash) + bytes[i];
            hash = hash & hash;
        }

        // Convert to hex string
        return Math.abs(hash).toString(16).padStart(8, '0');
    }

    async handleFiles(files) {
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
                    additionalTags: [],
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
    }

    async handleArchive(archiveFile) {
        // Show loading indicator
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'bg-primary primary-text p-2 mb-2 text-xs';
        loadingDiv.textContent = `Extracting ${archiveFile.name}...`;
        this.uploadArea.parentNode.insertBefore(loadingDiv, this.uploadArea.nextSibling);

        try {
            const formData = new FormData();
            formData.append('file', archiveFile);

            const response = await fetch('/api/media/extract-archive', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`Failed to extract archive: ${response.statusText}`);
            }

            const result = await response.json();

            // result.files contains array of extracted file data
            for (const extractedFileData of result.files) {
                // Convert base64 to blob
                const binaryString = atob(extractedFileData.content);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                const blob = new Blob([bytes], { type: extractedFileData.mime_type });
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
                        additionalTags: [],
                        preview: null
                    };

                    this.uploadedFiles.push(fileData);
                    this.createPreview(fileData, this.uploadedFiles.length - 1);
                }
            }

            loadingDiv.textContent = `✓ Extracted ${result.files.length} files from ${archiveFile.name}`;
            setTimeout(() => loadingDiv.remove(), 3000);

        } catch (error) {
            console.error('Archive extraction error:', error);
            loadingDiv.className = 'bg-danger tag-text p-2 mb-2 text-xs';
            loadingDiv.textContent = `✗ Error extracting ${archiveFile.name}: ${error.message}`;
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

        if (isVideo) {
            const video = document.createElement('video');
            video.className = 'w-full h-24 object-cover';
            video.src = URL.createObjectURL(fileData.file);
            video.muted = true;
            thumbnailDiv.appendChild(video);
        } else {
            const img = document.createElement('img');
            img.className = 'w-full h-24 object-cover';
            img.src = URL.createObjectURL(fileData.file);
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
        tagsIndicator.textContent = this.getFullTags(fileData).join(' ') || 'No tags';
        thumbnailDiv.appendChild(tagsIndicator);

        thumbnailDiv.addEventListener('click', (e) => {
            const clickedIndex = parseInt(e.currentTarget.dataset.index);
            if (this.selectedFileIndex === clickedIndex) {
                const fileData = this.uploadedFiles[clickedIndex];
                if (fileData && fileData.file) {
                    const src = URL.createObjectURL(fileData.file);
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
    }

    updateFinalTagsPreview() {
        if (this.selectedFileIndex !== null) {
            const fileData = this.uploadedFiles[this.selectedFileIndex];
            const finalTags = this.getFullTags(fileData);
            document.getElementById('final-tags-preview').textContent = finalTags.join(' ') || 'None';
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
                tagsIndicator.textContent = fullTags.join(' ') || 'No tags';
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
        submitBtn.textContent = 'Uploading...';

        let successCount = 0;
        let failCount = 0;
        let duplicateCount = 0;

        for (let i = 0; i < this.uploadedFiles.length; i++) {
            const fileData = this.uploadedFiles[i];
            submitBtn.textContent = `Uploading ${i + 1}/${this.uploadedFiles.length}...`;

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

        // Show results
        let message = `Successfully uploaded ${successCount} file(s).`;
        if (duplicateCount > 0) {
            message += ` ${duplicateCount} duplicate(s) skipped.`;
        }
        if (failCount > 0) {
            message += ` ${failCount} failed.`;
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
        const formData = new FormData();

        // If scanned file, send path instead of file
        if (fileData.scannedPath) {
            formData.append('scanned_path', fileData.scannedPath);
        } else {
            formData.append('file', fileData.file);
        }

        formData.append('rating', fileData.rating);

        const fullTags = this.getFullTags(fileData);
        if (fullTags.length > 0) {
            formData.append('tags', fullTags.join(' '));
        }

        if (fileData.source) {
            formData.append('source', fileData.source);
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

    cancelAll() {
        // Clear all data
        this.uploadedFiles = [];
        this.selectedFileIndex = null;
        this.baseTags = [];
        this.baseRating = 'safe';
        this.baseSource = '';
        this.fileHashes.clear();

        // Clear UI
        document.getElementById('preview-thumbnails').innerHTML = '';
        const baseTagsInput = document.getElementById('base-tags');
        const individualTagsInput = document.getElementById('individual-tags');
        if (baseTagsInput) baseTagsInput.textContent = '';
        if (individualTagsInput) individualTagsInput.textContent = '';

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
            // Compute hash for duplicate detection
            const hash = await this.computeFileHash(file);

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
                additionalTags: [],
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

    isFileQueued(filePath) {
        if (this.uploadedFiles.some(f => f.scannedPath === filePath)) {
            return true;
        }

        const filename = filePath.split('/').pop().split('\\').pop();
        return this.uploadedFiles.some(f => f.file.name === filename);
    }
}

// Initialize uploader if upload area exists and expose globally
if (document.getElementById('upload-area')) {
    window.uploaderInstance = new Uploader();
}
