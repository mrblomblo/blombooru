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
        this.isCancelled = false;

        // Tag resolution cache - persists across modal opens
        this.tagResolutionCache = new Map();

        // Initialize the helper class
        this.tagInputHelper = typeof TagInputHelper !== 'undefined' ? new TagInputHelper() : null;

        this.fullscreenViewer = new FullscreenMediaViewer();

        // Resize observer for dynamic button layout
        this.resizeObserver = null;
    }

    // ==================== Abstract Methods ====================

    getStates() {
        return ['loading', 'content', 'empty', 'cancelled'];
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
                <div class="flex justify-between items-center p-4 border-b border-color flex-shrink-0">
                    <h2 class="text-base sm:text-lg font-bold truncate pr-4">${this.options.title}</h2>
                    <button class="${prefix}-close flex items-center justify-center w-10 h-10 sm:w-8 sm:h-8 rounded-full surface-light hover:bg-danger hover:tag-text transition-colors" aria-label="Close">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5 sm:w-4 sm:h-4">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                    </button>
                </div>
                
                <!-- Body -->
                <div class="flex-1 overflow-hidden p-4">
                    ${this.getBodyHTML()}
                </div>
                
                <!-- Footer -->
                <div class="flex-shrink-0 p-4 border-t border-color bg-surface">
                    <div class="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3">
                        ${footerLeft ? `
                            <div class="flex gap-2">
                                ${footerLeft}
                            </div>
                        ` : ''}
                        <div class="flex gap-2 ${footerLeft ? '' : 'sm:ml-auto'}">
                            <button class="${prefix}-cancel flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 surface-light hover:surface-light text text-sm font-medium transition-colors">
                                ${window.i18n.t('modal.buttons.cancel')}
                            </button>
                            <button class="${prefix}-save flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 bg-primary hover:bg-primary tag-text text-sm font-medium transition-colors" style="display: none;">
                                ${window.i18n.t('modal.buttons.save_all')}
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

    getLoadingHTML(statusText) {
        if (!statusText) statusText = window.i18n.t('bulk_modal.progress.processing');
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-loading flex flex-col items-center justify-center h-full py-12" style="display: none;">
                <div class="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mb-4"></div>
                <p class="text-secondary ${prefix}-status text-center">${statusText}</p>
                <p class="text-secondary text-sm mt-2 text-center">
                    <span class="${prefix}-progress">0</span> / <span class="${prefix}-total">0</span> <span class="${prefix}-phase">${window.i18n.t('bulk_modal.progress.items_processed')}</span>
                </p>
            </div>
        `;
    }

    getContentHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-content h-full flex flex-col" style="display: none;">
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

    // ==================== Event Listeners ====================

    setupEventListeners() {
        if (!this.modalElement) return;

        const prefix = this.options.classPrefix;

        const closeBtn = this.modalElement.querySelector(`.${prefix}-close`);
        if (closeBtn) closeBtn.addEventListener('click', () => this.cancel());

        const cancelBtn = this.modalElement.querySelector(`.${prefix}-cancel`);
        if (cancelBtn) cancelBtn.addEventListener('click', () => this.cancel());

        const saveBtn = this.modalElement.querySelector(`.${prefix}-save`);
        if (saveBtn) saveBtn.addEventListener('click', () => this.saveTags());

        // Item action buttons (delegation)
        const itemsContainer = this.modalElement.querySelector(`.${prefix}-items`);
        if (itemsContainer) {
            itemsContainer.addEventListener('click', (e) => {
                const btn = e.target.closest('button');
                if (!btn) return;

                const index = parseInt(btn.dataset.index);
                const input = this.modalElement.querySelector(`.${prefix}-input[data-index="${index}"]`);
                if (!input) return;

                if (btn.classList.contains(`${prefix}-clear`)) {
                    input.textContent = '';
                    this.triggerValidation(input);
                }

                if (btn.classList.contains(`${prefix}-refresh`)) {
                    this.refreshSingleItem(index, input);
                }
            });

            // Thumbnail click listener
            itemsContainer.addEventListener('click', (e) => {
                if (e.target.classList.contains('item-thumbnail')) {
                    const itemDiv = e.target.closest(`.${prefix}-item`);
                    if (itemDiv) {
                        const index = parseInt(itemDiv.dataset.index);
                        const item = this.itemsData[index];
                        if (item && item.mediaId) {
                            const src = `/api/media/${item.mediaId}/file`;
                            // Detect if video based on filename extension
                            const isVideo = item.filename && /\.(mp4|webm|mov|avi|mkv)$/i.test(item.filename);
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

        this.setupAdditionalEventListeners();
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

        // Clean up observer
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }

        this.getStates().forEach(state => {
            const el = this.modalElement.querySelector(`.${prefix}-${state}`);
            if (el) el.style.display = 'none';
        });

        const saveBtn = this.modalElement.querySelector(`.${prefix}-save`);
        const itemsContainer = this.modalElement.querySelector(`.${prefix}-items`);

        if (saveBtn) saveBtn.style.display = 'none';
        if (itemsContainer) itemsContainer.innerHTML = '';

        this.itemsData = [];
    }

    showState(state) {
        const prefix = this.options.classPrefix;

        this.getStates().forEach(s => {
            const el = this.modalElement.querySelector(`.${prefix}-${s}`);
            if (el) el.style.display = s === state ? 'flex' : 'none';
        });
    }

    showError(message) {
        this.showState('error');
        const prefix = this.options.classPrefix;
        const errorMsg = this.modalElement.querySelector(`.${prefix}-error-message`);
        if (errorMsg) errorMsg.textContent = message;
    }

    showSaveButton() {
        const prefix = this.options.classPrefix;
        const saveBtn = this.modalElement.querySelector(`.${prefix}-save`);
        if (saveBtn) saveBtn.style.display = 'block';
    }

    // ==================== Progress Tracking ====================

    updateProgress(current, total, status, phase) {
        const prefix = this.options.classPrefix;

        const progress = this.modalElement.querySelector(`.${prefix}-progress`);
        const totalEl = this.modalElement.querySelector(`.${prefix}-total`);
        const statusEl = this.modalElement.querySelector(`.${prefix}-status`);
        const phaseEl = this.modalElement.querySelector(`.${prefix}-phase`);

        if (progress) progress.textContent = current;
        if (totalEl) totalEl.textContent = total;
        if (statusEl) statusEl.textContent = status;
        if (phaseEl) phaseEl.textContent = phase;
    }

    // ==================== Fetch Utilities ====================

    async fetchWithAbort(url, options = {}) {
        if (this.isCancelled) throw new DOMException('Cancelled', 'AbortError');

        return fetch(url, {
            ...options,
            signal: this.abortController?.signal
        });
    }

    async processBatch(items, processor, concurrency = 10) {
        for (let i = 0; i < items.length; i += concurrency) {
            if (this.isCancelled) return;
            const chunk = items.slice(i, i + concurrency);
            await Promise.all(chunk.map(item => processor(item)));
        }
    }

    // ==================== Tag Validation ====================

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

    async validateTags(tags, concurrency = 20) {
        const tagsToValidate = tags.filter(tag => !this.tagResolutionCache.has(tag.toLowerCase()));

        if (tagsToValidate.length === 0) return;

        this.updateProgress(0, tagsToValidate.length, window.i18n.t('bulk_modal.progress.validating_tags'), window.i18n.t('bulk_modal.progress.tags_checked'));

        try {
            // Use the batch endpoint for multiple tags
            const namesParam = tagsToValidate.map(n => encodeURIComponent(n.toLowerCase().trim())).join(',');
            const response = await this.fetchWithAbort(`/api/tags?names=${namesParam}`);

            if (response.ok) {
                const results = await response.json();
                const foundMap = new Map();
                results.forEach(t => foundMap.set(t.name.toLowerCase(), t.name));

                tagsToValidate.forEach(tag => {
                    const normalized = tag.toLowerCase().trim();
                    this.tagResolutionCache.set(tag, foundMap.get(normalized) || null);
                });
            } else {
                // Fallback to one-by-one if batch fails or is too large
                let progress = 0;
                const validateTag = async (tag) => {
                    if (this.isCancelled) return;
                    await this.validateAndCacheTag(tag);
                    progress++;
                    if (!this.isCancelled) {
                        this.updateProgress(progress, tagsToValidate.length, window.i18n.t('bulk_modal.progress.validating_tags'), window.i18n.t('bulk_modal.progress.tags_checked'));
                    }
                };
                await this.processBatch(tagsToValidate, validateTag, concurrency);
            }
        } catch (e) {
            if (e.name === 'AbortError') throw e;
            console.error('Error validating tags in batch:', e);
            // Fallback
            let progress = 0;
            const validateTag = async (tag) => {
                if (this.isCancelled) return;
                await this.validateAndCacheTag(tag);
                progress++;
                this.updateProgress(progress, tagsToValidate.length, window.i18n.t('bulk_modal.progress.validating_tags'), window.i18n.t('bulk_modal.progress.tags_checked'));
            };
            await this.processBatch(tagsToValidate, validateTag, concurrency);
        }

        this.updateProgress(tagsToValidate.length, tagsToValidate.length, window.i18n.t('bulk_modal.progress.validating_tags'), window.i18n.t('bulk_modal.progress.tags_checked'));
    }

    getResolvedTag(tag) {
        return this.tagResolutionCache.get(tag.toLowerCase());
    }

    triggerValidation(input) {
        if (this.tagInputHelper) {
            this.tagInputHelper.validateAndStyleTags(input, {
                validationCache: this.tagInputHelper.tagValidationCache,
                checkFunction: (tag) => this.tagInputHelper.checkTagExists(tag)
            });
        }
    }

    // ==================== Input Helpers ====================

    async initializeInputHelpers(container) {
        if (!this.tagInputHelper || this.isCancelled) return;

        const prefix = this.options.classPrefix;
        const inputs = container.querySelectorAll(`.${prefix}-input`);

        if (!this.resizeObserver) {
            this.resizeObserver = new ResizeObserver(entries => {
                for (const entry of entries) {
                    const input = entry.target;
                    const wrapper = input.parentElement;
                    const actions = wrapper.nextElementSibling;

                    if (!actions || !actions.classList.contains(`${prefix}-actions`)) continue;

                    // Compute line count
                    const style = window.getComputedStyle(input);
                    const lineHeight = parseFloat(style.lineHeight) || 20;
                    const paddingTop = parseFloat(style.paddingTop);
                    const paddingBottom = parseFloat(style.paddingBottom);

                    const contentHeight = input.clientHeight - paddingTop - paddingBottom;
                    const lines = contentHeight / lineHeight;

                    if (lines > 2.5) {
                        actions.classList.add('flex-col');
                    } else if (lines < 1.5) {
                        actions.classList.remove('flex-col');
                    }
                }
            });
        }

        for (const input of inputs) {
            if (this.isCancelled) return;

            this.resizeObserver.observe(input);

            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(input, {
                    multipleValues: true,
                    containerClasses: 'surface border border-color shadow-lg z-50',
                    onSelect: () => this.triggerValidation(input)
                });
            }

            this.tagInputHelper.setupTagInput(input, `${prefix}-${input.dataset.index}`, {
                onValidate: () => { },
                validationCache: this.tagInputHelper.tagValidationCache,
                checkFunction: (tag) => this.tagInputHelper.checkTagExists(tag)
            });

            await new Promise(r => setTimeout(r, 0));
            this.triggerValidation(input);
        }
    }

    // ==================== Rendering ====================

    renderItem(item, index) {
        const prefix = this.options.classPrefix;
        const currentTagsDisplay = item.currentTags.length > 0
            ? item.currentTags.slice(0, 3).join(', ') + (item.currentTags.length > 3 ? ` (${window.i18n.t('bulk_modal.messages.tag_overflow', { count: item.currentTags.length - 3 })})` : '')
            : window.i18n.t('bulk_modal.messages.no_tags');

        const tagsToShow = item.newTags || [];

        return `
            <div class="${prefix}-item surface-light p-3 border" data-index="${index}">
                <!-- Mobile: Stacked layout, Desktop: Side-by-side -->
                <div class="flex flex-col sm:flex-row gap-3">
                    <!-- Thumbnail -->
                    <div class="flex gap-3 sm:block">
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
                                <div class="${prefix}-input w-full bg px-3 py-2.5 sm:py-2 border text-sm focus:outline-none focus:border-primary min-h-[44px] sm:min-h-[36px]" 
                                     contenteditable="true"
                                     data-index="${index}"
                                     style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;">${tagsToShow.join(' ')}</div>
                            </div>
                            
                            <!-- Action buttons - Default Row, JS handles Col switch -->
                            <div class="${prefix}-actions flex gap-1.5 flex-shrink-0 transition-all">
                                <button type="button" 
                                        class="${prefix}-refresh w-11 h-11 sm:w-9 sm:h-9 surface hover:surface-light text-secondary hover:text-white flex items-center justify-center transition-colors"
                                        data-index="${index}"
                                        title="${window.i18n.t('bulk_modal.buttons.refresh_tags')}">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5 sm:w-4 sm:h-4">
                                        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path>
                                    </svg>
                                </button>
                                <button type="button" 
                                        class="${prefix}-clear w-11 h-11 sm:w-9 sm:h-9 bg-danger hover:bg-danger tag-text flex items-center justify-center transition-colors"
                                        data-index="${index}"
                                        title="${window.i18n.t('bulk_modal.buttons.clear_tags')}">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5 sm:w-4 sm:h-4">
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

    renderItems() {
        const prefix = this.options.classPrefix;
        const itemsContainer = this.modalElement.querySelector(`.${prefix}-items`);

        if (itemsContainer) {
            itemsContainer.innerHTML = this.itemsData.map((item, index) =>
                this.renderItem(item, index)
            ).join('');
        }
    }

    // ==================== Button Feedback ====================
    flashButton(index, color, buttonType = 'refresh') {
        const prefix = this.options.classPrefix;
        const btn = this.modalElement.querySelector(`.${prefix}-${buttonType}[data-index="${index}"]`);
        if (btn) {
            const originalColor = btn.style.color;
            btn.style.color = color;
            setTimeout(() => btn.style.color = originalColor, 500);
        }
    }

    // ==================== Save ====================

    async saveTags() {
        const prefix = this.options.classPrefix;
        const saveBtn = this.modalElement.querySelector(`.${prefix}-save`);

        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = window.i18n.t('modal.buttons.saving');
        }

        let successCount = 0;
        let errorCount = 0;

        const saveItem = async (index) => {
            const item = this.itemsData[index];
            const input = this.modalElement.querySelector(`.${prefix}-input[data-index="${index}"]`);

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

        const indices = this.itemsData.map((_, i) => i);
        await this.processBatch(indices, saveItem, 5);

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
