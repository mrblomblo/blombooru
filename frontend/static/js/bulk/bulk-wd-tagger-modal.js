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
        this.processedMediaIds = new Set();
        this.failedMediaIds = new Set();
        this.totalCount = 0;
        this.processedCount = 0;
        this.isScanningComplete = false;
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
                <div class="${prefix}-top-bar flex flex-col gap-2 mb-3 pb-2.5 border-b border-color shrink-0">
                    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 shrink-0">
                        <p class="text-secondary text-xs sm:text-sm">${window.i18n.t('bulk_modal.messages.review_tags')}</p>
                        ${this.getHideImpliedCheckboxHTML()}
                    </div>
                    <div class="${prefix}-progress-counter flex items-center flex-wrap gap-x-3 gap-y-1 text-xs sm:text-sm" style="display: none;">
                        <span class="${prefix}-progress-status-wrapper flex items-center gap-1.5 text-secondary">
                            <span class="spinner ${prefix}-progress-spinner" style="width: 14px; height: 14px; border-width: 2px; margin: 0; display: none;"></span>
                            <span class="${prefix}-progress-status-text"></span>
                        </span>
                        <span class="${prefix}-progress-count text-secondary"></span>
                        <span class="${prefix}-progress-tagged text-primary"></span>
                        <span class="${prefix}-progress-skipped text-secondary"></span>
                        <span class="${prefix}-progress-failed text-danger" style="display: none;"></span>
                    </div>
                </div>
                <div class="flex-1 overflow-y-auto -mx-4 px-4 pb-2 flex flex-col" style="overscroll-behavior: contain;">
                    <div class="${prefix}-items space-y-3"></div>
                </div>
            </div>
        `;
    }

    updateScanProgress(current, total, status) {
        this.updateProgressCounters(current, total, status, false);
    }

    updateProgressCounters(current, total, status, isComplete = false) {
        if (current != null) this.processedCount = current;
        if (total != null) this.totalCount = total;
        if (isComplete) this.isScanningComplete = true;

        const processed = this.processedCount || 0;
        const totalItems = this.totalCount || 0;
        const tagged = this.itemsData ? this.itemsData.length : 0;
        const failed = this.failedMediaIds ? this.failedMediaIds.size : 0;
        const skipped = Math.max(0, processed - tagged - failed);

        const prefix = this.options.classPrefix;
        if (!this.modalElement) return;

        const taggedText = window.i18n.t('bulk_modal.progress.tagged', { count: tagged });
        const skippedText = window.i18n.t('bulk_modal.progress.skipped', { count: skipped });
        const failedText = window.i18n.t('upload.progress.failed', { count: failed });
        const processedText = window.i18n.t('bulk_modal.progress.items_processed', {
            scannedMedia: processed,
            totalMedia: totalItems
        });

        // Update tagging progress
        const progressCounter = this.modalElement.querySelector(`.${prefix}-progress-counter`);
        const progressSpinner = this.modalElement.querySelector(`.${prefix}-progress-spinner`);
        const progressCheck = this.modalElement.querySelector(`.${prefix}-progress-check`);
        const progressStatusText = this.modalElement.querySelector(`.${prefix}-progress-status-text`);
        const progressCount = this.modalElement.querySelector(`.${prefix}-progress-count`);
        const progressTagged = this.modalElement.querySelector(`.${prefix}-progress-tagged`);
        const progressSkipped = this.modalElement.querySelector(`.${prefix}-progress-skipped`);
        const progressFailed = this.modalElement.querySelector(`.${prefix}-progress-failed`);

        if (progressCounter) progressCounter.style.display = 'flex';
        if (progressTagged) progressTagged.textContent = taggedText;
        if (progressSkipped) progressSkipped.textContent = skippedText;
        if (progressFailed) {
            progressFailed.textContent = failedText;
            progressFailed.style.display = failed > 0 ? 'inline' : 'none';
        }
        if (progressCount) progressCount.textContent = processedText;

        if (this.isScanningComplete) {
            if (progressSpinner) progressSpinner.style.display = 'none';
            if (progressCheck) progressCheck.style.display = 'inline-block';
            if (progressStatusText) progressStatusText.textContent = window.i18n.t('bulk_modal.progress.tagging_complete');
        } else {
            if (progressCheck) progressCheck.style.display = 'none';
            if (progressSpinner) {
                progressSpinner.style.display = status === null ? 'none' : 'inline-block';
            }
            if (progressStatusText) {
                progressStatusText.textContent = status || window.i18n.t('bulk_modal.progress.predicting_tags');
            }
        }
    }

    reset() {
        super.reset();
        this.displayedMediaIds = new Set();
        this.processedMediaIds = new Set();
        this.failedMediaIds = new Set();
        this.processedCount = 0;
        this.totalCount = 0;
        this.isScanningComplete = false;
        const prefix = this.options.classPrefix;
        const progressCounter = this.modalElement?.querySelector(`.${prefix}-progress-counter`);
        if (progressCounter) progressCounter.style.display = 'none';
    }

    async show(selectedItems) {
        if (!this.modalElement) {
            this.init();
        }

        this.selectedItems = new Set(selectedItems);
        this.reset();
        this.totalCount = this.selectedItems.size;
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
            window.i18n.t('bulk_modal.progress.predicting_tags')
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
            window.i18n.t('bulk_modal.progress.predicting_tags')
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
        let streamCompleted = false;
        let streamError = null;

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
                    streamError = e;
                    break;
                }

                if (done) {
                    // Process any remaining buffer
                    if (buffer.trim()) {
                        const { events } = this.parseSSEEvents(buffer + '\n\n');
                        for (const data of events) {
                            if (this.isCancelled) break;
                            const shouldStop = await this.handleStreamEvent(data, mediaInfoMap);
                            if (shouldStop) {
                                streamCompleted = true;
                                break;
                            }
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
                    if (shouldStop) {
                        streamCompleted = true;
                        break;
                    }
                }

                if (streamCompleted) break;
            }
        } finally {
            this.activeReader = null;
        }

        const isSuccess = streamCompleted || (this.processedMediaIds.size >= this.totalCount && !streamError);
        this.finalizeScanning(isSuccess);
    }

    async handleStreamEvent(data, mediaInfoMap) {
        if (data.type === 'complete') {
            return true; // Signal to stop
        }

        if (data.type === 'error' && data.error && !data.media_id) {
            // Global error
            throw new Error(data.error);
        }

        if (data.media_id != null) {
            const mediaIdStr = String(data.media_id);
            this.processedMediaIds.add(mediaIdStr);

            if (data.type === 'error') {
                this.failedMediaIds.add(mediaIdStr);
            } else if (data.type === 'result') {
                if (!this.displayedMediaIds.has(mediaIdStr)) {
                    this.displayedMediaIds.add(mediaIdStr);
                    const mediaData = mediaInfoMap.get(data.media_id) || mediaInfoMap.get(parseInt(data.media_id)) || mediaInfoMap.get(mediaIdStr);
                    await this.processAndDisplayScannedItem(data.media_id, data.tags || [], mediaData);
                }
            }

            this.updateScanProgress(
                this.processedMediaIds.size,
                this.totalCount,
                window.i18n.t('bulk_modal.progress.predicting_tags')
            );
        }

        return false;
    }

    async processAndDisplayScannedItem(mediaId, rawTags, mediaData) {
        if (this.isCancelled) return;

        const currentTags = (mediaData?.tags || []).map(t => (typeof t === 'object' && t !== null ? t.name : t));
        const predictedTags = (rawTags || []).map(t => (typeof t === 'object' && t !== null ? t.name : t).replace(/ /g, '_'));

        let resolvedResults = {};
        try {
            resolvedResults = await this.resolveCombinedTagsBatch([{
                id: mediaId,
                current_tags: currentTags,
                new_tags: predictedTags
            }]);
        } catch (e) {
            if (e.name === 'AbortError' || this.isCancelled) return;
            console.error('Error resolving combined tags for item:', e);
        }

        if (this.isCancelled) return;

        const res = resolvedResults[mediaId] || resolvedResults[String(mediaId)];
        if (!res || !res.added_tags || res.added_tags.length === 0) return;

        const item = this.initItemImplicationState({
            mediaId,
            currentTags: res.current_tags || [],
            predictedTags,
            newTags: res.new_tags || [],
            prefilledTags: res.added_tags || [],
            filename: mediaData?.filename || window.i18n.t('bulk_modal.ai_tags.default_media_name', { id: mediaId })
        }, mediaData?.tags || [], res.implied_by || {});

        const prefix = this.options.classPrefix;
        const itemsContainer = this.modalElement.querySelector(`.${prefix}-items`);

        const index = this.itemsData.length;
        this.itemsData.push(item);

        if (itemsContainer) {
            const itemHTML = this.renderItem(item, index);
            itemsContainer.insertAdjacentHTML('beforeend', itemHTML);

            await new Promise(resolve => setTimeout(resolve, 0));
        }

        this.updateProgressCounters();
        this.showSaveButton();
    }

    async predictWithBatching(mediaIds, mediaInfoMap) {
        this.updateScanProgress(
            this.processedMediaIds.size,
            this.totalCount,
            window.i18n.t('bulk_modal.progress.predicting_tags')
        );

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
                const resultsMap = new Map();
                for (const res of (batchResult.results || [])) {
                    resultsMap.set(String(res.media_id), res);
                }
                const failedSet = new Set((batchResult.failed_ids || []).map(String));

                for (const mid of batchIds) {
                    if (this.isCancelled) break;
                    const midStr = String(mid);
                    this.processedMediaIds.add(midStr);

                    if (failedSet.has(midStr)) {
                        this.failedMediaIds.add(midStr);
                    } else if (resultsMap.has(midStr)) {
                        const result = resultsMap.get(midStr);
                        if (!this.displayedMediaIds.has(midStr)) {
                            this.displayedMediaIds.add(midStr);
                            const mediaData = mediaInfoMap.get(mid) || mediaInfoMap.get(parseInt(mid)) || mediaInfoMap.get(midStr);
                            await this.processAndDisplayScannedItem(mid, result.tags || [], mediaData);
                        }
                    }

                    this.updateScanProgress(
                        this.processedMediaIds.size,
                        this.totalCount,
                        window.i18n.t('bulk_modal.progress.predicting_tags')
                    );
                }

            } catch (e) {
                if (e.name === 'AbortError') return;
                console.error('Batch prediction error:', e);
                for (const mid of batchIds) {
                    const midStr = String(mid);
                    this.processedMediaIds.add(midStr);
                    this.failedMediaIds.add(midStr);
                }
                this.updateScanProgress(
                    this.processedMediaIds.size,
                    this.totalCount,
                    window.i18n.t('bulk_modal.progress.predicting_tags')
                );
            }
        }

        const isSuccess = this.processedMediaIds.size >= this.totalCount;
        this.finalizeScanning(isSuccess);
    }

    finalizeScanning(isSuccess = true) {
        if (this.isCancelled) return;

        if (isSuccess) {
            this.updateProgressCounters(this.totalCount, this.totalCount, null, true);
        } else {
            this.updateProgressCounters(
                this.processedMediaIds.size,
                this.totalCount,
                window.i18n.t('bulk_modal.messages.error_occurred'),
                false
            );
            const prefix = this.options.classPrefix;
            const progressSpinner = this.modalElement?.querySelector(`.${prefix}-progress-spinner`);
            if (progressSpinner) progressSpinner.style.display = 'none';
        }

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
            const currentTags = (mediaData?.tags || []).map(t => (typeof t === 'object' && t !== null ? t.name : t));
            const predictedTags = (result.tags || []).map(t => (typeof t === 'object' && t !== null ? t.name : t).replace(/ /g, '_'));

            const resolvedResults = await this.resolveCombinedTagsBatch([{
                id: item.mediaId,
                current_tags: currentTags,
                new_tags: predictedTags
            }]);

            const res = resolvedResults[item.mediaId] || resolvedResults[String(item.mediaId)];
            if (res && res.added_tags && res.added_tags.length > 0) {
                item.currentTags = res.current_tags || [];
                item.newTags = res.new_tags || [];
                item.prefilledTags = res.added_tags || [];
                item.impliedTagsMap = new Map();
                item.hiddenImpliedTags = new Set();
                item.expandedTriggers = new Set();
                this.initItemImplicationState(item, mediaData?.tags || [], res.implied_by || {});

                inputElement.textContent = (item.newTags || []).join(' ');
                this.triggerValidation(inputElement);
                this.flashButton(index, 'var(--success)');
            } else {
                this.flashButton(index, 'var(--warning)');
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
