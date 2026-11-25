class BulkFieldModal extends BulkTagModalBase {
    static PRESETS = {
        custom_date: {
            id: 'bulk-custom-date-modal',
            classPrefix: 'bulk-custom-date',
            titleKey: 'modal.bulk_custom_date.title',
            labelKey: 'media.info.custom_date',
            reviewKey: 'bulk_modal.custom_date.review_dates',
            secondaryKey: 'admin.settings.upload_date',
            inputType: 'datetime-local',
            placeholder: '',
            statusWrapClass: 'break-words',
            supportsScan: true,
            mapItem(item) {
                const currentIso = item.custom_date || item.uploaded_at || null;
                const currentValue = toLocalInputDateTime(currentIso);
                return {
                    currentIso,
                    uploadedAtIso: item.uploaded_at || null,
                    uploadedValue: toLocalInputDateTime(item.uploaded_at),
                    currentValue,
                    newValue: currentValue,
                    resetFlag: false,
                    dateOrigin: null,
                    scanNotFound: false
                };
            },
            isModified(item) {
                if (item.resetFlag) {
                    const curTs = item.currentIso ? Date.parse(item.currentIso) : NaN;
                    const upTs = item.uploadedAtIso ? Date.parse(item.uploadedAtIso) : NaN;
                    return (!isNaN(curTs) && !isNaN(upTs)) ? curTs !== upTs : item.currentValue !== item.uploadedValue;
                }
                return item.newValue !== item.currentValue;
            },
            formatCurrent(item) {
                return escapeHtml(formatDateTime(item.currentIso || item.currentValue, window.i18n.t('common.none')));
            },
            formatNew(item) {
                const target = item.resetFlag ? (item.uploadedAtIso || item.uploadedValue) : item.newValue;
                return escapeHtml(formatDateTime(target, window.i18n.t('common.none')));
            },
            validateQuick(trimmed) {
                if (!parseLocalInputDateTime(trimmed)) {
                    app?.showNotification?.(window.i18n.t('notifications.media.error_updating_date'), 'error');
                    return false;
                }
                return true;
            },
            onItemInput(item, value) {
                const trimmed = (value || '').trim();
                item.newValue = trimmed;
                item.resetFlag = trimmed === '';
                item.dateOrigin = null;
                item.scanNotFound = false;
            },
            applySecondary(item) {
                item.newValue = item.uploadedValue;
                item.resetFlag = true;
                item.dateOrigin = null;
                item.scanNotFound = false;
            },
            formatBadge(item) {
                if (item.dateOrigin && typeof formatCustomDateOriginBadge === 'function') {
                    return formatCustomDateOriginBadge(item.dateOrigin);
                }
                if (item.scanNotFound) {
                    const label = escapeHtml(window.i18n.t('bulk_modal.custom_date.no_date_found'));
                    return `<span class="badge surface border border-color text-secondary text-[10px] px-1.5 py-0.5 shrink-0" title="${label}">${label}</span>`;
                }
                return '';
            },
            toPayload(item) {
                if (item.resetFlag || !item.newValue) return { id: item.mediaId, custom_date: null };
                const iso = parseLocalInputDateTime(item.newValue);
                if (!iso) {
                    app?.showNotification?.(window.i18n.t('notifications.media.error_updating_date'), 'error');
                    return null;
                }
                return { id: item.mediaId, custom_date: iso };
            }
        },
        source: {
            id: 'bulk-source-modal',
            classPrefix: 'bulk-source',
            titleKey: 'modal.bulk_source.title',
            labelKey: 'media.info.source',
            reviewKey: 'bulk_modal.source.review_sources',
            secondaryKey: 'modal.clear_tags.confirm',
            inputType: 'url',
            placeholder: 'https://example.com/source',
            statusWrapClass: 'break-all',
            mapItem(item) {
                const currentValue = (item.source || '').trim();
                return { currentValue, newValue: currentValue, resetFlag: false };
            },
            isModified(item) {
                return (item.newValue || '').trim() !== (item.currentValue || '').trim();
            },
            formatValue(val) {
                const trimmed = (val || '').trim();
                return trimmed ? escapeHtml(trimmed) : `<span class="italic">${escapeHtml(window.i18n.t('common.none'))}</span>`;
            },
            formatCurrent(item) {
                return this.formatValue(item.currentValue);
            },
            formatNew(item) {
                return this.formatValue(item.newValue);
            },
            validateQuick() {
                return true;
            },
            onItemInput(item, value) {
                item.newValue = value;
            },
            applySecondary(item) {
                item.newValue = '';
            },
            toPayload(item) {
                return { id: item.mediaId, source: (item.newValue || '').trim() || null };
            }
        }
    };

    constructor(field, options = {}) {
        const preset = BulkFieldModal.PRESETS[field];
        if (!preset) throw new Error(`Unknown bulk field preset: ${field}`);

        super({
            id: preset.id,
            title: window.i18n.t(preset.titleKey),
            classPrefix: preset.classPrefix,
            emptyMessage: window.i18n.t('bulk_modal.manual.empty_message'),
            closeOnOutsideClick: false,
            ...options
        });

        this.preset = preset;
        this.init();
    }

    reset() {
        super.reset();
        this._isScanningAll = false;
        const prefix = this.options.classPrefix;
        const quickInput = this.modalElement?.querySelector(`#${prefix}-quick-input`);
        if (quickInput) quickInput.value = '';
        this._setScanAllBusy(false);
    }

    getContentHTML() {
        const prefix = this.options.classPrefix;
        const p = this.preset;
        const placeholderAttr = p.placeholder ? `placeholder="${escapeAttr(p.placeholder)}"` : '';

        return `
            <div class="${prefix}-content flex-1 flex flex-col min-h-0" style="display: none;">
                <p class="text-secondary mb-3 text-xs sm:text-sm shrink-0">${window.i18n.t(p.reviewKey)}</p>
                <div class="flex flex-wrap sm:flex-nowrap gap-2 mb-3 shrink-0 items-center p-2 surface-light border">
                    <input type="${p.inputType}" id="${prefix}-quick-input" ${placeholderAttr}
                        aria-label="${escapeAttr(window.i18n.t(p.labelKey))}"
                        class="w-full sm:w-auto sm:flex-1 min-w-0 bg px-3 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors">
                    <div class="flex flex-wrap sm:flex-nowrap gap-1.5 shrink-0 w-full sm:w-auto">
                        <button type="button" id="${prefix}-quick-apply" class="btn-primary flex-1 sm:flex-none px-3 py-1.5 text-xs cursor-pointer shrink-0 whitespace-nowrap">
                            ${window.i18n.t('common.apply')}
                        </button>
                        <button type="button" id="${prefix}-quick-secondary" class="btn-dark flex-1 sm:flex-none px-3 py-1.5 text-xs cursor-pointer shrink-0 whitespace-nowrap">
                            ${window.i18n.t(p.secondaryKey)}
                        </button>
                        ${p.supportsScan ? `
                        <button type="button" id="${prefix}-scan-all" class="btn-dark flex-1 sm:flex-none px-3 py-1.5 text-xs cursor-pointer shrink-0 whitespace-nowrap">
                            ${window.i18n.t('bulk_modal.custom_date.scan_all')}
                        </button>` : ''}
                    </div>
                </div>
                ${p.supportsScan ? `
                <div class="${prefix}-scan-progress flex items-center gap-2 mb-3 text-xs text-secondary shrink-0" style="display: none;">
                    <span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span>
                    <span class="${prefix}-scan-progress-text"></span>
                </div>` : ''}
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

        this.modalElement?.querySelector(`#${prefix}-quick-apply`)?.addEventListener('click', () => {
            this._applyQuick(quickInput?.value || '');
        });
        quickInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this._applyQuick(quickInput.value || '');
            }
        });
        this.modalElement?.querySelector(`#${prefix}-quick-secondary`)?.addEventListener('click', () => {
            if (!this.itemsData.length) return;
            this.itemsData.forEach(item => this.preset.applySecondary(item));
            this.renderItems();
            this.showSaveButton();
        });
        if (this.preset.supportsScan) {
            this.modalElement?.querySelector(`#${prefix}-scan-all`)?.addEventListener('click', () => {
                this._scanAllItems();
            });
        }

        const container = this.modalElement?.querySelector(`.${prefix}-items`);
        if (!container) return;

        const onInput = (e) => {
            const input = e.target.closest(`.${prefix}-item-input`);
            if (!input) return;
            const index = parseInt(input.dataset.index, 10);
            const item = this.itemsData[index];
            if (!item) return;
            this.preset.onItemInput(item, input.value);
            this._updateItemStatusDOM(index);
            this.showSaveButton();
        };
        container.addEventListener('input', onInput);
        if (this.preset.inputType === 'datetime-local') {
            container.addEventListener('change', onInput);
        }

        container.addEventListener('click', (e) => {
            const scanBtn = e.target.closest(`.${prefix}-scan`);
            if (scanBtn) {
                const index = parseInt(scanBtn.dataset.index, 10);
                if (!isNaN(index)) this._scanSingleItem(index, scanBtn);
                return;
            }
            const resetBtn = e.target.closest(`.${prefix}-reset`);
            if (!resetBtn) return;
            const index = parseInt(resetBtn.dataset.index, 10);
            const item = this.itemsData[index];
            if (!item) return;
            item.newValue = item.currentValue;
            item.resetFlag = false;
            item.dateOrigin = null;
            item.scanNotFound = false;
            const input = this.modalElement?.querySelector(`.${prefix}-item[data-index="${index}"] .${prefix}-item-input`);
            if (input) input.value = item.newValue;
            this._updateItemStatusDOM(index);
            this.showSaveButton();
        });
    }

    _applyQuick(rawValue) {
        if (!this.itemsData.length) return;
        const trimmed = (rawValue || '').trim();
        if (!trimmed) {
            this.modalElement?.querySelector(`#${this.options.classPrefix}-quick-input`)?.focus();
            return;
        }
        if (!this.preset.validateQuick(trimmed)) return;
        this.itemsData.forEach(item => {
            item.newValue = trimmed;
            item.resetFlag = false;
            item.dateOrigin = null;
            item.scanNotFound = false;
        });
        this.renderItems();
        this.showSaveButton();
    }

    _setScanAllBusy(busy, label = null) {
        const prefix = this.options.classPrefix;
        const btn = this.modalElement?.querySelector(`#${prefix}-scan-all`);
        if (btn) btn.disabled = busy;
        const progress = this.modalElement?.querySelector(`.${prefix}-scan-progress`);
        if (progress) {
            progress.style.display = busy ? 'flex' : 'none';
            const text = progress.querySelector(`.${prefix}-scan-progress-text`);
            if (text) text.textContent = busy && label ? label : '';
        }
        this.modalElement?.querySelectorAll(`.${prefix}-scan`).forEach(b => { b.disabled = busy; });
    }

    _applyScanResult(index, result) {
        const item = this.itemsData[index];
        if (!item) return;
        const prefix = this.options.classPrefix;
        if (result && result.custom_date) {
            const localVal = toLocalInputDateTime(result.custom_date);
            if (localVal) {
                item.newValue = localVal;
                item.resetFlag = false;
                item.dateOrigin = result.origin || null;
                item.scanNotFound = false;
                const input = this.modalElement?.querySelector(`.${prefix}-item[data-index="${index}"] .${prefix}-item-input`);
                if (input) input.value = localVal;
                this._updateItemStatusDOM(index);
                this.showSaveButton();
                return true;
            }
        }
        item.dateOrigin = null;
        item.scanNotFound = true;
        this._updateItemStatusDOM(index);
        return false;
    }

    async _scanSingleItem(index, btn) {
        if (this._isScanningAll || this.isCancelled) return;
        const item = this.itemsData[index];
        if (!item) return;

        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span>`;

        try {
            const res = await this.fetchWithAbort('/api/media/batch-scan-dates', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids: [item.mediaId] })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (this.isCancelled) return;
            this._applyScanResult(index, (data.items || {})[String(item.mediaId)]);
        } catch (e) {
            if (e.name !== 'AbortError') {
                console.error('Error scanning date:', e);
                app?.showNotification?.(window.i18n.t('bulk_modal.messages.error_occurred'), 'error');
            }
        } finally {
            if (btn.isConnected) {
                btn.innerHTML = originalHTML;
                btn.disabled = this._isScanningAll;
            }
        }
    }

    async _scanAllItems() {
        if (this._isScanningAll || this.isCancelled || !this.itemsData.length) return;
        this._isScanningAll = true;

        const total = this.itemsData.length;
        const indexById = new Map(this.itemsData.map((it, idx) => [it.mediaId, idx]));
        const ids = this.itemsData.map(it => it.mediaId);
        const chunkSize = 10;
        let scanned = 0;
        let found = 0;
        let failed = false;

        this._setScanAllBusy(true, `${window.i18n.t('admin.actions.scanning')} (0/${total})`);

        try {
            for (let i = 0; i < ids.length && !this.isCancelled; i += chunkSize) {
                const chunk = ids.slice(i, i + chunkSize);
                const res = await this.fetchWithAbort('/api/media/batch-scan-dates', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: chunk })
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                if (this.isCancelled) return;

                const results = data.items || {};
                for (const mid of chunk) {
                    const idx = indexById.get(mid);
                    if (idx !== undefined && this._applyScanResult(idx, results[String(mid)])) {
                        found++;
                    }
                }
                scanned += chunk.length;
                this._setScanAllBusy(true, `${window.i18n.t('admin.actions.scanning')} (${scanned}/${total})`);
            }
        } catch (e) {
            if (e.name !== 'AbortError') {
                failed = true;
                console.error('Error scanning dates in bulk:', e);
                app?.showNotification?.(window.i18n.t('bulk_modal.messages.error_occurred'), 'error');
            }
        } finally {
            this._isScanningAll = false;
            this._setScanAllBusy(false);
        }

        if (!this.isCancelled && !failed) {
            const msg = found > 0
                ? window.i18n.t('bulk_modal.custom_date.scan_complete', { found, total })
                : window.i18n.t('bulk_modal.custom_date.no_date_found');
            app?.showNotification?.(msg, found > 0 ? 'success' : 'info');
        }
    }

    _getStatusHTML(item) {
        const arrow = this.preset.isModified(item)
            ? ` <span class="text-xs text-primary">-&gt; ${this.preset.formatNew(item)}</span>`
            : '';
        return `${window.i18n.t('bulk_modal.messages.current')}<span>${this.preset.formatCurrent(item)}</span>${arrow}`;
    }

    _updateItemStatusDOM(index) {
        const prefix = this.options.classPrefix;
        const item = this.itemsData[index];
        const row = this.modalElement?.querySelector(`.${prefix}-item[data-index="${index}"]`);
        if (!row || !item) return;

        const statusHTML = this._getStatusHTML(item);
        row.querySelectorAll(`.${prefix}-status-text`).forEach(el => { el.innerHTML = statusHTML; });

        if (this.preset.formatBadge) {
            const badgeHTML = this.preset.formatBadge(item);
            row.querySelectorAll(`.${prefix}-badge-slot`).forEach(el => { el.innerHTML = badgeHTML; });
        }

        const isModified = this.preset.isModified(item);
        const resetBtn = row.querySelector(`.${prefix}-reset`);
        if (resetBtn) {
            resetBtn.classList.toggle('cursor-pointer', isModified);
            resetBtn.classList.toggle('opacity-30', !isModified);
            resetBtn.classList.toggle('cursor-not-allowed', !isModified);
            resetBtn.classList.toggle('pointer-events-none', !isModified);
        }
    }

    renderItem(item, index) {
        const prefix = this.options.classPrefix;
        const p = this.preset;
        const isModified = p.isModified(item);
        const safeFilename = escapeHtml(item.filename || '');
        const statusHTML = this._getStatusHTML(item);
        const badgeHTML = p.formatBadge ? p.formatBadge(item) : '';
        const placeholderAttr = p.placeholder ? `placeholder="${escapeAttr(p.placeholder)}"` : '';

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
                                <p class="${prefix}-status-text text-xs text-secondary ${p.statusWrapClass} min-w-0">${statusHTML}</p>
                                <span class="${prefix}-badge-slot inline-flex items-center max-w-full empty:hidden">${badgeHTML}</span>
                            </div>
                        </div>
                    </div>
                    <div class="flex-1 min-w-0 flex flex-col justify-between">
                        <div class="hidden sm:block">
                            <p class="text-sm font-medium truncate mb-1" title="${safeFilename}">${safeFilename}</p>
                            <div class="flex flex-wrap items-center gap-x-2 gap-y-1 mb-2">
                                <p class="${prefix}-status-text text-xs text-secondary ${p.statusWrapClass} min-w-0">${statusHTML}</p>
                                <span class="${prefix}-badge-slot inline-flex items-center max-w-full empty:hidden">${badgeHTML}</span>
                            </div>
                        </div>
                        <div class="flex items-center gap-1.5 sm:gap-2">
                            <input type="${p.inputType}" ${placeholderAttr}
                                class="${prefix}-item-input flex-1 min-w-0 bg px-2.5 py-1.5 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                                data-index="${index}" aria-label="${escapeAttr(window.i18n.t(p.labelKey))}"
                                value="${escapeAttr(item.newValue || '')}">
                            ${p.supportsScan ? `
                            <button type="button"
                                class="${prefix}-scan w-8 h-8 shrink-0 surface hover:surface-light text-secondary hover:text flex items-center justify-center transition-colors border cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                                data-index="${index}"
                                aria-label="${escapeAttr(window.i18n.t('bulk_modal.custom_date.scan'))}"
                                title="${escapeAttr(window.i18n.t('bulk_modal.custom_date.scan'))}">
                                ${window.Icons?.search ? window.Icons.search({ size: 14 }) : ''}
                            </button>` : ''}
                            <button type="button"
                                class="${prefix}-reset w-8 h-8 shrink-0 surface hover:surface-light text-secondary hover:text flex items-center justify-center transition-colors border ${isModified ? 'cursor-pointer' : 'opacity-30 cursor-not-allowed pointer-events-none'}"
                                data-index="${index}" title="${escapeAttr(window.i18n.t('common.discard_changes'))}">
                                ${window.Icons?.reset ? window.Icons.reset({ size: 14 }) : '↺'}
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
                projection: 'info',
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
                ...this.preset.mapItem(item)
            }));

            this.renderItems();
            if (this.isCancelled) return;
            this.showState('content');
            this.showSaveButton();
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Error fetching media info:', e);
            this.showError(window.i18n.t('bulk_modal.messages.error_occurred'));
        }
    }

    async saveTags() {
        const updateItems = [];
        for (const item of this.itemsData) {
            if (!this.preset.isModified(item)) continue;
            const payload = this.preset.toPayload(item);
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
                const res = await fetch('/api/media/bulk-update-metadata', {
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
                console.error('Error saving metadata in bulk:', e);
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
    module.exports = BulkFieldModal;
}
