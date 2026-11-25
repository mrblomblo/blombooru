class BulkSourceModal extends BulkFieldModalBase {
    constructor(options = {}) {
        super({
            id: 'bulk-source-modal',
            title: window.i18n.t('modal.bulk_source.title'),
            classPrefix: 'bulk-source',
            statusWrapClass: 'break-all',
            ...options
        });
    }

    getReviewText() {
        return window.i18n.t('bulk_modal.source.review_sources');
    }

    getQuickBarHTML() {
        return this.getQuickInputBarHTML({
            inputType: 'url',
            placeholder: 'https://example.com/source',
            label: window.i18n.t('media.info.source'),
            secondaryText: window.i18n.t('modal.clear_tags.confirm')
        });
    }

    renderItemControlHTML(item, index) {
        return this.getItemInputHTML(item, index, {
            inputType: 'url',
            placeholder: 'https://example.com/source',
            label: window.i18n.t('media.info.source')
        });
    }

    mapItem(item) {
        const currentValue = (item.source || '').trim();
        return { currentValue, newValue: currentValue };
    }

    isItemModified(item) {
        return Boolean(item) && (item.newValue || '').trim() !== (item.currentValue || '').trim();
    }

    _formatSource(val) {
        const trimmed = (val || '').trim();
        return trimmed ? escapeHtml(trimmed) : `<span class="italic">${escapeHtml(window.i18n.t('common.none'))}</span>`;
    }

    formatCurrentValue(item) {
        return this._formatSource(item.currentValue);
    }

    formatNewValue(item) {
        return this._formatSource(item.newValue);
    }

    onSecondaryAction() {
        this.itemsData.forEach(item => { item.newValue = ''; });
    }

    toSavePayload(item) {
        return { id: item.mediaId, source: (item.newValue || '').trim() || null };
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkSourceModal;
}
