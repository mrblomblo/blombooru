class BulkCustomDateModal extends BulkFieldModalBase {
    constructor(options = {}) {
        super({
            id: 'bulk-custom-date-modal',
            title: window.i18n.t('modal.bulk_custom_date.title'),
            classPrefix: 'bulk-custom-date',
            ...options
        });
    }

    reset() {
        super.reset();
        this._isScanningAll = false;
        this._setScanAllBusy(false);
    }

    getReviewText() {
        return window.i18n.t('bulk_modal.custom_date.review_dates');
    }

    getQuickBarHTML() {
        const prefix = this.options.classPrefix;
        return this.getQuickInputBarHTML({
            inputType: 'datetime-local',
            label: window.i18n.t('media.info.custom_date'),
            secondaryText: window.i18n.t('admin.settings.upload_date'),
            extraButtonsHTML: `
                <button type="button" id="${prefix}-scan-all" class="btn-dark flex-1 sm:flex-none px-3 py-1.5 text-xs cursor-pointer shrink-0 whitespace-nowrap">
                    ${window.i18n.t('bulk_modal.custom_date.scan_all')}
                </button>
            `
        });
    }

    getBelowQuickBarHTML() {
        const prefix = this.options.classPrefix;
        return `
            <div class="${prefix}-scan-progress flex items-center gap-2 mb-3 text-xs text-secondary shrink-0" style="display: none;">
                <span class="spinner" style="width: 12px; height: 12px; border-width: 2px; margin: 0;"></span>
                <span class="${prefix}-scan-progress-text"></span>
            </div>
        `;
    }

    renderItemControlHTML(item, index) {
        return this.getItemInputHTML(item, index, {
            inputType: 'datetime-local',
            label: window.i18n.t('media.info.custom_date')
        });
    }

    renderItemExtraActionsHTML(_item, index) {
        const prefix = this.options.classPrefix;
        const label = escapeAttr(window.i18n.t('bulk_modal.custom_date.scan'));
        return `
            <button type="button"
                class="${prefix}-scan w-8 h-8 shrink-0 surface hover:surface-light text-secondary hover:text flex items-center justify-center transition-colors border cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                data-index="${index}" aria-label="${label}" title="${label}">
                ${window.Icons.search({ size: 14 })}
            </button>
        `;
    }

    mapItem(item) {
        const currentIso = item.custom_date || item.uploaded_at || null;
        const currentValue = toLocalInputDateTime(currentIso);
        return {
            currentIso,
            uploadedAtIso: item.uploaded_at || null,
            uploadedValue: toLocalInputDateTime(item.uploaded_at),
            currentValue,
            newValue: currentValue,
            resetToUpload: false,
            dateOrigin: null,
            scanNotFound: false
        };
    }

    isItemModified(item) {
        if (!item) return false;
        if (item.resetToUpload) {
            const curTs = item.currentIso ? Date.parse(item.currentIso) : NaN;
            const upTs = item.uploadedAtIso ? Date.parse(item.uploadedAtIso) : NaN;
            return (!isNaN(curTs) && !isNaN(upTs)) ? curTs !== upTs : item.currentValue !== item.uploadedValue;
        }
        return item.newValue !== item.currentValue;
    }

    formatCurrentValue(item) {
        return escapeHtml(formatDateTime(item.currentIso || item.currentValue, window.i18n.t('common.none')));
    }

    formatNewValue(item) {
        const target = item.resetToUpload ? (item.uploadedAtIso || item.uploadedValue) : item.newValue;
        return escapeHtml(formatDateTime(target, window.i18n.t('common.none')));
    }

    formatBadge(item) {
        if (item.dateOrigin) {
            return formatCustomDateOriginBadge(item.dateOrigin);
        }
        if (item.scanNotFound) {
            const label = escapeHtml(window.i18n.t('bulk_modal.custom_date.no_date_found'));
            return `<span class="badge surface border border-color text-secondary text-[10px] px-1.5 py-0.5 shrink-0" title="${label}">${label}</span>`;
        }
        return '';
    }

    validateQuickValue(trimmed) {
        if (!parseLocalInputDateTime(trimmed)) {
            app?.showNotification?.(window.i18n.t('notifications.media.error_updating_date'), 'error');
            return false;
        }
        return true;
    }

    onItemValueCleared(item) {
        item.resetToUpload = false;
        item.dateOrigin = null;
        item.scanNotFound = false;
    }

    onItemInput(item, value) {
        const trimmed = (value || '').trim();
        item.newValue = trimmed;
        item.resetToUpload = trimmed === '';
        item.dateOrigin = null;
        item.scanNotFound = false;
    }

    onSecondaryAction() {
        this.itemsData.forEach(item => {
            item.newValue = item.uploadedValue;
            item.resetToUpload = true;
            item.dateOrigin = null;
            item.scanNotFound = false;
        });
    }

    toSavePayload(item) {
        if (item.resetToUpload || !item.newValue) return { id: item.mediaId, custom_date: null };
        const iso = parseLocalInputDateTime(item.newValue);
        if (!iso) {
            app?.showNotification?.(window.i18n.t('notifications.media.error_updating_date'), 'error');
            return null;
        }
        return { id: item.mediaId, custom_date: iso };
    }

    setupFieldEventListeners() {
        const prefix = this.options.classPrefix;
        this.modalElement?.querySelector(`#${prefix}-scan-all`)?.addEventListener('click', () => this._scanAllItems());
        this.modalElement?.querySelector(`.${prefix}-items`)?.addEventListener('click', (e) => {
            const scanBtn = e.target.closest(`.${prefix}-scan`);
            if (!scanBtn) return;
            const index = parseInt(scanBtn.dataset.index, 10);
            if (!isNaN(index)) this._scanSingleItem(index, scanBtn);
        });
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
        if (!item) return false;
        const prefix = this.options.classPrefix;
        const localVal = result?.custom_date ? toLocalInputDateTime(result.custom_date) : '';
        if (localVal) {
            item.newValue = localVal;
            item.resetToUpload = false;
            item.dateOrigin = result.origin || null;
            item.scanNotFound = false;
            const input = this.modalElement?.querySelector(`.${prefix}-item[data-index="${index}"] .${prefix}-item-input`);
            if (input) input.value = localVal;
            this._updateItemStatusDOM(index);
            this.showSaveButton();
            return true;
        }
        item.dateOrigin = null;
        item.scanNotFound = true;
        this._updateItemStatusDOM(index);
        return false;
    }

    async _scanSingleItem(index, btn) {
        if (this._isScanningAll || this.isCancelled || !this.itemsData[index]) return;
        const item = this.itemsData[index];
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
            if (!this.isCancelled) this._applyScanResult(index, (data.items || {})[String(item.mediaId)]);
        } catch (e) {
            if (e.name !== 'AbortError') {
                console.error('Error scanning date:', e);
                app?.showNotification?.(window.i18n.t('notifications.error_occurred'), 'error');
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
        let scanned = 0, found = 0, failed = false;

        this._setScanAllBusy(true, `${window.i18n.t('admin.actions.scanning')} (0/${total})`);
        try {
            for (let i = 0; i < ids.length && !this.isCancelled; i += 10) {
                const chunk = ids.slice(i, i + 10);
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
                    if (idx !== undefined && this._applyScanResult(idx, results[String(mid)])) found++;
                }
                scanned += chunk.length;
                this._setScanAllBusy(true, `${window.i18n.t('admin.actions.scanning')} (${scanned}/${total})`);
            }
        } catch (e) {
            if (e.name !== 'AbortError') {
                failed = true;
                console.error('Error scanning dates in bulk:', e);
                app?.showNotification?.(window.i18n.t('notifications.error_occurred'), 'error');
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
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkCustomDateModal;
}
