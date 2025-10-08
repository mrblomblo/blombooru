class Uploader {
    constructor() {
        this.uploadArea = document.getElementById('upload-area');
        this.fileInput = document.getElementById('file-input');
        this.uploadedFiles = [];
        this.selectedFileIndex = null;
        this.baseRating = 'safe';
        this.baseTags = [];
        
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
        controlsDiv.className = 'bg-[#0f172a] p-4 border border-[#334155] mb-4';
        controlsDiv.style.display = 'none';
        controlsDiv.innerHTML = `
            <h3 class="text-sm font-bold mb-3">Base Settings (applies to all media)</h3>
            
            <div class="mb-4">
                <label class="block text-xs font-bold mb-2">Base Rating</label>
                <select id="base-rating" class="w-full px-3 py-2 bg-[#0f172a] border border-[#334155] text-xs focus:outline-none focus:border-blue-500">
                    <option value="safe">Safe</option>
                    <option value="questionable">Questionable</option>
                    <option value="explicit">Explicit</option>
                </select>
            </div>
            
            <div class="mb-4">
                <label class="block text-xs font-bold mb-2">Base Tags (prefixed to all media)</label>
                <input type="text" id="base-tags" class="tag-input w-full px-3 py-2 bg-[#0f172a] border border-[#334155] text-xs focus:outline-none focus:border-blue-500" placeholder="tag1 tag2 tag3">
            </div>
        `;
        
        this.uploadArea.parentNode.insertBefore(controlsDiv, this.uploadArea.nextSibling);
        
        // Setup event listeners
        document.getElementById('base-rating').addEventListener('change', (e) => {
            this.baseRating = e.target.value;
            this.updateAllMediaRatings();
        });
        
        document.getElementById('base-tags').addEventListener('input', (e) => {
            this.baseTags = e.target.value.split(/\s+/).filter(tag => tag.length > 0);
            this.updateAllMediaTags();
        });
        
        // Initialize tag autocomplete if available
        if (typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(document.getElementById('base-tags'), {
                multipleValues: true
            });
        }
    }
    
    createPreviewGrid() {
        const gridDiv = document.createElement('div');
        gridDiv.id = 'preview-grid';
        gridDiv.style.display = 'none';
        gridDiv.innerHTML = `
            <div class="bg-[#0f172a] p-4 border border-[#334155] mb-4">
                <h3 class="text-sm font-bold mb-3">Uploaded Media (click to edit individual tags/rating)</h3>
                <div id="preview-thumbnails" class="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-2 mb-4"></div>
                
                <div id="individual-controls" style="display: none;" class="border-t border-[#334155] pt-4">
                    <h4 class="text-xs font-bold mb-3">Editing: <span id="current-filename"></span></h4>
                    
                    <div class="mb-3">
                        <label class="block text-xs font-bold mb-2">Individual Rating</label>
                        <select id="individual-rating" class="w-full px-3 py-2 bg-[#0f172a] border border-[#334155] text-xs focus:outline-none focus:border-blue-500">
                            <option value="safe">Safe</option>
                            <option value="questionable">Questionable</option>
                            <option value="explicit">Explicit</option>
                        </select>
                    </div>
                    
                    <div class="mb-3">
                        <label class="block text-xs font-bold mb-2">Additional Tags (base tags are prefixed automatically)</label>
                        <input type="text" id="individual-tags" class="tag-input w-full px-3 py-2 bg-[#0f172a] border border-[#334155] text-xs focus:outline-none focus:border-blue-500" placeholder="additional_tag1 additional_tag2">
                    </div>
                    
                    <div class="text-xs text-[#94a3b8] mb-2">
                        Final tags: <span id="final-tags-preview" class="text-white"></span>
                    </div>
                    
                    <button id="remove-media-btn" class="px-3 py-2 bg-red-600 hover:bg-red-700 text-white text-xs">Remove This Media</button>
                </div>
            </div>
        `;
        
        document.getElementById('base-controls').parentNode.insertBefore(gridDiv, document.getElementById('base-controls').nextSibling);
        
        // Setup individual controls
        document.getElementById('individual-rating').addEventListener('change', (e) => {
            if (this.selectedFileIndex !== null) {
                this.uploadedFiles[this.selectedFileIndex].rating = e.target.value;
                this.updateThumbnailIndicator(this.selectedFileIndex);
            }
        });
        
        document.getElementById('individual-tags').addEventListener('input', (e) => {
            if (this.selectedFileIndex !== null) {
                this.uploadedFiles[this.selectedFileIndex].additionalTags = 
                    e.target.value.split(/\s+/).filter(tag => tag.length > 0);
                this.updateFinalTagsPreview();
                this.updateThumbnailIndicator(this.selectedFileIndex);
            }
        });
        
        document.getElementById('remove-media-btn').addEventListener('click', () => {
            if (this.selectedFileIndex !== null) {
                this.removeMedia(this.selectedFileIndex);
            }
        });
        
        // Initialize tag autocomplete for individual tags
        if (typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(document.getElementById('individual-tags'), {
                multipleValues: true
            });
        }
    }
    
    createSubmitControls() {
        const submitDiv = document.createElement('div');
        submitDiv.id = 'submit-controls';
        submitDiv.style.display = 'none';
        submitDiv.className = 'flex gap-2';
        submitDiv.innerHTML = `
            <button id="submit-all-btn" class="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold">Submit All Media</button>
            <button id="cancel-all-btn" class="flex-1 px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white text-xs">Cancel & Clear All</button>
        `;
        
        document.getElementById('preview-grid').parentNode.insertBefore(submitDiv, document.getElementById('preview-grid').nextSibling);
        
        document.getElementById('submit-all-btn').addEventListener('click', () => {
            this.submitAll();
        });
        
        document.getElementById('cancel-all-btn').addEventListener('click', () => {
            this.cancelAll();
        });
    }
    
    handleFiles(files) {
        files.forEach(file => {
            if (this.isValidFile(file)) {
                const fileData = {
                    file: file,
                    rating: this.baseRating,
                    additionalTags: [],
                    preview: null
                };
                
                this.uploadedFiles.push(fileData);
                this.createPreview(fileData, this.uploadedFiles.length - 1);
            }
        });
        
        if (this.uploadedFiles.length > 0) {
            document.getElementById('base-controls').style.display = 'block';
            document.getElementById('preview-grid').style.display = 'block';
            document.getElementById('submit-controls').style.display = 'flex';
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
        thumbnailDiv.className = 'relative cursor-pointer border-2 border-[#334155] hover:border-blue-500 transition-colors';
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
        indicator.className = 'absolute top-0 right-0 bg-black bg-opacity-75 px-1 text-xs';
        indicator.innerHTML = `<span class="rating-indicator">${fileData.rating[0].toUpperCase()}</span>`;
        thumbnailDiv.appendChild(indicator);
        
        // Add tags indicator
        const tagsIndicator = document.createElement('div');
        tagsIndicator.className = 'absolute bottom-0 left-0 right-0 bg-black bg-opacity-75 px-1 text-xs truncate tags-indicator';
        tagsIndicator.textContent = this.getFullTags(fileData).join(' ') || 'No tags';
        thumbnailDiv.appendChild(tagsIndicator);
        
        thumbnailDiv.addEventListener('click', () => {
            this.selectMedia(index);
        });
        
        container.appendChild(thumbnailDiv);
    }
    
    selectMedia(index) {
        this.selectedFileIndex = index;
        const fileData = this.uploadedFiles[index];
        
        // Update UI
        document.querySelectorAll('#preview-thumbnails > div').forEach((div, i) => {
            if (i === index) {
                div.classList.add('border-blue-500');
                div.classList.remove('border-[#334155]');
            } else {
                div.classList.remove('border-blue-500');
                div.classList.add('border-[#334155]');
            }
        });
        
        // Show individual controls
        document.getElementById('individual-controls').style.display = 'block';
        document.getElementById('current-filename').textContent = fileData.file.name;
        document.getElementById('individual-rating').value = fileData.rating;
        document.getElementById('individual-tags').value = fileData.additionalTags.join(' ');
        
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
        
        if (this.selectedFileIndex !== null) {
            document.getElementById('individual-rating').value = this.baseRating;
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
        
        // Clear selection
        this.selectedFileIndex = null;
        document.getElementById('individual-controls').style.display = 'none';
        
        // Hide everything if no files left
        if (this.uploadedFiles.length === 0) {
            this.cancelAll();
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
        
        for (let i = 0; i < this.uploadedFiles.length; i++) {
            const fileData = this.uploadedFiles[i];
            submitBtn.textContent = `Uploading ${i + 1}/${this.uploadedFiles.length}...`;
            
            try {
                await this.uploadFile(fileData);
                successCount++;
            } catch (error) {
                console.error('Upload error:', error);
                failCount++;
            }
        }
        
        // Show results
        if (failCount === 0) {
            alert(`Successfully uploaded ${successCount} file(s)!`);
        } else {
            alert(`Uploaded ${successCount} file(s). Failed: ${failCount}`);
        }
        
        // Reset
        this.cancelAll();
        
        // Reload gallery if on gallery page
        if (window.gallery) {
            window.location.reload();
        }
    }
    
    async uploadFile(fileData) {
        const formData = new FormData();
        formData.append('file', fileData.file);
        formData.append('rating', fileData.rating);
        
        const fullTags = this.getFullTags(fileData);
        if (fullTags.length > 0) {
            formData.append('tags', JSON.stringify(fullTags));
        }
        
        const response = await fetch('/api/media/', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`Upload failed: ${response.statusText}`);
        }
        
        return await response.json();
    }
    
    cancelAll() {
        // Clear all data
        this.uploadedFiles = [];
        this.selectedFileIndex = null;
        this.baseTags = [];
        this.baseRating = 'safe';
        
        // Clear UI
        document.getElementById('preview-thumbnails').innerHTML = '';
        document.getElementById('base-tags').value = '';
        document.getElementById('base-rating').value = 'safe';
        document.getElementById('individual-controls').style.display = 'none';
        
        // Hide sections
        document.getElementById('base-controls').style.display = 'none';
        document.getElementById('preview-grid').style.display = 'none';
        document.getElementById('submit-controls').style.display = 'none';
        
        // Reset file input
        this.fileInput.value = '';
    }
}

// Initialize uploader if upload area exists
if (document.getElementById('upload-area')) {
    const uploader = new Uploader();
}
