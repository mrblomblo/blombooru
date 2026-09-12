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
        const itemsWithPrompts = [];

        for (const item of batchItems) {
            const metadata = item.metadata;
            if (!metadata) continue;

            const aiPrompt = AITagUtils.extractAIPrompt(metadata);
            if (!aiPrompt) continue;

            const promptTags = AITagUtils.extractPromptTags(metadata);
            if (promptTags.length === 0) continue;

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

        // Phase 3: Batch resolve combined tags (resolves aliases, canonical names, and implications on combined tags)
        const itemsToResolve = itemsWithPrompts.map(({ mediaId, mediaData, promptTags }) => ({
            id: mediaId,
            current_tags: (mediaData.tags || []).map(t => (typeof t === 'object' && t !== null ? t.name : t)),
            new_tags: promptTags
        }));

        let resolvedResults = {};
        try {
            resolvedResults = await this.resolveCombinedTagsBatch(itemsToResolve);
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error resolving combined tags batch:', e);
        }

        if (this.isCancelled) return;

        // Phase 4: Build final data
        for (const { mediaId, mediaData } of itemsWithPrompts) {
            const res = resolvedResults[mediaId] || resolvedResults[String(mediaId)];
            if (!res) continue;

            if (res.added_tags && res.added_tags.length > 0) {
                this.itemsData.push({
                    mediaId,
                    currentTags: res.current_tags || [],
                    newTags: res.new_tags || [],
                    prefilledTags: res.added_tags || [],
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
            const promptTags = AITagUtils.extractPromptTags(metadata);
            const currentTags = (mediaData.tags || []).map(t => (typeof t === 'object' && t !== null ? t.name : t));

            const resolvedResults = await this.resolveCombinedTagsBatch([{
                id: mediaId,
                current_tags: currentTags,
                new_tags: promptTags
            }]);

            const res = resolvedResults[mediaId] || resolvedResults[String(mediaId)];
            if (res && res.added_tags && res.added_tags.length > 0) {
                return {
                    mediaId,
                    currentTags: res.current_tags || [],
                    newTags: res.new_tags || [],
                    prefilledTags: res.added_tags || [],
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
                item.currentTags = result.currentTags;
                item.newTags = result.newTags;
                item.prefilledTags = result.prefilledTags;

                const prefilledSet = new Set(item.prefilledTags.map(t => t.toLowerCase()));
                const renderedContent = item.newTags.map(tag => {
                    const escaped = this.escapeHtml(tag);
                    if (prefilledSet.has(tag.toLowerCase())) {
                        return `<span class="new-tag">${escaped}</span>`;
                    }
                    return escaped;
                }).join(' ');

                inputElement.innerHTML = renderedContent;
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
    module.exports = BulkAITagsModal;
}
