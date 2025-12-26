class BulkAITagsModal {
    constructor(options = {}) {
        this.options = {
            id: options.id || 'bulk-ai-tags-modal',
            onSave: options.onSave || null,
            onClose: options.onClose || null,
            closeOnEscape: options.closeOnEscape !== false,
            closeOnOutsideClick: options.closeOnOutsideClick !== false,
            ...options
        };

        this.modalElement = null;
        this.isVisible = false;
        this.selectedItems = new Set();
        this.bulkAITagsData = [];

        // Cancellation support
        this.abortController = null;
        this.isCancelled = false;

        // Tag resolution cache - persists across modal opens for speed
        this.tagResolutionCache = new Map();

        // Initialize the helper class
        this.tagInputHelper = typeof TagInputHelper !== 'undefined' ? new TagInputHelper() : null;

        this.init();
    }

    init() {
        this.createModal();
        this.setupEventListeners();
    }

    createModal() {
        if (document.getElementById(this.options.id)) {
            this.modalElement = document.getElementById(this.options.id);
            return;
        }

        const modal = document.createElement('div');
        modal.id = this.options.id;
        modal.className = 'fixed inset-0 flex items-center justify-center z-50';
        modal.style.display = 'none';
        modal.style.background = 'rgba(0, 0, 0, 0.5)';

        modal.innerHTML = `
            <div class="surface p-6 max-w-4xl w-full mx-4 max-h-[80vh] flex flex-col border">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-lg font-bold">Bulk Append AI Tags</h2>
                    <button class="bulk-ai-tags-close text-secondary hover:text text-2xl leading-none">&times;</button>
                </div>
                
                <div class="bulk-ai-tags-loading text-center py-8" style="display: none;">
                    <p class="text-secondary bulk-ai-tags-status">Fetching AI metadata...</p>
                    <p class="text-secondary text-sm mt-2">
                        <span class="bulk-ai-tags-progress">0</span> / <span class="bulk-ai-tags-total">0</span> <span class="bulk-ai-tags-phase">items processed</span>
                    </p>
                </div>
                
                <div class="bulk-ai-tags-content flex-1 overflow-y-auto" style="display: none;">
                    <p class="text-secondary mb-4 text-sm">Review and edit tags for each item. Invalid tags are highlighted in red.</p>
                    <div class="bulk-ai-tags-items space-y-3"></div>
                </div>
                
                <div class="bulk-ai-tags-empty text-center py-8" style="display: none;">
                    <p class="text-secondary">No AI tags found in the selected items' metadata.</p>
                </div>
                
                <div class="bulk-ai-tags-cancelled text-center py-8" style="display: none;">
                    <p class="text-secondary">Operation cancelled.</p>
                </div>
                
                <div class="flex justify-end gap-2 mt-4 pt-4 border-t border-color bg-surface z-20">
                    <button class="bulk-ai-tags-cancel px-4 py-2 surface-light transition-colors hover:surface-light text text-sm">
                        Cancel
                    </button>
                    <button class="bulk-ai-tags-save px-4 py-2 bg-primary transition-colors hover:bg-primary tag-text text-sm" style="display: none;">
                        Save All
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this.modalElement = modal;
    }

    setupEventListeners() {
        if (!this.modalElement) return;

        const closeBtn = this.modalElement.querySelector('.bulk-ai-tags-close');
        if (closeBtn) closeBtn.addEventListener('click', () => this.cancel());

        const cancelBtn = this.modalElement.querySelector('.bulk-ai-tags-cancel');
        if (cancelBtn) cancelBtn.addEventListener('click', () => this.cancel());

        const saveBtn = this.modalElement.querySelector('.bulk-ai-tags-save');
        if (saveBtn) saveBtn.addEventListener('click', () => this.saveAITags());

        const itemsContainer = this.modalElement.querySelector('.bulk-ai-tags-items');
        if (itemsContainer) {
            itemsContainer.addEventListener('click', (e) => {
                const btn = e.target.closest('button');
                if (!btn) return;

                const index = btn.dataset.index;
                const input = this.modalElement.querySelector(`.bulk-ai-tag-input[data-index="${index}"]`);
                if (!input) return;

                if (btn.classList.contains('bulk-ai-tag-clear')) {
                    input.textContent = '';
                    this.triggerValidation(input);
                }

                if (btn.classList.contains('bulk-ai-tag-append')) {
                    this.fetchSingleItemAI(index, input);
                }
            });
        }

        if (this.options.closeOnEscape) {
            this._escapeHandler = (e) => {
                if (e.key === 'Escape' && this.isVisible) this.cancel();
            };
            document.addEventListener('keydown', this._escapeHandler);
        }

        if (this.options.closeOnOutsideClick) {
            this.modalElement.addEventListener('click', (e) => {
                if (e.target === this.modalElement) this.cancel();
            });
        }
    }

    triggerValidation(input) {
        if (this.tagInputHelper) {
            this.tagInputHelper.validateAndStyleTags(input, {
                validationCache: this.tagInputHelper.tagValidationCache,
                checkFunction: (tag) => this.tagInputHelper.checkTagExists(tag)
            });
        }
    }

    show(selectedItems) {
        if (!this.modalElement) {
            this.createModal();
            this.setupEventListeners();
        }

        this.selectedItems = new Set(selectedItems);
        this.reset();
        this.isCancelled = false;
        this.abortController = new AbortController();
        this.modalElement.style.display = 'flex';
        this.isVisible = true;

        this.fetchAITags();

        return this;
    }

    hide() {
        if (this.modalElement) {
            this.modalElement.style.display = 'none';
            this.isVisible = false;
        }

        return this;
    }

    cancel() {
        this.isCancelled = true;

        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }

        this.hide();

        if (typeof this.options.onClose === 'function') {
            this.options.onClose();
        }
    }

    reset() {
        const states = ['.bulk-ai-tags-loading', '.bulk-ai-tags-content', '.bulk-ai-tags-empty', '.bulk-ai-tags-cancelled'];
        states.forEach(selector => {
            const el = this.modalElement.querySelector(selector);
            if (el) el.style.display = 'none';
        });

        const saveBtn = this.modalElement.querySelector('.bulk-ai-tags-save');
        const itemsContainer = this.modalElement.querySelector('.bulk-ai-tags-items');

        if (saveBtn) saveBtn.style.display = 'none';
        if (itemsContainer) itemsContainer.innerHTML = '';

        this.bulkAITagsData = [];
    }

    showState(state) {
        const states = ['loading', 'content', 'empty', 'cancelled'];
        states.forEach(s => {
            const el = this.modalElement.querySelector(`.bulk-ai-tags-${s}`);
            if (el) el.style.display = s === state ? 'block' : 'none';
        });
    }

    updateProgress(current, total, status, phase) {
        const progress = this.modalElement.querySelector('.bulk-ai-tags-progress');
        const totalEl = this.modalElement.querySelector('.bulk-ai-tags-total');
        const statusEl = this.modalElement.querySelector('.bulk-ai-tags-status');
        const phaseEl = this.modalElement.querySelector('.bulk-ai-tags-phase');

        if (progress) progress.textContent = current;
        if (totalEl) totalEl.textContent = total;
        if (statusEl) statusEl.textContent = status;
        if (phaseEl) phaseEl.textContent = phase;
    }

    async fetchWithAbort(url, options = {}) {
        if (this.isCancelled) throw new DOMException('Cancelled', 'AbortError');

        return fetch(url, {
            ...options,
            signal: this.abortController?.signal
        });
    }

    async fetchAITags() {
        if (this.isCancelled) return;

        this.showState('loading');
        const saveBtn = this.modalElement.querySelector('.bulk-ai-tags-save');
        const itemsContainer = this.modalElement.querySelector('.bulk-ai-tags-items');

        const selectedArray = Array.from(this.selectedItems);
        const FETCH_CONCURRENCY = 10;
        const TAG_VALIDATION_CONCURRENCY = 20;

        this.bulkAITagsData = [];

        // Phase 1: Fetch metadata and media info
        this.updateProgress(0, selectedArray.length, 'Fetching metadata...', 'items fetched');

        const rawData = [];
        let fetchProgress = 0;

        const fetchMediaData = async (mediaId) => {
            if (this.isCancelled) return;
            try {
                const [metaRes, mediaRes] = await Promise.all([
                    this.fetchWithAbort(`/api/media/${mediaId}/metadata`),
                    this.fetchWithAbort(`/api/media/${mediaId}`)
                ]);

                const metadata = metaRes.ok ? await metaRes.json() : null;
                const mediaData = mediaRes.ok ? await mediaRes.json() : { tags: [] };

                rawData.push({ mediaId, metadata, mediaData });
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
            for (let i = 0; i < selectedArray.length; i += FETCH_CONCURRENCY) {
                if (this.isCancelled) return;
                const chunk = selectedArray.slice(i, i + FETCH_CONCURRENCY);
                await Promise.all(chunk.map(id => fetchMediaData(id)));
            }
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

            const aiPrompt = this.extractAIPromptFromMetadata(metadata);
            if (!aiPrompt) continue;

            const promptTags = aiPrompt
                .split(',')
                .map(tag => tag.trim().replace(/\s+/g, '_').toLowerCase())
                .filter(tag => tag.length > 0);

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
        const tagsToValidate = Array.from(allUniqueTags).filter(
            tag => !this.tagResolutionCache.has(tag)
        );

        if (tagsToValidate.length > 0) {
            this.updateProgress(0, tagsToValidate.length, 'Validating tags...', 'tags checked');

            let validationProgress = 0;

            const validateTag = async (tag) => {
                if (this.isCancelled) return;
                await this.validateAndCacheTag(tag);
                validationProgress++;
                if (!this.isCancelled) {
                    this.updateProgress(validationProgress, tagsToValidate.length, 'Validating tags...', 'tags checked');
                }
            };

            try {
                for (let i = 0; i < tagsToValidate.length; i += TAG_VALIDATION_CONCURRENCY) {
                    if (this.isCancelled) return;
                    const chunk = tagsToValidate.slice(i, i + TAG_VALIDATION_CONCURRENCY);
                    await Promise.all(chunk.map(tag => validateTag(tag)));
                }
            } catch (e) {
                if (e.name === 'AbortError') return;
                throw e;
            }
        }

        if (this.isCancelled) return;

        // Phase 4: Build final data
        for (const { mediaId, mediaData, promptTags } of itemsWithPrompts) {
            const currentTags = (mediaData.tags || []).map(t => t.name || t);
            const currentTagsSet = new Set(currentTags.map(t => t.toLowerCase()));

            const validTags = [];
            const seenTags = new Set();

            for (const tag of promptTags) {
                const resolvedTag = this.tagResolutionCache.get(tag);

                if (resolvedTag &&
                    !currentTagsSet.has(resolvedTag.toLowerCase()) &&
                    !seenTags.has(resolvedTag.toLowerCase())) {
                    validTags.push(resolvedTag);
                    seenTags.add(resolvedTag.toLowerCase());
                }
            }

            if (validTags.length > 0) {
                this.bulkAITagsData.push({
                    mediaId,
                    currentTags,
                    aiTags: validTags,
                    filename: mediaData.filename || `Media ${mediaId}`
                });
            }
        }

        if (this.bulkAITagsData.length === 0) {
            this.showState('empty');
            return;
        }

        // Render items
        if (itemsContainer) {
            itemsContainer.innerHTML = this.bulkAITagsData.map((item, index) =>
                this.renderTagItem(item, index)
            ).join('');
        }

        await this.initializeInputHelpers(itemsContainer);

        if (this.isCancelled) return;

        this.showState('content');
        if (saveBtn) saveBtn.style.display = 'block';
    }

    async validateAndCacheTag(tag) {
        if (this.tagResolutionCache.has(tag)) return;
        if (this.isCancelled) return;

        try {
            const response = await this.fetchWithAbort(`/api/tags/autocomplete?q=${encodeURIComponent(tag)}`);

            let result = null;
            if (response.ok) {
                const results = await response.json();
                if (results && results.length > 0) {
                    const aliasMatch = results.find(t => t.is_alias && t.alias_name === tag);
                    if (aliasMatch) {
                        result = aliasMatch.name;
                    } else {
                        const exactMatch = results.find(t => t.name === tag);
                        if (exactMatch) result = exactMatch.name;
                    }
                }
            }

            this.tagResolutionCache.set(tag, result);
        } catch (e) {
            if (e.name === 'AbortError') throw e;
            this.tagResolutionCache.set(tag, null);
        }
    }

    async getTagOrAlias(tagName) {
        if (!tagName) return null;
        const normalized = tagName.toLowerCase().trim();

        if (this.tagResolutionCache.has(normalized)) {
            return this.tagResolutionCache.get(normalized);
        }

        await this.validateAndCacheTag(normalized);
        return this.tagResolutionCache.get(normalized);
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
            const aiPrompt = this.extractAIPromptFromMetadata(metadata);
            if (!aiPrompt) return null;

            const mediaData = mediaRes.ok ? await mediaRes.json() : { tags: [] };

            const promptTags = aiPrompt
                .split(',')
                .map(tag => tag.trim().replace(/\s+/g, '_').toLowerCase())
                .filter(tag => tag.length > 0);

            const currentTags = (mediaData.tags || []).map(t => t.name || t);
            const currentTagsSet = new Set(currentTags.map(t => t.toLowerCase()));

            const validTags = [];
            const seenTags = new Set();

            for (const tag of promptTags) {
                if (currentTagsSet.has(tag)) continue;

                const validTag = await this.getTagOrAlias(tag);

                if (validTag &&
                    !currentTagsSet.has(validTag.toLowerCase()) &&
                    !seenTags.has(validTag.toLowerCase())) {
                    validTags.push(validTag);
                    seenTags.add(validTag.toLowerCase());
                }
            }

            if (validTags.length > 0) {
                return {
                    mediaId,
                    currentTags,
                    aiTags: validTags,
                    filename: mediaData.filename || `Media ${mediaId}`
                };
            }
        } catch (e) {
            if (e.name === 'AbortError') throw e;
            console.error(`Error processing media ${mediaId}:`, e);
        }
        return null;
    }

    async fetchSingleItemAI(index, inputElement) {
        const item = this.bulkAITagsData[index];
        if (!item || this.isCancelled) return;

        inputElement.style.opacity = '0.5';

        try {
            const result = await this.processMediaItem(item.mediaId);
            if (result && result.aiTags.length > 0) {
                const existingInputTags = this.tagInputHelper
                    ? this.tagInputHelper.getValidTagsFromInput(inputElement)
                    : inputElement.textContent.trim().split(/\s+/).filter(t => t);

                const existingSet = new Set(existingInputTags.map(t => t.toLowerCase()));
                const toAdd = result.aiTags.filter(t => !existingSet.has(t.toLowerCase()));

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

    flashButton(index, color) {
        const btn = this.modalElement.querySelector(`.bulk-ai-tag-append[data-index="${index}"]`);
        if (btn) {
            const originalColor = btn.style.color;
            btn.style.color = color;
            setTimeout(() => btn.style.color = originalColor, 500);
        }
    }

    async initializeInputHelpers(container) {
        if (!this.tagInputHelper || this.isCancelled) return;

        const inputs = container.querySelectorAll('.bulk-ai-tag-input');
        for (const input of inputs) {
            if (this.isCancelled) return;

            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(input, {
                    multipleValues: true,
                    containerClasses: 'surface border border-color shadow-lg z-50',
                    onSelect: () => this.triggerValidation(input)
                });
            }

            this.tagInputHelper.setupTagInput(input, `bulk-ai-tag-${input.dataset.index}`, {
                onValidate: () => { },
                validationCache: this.tagInputHelper.tagValidationCache,
                checkFunction: (tag) => this.tagInputHelper.checkTagExists(tag)
            });

            await new Promise(r => setTimeout(r, 0));
            this.triggerValidation(input);
        }
    }

    extractAIPromptFromMetadata(metadata) {
        const aiDataSources = [
            metadata.parameters,
            metadata.prompt,
            metadata.Comment,
            metadata.UserComment,
            metadata.sui_image_params,
            metadata.comfy_workflow
        ];

        for (const source of aiDataSources) {
            if (!source) continue;

            let parsed = source;
            if (typeof source === 'string') {
                try {
                    parsed = JSON.parse(source);
                } catch {
                    if (source.includes(',') && !source.includes('{')) return source;
                    const match = source.match(/^(.+?)(?:\nNegative prompt:|$)/s);
                    if (match) return match[1].trim();
                }
            }

            if (typeof parsed === 'object' && parsed !== null) {
                const promptKeys = ['prompt', 'Prompt', 'positive_prompt', 'positive'];
                for (const key of promptKeys) {
                    if (parsed[key] && typeof parsed[key] === 'string') return parsed[key];
                }
                if (parsed.sui_image_params?.prompt) return parsed.sui_image_params.prompt;
            }
        }
        return null;
    }

    renderTagItem(item, index) {
        const currentTagsDisplay = item.currentTags.length > 0
            ? item.currentTags.slice(0, 5).join(', ') + (item.currentTags.length > 5 ? ` (+${item.currentTags.length - 5} more)` : '')
            : 'No tags';

        return `
            <div class="bulk-ai-tag-item surface-light p-3 border" data-index="${index}">
                <div class="flex gap-3">
                    <img src="/api/media/${item.mediaId}/thumbnail" 
                         alt="" 
                         class="w-24 object-cover flex-shrink-0"
                         onerror="this.src='/static/images/no-thumbnail.png'">
                    <div class="flex-1 min-w-0">
                        <p class="text-sm truncate mb-1" title="${item.filename}">${item.filename}</p>
                        <p class="text-xs text-secondary mb-2">Current: ${currentTagsDisplay}</p>
                        
                        <div class="flex gap-2 items-start">
                            <div class="relative flex-1">
                                <div class="bulk-ai-tag-input w-full bg px-2 py-1 border text-sm focus:outline-none focus:border-primary" 
                                     contenteditable="true"
                                     data-index="${index}"
                                     style="white-space: pre-wrap; overflow-wrap: break-word;">${item.aiTags.join(' ')}</div>
                            </div>
                            
                            <div class="flex flex-row gap-1">
                                <button type="button" 
                                        class="bulk-ai-tag-append px-2 py-1 surface text-secondary hover:surface-light hover:text-white h-[1.8rem] w-[2rem] flex items-center justify-center transition-colors"
                                        data-index="${index}"
                                        title="Re-append AI tags">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path>
                                    </svg>
                                </button>
                                <button type="button" 
                                        class="bulk-ai-tag-clear px-2 py-1 bg-danger tag-text hover:bg-danger h-[1.8rem] w-[2rem] flex items-center justify-center transition-colors"
                                        data-index="${index}"
                                        title="Clear tags">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <polyline points="3 6 5 6 21 6"></polyline>
                                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async saveAITags() {
        const saveBtn = this.modalElement.querySelector('.bulk-ai-tags-save');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
        }

        let successCount = 0;
        let errorCount = 0;

        const SAVE_CONCURRENCY = 5;

        const saveItem = async (index) => {
            const item = this.bulkAITagsData[index];
            const input = this.modalElement.querySelector(`.bulk-ai-tag-input[data-index="${index}"]`);

            if (!input) return;

            let newTags = [];
            if (this.tagInputHelper) {
                newTags = this.tagInputHelper.getValidTagsFromInput(input);
            } else {
                newTags = input.innerText.trim().split(/\s+/).filter(t => t.length > 0);
            }

            if (newTags.length === 0) return;

            const existingSet = new Set(item.currentTags.map(t => t.toLowerCase()));
            const uniqueNewTags = newTags.filter(t => !existingSet.has(t.toLowerCase()));

            if (uniqueNewTags.length === 0) return;

            const allTags = [...item.currentTags, ...uniqueNewTags];

            try {
                const response = await fetch(`/api/media/${item.mediaId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tags: allTags })
                });

                if (response.ok) successCount++;
                else errorCount++;
            } catch (e) {
                console.error(`Error saving tags for media ${item.mediaId}:`, e);
                errorCount++;
            }
        };

        const indices = this.bulkAITagsData.map((_, i) => i);
        for (let i = 0; i < indices.length; i += SAVE_CONCURRENCY) {
            const chunk = indices.slice(i, i + SAVE_CONCURRENCY);
            await Promise.all(chunk.map(idx => saveItem(idx)));
        }

        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save All';
        }

        this.hide();

        if (typeof this.options.onSave === 'function') {
            this.options.onSave({ successCount, errorCount });
        }

        if (typeof app !== 'undefined' && app.showNotification) {
            if (successCount > 0) app.showNotification(`Successfully updated ${successCount} item(s)`, 'success');
            if (errorCount > 0) app.showNotification(`Failed to update ${errorCount} item(s)`, 'error');
        }
    }

    destroy() {
        this.cancel();
        if (this._escapeHandler) {
            document.removeEventListener('keydown', this._escapeHandler);
        }
        if (this.modalElement && this.modalElement.parentNode) {
            this.modalElement.parentNode.removeChild(this.modalElement);
        }
        this.modalElement = null;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkAITagsModal;
}
