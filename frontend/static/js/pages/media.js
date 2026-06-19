class MediaViewer extends MediaViewerBase {
    constructor(mediaId, externalShareUrl = null) {
        super();
        this.mediaId = mediaId;
        this.externalShareUrl = externalShareUrl;
        this.tagInputHelper = new TagInputHelper();
        this.validationTimeout = null;
        this.tooltipHelper = null;
        this.ratingSelect = null;
        this.shareLanguageSelect = null;

        // WD Tagger settings
        this.wdTaggerSettings = {
            generalThreshold: 0.35,
            characterThreshold: 0.85,
            modelName: 'wd-eva02-large-tagger-v3'
        };

        this.init();
    }

    async init() {
        await this.loadWDTaggerSettings();
        this.initFullscreenViewer();
        this.initTooltipHelper();
        this.loadMedia();
        this.setupAIMetadataToggle();
        this.setupEventListeners();
    }

    async loadWDTaggerSettings() {
        try {
            const res = await fetch('/api/ai-tagger/settings');
            if (res.ok) {
                const data = await res.json();
                this.wdTaggerSettings.generalThreshold = data.general_threshold ?? this.wdTaggerSettings.generalThreshold;
                this.wdTaggerSettings.characterThreshold = data.character_threshold ?? this.wdTaggerSettings.characterThreshold;
                this.wdTaggerSettings.modelName = data.model_name ?? this.wdTaggerSettings.modelName;
            }
        } catch (e) {
            // Non-fatal, fall back to defaults
        }
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

            // Show description for all users when it is set and not in admin mode
            if (this.currentMedia.description && !app.isAdminMode) {
                const displaySection = this.el('description-display-section');
                const displayText = this.el('description-display-text');
                if (displaySection && displayText) {
                    displayText.textContent = this.currentMedia.description;
                    displaySection.style.display = 'block';
                }
            }
        } catch (e) {
            console.error('loadMedia error', e);
        }
    }

    setupAdminMode() {
        this.el('edit-tags-section').style.display = 'block';
        this.el('edit-source-section').style.display = 'block';
        this.el('edit-description-section').style.display = 'block';
        this.el('admin-actions').style.display = 'flex';
        this.setupTagInput();
        this.setupEditTagsToggle();

        // Set source input value
        const sourceInput = this.el('source-input');
        if (sourceInput) {
            sourceInput.value = this.currentMedia.source || '';
        }

        // Set description input value
        const descriptionInput = this.el('description-input');
        if (descriptionInput) {
            descriptionInput.value = this.currentMedia.description || '';
        }

        // Initialize tag autocomplete
        const tagsInput = this.el('tags-input');
        if (tagsInput) {
            new TagAutocomplete(tagsInput, {
                multipleValues: true,
                allowCreate: true,
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

        // Initialize custom select for share language
        const shareLanguageSelectElement = this.el('share-language-select');
        if (shareLanguageSelectElement) {
            this.shareLanguageSelect = new CustomSelect(shareLanguageSelectElement);
            if (this.currentMedia.share_language) {
                this.shareLanguageSelect.setValue(this.currentMedia.share_language);
            }

            this.shareLanguageSelect.element.addEventListener('change', async (e) => {
                await this.updateShareSettings({ share_language: e.detail.value });
            });
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

            const source = document.createElement('source');
            source.src = `/api/media/${media.id}/file${media.hash ? '?v=' + media.hash : ''}`;
            source.type = media.mime_type;

            video.appendChild(source);

            video.onerror = () => {
                container.innerHTML = `
                    <div class="flex flex-col items-center justify-center py-8 text-secondary">
                        <img src="/static/images/no-thumbnail.png" alt="${window.i18n.t('common.media_not_found')}" class="w-32 h-32 mb-4 opacity-50">
                        <p class="text-sm">${window.i18n.t('media.errors.failed_to_load_video')}</p>
                    </div>
                `;
            };

            container.innerHTML = '';
            container.appendChild(video);
        } else {
            const img = document.createElement('img');
            img.src = `/api/media/${media.id}/file${media.hash ? '?v=' + media.hash : ''}`;
            img.alt = media.filename;
            img.id = 'main-media-image';
            img.style.cursor = 'pointer';

            img.onerror = () => {
                img.src = '/static/images/no-thumbnail.png';
                img.alt = window.i18n.t('common.media_not_found');
                img.style.cursor = 'default';
                img.onclick = null;
            };

            img.onload = () => {
                if (!img.src.includes('no-thumbnail.png')) {
                    img.addEventListener('click', () => {
                        this.fullscreenViewer.open(`/api/media/${media.id}/file${media.hash ? '?v=' + media.hash : ''}`, false);
                    });
                }
            };

            container.innerHTML = '';
            container.appendChild(img);
        }

        this.el('download-btn').href = `/api/media/${media.id}/file${media.hash ? '?v=' + media.hash : ''}`;
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

        const relatedMediaEl = this.el('related-media');
        const relatedMediaSection = this.el('related-media-section') || relatedMediaEl?.parentElement;
        const relatedMediaLoading = this.el('related-media-loading');

        if (relatedMediaSection) relatedMediaSection.style.display = 'block';
        if (relatedMediaLoading) relatedMediaLoading.style.display = 'block';
        if (relatedMediaEl) relatedMediaEl.style.display = 'none';

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
        const relatedMediaSection = this.el('related-media-section') || relatedMediaEl?.parentElement;
        const relatedMediaLoading = this.el('related-media-loading');
        const params = new URLSearchParams(window.location.search);
        const queryString = params.toString();

        if (relatedMediaSection) relatedMediaSection.style.display = 'block';
        if (relatedMediaLoading) relatedMediaLoading.style.display = 'none';
        if (relatedMediaEl) {
            relatedMediaEl.style.display = 'grid';
            relatedMediaEl.classList.add('grid');
            relatedMediaEl.innerHTML = '';
        }

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
        img.src = `/api/media/${media.id}/thumbnail${media.hash ? '?v=' + media.hash : ''}`;
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
            shareIcon.className = 'share-icon w-6 h-6 flex items-center justify-center p-0';
            shareIcon.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
                    stroke-linejoin="round">
                    <circle cx="18" cy="5" r="3"></circle>
                    <circle cx="6" cy="12" r="3"></circle>
                    <circle cx="18" cy="19" r="3"></circle>
                    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
                    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
                </svg>`;
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
        const relatedMediaSection = this.el('related-media-section') || relatedMediaEl?.parentElement;
        if (relatedMediaSection) {
            relatedMediaSection.style.display = 'none';
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

        this.el('save-description-btn')?.addEventListener('click', async () => {
            await this.saveDescription();
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
            await this.updateShareSettings({ share_ai_metadata: e.target.checked });
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

        this.el('update-post-btn')?.addEventListener('click', () => {
            const modal = new UpdatePostModal(this.mediaId, this.currentMedia);
            modal.show();
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
                    cancelText: window.i18n.t('common.cancel'),
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
                title: window.i18n.t('common.add_to_albums'),
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

    async saveDescription() {
        const descriptionInput = this.el('description-input');
        const descriptionValue = descriptionInput ? descriptionInput.value.trim() : '';

        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ description: descriptionValue || null })
            });
            app.showNotification(window.i18n.t('notifications.media.description_updated'), 'success');
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('notifications.media.error_updating_description'));
        }
    }

    async updateRating(rating) {
        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ rating })
            });
            app.showNotification(window.i18n.t('notifications.media.rating_updated'), 'success');
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
            cancelText: window.i18n.t('common.cancel'),
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
                        btnText.innerHTML = window.i18n.t('common.share');
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
            confirmText: window.i18n.t('common.yes_delete'),
            cancelText: window.i18n.t('common.cancel'),
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

    async updateShareSettings(updates) {
        try {
            await app.apiCall(`/api/media/${this.mediaId}/share-settings`, {
                method: 'PATCH',
                body: JSON.stringify(updates)
            });
        } catch (err) {
            app.showNotification(err.message, 'error', window.i18n.t('media.errors.updating_share_settings'));
            const toggle = this.el('share-ai-metadata-toggle');
            const languageSelect = this.el('share-language-select');
            if (toggle) toggle.checked = !toggle.checked;
            if (languageSelect) languageSelect.value = 'default';
        }
    }

    // ==================== AI Metadata Tags ====================

    async appendAITags() {
        const btn = this.el('append-ai-tags-btn');
        this.setButtonState(btn, window.i18n.t('common.processing'), true);

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

        // Track current children IDs for badge/removal functionality
        this.relationChildIds = new Set();
        if (this.currentMedia.hierarchy) {
            this.currentMedia.hierarchy.forEach(item => {
                if (!this.currentMedia.parent_id) {
                    this.relationChildIds.add(item.id);
                }
            });
        }

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

    _buildRelationStatusHtml() {
        const hasParent = !!this.currentMedia.parent_id;
        const hasChildren = this.currentMedia.has_children;
        const childCount = this.relationChildIds.size;

        const infoIcon = `<svg xmlns="http://www.w3.org/2000/svg" class="inline-block w-4 h-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;

        if (hasParent) {
            return `
                <div class="flex items-center justify-between flex-wrap gap-2">
                    <div>
                        <span class="font-medium">${window.i18n.t('media.relations.current_parent_label')}</span>
                        <a href="/media/${this.currentMedia.parent_id}" target="_blank" class="text-primary hover:underline ml-1">
                            ID ${this.currentMedia.parent_id}
                        </a>
                    </div>
                    <button id="relation-remove-parent-btn" class="btn-danger px-3 py-1">
                        ${window.i18n.t('media.relations.remove_parent_button')}
                    </button>
                </div>
                <p class="text-xs text-secondary mt-2">${infoIcon}${window.i18n.t('media.relations.info_has_parent')}</p>
            `;
        } else if (hasChildren) {
            return `
                <div class="flex items-center justify-between flex-wrap gap-2">
                    <span><span class="font-medium">${window.i18n.t('media.relations.children_label')}</span> ${childCount === 1 ? window.i18n.t('media.relations.children_items', { count: childCount }) : window.i18n.t('common.items_count', { count: childCount })}</span>
                </div>
                <p class="text-xs text-secondary mt-2">${infoIcon}${window.i18n.t('media.relations.info_has_children')}</p>
            `;
        } else {
            return `<p class="text-secondary">${infoIcon}${window.i18n.t('media.relations.info_no_relations')}</p>`;
        }
    }

    openRelationModal() {
        const currentId = parseInt(this.mediaId);
        const isCurrentItemParent = this.currentMedia.has_children ||
            (this.currentMedia.hierarchy &&
                this.currentMedia.hierarchy.length > 0 &&
                !this.currentMedia.parent_id);

        // Build extra action buttons for relation management
        const extraButtons = [
            { id: 'relation-set-parent-btn', text: window.i18n.t('media.relations.set_parent'), className: 'btn-primary', onClick: () => this.setSelectedAsParent() },
            { id: 'relation-add-child-btn', text: window.i18n.t('media.relations.add_child'), className: 'btn-primary', onClick: () => this.addSelectedAsChildren() },
            { id: 'relation-add-children-btn', text: window.i18n.t('media.relations.add_children'), className: 'btn-primary', onClick: () => this.addSelectedAsChildren() },
            { id: 'relation-remove-children-btn', text: window.i18n.t('media.relations.remove_selected'), className: 'btn-danger', onClick: () => this.removeSelectedChildren() },
        ];

        // Destroy any previous picker instance
        if (this._relationPicker) {
            this._relationPicker.destroy();
        }

        this._relationPicker = new MediaPickerModal({
            title: window.i18n.t('media.relations.title'),
            mode: 'multi',
            excludeIds: [currentId],
            statusHtml: this._buildRelationStatusHtml(),
            extraButtons: extraButtons,
            confirmText: window.i18n.t('common.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            filterFn: (item) => {
                // Items already parented to someone else are not eligible
                if (item.parent_id && item.parent_id !== currentId) return false;
                // If current is a parent, other parents cannot become children
                if (isCurrentItemParent && item.has_children) return false;
                return true;
            },
            getInitialItems: async () => {
                return await this._getRelatedItemsForModal();
            },
            badgeFn: (media) => {
                const isParent = media.id === this.currentMedia.parent_id;
                const isChild = this.relationChildIds.has(media.id);
                if (isParent) return { text: window.i18n.t('media.relations.parent_badge'), className: 'bg-[var(--parent-outline)] tag-text' };
                if (isChild) return { text: window.i18n.t('media.relations.child_badge'), className: 'bg-[var(--child-outline)] tag-text' };
                return null;
            },
            onCancel: () => {},
        });

        // Override the footer update to add relation-specific button logic
        const originalUpdateFooter = this._relationPicker._updateFooter.bind(this._relationPicker);
        this._relationPicker._updateFooter = () => {
            originalUpdateFooter();
            this._updateRelationActionButtons();
        };

        this._relationPicker.open();

        // Attach remove-parent listener in the status bar
        const removeParentBtn = this._relationPicker.root?.querySelector('#relation-remove-parent-btn');
        if (removeParentBtn) {
            removeParentBtn.addEventListener('click', () => this.removeParent());
        }
    }

    closeRelationModal() {
        if (this._relationPicker) {
            this._relationPicker.close();
        }
    }

    _updateRelationActionButtons() {
        const picker = this._relationPicker;
        if (!picker || !picker.root) return;

        const selectedCount = picker.selectedItems.size;
        const hasParent = !!this.currentMedia.parent_id;
        const hasChildren = this.currentMedia.has_children;

        const setParentBtn = picker.getButton('relation-set-parent-btn');
        const addChildBtn = picker.getButton('relation-add-child-btn');
        const addChildrenBtn = picker.getButton('relation-add-children-btn');
        const removeChildrenBtn = picker.getButton('relation-remove-children-btn');

        // Hide all first
        if (setParentBtn) setParentBtn.style.display = 'none';
        if (addChildBtn) addChildBtn.style.display = 'none';
        if (addChildrenBtn) addChildrenBtn.style.display = 'none';
        if (removeChildrenBtn) removeChildrenBtn.style.display = 'none';

        // Also hide the generic confirm button (relation manager uses its own buttons)
        const confirmBtn = picker.root.querySelector('.mpicker-confirm-btn');
        if (confirmBtn) confirmBtn.style.display = 'none';

        if (selectedCount === 0) return;

        const selectedIds = [...picker.selectedItems.keys()];
        const selectedChildIds = selectedIds.filter(id => this.relationChildIds.has(id));
        const nonChildSelected = selectedIds.filter(id => !this.relationChildIds.has(id));

        if (hasParent) {
            if (selectedCount === 1) {
                const selectedId = selectedIds[0];
                if (selectedId !== this.currentMedia.parent_id) {
                    if (setParentBtn) setParentBtn.style.display = 'block';
                }
            }
        } else if (hasChildren) {
            if (selectedChildIds.length > 0) {
                if (removeChildrenBtn) {
                    removeChildrenBtn.style.display = 'block';
                    removeChildrenBtn.textContent = window.i18n.t('media.relations.remove_children', { count: selectedChildIds.length });
                }
            }
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

    async _getRelatedItemsForModal() {
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

    async setSelectedAsParent() {
        const picker = this._relationPicker;
        if (!picker || picker.selectedItems.size !== 1) return;

        const parentId = [...picker.selectedItems.keys()][0];

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
        const picker = this._relationPicker;
        if (!picker) return;

        const selectedIds = [...picker.selectedItems.keys()].filter(id =>
            !this.relationChildIds.has(id)
        );

        if (selectedIds.length === 0) return;

        try {
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
        const picker = this._relationPicker;
        if (!picker) return;

        const selectedChildIds = [...picker.selectedItems.keys()].filter(id =>
            this.relationChildIds.has(id)
        );

        if (selectedChildIds.length === 0) return;

        const modal = new ModalHelper({
            id: 'remove-children-modal',
            type: 'warning',
            title: window.i18n.t('modal.remove_children.title'),
            message: window.i18n.t('modal.remove_children.message', { count: selectedChildIds.length }),
            confirmText: window.i18n.t('common.yes_remove'),
            cancelText: window.i18n.t('common.cancel'),
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
            confirmText: window.i18n.t('common.yes_remove'),
            cancelText: window.i18n.t('common.cancel'),
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
            btnText.innerHTML = window.i18n.t('common.unshare');
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
