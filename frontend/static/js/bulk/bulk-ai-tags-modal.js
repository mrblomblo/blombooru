class BulkAITagsModal extends BulkTagModalBase {
    constructor(options = {}) {
        super({
            id: 'bulk-ai-tags-modal',
            title: window.i18n.t('bulk_modal.ai_tags.title'),
            classPrefix: 'bulk-ai-tags',
            emptyMessage: window.i18n.t('bulk_modal.ai_tags.empty_message'),
            closeOnOutsideClick: false,
            ...options
        });

        this.init();
    }

    getBodyHTML() {
        return `
            ${this.getLoadingHTML(window.i18n.t('bulk_modal.progress.fetching_metadata'))}
            ${this.getContentHTML()}
            ${this.getEmptyHTML()}
            ${this.getErrorHTML()}
            ${this.getCancelledHTML()}
        `;
    }

    async fetchTags() {
        if (this.isCancelled) return;

        this.showState('loading');
        const selectedArray = Array.from(this.selectedItems);

        // Phase 1: Fetch media info and AI metadata in one concurrent chunked pass
        let batchItems = [];

        try {
            batchItems = await this.fetchMediaInChunks(selectedArray, {
                chunkSize: 50,
                concurrency: 3,
                projection: 'ai_metadata',
                statusText: window.i18n.t('bulk_modal.progress.fetching_metadata'),
                phaseText: window.i18n.t('bulk_modal.progress.items_fetched')
            });

            if (this.isCancelled) return;
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error fetching media batch or metadata:', e);
            this.showError(window.i18n.t('bulk_modal.messages.error_occurred'));
            return;
        }
        if (this.isCancelled) return;

        if (!batchItems || batchItems.length === 0) {
            this.showState('empty');
            return;
        }

        // Phase 2: Extract prompts and collect tags
        const allUniqueTags = new Set();
        const itemsWithPrompts = [];

        for (const item of batchItems) {
            const metadata = item.metadata;
            if (!metadata) continue;

            const aiPrompt = AITagUtils.extractAIPrompt(metadata);
            if (!aiPrompt) continue;

            const promptTags = AITagUtils.parsePromptTags(aiPrompt);

            if (promptTags.length === 0) continue;

            promptTags.forEach(tag => allUniqueTags.add(tag));

            itemsWithPrompts.push({
                mediaId: item.id,
                mediaData: item,
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
                const resolved = this.getResolvedTag(tag);
                const resolvedTag = typeof resolved === 'object' && resolved !== null ? resolved.name : resolved;

                if (resolvedTag &&
                    typeof resolvedTag === 'string' &&
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
                    filename: mediaData.filename || window.i18n.t('bulk_modal.ai_tags.default_media_name', { id: mediaId })
                });
            }
        }

        if (this.itemsData.length === 0) {
            this.showState('empty');
            return;
        }

        this.renderItems();

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

                const resolved = this.getResolvedTag(tag);
                const resolvedTag = typeof resolved === 'object' && resolved !== null ? resolved.name : resolved;

                if (resolvedTag &&
                    typeof resolvedTag === 'string' &&
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
                    filename: mediaData.filename || window.i18n.t('bulk_modal.ai_tags.default_media_name', { id: mediaId })
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
