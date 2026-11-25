class BulkRatingModal extends BulkTagModalBase {
    constructor(options = {}) {
        super({
            id: 'bulk-rating-modal',
            title: window.i18n.t('modal.bulk_rating.title'),
            classPrefix: 'bulk-rating',
            emptyMessage: window.i18n.t('bulk_modal.manual.empty_message'),
            closeOnOutsideClick: false,
            ...options
        });

        this.selectedQuickRating = 'safe';
        this.init();
    }

    getContentHTML() {
        const prefix = this.options.classPrefix;
        const reviewText = window.i18n.t('bulk_modal.rating.review_ratings');
        const applyText = window.i18n.t('common.apply');

        return `
            <div class="${prefix}-content flex-1 flex flex-col min-h-0" style="display: none;">
                <p class="text-secondary mb-3 text-xs sm:text-sm shrink-0">${reviewText}</p>
                <div class="flex flex-wrap sm:flex-nowrap gap-2 mb-3 shrink-0 items-center justify-between p-2 surface-light border">
                    <div class="flex items-center gap-2">
                        <div class="flex gap-1" id="${prefix}-quick-selector">
                            ${['safe', 'questionable', 'explicit'].map(rating => `
                                <button type="button" 
                                    class="quick-rating-btn px-3 py-1.5 text-xs border cursor-pointer transition-colors ${rating === this.selectedQuickRating ? 'btn-primary' : 'bg hover:border-primary'}" 
                                    data-rating="${rating}">
                                    ${window.i18n.t('common.' + rating)}
                                </button>
                            `).join('')}
                        </div>
                    </div>
                    <button type="button" id="${prefix}-quick-apply" class="btn-primary px-3 py-1.5 text-xs cursor-pointer shrink-0">
                        ${applyText}
                    </button>
                </div>
                <div class="${prefix}-items space-y-3 overflow-y-auto flex-1 -mx-4 px-4 pb-2" style="overscroll-behavior: contain;"></div>
            </div>
        `;
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

    setupAdditionalEventListeners() {
        const prefix = this.options.classPrefix;

        // Quick rating selector buttons
        this.modalElement?.querySelectorAll(`#${prefix}-quick-selector .quick-rating-btn`).forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetRating = e.currentTarget.dataset.rating;
                this.selectedQuickRating = targetRating;
                this.modalElement.querySelectorAll(`#${prefix}-quick-selector .quick-rating-btn`).forEach(b => {
                    const isSelected = b.dataset.rating === targetRating;
                    b.classList.toggle('btn-primary', isSelected);
                    b.classList.toggle('bg', !isSelected);
                });
            });
        });

        // Quick apply to all button
        const quickApplyBtn = this.modalElement?.querySelector(`#${prefix}-quick-apply`);
        if (quickApplyBtn) {
            quickApplyBtn.addEventListener('click', () => {
                this._applyQuickRating(this.selectedQuickRating);
            });
        }

        // Delegated clicks for item cards (item rating buttons and reset button)
        const itemsContainer = this.modalElement?.querySelector(`.${prefix}-items`);
        if (itemsContainer) {
            itemsContainer.addEventListener('click', (e) => {
                // Item rating button
                const ratingBtn = e.target.closest('.item-rating-btn');
                if (ratingBtn) {
                    const index = parseInt(ratingBtn.dataset.index, 10);
                    const rating = ratingBtn.dataset.rating;
                    if (!isNaN(index) && rating) {
                        this._setItemRating(index, rating);
                    }
                    return;
                }

                // Item reset button
                const resetBtn = e.target.closest(`.${prefix}-reset`);
                if (resetBtn) {
                    const index = parseInt(resetBtn.dataset.index, 10);
                    if (!isNaN(index)) {
                        this._resetItemRating(index);
                    }
                    return;
                }
            });
        }
    }

    _applyQuickRating(targetRating) {
        if (!this.itemsData || this.itemsData.length === 0) return;
        this.itemsData.forEach(item => {
            item.newRating = targetRating;
        });
        this.renderItems();
        this.showSaveButton();
    }

    _setItemRating(index, newRating) {
        const item = this.itemsData[index];
        if (!item) return;
        item.newRating = newRating;
        this._updateItemDOM(index);
        this.showSaveButton();
    }

    _resetItemRating(index) {
        const item = this.itemsData[index];
        if (!item) return;
        item.newRating = item.currentRating;
        this._updateItemDOM(index);
        this.showSaveButton();
    }

    _updateItemDOM(index) {
        const prefix = this.options.classPrefix;
        const row = this.modalElement?.querySelector(`.${prefix}-item[data-index="${index}"]`);
        if (!row || !this.itemsData[index]) return;
        const temp = document.createElement('div');
        temp.innerHTML = this.renderItem(this.itemsData[index], index);
        const newRow = temp.firstElementChild;
        if (newRow) {
            row.replaceWith(newRow);
        }
    }

    renderItem(item, index) {
        const prefix = this.options.classPrefix;
        const currentRating = item.currentRating || 'safe';
        const activeRating = item.newRating || currentRating;
        const isModified = activeRating !== currentRating;
        const safeFilename = escapeHtml(item.filename || '');
        const currentLabel = window.i18n.t('common.' + currentRating);
        const activeLabel = window.i18n.t('common.' + activeRating);
        const resetTitle = window.i18n.t('common.discard_changes');

        return `
            <div class="${prefix}-item surface-light p-3 border mb-3" data-index="${index}" style="content-visibility: auto; contain-intrinsic-size: auto 120px;">
                <div class="flex flex-col sm:flex-row gap-3">
                    <!-- Thumbnail -->
                    <div class="flex gap-3 sm:block shrink-0">
                        <img src="/api/media/${item.mediaId}/thumbnail" 
                             alt="" 
                             class="w-16 h-16 sm:w-20 sm:h-20 object-cover shrink-0 item-thumbnail cursor-pointer"
                             onerror="this.src='/static/images/no-thumbnail.png'">
                        
                        <!-- Mobile: Info next to thumbnail -->
                        <div class="flex-1 sm:hidden min-w-0">
                            <p class="text-sm font-medium truncate mb-1" title="${safeFilename}">${safeFilename}</p>
                            <p class="text-xs text-secondary">
                                ${window.i18n.t('bulk_modal.messages.current')}<span>${currentLabel}</span>
                                ${isModified ? ` <span class="text-xs text-primary">-> ${activeLabel}</span>` : ''}
                            </p>
                        </div>
                    </div>

                    <!-- Content -->
                    <div class="flex-1 min-w-0 flex flex-col justify-between">
                        <!-- Desktop: Info above rating buttons -->
                        <div class="hidden sm:block">
                            <p class="text-sm font-medium truncate mb-1" title="${safeFilename}">${safeFilename}</p>
                            <p class="text-xs text-secondary mb-2">
                                ${window.i18n.t('bulk_modal.messages.current')}<span>${currentLabel}</span>
                                ${isModified ? ` <span class="text-xs text-primary">-> ${activeLabel}</span>` : ''}
                            </p>
                        </div>

                        <!-- Rating selection buttons and actions -->
                        <div class="flex items-center justify-between gap-2">
                            <div class="flex gap-1.5 flex-wrap">
                                ${['safe', 'questionable', 'explicit'].map(r => `
                                    <button type="button"
                                        class="item-rating-btn px-3 py-1.5 text-xs border cursor-pointer transition-colors ${r === activeRating ? 'btn-primary' : 'bg hover:border-primary text-secondary hover:text'}"
                                        data-index="${index}"
                                        data-rating="${r}">
                                        ${window.i18n.t('common.' + r)}
                                    </button>
                                `).join('')}
                            </div>
                            
                            <!-- Action button: Reset/Revert -->
                            <button type="button"
                                class="${prefix}-reset w-8 h-8 surface hover:surface-light text-secondary hover:text flex items-center justify-center transition-colors border ${isModified ? 'cursor-pointer' : 'opacity-30 cursor-not-allowed pointer-events-none'}"
                                data-index="${index}"
                                title="${resetTitle}">
                                ${window.Icons && window.Icons.reset ? window.Icons.reset({ size: 14 }) : '↺'}
                            </button>
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
    }

    async fetchTags() {
        if (this.isCancelled) return;

        this.showState('loading');
        const selectedArray = Array.from(this.selectedItems);

        try {
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

            this.itemsData = items.map(item => {
                const currentRating = item.rating || 'safe';
                const prefilled = this.options.prefillRatings && this.options.prefillRatings[item.id]
                    ? this.options.prefillRatings[item.id]
                    : null;
                const newRating = prefilled || currentRating;

                return {
                    mediaId: item.id,
                    filename: item.filename || window.i18n.t('bulk_modal.ai_tags.default_media_name', { id: item.id }),
                    file_type: item.file_type,
                    currentRating: currentRating,
                    newRating: newRating
                };
            });

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
            console.error('Error fetching media ratings:', e);
            this.showError(window.i18n.t('notifications.error_occurred'));
        }
    }

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

        const updateItems = [];
        for (const item of this.itemsData) {
            if (item.newRating && item.newRating !== item.currentRating) {
                updateItems.push({
                    id: item.mediaId,
                    rating: item.newRating
                });
            }
        }

        let successCount = 0;
        let errorCount = 0;

        if (updateItems.length > 0) {
            try {
                const response = await fetch('/api/media/bulk-update-ratings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items: updateItems })
                });

                if (response.ok) {
                    const data = await response.json();
                    successCount = data.updated_count ?? updateItems.length;
                } else {
                    errorCount = updateItems.length;
                }
            } catch (e) {
                console.error('Error saving ratings in bulk:', e);
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
            if (successCount > 0) {
                app.showNotification(window.i18n.t('bulk_modal.notifications.updated_success', { count: successCount }), 'success');
            }
            if (errorCount > 0) {
                app.showNotification(window.i18n.t('bulk_modal.notifications.updated_failed', { count: errorCount }), 'error');
            }
        }
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkRatingModal;
}
