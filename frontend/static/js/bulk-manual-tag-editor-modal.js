class BulkManualTagEditorModal extends BulkTagModalBase {
    constructor(options = {}) {
        super({
            id: 'bulk-manual-tag-editor-modal',
            title: window.i18n.t('bulk_modal.manual.title'),
            classPrefix: 'bulk-manual',
            emptyMessage: window.i18n.t('bulk_modal.manual.empty_message'),
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
            ${this.getCancelledHTML()}
        `;
    }

    async fetchTags() {
        if (this.isCancelled) return;

        this.showState('loading');
        const prefix = this.options.classPrefix;
        const itemsContainer = this.modalElement.querySelector(`.${prefix}-items`);

        const selectedArray = Array.from(this.selectedItems);

        // Fetch media data in batch
        this.updateProgress(0, selectedArray.length, window.i18n.t('bulk_modal.progress.fetching_metadata'), window.i18n.t('bulk_modal.progress.items_fetched'));

        try {
            const idsParam = selectedArray.join(',');
            const res = await this.fetchWithAbort(`/api/media/batch?ids=${idsParam}`);

            if (!res.ok) throw new Error('Failed to fetch media');

            const data = await res.json();
            const items = data.items || [];

            if (items.length === 0) {
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
                return {
                    mediaId: item.id,
                    currentTags: [...currentTags],
                    newTags: [...currentTags],
                    filename: item.filename || window.i18n.t('bulk_modal.ai_tags.default_media_name', { id: item.id })
                };
            });

            this.renderItems();
            await this.initializeInputHelpers(itemsContainer);

            if (this.isCancelled) return;

            this.showState('content');
            this.showSaveButton();

        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error fetching tags:', e);
            this.showError(window.i18n.t('bulk_modal.messages.error_occurred'));
        }
    }

    // Override saveTags to replace tags instead of merging
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

            let finalTags = [];
            if (this.tagInputHelper) {
                finalTags = this.tagInputHelper.getValidTagsFromInput(input);
            } else {
                finalTags = input.innerText.trim().split(/\s+/).filter(t => t.length > 0);
            }

            try {
                const response = await fetch(`/api/media/${item.mediaId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tags: finalTags })
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
                    return tagObj ? tagObj : { name: tagName, category: 'general' }; // Default to general if unknown
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
                const newValue = sortedTagNames.join(' ');
                inputElement.textContent = newValue;
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
