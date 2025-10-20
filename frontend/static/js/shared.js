class SharedViewer extends MediaViewerBase {
    constructor(shareUuid) {
        super();
        this.shareUuid = shareUuid;
        this.ageVerificationModal = null;
        
        this.init();
    }

    init() {
        this.initFullscreenViewer();
        this.initAgeVerificationModal();
        this.loadSharedContent();
    }

    initAgeVerificationModal() {
        this.ageVerificationModal = new ModalHelper({
            id: 'age-verification-modal',
            type: 'danger',
            title: 'Explicit Content Warning',
            message: 'This media contains explicit content.<br>By clicking "Yes, I am 18+", you confirm that you are over the age of 18 and consent to viewing adult content.',
            confirmText: 'Yes, I am 18+',
            cancelText: 'No, I am not 18',
            confirmId: 'age-confirm-yes',
            cancelId: 'age-confirm-no',
            blurTarget: '.lg\\:col-span-3 > div',
            onCancel: () => this.denyAge(),
            closeOnOutsideClick: false,
            closeOnEscape: false
        });
    }

    async loadSharedContent() {
        try {
            const response = await fetch(`/api/shared/${this.shareUuid}`);
            const data = await response.json();
            
            if (data.type === 'media') {
                this.currentMedia = data.data;
                this.renderSharedMedia(this.currentMedia);
                
                // Check if content is explicit and show age verification
                if (this.currentMedia.rating === 'explicit') {
                    this.showAgeVerification();
                }
            }
        } catch (error) {
            console.error('Error loading shared content:', error);
            this.showErrorMessage();
        }
    }

    showErrorMessage() {
        const container = this.el('shared-content');
        container.innerHTML = `
            <div class="text-center py-16">
                <h2 class="text-lg font-bold mb-2">Content Not Found</h2>
                <p class="text-xs text-secondary">This shared link is invalid or has been removed.</p>
            </div>
        `;
    }

    showAgeVerification() {
        if (this.ageVerificationModal) {
            this.ageVerificationModal.show();
        }
    }

    denyAge() {
        window.location.href = 'about:blank';
    }

    renderSharedMedia(media) {
        const container = this.el('shared-content');
        const showAIMetadata = media.share_ai_metadata === true;

        container.innerHTML = `
            <div class="grid grid-cols-1 lg:grid-cols-4 gap-4">
                <div class="lg:col-span-3">
                    <div class="surface p-4 border text-center">
                        ${this.getMediaHTML(media)}
                    </div>
                </div>

                <div class="lg:col-span-1">
                    <div class="surface p-3 border mb-4">
                        <h3 class="text-sm font-bold mb-3 pb-2 border-b">Information</h3>
                        <div id="media-info-content" class="text-xs"></div>
                    </div>

                    <div class="surface p-3 border mb-4">
                        <h3 class="text-sm font-bold mb-3 pb-2 border-b">Tags</h3>
                        <div id="tags-container"></div>
                    </div>

                    ${showAIMetadata ? `
                    <div id="ai-metadata-section" class="surface p-3 border mb-4">
                        <h3 class="text-sm font-bold mb-3 pb-2 border-b">AI Generation Data</h3>
                        <div id="ai-metadata-content" class="text-xs"></div>
                    </div>
                    ` : ''}

                    <div class="surface p-3 border">
                        <h3 class="text-sm font-bold mb-3 pb-2 border-b">Actions</h3>
                        <div class="space-y-2">
                            <a id="download-btn" href="/api/shared/${this.shareUuid}/file" download="${media.filename}" 
                               class="block w-full px-3 py-2 surface-light transition-colors hover:surface-light text text-center text-xs">
                                Download
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Render the data into the containers
        this.renderInfo(media, { isShared: true });
        this.renderTags(media, { clickable: false });
        
        // Only render AI metadata if sharing is enabled
        if (showAIMetadata) {
            this.renderAIMetadata(media, { showControls: false, isShared: true });
        }
        
        // Add click listener for fullscreen (only for images/GIFs)
        if (media.file_type !== 'video') {
            this.setupImageClickHandler();
        }
    }

    getMediaHTML(media) {
        if (media.file_type === 'video') {
            return `
                <video controls loop style="max-width: 100%; max-height: 80vh; margin: 0 auto;">
                    <source src="/api/shared/${this.shareUuid}/file" type="${media.mime_type}">
                </video>
            `;
        } else {
            return `
                <img src="/api/shared/${this.shareUuid}/file" alt="${media.filename}" 
                     id="shared-media-image" 
                     style="max-width: 100%; max-height: 80vh; margin: 0 auto; cursor: pointer;">
            `;
        }
    }

    setupImageClickHandler() {
        setTimeout(() => {
            const sharedImage = this.el('shared-media-image');
            if (sharedImage && this.fullscreenViewer) {
                sharedImage.addEventListener('click', () => {
                    this.fullscreenViewer.open(`/api/shared/${this.shareUuid}/file`);
                });
            }
        }, 0);
    }
}
