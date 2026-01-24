class BulkWDTaggerModal extends BulkTagModalBase {
    constructor(options = {}) {
        super({
            id: 'bulk-wd-tagger-modal',
            title: 'Bulk AI Tag Prediction (WD Tagger)',
            classPrefix: 'bulk-wd-tagger',
            emptyMessage: 'No new tags could be predicted for the selected items.',
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
        this.init();
    }

    getStates() {
        return ['loading', 'content', 'empty', 'error', 'cancelled', 'download-confirm', 'downloading'];
    }

    getBodyHTML() {
        return `
            ${this.getSettingsHTML()}
            ${this.getDownloadConfirmHTML()}
            ${this.getDownloadingHTML()}
            ${this.getLoadingHTML('Initializing AI Tagger...')}
            ${this.getContentHTML()}
            ${this.getEmptyHTML()}
            ${this.getErrorHTML()}
            ${this.getCancelledHTML()}
        `;
    }

    getSettingsHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-settings mb-4 p-3 surface-light border text-sm" style="display: none;">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs text-secondary mb-1">General Confidence Threshold</label>
                        <input type="number" class="wd-general-threshold w-full px-2 py-1 border surface text-sm" 
                               min="0" max="1" step="0.05" value="${this.settings.generalThreshold}">
                    </div>
                    <div>
                        <label class="block text-xs text-secondary mb-1">Character Confidence Threshold</label>
                        <input type="number" class="wd-character-threshold w-full px-2 py-1 border surface text-sm" 
                               min="0" max="1" step="0.05" value="${this.settings.characterThreshold}">
                    </div>
                </div>
            </div>
        `;
    }

    getDownloadConfirmHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-download-confirm text-center py-8" style="display: none;">
                <div class="mb-4">
                    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mx-auto text-warning">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                </div>
                <p class="text-secondary mb-2">The AI model needs to be downloaded first.</p>
                <p class="text-secondary text-sm mb-4">
                    Model: <strong class="download-model-name">${this.settings.modelName}</strong><br>
                    Size: approximately <strong class="download-model-size">~850 MB</strong>
                </p>
                <div class="flex justify-center gap-2">
                    <button class="${prefix}-download-cancel px-4 py-2 surface-light text text-sm">
                        Cancel
                    </button>
                    <button class="${prefix}-download-confirm-btn px-4 py-2 bg-primary tag-text text-sm">
                        Download & Continue
                    </button>
                </div>
            </div>
        `;
    }

    getDownloadingHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-downloading text-center py-8" style="display: none;">
                <div class="mb-4">
                    <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent"></div>
                </div>
                <p class="text-secondary mb-2">Downloading AI model...</p>
                <p class="text-secondary text-sm">This may take a few minutes depending on your connection.</p>
                <p class="text-secondary text-xs mt-2">Model files are cached locally for future use.</p>
            </div>
        `;
    }

    getFooterLeftHTML() {
        const prefix = this.options.classPrefix;
        return `
            <button class="${prefix}-toggle-settings px-3 py-2 surface-light text text-sm">
                Settings
            </button>
        `;
    }

    setupAdditionalEventListeners() {
        const prefix = this.options.classPrefix;

        // Settings toggle
        const toggleSettings = this.modalElement.querySelector(`.${prefix}-toggle-settings`);
        if (toggleSettings) {
            toggleSettings.addEventListener('click', () => {
                const settings = this.modalElement.querySelector(`.${prefix}-settings`);
                if (settings) {
                    settings.style.display = settings.style.display === 'none' ? 'block' : 'none';
                }
            });
        }

        // Download buttons
        const downloadCancelBtn = this.modalElement.querySelector(`.${prefix}-download-cancel`);
        if (downloadCancelBtn) {
            downloadCancelBtn.addEventListener('click', () => this.cancel());
        }

        const downloadConfirmBtn = this.modalElement.querySelector(`.${prefix}-download-confirm-btn`);
        if (downloadConfirmBtn) {
            downloadConfirmBtn.addEventListener('click', () => this.downloadModelAndContinue());
        }

        // Settings inputs
        const generalThreshold = this.modalElement.querySelector('.wd-general-threshold');
        if (generalThreshold) {
            generalThreshold.addEventListener('change', (e) => {
                this.settings.generalThreshold = parseFloat(e.target.value);
            });
        }

        const characterThreshold = this.modalElement.querySelector('.wd-character-threshold');
        if (characterThreshold) {
            characterThreshold.addEventListener('change', (e) => {
                this.settings.characterThreshold = parseFloat(e.target.value);
            });
        }
    }

    reset() {
        super.reset();
        const prefix = this.options.classPrefix;
        const settings = this.modalElement.querySelector(`.${prefix}-settings`);
        if (settings) settings.style.display = 'none';
    }

    async onShow() {
        await this.checkModelAndStart();
    }

    async checkModelAndStart() {
        this.showState('loading');
        this.updateProgress(0, 0, 'Checking AI model status...', '');

        try {
            const response = await this.fetchWithAbort(`/api/ai-tagger/model-status/${this.settings.modelName}`);

            if (this.isCancelled) return;

            if (!response.ok) {
                throw new Error('Failed to check model status');
            }

            const status = await response.json();

            if (status.is_downloaded || status.is_loaded) {
                await this.fetchTags();
            } else {
                const modelNameEl = this.modalElement.querySelector('.download-model-name');
                const modelSizeEl = this.modalElement.querySelector('.download-model-size');

                if (modelNameEl) modelNameEl.textContent = this.settings.modelName;
                if (modelSizeEl) modelSizeEl.textContent = status.download_size_mb
                    ? `~${status.download_size_mb} MB`
                    : 'Unknown';

                this.showState('download-confirm');
            }
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error checking model status:', e);
            this.showError(`Failed to check model status: ${e.message}`);
        }
    }

    async downloadModelAndContinue() {
        this.showState('downloading');

        try {
            const response = await this.fetchWithAbort(`/api/ai-tagger/download/${this.settings.modelName}`, {
                method: 'POST'
            });

            if (this.isCancelled) return;

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || 'Download failed');
            }

            await this.fetchTags();
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error downloading model:', e);
            this.showError(`Failed to download model: ${e.message}`);
        }
    }

    async fetchTags() {
        if (this.isCancelled) return;

        this.showState('loading');
        const prefix = this.options.classPrefix;
        const itemsContainer = this.modalElement.querySelector(`.${prefix}-items`);

        const selectedArray = Array.from(this.selectedItems);

        // Phase 1: Fetch media info in batch
        const mediaInfoMap = new Map();
        this.updateProgress(0, selectedArray.length, 'Fetching media info...', 'items fetched');

        try {
            const idsParam = selectedArray.join(',');
            const res = await this.fetchWithAbort(`/api/media/batch?ids=${idsParam}`);
            if (res.ok) {
                const data = await res.json();
                if (data.items) {
                    data.items.forEach(item => mediaInfoMap.set(item.id, item));
                }
            } else {
                throw new Error('Failed to fetch media info batch');
            }
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error fetching media info batch:', e);
            // Fallback to individual fetching if batch fails
            let fetchProgress = 0;
            const fetchMediaInfo = async (mediaId) => {
                if (this.isCancelled) return;
                try {
                    const res = await this.fetchWithAbort(`/api/media/${mediaId}`);
                    if (res.ok) {
                        const data = await res.json();
                        mediaInfoMap.set(mediaId, data);
                    }
                } catch (err) {
                    console.error(`Error fetching media ${mediaId}:`, err);
                } finally {
                    fetchProgress++;
                    if (!this.isCancelled) {
                        this.updateProgress(fetchProgress, selectedArray.length, 'Fetching media info...', 'items fetched');
                    }
                }
            };
            await this.processBatch(selectedArray, fetchMediaInfo, 20);
        }

        if (this.isCancelled) return;

        // Phase 2: Predict tags
        if (this.useStreaming) {
            try {
                await this.predictWithStreaming(selectedArray, mediaInfoMap);
            } catch (e) {
                if (e.name === 'AbortError') return;
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
        let remaining = buffer;

        // SSE events are separated by double newlines
        let idx;
        while ((idx = remaining.indexOf('\n\n')) !== -1) {
            const eventText = remaining.slice(0, idx);
            remaining = remaining.slice(idx + 2);

            // Parse the event
            for (const line of eventText.split('\n')) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.slice(6);
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
        this.updateProgress(0, mediaIds.length, 'Predicting tags with AI...', 'items processed');

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
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            if (this.isCancelled) break;

            const { done, value } = await reader.read();

            if (done) {
                // Process any remaining buffer
                if (buffer.trim()) {
                    const { events } = this.parseSSEEvents(buffer + '\n\n');
                    for (const data of events) {
                        this.handleStreamEvent(data, mediaInfoMap);
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

                const shouldStop = this.handleStreamEvent(data, mediaInfoMap);
                if (shouldStop) break;
            }
        }

        await this.finalizeResults();
    }

    handleStreamEvent(data, mediaInfoMap) {
        if (data.type === 'complete') {
            return true; // Signal to stop
        }

        if (data.type === 'error' && data.error && !data.media_id) {
            // Global error
            throw new Error(data.error);
        }

        if (data.type === 'result' && data.media_id != null) {
            const mediaData = mediaInfoMap.get(data.media_id);
            const result = this.processStreamedResult(data, mediaData);

            if (result) {
                this.itemsData.push(result);
            }

            if (data.progress != null && data.total != null) {
                this.updateProgress(
                    data.progress,
                    data.total,
                    'Predicting tags with AI...',
                    'items processed'
                );
            }
        }

        return false;
    }

    async predictWithBatching(mediaIds, mediaInfoMap) {
        this.updateProgress(0, mediaIds.length, 'Predicting tags with AI...', 'items processed');

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
                    const mediaData = mediaInfoMap.get(result.media_id);
                    const processedResult = this.processBatchResult(result, mediaData);

                    if (processedResult) {
                        this.itemsData.push(processedResult);
                    }
                }

                processed += batchIds.length;
                this.updateProgress(
                    processed,
                    mediaIds.length,
                    'Predicting tags with AI...',
                    'items processed'
                );

            } catch (e) {
                if (e.name === 'AbortError') return;
                console.error('Batch prediction error:', e);
                processed += batchIds.length;
                // Continue with next batch
            }
        }

        await this.finalizeResults();
    }

    processStreamedResult(data, mediaData) {
        const currentTags = (mediaData?.tags || []).map(t => (t.name || t).toLowerCase());
        const currentTagsSet = new Set(currentTags);

        const predictedTags = data.tags
            .map(t => t.name.replace(/ /g, '_'))
            .filter(t => !currentTagsSet.has(t.toLowerCase()));

        if (predictedTags.length > 0) {
            return {
                mediaId: data.media_id,
                currentTags: (mediaData?.tags || []).map(t => t.name || t),
                predictedTags,
                filename: mediaData?.filename || `Media ${data.media_id}`
            };
        }
        return null;
    }

    processBatchResult(result, mediaData) {
        const currentTags = (mediaData?.tags || []).map(t => (t.name || t).toLowerCase());
        const currentTagsSet = new Set(currentTags);

        const predictedTags = result.tags
            .map(t => t.name.replace(/ /g, '_'))
            .filter(t => !currentTagsSet.has(t.toLowerCase()));

        if (predictedTags.length > 0) {
            return {
                mediaId: result.media_id,
                currentTags: (mediaData?.tags || []).map(t => t.name || t),
                predictedTags,
                filename: mediaData?.filename || `Media ${result.media_id}`
            };
        }
        return null;
    }

    async finalizeResults() {
        if (this.isCancelled) return;

        if (this.itemsData.length === 0) {
            this.showState('empty');
            return;
        }

        // Validate tags
        const allTags = new Set();
        for (const item of this.itemsData) {
            item.predictedTags.forEach(tag => allTags.add(tag.toLowerCase()));
        }

        try {
            await this.validateTags(Array.from(allTags));
        } catch (e) {
            if (e.name === 'AbortError') return;
            throw e;
        }

        if (this.isCancelled) return;

        // Apply validated tags
        for (const item of this.itemsData) {
            item.newTags = item.predictedTags.filter(tag => {
                const resolved = this.getResolvedTag(tag);
                return resolved !== null;
            }).map(tag => {
                const resolved = this.getResolvedTag(tag);
                return resolved || tag;
            });
        }

        this.itemsData = this.itemsData.filter(item => item.newTags.length > 0);

        if (this.itemsData.length === 0) {
            this.showState('empty');
            return;
        }

        const prefix = this.options.classPrefix;
        const itemsContainer = this.modalElement.querySelector(`.${prefix}-items`);

        this.renderItems();
        await this.initializeInputHelpers(itemsContainer);

        if (this.isCancelled) return;

        this.showState('content');
        this.showSaveButton();
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

            const newPredictions = result.tags
                .map(t => t.name.replace(/ /g, '_'))
                .filter(t => !currentTagsSet.has(t.toLowerCase()));

            if (newPredictions.length > 0) {
                // Validate new tags
                for (const tag of newPredictions) {
                    if (!this.tagResolutionCache.has(tag.toLowerCase())) {
                        await this.validateAndCacheTag(tag.toLowerCase());
                    }
                }

                const validTags = newPredictions.filter(tag => {
                    const resolved = this.getResolvedTag(tag);
                    return resolved !== null;
                }).map(tag => {
                    const resolved = this.getResolvedTag(tag);
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
