class BulkRatingModal {
    constructor(options = {}) {
        this.options = {
            onSave: options.onSave || (() => { })
        };
        this.modal = null;
        this.selectedItems = new Set();
    }

    show(selectedItems) {
        this.selectedItems = new Set(selectedItems);
        this.createModal();
        this.modal.style.display = 'flex';
    }

    createModal() {
        const existing = document.getElementById('bulk-rating-modal');
        if (existing) existing.remove();

        this.modal = document.createElement('div');
        this.modal.id = 'bulk-rating-modal';
        this.modal.className = 'modal';

        const countText = window.i18n.t('common.items_selected', { count: this.selectedItems.size });

        this.modal.innerHTML = `
            <div class="modal-content surface border p-4" style="max-width: 360px;">
                <div class="flex items-center mb-4 pb-3 border-b">
                    <h3 class="text-base font-bold">${window.i18n.t('modal.bulk_rating.title')}</h3>
                </div>

                <p class="mb-4 text-secondary text-xs">${countText}</p>

                <div class="grid grid-cols-1 gap-2 mb-3">
                    ${['safe', 'questionable', 'explicit'].map(rating => `
                        <label class="flex-1">
                            <input type="radio" name="bulk_rating_choice" value="${rating}" class="hidden bulk-rating-input" ${rating === 'safe' ? 'checked' : ''}>
                            <span class="block text-center px-3 py-1 border-1 cursor-pointer bg hover:border-primary transition-colors bulk-rating-label">
                                ${window.i18n.t('common.' + rating)}
                            </span>
                        </label>
                    `).join('')}
                </div>

                <div class="flex gap-2 justify-end pt-3 border-t">
                    <button id="bulk-rating-confirm" class="btn-primary">${window.i18n.t('common.confirm')}</button>
                    <button id="bulk-rating-cancel" class="btn">${window.i18n.t('common.cancel')}</button>
                </div>
            </div>
        `;

        document.body.appendChild(this.modal);

        // Apply initial checked state visually
        this._updateLabels('safe');

        // Wire radio change to update label styling
        this.modal.querySelectorAll('.bulk-rating-input').forEach(radio => {
            radio.addEventListener('change', (e) => {
                this._updateLabels(e.target.value);
            });
        });

        this.modal.querySelector('#bulk-rating-cancel').addEventListener('click', () => this.hide());
        this.modal.querySelector('#bulk-rating-confirm').addEventListener('click', () => this.confirm());

        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) this.hide();
        });

        this.modal.querySelector('.modal-content').addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    _updateLabels(selectedValue) {
        this.modal.querySelectorAll('.bulk-rating-label').forEach(label => {
            label.classList.remove('checked');
        });
        this.modal.querySelectorAll(`.bulk-rating-input[value="${selectedValue}"]`).forEach(radio => {
            radio.checked = true;
            const label = radio.nextElementSibling;
            if (label) label.classList.add('checked');
        });
    }

    async confirm() {
        const checkedRadio = this.modal.querySelector('.bulk-rating-input:checked');
        if (!checkedRadio) return;

        const newRating = checkedRadio.value;
        const confirmBtn = this.modal.querySelector('#bulk-rating-confirm');
        confirmBtn.disabled = true;
        confirmBtn.textContent = window.i18n.t('modal.buttons.saving');

        let successCount = 0;
        let errorCount = 0;

        const mediaIds = Array.from(this.selectedItems);

        for (let i = 0; i < mediaIds.length; i += 5) {
            const chunk = mediaIds.slice(i, i + 5);
            await Promise.all(chunk.map(async (id) => {
                try {
                    const response = await fetch(`/api/media/${id}`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ rating: newRating })
                    });
                    if (response.ok) successCount++;
                    else errorCount++;
                } catch (e) {
                    console.error(`Error updating rating for ${id}:`, e);
                    errorCount++;
                }
            }));
        }

        this.hide();

        if (typeof app !== 'undefined' && app.showNotification) {
            if (successCount > 0) {
                app.showNotification(
                    window.i18n.t('bulk_modal.notifications.updated_success', { count: successCount }),
                    'success'
                );
            }
            if (errorCount > 0) {
                app.showNotification(
                    window.i18n.t('bulk_modal.notifications.updated_failed', { count: errorCount }),
                    'error'
                );
            }
        }

        this.options.onSave();
    }

    hide() {
        if (this.modal) {
            this.modal.remove();
            this.modal = null;
        }
    }
}
