class MediaViewer extends MediaViewerBase {
    constructor(mediaId) {
        super();
        this.mediaId = mediaId;
        this.tagInputHelper = new TagInputHelper();
        this.validationTimeout = null;
        this.tooltipHelper = null;
        this.ratingSelect = null;

        this.init();
    }

    init() {
        this.initFullscreenViewer();
        this.initTooltipHelper();
        this.loadMedia();
        this.setupEventListeners();
    }

    initTooltipHelper() {
        this.tooltipHelper = new TooltipHelper({
            id: 'media-tooltip',
            delay: 300
        });
    }

    async loadMedia() {
        try {
            const res = await fetch(`/api/media/${this.mediaId}`);
            this.currentMedia = await res.json();
            this.renderMedia(this.currentMedia);
            this.renderInfo(this.currentMedia);
            this.renderTags(this.currentMedia, { clickable: true });

            // Hide AI metadata toggle by default
            const aiMetadataShareToggle = this.el('ai-metadata-share-toggle');
            if (aiMetadataShareToggle) {
                aiMetadataShareToggle.style.display = 'none';
            }

            await this.renderAIMetadata(this.currentMedia, {
                showControls: app.isAdminMode
            });

            if (app.isAdminMode) {
                this.setupAdminMode();
            }

            if (this.currentMedia.is_shared) {
                this.showShareLink(this.currentMedia.share_uuid, this.currentMedia.share_ai_metadata);
            }

            await this.loadRelatedMedia();
        } catch (e) {
            console.error('loadMedia error', e);
        }
    }

    setupAdminMode() {
        this.el('edit-tags-section').style.display = 'block';
        this.el('edit-source-section').style.display = 'block';
        this.el('admin-actions').style.display = 'block';
        this.el('unshare-btn').style.display = 'block';
        this.setupTagInput();

        // Set source input value
        const sourceInput = this.el('source-input');
        if (sourceInput) {
            sourceInput.value = this.currentMedia.source || '';
        }

        // Initialize tag autocomplete
        const tagsInput = this.el('tags-input');
        if (tagsInput) {
            new TagAutocomplete(tagsInput, {
                multipleValues: true,
                onSelect: () => {
                    setTimeout(() => this.validateAndStyleTags(), 100);
                }
            });

            // Set initial tags
            tagsInput.textContent = (this.currentMedia.tags || []).map(t => t.name).join(' ');
            setTimeout(() => this.validateAndStyleTags(), 100);
        }

        // Initialize custom select for rating
        const ratingSelectElement = this.el('rating-select');
        if (ratingSelectElement) {
            this.ratingSelect = new CustomSelect(ratingSelectElement);
            if (this.currentMedia.rating) {
                this.ratingSelect.setValue(this.currentMedia.rating);
            }
        }

        // Load albums
        this.loadAlbums();
        this.checkAlbumsExistence();
    }

    async checkAlbumsExistence() {
        try {
            const res = await fetch('/api/albums?limit=1');
            const data = await res.json();
            const section = this.el('albums-section');

            if (section) {
                if (data.total === 0) {
                    section.style.display = 'none';
                } else {
                    section.style.display = 'block';
                }
            }
        } catch (e) {
            console.error('Error checking albums existence:', e);
        }
    }

    renderMedia(media) {
        const container = this.el('media-container');
        if (media.file_type === 'video') {
            container.innerHTML = `<video controls loop><source src="/api/media/${media.id}/file" type="${media.mime_type}"></video>`;
        } else {
            container.innerHTML = `<img src="/api/media/${media.id}/file" alt="${media.filename}" id="main-media-image">`;

            setTimeout(() => {
                const mainImage = this.el('main-media-image');
                if (mainImage) {
                    mainImage.addEventListener('click', () => {
                        this.fullscreenViewer.open(`/api/media/${media.id}/file`);
                    });
                }
            }, 0);
        }

        this.el('download-btn').href = `/api/media/${media.id}/file`;
        this.el('download-btn').download = media.filename;
    }

    setupTagInput() {
        const tagsInput = this.el('tags-input');
        if (!tagsInput) return;

        this.tagInputHelper.setupTagInput(tagsInput, 'media-tags-input', {
            onValidate: () => { },
            validationCache: this.tagInputHelper.tagValidationCache,
            checkFunction: (tag) => this.tagInputHelper.checkTagExists(tag)
        });
    }

    async validateAndStyleTags() {
        const tagsInput = this.el('tags-input');
        if (!tagsInput) return;

        await this.tagInputHelper.validateAndStyleTags(tagsInput, {
            validationCache: this.tagInputHelper.tagValidationCache,
            checkFunction: (tag) => this.tagInputHelper.checkTagExists(tag)
        });
    }

