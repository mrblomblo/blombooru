class BulkRatingModal extends BulkFieldModalBase {
    static RATINGS = ['safe', 'questionable', 'explicit'];

    constructor(options = {}) {
        super({
            id: 'bulk-rating-modal',
            title: window.i18n.t('modal.bulk_rating.title'),
            classPrefix: 'bulk-rating',
            fetchProjection: 'tags_only',
            saveEndpoint: '/api/media/bulk-update-ratings',
            ...options
        });

        this.selectedQuickRating = 'safe';
    }

    getReviewText() {
        return window.i18n.t('bulk_modal.rating.review_ratings');
    }

    getQuickBarHTML() {
        const prefix = this.options.classPrefix;
        const selected = this.selectedQuickRating || 'safe';
        return `
            <div class="flex items-center gap-2">
                <div class="flex gap-1" id="${prefix}-quick-selector">
                    ${BulkRatingModal.RATINGS.map(r => `
                        <button type="button"
                            class="quick-rating-btn px-3 py-1.5 text-xs border cursor-pointer transition-colors ${r === selected ? 'btn-primary' : 'bg hover:border-primary'}"
                            data-rating="${r}">
                            ${window.i18n.t('common.' + r)}
                        </button>
                    `).join('')}
                </div>
            </div>
            <button type="button" id="${prefix}-quick-apply" class="btn-primary px-3 py-1.5 text-xs cursor-pointer shrink-0">
                ${window.i18n.t('common.apply')}
            </button>
        `;
    }

    renderItemControlHTML(item, index) {
        const active = item.newValue || item.currentValue || 'safe';
        return `
            <div class="flex gap-1.5 flex-wrap">
                ${BulkRatingModal.RATINGS.map(r => `
                    <button type="button"
                        class="item-rating-btn px-3 py-1.5 text-xs border cursor-pointer transition-colors ${r === active ? 'btn-primary' : 'bg hover:border-primary text-secondary hover:text'}"
                        data-index="${index}" data-rating="${r}">
                        ${window.i18n.t('common.' + r)}
                    </button>
                `).join('')}
            </div>
        `;
    }

    mapItem(item) {
        const currentValue = item.rating || 'safe';
        const prefilled = this.options.prefillRatings?.[item.id] || null;
        return { currentValue, newValue: prefilled || currentValue };
    }

    formatCurrentValue(item) {
        return escapeHtml(window.i18n.t('common.' + (item.currentValue || 'safe')));
    }

    formatNewValue(item) {
        return escapeHtml(window.i18n.t('common.' + (item.newValue || item.currentValue || 'safe')));
    }

    onItemReset(item, index) {
        item.newValue = item.currentValue;
        this._replaceItemRowDOM(index);
    }

    toSavePayload(item) {
        return { id: item.mediaId, rating: item.newValue };
    }

    setupFieldEventListeners() {
        const prefix = this.options.classPrefix;

        this.modalElement?.querySelectorAll(`#${prefix}-quick-selector .quick-rating-btn`).forEach(btn => {
            btn.addEventListener('click', (e) => {
                const rating = e.currentTarget.dataset.rating;
                this.selectedQuickRating = rating;
                this.modalElement.querySelectorAll(`#${prefix}-quick-selector .quick-rating-btn`).forEach(b => {
                    const isSelected = b.dataset.rating === rating;
                    b.classList.toggle('btn-primary', isSelected);
                    b.classList.toggle('bg', !isSelected);
                });
            });
        });

        this.modalElement?.querySelector(`#${prefix}-quick-apply`)?.addEventListener('click', () => {
            if (!this.itemsData.length) return;
            this.onQuickApply(this.selectedQuickRating || 'safe');
        });

        this.modalElement?.querySelector(`.${prefix}-items`)?.addEventListener('click', (e) => {
            const ratingBtn = e.target.closest('.item-rating-btn');
            if (!ratingBtn) return;
            const index = parseInt(ratingBtn.dataset.index, 10);
            const rating = ratingBtn.dataset.rating;
            if (!isNaN(index) && rating && this.itemsData[index]) {
                this.itemsData[index].newValue = rating;
                this._replaceItemRowDOM(index);
                this.showSaveButton();
            }
        });
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkRatingModal;
}
