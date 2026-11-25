class BulkFieldModalBase extends BulkTagModalBase {
    constructor(options = {}) {
        super({
            emptyMessage: window.i18n.t('bulk_modal.manual.empty_message'),
            closeOnOutsideClick: false,
            fetchProjection: 'info',
            saveEndpoint: '/api/media/bulk-update-metadata',
            statusWrapClass: 'break-words',
            ...options
        });

        this.init();
    }

    // ==================== Overridable Hooks ====================

    getReviewText() {
        return this.options.reviewText || '';
    }

    getQuickBarHTML() {
        return this.getQuickInputBarHTML();
    }

    getBelowQuickBarHTML() {
        return '';
    }

    renderItemControlHTML(item, index) {
        return this.getItemInputHTML(item, index);
    }

    renderItemExtraActionsHTML() {
        return '';
    }

    formatBadge() {
        return '';
    }

    mapItem(item) {
        return { currentValue: '', newValue: '' };
    }

    isItemModified(item) {
        return Boolean(item) && item.newValue !== item.currentValue;
    }

    formatCurrentValue(item) {
        return escapeHtml(item.currentValue || '');
    }

    formatNewValue(item) {
        return escapeHtml(item.newValue || '');
    }

    validateQuickValue() {
        return true;
    }

    onQuickApply(trimmedValue) {
        this.itemsData.forEach(item => {
            item.newValue = trimmedValue;
            this.onItemValueCleared(item);
        });
        this.renderItems();
        this.showSaveButton();
    }

    onSecondaryAction() {
        // Override in subclass if quick bar includes a secondary button
    }

    onItemInput(item, value) {
        item.newValue = value;
    }

    onItemReset(item) {
        item.newValue = item.currentValue;
        this.onItemValueCleared(item);
    }

    onItemValueCleared() {
        // Optional hook for subclasses with auxiliary per-item state
    }

    toSavePayload() {
        throw new Error('toSavePayload must be implemented by subclass');
    }

    setupFieldEventListeners() {
        // Override in subclass for additional custom controls
    }

    // ==================== Reusable Input-Based Helpers ====================

    getQuickInputBarHTML({ inputType = 'text', placeholder = '', label = '', secondaryText = '', extraButtonsHTML = '' } = {}) {
        const prefix = this.options.classPrefix;
        const placeholderAttr = placeholder ? `placeholder="${escapeAttr(placeholder)}"` : '';
        return `
            <input type="${inputType}" id="${prefix}-quick-input" ${placeholderAttr}
                aria-label="${escapeAttr(label)}"
                class="w-full sm:w-auto sm:flex-1 min-w-0 bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors">
            <div class="flex flex-wrap sm:flex-nowrap gap-1.5 shrink-0 w-full sm:w-auto">
                <button type="button" id="${prefix}-quick-apply" class="btn-primary flex-1 sm:flex-none px-3 py-1.5 text-xs cursor-pointer shrink-0 whitespace-nowrap">
                    ${window.i18n.t('common.apply')}
                </button>
                ${secondaryText ? `
                <button type="button" id="${prefix}-quick-secondary" class="btn-dark flex-1 sm:flex-none px-3 py-1.5 text-xs cursor-pointer shrink-0 whitespace-nowrap">
                    ${secondaryText}
                </button>` : ''}
                ${extraButtonsHTML}
            </div>
        `;
    }

    getItemInputHTML(item, index, { inputType = 'text', placeholder = '', label = '' } = {}) {
        const prefix = this.options.classPrefix;
        const placeholderAttr = placeholder ? `placeholder="${escapeAttr(placeholder)}"` : '';
        return `
            <input type="${inputType}" ${placeholderAttr}
                class="${prefix}-item-input flex-1 min-w-0 bg px-2.5 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                data-index="${index}" aria-label="${escapeAttr(label)}"
                value="${escapeAttr(item.newValue || '')}">
        `;
    }

    // ==================== Core Modal Layout & Lifecycle ====================

    reset() {
        super.reset();
        const quickInput = this.modalElement?.querySelector(`#${this.options.classPrefix}-quick-input`);
        if (quickInput) quickInput.value = '';
    }

    getContentHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-content flex-1 flex flex-col min-h-0" style="display: none;">
                <p class="text-secondary mb-3 text-xs sm:text-sm shrink-0">${this.getReviewText()}</p>
                <div class="flex flex-wrap sm:flex-nowrap gap-2 mb-3 shrink-0 items-center justify-between p-2 surface-light border">
                    ${this.getQuickBarHTML()}
                </div>
                ${this.getBelowQuickBarHTML()}
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
        const quickInput = this.modalElement?.querySelector(`#${prefix}-quick-input`);

        if (quickInput) {
            this.modalElement?.querySelector(`#${prefix}-quick-apply`)?.addEventListener('click', () => {
                this._handleQuickInputApply(quickInput);
            });
            quickInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this._handleQuickInputApply(quickInput);
                }
            });
        }

        this.modalElement?.querySelector(`#${prefix}-quick-secondary`)?.addEventListener('click', () => {
            if (!this.itemsData.length) return;
            this.onSecondaryAction();
            this.renderItems();
            this.showSaveButton();
        });

        const container = this.modalElement?.querySelector(`.${prefix}-items`);
        if (container) {
            const handleInput = (e) => {
                const input = e.target.closest(`.${prefix}-item-input`);
                if (!input) return;
                const index = parseInt(input.dataset.index, 10);
                const item = this.itemsData[index];
                if (!item) return;
                this.onItemInput(item, input.value);
                this._updateItemStatusDOM(index);
                this.showSaveButton();
            };
            container.addEventListener('input', handleInput);
            container.addEventListener('change', (e) => {
                if (e.target.matches(`.${prefix}-item-input[type="datetime-local"]`)) handleInput(e);
            });

            container.addEventListener('click', (e) => {
                const resetBtn = e.target.closest(`.${prefix}-reset`);
                if (!resetBtn) return;
                const index = parseInt(resetBtn.dataset.index, 10);
                this._resetItem(index);
            });
        }

        this.setupFieldEventListeners();
    }

    _handleQuickInputApply(quickInput) {
        if (!this.itemsData.length) return;
        const trimmed = (quickInput.value || '').trim();
        if (!trimmed) {
            quickInput.focus();
            return;
        }
        if (!this.validateQuickValue(trimmed)) return;
        this.onQuickApply(trimmed);
    }

    _resetItem(index) {
        const item = this.itemsData[index];
        if (!item) return;
        this.onItemReset(item, index);
        const prefix = this.options.classPrefix;
        const input = this.modalElement?.querySelector(`.${prefix}-item[data-index="${index}"] .${prefix}-item-input`);
        if (input) input.value = item.newValue || '';
        this._updateItemStatusDOM(index);
        this.showSaveButton();
    }

    _getStatusHTML(item) {
        const arrow = this.isItemModified(item)
            ? ` <span class="text-xs text-primary">-&gt; ${this.formatNewValue(item)}</span>`
            : '';
        return `${window.i18n.t('bulk_modal.messages.current')}<span>${this.formatCurrentValue(item)}</span>${arrow}`;
    }

    _updateItemStatusDOM(index) {
        const prefix = this.options.classPrefix;
        const item = this.itemsData[index];
        const row = this.modalElement?.querySelector(`.${prefix}-item[data-index="${index}"]`);
        if (!row || !item) return;

        const statusHTML = this._getStatusHTML(item);
        row.querySelectorAll(`.${prefix}-status-text`).forEach(el => { el.innerHTML = statusHTML; });

        const badgeHTML = this.formatBadge(item);
        row.querySelectorAll(`.${prefix}-badge-slot`).forEach(el => { el.innerHTML = badgeHTML; });

        const isModified = this.isItemModified(item);
        const resetBtn = row.querySelector(`.${prefix}-reset`);
        if (resetBtn) {
            resetBtn.classList.toggle('cursor-pointer', isModified);
            resetBtn.classList.toggle('opacity-30', !isModified);
            resetBtn.classList.toggle('cursor-not-allowed', !isModified);
            resetBtn.classList.toggle('pointer-events-none', !isModified);
        }
    }

    _replaceItemRowDOM(index) {
        const prefix = this.options.classPrefix;
        const row = this.modalElement?.querySelector(`.${prefix}-item[data-index="${index}"]`);
        if (!row || !this.itemsData[index]) return;
        const temp = document.createElement('div');
        temp.innerHTML = this.renderItem(this.itemsData[index], index);
        if (temp.firstElementChild) row.replaceWith(temp.firstElementChild);
    }

    renderItem(item, index) {
        const prefix = this.options.classPrefix;
        const isModified = this.isItemModified(item);
        const safeFilename = escapeHtml(item.filename || '');
        const statusHTML = this._getStatusHTML(item);
        const badgeHTML = this.formatBadge(item);
        const wrapClass = this.options.statusWrapClass;

        return `
            <div class="${prefix}-item surface-light p-3 border mb-3" data-index="${index}" style="content-visibility: auto; contain-intrinsic-size: auto 120px;">
                <div class="flex flex-col sm:flex-row gap-3">
                    <div class="flex gap-3 sm:block shrink-0">
                        <img src="/api/media/${item.mediaId}/thumbnail" alt=""
                             class="w-16 h-16 sm:w-20 sm:h-20 object-cover shrink-0 item-thumbnail cursor-pointer"
                             onerror="this.src='/static/images/no-thumbnail.png'">
                        <div class="flex-1 sm:hidden min-w-0">
                            <p class="text-sm font-medium truncate mb-1" title="${safeFilename}">${safeFilename}</p>
                            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                                <p class="${prefix}-status-text text-xs text-secondary ${wrapClass} min-w-0">${statusHTML}</p>
                                <span class="${prefix}-badge-slot inline-flex items-center max-w-full empty:hidden">${badgeHTML}</span>
                            </div>
                        </div>
                    </div>
                    <div class="flex-1 min-w-0 flex flex-col justify-between">
                        <div class="hidden sm:block">
                            <p class="text-sm font-medium truncate mb-1" title="${safeFilename}">${safeFilename}</p>
                            <div class="flex flex-wrap items-center gap-x-2 gap-y-1 mb-2">
                                <p class="${prefix}-status-text text-xs text-secondary ${wrapClass} min-w-0">${statusHTML}</p>
                                <span class="${prefix}-badge-slot inline-flex items-center max-w-full empty:hidden">${badgeHTML}</span>
                            </div>
                        </div>
                        <div class="flex items-center justify-between gap-1.5 sm:gap-2">
                            ${this.renderItemControlHTML(item, index)}
                            ${this.renderItemExtraActionsHTML(item, index)}
                            <button type="button"
                                class="${prefix}-reset w-8 h-8 shrink-0 surface hover:surface-light text-secondary hover:text flex items-center justify-center transition-colors border ${isModified ? 'cursor-pointer' : 'opacity-30 cursor-not-allowed pointer-events-none'}"
                                data-index="${index}" title="${escapeAttr(window.i18n.t('common.discard_changes'))}">
                                ${window.Icons.reset({ size: 14 })}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    renderItems() {
        const container = this.modalElement?.querySelector(`.${this.options.classPrefix}-items`);
        if (!container || !this.itemsData) return;
        container.scrollTop = 0;
        container.innerHTML = this.itemsData.map((item, i) => this.renderItem(item, i)).join('');
    }

    async fetchTags() {
        if (this.isCancelled) return;
        this.showState('loading');

        try {
            const items = await this.fetchMediaInChunks(Array.from(this.selectedItems), {
                chunkSize: 50,
                concurrency: 3,
                projection: this.options.fetchProjection,
                statusText: window.i18n.t('bulk_modal.progress.fetching_metadata'),
                phaseText: window.i18n.t('bulk_modal.progress.items_fetched')
            });
            if (this.isCancelled) return;
            if (!items || !items.length) {
                this.showState('empty');
                return;
            }

            this.itemsData = items.map(item => ({
                mediaId: item.id,
                filename: item.filename || window.i18n.t('bulk_modal.ai_tags.default_media_name', { id: item.id }),
                file_type: item.file_type,
                ...this.mapItem(item)
            }));

            this.renderItems();
            if (this.isCancelled) return;
            this.showState('content');
            this.showSaveButton();
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error(`Error fetching items for ${this.options.id}:`, e);
            this.showError(window.i18n.t('notifications.error_occurred'));
        }
    }

    async saveTags() {
        const updateItems = [];
        for (const item of this.itemsData) {
            if (!this.isItemModified(item)) continue;
            const payload = this.toSavePayload(item);
            if (!payload) return;
            updateItems.push(payload);
        }

        this.isCancelled = true;
        this.abortController?.abort();
        this.abortController = null;

        const saveBtn = this.modalElement?.querySelector(`.${this.options.classPrefix}-save`);
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = window.i18n.t('modal.buttons.saving');
        }

        let successCount = 0;
        let errorCount = 0;
        if (updateItems.length > 0) {
            try {
                const res = await fetch(this.options.saveEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items: updateItems })
                });
                if (res.ok) {
                    const data = await res.json();
                    successCount = data.updated_count ?? updateItems.length;
                } else {
                    errorCount = updateItems.length;
                }
            } catch (e) {
                console.error(`Error saving bulk updates for ${this.options.id}:`, e);
                errorCount = updateItems.length;
            }
        }

        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = window.i18n.t('modal.buttons.save_all');
        }

        this.hide();
        this.options.onSave?.({ successCount, errorCount });

        if (successCount > 0) {
            app?.showNotification?.(window.i18n.t('bulk_modal.notifications.updated_success', { count: successCount }), 'success');
        }
        if (errorCount > 0) {
            app?.showNotification?.(window.i18n.t('bulk_modal.notifications.updated_failed', { count: errorCount }), 'error');
        }
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkFieldModalBase;
}
