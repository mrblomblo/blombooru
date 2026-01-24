class BulkAITagsModal extends BulkTagModalBase {
    constructor(options = {}) {
        super({
            id: 'bulk-ai-tags-modal',
            title: 'Bulk Append AI Tags',
            classPrefix: 'bulk-ai-tags',
            emptyMessage: 'No new AI tags found in the selected items\' metadata.',
            closeOnOutsideClick: false,
            ...options
        });

        this.init();
    }

    getBodyHTML() {
        return `
            ${this.getLoadingHTML('Fetching AI metadata...')}
            ${this.getContentHTML()}
            ${this.getEmptyHTML()}
            ${this.getCancelledHTML()}
        `;
    }

    async fetchTags() {
        if (this.isCancelled) return;

        this.showState('loading');
        const prefix = this.options.classPrefix;
        const itemsContainer = this.modalElement.querySelector(`.${prefix}-items`);

        const selectedArray = Array.from(this.selectedItems);

        // Phase 1: Fetch metadata and media info
        this.updateProgress(0, selectedArray.length, 'Fetching metadata...', 'items fetched');

        const rawData = [];
        const mediaDataMap = new Map();

        // 1a. Batch fetch media data
        try {
            const idsParam = selectedArray.join(',');
            const res = await this.fetchWithAbort(`/api/media/batch?ids=${idsParam}`);
            if (res.ok) {
                const data = await res.json();
                if (data.items) {
                    data.items.forEach(item => mediaDataMap.set(item.id, item));
                }
            }
        } catch (e) {
            console.error('Error fetching media batch:', e);
        }

        // 1b. Fetch metadata individuals (and media data fallback)
        let fetchProgress = 0;
        const fetchMediaData = async (mediaId) => {
            if (this.isCancelled) return;
            try {
                let mediaData = mediaDataMap.get(mediaId);

                const fetchTasks = [this.fetchWithAbort(`/api/media/${mediaId}/metadata`)];
                if (!mediaData) {
                    fetchTasks.push(this.fetchWithAbort(`/api/media/${mediaId}`));
                }

                const results = await Promise.all(fetchTasks);
                const metaRes = results[0];
                const mediaRes = results[1];

                const metadata = metaRes.ok ? await metaRes.json() : null;
                if (mediaRes && mediaRes.ok) {
                    mediaData = await mediaRes.json();
                }

                if (metadata) {
                    rawData.push({ mediaId, metadata, mediaData: mediaData || { tags: [] } });
                }
            } catch (e) {
                if (e.name === 'AbortError') throw e;
                console.error(`Error fetching media ${mediaId}:`, e);
            } finally {
                fetchProgress++;
                if (!this.isCancelled) {
                    this.updateProgress(fetchProgress, selectedArray.length, 'Fetching metadata...', 'items fetched');
                }
            }
        };

        try {
            await this.processBatch(selectedArray, fetchMediaData, 10);
        } catch (e) {
            if (e.name === 'AbortError') return;
            throw e;
        }
        if (this.isCancelled) return;

        // Phase 2: Extract prompts and collect tags
        const allUniqueTags = new Set();
        const itemsWithPrompts = [];

        for (const { mediaId, metadata, mediaData } of rawData) {
            if (!metadata) continue;

            const aiPrompt = AITagUtils.extractAIPrompt(metadata);
            if (!aiPrompt) continue;

            const promptTags = AITagUtils.parsePromptTags(aiPrompt);

            if (promptTags.length === 0) continue;

            promptTags.forEach(tag => allUniqueTags.add(tag));

            itemsWithPrompts.push({
                mediaId,
                mediaData,
                promptTags: [...new Set(promptTags)]
            });
        }

        if (itemsWithPrompts.length === 0) {
            this.showState('empty');
            return;
        }

        // Phase 3: Validate tags
        try {
            await this.validateTags(Array.from(allUniqueTags));
        } catch (e) {
            if (e.name === 'AbortError') return;
            throw e;
        }

        if (this.isCancelled) return;

        // Phase 4: Build final data
        for (const { mediaId, mediaData, promptTags } of itemsWithPrompts) {
            const currentTags = (mediaData.tags || []).map(t => t.name || t);
            const currentTagsSet = new Set(currentTags.map(t => t.toLowerCase()));

            const validTags = [];
            const seenTags = new Set();

            for (const tag of promptTags) {
                const resolvedTag = this.getResolvedTag(tag);

                if (resolvedTag &&
                    !currentTagsSet.has(resolvedTag.toLowerCase()) &&
                    !seenTags.has(resolvedTag.toLowerCase())) {
                    validTags.push(resolvedTag);
                    seenTags.add(resolvedTag.toLowerCase());
                }
            }

            if (validTags.length > 0) {
                this.itemsData.push({
                    mediaId,
                    currentTags,
                    newTags: validTags,
                    filename: mediaData.filename || `Media ${mediaId}`
                });
            }
        }

        if (this.itemsData.length === 0) {
            this.showState('empty');
            return;
        }

        this.renderItems();
        await this.initializeInputHelpers(itemsContainer);

        if (this.isCancelled) return;

        this.showState('content');
        this.showSaveButton();
    }

    async processMediaItem(mediaId) {
        if (this.isCancelled) return null;

        try {
            const [metaRes, mediaRes] = await Promise.all([
                this.fetchWithAbort(`/api/media/${mediaId}/metadata`),
                this.fetchWithAbort(`/api/media/${mediaId}`)
            ]);

            if (!metaRes.ok) return null;

            const metadata = await metaRes.json();
            const aiPrompt = AITagUtils.extractAIPrompt(metadata);
            if (!aiPrompt) return null;

            const mediaData = mediaRes.ok ? await mediaRes.json() : { tags: [] };

            const promptTags = AITagUtils.parsePromptTags(aiPrompt);

            const currentTags = (mediaData.tags || []).map(t => t.name || t);
            const currentTagsSet = new Set(currentTags.map(t => t.toLowerCase()));

            const validTags = [];
            const seenTags = new Set();

            for (const tag of promptTags) {
                if (currentTagsSet.has(tag)) continue;

                // Validate if not in cache
                if (!this.tagResolutionCache.has(tag)) {
                    await this.validateAndCacheTag(tag);
                }

                const resolvedTag = this.getResolvedTag(tag);

                if (resolvedTag &&
                    !currentTagsSet.has(resolvedTag.toLowerCase()) &&
                    !seenTags.has(resolvedTag.toLowerCase())) {
                    validTags.push(resolvedTag);
                    seenTags.add(resolvedTag.toLowerCase());
                }
            }

            if (validTags.length > 0) {
                return {
                    mediaId,
                    currentTags,
                    newTags: validTags,
                    filename: mediaData.filename || `Media ${mediaId}`
                };
            }
        } catch (e) {
            if (e.name === 'AbortError') throw e;
            console.error(`Error processing media ${mediaId}:`, e);
        }
        return null;
    }

    async refreshSingleItem(index, inputElement) {
        const item = this.itemsData[index];
        if (!item || this.isCancelled) return;

        inputElement.style.opacity = '0.5';

        try {
            const result = await this.processMediaItem(item.mediaId);
            if (result && result.newTags.length > 0) {
                const existingInputTags = this.tagInputHelper
                    ? this.tagInputHelper.getValidTagsFromInput(inputElement)
                    : inputElement.textContent.trim().split(/\s+/).filter(t => t);

                const existingSet = new Set(existingInputTags.map(t => t.toLowerCase()));
                const toAdd = result.newTags.filter(t => !existingSet.has(t.toLowerCase()));

                if (toAdd.length > 0) {
                    const newValue = [...existingInputTags, ...toAdd].join(' ');
                    inputElement.textContent = newValue;
                    this.triggerValidation(inputElement);
                } else {
                    this.flashButton(index, 'var(--warning)');
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
    module.exports = BulkAITagsModal;
}