    async getTagOrAlias(tagName) {
        if (!tagName || !tagName.trim()) return null;
        const normalized = tagName.toLowerCase().trim();

        try {
            const res = await fetch(`/api/tags/${encodeURIComponent(normalized)}`);
            if (!res.ok) return null;

            const data = await res.json();
            return data.aliased_to || data.name;
        } catch (e) {
            console.error('Error fetching tag:', e);
            return null;
        }
    }

    async loadRelatedMedia() {
        if (!this.currentMedia || !this.currentMedia.tags || !this.currentMedia.tags.length) {
            this.hideRelatedMedia();
            return;
        }

        let generalTags = this.currentMedia.tags.filter(t => t.category === 'general');

        if (!generalTags.length) {
            this.hideRelatedMedia();
            return;
        }

        // Shuffle tags
        for (let i = generalTags.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [generalTags[i], generalTags[j]] = [generalTags[j], generalTags[i]];
        }

        const numTags = Math.min(2, Math.max(1, Math.floor(Math.random() * generalTags.length) + 1));
        const tagQuery = generalTags.slice(0, numTags).map(t => t.name).join(' ');

        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(tagQuery)}&limit=12`);
            const data = await res.json();
            const currentMediaId = parseInt(this.mediaId);
            const items = (data.items || []).filter(i => i.id !== currentMediaId);

            if (items.length === 0) {
                this.hideRelatedMedia();
                return;
            }

            this.renderRelatedMedia(items);
        } catch (e) {
            console.error('related error', e);
            this.hideRelatedMedia();
        }
    }

    renderRelatedMedia(items) {
        const relatedMediaEl = this.el('related-media');
        const relatedMediaSection = relatedMediaEl.parentElement;
        const params = new URLSearchParams(window.location.search);
        const queryString = params.toString();
        relatedMediaSection.style.display = 'block';

        relatedMediaEl.innerHTML = '';

        items.forEach(media => {
            const item = this.createRelatedMediaItem(media, queryString);
            relatedMediaEl.appendChild(item);
        });
    }

    createRelatedMediaItem(media, queryString) {
        const item = document.createElement('div');
        item.className = `gallery-item ${media.file_type}`;
        item.dataset.id = media.id;
        item.dataset.rating = media.rating;

        const link = document.createElement('a');
        link.href = `/media/${media.id}${queryString ? '?' + queryString : ''}`;

        const img = document.createElement('img');
        img.src = `/api/media/${media.id}/thumbnail`;
        img.alt = media.filename;
        img.loading = 'lazy';
        img.className = 'transition-colors';
        img.onerror = () => {
            console.error('Failed to load thumbnail for media:', media.id);
            img.src = '/static/images/no-thumbnail.png';
        };

        link.appendChild(img);
        item.appendChild(link);

        if (media.is_shared) {
            const shareIcon = document.createElement('div');
            shareIcon.className = 'share-icon';
            shareIcon.textContent = 'SHARED';
            item.appendChild(shareIcon);
        }

        // Add tooltip functionality
        if (this.tooltipHelper && media.tags && media.tags.length > 0) {
            this.tooltipHelper.addToElement(item, media.tags);
        }

        return item;
    }

    hideRelatedMedia() {
        const relatedMediaEl = this.el('related-media');
        if (relatedMediaEl) {
            const relatedMediaSection = relatedMediaEl.parentElement;
            if (relatedMediaSection) {
                relatedMediaSection.style.display = 'none';
            }
        }
    }

    setupEventListeners() {
        this.el('edit-tags-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.saveTags();
        });

        this.el('save-source-btn')?.addEventListener('click', async () => {
            await this.saveSource();
        });

        const ratingSelectElement = this.el('rating-select');
        if (ratingSelectElement) {
            ratingSelectElement.addEventListener('change', async (e) => {
                await this.updateRating(e.detail.value);
            });
        }

        this.el('share-btn')?.addEventListener('click', async () => {
            await this.shareMedia();
        });

        this.el('copy-share-link-btn')?.addEventListener('click', () => {
            this.copyShareLink();
        });

        this.el('unshare-btn')?.addEventListener('click', async () => {
            await this.unshareMedia();
        });

        this.el('delete-btn')?.addEventListener('click', async () => {
            await this.deleteMedia();
        });

        this.el('share-ai-metadata-toggle')?.addEventListener('change', async (e) => {
            await this.updateShareSettings(e.target.checked);
        });

        this.el('append-ai-tags-btn')?.addEventListener('click', async () => {
            await this.appendAITags();
        });

        this.el('add-to-albums-btn')?.addEventListener('click', () => {
            this.addToAlbums();
        });
    }

    // Admin action methods
    async loadAlbums() {
        try {
            const res = await fetch(`/api/media/${this.mediaId}/albums`);
            if (!res.ok) throw new Error('Failed to load albums');

            const data = await res.json();
            this.renderAlbumsList(data.albums || []);
        } catch (e) {
            console.error('Error loading albums:', e);
            const container = this.el('current-albums');
            if (container) {
                container.innerHTML = '<p class="text-xs text-danger">Error loading albums</p>';
            }
        }
    }

    renderAlbumsList(albums) {
        const container = this.el('current-albums');
        if (!container) return;

        if (albums.length === 0) {
            container.innerHTML = '<p class="text-xs text-secondary">Not in any albums</p>';
            return;
        }

        container.innerHTML = albums.map(album => `
            <div class="flex justify-between items-center py-1 border-b last:border-0">
                <a href="/album/${album.id}" class="text-xs hover:text-primary truncate flex-1" title="${album.name}">${album.name}</a>
                <button class="remove-from-album-btn text-xs text-secondary hover:text-danger ml-2" data-album-id="${album.id}" title="Remove from album">&times;</button>
            </div>
        `).join('');

        // Add event listeners for remove buttons
        container.querySelectorAll('.remove-from-album-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const albumId = btn.dataset.albumId;
                this.removeFromAlbum(albumId);
            });
        });
    }

    async addToAlbums() {
        try {
            // Get current album IDs to pre-select
            const res = await fetch(`/api/media/${this.mediaId}/albums`);
            const data = await res.json();
            const currentAlbumIds = (data.albums || []).map(a => a.id);

            const result = await AlbumPicker.pick({
                title: 'Add to Albums',
                multiSelect: true,
                preSelected: currentAlbumIds
            });

            if (!result) return;
            const { ids: selectedIds } = result;

            // Determine added and removed albums
            const addedIds = selectedIds.filter(id => !currentAlbumIds.includes(id));
            const removedIds = currentAlbumIds.filter(id => !selectedIds.includes(id));

            if (addedIds.length === 0 && removedIds.length === 0) return;

            try {
                // Process additions
                for (const albumId of addedIds) {
                    await app.apiCall(`/api/albums/${albumId}/media`, {
                        method: 'POST',
                        body: JSON.stringify({ media_ids: [parseInt(this.mediaId)] })
                    });
                }

                // Process removals
                for (const albumId of removedIds) {
                    await app.apiCall(`/api/albums/${albumId}/media`, {
                        method: 'DELETE',
                        body: JSON.stringify({ media_ids: [parseInt(this.mediaId)] })
                    });
                }

                app.showNotification('Albums updated successfully', 'success');
                this.loadAlbums();
            } catch (error) {
                app.showNotification(error.message, 'error', 'Error updating albums');
            }
        } catch (error) {
            console.error('Error opening album picker:', error);
            app.showNotification('Error opening album picker', 'error');
        }
    }

    async removeFromAlbum(albumId) {
        try {
            await app.apiCall(`/api/albums/${albumId}/media`, {
                method: 'DELETE',
                body: JSON.stringify({ media_ids: [parseInt(this.mediaId)] })
            });

            app.showNotification('Removed from album', 'success');
            this.loadAlbums();
        } catch (error) {
            app.showNotification(error.message, 'error', 'Error removing from album');
        }
    }

    async saveTags() {
        const tagsInput = this.el('tags-input');
        const validTags = this.tagInputHelper.getValidTagsFromInput(tagsInput);

        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ tags: validTags })
            });
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', 'Error updating tags');
        }
    }

    async saveSource() {
        const sourceInput = this.el('source-input');
        const sourceValue = sourceInput.value.trim();

        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ source: sourceValue || null })
            });
            app.showNotification('Source updated successfully', 'success');
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', 'Error updating source');
        }
    }

    async updateRating(rating) {
        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ rating })
            });
        } catch (e) {
            app.showNotification(e.message, 'error', 'Error updating rating');
        }
    }

    async shareMedia() {
        try {
            const res = await app.apiCall(`/api/media/${this.mediaId}/share`, { method: 'POST' });
            this.showShareLink(res.share_url.split('/').pop(), res.share_ai_metadata);
        } catch (e) {
            app.showNotification(e.message, 'error', 'Error creating share link');
        }
    }

    copyShareLink() {
        this.el('share-link-input').select();
        document.execCommand('copy');
    }

    async unshareMedia() {
        const modal = new ModalHelper({
            id: 'unshare-modal',
            type: 'warning',
            title: 'Unshare Media',
            message: 'Are you sure you want to unshare this media? The share link will stop working.',
            confirmText: 'Yes, Unshare',
            cancelText: 'Cancel',
            confirmId: 'unshare-confirm-yes',
            cancelId: 'unshare-confirm-no',
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/media/${this.mediaId}/share`, { method: 'DELETE' });
                    this.el('share-link-section').style.display = 'none';
                    this.el('share-btn').style.display = 'block';
                    app.showNotification('Media successfully unshared', 'success');
                } catch (e) {
                    app.showNotification(e.message, 'error', 'Error removing share');
                }
            }
        });
        modal.show();
    }

    async deleteMedia() {
        const modal = new ModalHelper({
            id: 'delete-modal',
            type: 'danger',
            title: 'Delete Media',
            message: 'Are you sure you want to delete this media? This action cannot be undone.',
            confirmText: 'Yes, Delete',
            cancelText: 'Cancel',
            confirmId: 'delete-confirm-yes',
            cancelId: 'delete-confirm-no',
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/media/${this.mediaId}`, { method: 'DELETE' });
                    window.location.href = '/';
                } catch (e) {
                    app.showNotification(e.message, 'error', 'Error deleting media');
                }
            }
        });
        modal.show();
    }

    async updateShareSettings(shareAIMetadata) {
        try {
            await app.apiCall(`/api/media/${this.mediaId}/share-settings?share_ai_metadata=${shareAIMetadata}`, {
                method: 'PATCH'
            });
        } catch (err) {
            app.showNotification(err.message, 'error', 'Error updating share settings');
            const toggle = this.el('share-ai-metadata-toggle');
            if (toggle) toggle.checked = !toggle.checked;
        }
    }

    async appendAITags() {
        try {
            const res = await fetch(`/api/media/${this.mediaId}/metadata`);
            if (!res.ok) {
                app.showNotification('Could not load AI metadata', 'error');
                return;
            }

            const metadata = await res.json();
            const aiPrompt = this.extractAIPrompt(metadata);

            if (!aiPrompt || typeof aiPrompt !== 'string') {
                app.showNotification('No AI prompt found in metadata', 'error');
                return;
            }

            const promptTags = aiPrompt
                .split(',')
                .map(tag => tag.trim().replace(/\s+/g, '_'))
                .filter(tag => tag.length > 0);

            const validTags = [];
            for (const tag of promptTags) {
                const validTag = await this.getTagOrAlias(tag);
                if (validTag) {
                    validTags.push(validTag);
                }
            }

            if (validTags.length === 0) {
                app.showNotification('No valid tags found in AI prompt', 'error');
                return;
            }

            const tagsInput = this.el('tags-input');
            const currentText = this.tagInputHelper.getPlainTextFromDiv(tagsInput).trim();
            const currentTags = currentText ? currentText.split(/\s+/) : [];

            const existingTagsSet = new Set(currentTags.map(t => t.toLowerCase()));
            const newTags = validTags.filter(tag => !existingTagsSet.has(tag.toLowerCase()));

            if (newTags.length === 0) {
                app.showNotification('All AI tags are already present', 'info');
                return;
            }

            const allTags = [...currentTags, ...newTags];
            tagsInput.textContent = allTags.join(' ');

            await this.validateAndStyleTags();
            app.showNotification(`Appended ${newTags.length} tag(s) from AI prompt`, 'success');

        } catch (e) {
            console.error('Error appending AI tags:', e);
            app.showNotification('Error processing AI tags: ' + e.message, 'error');
        }
    }

    extractAIPrompt(metadata) {
        // Use the same extraction logic as renderAIMetadata
        const aiData = this.extractAIData(metadata);

        if (!aiData) {
            return null;
        }

        // Extract the positive prompt from the parsed AI data
        // Check various possible keys for the prompt
        const promptLocations = [
            aiData.prompt,
            aiData.Prompt,
            aiData.positive_prompt,
            aiData.positive,
            aiData.sui_image_params?.prompt
        ];

        for (const location of promptLocations) {
            if (location && typeof location === 'string') {
                return location;
            }
        }

        // Fallback: if aiData has a prompt nested somewhere
        for (const [key, value] of Object.entries(aiData)) {
            if (key.toLowerCase().includes('prompt') &&
                !key.toLowerCase().includes('negative') &&
                typeof value === 'string') {
                return value;
            }
        }

        return null;
    }

    showShareLink(uuid, shareAIMetadata) {
        this.el('share-link-input').value = `${window.location.origin}/shared/${uuid}`;
        this.el('share-link-section').style.display = 'block';
        this.el('share-btn').style.display = 'none';

        const aiMetadataToggle = this.el('share-ai-metadata-toggle');
        if (aiMetadataToggle) {
            aiMetadataToggle.checked = shareAIMetadata || false;
        }
    }

    // Cleanup method
    destroy() {
        if (this.tooltipHelper) {
            this.tooltipHelper.destroy();
        }
        if (this.tagInputHelper) {
            this.tagInputHelper.destroy();
        }
    }
}
