class ModalHelper {
    constructor(options = {}) {
        this.options = {
            id: options.id || 'modal-helper',
            type: options.type || 'info', // 'info', 'warning', 'danger'
            title: options.title || this.getDefaultTitle(options.type),
            message: options.message || '',
            showIcon: options.showIcon !== false,
            confirmText: options.confirmText || window.i18n.t('modal.buttons.yes'),
            cancelText: options.cancelText || window.i18n.t('modal.buttons.no'),
            confirmId: options.confirmId || 'modal-confirm-yes',
            cancelId: options.cancelId || 'modal-confirm-no',
            onConfirm: options.onConfirm || null,
            onCancel: options.onCancel || null,
            blurTarget: options.blurTarget || null, // CSS selector for element to blur
            closeOnEscape: options.closeOnEscape !== false,
            closeOnOutsideClick: options.closeOnOutsideClick !== false,
            ...options
        };

        this.modalElement = null;
        this.isVisible = false;

        this.init();
    }

    init() {
        this.createModal();
        this.setupEventListeners();
    }

    getDefaultTitle(type) {
        const titles = {
            info: window.i18n.t('modal.default_titles.info'),
            warning: window.i18n.t('modal.default_titles.warning'),
            danger: window.i18n.t('modal.default_titles.danger')
        };
        return titles[type] || window.i18n.t('modal.default_titles.info');
    }

    getIconSVG(type) {
        const icons = {
            info: `
                <svg class="mx-auto mb-4" width="64" height="64" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" fill="var(--info)"/>
                </svg>
            `,
            warning: `
                <svg class="mx-auto mb-4" width="64" height="64" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" fill="var(--warning)"/>
                </svg>
            `,
            danger: `
                <svg class="mx-auto mb-4" width="64" height="64" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" fill="var(--danger)"/>
                </svg>
            `
        };
        return icons[type] || icons.info;
    }

    getTitleClass(type) {
        const classes = {
            info: 'text-info',
            warning: 'text-warning',
            danger: 'text-danger'
        };
        return classes[type] || classes.info;
    }

    getBorderClass(type) {
        const classes = {
            info: 'border-info',
            warning: 'border-warning',
            danger: 'border-danger'
        };
        return classes[type] || classes.info;
    }

    getConfirmButtonClass(type) {
        const classes = {
            info: 'bg-info hover:bg-info',
            warning: 'bg-warning hover:bg-warning',
            danger: 'bg-danger hover:bg-danger'
        };
        return classes[type] || classes.info;
    }

    getCancelButtonClass(type) {
        const classes = {
            info: 'surface-light hover:surface-light',
            warning: 'surface-light hover:surface-light',
            danger: 'surface-light hover:surface-light'
        };
        return classes[type] || classes.info;
    }

    createModal() {
        // Check if modal already exists and remove it to prevent event listener duplication
        const existing = document.getElementById(this.options.id);
        if (existing) {
            existing.remove();
        }

        const modal = document.createElement('div');
        modal.id = this.options.id;
        modal.className = 'age-verification-overlay';
        modal.style.display = 'none';

        const iconHTML = this.options.showIcon ? this.getIconSVG(this.options.type) : '';

        modal.innerHTML = `
            <div class="surface border-2 ${this.getBorderClass(this.options.type)} p-4 pb-2 md:p-8 md:pb-4 mx-1 md:mx-0 max-w-lg w-full text-center">
                ${iconHTML}
                <h2 class="text-xl font-bold mb-4 ${this.getTitleClass(this.options.type)}">${this.options.title}</h2>
                <p class="text-base mb-6 text">${this.options.message}</p>
                <div class="flex gap-4 mt-2 md:mt-4 justify-center">
                    <button id="${this.options.confirmId}" class="px-6 py-3 transition-colors ${this.getConfirmButtonClass(this.options.type)} tag-text font-bold text-sm">
                        ${this.options.confirmText}
                    </button>
                    ${this.options.cancelText ? `<button id="${this.options.cancelId}" class="px-6 py-3 transition-colors ${this.getCancelButtonClass(this.options.type)} text font-bold text-sm">
                        ${this.options.cancelText}
                    </button>` : ''}
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this.modalElement = modal;
    }

    setupEventListeners() {
        const confirmBtn = document.getElementById(this.options.confirmId);
        const cancelBtn = document.getElementById(this.options.cancelId);

        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => this.confirm());
        }

        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.cancel());
        }

        if (this.options.closeOnEscape) {
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this.isVisible) {
                    this.cancel();
                }
            });
        }

        if (this.options.closeOnOutsideClick) {
            this.modalElement.addEventListener('click', (e) => {
                if (e.target === this.modalElement) {
                    this.cancel();
                }
            });
        }
    }

    show() {
        if (!this.modalElement) {
            this.createModal();
        }

        this.modalElement.style.display = 'flex';
        this.isVisible = true;

        // Blur target element if specified
        if (this.options.blurTarget) {
            const target = document.querySelector(this.options.blurTarget);
            if (target) {
                target.classList.add('media-blurred');
            }
        }

        return this;
    }

    hide() {
        if (this.modalElement) {
            this.modalElement.style.display = 'none';
            this.isVisible = false;

            // Remove blur from target element
            if (this.options.blurTarget) {
                const target = document.querySelector(this.options.blurTarget);
                if (target) {
                    target.classList.remove('media-blurred');
                }
            }
        }

        return this;
    }

    confirm() {
        this.hide();
        if (typeof this.options.onConfirm === 'function') {
            this.options.onConfirm();
        }
    }

    cancel() {
        this.hide();
        if (typeof this.options.onCancel === 'function') {
            this.options.onCancel();
        }
    }

    updateContent(options = {}) {
        if (options.title) {
            this.options.title = options.title;
        }
        if (options.message) {
            this.options.message = options.message;
        }
        if (options.type) {
            this.options.type = options.type;
        }

        // Recreate modal with new content
        if (this.modalElement && this.modalElement.parentNode) {
            this.modalElement.parentNode.removeChild(this.modalElement);
        }
        this.createModal();
        this.setupEventListeners();

        return this;
    }

    destroy() {
        this.hide();
        if (this.modalElement && this.modalElement.parentNode) {
            this.modalElement.parentNode.removeChild(this.modalElement);
        }
        this.modalElement = null;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ModalHelper;
}
