class BulkWDTaggerModal {
    constructor(options = {}) {
        this.options = {
            id: options.id || 'bulk-wd-tagger-modal',
            onSave: options.onSave || null,
            onClose: options.onClose || null,
            closeOnEscape: options.closeOnEscape !== false,
            closeOnOutsideClick: options.closeOnOutsideClick !== false,
            ...options
        };

        this.modalElement = null;
        this.isVisible = false;
        this.selectedItems = new Set();
        this.bulkTagsData = [];

        // Cancellation support
        this.abortController = null;
        this.isCancelled = false;

        // Settings
        this.settings = {
            generalThreshold: 0.35,
            characterThreshold: 0.85,
            hideRatingTags: true,
            characterTagsFirst: true,
            modelName: 'wd-eva02-large-tagger-v3'
        };

        // Tag resolution cache
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
                    <h2 class="text-lg font-bold">Bulk AI Tag Prediction (WD Tagger)</h2>
                    <button class="bulk-wd-tagger-close text-secondary hover:text text-2xl leading-none">&times;</button>
                </div>
                
                <!-- Settings -->
                <div class="bulk-wd-tagger-settings mb-4 p-3 surface-light border text-sm" style="display: none;">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs text-secondary mb-1">General Confidence Threshold</label>
                            <input type="number" class="wd-general-threshold w-full px-2 py-1 border surface text-sm" 
                                   min="0" max="1" step="0.05" value="0.35">
                        </div>
                        <div>
                            <label class="block text-xs text-secondary mb-1">Character Confidence Threshold</label>
                            <input type="number" class="wd-character-threshold w-full px-2 py-1 border surface text-sm" 
                                   min="0" max="1" step="0.05" value="0.85">
                        </div>
                    </div>
                </div>
                
                <!-- Model Download Confirmation -->
                <div class="bulk-wd-tagger-download-confirm text-center py-8" style="display: none;">
                    <div class="mb-4">
                        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mx-auto text-warning">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                    </div>
                    <p class="text-secondary mb-2">The AI model needs to be downloaded first.</p>
                    <p class="text-secondary text-sm mb-4">
                        Model: <strong class="download-model-name">wd-eva02-large-tagger-v3</strong><br>
                        Size: approximately <strong class="download-model-size">~850 MB</strong>
                    </p>
                    <div class="flex justify-center gap-2">
                        <button class="bulk-wd-tagger-download-cancel px-4 py-2 surface-light text text-sm">
                            Cancel
                        </button>
                        <button class="bulk-wd-tagger-download-confirm-btn px-4 py-2 bg-primary tag-text text-sm">
                            Download & Continue
                        </button>
                    </div>
                </div>
                
                <!-- Model Downloading -->
                <div class="bulk-wd-tagger-downloading text-center py-8" style="display: none;">
                    <div class="mb-4">
                        <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent"></div>
                    </div>
                    <p class="text-secondary mb-2">Downloading AI model...</p>
                    <p class="text-secondary text-sm">This may take a few minutes depending on your connection.</p>
                    <p class="text-secondary text-xs mt-2">Model files are cached locally for future use.</p>
                </div>
                
                <!-- Loading/Processing state -->
                <div class="bulk-wd-tagger-loading text-center py-8" style="display: none;">
                    <p class="text-secondary bulk-wd-tagger-status">Initializing AI Tagger...</p>
                    <p class="text-secondary text-sm mt-2">
                        <span class="bulk-wd-tagger-progress">0</span> / <span class="bulk-wd-tagger-total">0</span> <span class="bulk-wd-tagger-phase">items processed</span>
                    </p>
                </div>
                
                <!-- Content with editable items -->
                <div class="bulk-wd-tagger-content flex-1 overflow-y-auto" style="display: none;">
                    <p class="text-secondary mb-4 text-sm">Review predicted tags for each item. Invalid tags are highlighted in red.</p>
                    <div class="bulk-wd-tagger-items space-y-3"></div>
                </div>
                
                <!-- Empty state -->
                <div class="bulk-wd-tagger-empty text-center py-8" style="display: none;">
                    <p class="text-secondary">No new tags could be predicted for the selected items.</p>
                </div>
                
                <!-- Error state -->
                <div class="bulk-wd-tagger-error text-center py-8" style="display: none;">
                    <p class="text-danger bulk-wd-tagger-error-message">An error occurred.</p>
                </div>
                
                <!-- Cancelled state -->
                <div class="bulk-wd-tagger-cancelled text-center py-8" style="display: none;">
                    <p class="text-secondary">Operation cancelled.</p>
                </div>
                
                <div class="flex justify-between gap-2 mt-4 pt-4 border-t border-color bg-surface z-20">
                    <button class="bulk-wd-tagger-toggle-settings px-3 py-2 surface-light text text-sm">
                        Settings
                    </button>
                    <div class="flex gap-2">
                        <button class="bulk-wd-tagger-cancel px-4 py-2 surface-light transition-colors hover:surface-light text text-sm">
                            Cancel
                        </button>
                        <button class="bulk-wd-tagger-save px-4 py-2 bg-primary transition-colors hover:bg-primary tag-text text-sm" style="display: none;">
                            Save All
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this.modalElement = modal;
    }

