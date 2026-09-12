class BulkWDTaggerModal extends BulkTagModalBase {
    constructor(options = {}) {
        super({
            id: 'bulk-wd-tagger-modal',
            title: window.i18n.t('bulk_modal.wd_tagger.title'),
            classPrefix: 'bulk-wd-tagger',
            emptyMessage: window.i18n.t('bulk_modal.wd_tagger.empty_message'),
            closeOnOutsideClick: false,
            ...options
        });

        this.settings = {
            generalThreshold: 0.35,
            characterThreshold: 0.85,
            hideRatingTags: true,
            characterTagsFirst: true,
            modelName: 'wd-eva02-large-tagger-v3'
        };

        this.useStreaming = true;
        this.batchSize = 20;
        this.displayedMediaIds = new Set();
        this.init();
    }

    getStates() {
        return ['loading', 'content', 'empty', 'error', 'cancelled'];
    }

    getBodyHTML() {
        return `
            ${this.getLoadingHTML(window.i18n.t('bulk_modal.progress.initializing_tagger'))}
            ${this.getContentHTML()}
            ${this.getEmptyHTML()}
            ${this.getErrorHTML()}
            ${this.getCancelledHTML()}
        `;
    }

    getContentHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-content flex-1 flex flex-col min-h-0" style="display: none;">
                <p class="text-secondary mb-3 text-xs sm:text-sm flex-shrink-0">${window.i18n.t('bulk_modal.messages.review_tags')}</p>
                <div class="flex-1 overflow-y-auto -mx-4 px-4 pb-2 flex flex-col" style="overscroll-behavior: contain;">
                    <div class="${prefix}-items space-y-3"></div>
                    <div class="${prefix}-scan-loading flex flex-col items-center justify-center py-8" style="display: none;">
                        <div class="spinner"></div>
                        <p class="text-secondary mt-2 ${prefix}-scan-status text-center">${window.i18n.t('bulk_modal.progress.predicting_tags')}</p>
                        <p class="text-secondary text-sm text-center">
                            <span class="${prefix}-scan-progress">0</span> / <span class="${prefix}-scan-total">0</span> <span class="${prefix}-scan-phase">${window.i18n.t('bulk_modal.progress.items_processed')}</span>
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    updateScanProgress(current, total, status, phase) {
        const prefix = this.options.classPrefix;
        const loadingEl = this.modalElement?.querySelector(`.${prefix}-scan-loading`);
        const progressEl = this.modalElement?.querySelector(`.${prefix}-scan-progress`);
        const totalEl = this.modalElement?.querySelector(`.${prefix}-scan-total`);
        const statusEl = this.modalElement?.querySelector(`.${prefix}-scan-status`);
        const phaseEl = this.modalElement?.querySelector(`.${prefix}-scan-phase`);

        if (loadingEl) loadingEl.style.display = 'flex';
        if (progressEl) progressEl.textContent = current;
        if (totalEl) totalEl.textContent = total;
        if (statusEl && status) statusEl.textContent = status;
        if (phaseEl && phase) phaseEl.textContent = phase;
    }

    hideScanProgress() {
        const prefix = this.options.classPrefix;
        const loadingEl = this.modalElement?.querySelector(`.${prefix}-scan-loading`);
        if (loadingEl) loadingEl.style.display = 'none';
    }

    reset() {
        super.reset();
        this.displayedMediaIds = new Set();
        this.hideScanProgress();
    }

    async show(selectedItems) {
        if (!this.modalElement) {
            this.init();
        }

        this.selectedItems = new Set(selectedItems);
        this.reset();
        this.isCancelled = false;
        this.abortController = new AbortController();

        // Keep bulk modal hidden while checking or downloading model
        this.modalElement.style.display = 'none';
        this.isVisible = false;

        await this.loadAdminSettings();

        const downloadModal = new ModelDownloadModal({
            onCancel: () => this.cancel()
        });

        const isReady = await downloadModal.ensureModelReady(this.settings.modelName);
        if (this.isCancelled || !isReady) {
            this.cancel();
            return this;
        }

        // Model is ready, now display the bulk modal
        this.modalElement.style.display = 'flex';
        this.isVisible = true;
        document.body.style.overflow = 'hidden';
        document.documentElement.style.overflow = 'hidden';

        this.showState('loading');
        await this.fetchTags();

        return this;
    }

    async loadAdminSettings() {
        try {
            const res = await fetch('/api/ai-tagger/settings');
            if (res.ok) {
                const data = await res.json();
                if (data.general_threshold != null) this.settings.generalThreshold = data.general_threshold;
                if (data.character_threshold != null) this.settings.characterThreshold = data.character_threshold;
                if (data.model_name) this.settings.modelName = data.model_name;
            }
        } catch (e) {
            // Non-fatal, keep current defaults
        }
    }

    async fetchTags() {
        if (this.isCancelled) return;

        this.showState('loading');
        this.displayedMediaIds = new Set();

        const selectedArray = Array.from(this.selectedItems);

        // Phase 1: Fetch media info in concurrent chunks
        const mediaInfoMap = new Map();
        try {
            const batchItems = await this.fetchMediaInChunks(selectedArray, {
                chunkSize: 50,
                concurrency: 3,
                projection: 'tags_only',
                statusText: window.i18n.t('bulk_modal.progress.fetching_media'),
                phaseText: window.i18n.t('bulk_modal.progress.items_fetched')
            });
            if (batchItems) {
                batchItems.forEach(item => mediaInfoMap.set(item.id, item));
            }
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error fetching media info batch:', e);
            this.showError(window.i18n.t('bulk_modal.messages.error_occurred'));
            return;
        }

        if (this.isCancelled) return;

        // Switch to content view and show the live scan progress indicator
        this.showState('content');
        this.updateScanProgress(
            0,
            selectedArray.length,
            window.i18n.t('bulk_modal.progress.predicting_tags'),
            window.i18n.t('bulk_modal.progress.items_processed')
        );

        // Phase 2: Predict tags
        if (this.useStreaming) {
            try {
                await this.predictWithStreaming(selectedArray, mediaInfoMap);
            } catch (e) {
                if (this.isCancelled || e.name === 'AbortError') return;
                console.warn('Streaming failed, falling back to batch:', e);
                // Fallback to batch
                await this.predictWithBatching(selectedArray, mediaInfoMap);
            }
        } else {
            await this.predictWithBatching(selectedArray, mediaInfoMap);
        }
    }

    parseSSEEvents(buffer) {
        const events = [];
        const normalized = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

        const parts = normalized.split('\n\n');
        const remaining = parts.pop() || '';

        for (const block of parts) {
            for (const line of block.split('\n')) {
                const trimmed = line.trim();
                if (trimmed.startsWith('data:')) {
                    const jsonStr = trimmed.slice(5).trim();
                    try {
                        events.push(JSON.parse(jsonStr));
                    } catch (e) {
                        console.warn('Failed to parse SSE JSON:', jsonStr, e);
                    }
                }
            }
        }

        return { events, remaining };
    }

    async predictWithStreaming(mediaIds, mediaInfoMap) {
        this.updateScanProgress(
            0,
            mediaIds.length,
            window.i18n.t('bulk_modal.progress.predicting_tags'),
            window.i18n.t('bulk_modal.progress.items_processed')
        );

        const response = await fetch('/api/ai-tagger/predict-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                media_ids: mediaIds,
                general_threshold: this.settings.generalThreshold,
                character_threshold: this.settings.characterThreshold,
                hide_rating_tags: this.settings.hideRatingTags,
                character_tags_first: this.settings.characterTagsFirst,
                model_name: this.settings.modelName
            }),
            signal: this.abortController?.signal
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Stream request failed');
        }

        const reader = response.body.getReader();
        this.activeReader = reader;
        const decoder = new TextDecoder();
        let buffer = '';

        try {
            while (true) {
                if (this.isCancelled) {
                    try { await reader.cancel(); } catch (e) { }
                    break;
                }

                let done, value;
                try {
                    const res = await reader.read();
                    done = res.done;
                    value = res.value;
                } catch (e) {
                    break;
                }

                if (done) {
                    // Process any remaining buffer
                    if (buffer.trim()) {
                        const { events } = this.parseSSEEvents(buffer + '\n\n');
                        for (const data of events) {
                            if (this.isCancelled) break;
                            await this.handleStreamEvent(data, mediaInfoMap);
                        }
                    }
                    break;
                }

                buffer += decoder.decode(value, { stream: true });

                // Parse complete events from buffer
                const { events, remaining } = this.parseSSEEvents(buffer);
                buffer = remaining;

                for (const data of events) {
                    if (this.isCancelled) break;

                    const shouldStop = await this.handleStreamEvent(data, mediaInfoMap);
                    if (shouldStop) break;
                }
            }
        } finally {
            this.activeReader = null;
        }

        this.finalizeScanning();
    }

    async handleStreamEvent(data, mediaInfoMap) {
        if (data.type === 'complete') {
            return true; // Signal to stop
        }

        if (data.type === 'error' && data.error && !data.media_id) {
            // Global error
            throw new Error(data.error);
        }

        if (data.type === 'result' && data.media_id != null) {
            const mediaIdStr = String(data.media_id);
            if (!this.displayedMediaIds.has(mediaIdStr)) {
                this.displayedMediaIds.add(mediaIdStr);
                const mediaData = mediaInfoMap.get(data.media_id) || mediaInfoMap.get(parseInt(data.media_id)) || mediaInfoMap.get(mediaIdStr);
                await this.processAndDisplayScannedItem(data.media_id, data.tags || [], mediaData);
            }

            if (data.progress != null && data.total != null) {
                this.updateScanProgress(
                    data.progress,
                    data.total,
                    window.i18n.t('bulk_modal.progress.predicting_tags'),
                    window.i18n.t('bulk_modal.progress.items_processed')
                );
            }
        } else if (data.type === 'error' && data.media_id != null) {
            if (data.progress != null && data.total != null) {
                this.updateScanProgress(
                    data.progress,
                    data.total,
                    window.i18n.t('bulk_modal.progress.predicting_tags'),
                    window.i18n.t('bulk_modal.progress.items_processed')
                );
            }
        }

        return false;
    }

    async processAndDisplayScannedItem(mediaId, rawTags, mediaData) {
        if (this.isCancelled) return;

        const currentTags = (mediaData?.tags || []).map(t => (t.name || t).toLowerCase());
        const currentTagsSet = new Set(currentTags);

        const predictedTags = (rawTags || [])
            .map(t => (t.name || t).replace(/ /g, '_'))
            .filter(t => !currentTagsSet.has(t.toLowerCase()));

        if (predictedTags.length === 0) return;

        // Validate any un-cached tags immediately
        const unvalidatedTags = predictedTags.filter(t => !this.tagResolutionCache.has(t.toLowerCase().trim()));
        if (unvalidatedTags.length > 0) {
            try {
                await this.validateTags(unvalidatedTags, 2, false);
            } catch (e) {
                if (e.name === 'AbortError' || this.isCancelled) return;
                console.error('Error validating tags for item:', e);
            }
        }

        if (this.isCancelled) return;

        // Filter and map to resolved tags
        const validNewTags = [];
        const seen = new Set();
        for (const tag of predictedTags) {
            const rawResolved = this.getResolvedTag(tag);
            const resolved = typeof rawResolved === 'object' && rawResolved !== null ? rawResolved.name : rawResolved;
            if (resolved && typeof resolved === 'string' && !seen.has(resolved.toLowerCase()) && !currentTagsSet.has(resolved.toLowerCase())) {
                validNewTags.push(resolved);
                seen.add(resolved.toLowerCase());
            }
        }

        if (validNewTags.length === 0) return;

        const item = {
            mediaId,
            currentTags: (mediaData?.tags || []).map(t => t.name || t),
            predictedTags,
            newTags: validNewTags,
            filename: mediaData?.filename || window.i18n.t('bulk_modal.ai_tags.default_media_name', { id: mediaId })
        };

        const prefix = this.options.classPrefix;
        const itemsContainer = this.modalElement.querySelector(`.${prefix}-items`);

        const index = this.itemsData.length;
        this.itemsData.push(item);

        if (itemsContainer) {
            const itemHTML = this.renderItem(item, index);
            itemsContainer.insertAdjacentHTML('beforeend', itemHTML);

            await new Promise(resolve => setTimeout(resolve, 0));
        }

        this.showSaveButton();
    }

    async predictWithBatching(mediaIds, mediaInfoMap) {
        this.updateScanProgress(
            0,
            mediaIds.length,
            window.i18n.t('bulk_modal.progress.predicting_tags'),
            window.i18n.t('bulk_modal.progress.items_processed')
        );

        let processed = 0;

        for (let i = 0; i < mediaIds.length; i += this.batchSize) {
            if (this.isCancelled) break;

            const batchIds = mediaIds.slice(i, i + this.batchSize);

            try {
                const response = await this.fetchWithAbort('/api/ai-tagger/predict-batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        media_ids: batchIds,
                        general_threshold: this.settings.generalThreshold,
                        character_threshold: this.settings.characterThreshold,
                        hide_rating_tags: this.settings.hideRatingTags,
                        character_tags_first: this.settings.characterTagsFirst,
                        model_name: this.settings.modelName
                    })
                });

                if (!response.ok) {
                    const error = await response.json().catch(() => ({}));
                    throw new Error(error.detail || 'Batch prediction failed');
                }

                const batchResult = await response.json();

                for (const result of batchResult.results) {
                    if (this.isCancelled) break;
                    if (!this.displayedMediaIds.has(result.media_id)) {
                        this.displayedMediaIds.add(result.media_id);
                        const mediaData = mediaInfoMap.get(result.media_id);
                        await this.processAndDisplayScannedItem(result.media_id, result.tags || [], mediaData);
                    }
                }

                processed += batchIds.length;
                this.updateScanProgress(
                    processed,
                    mediaIds.length,
                    window.i18n.t('bulk_modal.progress.predicting_tags'),
                    window.i18n.t('bulk_modal.progress.items_processed')
                );

            } catch (e) {
                if (e.name === 'AbortError') return;
                console.error('Batch prediction error:', e);
                processed += batchIds.length;
                this.updateScanProgress(
                    processed,
                    mediaIds.length,
                    window.i18n.t('bulk_modal.progress.predicting_tags'),
                    window.i18n.t('bulk_modal.progress.items_processed')
                );
            }
        }

        this.finalizeScanning();
    }

    finalizeScanning() {
        if (this.isCancelled) return;

        this.hideScanProgress();

        if (this.itemsData.length === 0) {
            this.showState('empty');
        } else {
            this.showState('content');
            this.showSaveButton();
        }
    }

    async refreshSingleItem(index, inputElement) {
        const item = this.itemsData[index];
        if (!item || this.isCancelled) return;

        inputElement.style.opacity = '0.5';

        try {
            const mediaRes = await this.fetchWithAbort(`/api/media/${item.mediaId}`);
            const mediaData = mediaRes.ok ? await mediaRes.json() : { tags: [] };

            const response = await this.fetchWithAbort(`/api/ai-tagger/predict/${item.mediaId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    general_threshold: this.settings.generalThreshold,
                    character_threshold: this.settings.characterThreshold,
                    hide_rating_tags: this.settings.hideRatingTags,
                    character_tags_first: this.settings.characterTagsFirst,
                    model_name: this.settings.modelName
                })
            });

            if (!response.ok) {
                throw new Error('Prediction failed');
            }

            const result = await response.json();
            const currentTagsSet = new Set((mediaData?.tags || []).map(t => (t.name || t).toLowerCase()));

            const newPredictions = (result.tags || [])
                .map(t => (t.name || t).replace(/ /g, '_'))
                .filter(t => !currentTagsSet.has(t.toLowerCase()));

            if (newPredictions.length > 0) {
                // Validate new tags
                const unvalidated = newPredictions.filter(t => !this.tagResolutionCache.has(t.toLowerCase().trim()));
                if (unvalidated.length > 0) {
                    await this.validateTags(unvalidated, 20, false);
                }

                const validTags = newPredictions.filter(tag => {
                    const resolved = this.getResolvedTag(tag);
                    return resolved !== null && resolved !== undefined;
                }).map(tag => {
                    const rawResolved = this.getResolvedTag(tag);
                    const resolved = typeof rawResolved === 'object' && rawResolved !== null ? rawResolved.name : rawResolved;
                    return resolved || tag;
                });

                if (validTags.length > 0) {
                    const existingTags = this.tagInputHelper
                        ? this.tagInputHelper.getValidTagsFromInput(inputElement)
                        : inputElement.textContent.trim().split(/\s+/).filter(t => t);

                    const existingSet = new Set(existingTags.map(t => t.toLowerCase()));
                    const toAdd = validTags.filter(t => !existingSet.has(t.toLowerCase()));

                    if (toAdd.length > 0) {
                        const newValue = [...existingTags, ...toAdd].join(' ');
                        inputElement.textContent = newValue;
                        this.triggerValidation(inputElement);
                    } else {
                        this.flashButton(index, 'var(--warning)');
                    }
                } else {
                    this.flashButton(index, 'var(--danger)');
                }
            } else {
                this.flashButton(index, 'var(--danger)');
            }
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error(e);
            this.flashButton(index, 'var(--danger)');
        } finally {
            inputElement.style.opacity = '1';
        }
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkWDTaggerModal;
}
