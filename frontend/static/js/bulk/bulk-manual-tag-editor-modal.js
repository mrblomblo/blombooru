class BulkManualTagEditorModal extends BulkTagModalBase {
    constructor(options = {}) {
        super({
            id: 'bulk-manual-tag-editor-modal',
            title: window.i18n.t('common.manual_tag_editor'),
            classPrefix: 'bulk-manual',
            emptyMessage: window.i18n.t('bulk_modal.manual.empty_message'),
            closeOnOutsideClick: false,
            ...options
        });

        this.init();
    }

    getContentHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-content flex-1 flex flex-col min-h-0" style="display: none;">
                <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3 flex-shrink-0">
                    <p class="text-secondary text-xs sm:text-sm">${window.i18n.t('bulk_modal.messages.review_tags')}</p>
                    ${this.getHideImpliedCheckboxHTML()}
                </div>
                <div class="flex gap-2 mb-3 flex-shrink-0 items-start relative z-20">
                    <div class="relative flex-1 min-w-0">
                        <div id="${prefix}-quick-input"
                            contenteditable="true"
                            data-placeholder="${window.i18n.t('bulk_modal.manual.quick_apply_placeholder')}"
                            class="bulk-manual-quick-input w-full bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary min-h-[34px]"
                            style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;"></div>
                    </div>
                    <button id="${prefix}-quick-add" class="btn-primary px-3 py-2 text-xs flex-shrink-0 cursor-pointer">${window.i18n.t('common.add')}</button>
                    <button id="${prefix}-quick-remove" class="btn-danger px-3 py-2 text-xs flex-shrink-0 cursor-pointer">${window.i18n.t('common.remove')}</button>
                </div>
                <div class="${prefix}-items space-y-3 overflow-y-auto flex-1 -mx-4 px-4 pb-2" style="overscroll-behavior: contain;"></div>
            </div>
        `;
    }

    setupAdditionalEventListeners() {
        const prefix = this.options.classPrefix;

        const quickInput = this.modalElement?.querySelector(`#${prefix}-quick-input`);
        const addBtn = this.modalElement?.querySelector(`#${prefix}-quick-add`);
        const removeBtn = this.modalElement?.querySelector(`#${prefix}-quick-remove`);

        if (!quickInput || !addBtn || !removeBtn) return;

        this.quickImpliedTagsMap = new Map();
        this.quickExpandedTriggers = new Set();
        this.quickHiddenImpliedTags = new Set();

        if (typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(quickInput, {
                multipleValues: true,
                allowCreate: true,
                containerClasses: 'surface border border-color shadow-lg z-50',
                onSelect: () => this.triggerValidation(quickInput)
            });
        }

        if (this.tagInputHelper) {
            this.tagInputHelper.setupTagInput(quickInput, `${prefix}-quick`, {
                onValidate: () => { },
                validationCache: this.tagInputHelper.tagValidationCache,
                checkFunction: (tag) => this.tagInputHelper.checkTagExists(tag),
                getHighlightTags: () => null,
                getImpliedTags: () => this.quickImpliedTagsMap,
                getHiddenImpliedTags: () => this.quickHiddenImpliedTags,
                getExpandedTriggers: () => this.quickExpandedTriggers,
                onImplicationExpanded: (impliedByMap, impliedTags) => {
                    for (const tagName of (impliedTags || [])) {
                        const lower = String(tagName || '').toLowerCase().trim();
                        if (!lower) continue;
                        const groups = (impliedByMap && impliedByMap[lower]) || (impliedByMap && impliedByMap[tagName]) || [];
                        const existingGroups = this.quickImpliedTagsMap.get(lower) || [];
                        const merged = [...existingGroups];
                        for (const g of groups) {
                            if (Array.isArray(g) && !merged.some(eg => JSON.stringify(eg) === JSON.stringify(g))) {
                                merged.push(g);
                            }
                        }
                        this.quickImpliedTagsMap.set(lower, merged);
                    }
                },
                isHideImpliedActive: () => false
            });
            this.triggerValidation(quickInput);
        }

        addBtn.addEventListener('click', () => this._applyQuickTags('add'));
        removeBtn.addEventListener('click', () => this._applyQuickTags('remove'));
    }

    async _applyQuickTags(action) {
        const prefix = this.options.classPrefix;
        const quickInput = this.modalElement?.querySelector(`#${prefix}-quick-input`);
        if (!quickInput) return;

        let resolvedTags;
        if (this.tagInputHelper) {
            resolvedTags = this.tagInputHelper.getValidTagsFromInput(quickInput);
        } else {
            const raw = quickInput.innerText.trim();
            resolvedTags = [...new Set(raw.split(/\s+/).filter(t => t.length > 0))];
        }

        if (resolvedTags.length === 0) return;

        if (action === 'add') {
            let explicitTags = [];
            let impliedTags = [];
            let impliedBy = {};

            if (this.quickImpliedTagsMap instanceof Map && this.quickImpliedTagsMap.size > 0) {
                for (const tag of resolvedTags) {
                    const lower = tag.toLowerCase().trim();
                    if (this.quickImpliedTagsMap.has(lower)) {
                        impliedTags.push(tag);
                        impliedBy[lower] = this.quickImpliedTagsMap.get(lower) || [];
                    } else {
                        explicitTags.push(tag);
                    }
                }
            } else {
                explicitTags = [...resolvedTags];
            }

            if (explicitTags.length > 0) {
                try {
                    const res = await fetch('/api/tag-implications/expand', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tags: explicitTags })
                    });
                    if (res.ok) {
                        const data = await res.json();
                        for (const imp of (data.implied_tags || [])) {
                            const impLower = imp.toLowerCase().trim();
                            if (!impliedTags.some(t => t.toLowerCase().trim() === impLower) &&
                                !explicitTags.some(t => t.toLowerCase().trim() === impLower)) {
                                impliedTags.push(imp);
                            }
                            if (data.implied_by && data.implied_by[impLower]) {
                                const existing = impliedBy[impLower] || [];
                                const merged = [...existing];
                                for (const g of data.implied_by[impLower]) {
                                    if (Array.isArray(g) && !merged.some(eg => JSON.stringify(eg) === JSON.stringify(g))) {
                                        merged.push(g);
                                    }
                                }
                                impliedBy[impLower] = merged;
                            }
                        }
                    }
                } catch (e) {
                    console.error('Error expanding quick tags implications:', e);
                }
            }

            const hideActive = this.isHideImpliedEnabled();

            this.itemsData.forEach(item => {
                if (!(item.impliedTagsMap instanceof Map)) item.impliedTagsMap = new Map();
                if (!(item.hiddenImpliedTags instanceof Set)) item.hiddenImpliedTags = new Set();
                if (!(item.expandedTriggers instanceof Set)) item.expandedTriggers = new Set();
                if (!Array.isArray(item.prefilledTags)) item.prefilledTags = [];
                if (!Array.isArray(item.newTags)) item.newTags = [];

                const effectiveTags = this.getEffectiveItemTags(item);
                const currentEffectiveSet = new Set(effectiveTags.map(t => t.toLowerCase().trim()));

                // 1. Explicit tags:
                for (const t of explicitTags) {
                    const lower = t.toLowerCase().trim();
                    if (!lower) continue;

                    // If it was previously implied on this item, promote to explicit
                    if (item.impliedTagsMap.has(lower)) {
                        item.impliedTagsMap.delete(lower);
                    }
                    if (item.hiddenImpliedTags.has(lower)) {
                        item.hiddenImpliedTags.delete(lower);
                    }

                    if (!item.newTags.some(existing => existing.toLowerCase().trim() === lower)) {
                        item.newTags.push(t);
                    }
                    if (!item.prefilledTags.some(existing => existing.toLowerCase().trim() === lower)) {
                        item.prefilledTags.push(t);
                    }
                    item.expandedTriggers.add(lower);
                }

                // 2. Implied tags:
                for (const t of impliedTags) {
                    const lower = t.toLowerCase().trim();
                    if (!lower) continue;

                    const groups = impliedBy[lower] || [];

                    // If tag was already explicit on the item, keep it explicit
                    if (currentEffectiveSet.has(lower) && !item.impliedTagsMap.has(lower)) {
                        continue;
                    }

                    const existingGroups = item.impliedTagsMap.get(lower) || [];
                    const merged = [...existingGroups];
                    for (const g of groups) {
                        if (Array.isArray(g) && !merged.some(eg => JSON.stringify(eg) === JSON.stringify(g))) {
                            merged.push(g);
                        }
                    }
                    item.impliedTagsMap.set(lower, merged);
                    item.expandedTriggers.add(lower);

                    if (hideActive) {
                        item.hiddenImpliedTags.add(lower);
                        item.newTags = item.newTags.filter(existing => existing.toLowerCase().trim() !== lower);
                    } else {
                        if (!item.newTags.some(existing => existing.toLowerCase().trim() === lower)) {
                            item.newTags.push(t);
                        }
                    }
                }
            });
        } else {
            const toRemoveSet = new Set(resolvedTags.map(t => t.toLowerCase().trim()));
            this.itemsData.forEach(item => {
                if (Array.isArray(item.newTags)) {
                    item.newTags = item.newTags.filter(t => !toRemoveSet.has(t.toLowerCase().trim()));
                }
                if (item.hiddenImpliedTags instanceof Set) {
                    for (const rem of toRemoveSet) {
                        item.hiddenImpliedTags.delete(rem);
                    }
                }
                if (item.impliedTagsMap instanceof Map) {
                    for (const rem of toRemoveSet) {
                        item.impliedTagsMap.delete(rem);
                    }
                }
                if (item.expandedTriggers instanceof Set) {
                    for (const rem of toRemoveSet) {
                        item.expandedTriggers.delete(rem);
                    }
                }
                if (Array.isArray(item.prefilledTags)) {
                    item.prefilledTags = item.prefilledTags.filter(t => !toRemoveSet.has(t.toLowerCase().trim()));
                }
            });
        }

        // Re-render items in DOM
        this.renderItems();

        quickInput.textContent = '';
        if (this.quickImpliedTagsMap instanceof Map) this.quickImpliedTagsMap.clear();
        if (this.quickExpandedTriggers instanceof Set) this.quickExpandedTriggers.clear();
        if (this.quickHiddenImpliedTags instanceof Set) this.quickHiddenImpliedTags.clear();
        this.triggerValidation(quickInput);
    }

    reset() {
        super.reset();
        const prefix = this.options.classPrefix;
        const quickInput = this.modalElement?.querySelector(`#${prefix}-quick-input`);
        if (quickInput) {
            quickInput.textContent = '';
            this.triggerValidation(quickInput);
        }
        if (this.quickImpliedTagsMap instanceof Map) this.quickImpliedTagsMap.clear();
        if (this.quickExpandedTriggers instanceof Set) this.quickExpandedTriggers.clear();
        if (this.quickHiddenImpliedTags instanceof Set) this.quickHiddenImpliedTags.clear();
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

        try {
            // Concurrent chunked fetching with live progress updates
            const items = await this.fetchMediaInChunks(selectedArray, {
                chunkSize: 50,
                concurrency: 3,
                projection: 'tags_only',
                statusText: window.i18n.t('bulk_modal.progress.fetching_metadata'),
                phaseText: window.i18n.t('bulk_modal.progress.items_fetched')
            });

            if (this.isCancelled) return;

            if (!items || items.length === 0) {
                this.showState('empty');
                return;
            }

            // Process items
            const categoryOrder = ['artist', 'character', 'copyright', 'general', 'meta'];
            this.itemsData = items.map(item => {
                let tags = item.tags || [];

                // Sort tags if they are objects with category
                tags.sort((a, b) => {
                    const catA = a.category ? categoryOrder.indexOf(a.category) : 3;
                    const catB = b.category ? categoryOrder.indexOf(b.category) : 3;

                    const orderA = catA === -1 ? 99 : catA;
                    const orderB = catB === -1 ? 99 : catB;

                    if (orderA !== orderB) return orderA - orderB;

                    const nameA = a.name || a;
                    const nameB = b.name || b;
                    return nameA.localeCompare(nameB);
                });

                const currentTags = tags.map(t => t.name || t);
                let newTags = [...currentTags];
                let prefilledTags = [];

                if (this.options.removeTags && this.options.removeTags[item.id]) {
                    const removed = this.options.removeTags[item.id];
                    newTags = newTags.filter(t => !removed.includes(t));
                }

                if (this.options.prefillTags && this.options.prefillTags[item.id]) {
                    const added = this.options.prefillTags[item.id];
                    added.forEach(t => {
                        if (!newTags.includes(t)) {
                            newTags.push(t);
                            prefilledTags.push(t);
                        }
                    });
                }

                const currentSet = new Set(currentTags);
                const newSet = new Set(newTags);
                const hasChanges = currentSet.size !== newSet.size || [...currentSet].some(t => !newSet.has(t));

                if (!hasChanges && (this.options.removeTags || this.options.prefillTags)) {
                    return null;
                }

                const itemObj = {
                    mediaId: item.id,
                    currentTags: [...currentTags],
                    newTags: newTags,
                    prefilledTags: prefilledTags,
                    filename: item.filename || window.i18n.t('bulk_modal.ai_tags.default_media_name', { id: item.id })
                };
                const prefillImpliedBy = this.options.prefillImpliedBy
                    ? this.options.prefillImpliedBy[item.id]
                    : null;
                return this.initItemImplicationState(itemObj, tags, prefillImpliedBy);
            }).filter(Boolean);

            if (this.itemsData.length === 0) {
                this.showState('empty');
                return;
            }

            this.renderItems();

            if (this.isCancelled) return;

            this.showState('content');
            this.showSaveButton();

        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error fetching tags:', e);
            this.showError(window.i18n.t('notifications.error_occurred'));
        }
    }

    // Atomic bulk save
    async saveTags() {
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

        // Build list of items to update from authoritative itemsData
        const updateItems = [];
        for (let i = 0; i < this.itemsData.length; i++) {
            const item = this.itemsData[i];
            const tags = this.getEffectiveItemTags(item);
            const impliedTagsPayload = this.getItemImpliedTagsPayload(item, tags);
            updateItems.push({
                id: item.mediaId,
                tags: tags,
                implied_tags: impliedTagsPayload
            });
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
                console.error('Error saving tags in bulk:', e);
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

    async refreshSingleItem(index, inputElement) {
        const item = this.itemsData[index];
        if (!item || this.isCancelled) return;

        inputElement.style.opacity = '0.5';

        try {
            // Fetch authoritative tags
            const response = await this.fetchWithAbort(`/api/media/${item.mediaId}`);
            if (!response.ok) throw new Error('Failed to fetch media');

            const mediaData = await response.json();
            const serverTags = (mediaData.tags || []).map(t => t.name || t);

            // Get current input tags
            let currentInputTags = [];
            if (this.tagInputHelper) {
                currentInputTags = this.tagInputHelper.getValidTagsFromInput(inputElement);
            } else {
                currentInputTags = inputElement.innerText.trim().split(/\s+/).filter(t => t.length > 0);
            }

            const uniqueTags = new Set([...serverTags, ...currentInputTags]);
            const mergedTags = Array.from(uniqueTags);

            // Resolve tags to get categories for sorting
            let tagObjects = [];
            if (this.tagInputHelper) {
                const limit = 100; // Batch limit safe guard
                const batches = [];
                for (let i = 0; i < mergedTags.length; i += limit) {
                    batches.push(mergedTags.slice(i, i + limit));
                }

                const resolvedBatches = await Promise.all(batches.map(batch => this.tagInputHelper.checkTagsBatch(batch)));
                const resolvedMap = Object.assign({}, ...resolvedBatches);

                tagObjects = mergedTags.map(tagName => {
                    const tagObj = resolvedMap[tagName.toLowerCase()];
                    return tagObj ? tagObj : { name: tagName, category: 'general' };
                });
            } else {
                // Likely not needed, but just in case
                tagObjects = mergedTags.map(t => ({ name: t, category: 'general' }));
            }

            // Sort tags
            const categoryOrder = ['artist', 'character', 'copyright', 'general', 'meta'];
            tagObjects.sort((a, b) => {
                const catA = categoryOrder.indexOf(a.category);
                const catB = categoryOrder.indexOf(b.category);

                // If category for some reason is not found in list, push to end
                const orderA = catA === -1 ? 99 : catA;
                const orderB = catB === -1 ? 99 : catB;

                if (orderA !== orderB) return orderA - orderB;
                return a.name.localeCompare(b.name);
            });

            const sortedTagNames = tagObjects.map(t => t.name);

            // Check if anything actually changed from what's currently in input
            const inputSet = new Set(currentInputTags.map(t => t.toLowerCase()));
            const mergedSet = new Set(mergedTags.map(t => t.toLowerCase()));

            let changed = false;
            if (inputSet.size !== mergedSet.size) {
                changed = true;
            } else {
                for (const t of mergedSet) {
                    if (!inputSet.has(t)) {
                        changed = true;
                        break;
                    }
                }
            }

            if (!changed) {
                const currentNormalized = currentInputTags.map(t => t.toLowerCase());
                const sortedNormalized = sortedTagNames.map(t => t.toLowerCase());

                // Check order
                for (let i = 0; i < currentNormalized.length; i++) {
                    if (currentNormalized[i] !== sortedNormalized[i]) {
                        changed = true;
                        break;
                    }
                }
            }

            if (changed) {
                if (!(item.impliedTagsMap instanceof Map)) item.impliedTagsMap = new Map();
                if (!(item.hiddenImpliedTags instanceof Set)) item.hiddenImpliedTags = new Set();
                for (const t of (mediaData.tags || [])) {
                    if (typeof t === 'object' && t !== null && t.implied) {
                        const lower = (t.name || '').toLowerCase().trim();
                        if (lower && !item.impliedTagsMap.has(lower)) {
                            item.impliedTagsMap.set(lower, Array.isArray(t.implied_by) ? t.implied_by : []);
                        }
                    }
                }
                if (this.isHideImpliedEnabled()) {
                    const visible = [];
                    for (const t of sortedTagNames) {
                        const lower = t.toLowerCase().trim();
                        if (item.impliedTagsMap.has(lower)) {
                            item.hiddenImpliedTags.add(lower);
                        } else {
                            visible.push(t);
                        }
                    }
                    item.newTags = visible;
                    inputElement.textContent = visible.join(' ');
                } else {
                    item.newTags = sortedTagNames;
                    inputElement.textContent = sortedTagNames.join(' ');
                }
                this.triggerValidation(inputElement);
                this.flashButton(index, 'var(--primary)');
            } else {
                this.flashButton(index, 'var(--secondary)');
            }

        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error(`Error refreshing item ${index}:`, e);
            this.flashButton(index, 'var(--danger)');
        } finally {
            inputElement.style.opacity = '1';
        }
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkManualTagEditorModal;
}