    setupEventListeners() {
        if (!this.modalElement) return;

        const closeBtn = this.modalElement.querySelector('.bulk-wd-tagger-close');
        if (closeBtn) closeBtn.addEventListener('click', () => this.cancel());

        const cancelBtn = this.modalElement.querySelector('.bulk-wd-tagger-cancel');
        if (cancelBtn) cancelBtn.addEventListener('click', () => this.cancel());

        const saveBtn = this.modalElement.querySelector('.bulk-wd-tagger-save');
        if (saveBtn) saveBtn.addEventListener('click', () => this.saveAllTags());

        const toggleSettings = this.modalElement.querySelector('.bulk-wd-tagger-toggle-settings');
        if (toggleSettings) {
            toggleSettings.addEventListener('click', () => {
                const settings = this.modalElement.querySelector('.bulk-wd-tagger-settings');
                if (settings) {
                    settings.style.display = settings.style.display === 'none' ? 'block' : 'none';
                }
            });
        }

        // Download confirmation buttons
        const downloadCancelBtn = this.modalElement.querySelector('.bulk-wd-tagger-download-cancel');
        if (downloadCancelBtn) {
            downloadCancelBtn.addEventListener('click', () => this.cancel());
        }

        const downloadConfirmBtn = this.modalElement.querySelector('.bulk-wd-tagger-download-confirm-btn');
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

        // Event delegation for items
        const itemsContainer = this.modalElement.querySelector('.bulk-wd-tagger-items');
        if (itemsContainer) {
            itemsContainer.addEventListener('click', (e) => {
                const btn = e.target.closest('button');
                if (!btn) return;

                const index = btn.dataset.index;
                const input = this.modalElement.querySelector(`.bulk-wd-tag-input[data-index="${index}"]`);
                if (!input) return;

                if (btn.classList.contains('bulk-wd-tag-clear')) {
                    input.textContent = '';
                    this.triggerValidation(input);
                }

                if (btn.classList.contains('bulk-wd-tag-repredict')) {
                    this.repredictSingleItem(index, input);
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

        // Check model status first
        this.checkModelAndStart();

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
        // Set cancelled flag
        this.isCancelled = true;

        // Abort all pending fetch requests
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
        const states = [
            '.bulk-wd-tagger-loading',
            '.bulk-wd-tagger-content',
            '.bulk-wd-tagger-empty',
            '.bulk-wd-tagger-error',
            '.bulk-wd-tagger-cancelled',
            '.bulk-wd-tagger-download-confirm',
            '.bulk-wd-tagger-downloading'
        ];

        states.forEach(selector => {
            const el = this.modalElement.querySelector(selector);
            if (el) el.style.display = 'none';
        });

        const saveBtn = this.modalElement.querySelector('.bulk-wd-tagger-save');
        const itemsContainer = this.modalElement.querySelector('.bulk-wd-tagger-items');
        const settings = this.modalElement.querySelector('.bulk-wd-tagger-settings');

        if (saveBtn) saveBtn.style.display = 'none';
        if (itemsContainer) itemsContainer.innerHTML = '';
        if (settings) settings.style.display = 'none';

        this.bulkTagsData = [];
    }

    showState(state) {
        const states = [
            'loading', 'content', 'empty', 'error', 'cancelled',
            'download-confirm', 'downloading'
        ];

        states.forEach(s => {
            const el = this.modalElement.querySelector(`.bulk-wd-tagger-${s}`);
            if (el) el.style.display = s === state ? 'block' : 'none';
        });
    }

    updateProgress(current, total, status, phase) {
        const progress = this.modalElement.querySelector('.bulk-wd-tagger-progress');
        const totalEl = this.modalElement.querySelector('.bulk-wd-tagger-total');
        const statusEl = this.modalElement.querySelector('.bulk-wd-tagger-status');
        const phaseEl = this.modalElement.querySelector('.bulk-wd-tagger-phase');

        if (progress) progress.textContent = current;
        if (totalEl) totalEl.textContent = total;
        if (statusEl) statusEl.textContent = status;
        if (phaseEl) phaseEl.textContent = phase;
    }

    showError(message) {
        this.showState('error');
        const errorMsg = this.modalElement.querySelector('.bulk-wd-tagger-error-message');
        if (errorMsg) errorMsg.textContent = message;
    }

    async checkModelAndStart() {
        this.showState('loading');
        this.updateProgress(0, 0, 'Checking AI model status...', '');

        try {
            const response = await fetch(`/api/ai-tagger/model-status/${this.settings.modelName}`, {
                signal: this.abortController?.signal
            });

            if (this.isCancelled) return;

            if (!response.ok) {
                throw new Error('Failed to check model status');
            }

            const status = await response.json();

            if (status.is_downloaded || status.is_loaded) {
                // Model is ready, proceed
                this.predictAllTags();
            } else {
                // Need to download - show confirmation
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
            const response = await fetch(`/api/ai-tagger/download/${this.settings.modelName}`, {
                method: 'POST',
                signal: this.abortController?.signal
            });

            if (this.isCancelled) return;

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || 'Download failed');
            }

            // Model downloaded, now proceed with predictions
            this.predictAllTags();
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error downloading model:', e);
            this.showError(`Failed to download model: ${e.message}`);
        }
    }

    async fetchWithAbort(url, options = {}) {
        if (this.isCancelled) throw new DOMException('Cancelled', 'AbortError');

        return fetch(url, {
            ...options,
            signal: this.abortController?.signal
        });
    }

    async predictAllTags() {
        if (this.isCancelled) return;

        this.showState('loading');
        const saveBtn = this.modalElement.querySelector('.bulk-wd-tagger-save');
        const itemsContainer = this.modalElement.querySelector('.bulk-wd-tagger-items');

        const selectedArray = Array.from(this.selectedItems);
        const CONCURRENCY = 3;

        this.bulkTagsData = [];

        // Phase 1: Fetch media info
        const mediaInfoMap = new Map();
        let fetchProgress = 0;

        this.updateProgress(0, selectedArray.length, 'Fetching media info...', 'items fetched');

        const fetchMediaInfo = async (mediaId) => {
            if (this.isCancelled) return;
            try {
                const res = await this.fetchWithAbort(`/api/media/${mediaId}`);
                if (res.ok) {
                    const data = await res.json();
                    mediaInfoMap.set(mediaId, data);
                }
            } catch (e) {
                if (e.name === 'AbortError') throw e;
                console.error(`Error fetching media ${mediaId}:`, e);
            } finally {
                fetchProgress++;
                if (!this.isCancelled) {
                    this.updateProgress(fetchProgress, selectedArray.length, 'Fetching media info...', 'items fetched');
                }
            }
        };

        try {
            for (let i = 0; i < selectedArray.length; i += 10) {
                if (this.isCancelled) return;
                const chunk = selectedArray.slice(i, i + 10);
                await Promise.all(chunk.map(id => fetchMediaInfo(id)));
            }
        } catch (e) {
            if (e.name === 'AbortError') return;
            throw e;
        }

        if (this.isCancelled) return;

        // Phase 2: Predict tags
        let processed = 0;
        this.updateProgress(0, selectedArray.length, 'Predicting tags with AI...', 'items processed');

        const predictItem = async (mediaId) => {
            if (this.isCancelled) return;
            try {
                const result = await this.predictMediaTags(mediaId, mediaInfoMap.get(mediaId));
                if (result) {
                    this.bulkTagsData.push(result);
                }
            } catch (e) {
                if (e.name === 'AbortError') throw e;
                console.error(`Error predicting tags for media ${mediaId}:`, e);
            } finally {
                processed++;
                if (!this.isCancelled) {
                    this.updateProgress(processed, selectedArray.length, 'Predicting tags with AI...', 'items processed');
                }
            }
        };

        try {
            for (let i = 0; i < selectedArray.length; i += CONCURRENCY) {
                if (this.isCancelled) return;
                const chunk = selectedArray.slice(i, i + CONCURRENCY);
                await Promise.all(chunk.map(id => predictItem(id)));
            }
        } catch (e) {
            if (e.name === 'AbortError') return;
            throw e;
        }

        if (this.isCancelled) return;

        if (this.bulkTagsData.length === 0) {
            this.showState('empty');
            return;
        }

        // Phase 3: Validate tags (keep loading visible)
        this.updateProgress(0, 0, 'Validating tags...', '');
        await this.validatePredictedTags();

        if (this.isCancelled) return;

        // Render items
        if (itemsContainer) {
            itemsContainer.innerHTML = this.bulkTagsData.map((item, index) =>
                this.renderTagItem(item, index)
            ).join('');
        }

        await this.initializeInputHelpers(itemsContainer);

        if (this.isCancelled) return;

        this.showState('content');
        if (saveBtn) saveBtn.style.display = 'block';
    }

    async predictMediaTags(mediaId, mediaData) {
        if (this.isCancelled) return null;

        try {
            const response = await this.fetchWithAbort(`/api/ai-tagger/predict/${mediaId}`, {
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
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || 'Prediction failed');
            }

            const result = await response.json();
            const currentTags = (mediaData?.tags || []).map(t => t.name || t);
            const currentTagsSet = new Set(currentTags.map(t => t.toLowerCase()));

            const predictedTags = result.tags
                .map(t => t.name.replace(/ /g, '_'))
                .filter(t => !currentTagsSet.has(t.toLowerCase()));

            if (predictedTags.length > 0) {
                return {
                    mediaId,
                    currentTags,
                    predictedTags,
                    filename: mediaData?.filename || `Media ${mediaId}`
                };
            }
        } catch (e) {
            if (e.name === 'AbortError') throw e;
            console.error(`Error predicting tags for media ${mediaId}:`, e);
        }
        return null;
    }

    async validatePredictedTags() {
        if (this.isCancelled) return;

        const allTags = new Set();
        for (const item of this.bulkTagsData) {
            item.predictedTags.forEach(tag => allTags.add(tag.toLowerCase()));
        }

        const tagsToValidate = Array.from(allTags).filter(tag => !this.tagResolutionCache.has(tag));

        if (tagsToValidate.length === 0) {
            this.applyValidatedTags();
            return;
        }

        let validationProgress = 0;
        const VALIDATION_CONCURRENCY = 20;

        this.updateProgress(0, tagsToValidate.length, 'Validating tags...', 'tags checked');

        const validateTag = async (tag) => {
            if (this.isCancelled) return;
            await this.validateAndCacheTag(tag);
            validationProgress++;
            if (!this.isCancelled) {
                this.updateProgress(validationProgress, tagsToValidate.length, 'Validating tags...', 'tags checked');
            }
        };

        try {
            for (let i = 0; i < tagsToValidate.length; i += VALIDATION_CONCURRENCY) {
                if (this.isCancelled) return;
                const chunk = tagsToValidate.slice(i, i + VALIDATION_CONCURRENCY);
                await Promise.all(chunk.map(tag => validateTag(tag)));
            }
        } catch (e) {
            if (e.name === 'AbortError') return;
            throw e;
        }

        this.applyValidatedTags();
    }

    applyValidatedTags() {
        for (const item of this.bulkTagsData) {
            item.validTags = item.predictedTags.filter(tag => {
                const resolved = this.tagResolutionCache.get(tag.toLowerCase());
                return resolved !== null;
            }).map(tag => {
                const resolved = this.tagResolutionCache.get(tag.toLowerCase());
                return resolved || tag;
            });
        }
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

    async repredictSingleItem(index, inputElement) {
        const item = this.bulkTagsData[index];
        if (!item || this.isCancelled) return;

        inputElement.style.opacity = '0.5';

        try {
            const mediaRes = await this.fetchWithAbort(`/api/media/${item.mediaId}`);
            const mediaData = mediaRes.ok ? await mediaRes.json() : { tags: [] };

            const result = await this.predictMediaTags(item.mediaId, mediaData);

            if (result && result.predictedTags.length > 0) {
                for (const tag of result.predictedTags) {
                    if (!this.tagResolutionCache.has(tag.toLowerCase())) {
                        await this.validateAndCacheTag(tag.toLowerCase());
                    }
                }

                const validTags = result.predictedTags.filter(tag => {
                    const resolved = this.tagResolutionCache.get(tag.toLowerCase());
                    return resolved !== null;
                }).map(tag => {
                    const resolved = this.tagResolutionCache.get(tag.toLowerCase());
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

    flashButton(index, color) {
        const btn = this.modalElement.querySelector(`.bulk-wd-tag-repredict[data-index="${index}"]`);
        if (btn) {
            const originalColor = btn.style.color;
            btn.style.color = color;
            setTimeout(() => btn.style.color = originalColor, 500);
        }
    }

    async initializeInputHelpers(container) {
        if (!this.tagInputHelper || this.isCancelled) return;

        const inputs = container.querySelectorAll('.bulk-wd-tag-input');
        for (const input of inputs) {
            if (this.isCancelled) return;

            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(input, {
                    multipleValues: true,
                    containerClasses: 'surface border border-color shadow-lg z-50',
                    onSelect: () => this.triggerValidation(input)
                });
            }

            this.tagInputHelper.setupTagInput(input, `bulk-wd-tag-${input.dataset.index}`, {
                onValidate: () => { },
                validationCache: this.tagInputHelper.tagValidationCache,
                checkFunction: (tag) => this.tagInputHelper.checkTagExists(tag)
            });

            await new Promise(r => setTimeout(r, 0));
            this.triggerValidation(input);
        }
    }

    renderTagItem(item, index) {
        const currentTagsDisplay = item.currentTags.length > 0
            ? item.currentTags.slice(0, 5).join(', ') + (item.currentTags.length > 5 ? ` (+${item.currentTags.length - 5} more)` : '')
            : 'No tags';

        const tagsToShow = item.validTags || item.predictedTags || [];

        return `
            <div class="bulk-wd-tag-item surface-light p-3 border" data-index="${index}">
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
                                <div class="bulk-wd-tag-input w-full bg px-2 py-1 border text-sm focus:outline-none focus:border-primary" 
                                     contenteditable="true"
                                     data-index="${index}"
                                     style="white-space: pre-wrap; overflow-wrap: break-word;">${tagsToShow.join(' ')}</div>
                            </div>
                            
                            <div class="flex flex-row gap-1">
                                <button type="button" 
                                        class="bulk-wd-tag-repredict px-2 py-1 surface text-secondary hover:surface-light hover:text-white h-[1.8rem] w-[2rem] flex items-center justify-center transition-colors"
                                        data-index="${index}"
                                        title="Re-predict tags">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path>
                                    </svg>
                                </button>
                                <button type="button" 
                                        class="bulk-wd-tag-clear px-2 py-1 bg-danger tag-text hover:bg-danger h-[1.8rem] w-[2rem] flex items-center justify-center transition-colors"
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

    async saveAllTags() {
        const saveBtn = this.modalElement.querySelector('.bulk-wd-tagger-save');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
        }

        let successCount = 0;
        let errorCount = 0;

        const SAVE_CONCURRENCY = 5;

        const saveItem = async (index) => {
            const item = this.bulkTagsData[index];
            const input = this.modalElement.querySelector(`.bulk-wd-tag-input[data-index="${index}"]`);

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

        const indices = this.bulkTagsData.map((_, i) => i);
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

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkWDTaggerModal;
}
