class BulkManageTagsModal {
    constructor(options = {}) {
        this.options = {
            id: 'bulk-manage-tags-modal',
            onAction: options.onAction || (() => { }), // (action) => {}
            ...options
        };
        this.element = null;
    }

    show() {
        if (!this.element) {
            this.create();
        }
        this.element.style.display = 'flex';

        // Prevent body scroll
        document.body.style.overflow = 'hidden';
    }

    hide() {
        if (this.element) {
            this.element.style.display = 'none';
        }
        document.body.style.overflow = '';
    }

    create() {
        const modal = document.createElement('div');
        modal.id = this.options.id;
        modal.className = 'fixed inset-0 flex items-center justify-center z-50';
        modal.style.background = 'rgba(0, 0, 0, 0.5)';
        modal.style.display = 'none';

        modal.innerHTML = `
            <div class="surface p-2 sm:p-6 border shadow-2xl w-full max-w-sm mx-4 relative">
                <div class="flex justify-between items-center mb-4 flex-shrink-0">
                    <h2 class="text-base sm:text-lg font-bold truncate pr-4">${window.i18n.t('bulk_modal.manage_title')}</h2>
                    <button class="close-btn flex items-center justify-center w-10 h-10 sm:w-8 sm:h-8 rounded-full surface-light hover:bg-danger hover:tag-text transition-colors" aria-label="Close">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5 sm:w-4 sm:h-4">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                    </button>
                </div>
                
                <div class="flex flex-col gap-3">
                    <button class="action-btn text-left px-4 py-4 bg hover:border-primary hover:text-primary transition-colors border flex items-center gap-3" data-action="manual">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                        </svg>
                        <div class="flex-1">
                            <div class="font-bold text-sm">${window.i18n.t('bulk_modal.menu.manual_editor')}</div>
                            <div class="text-xs opacity-70">${window.i18n.t('bulk_modal.menu.manual_desc')}</div>
                        </div>
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="opacity-50">
                            <polyline points="9 18 15 12 9 6"></polyline>
                        </svg>
                    </button>

                    <button class="action-btn text-left px-4 py-4 bg hover:border-primary hover:text-primary transition-colors border flex items-center gap-3" data-action="ai_tags">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
                        </svg>
                        <div class="flex-1">
                            <div class="font-bold text-sm">${window.i18n.t('bulk_modal.menu.ai_tags')}</div>
                            <div class="text-xs opacity-70">${window.i18n.t('bulk_modal.menu.ai_desc')}</div>
                        </div>
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="opacity-50">
                            <polyline points="9 18 15 12 9 6"></polyline>
                        </svg>
                    </button>

                    <button class="action-btn text-left px-4 py-4 bg hover:border-primary hover:text-primary transition-colors border flex items-center gap-3" data-action="wd_tagger">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                            <circle cx="12" cy="13" r="4"></circle>
                        </svg>
                        <div class="flex-1">
                            <div class="font-bold text-sm">${window.i18n.t('bulk_modal.menu.wd_tagger')}</div>
                            <div class="text-xs opacity-70">${window.i18n.t('bulk_modal.menu.wd_desc')}</div>
                        </div>
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="opacity-50">
                            <polyline points="9 18 15 12 9 6"></polyline>
                        </svg>
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this.element = modal;
        this.setupResultListeners();
    }

    setupResultListeners() {
        if (!this.element) return;

        this.element.addEventListener('click', (e) => {
            // Close button
            if (e.target.closest('.close-btn') || e.target === this.element) {
                this.hide();
                return;
            }

            // Action buttons
            const btn = e.target.closest('.action-btn');
            if (btn) {
                const action = btn.dataset.action;
                this.hide();
                if (this.options.onAction) {
                    this.options.onAction(action);
                }
            }
        });

        // Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.element.style.display === 'flex') {
                this.hide();
            }
        });
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = BulkManageTagsModal;
}
