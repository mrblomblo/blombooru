class AcknowledgementsModal {
    constructor() {
        this.modalElement = null;
        this.cachedHtml = null;
        this._escapeHandler = null;
    }

    static init() {
        const instance = new AcknowledgementsModal();
        const btn = document.getElementById('footer-acknowledgements-btn');
        if (btn) {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                instance.open();
            });
        }
    }

    async open() {
        if (!this.cachedHtml) {
            const t = (key, params) => (window.i18n.t(key, params));
            try {
                const response = await fetch('/api/acknowledgements');
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                const data = await response.json();
                this.cachedHtml = data && data.html ? data.html : `<p class="text-secondary">${t('acknowledgements.not_found')}</p>`;
            } catch (error) {
                console.error('Failed to load acknowledgements:', error);
                this.cachedHtml = `<p class="text-secondary">${t('acknowledgements.failed_to_load')}</p>`;
            }
        }

        this.render(this.cachedHtml);
    }

    render(htmlContent) {
        const existing = document.getElementById('acknowledgements-modal-overlay');
        if (existing) {
            existing.remove();
        }

        const overlay = document.createElement('div');
        overlay.id = 'acknowledgements-modal-overlay';
        overlay.className = 'age-verification-overlay';

        const t = (key, params) => (window.i18n.t(key, params));
        const currentLang = window.CURRENT_LANGUAGE || 'en';
        const showNotice = currentLang !== 'en';

        const modalTitle = t('acknowledgements.modal_title');
        const noticeText = t('acknowledgements.english_only_notice');
        const searchPlaceholder = t('acknowledgements.search_placeholder');
        const closeText = t('common.close');

        overlay.innerHTML = `
            <div class="surface border-2 border-primary p-4 md:p-6 mx-2 md:mx-0 max-w-5xl w-full flex flex-col shadow-2xl" style="max-height: 85vh;">
                <div class="flex items-center justify-between gap-2 mb-2">
                    <h2 class="text-lg md:text-xl font-bold text-primary">${modalTitle}</h2>
                </div>
                ${showNotice ? `<p class="text-xs text-secondary italic mb-2">${noticeText}</p>` : ''}
                <div class="mb-2">
                    <input type="text" id="acknowledgements-search-input"
                        placeholder="${searchPlaceholder}"
                        class="w-full bg px-3 py-1.5 border text text-xs sm:text-sm focus:outline-none focus:border-primary hover:border-primary transition-colors"
                        autocomplete="off" />
                </div>
                <div id="acknowledgements-scroll-body" class="acknowledgements-content overflow-y-auto custom-scrollbar flex-1 text-left text-sm mt-2 space-y-3" style="overscroll-behavior: contain;">
                    ${htmlContent}
                </div>
                <div class="flex pt-4 border-t justify-center mt-3">
                    <button id="acknowledgements-close-btn" class="btn-primary px-6 py-3 font-bold text-sm cursor-pointer">
                        ${closeText}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        this.modalElement = overlay;

        // Close button handler
        const closeBtn = overlay.querySelector('#acknowledgements-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }

        // Close on backdrop click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                this.close();
            }
        });

        // Close on Escape key
        this._escapeHandler = (e) => {
            if (e.key === 'Escape') {
                this.close();
            }
        };
        document.addEventListener('keydown', this._escapeHandler);

        // Instant search / filter
        const searchInput = overlay.querySelector('#acknowledgements-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                const query = e.target.value.trim().toLowerCase();
                const cards = overlay.querySelectorAll('.acknowledgement-card');
                cards.forEach((card) => {
                    const pkgName = card.getAttribute('data-pkg-name') || '';
                    const text = card.textContent.toLowerCase();
                    if (!query || pkgName.includes(query) || text.includes(query)) {
                        card.style.display = '';
                    } else {
                        card.style.display = 'none';
                    }
                });
            });
            // Focus search input
            setTimeout(() => searchInput.focus(), 50);
        }
    }

    close() {
        if (this._escapeHandler) {
            document.removeEventListener('keydown', this._escapeHandler);
            this._escapeHandler = null;
        }
        if (this.modalElement) {
            this.modalElement.remove();
            this.modalElement = null;
        }
    }
}

// Auto-initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    AcknowledgementsModal.init();
});
