class Uploader {
    constructor() {
        this.uploadArea = document.getElementById('upload-area');
        this.fileInput = document.getElementById('file-input');
        this.uploadQueue = [];
        this.isUploading = false;
        
        if (this.uploadArea) {
            this.init();
        }
    }
    
    init() {
        this.setupDragAndDrop();
        this.setupFileInput();
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
    
    handleFiles(files) {
        files.forEach(file => {
            if (this.isValidFile(file)) {
                this.uploadQueue.push(file);
            }
        });
        
        if (!this.isUploading) {
            this.processQueue();
        }
    }
    
    isValidFile(file) {
        const validTypes = [
            'image/jpeg', 'image/png', 'image/gif', 'image/webp',
            'video/mp4', 'video/webm'
        ];
        return validTypes.includes(file.type);
    }
    
    async processQueue() {
        if (this.uploadQueue.length === 0) {
            this.isUploading = false;
            return;
        }
        
        this.isUploading = true;
        const file = this.uploadQueue.shift();
        
        await this.uploadFile(file);
        
        // Process next file
        this.processQueue();
    }
    
    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        
        // Get rating and tags from form if present
        const ratingInput = document.querySelector('input[name="upload-rating"]:checked');
        if (ratingInput) {
            formData.append('rating', ratingInput.value);
        }
        
        const tagsInput = document.getElementById('upload-tags');
        if (tagsInput && tagsInput.value) {
            const tags = tagsInput.value.split(/\s+/).filter(tag => tag.length > 0);
            formData.append('tags', JSON.stringify(tags));
        }
        
        try {
            const response = await fetch('/api/media/', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error('Upload failed');
            }
            
            const media = await response.json();
            this.onUploadSuccess(media);
            
        } catch (error) {
            console.error('Upload error:', error);
            this.onUploadError(file, error);
        }
    }
    
    onUploadSuccess(media) {
        // Show success message or update gallery
        console.log('Uploaded:', media);
        
        // Reload gallery if on gallery page
        if (window.gallery) {
            window.location.reload();
        }
    }
    
    onUploadError(file, error) {
        alert(`Failed to upload ${file.name}: ${error.message}`);
    }
}

// Initialize uploader if upload area exists
if (document.getElementById('upload-area')) {
    const uploader = new Uploader();
}
