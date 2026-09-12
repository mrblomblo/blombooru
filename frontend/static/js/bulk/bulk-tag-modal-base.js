class BulkTagModalBase {
    constructor(options = {}) {
        this.options = {
            id: options.id || 'bulk-tag-modal',
            title: options.title || window.i18n.t('bulk_modal.defaults.title'),
            classPrefix: options.classPrefix || 'bulk-tag',
            emptyMessage: options.emptyMessage || window.i18n.t('bulk_modal.defaults.empty_message'),
            onSave: options.onSave || null,
            onClose: options.onClose || null,
            closeOnEscape: options.closeOnEscape !== false,
            closeOnOutsideClick: options.closeOnOutsideClick !== false,
            ...options
        };

        this.modalElement = null;
        this.isVisible = false;
        this.selectedItems = new Set();
        this.itemsData = [];

        // Cancellation support
        this.abortController = null;
        this.activeReader = null;
        this.isCancelled = false;

        // Tag resolution cache - persists across modal opens
        this.tagResolutionCache = new Map();

        // Initialize the helper class
        this.tagInputHelper = typeof TagInputHelper !== 'undefined' ? new TagInputHelper() : null;

        this.fullscreenViewer = new FullscreenMediaViewer();
    }

    // ==================== Abstract Methods ====================

    getStates() {
        return ['loading', 'content', 'empty', 'error', 'cancelled'];
    }

    getBodyHTML() {
        throw new Error('getBodyHTML must be implemented by subclass');
    }

    getFooterLeftHTML() {
        return '';
    }

    async fetchTags() {
        throw new Error('fetchTags must be implemented by subclass');
    }

    async refreshSingleItem(index, inputElement) {
        // Override in subclass
    }

    async onShow() {
        await this.fetchTags();
    }

    setupAdditionalEventListeners() {
        // Override in subclass
    }

    // ==================== Initialization ====================

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
        modal.className = 'fixed inset-0 flex items-end sm:items-center justify-center z-50';
        modal.style.display = 'none';
        modal.style.background = 'rgba(0, 0, 0, 0.5)';

        const prefix = this.options.classPrefix;
        const footerLeft = this.getFooterLeftHTML();

        modal.innerHTML = `
            <div class="surface w-full h-full sm:h-auto sm:max-h-[85vh] sm:max-w-4xl sm:mx-4 flex flex-col border-t sm:border shadow-2xl safe-area-bottom">
                <!-- Header -->
                <div class="flex items-center p-4 border-b border-color flex-shrink-0">
                    <h2 class="text-base sm:text-lg font-bold truncate">${this.options.title}</h2>
                </div>
                
                <!-- Body -->
                <div class="flex-1 overflow-hidden p-4 flex flex-col min-h-0">
                    ${this.getBodyHTML()}
                </div>
                
                <!-- Footer -->
                <div class="flex-shrink-0 p-4 border-t border-color surface">
                    <div class="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3">
                        ${footerLeft ? `
                            <div class="flex gap-2">
                                ${footerLeft}
                            </div>
                        ` : ''}
                        <div class="flex gap-2 ${footerLeft ? '' : 'sm:ml-auto'}">
                            <button class="${prefix}-save flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn-primary text-sm font-medium cursor-pointer" style="display: none;">
                                ${window.i18n.t('modal.buttons.save_all')}
                            </button>
                            <button class="${prefix}-cancel flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn text-sm font-medium cursor-pointer">
                                ${window.i18n.t('common.cancel')}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this.modalElement = modal;
    }

    // ==================== HTML Helpers ====================

    getSpinnerHTML(extraClass = '') {
        return `<div class="spinner ${extraClass}"></div>`;
    }

    getLoadingHTML(statusText) {
        if (!statusText) statusText = window.i18n.t('common.processing');
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-loading flex flex-col items-center justify-center h-full py-12" style="display: none;">
                <div class="spinner"></div>
                <p class="text-secondary mt-2 ${prefix}-status text-center">${statusText}</p>
                <p class="text-secondary text-sm text-center">
                    <span class="${prefix}-progress">0</span> / <span class="${prefix}-total">0</span> <span class="${prefix}-phase">${window.i18n.t('bulk_modal.progress.items_processed')}</span>
                </p>
            </div>
        `;
    }

    getContentHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-content flex-1 flex flex-col min-h-0" style="display: none;">
                <p class="text-secondary mb-3 text-xs sm:text-sm flex-shrink-0">${window.i18n.t('bulk_modal.messages.review_tags')}</p>
                <div class="${prefix}-items space-y-3 overflow-y-auto flex-1 -mx-4 px-4 pb-2" style="overscroll-behavior: contain;"></div>
            </div>
        `;
    }

    getEmptyHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-empty flex items-center justify-center h-full py-12" style="display: none;">
                <p class="text-secondary text-center">${this.options.emptyMessage}</p>
            </div>
        `;
    }

    getCancelledHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-cancelled flex items-center justify-center h-full py-12" style="display: none;">
                <p class="text-secondary text-center">${window.i18n.t('bulk_modal.messages.operation_cancelled')}</p>
            </div>
        `;
    }

    getErrorHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-error flex items-center justify-center h-full py-12" style="display: none;">
                <p class="text-danger ${prefix}-error-message text-center">${window.i18n.t('bulk_modal.messages.error_occurred')}</p>
            </div>
        `;
    }

    // ==================== Progress Tracking ====================

    updateProgress(current, total, status, phase) {
        const prefix = this.options.classPrefix;

        const progress = this.modalElement?.querySelector(`.${prefix}-progress`);
        const totalEl = this.modalElement?.querySelector(`.${prefix}-total`);
        const statusEl = this.modalElement?.querySelector(`.${prefix}-status`);
        const phaseEl = this.modalElement?.querySelector(`.${prefix}-phase`);

        if (progress) progress.textContent = current;
        if (totalEl) totalEl.textContent = total;
        if (statusEl && status) statusEl.textContent = status;
        if (phaseEl && phase) phaseEl.textContent = phase;
    }

    // ==================== Chunked Fetchers ====================

    async fetchWithAbort(url, options = {}) {
        if (this.isCancelled) throw new DOMException('Cancelled', 'AbortError');

        return fetch(url, {
            ...options,
            signal: this.abortController?.signal
        });
    }

    async fetchMediaInChunks(mediaIds, options = {}) {
        const {
            chunkSize = 50,
            concurrency = 1,
            projection = 'tags_only',
            statusText = window.i18n.t('bulk_modal.progress.fetching_metadata'),
            phaseText = window.i18n.t('bulk_modal.progress.items_fetched')
        } = options;

        if (!mediaIds || mediaIds.length === 0) return [];

        this.updateProgress(0, mediaIds.length, statusText, phaseText);

        const chunks = [];
        for (let i = 0; i < mediaIds.length; i += chunkSize) {
            chunks.push(mediaIds.slice(i, i + chunkSize));
        }

        let fetchedCount = 0;
        const resultsMap = new Map();
        const failedIds = [];

        const maxRetries = 2;
        const fetchChunkWithRetry = async (chunk, retryCount = maxRetries) => {
            if (this.isCancelled) return;
            try {
                const response = await this.fetchWithAbort('/api/media/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ids: chunk,
                        projection: projection
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: Failed to fetch media batch`);
                }

                const data = await response.json();
                const items = data.items || [];

                for (const item of items) {
                    resultsMap.set(item.id, item);
                    if (item.tags && Array.isArray(item.tags)) {
                        for (const t of item.tags) {
                            const tagName = (t.name || t).toLowerCase().trim();
                            if (tagName) {
                                this.tagResolutionCache.set(tagName, t.name || t);
                                if (this.tagInputHelper) {
                                    this.tagInputHelper.tagValidationCache.set(tagName, true);
                                }
                            }
                        }
                    }
                }
            } catch (err) {
                if (err.name === 'AbortError' || this.isCancelled) throw err;
                if (retryCount > 0) {
                    const delay = 200 * Math.pow(2, maxRetries - retryCount);
                    await new Promise(r => setTimeout(r, delay));
                    return fetchChunkWithRetry(chunk, retryCount - 1);
                }
                console.error('Error fetching media chunk:', err);
                failedIds.push(...chunk);
            } finally {
                fetchedCount += chunk.length;
                if (!this.isCancelled) {
                    this.updateProgress(Math.min(fetchedCount, mediaIds.length), mediaIds.length, statusText, phaseText);
                }
            }
        };

        let chunkIndex = 0;
        const worker = async () => {
            while (chunkIndex < chunks.length && !this.isCancelled) {
                const currentChunk = chunks[chunkIndex++];
                await fetchChunkWithRetry(currentChunk);
            }
        };

        const workers = Array.from({ length: Math.min(concurrency, chunks.length) }, () => worker());
        await Promise.all(workers);

        if (this.isCancelled) return [];

        const successfulItems = mediaIds.map(id => resultsMap.get(id)).filter(Boolean);

        if (successfulItems.length === 0 && failedIds.length > 0) {
            throw new Error('Failed to fetch media items');
        }

        if (failedIds.length > 0 && successfulItems.length > 0) {
            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(window.i18n.t('bulk_modal.messages.error_occurred'), 'warning');
            }
        }

        return successfulItems;
    }

    async fetchMetadataInChunks(mediaIds, options = {}) {
        const {
            chunkSize = 50,
            concurrency = 3,
            statusText = window.i18n.t('bulk_modal.progress.fetching_metadata'),
            phaseText = window.i18n.t('bulk_modal.progress.items_fetched')
        } = options;

        if (!mediaIds || mediaIds.length === 0) return new Map();

        this.updateProgress(0, mediaIds.length, statusText, phaseText);

        const chunks = [];
        for (let i = 0; i < mediaIds.length; i += chunkSize) {
            chunks.push(mediaIds.slice(i, i + chunkSize));
        }

        let fetchedCount = 0;
        const metadataMap = new Map();
        const failedIds = [];

        const maxRetries = 2;
        const fetchChunkWithRetry = async (chunk, retryCount = maxRetries) => {
            if (this.isCancelled) return;
            try {
                const response = await this.fetchWithAbort('/api/media/batch-metadata', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: chunk })
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: Failed to fetch metadata batch`);
                }

                const data = await response.json();
                const items = data.items || {};

                for (const [mid, meta] of Object.entries(items)) {
                    metadataMap.set(parseInt(mid), meta);
                }
            } catch (err) {
                if (err.name === 'AbortError' || this.isCancelled) throw err;
                if (retryCount > 0) {
                    const delay = 200 * Math.pow(2, maxRetries - retryCount);
                    await new Promise(r => setTimeout(r, delay));
                    return fetchChunkWithRetry(chunk, retryCount - 1);
                }
                console.error('Error fetching metadata chunk:', err);
                failedIds.push(...chunk);
            } finally {
                fetchedCount += chunk.length;
                if (!this.isCancelled) {
                    this.updateProgress(Math.min(fetchedCount, mediaIds.length), mediaIds.length, statusText, phaseText);
                }
            }
        };

        let chunkIndex = 0;
        const worker = async () => {
            while (chunkIndex < chunks.length && !this.isCancelled) {
                const currentChunk = chunks[chunkIndex++];
                await fetchChunkWithRetry(currentChunk);
            }
        };

        const workers = Array.from({ length: Math.min(concurrency, chunks.length) }, () => worker());
        await Promise.all(workers);

        if (metadataMap.size === 0 && failedIds.length > 0) {
            throw new Error('Failed to fetch metadata');
        }

        if (failedIds.length > 0 && metadataMap.size > 0) {
            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(window.i18n.t('bulk_modal.messages.error_occurred'), 'warning');
            }
        }

        return metadataMap;
    }

    async resolveCombinedTagsBatch(items) {
        if (!items || items.length === 0) return {};

        try {
            const response = await this.fetchWithAbort('/api/tags/batch-resolve-combined', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ items })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: Failed to batch resolve combined tags`);
            }

            const data = await response.json();
            const results = data.results || {};

            // Cache tag validity and resolution
            for (const itemRes of Object.values(results)) {
                if (itemRes.new_tags && Array.isArray(itemRes.new_tags)) {
                    for (const tag of itemRes.new_tags) {
                        const tagLower = (typeof tag === 'string' ? tag : '').toLowerCase().trim();
                        if (tagLower) {
                            this.tagResolutionCache.set(tagLower, tag);
                            if (this.tagInputHelper) {
                                this.tagInputHelper.tagValidationCache.set(tagLower, true);
                            }
                        }
                    }
                }
            }

            // Cache alias resolutions
            if (data.alias_resolutions) {
                for (const [alias, target] of Object.entries(data.alias_resolutions)) {
                    const aliasLower = alias.toLowerCase().trim();
                    if (aliasLower) {
                        this.tagResolutionCache.set(aliasLower, target);
                        if (this.tagInputHelper) {
                            this.tagInputHelper.tagValidationCache.set(aliasLower, true);
                        }
                    }
                }
            }

            return results;
        } catch (err) {
            if (err.name === 'AbortError' || this.isCancelled) throw err;
            console.error('Error in resolveCombinedTagsBatch:', err);
            return {};
        }
    }

    // ==================== Event Listeners ====================

    setupEventListeners() {
        if (!this.modalElement) return;

        const prefix = this.options.classPrefix;

        const cancelBtn = this.modalElement.querySelector(`.${prefix}-cancel`);
        if (cancelBtn) cancelBtn.addEventListener('click', () => this.cancel());

        const saveBtn = this.modalElement.querySelector(`.${prefix}-save`);
        if (saveBtn) saveBtn.addEventListener('click', () => this.saveTags());

        const container = this.modalElement.querySelector(`.${prefix}-items`);
        if (container) {
            // Lazy input initialization on focus
            container.addEventListener('focusin', (e) => {
                const input = e.target.closest(`.${prefix}-input`);
                if (!input) return;
                this.initializeSingleInput(input);
            });

            container.addEventListener('focusout', (e) => {
                const input = e.target.closest(`.${prefix}-input`);
                if (!input) return;

                const index = parseInt(input.dataset.index);
                this.flushInputState(input, index);
            });

            container.addEventListener('input', (e) => {
                const input = e.target.closest(`.${prefix}-input`);
                if (!input) return;

                const index = parseInt(input.dataset.index);
                this.syncInputState(input, index);
            });

            // Action buttons (Clear & Refresh)
            container.addEventListener('click', (e) => {
                const btn = e.target.closest('button');
                if (!btn) return;

                const index = parseInt(btn.dataset.index);
                if (isNaN(index)) return;

                const input = container.querySelector(`.${prefix}-input[data-index="${index}"]`);

                if (btn.classList.contains(`${prefix}-clear`)) {
                    if (this.itemsData[index]) {
                        this.itemsData[index].newTags = [];
                    }
                    if (input) {
                        input.textContent = '';
                        this.triggerValidation(input);
                    }
                }

                if (btn.classList.contains(`${prefix}-refresh`)) {
                    if (input) {
                        this.refreshSingleItem(index, input);
                    }
                }
            });

            // Thumbnail click listener for Fullscreen viewer
            container.addEventListener('click', (e) => {
                if (e.target.classList.contains('item-thumbnail')) {
                    const row = e.target.closest(`.${prefix}-item`);
                    if (row) {
                        const index = parseInt(row.dataset.index);
                        const item = this.itemsData[index];
                        if (item && item.mediaId) {
                            const isVideo = item.file_type === 'video' || window.FormatRegistry.isVideo(item.filename);
                            const src = `/api/media/${item.mediaId}/file${isVideo ? '?chunked=true' : ''}`;
                            this.fullscreenViewer.open(src, isVideo);
                        }
                    }
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

        window.addEventListener('beforeunload', () => {
            if (this.isVisible) this.handleUnload();
        });
        window.addEventListener('pagehide', () => {
            if (this.isVisible) this.handleUnload();
        });

        this.setupAdditionalEventListeners();
    }

    syncInputState(input, index) {
        if (!this.itemsData[index]) return;
        const text = input.innerText || input.textContent || '';
        const tags = text.trim().split(/\s+/).filter(t => t.length > 0);
        this.itemsData[index].newTags = tags;
    }

    flushInputState(input, index) {
        if (!this.itemsData[index]) return;
        let tags = [];
        if (this.tagInputHelper) {
            tags = this.tagInputHelper.getValidTagsFromInput(input);
        } else {
            const text = input.innerText || input.textContent || '';
            tags = text.trim().split(/\s+/).filter(t => t.length > 0);
        }
        this.itemsData[index].newTags = tags;
    }

    handleUnload() {
        this.isCancelled = true;

        if (this.activeReader) {
            try {
                this.activeReader.cancel();
            } catch (e) { }
            this.activeReader = null;
        }

        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    // ==================== Visibility Management ====================

    show(selectedItems) {
        if (!this.modalElement) {
            this.init();
        }

        this.selectedItems = new Set(selectedItems);
        this.reset();
        this.isCancelled = false;
        this.abortController = new AbortController();
        this.modalElement.style.display = 'flex';
        this.isVisible = true;

        // Prevent body scroll on mobile
        document.body.style.overflow = 'hidden';
        document.documentElement.style.overflow = 'hidden';

        this.onShow();

        return this;
    }

    hide() {
        if (this.modalElement) {
            this.modalElement.style.display = 'none';
            this.isVisible = false;
        }

        // Restore body scroll
        document.body.style.overflow = '';
        document.documentElement.style.overflow = '';

        return this;
    }

    cancel() {
        this.isCancelled = true;

        if (this.activeReader) {
            try {
                this.activeReader.cancel();
            } catch (e) { }
            this.activeReader = null;
        }

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
        const prefix = this.options.classPrefix;

        this.getStates().forEach(state => {
            const el = this.modalElement?.querySelector(`.${prefix}-${state}`);
            if (el) el.style.display = 'none';
        });

        const saveBtn = this.modalElement?.querySelector(`.${prefix}-save`);
        const itemsContainer = this.modalElement?.querySelector(`.${prefix}-items`);

        if (saveBtn) saveBtn.style.display = 'none';
        if (itemsContainer) itemsContainer.innerHTML = '';

        this.itemsData = [];
    }

    showState(state) {
        const prefix = this.options.classPrefix;

        this.getStates().forEach(s => {
            const el = this.modalElement?.querySelector(`.${prefix}-${s}`);
            if (el) el.style.display = (s === state) ? 'flex' : 'none';
        });
    }

    showError(message) {
        this.showState('error');
        const prefix = this.options.classPrefix;
        const errorMsg = this.modalElement?.querySelector(`.${prefix}-error-message`);
        if (errorMsg) errorMsg.textContent = message;
    }

    showSaveButton() {
        const prefix = this.options.classPrefix;
        const saveBtn = this.modalElement?.querySelector(`.${prefix}-save`);
        if (saveBtn) saveBtn.style.display = 'block';
    }

    // ==================== Batch Tag Validation ====================

    async validateAndCacheTag(tag) {
        const normalized = tag?.toLowerCase().trim();
        if (!normalized) return;
        if (this.tagResolutionCache.has(normalized)) return;
        if (this.isCancelled) return;

        try {
            const response = await this.fetchWithAbort('/api/tags/batch-validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ names: [normalized] })
            });

            if (response.ok) {
                const data = await response.json();
                const resolved = (data.resolved && data.resolved[normalized]) || null;
                this.tagResolutionCache.set(normalized, resolved);
                if (this.tagInputHelper) {
                    this.tagInputHelper.tagValidationCache.set(normalized, !!resolved);
                }
            }
        } catch (e) {
            if (e.name === 'AbortError') throw e;
            console.error('Error validating tag:', e);
        }
    }

    async validateTags(tags, concurrency = 2, updateModalProgress = true) {
        const tagsToValidate = tags
            .map(t => t?.toLowerCase().trim())
            .filter(tag => tag && !this.tagResolutionCache.has(tag));

        if (tagsToValidate.length === 0) return;

        if (updateModalProgress) {
            this.updateProgress(0, tagsToValidate.length, window.i18n.t('bulk_modal.progress.validating_tags'), window.i18n.t('bulk_modal.progress.tags_checked'));
        }

        const chunkSize = 100;
        const chunks = [];
        for (let i = 0; i < tagsToValidate.length; i += chunkSize) {
            chunks.push(tagsToValidate.slice(i, i + chunkSize));
        }

        let processedCount = 0;

        const maxRetries = 2;
        const processChunkWithRetry = async (chunk, retryCount = maxRetries) => {
            if (this.isCancelled) return;
            try {
                const response = await this.fetchWithAbort('/api/tags/batch-validate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ names: chunk })
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: Failed to validate tags`);
                }

                const data = await response.json();
                const resolvedMap = data.resolved || {};

                chunk.forEach(tag => {
                    const resolved = resolvedMap[tag] || null;
                    this.tagResolutionCache.set(tag, resolved);
                    if (this.tagInputHelper) {
                        this.tagInputHelper.tagValidationCache.set(tag, !!resolved);
                    }
                });
            } catch (e) {
                if (e.name === 'AbortError' || this.isCancelled) throw e;
                if (retryCount > 0) {
                    const delay = 200 * Math.pow(2, maxRetries - retryCount);
                    await new Promise(r => setTimeout(r, delay));
                    return processChunkWithRetry(chunk, retryCount - 1);
                }
                console.error('Error validating tags batch:', e);
                // Do not poison cache with null on network/server errors
            } finally {
                processedCount += chunk.length;
                if (updateModalProgress && !this.isCancelled) {
                    this.updateProgress(Math.min(processedCount, tagsToValidate.length), tagsToValidate.length, window.i18n.t('bulk_modal.progress.validating_tags'), window.i18n.t('bulk_modal.progress.tags_checked'));
                }
            }
        };

        let chunkIndex = 0;
        const worker = async () => {
            while (chunkIndex < chunks.length && !this.isCancelled) {
                const currentChunk = chunks[chunkIndex++];
                await processChunkWithRetry(currentChunk);
            }
        };

        const workers = Array.from({ length: Math.min(concurrency, chunks.length) }, () => worker());
        await Promise.all(workers);
    }

    getResolvedTag(tag) {
        if (!tag) return null;
        const entry = this.tagResolutionCache.get(tag.toLowerCase().trim());
        if (!entry) return null;
        if (typeof entry === 'object') {
            return entry.name || null;
        }
        return entry;
    }

    getResolvedTagInfo(tag) {
        if (!tag) return null;
        return this.tagResolutionCache.get(tag.toLowerCase().trim()) || null;
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getHighlightTagsForItem(inputElement) {
        if (!inputElement) return null;
        const rawIndex = inputElement.getAttribute('data-index');
        if (rawIndex === null || rawIndex === undefined) return null;
        const index = parseInt(rawIndex, 10);
        if (isNaN(index) || !this.itemsData || !this.itemsData[index]) return null;

        const item = this.itemsData[index];
        const prefilledList = item.prefilledTags && item.prefilledTags.length > 0
            ? item.prefilledTags
            : (item.currentTags ? (item.newTags || []).filter(t => !new Set(item.currentTags.map(c => c.toLowerCase())).has(t.toLowerCase())) : null);
        if (!prefilledList || prefilledList.length === 0) return null;

        const prefilledSet = new Set(prefilledList.map(t => t.toLowerCase()));
        const rawText = this.tagInputHelper ? this.tagInputHelper.getPlainTextFromDiv(inputElement) : (inputElement.innerText || inputElement.textContent || '');
        const inputTags = rawText.split(/\s+/).filter(t => t.length > 0);
        const highlightTags = new Set();
        for (const t of inputTags) {
            if (prefilledSet.has(t.toLowerCase())) {
                highlightTags.add(t.toLowerCase());
            }
        }
        return highlightTags;
    }

    triggerValidation(input) {
        if (!this.tagInputHelper || !input) return;
        const highlightTags = this.getHighlightTagsForItem(input);

        this.tagInputHelper.validateAndStyleTags(input, {
            validationCache: this.tagInputHelper.tagValidationCache,
            checkFunction: (tag) => {
                const resolved = this.getResolvedTag ? this.getResolvedTag(tag) : null;
                if (resolved !== null && resolved !== undefined) return true;
                return this.tagInputHelper.checkTagExists(tag);
            },
            highlightTags: highlightTags
        });
    }

    // ==================== Lazy Input Helpers ====================

    initializeSingleInput(input) {
        if (!this.tagInputHelper || this.isCancelled || !input) return;
        if (input.dataset.initialized === 'true') return;

        input.dataset.initialized = 'true';
        const prefix = this.options.classPrefix;

        if (typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(input, {
                multipleValues: true,
                allowCreate: true,
                containerClasses: 'surface border border-color shadow-lg z-50',
                onSelect: () => {
                    this.triggerValidation(input);
                    const idx = parseInt(input.dataset.index);
                    if (!isNaN(idx)) this.syncInputState(input, idx);
                }
            });
        }

        this.tagInputHelper.setupTagInput(input, `${prefix}-${input.dataset.index}`, {
            onValidate: () => { },
            validationCache: this.tagInputHelper.tagValidationCache,
            checkFunction: (tag) => {
                const resolved = this.getResolvedTag ? this.getResolvedTag(tag) : null;
                if (resolved !== null && resolved !== undefined) return true;
                return this.tagInputHelper.checkTagExists(tag);
            },
            getHighlightTags: (inputElement) => this.getHighlightTagsForItem(inputElement)
        });

        this.triggerValidation(input);
    }

    // ==================== Rendering ====================

    renderItem(item, index) {
        const prefix = this.options.classPrefix;
        const currentTagsDisplay = item.currentTags && item.currentTags.length > 0
            ? item.currentTags.slice(0, 3).join(', ') + (item.currentTags.length > 3 ? ` (${window.i18n.t('bulk_modal.messages.tag_overflow', { count: item.currentTags.length - 3 })})` : '')
            : window.i18n.t('common.no_tags');

        const tagsToShow = item.newTags || [];

        const prefilledList = item.prefilledTags && item.prefilledTags.length > 0
            ? item.prefilledTags
            : (item.currentTags ? tagsToShow.filter(t => !new Set(item.currentTags.map(c => c.toLowerCase())).has(t.toLowerCase())) : []);
        const prefilledSet = new Set(prefilledList.map(t => t.toLowerCase()));

        const renderedContent = tagsToShow.map(tag => {
            const escaped = this.escapeHtml(tag);
            if (prefilledSet.has(tag.toLowerCase())) {
                return `<span class="new-tag">${escaped}</span>`;
            }
            return escaped;
        }).join(' ');

        return `
            <div class="${prefix}-item surface-light p-3 border mb-3" data-index="${index}" style="content-visibility: auto; contain-intrinsic-size: auto 120px;">
                <!-- Mobile: Stacked layout, Desktop: Side-by-side -->
                <div class="flex flex-col sm:flex-row gap-3">
                    <!-- Thumbnail -->
                    <div class="flex gap-3 sm:block flex-shrink-0">
                        <img src="/api/media/${item.mediaId}/thumbnail" 
                             alt="" 
                             class="w-16 h-16 sm:w-20 sm:h-20 object-cover flex-shrink-0 item-thumbnail cursor-pointer"
                             onerror="this.src='/static/images/no-thumbnail.png'">
                        
                        <!-- Mobile: Info next to thumbnail -->
                        <div class="flex-1 sm:hidden min-w-0">
                            <p class="text-sm font-medium truncate mb-1" title="${item.filename}">${item.filename}</p>
                            <p class="text-xs text-secondary line-clamp-2">${window.i18n.t('bulk_modal.messages.current')}${currentTagsDisplay}</p>
                        </div>
                    </div>
                    
                    <!-- Content -->
                    <div class="flex-1 min-w-0">
                        <!-- Desktop: Info above input -->
                        <div class="hidden sm:block">
                            <p class="text-sm font-medium truncate mb-1" title="${item.filename}">${item.filename}</p>
                            <p class="text-xs text-secondary mb-2">${window.i18n.t('bulk_modal.messages.current')}${currentTagsDisplay}</p>
                        </div>
                        
                        <!-- Input and buttons -->
                        <div class="flex gap-2 items-start">
                            <div class="relative flex-1 min-w-0">
                                <div class="${prefix}-input w-full bg px-3 py-2.5 sm:py-2 border text-sm focus:outline-none focus:border-primary hover:border-primary transition-colors min-h-[44px] sm:min-h-[36px]" 
                                     contenteditable="true"
                                     data-index="${index}"
                                     style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;">${renderedContent}</div>
                            </div>
                            
                            <!-- Action buttons -->
                            <div class="${prefix}-actions flex gap-1.5 flex-shrink-0 transition-all">
                                <button type="button" 
                                        class="${prefix}-refresh w-11 h-11 sm:w-9 sm:h-9 surface hover:surface-light text-secondary hover:text flex items-center justify-center transition-colors cursor-pointer"
                                        data-index="${index}"
                                        title="${window.i18n.t('bulk_modal.buttons.refresh_tags')}">
                                    ${window.Icons.wand({ size: 20, class: 'w-5 h-5 sm:w-4 sm:h-4' })}
                                </button>
                                <button type="button" 
                                        class="${prefix}-clear w-11 h-11 sm:w-9 sm:h-9 bg-danger hover:bg-danger tag-text flex items-center justify-center transition-colors cursor-pointer"
                                        data-index="${index}"
                                        title="${window.i18n.t('bulk_modal.buttons.clear_tags')}">
                                    ${window.Icons.trash({ size: 20, class: 'w-5 h-5 sm:w-4 sm:h-4' })}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    renderItems() {
        if (!this.modalElement || !this.itemsData) return;
        const prefix = this.options.classPrefix;
        const container = this.modalElement.querySelector(`.${prefix}-items`);
        if (!container) return;

        container.scrollTop = 0;
        const html = this.itemsData.map((item, index) => this.renderItem(item, index)).join('');
        container.innerHTML = html;
        const inputs = container.querySelectorAll(`.${prefix}-input`);
        inputs.forEach(input => this.triggerValidation(input));
    }

    // ==================== Button Feedback ====================
    flashButton(index, color, buttonType = 'refresh') {
        const prefix = this.options.classPrefix;
        const btn = this.modalElement?.querySelector(`.${prefix}-${buttonType}[data-index="${index}"]`);
        if (btn) {
            const originalColor = btn.style.color;
            btn.style.color = color;
            setTimeout(() => btn.style.color = originalColor, 500);
        }
    }

    // ==================== Atomic Bulk Save ====================

    async saveTags() {
        // Cancel any pending streaming/background fetch
        this.isCancelled = true;
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }

        const prefix = this.options.classPrefix;
        const saveBtn = this.modalElement?.querySelector(`.${prefix}-save`);

        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = window.i18n.t('modal.buttons.saving');
        }

        // Flush all inputs to itemsData first
        const container = this.modalElement?.querySelector(`.${prefix}-items`);
        if (container) {
            const inputs = container.querySelectorAll(`.${prefix}-input`);
            inputs.forEach(input => {
                const index = parseInt(input.dataset.index, 10);
                if (!isNaN(index)) {
                    this.flushInputState(input, index);
                }
            });
        }

        const updateItems = [];
        for (const item of this.itemsData) {
            const tags = item.newTags || [];
            const currentTags = item.currentTags || [];
            const currentSet = new Set(currentTags.map(t => (typeof t === 'string' ? t : '').toLowerCase()));
            const newSet = new Set(tags.map(t => (typeof t === 'string' ? t : '').toLowerCase()));

            const hasChanges = currentSet.size !== newSet.size ||
                [...newSet].some(t => !currentSet.has(t)) ||
                [...currentSet].some(t => !newSet.has(t));

            if (hasChanges) {
                updateItems.push({
                    id: item.mediaId,
                    tags: tags
                });
            }
        }

        let successCount = 0;
        let errorCount = 0;

        if (updateItems.length > 0) {
            try {
                const response = await fetch('/api/media/bulk-update-tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items: updateItems })
                });

                if (response.ok) {
                    const data = await response.json();
                    successCount = data.updated_count || updateItems.length;
                } else {
                    errorCount = updateItems.length;
                }
            } catch (e) {
                console.error('Error in atomic bulk save:', e);
                errorCount = updateItems.length;
            }
        }

        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = window.i18n.t('modal.buttons.save_all');
        }

        this.hide();

        if (typeof this.options.onSave === 'function') {
            this.options.onSave({ successCount, errorCount });
        }
        if (typeof app !== 'undefined' && app.showNotification) {
            if (successCount > 0) app.showNotification(window.i18n.t('bulk_modal.notifications.updated_success', { count: successCount }), 'success');
            if (errorCount > 0) app.showNotification(window.i18n.t('bulk_modal.notifications.updated_failed', { count: errorCount }), 'error');
        }
    }

    // ==================== Cleanup ====================

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

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkTagModalBase;
}
