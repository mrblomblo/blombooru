class SharedViewer extends MediaViewerBase {
    constructor(shareUuid) {
        super();
        this.shareUuid = shareUuid;
        this.ageVerificationModal = null;

        this.init();
    }

    async init() {
        this.initFullscreenViewer();
        this.initAgeVerificationModal();
        await this.loadSharedContent();
        this.setupAIMetadataToggle();
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

            if (response.ok) {
                if (data.type === 'media') {
                    this.currentMedia = data.data;
                    this.renderSharedMedia(this.currentMedia);

                    // Check if content is explicit and show age verification
                    if (this.currentMedia.rating === 'explicit') {
                        this.showAgeVerification();
                    }
                }
            } else {
                if (data.detail === "Shared content not found" || data.detail === "Not Found") {
                    this.showErrorMessage("The media you attempted to view has either been unshared, deleted, or never existed.");
                } else {
                    this.showErrorMessage();
                }
            }
        } catch (error) {
            console.error('Error loading shared content:', error);
            this.showErrorMessage();
        }
    }

    showErrorMessage(message = "This shared link is invalid or has been removed.") {
        const container = this.el('shared-content');
        container.innerHTML = `
            <div class="text-center py-16">
                <h2 class="text-lg font-bold mb-2">Content Not Found</h2>
                <p class="text-xs text-secondary">${message}</p>
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
                    <div id="ai-metadata-section" style="display: none;" class="surface border mb-4">
                        <button type="button" id="ai-metadata-toggle" class="w-full p-3 flex justify-between items-center text-left hover:text-primary transition-colors">
                            <h3 class="text-sm font-bold">AI Generation Data</h3>
                            <svg id="ai-metadata-chevron" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="transition-transform duration-200">
                                <polyline points="6 9 12 15 18 9"></polyline>
                            </svg>
                        </button>
                        <div id="ai-metadata-content" class="text-xs px-3 pb-3" style="display: none;"></div>
                    </div>
                    ` : ''}

                    <div class="surface p-3 border">
                        <h3 class="text-sm font-bold mb-3 pb-2 border-b">Actions</h3>
                        <div class="space-y-2">
                            <a id="download-btn" href="/api/shared/${this.shareUuid}/file" download="${media.filename}" 
                               class="flex items-center justify-center gap-2 w-full px-4 py-2 bg-primary primary-text transition-colors hover:bg-primary text-sm font-medium">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
                                    stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                    <polyline points="7 10 12 15 17 10"></polyline>
                                    <line x1="12" y1="15" x2="12" y2="3"></line>
                                </svg>
                                Download
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Setup error handlers for media elements
        this.setupMediaErrorHandlers(media);

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
                <video controls loop id="shared-media-video" style="max-width: 100%; max-height: 80vh; margin: 0 auto;">
                    <source src="/api/shared/${this.shareUuid}/file" type="${media.mime_type}">
                </video>
                <div id="video-error" style="display: none;" class="flex flex-col items-center justify-center py-8 text-secondary">
                    <img src="/static/images/no-thumbnail.png" alt="Media not found" class="w-32 h-32 mb-4 opacity-50">
                    <p class="text-sm">Failed to load video</p>
                </div>
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
            if (sharedImage && this.fullscreenViewer && sharedImage.src) {
                sharedImage.addEventListener('click', () => {
                    if (sharedImage.dataset.failed === 'true') return;
                    this.fullscreenViewer.open(`/api/shared/${this.shareUuid}/file`);
                });
            }
        }, 0);
    }

    setupMediaErrorHandlers(media) {
        if (media.file_type === 'video') {
            const video = this.el('shared-media-video');
            const errorDiv = this.el('video-error');

            if (video) {
                video.onerror = () => {
                    video.style.display = 'none';
                    if (errorDiv) errorDiv.style.display = 'flex';
                };
            }
        } else {
            const img = this.el('shared-media-image');

            if (img) {
                img.onerror = () => {
                    img.src = '/static/images/no-thumbnail.png';
                    img.alt = 'Media not found';
                    img.style.cursor = 'default';
                    img.dataset.failed = 'true';
                };
            }
        }
    }
}
