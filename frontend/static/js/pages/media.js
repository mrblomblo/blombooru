class MediaViewer extends MediaViewerBase {
    constructor(mediaId, externalShareUrl = null, albumId = null) {
        super();
        this.mediaId = mediaId;
        this.externalShareUrl = externalShareUrl;
        if (albumId) {
            this.albumId = albumId;
        } else {
            const albumMatch = window.location.pathname.match(/\/album\/(\d+)\/media\//);
            this.albumId = albumMatch ? albumMatch[1] : null;
        }
        this.tagInputHelper = new TagInputHelper();
        this.originalTags = new Set();
        this.impliedTagsMap = new Map();
        this.hiddenImpliedTags = new Set();
        this.expandedTriggerTags = new Set();
        this.validationTimeout = null;
        this.tooltipHelper = null;
        this.ratingSelect = null;
        this.shareLanguageSelect = null;
        this.suggestedCategorySelect = null;
        this.suggestedSearchCategorySelect = null;
        this.tagCategoryCache = new Map();
        this._suggestedTagsCategory = null;
        this._suggestedSearchCategory = null;
        this._suggestedTagsRetryTimeout = null;

        // WD Tagger settings
        this.wdTaggerSettings = {
            generalThreshold: 0.35,
            characterThreshold: 0.85,
            modelName: 'wd-eva02-large-tagger-v3'
        };
        this._descPreviewRequestId = 0;
        this.isDescEnlarged = false;
        this._isTogglingEnlarge = false;
        this.loadedGifs = new Set();

        this.init();
    }

    async init() {
        await this.loadWDTaggerSettings();
        this.initFullscreenViewer();
        this.initTooltipHelper();
        this.setupBackToAlbum();
        this.setupMediaNavigation();
        this.loadMedia();
        this.setupAIMetadataToggle();
        this.setupEventListeners();
        this.setupKeybindings();
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
            this.isDescEnlarged = Boolean(this.currentMedia && this.currentMedia.description_enlarged);
            this.applyDescriptionLayout();

            if (this.currentMedia && Array.isArray(this.currentMedia.tags)) {
                this.originalTags = new Set(this.currentMedia.tags.map(t => (t.name || t).toLowerCase().trim()));
                this.impliedTagsMap = new Map();
                this.hiddenImpliedTags = new Set();
                this.expandedTriggerTags = new Set();
                for (const tag of this.currentMedia.tags) {
                    const tagName = (tag.name || tag).toLowerCase().trim();
                    if (tagName) {
                        this.expandedTriggerTags.add(tagName);
                        if (tag && typeof tag === 'object' && tag.implied) {
                            this.impliedTagsMap.set(
                                tagName,
                                Array.isArray(tag.implied_by) ? tag.implied_by : []
                            );
                        }
                        if (this.tagInputHelper) {
                            this.tagInputHelper.tagValidationCache.set(tagName, true);
                            this.tagInputHelper.tagCategoryCache.set(tagName, tag.category || 'general');
                        }
                        const cat = tag.category || 'general';
                        this.tagCategoryCache.set(tagName, cat);
                    }
                }
            } else {
                this.originalTags = new Set();
                this.impliedTagsMap = new Map();
                this.hiddenImpliedTags = new Set();
                this.expandedTriggerTags = new Set();
            }
            this.renderMedia(this.currentMedia);
            this.renderInfo(this.currentMedia, { isAdmin: app.isAdminMode });
            this.renderTags(this.currentMedia, { clickable: true });

            // Show rendered description for non-admin viewers
            if (this.currentMedia.description && !app.isAdminMode) {
                const html = this.currentMedia.description_html
                    || escapeHtml(this.currentMedia.description);
                const displayText = this.el('description-display-text');
                if (displayText) displayText.innerHTML = html;
                const enlargedDisplayText = this.el('enlarged-desc-display-text');
                if (enlargedDisplayText) enlargedDisplayText.innerHTML = html;
            }

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

            await this.renderHierarchy(this.currentMedia.hierarchy);
            await Promise.all([
                this.loadMediaAlbums(),
                this.albumId ? this.loadAlbumStrip() : Promise.resolve(),
                this.loadRelatedMedia(),
            ]);
        } catch (e) {
            console.error('loadMedia error', e);
        }
    }

    setupAdminMode() {
        this.el('edit-tags-section').style.display = 'block';
        this.el('admin-actions').style.display = 'flex';
        this.setupTagInput();
        this.setupEditTagsToggle();
        this.setupSuggestedTags();
        this.setupEditDateToggle();
        this.setupEditSourceToggle();

        // Set description input value and tabs
        const desc = (this.currentMedia && this.currentMedia.description) || '';
        const descriptionInput = this.el('description-input');
        if (descriptionInput) {
            descriptionInput.value = desc;
        }
        const enlargedDescriptionInput = this.el('enlarged-description-input');
        if (enlargedDescriptionInput) {
            enlargedDescriptionInput.value = desc;
        }
        this.setupDescriptionTabs();
        this.applyDescriptionLayout();

        // Initialize tag autocomplete
        const tagsInput = this.el('tags-input');
        if (tagsInput) {
            new TagAutocomplete(tagsInput, {
                multipleValues: true,
                allowCreate: true,
                onSelect: () => {
                    setTimeout(() => {
                        this.validateAndStyleTags();
                        this.updateSuggestedTags();
                    }, 100);
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

            const hideImpliedCheckbox = this.el('hide-implied-tags-checkbox');
            const isHideImplied = this.tagInputHelper ? this.tagInputHelper.isHideImpliedEnabled() : false;
            if (hideImpliedCheckbox) {
                hideImpliedCheckbox.checked = isHideImplied;
                hideImpliedCheckbox.onchange = () => {
                    const checked = hideImpliedCheckbox.checked;
                    this.tagInputHelper.setHideImpliedEnabled(checked);
                    this.applyHideImpliedToEditor(checked);
                };
            }
            if (!this._hideImpliedWindowListenerAdded) {
                this._hideImpliedWindowListenerAdded = true;
                window.addEventListener('hideImpliedTagsChanged', (e) => {
                    const enabled = Boolean(e.detail && e.detail.enabled);
                    const cb = this.el('hide-implied-tags-checkbox');
                    if (cb && cb.checked !== enabled) {
                        cb.checked = enabled;
                    }
                    this.applyHideImpliedToEditor(enabled);
                });
            }

            this.hiddenImpliedTags.clear();
            if (isHideImplied) {
                const visibleSorted = [];
                for (const t of sortedTags) {
                    const lower = (t.name || '').toLowerCase().trim();
                    if (this.impliedTagsMap.has(lower)) {
                        this.hiddenImpliedTags.add(lower);
                    } else {
                        visibleSorted.push(t.name);
                    }
                }
                tagsInput.textContent = visibleSorted.join(' ');
            } else {
                tagsInput.textContent = sortedTags.map(t => t.name).join(' ');
            }
            this.validateAndStyleTags();
            this.updateSuggestedTags();
        }

        // Initialize custom select for rating
        const ratingSelectElement = this.el('rating-select-inline');
        if (ratingSelectElement) {
            this.ratingSelect = new CustomSelect(ratingSelectElement);
            if (this.currentMedia.rating) {
                this.ratingSelect.setValue(this.currentMedia.rating);
            }
            ratingSelectElement.addEventListener('change', async (e) => {
                await this.updateRating(e.detail.value);
            });
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

            if (isHidden) {
                this.updateSuggestedTags();
            }
        });
    }

    setupEditDateToggle() {
        const toggle = this.el('edit-date-toggle');
        const content = this.el('edit-date-content');

        if (!toggle || !content) return;

        // Ensure initial state
        content.style.display = 'none';
        const chevron = toggle.querySelector('#edit-date-chevron');
        if (chevron) {
            chevron.style.transform = 'rotate(0deg)';
        }

        // Remove any existing listeners by cloning
        const newToggle = toggle.cloneNode(true);
        toggle.parentNode.replaceChild(newToggle, toggle);

        newToggle.addEventListener('click', () => {
            const isHidden = content.style.display === 'none';
            content.style.display = isHidden ? 'block' : 'none';

            const activeChevron = newToggle.querySelector('#edit-date-chevron');
            if (activeChevron) {
                activeChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });

        const customDateInput = this.el('custom-date-input');
        if (customDateInput) {
            customDateInput.value = toLocalInputDateTime(this.currentMedia.custom_date || this.currentMedia.uploaded_at);
            this.initialCustomDateValue = customDateInput.value;
            this.updateSaveCustomDateButtonVisibility();

            customDateInput.oninput = () => this.updateSaveCustomDateButtonVisibility();
            customDateInput.onchange = () => this.updateSaveCustomDateButtonVisibility();
            customDateInput.onkeydown = async (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const saveBtn = this.el('save-custom-date-btn');
                    if (saveBtn && saveBtn.style.display !== 'none') {
                        await this.saveCustomDate();
                    }
                }
            };
        }

        const saveDateBtn = this.el('save-custom-date-btn');
        if (saveDateBtn) {
            saveDateBtn.onclick = async () => {
                await this.saveCustomDate();
            };
        }
    }

    setupEditSourceToggle() {
        const toggle = this.el('edit-source-toggle');
        const content = this.el('edit-source-content');

        if (!toggle || !content) return;

        // Ensure initial state
        content.style.display = 'none';
        const chevron = toggle.querySelector('#edit-source-chevron');
        if (chevron) {
            chevron.style.transform = 'rotate(0deg)';
        }

        // Remove any existing listeners by cloning
        const newToggle = toggle.cloneNode(true);
        toggle.parentNode.replaceChild(newToggle, toggle);

        newToggle.addEventListener('click', (e) => {
            if (e.target.closest('a')) {
                return;
            }
            const isHidden = content.style.display === 'none';
            content.style.display = isHidden ? 'block' : 'none';

            const activeChevron = newToggle.querySelector('#edit-source-chevron');
            if (activeChevron) {
                activeChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });

        const sourceInput = this.el('source-input');
        if (sourceInput) {
            sourceInput.value = this.currentMedia.source || '';
            this.initialSourceValue = sourceInput.value.trim();
            this.updateSaveSourceButtonVisibility();

            sourceInput.oninput = () => this.updateSaveSourceButtonVisibility();
            sourceInput.onchange = () => this.updateSaveSourceButtonVisibility();
            sourceInput.onkeydown = async (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const saveBtn = this.el('save-source-btn');
                    if (saveBtn && saveBtn.style.display !== 'none') {
                        await this.saveSource();
                    }
                }
            };
        }

        const saveSourceBtn = this.el('save-source-btn');
        if (saveSourceBtn) {
            saveSourceBtn.onclick = async () => {
                await this.saveSource();
            };
        }
    }

    renderMedia(media) {
        const container = this.el('media-container');
        if (media.file_type === 'video') {
            const video = document.createElement('video');
            video.controls = true;
            video.loop = true;

            const source = document.createElement('source');
            source.src = `/api/media/${media.id}/file?chunked=true${media.hash ? '&v=' + media.hash : ''}`;

            let videoType = media.mime_type || 'video/mp4';
            const fmt = window.FormatRegistry ? window.FormatRegistry.getFormat(media.filename) : null;
            if (media.transcoded_path) {
                const transcodedFmt = window.FormatRegistry ? window.FormatRegistry.getFormat(media.transcoded_path) : null;
                videoType = transcodedFmt ? transcodedFmt.mime_type : 'video/mp4';
            } else if (fmt && fmt.requires_transcode && fmt.category === 'video') {
                const targetFmt = fmt.transcode_target && window.FormatRegistry ? window.FormatRegistry.getFormat(fmt.transcode_target) : null;
                videoType = targetFmt ? targetFmt.mime_type : 'video/mp4';
            }
            source.type = videoType;

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

    setupEventListeners() {
        this.el('edit-tags-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.saveTags();
        });

        this.el('save-description-btn')?.addEventListener('click', async () => {
            await this.saveDescription();
        });

        this.el('enlarged-save-description-btn')?.addEventListener('click', async () => {
            await this.saveDescription();
        });

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

    async saveSource() {
        const sourceInput = this.el('source-input');
        const sourceValue = sourceInput.value.trim();

        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ source: sourceValue || null })
            });
            this.initialSourceValue = sourceValue;
            this.updateSaveSourceButtonVisibility();
            app.showNotification(window.i18n.t('notifications.media.source_updated'), 'success');
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('notifications.media.error_updating_source'));
        }
    }

    async saveCustomDate() {
        const input = this.el('custom-date-input');
        if (!input) return;
        const val = input.value.trim();
        let isoValue = null;
        if (val) {
            isoValue = parseLocalInputDateTime(val);
            if (!isoValue) {
                app.showNotification(window.i18n.t('notifications.media.error_updating_date'), 'error');
                return;
            }
        }

        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ custom_date: isoValue })
            });
            this.initialCustomDateValue = input.value;
            this.updateSaveCustomDateButtonVisibility();
            app.showNotification(window.i18n.t('notifications.media.date_updated'), 'success');
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('notifications.media.error_updating_date'));
        }
    }

    updateSaveCustomDateButtonVisibility() {
        const input = this.el('custom-date-input');
        const saveBtn = this.el('save-custom-date-btn');
        if (!saveBtn) return;

        const currentVal = input ? input.value.trim() : '';
        const initialVal = (this.initialCustomDateValue !== undefined)
            ? this.initialCustomDateValue.trim()
            : (this.currentMedia ? toLocalInputDateTime(this.currentMedia.custom_date || this.currentMedia.uploaded_at).trim() : '');
        const isDifferent = currentVal !== initialVal;
        saveBtn.style.display = isDifferent ? 'block' : 'none';
    }

    updateSaveSourceButtonVisibility() {
        const input = this.el('source-input');
        const saveBtn = this.el('save-source-btn');
        if (!saveBtn) return;

        const currentVal = input ? input.value.trim() : '';
        const initialVal = (this.initialSourceValue !== undefined)
            ? this.initialSourceValue.trim()
            : ((this.currentMedia && this.currentMedia.source) ? this.currentMedia.source.trim() : '');
        const isDifferent = currentVal !== initialVal;
        saveBtn.style.display = isDifferent ? 'block' : 'none';
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
                    const albumMatch = window.location.pathname.match(/\/album\/(\d+)\/media\//);
                    const albumId = albumMatch ? albumMatch[1] : this.albumId;
                    const basePath = albumId ? `/album/${albumId}` : '/';
                    let targetUrl = `${basePath}${window.location.search || ''}`;

                    if (!window.location.search && document.referrer) {
                        try {
                            const refUrl = new URL(document.referrer);
                            if (refUrl.origin === window.location.origin && !refUrl.pathname.includes('/media/')) {
                                if (!albumId || refUrl.pathname === `/album/${albumId}`) {
                                    targetUrl = refUrl.pathname + refUrl.search;
                                }
                            }
                        } catch (e) { }
                    }
                    window.location.href = targetUrl;
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('media.errors.deleting_media'));
                }
            }
        });
        modal.show();
    }

    // Cleanup method
    destroy() {
        if (this._suggestedTagsRetryTimeout) {
            clearTimeout(this._suggestedTagsRetryTimeout);
            this._suggestedTagsRetryTimeout = null;
        }
        if (this._suggestedTagsAbort) {
            this._suggestedTagsAbort.abort();
            this._suggestedTagsAbort = null;
        }
        if (this.tooltipHelper) {
            this.tooltipHelper.destroy();
        }
        if (this.tagInputHelper) {
            this.tagInputHelper.destroy();
        }
        if (this._hierarchyReorder) {
            this._hierarchyReorder.deactivate();
        }
        this.unloadAllGifs();
    }

    unloadAllGifs() {
        if (window.unloadAllGifs) {
            window.unloadAllGifs(this.loadedGifs, this.el('related-media'));
        }
    }
}
