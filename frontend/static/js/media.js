class MediaViewer extends MediaViewerBase {
    constructor(mediaId, externalShareUrl = null) {
        super();
        this.mediaId = mediaId;
        this.externalShareUrl = externalShareUrl;
        this.tagInputHelper = new TagInputHelper();
        this.validationTimeout = null;
        this.tooltipHelper = null;
        this.ratingSelect = null;

        // WD Tagger settings
        this.wdTaggerSettings = {
            generalThreshold: 0.35,
            characterThreshold: 0.85,
            modelName: 'wd-eva02-large-tagger-v3'
        };

        // Relation Manager state
        this.relationModal = {
            isOpen: false,
            selectedItems: new Set(),
            currentPage: 1,
            totalPages: 1,
            isSearchMode: false,
            searchQuery: '',
            isLoading: false,
            childIds: new Set() // Track current children for removal
        };

        this.init();
    }

    init() {
        this.initFullscreenViewer();
        this.initTooltipHelper();
        this.loadMedia();
        this.setupAIMetadataToggle();
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

            this.renderHierarchy(this.currentMedia.hierarchy);
            await this.loadRelatedMedia();
        } catch (e) {
            console.error('loadMedia error', e);
        }
    }

    setupAdminMode() {
        this.el('edit-tags-section').style.display = 'block';
        this.el('edit-source-section').style.display = 'block';
        this.el('admin-actions').style.display = 'flex';
        this.setupTagInput();
        this.setupEditTagsToggle();

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
            const categoryOrder = ['artist', 'character', 'copyright', 'general', 'meta'];
            const sortedTags = [...(this.currentMedia.tags || [])].sort((a, b) => {
                const catA = categoryOrder.indexOf(a.category);
                const catB = categoryOrder.indexOf(b.category);
                const orderA = catA === -1 ? 99 : catA;
                const orderB = catB === -1 ? 99 : catB;
                if (orderA !== orderB) return orderA - orderB;
                return a.name.localeCompare(b.name);
            });
            tagsInput.textContent = sortedTags.map(t => t.name).join(' ');
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

        // Show predict button (always available for admin)
        const predictBtn = this.el('predict-wd-tags-btn');
        if (predictBtn) {
            predictBtn.style.display = 'block';
        }

        // Load albums
        this.checkAlbumsExistence();

        // Setup relation manager
        this.setupRelationManager();
    }

    setupEditTagsToggle() {
        const toggle = this.el('edit-tags-toggle');
        const content = this.el('edit-tags-content');

        if (!toggle || !content) return;

        // Ensure initial state
        content.style.display = 'none';

        // Remove any existing listeners by cloning
        const newToggle = toggle.cloneNode(true);
        toggle.parentNode.replaceChild(newToggle, toggle);

        newToggle.addEventListener('click', () => {
            const isHidden = content.style.display === 'none';
            content.style.display = isHidden ? 'block' : 'none';

            const activeChevron = newToggle.querySelector('#edit-tags-chevron');
            if (activeChevron) {
                activeChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });
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
            const video = document.createElement('video');
            video.controls = true;
            video.loop = true;
            video.style.cursor = 'pointer';

            const source = document.createElement('source');
            source.src = `/api/media/${media.id}/file`;
            source.type = media.mime_type;

            video.appendChild(source);

            video.onerror = () => {
                container.innerHTML = `
                    <div class="flex flex-col items-center justify-center py-8 text-secondary">
                        <img src="/static/images/no-thumbnail.png" alt="${window.i18n.t('media.errors.media_not_found')}" class="w-32 h-32 mb-4 opacity-50">
                        <p class="text-sm">${window.i18n.t('media.errors.failed_to_load_video')}</p>
                    </div>
                `;
            };

            // Add click handler for fullscreen (avoid controls area)
            video.addEventListener('click', (e) => {
                // Only open fullscreen if not clicking on controls
                const rect = video.getBoundingClientRect();
                const clickY = e.clientY - rect.top;
                const controlsHeight = 50; // Approximate height of video controls

                if (clickY < rect.height - controlsHeight) {
                    this.fullscreenViewer.open(`/api/media/${media.id}/file`, true);
                }
            });

            container.innerHTML = '';
            container.appendChild(video);
        } else {
            const img = document.createElement('img');
            img.src = `/api/media/${media.id}/file`;
            img.alt = media.filename;
            img.id = 'main-media-image';
            img.style.cursor = 'pointer';

            img.onerror = () => {
                img.src = '/static/images/no-thumbnail.png';
                img.alt = window.i18n.t('media.errors.media_not_found');
                img.style.cursor = 'default';
                img.onclick = null;
            };

            img.onload = () => {
                if (!img.src.includes('no-thumbnail.png')) {
                    img.addEventListener('click', () => {
                        this.fullscreenViewer.open(`/api/media/${media.id}/file`, false);
                    });
                }
            };

            container.innerHTML = '';
            container.appendChild(img);
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

        const generalTags = this.currentMedia.tags.filter(t => t.category === 'general');

        if (!generalTags.length) {
            this.hideRelatedMedia();
            return;
        }

        const currentMediaId = parseInt(this.mediaId);
        const minTags = Math.min(3, generalTags.length);

        const searchOnce = async (numTags) => {
            const shuffled = [...generalTags];
            for (let i = shuffled.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
            }

            const actualNumTags = Math.min(numTags, shuffled.length);
            const tagQuery = shuffled.slice(0, actualNumTags).map(t => t.name).join(' ');

            const res = await fetch(`/api/search?q=${encodeURIComponent(tagQuery)}&limit=12`, {
                credentials: 'include'
            });
            const data = await res.json();
            return (data.items || []).filter(i => i.id !== currentMediaId);
        };

        try {
            const maxStartingTags = Math.min(6, generalTags.length);

            for (let numTags = maxStartingTags; numTags >= minTags; numTags--) {
                let bestItems = [];

                for (let i = 0; i < 3; i++) {
                    const items = await searchOnce(numTags);
                    if (items.length > bestItems.length) {
                        bestItems = items;
                    }
                    if (bestItems.length >= 3) break;
                }

                if (bestItems.length >= 1) {
                    this.renderRelatedMedia(bestItems);
                    return;
                }

                for (let i = 0; i < 3; i++) {
                    const items = await searchOnce(numTags);
                    if (items.length > 0) {
                        this.renderRelatedMedia(items);
                        return;
                    }
                }
            }

            this.hideRelatedMedia();
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
        if (media.parent_id) item.classList.add('child-item');
        if (media.has_children) item.classList.add('parent-item');
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
            console.error(window.i18n.t('media.errors.failed_load_thumbnail', { id: media.id }));
            img.src = '/static/images/no-thumbnail.png';
        };

        link.appendChild(img);
        item.appendChild(link);

        if (media.is_shared) {
            const shareIcon = document.createElement('div');
            shareIcon.className = 'share-icon';
            shareIcon.textContent = window.i18n.t('media.relations.shared');
            item.appendChild(shareIcon);
        }

        // Add tooltip functionality
        if (this.tooltipHelper && media.tags && media.tags.length > 0) {
            const isPrimaryTouch = window.matchMedia('(pointer: coarse)').matches;

            if (!isPrimaryTouch) {
                this.tooltipHelper.addToElement(item, media.tags);
            }
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
            const btn = this.el('share-btn');
            if (btn.classList.contains('unshare-mode')) {
                await this.unshareMedia();
            } else {
                await this.shareMedia();
            }
        });

        this.el('copy-share-link-btn')?.addEventListener('click', () => {
            this.copyShareLink();
        });

        this.el('share-link-input')?.addEventListener('click', function () {
            if (this.selectionStart === this.selectionEnd) {
                this.select();
            }
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

        this.el('predict-wd-tags-btn')?.addEventListener('click', async () => {
            await this.predictWDTags();
        });

        this.el('add-to-albums-btn')?.addEventListener('click', () => {
            this.addToAlbums();
        });
    }

    // ==================== WD Tagger Methods ====================

    async predictWDTags() {
        const btn = this.el('predict-wd-tags-btn');
        if (!btn) return;

        try {
            // Check model status first
            const statusRes = await fetch(`/api/ai-tagger/model-status/${this.wdTaggerSettings.modelName}`);
            if (!statusRes.ok) {
                throw new Error('Failed to check model status');
            }

            const status = await statusRes.json();

            if (!status.is_downloaded && !status.is_loaded) {
                // Show download confirmation modal
                const modal = new ModalHelper({
                    id: 'wd-download-modal',
                    type: 'info',
                    title: window.i18n.t('modal.download_model.title'),
                    message: window.i18n.t('modal.download_model.message', {
                        modelName: this.wdTaggerSettings.modelName,
                        size: status.download_size_mb || 850
                    }),
                    confirmText: window.i18n.t('modal.download_model.confirm'),
                    cancelText: window.i18n.t('modal.buttons.cancel'),
                    showIcon: true,
                    onConfirm: async () => {
                        await this.downloadModelAndPredict(btn);
                    }
                });
                modal.show();
                return;
            }

            // Model is ready, perform prediction
            await this.performWDPrediction(btn);

        } catch (e) {
            console.error('Error checking model status:', e);
            app.showNotification(window.i18n.t('notifications.media.error_checking_ai_model', { error: e.message }), 'error');
        }
    }

    async downloadModelAndPredict(btn) {
        this.setButtonState(btn, window.i18n.t('media.progress.downloading'), true);

        try {
            const res = await fetch(`/api/ai-tagger/download/${this.wdTaggerSettings.modelName}`, {
                method: 'POST'
            });

            if (!res.ok) {
                const error = await res.json().catch(() => ({}));
                throw new Error(error.detail || 'Download failed');
            }

            // Download complete, now predict
            await this.performWDPrediction(btn);

        } catch (e) {
            console.error('Error downloading model:', e);
            app.showNotification(window.i18n.t('notifications.media.error_downloading_ai_model', { error: e.message }), 'error');
            this.setButtonState(btn, window.i18n.t('media.tags.predict_tags'), false);
        }
    }

    async performWDPrediction(btn) {
        this.setButtonState(btn, window.i18n.t('media.progress.predicting'), true);

        try {
            const res = await fetch(`/api/ai-tagger/predict/${this.mediaId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    general_threshold: this.wdTaggerSettings.generalThreshold,
                    character_threshold: this.wdTaggerSettings.characterThreshold,
                    model_name: this.wdTaggerSettings.modelName
                })
            });

            if (!res.ok) {
                const error = await res.json().catch(() => ({}));
                throw new Error(error.detail || 'Prediction failed');
            }

            const result = await res.json();

            // Get current tags from input
            const tagsInput = this.el('tags-input');
            const currentText = this.tagInputHelper.getPlainTextFromDiv(tagsInput).trim();
            const currentTags = currentText ? currentText.split(/\s+/) : [];
            const existingSet = new Set(currentTags.map(t => t.toLowerCase()));

            // Process predicted tags
            const predictedTags = result.tags
                .map(t => t.name.replace(/ /g, '_'))
                .filter(t => !existingSet.has(t.toLowerCase()));

            if (predictedTags.length === 0) {
                app.showNotification(window.i18n.t('notifications.media.no_new_tags_predicted'), 'info');
                this.setButtonState(btn, window.i18n.t('media.tags.predict_tags'), false);
                return;
            }

            // Validate predicted tags against database in batch
            this.setButtonState(btn, window.i18n.t('media.progress.validating'), true);

            const validTags = [];
            try {
                const results = await this.tagInputHelper.checkTagsBatch(predictedTags);
                for (const tag of predictedTags) {
                    const tagObj = results[tag.toLowerCase()];
                    if (tagObj && !existingSet.has(tagObj.name.toLowerCase())) {
                        validTags.push(tagObj.name);
                        existingSet.add(tagObj.name.toLowerCase());
                    }
                }
            } catch (e) {
                console.error('Error validating tags in batch:', e);
                // Fallback
                for (const tag of predictedTags) {
                    const validTag = await this.getTagOrAlias(tag);
                    if (validTag && !existingSet.has(validTag.toLowerCase())) {
                        validTags.push(validTag);
                        existingSet.add(validTag.toLowerCase());
                    }
                }
            }

            if (validTags.length === 0) {
                app.showNotification(window.i18n.t('notifications.media.no_valid_tags_predictions'), 'info');
            } else {
                const allTags = [...currentTags, ...validTags];
                tagsInput.textContent = allTags.join(' ');
                await this.validateAndStyleTags();
                app.showNotification(window.i18n.t('notifications.media.tags_added', { count: validTags.length }), 'success');
            }

        } catch (e) {
            console.error('Error predicting tags:', e);
            app.showNotification(window.i18n.t('notifications.media.error_predicting_tags', { error: e.message }), 'error');
        } finally {
            this.setButtonState(btn, window.i18n.t('media.tags.predict_tags'), false);
        }
    }

    setButtonState(btn, text, disabled) {
        if (!btn) return;
        const textSpan = btn.querySelector('.btn-text');
        if (textSpan) {
            textSpan.textContent = text;
        } else {
            btn.textContent = text;
        }
        btn.disabled = disabled;
        btn.style.opacity = disabled ? '0.7' : '1';
    }

    // ==================== Album Methods ====================


    async addToAlbums() {
        try {
            // Get current album IDs to pre-select
            const res = await fetch(`/api/media/${this.mediaId}/albums`);
            const data = await res.json();
            const currentAlbumIds = (data.albums || []).map(a => a.id);

            const result = await AlbumPicker.pick({
                title: window.i18n.t('media.albums.add_to_albums_title'),
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

                app.showNotification(window.i18n.t('notifications.media.albums_updated'), 'success');
            } catch (error) {
                app.showNotification(error.message, 'error', window.i18n.t('notifications.media.error_updating_albums'));
            }
        } catch (error) {
            console.error('Error opening album picker:', error);
            app.showNotification(window.i18n.t('notifications.media.error_opening_album_picker'), 'error');
        }
    }

    async removeFromAlbum(albumId) {
        try {
            await app.apiCall(`/api/albums/${albumId}/media`, {
                method: 'DELETE',
                body: JSON.stringify({ media_ids: [parseInt(this.mediaId)] })
            });

            app.showNotification(window.i18n.t('notifications.media.removed_from_album'), 'success');
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.media.error_removing_from_album'));
        }
    }

    // ==================== Tag Methods ====================

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
            app.showNotification(e.message, 'error', window.i18n.t('notifications.media.error_updating_tags'));
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
            app.showNotification(window.i18n.t('notifications.media.source_updated'), 'success');
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('notifications.media.error_updating_source'));
        }
    }

    async updateRating(rating) {
        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ rating })
            });
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('media.errors.updating_rating'));
        }
    }

    // ==================== Share Methods ====================

    async shareMedia() {
        try {
            const res = await app.apiCall(`/api/media/${this.mediaId}/share`, { method: 'POST' });
            this.showShareLink(res.share_url.split('/').pop(), res.share_ai_metadata);
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('media.errors.creating_share_link'));
        }
    }

    copyShareLink() {
        this.el('share-link-input').select();
        document.execCommand('copy');
        app.showNotification(window.i18n.t('notifications.media.link_copied'), 'success');
    }

    async unshareMedia() {
        const modal = new ModalHelper({
            id: 'unshare-modal',
            type: 'warning',
            title: window.i18n.t('modal.unshare_media.title'),
            message: window.i18n.t('modal.unshare_media.message'),
            confirmText: window.i18n.t('modal.unshare_media.confirm'),
            cancelText: window.i18n.t('modal.buttons.cancel'),
            confirmId: 'unshare-confirm-yes',
            cancelId: 'unshare-confirm-no',
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/media/${this.mediaId}/share`, { method: 'DELETE' });
                    this.el('share-link-section').style.display = 'none';

                    // Reset share button
                    const btn = this.el('share-btn');
                    const btnText = this.el('share-btn-text');
                    if (btn) {
                        btn.style.removeProperty('display');
                        btn.classList.remove('unshare-mode', 'border-danger', 'text-danger', 'hover:bg-danger', 'hover:tag-text');
                        btn.classList.add('surface-light', 'hover:surface-light');
                        btnText.innerHTML = window.i18n.t('media.share.share_button');
                    }

                    app.showNotification(window.i18n.t('notifications.media.media_unshared'), 'success');
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('media.errors.removing_share'));
                }
            }
        });
        modal.show();
    }

    async deleteMedia() {
        const modal = new ModalHelper({
            id: 'delete-modal',
            type: 'danger',
            title: window.i18n.t('modal.delete_media.title'),
            message: window.i18n.t('modal.delete_media.message'),
            confirmText: window.i18n.t('modal.delete_media.confirm'),
            cancelText: window.i18n.t('modal.buttons.cancel'),
            confirmId: 'delete-confirm-yes',
            cancelId: 'delete-confirm-no',
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/media/${this.mediaId}`, { method: 'DELETE' });
                    window.location.href = '/';
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('media.errors.deleting_media'));
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
            app.showNotification(err.message, 'error', window.i18n.t('media.errors.updating_share_settings'));
            const toggle = this.el('share-ai-metadata-toggle');
            if (toggle) toggle.checked = !toggle.checked;
        }
    }

    // ==================== AI Metadata Tags ====================

    async appendAITags() {
        const btn = this.el('append-ai-tags-btn');
        this.setButtonState(btn, window.i18n.t('media.progress.processing'), true);

        try {
            const res = await fetch(`/api/media/${this.mediaId}/metadata`);
            if (!res.ok) {
                app.showNotification(window.i18n.t('notifications.media.could_not_load_ai_metadata'), 'error');
                return;
            }

            const metadata = await res.json();
            const aiPrompt = AITagUtils.extractAIPrompt(metadata);

            if (!aiPrompt || typeof aiPrompt !== 'string') {
                app.showNotification(window.i18n.t('notifications.media.no_ai_prompt'), 'error');
                return;
            }

            const promptTags = AITagUtils.parsePromptTags(aiPrompt);

            const validTags = [];
            for (const tag of promptTags) {
                const validTag = await this.getTagOrAlias(tag);
                if (validTag) {
                    validTags.push(validTag);
                }
            }

            if (validTags.length === 0) {
                app.showNotification(window.i18n.t('notifications.media.no_valid_tags_ai_prompt'), 'error');
                return;
            }

            const tagsInput = this.el('tags-input');
            const currentText = this.tagInputHelper.getPlainTextFromDiv(tagsInput).trim();
            const currentTags = currentText ? currentText.split(/\s+/) : [];

            const existingTagsSet = new Set(currentTags.map(t => t.toLowerCase()));
            const newTags = validTags.filter(tag => !existingTagsSet.has(tag.toLowerCase()));

            if (newTags.length === 0) {
                app.showNotification(window.i18n.t('notifications.media.ai_tags_already_present'), 'info');
                return;
            }

            const allTags = [...currentTags, ...newTags];
            tagsInput.textContent = allTags.join(' ');

            await this.validateAndStyleTags();
            app.showNotification(window.i18n.t('media.ai_tags.appended_count', { count: newTags.length }), 'success');

        } catch (e) {
            console.error('Error appending AI tags:', e);
            app.showNotification(window.i18n.t('media.errors.processing_ai_tags', { error: e.message }), 'error');
        } finally {
            this.setButtonState(btn, window.i18n.t('media.tags.append_ai_tags'), false);
        }
    }



    // ==================== Hierarchy Methods ====================
    renderHierarchy(items) {
        const hierarchyMediaEl = this.el('hierarchy-media');
        const hierarchySection = this.el('hierarchy-media-section');
        const titleEl = this.el('hierarchy-media-title');

        if (!hierarchyMediaEl || !hierarchySection) return;

        if (!items || items.length === 0) {
            hierarchySection.style.display = 'none';
            return;
        }

        // Set dynamic title
        if (this.currentMedia.parent_id) {
            titleEl.textContent = window.i18n.t('media.relations.belongs_to_parent');
        } else {
            const childCount = items.length;
            titleEl.textContent = childCount === 1
                ? window.i18n.t('media.relations.has_one_child')
                : window.i18n.t('media.relations.has_children', { count: childCount });
        }

        const params = new URLSearchParams(window.location.search);
        const queryString = params.toString();
        hierarchySection.style.display = 'block';

        hierarchyMediaEl.innerHTML = '';
        items.forEach(media => {
            const item = this.createRelatedMediaItem(media, queryString);
            item.style.flex = '0 0 auto';
            item.style.width = '120px';
            hierarchyMediaEl.appendChild(item);
        });

        this.setupHierarchyToggle();
        this.setupCarousel();
    }

    setupHierarchyToggle() {
        const toggle = this.el('hierarchy-media-toggle');
        const content = this.el('hierarchy-media-content');
        const chevron = this.el('hierarchy-media-chevron');

        if (!toggle || !content) return;

        // Reset display if needed (default to visible)
        content.style.display = 'block';

        const newToggle = toggle.cloneNode(true);
        toggle.parentNode.replaceChild(newToggle, toggle);

        newToggle.addEventListener('click', () => {
            const isHidden = content.style.display === 'none';
            content.style.display = isHidden ? 'block' : 'none';
            if (chevron) {
                // Point up when expanded (block), point down when collapsed (none)
                chevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });
    }

    setupCarousel() {
        const container = this.el('hierarchy-media');
        const prevBtn = this.el('hierarchy-prev-btn');
        const nextBtn = this.el('hierarchy-next-btn');

        if (!container) return;

        // Prevent native drag on images and links within the carousel
        container.querySelectorAll('a, img').forEach(el => {
            el.draggable = false;
        });

        // Update buttons visibility
        const updateButtons = () => {
            if (prevBtn) {
                const isDisabled = container.scrollLeft <= 0;
                prevBtn.disabled = isDisabled;
                prevBtn.style.pointerEvents = isDisabled ? 'none' : 'auto';
            }
            if (nextBtn) {
                const isDisabled = container.scrollLeft + container.clientWidth >= container.scrollWidth - 1;
                nextBtn.disabled = isDisabled;
                nextBtn.style.pointerEvents = isDisabled ? 'none' : 'auto';
            }
        };

        container.addEventListener('scroll', updateButtons);
        window.addEventListener('resize', updateButtons);
        setTimeout(updateButtons, 100);

        // Click & Drag logic
        let isDown = false;
        let startX;
        let scrollLeft;
        let hasDragged = false;
        const dragThreshold = 5;

        container.addEventListener('mousedown', (e) => {
            isDown = true;
            hasDragged = false;
            container.classList.add('grabbing');
            startX = e.pageX - container.offsetLeft;
            scrollLeft = container.scrollLeft;
        });

        container.addEventListener('mouseleave', () => {
            isDown = false;
            container.classList.remove('grabbing');
        });

        container.addEventListener('mouseup', () => {
            isDown = false;
            container.classList.remove('grabbing');
        });

        container.addEventListener('mousemove', (e) => {
            if (!isDown) return;
            e.preventDefault();
            const x = e.pageX - container.offsetLeft;
            const walk = x - startX;

            if (Math.abs(walk) > dragThreshold) {
                hasDragged = true;
            }

            container.scrollLeft = scrollLeft - walk;
        });

        // Prevent click navigation if user was dragging
        container.addEventListener('click', (e) => {
            if (hasDragged) {
                e.preventDefault();
                e.stopPropagation();
                hasDragged = false;
            }
        }, true);

        // Button logic
        if (prevBtn) {
            prevBtn.onclick = () => {
                container.scrollBy({ left: -300, behavior: 'smooth' });
            };
        }

        if (nextBtn) {
            nextBtn.onclick = () => {
                container.scrollBy({ left: 300, behavior: 'smooth' });
            };
        }
    }

    // ==================== Relation Manager Methods ====================

    setupRelationManager() {
        this.renderRelationStatusDisplay();
        this.setupRelationModalEvents();

        this.el('manage-relations-btn')?.addEventListener('click', () => {
            this.openRelationModal();
        });
    }

    renderRelationStatusDisplay() {
        const container = this.el('relation-status-display');
        if (!container) return;

        const hasParent = !!this.currentMedia.parent_id;
        const hasChildren = this.currentMedia.has_children;
        const childCount = this.currentMedia.hierarchy?.length || 0;

        if (hasParent) {
            container.innerHTML = `
                <div class="flex items-center justify-between">
                    <span class="text-xs">${window.i18n.t('media.relations.parent_label')} <a href="/media/${this.currentMedia.parent_id}" class="hover:text-primary">${window.i18n.t('media.relations.parent_id_link', { id: this.currentMedia.parent_id })}</a></span>
                </div>
            `;
        } else if (hasChildren) {
            container.innerHTML = `
                <span class="text-xs">${childCount === 1 ? window.i18n.t('media.relations.children_count', { count: childCount }) : window.i18n.t('media.relations.children_count_plural', { count: childCount })}</span>
            `;
        } else {
            container.innerHTML = `<p class="text-xs text-secondary">${window.i18n.t('media.relations.no_relations')}</p>`;
        }
    }

    setupRelationModalEvents() {
        const modal = this.el('relation-manager-modal');
        const backdrop = this.el('relation-modal-backdrop');
        const closeBtn = this.el('relation-modal-close');
        const searchForm = this.el('relation-search-form');
        const searchInput = this.el('relation-search-input');

        // Close modal events
        backdrop?.addEventListener('click', () => this.closeRelationModal());
        closeBtn?.addEventListener('click', () => this.closeRelationModal());

        // Search form
        searchForm?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.performRelationSearch();
        });

        // Search input with debounce
        let searchTimeout;
        searchInput?.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.performRelationSearch();
            }, 300);
        });

        // Initialize tag autocomplete for search input
        if (searchInput && typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(searchInput, {
                multipleValues: true
            });
        }

        // Buttons
        this.el('relation-set-parent-btn')?.addEventListener('click', () => this.setSelectedAsParent());
        this.el('relation-add-child-btn')?.addEventListener('click', () => this.addSelectedAsChildren());
        this.el('relation-add-children-btn')?.addEventListener('click', () => this.addSelectedAsChildren());
        this.el('relation-remove-children-btn')?.addEventListener('click', () => this.removeSelectedChildren());
        this.el('relation-clear-selection')?.addEventListener('click', () => this.clearRelationSelection());
        this.el('relation-load-more-btn')?.addEventListener('click', () => this.loadMoreRelationItems());
    }

    openRelationModal() {
        const modal = this.el('relation-manager-modal');
        if (!modal) return;

        // Reset state
        this.relationModal.isOpen = true;
        this.relationModal.selectedItems.clear();
        this.relationModal.currentPage = 1;
        this.relationModal.isSearchMode = false;
        this.relationModal.searchQuery = '';
        this.relationModal.childIds.clear();

        // Store current children IDs for removal functionality
        if (this.currentMedia.hierarchy) {
            this.currentMedia.hierarchy.forEach(item => {
                if (!this.currentMedia.parent_id) {
                    // Current media is parent, hierarchy items are children
                    this.relationModal.childIds.add(item.id);
                }
            });
        }

        // Clear search input
        const searchInput = this.el('relation-search-input');
        if (searchInput) searchInput.value = '';

        // Update status
        this.updateRelationModalStatus();

        // Show modal
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        // Load initial content (related items)
        this.loadRelationGallery();
    }

    closeRelationModal() {
        const modal = this.el('relation-manager-modal');
        if (!modal) return;

        this.relationModal.isOpen = false;
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }

    updateRelationModalStatus() {
        const container = this.el('relation-status-content');
        if (!container) return;

        const hasParent = !!this.currentMedia.parent_id;
        const hasChildren = this.currentMedia.has_children;
        const childCount = this.relationModal.childIds.size;

        let html = '';

        if (hasParent) {
            html = `
                <div class="flex items-center justify-between flex-wrap gap-2">
                    <div>
                        <span class="font-medium">${window.i18n.t('media.relations.current_parent_label')}</span>
                        <a href="/media/${this.currentMedia.parent_id}" target="_blank" class="text-primary hover:underline ml-1">
                            ID ${this.currentMedia.parent_id}
                        </a>
                    </div>
                    <button id="relation-remove-parent-btn" class="px-3 py-1 bg-danger tag-text text-xs hover:opacity-90 transition-opacity">
                        ${window.i18n.t('media.relations.remove_parent_button')}
                    </button>
                </div>
                <p class="text-xs text-secondary mt-2">
                    <svg xmlns="http://www.w3.org/2000/svg" class="inline-block w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="16" x2="12" y2="12"></line>
                        <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    ${window.i18n.t('media.relations.info_has_parent')}
                </p>
            `;
        } else if (hasChildren) {
            html = `
                <div class="flex items-center justify-between flex-wrap gap-2">
                    <span><span class="font-medium">${window.i18n.t('media.relations.children_label')}</span> ${childCount === 1 ? window.i18n.t('media.relations.children_items', { count: childCount }) : window.i18n.t('media.relations.children_items_plural', { count: childCount })}</span>
                </div>
                <p class="text-xs text-secondary mt-2">
                    <svg xmlns="http://www.w3.org/2000/svg" class="inline-block w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="16" x2="12" y2="12"></line>
                        <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    ${window.i18n.t('media.relations.info_has_children')}
                </p>
            `;
        } else {
            html = `
                <p class="text-secondary">
                    <svg xmlns="http://www.w3.org/2000/svg" class="inline-block w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="16" x2="12" y2="12"></line>
                        <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    ${window.i18n.t('media.relations.info_no_relations')}
                </p>
            `;
        }

        container.innerHTML = html;

        // Add remove parent event listener
        this.el('relation-remove-parent-btn')?.addEventListener('click', () => this.removeParent());
    }

    async loadRelationGallery(append = false) {
        if (this.relationModal.isLoading) return;

        this.relationModal.isLoading = true;
        const gallery = this.el('relation-gallery');
        const loading = this.el('relation-loading');
        const empty = this.el('relation-empty');
        const loadMore = this.el('relation-load-more');
        const searchHint = this.el('relation-search-hint');

        if (!append) {
            gallery.innerHTML = '';
        }
        loading.style.display = 'block';
        empty.style.display = 'none';
        loadMore.style.display = 'none';

        try {
            let items = [];
            let totalPages = 1;

            if (this.relationModal.isSearchMode && this.relationModal.searchQuery) {
                const params = new URLSearchParams({
                    q: this.relationModal.searchQuery,
                    page: this.relationModal.currentPage,
                    limit: 24
                });

                const res = await fetch(`/api/search?${params.toString()}`, {
                    credentials: 'include'
                });
                const data = await res.json();
                items = data.items || [];
                totalPages = data.pages || 1;

                searchHint.textContent = window.i18n.t('media.relations.search_results', { query: this.relationModal.searchQuery });
            } else {
                items = await this.getRelatedItemsForModal();
                searchHint.textContent = window.i18n.t('media.relations.search_hint');
            }

            // Filtering logic
            const currentId = parseInt(this.mediaId);

            const isCurrentItemParent = this.currentMedia.has_children ||
                (this.currentMedia.hierarchy &&
                    this.currentMedia.hierarchy.length > 0 &&
                    !this.currentMedia.parent_id);

            items = items.filter(item => {
                if (item.id === currentId) return false;
                if (item.parent_id && item.parent_id !== currentId) {
                    return false;
                }
                if (isCurrentItemParent && item.has_children) {
                    return false;
                }

                return true;
            });

            this.relationModal.totalPages = totalPages;

            if (items.length === 0 && !append) {
                empty.style.display = 'block';
            } else {
                items.forEach(media => {
                    const item = this.createRelationGalleryItem(media);
                    gallery.appendChild(item);
                });

                // Show load more if there are more pages (only in search mode)
                if (this.relationModal.isSearchMode && this.relationModal.currentPage < totalPages) {
                    loadMore.style.display = 'block';
                }
            }
        } catch (e) {
            console.error('Error loading relation gallery:', e);
            empty.style.display = 'block';
            empty.innerHTML = `<p class="text-danger">${window.i18n.t('media.errors.loading_items')}</p>`;
        } finally {
            loading.style.display = 'none';
            this.relationModal.isLoading = false;
        }
    }

    async getRelatedItemsForModal() {
        const items = [];
        const addedIds = new Set();
        const currentId = parseInt(this.mediaId);

        // Add hierarchy items first (parent/siblings or children)
        if (this.currentMedia.hierarchy) {
            this.currentMedia.hierarchy.forEach(item => {
                if (item.id !== currentId && !addedIds.has(item.id)) {
                    items.push(item);
                    addedIds.add(item.id);
                }
            });
        }

        // Add parent if exists
        if (this.currentMedia.parent_id && !addedIds.has(this.currentMedia.parent_id)) {
            try {
                const res = await fetch(`/api/media/${this.currentMedia.parent_id}`);
                if (res.ok) {
                    const parent = await res.json();
                    items.unshift(parent);
                    addedIds.add(parent.id);
                }
            } catch (e) {
                console.error('Error loading parent:', e);
            }
        }

        // Get more related items using tags
        if (this.currentMedia.tags && this.currentMedia.tags.length > 0) {
            const generalTags = this.currentMedia.tags.filter(t => t.category === 'general');
            if (generalTags.length > 0) {
                const tagQuery = generalTags.slice(0, 3).map(t => t.name).join(' ');
                try {
                    const res = await fetch(`/api/search?q=${encodeURIComponent(tagQuery)}&limit=30`, {
                        credentials: 'include'
                    });
                    const data = await res.json();
                    (data.items || []).forEach(item => {
                        if (item.id !== currentId && !addedIds.has(item.id)) {
                            items.push(item);
                            addedIds.add(item.id);
                        }
                    });
                } catch (e) {
                    console.error('Error loading related items:', e);
                }
            }
        }

        return items;
    }

    createRelationGalleryItem(media) {
        const item = document.createElement('div');
        item.className = 'gallery-item relative cursor-pointer border border-2 group';
        item.dataset.id = media.id;

        const isSelected = this.relationModal.selectedItems.has(media.id);
        const isChild = this.relationModal.childIds.has(media.id);
        const isParent = media.id === this.currentMedia.parent_id;

        if (isSelected) item.classList.add('selected');
        if (isChild) item.classList.add('is-child');
        if (isParent) item.classList.add('is-parent');

        // Thumbnail
        const img = document.createElement('img');
        img.src = `/api/media/${media.id}/thumbnail`;
        img.alt = media.filename || window.i18n.t('media.relations.fallback_alt', { id: media.id });
        img.loading = 'lazy';
        img.className = 'w-full aspect-square object-cover transition-all';
        img.draggable = false;
        img.onerror = () => {
            img.src = '/static/images/no-thumbnail.png';
        };

        // Selection overlay
        const overlay = document.createElement('div');
        overlay.className = 'absolute inset-0 bg-primary/30 opacity-0 transition-opacity pointer-events-none';
        if (isSelected) overlay.classList.add('opacity-100');

        // Select Indicator
        const indicator = document.createElement('div');
        indicator.className = 'select-indicator';
        indicator.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
        `;

        // Status badge (parent/child)
        if (isParent || isChild) {
            const badge = document.createElement('div');
            badge.className = `absolute top-1 right-1 px-1.5 py-0.5 text-xs font-medium ${isParent ? 'bg-[var(--parent-outline)] tag-text' : 'bg-[var(--child-outline)] tag-text'}`;
            badge.textContent = isParent ? window.i18n.t('media.relations.parent_badge') : window.i18n.t('media.relations.child_badge');
            item.appendChild(badge);
        }

        // Click handler
        item.addEventListener('click', () => {
            this.toggleRelationItemSelection(media.id, item);
        });

        item.appendChild(img);
        item.appendChild(overlay);
        item.appendChild(indicator);

        return item;
    }

    toggleRelationItemSelection(mediaId, itemElement) {
        const overlay = itemElement.querySelector('.absolute.bg-primary\\/30');

        if (this.relationModal.selectedItems.has(mediaId)) {
            this.relationModal.selectedItems.delete(mediaId);
            itemElement.classList.remove('selected');
            itemElement.classList.remove('border-primary');
            if (overlay) overlay.classList.remove('opacity-100');
        } else {
            this.relationModal.selectedItems.add(mediaId);
            itemElement.classList.add('selected');
            itemElement.classList.add('border-primary');
            if (overlay) overlay.classList.add('opacity-100');
        }

        this.updateRelationActionButtons();
    }

    updateRelationActionButtons() {
        const selectedCount = this.relationModal.selectedItems.size;
        const hasParent = !!this.currentMedia.parent_id;
        const hasChildren = this.currentMedia.has_children;

        const countEl = this.el('relation-selected-count');
        const clearBtn = this.el('relation-clear-selection');
        const setParentBtn = this.el('relation-set-parent-btn');
        const addChildBtn = this.el('relation-add-child-btn');
        const addChildrenBtn = this.el('relation-add-children-btn');
        const removeChildrenBtn = this.el('relation-remove-children-btn');
        const actionsContainer = this.el('relation-actions');

        // Update count
        if (countEl) {
            countEl.textContent = window.i18n.t('media.relations.selected', { count: selectedCount });
        }

        // Show/hide clear button
        if (clearBtn) {
            clearBtn.style.display = selectedCount > 0 ? 'inline' : 'none';
        }

        // Hide all action buttons first
        if (setParentBtn) setParentBtn.style.display = 'none';
        if (addChildBtn) addChildBtn.style.display = 'none';
        if (addChildrenBtn) addChildrenBtn.style.display = 'none';
        if (removeChildrenBtn) removeChildrenBtn.style.display = 'none';

        if (selectedCount === 0) {
            return;
        }

        // Check if any selected items are current children (for removal)
        const selectedChildIds = [...this.relationModal.selectedItems].filter(id =>
            this.relationModal.childIds.has(id)
        );
        const hasSelectedChildren = selectedChildIds.length > 0;

        // Determine which buttons to show based on current state and selection
        if (hasParent) {
            // Current media has a parent - can only change parent
            if (selectedCount === 1) {
                const selectedId = [...this.relationModal.selectedItems][0];
                if (selectedId !== this.currentMedia.parent_id) {
                    if (setParentBtn) setParentBtn.style.display = 'block';
                }
            }
        } else if (hasChildren) {
            // Current media has children - can add more or remove existing
            if (hasSelectedChildren) {
                if (removeChildrenBtn) {
                    removeChildrenBtn.style.display = 'block';
                    removeChildrenBtn.textContent = window.i18n.t('media.relations.remove_children', { count: selectedChildIds.length });
                }
            }
            // Check for non-child items to add
            const nonChildSelected = [...this.relationModal.selectedItems].filter(id =>
                !this.relationModal.childIds.has(id)
            );
            if (nonChildSelected.length > 0) {
                if (nonChildSelected.length === 1) {
                    if (addChildBtn) addChildBtn.style.display = 'block';
                } else {
                    if (addChildrenBtn) {
                        addChildrenBtn.style.display = 'block';
                        addChildrenBtn.textContent = window.i18n.t('media.relations.add_children_count', { count: nonChildSelected.length });
                    }
                }
            }
        } else {
            // No relations - can set parent (1 item) or add children (any number)
            if (selectedCount === 1) {
                if (setParentBtn) setParentBtn.style.display = 'block';
                if (addChildBtn) addChildBtn.style.display = 'block';
            } else {
                if (addChildrenBtn) {
                    addChildrenBtn.style.display = 'block';
                    addChildrenBtn.textContent = window.i18n.t('media.relations.add_children_count', { count: selectedCount });
                }
            }
        }
    }

    clearRelationSelection() {
        this.relationModal.selectedItems.clear();

        const gallery = this.el('relation-gallery');
        gallery.querySelectorAll('.gallery-item').forEach(item => {
            item.classList.remove('selected');
            item.classList.remove('border-primary');

            const overlay = item.querySelector('.absolute.bg-primary\\/30');
            if (overlay) overlay.classList.remove('opacity-100');
        });

        this.updateRelationActionButtons();
    }

    performRelationSearch() {
        const searchInput = this.el('relation-search-input');
        const query = searchInput?.value.trim() || '';

        this.relationModal.searchQuery = query;
        this.relationModal.isSearchMode = query.length > 0;
        this.relationModal.currentPage = 1;

        this.loadRelationGallery();
    }

    loadMoreRelationItems() {
        this.relationModal.currentPage++;
        this.loadRelationGallery(true);
    }

    async setSelectedAsParent() {
        if (this.relationModal.selectedItems.size !== 1) return;

        const parentId = [...this.relationModal.selectedItems][0];

        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ parent_id: parentId })
            });

            app.showNotification(window.i18n.t('notifications.media.parent_set'), 'success');
            this.closeRelationModal();
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('media.errors.setting_parent'));
        }
    }

    async addSelectedAsChildren() {
        const selectedIds = [...this.relationModal.selectedItems].filter(id =>
            !this.relationModal.childIds.has(id)
        );

        if (selectedIds.length === 0) return;

        try {
            // Set current media as parent for each selected item
            for (const childId of selectedIds) {
                await app.apiCall(`/api/media/${childId}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ parent_id: parseInt(this.mediaId) })
                });
            }

            app.showNotification(selectedIds.length === 1 ? window.i18n.t('media.relations.added_children_success', { count: selectedIds.length }) : window.i18n.t('media.relations.added_children_success_plural', { count: selectedIds.length }), 'success');
            this.closeRelationModal();
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('media.errors.adding_children'));
        }
    }

    async removeSelectedChildren() {
        const selectedChildIds = [...this.relationModal.selectedItems].filter(id =>
            this.relationModal.childIds.has(id)
        );

        if (selectedChildIds.length === 0) return;

        const modal = new ModalHelper({
            id: 'remove-children-modal',
            type: 'warning',
            title: window.i18n.t('modal.remove_children.title'),
            message: window.i18n.t('modal.remove_children.message', { count: selectedChildIds.length }),
            confirmText: window.i18n.t('modal.remove_children.confirm'),
            cancelText: window.i18n.t('modal.buttons.cancel'),
            onConfirm: async () => {
                try {
                    for (const childId of selectedChildIds) {
                        await app.apiCall(`/api/media/${childId}`, {
                            method: 'PATCH',
                            body: JSON.stringify({ parent_id: null })
                        });
                    }

                    app.showNotification(selectedChildIds.length === 1 ? window.i18n.t('media.relations.removed_children_success', { count: selectedChildIds.length }) : window.i18n.t('media.relations.removed_children_success_plural', { count: selectedChildIds.length }), 'success');
                    this.closeRelationModal();
                    location.reload();
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('media.errors.removing_children'));
                }
            }
        });
        modal.show();
    }

    async removeParent() {
        const modal = new ModalHelper({
            id: 'remove-parent-modal',
            type: 'warning',
            title: window.i18n.t('modal.remove_parent.title'),
            message: window.i18n.t('modal.remove_parent.message'),
            confirmText: window.i18n.t('modal.remove_parent.confirm'),
            cancelText: window.i18n.t('modal.buttons.cancel'),
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/media/${this.mediaId}`, {
                        method: 'PATCH',
                        body: JSON.stringify({ parent_id: null })
                    });

                    app.showNotification(window.i18n.t('notifications.media.parent_removed'), 'success');
                    this.closeRelationModal();
                    location.reload();
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('media.errors.removing_parent'));
                }
            }
        });
        modal.show();
    }

    showShareLink(uuid, shareAIMetadata) {
        const baseUrl = this.externalShareUrl || window.location.origin;
        // Remove trailing slash if present to avoid double slashes
        const cleanBaseUrl = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;

        this.el('share-link-input').value = `${cleanBaseUrl}/shared/${uuid}`;
        this.el('share-link-section').style.display = 'block';

        // Update share button to unshare mode
        const btn = this.el('share-btn');
        const btnText = this.el('share-btn-text');
        if (btn) {
            btn.style.removeProperty('display');
            btn.classList.add('unshare-mode', 'border-danger', 'text-danger', 'hover:bg-danger', 'hover:tag-text');
            btn.classList.remove('surface-light', 'hover:surface-light');
            btnText.innerHTML = window.i18n.t('media.share.unshare_button');
        }

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
