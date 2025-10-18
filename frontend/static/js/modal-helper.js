class ModalHelper {
    constructor(options = {}) {
        this.options = {
            id: options.id || 'modal-helper',
            type: options.type || 'info', // 'info', 'warning', 'danger'
            title: options.title || this.getDefaultTitle(options.type),
            message: options.message || '',
            showIcon: options.showIcon !== false,
            confirmText: options.confirmText || 'Yes',
            cancelText: options.cancelText || 'No',
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
            info: 'Info',
            warning: 'Warning',
            danger: 'Explicit Content Warning'
        };
        return titles[type] || 'Info';
    }

    getIconSVG(type) {
        const icons = {
            info: `
                <svg class="mx-auto mb-4" width="64" height="64" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" fill="var(--blue)"/>
                </svg>
            `,
            warning: `
                <svg class="mx-auto mb-4" width="64" height="64" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" fill="var(--yellow)"/>
                </svg>
            `,
            danger: `
                <svg class="mx-auto mb-4" width="64" height="64" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" fill="var(--red)"/>
                </svg>
            `
        };
        return icons[type] || icons.info;
    }

    getTitleClass(type) {
        const classes = {
            info: 'text-[var(--blue)]',
            warning: 'text-[var(--yellow)]',
            danger: 'text-danger'
        };
        return classes[type] || classes.info;
    }

    getBorderClass(type) {
        const classes = {
            info: 'border-[var(--blue)]',
            warning: 'border-[var(--yellow)]',
            danger: 'border-danger'
        };
        return classes[type] || classes.info;
    }

    getConfirmButtonClass(type) {
        const classes = {
            info: 'bg-[var(--blue)] hover:bg-[var(--blue)]',
            warning: 'bg-[var(--yellow)] hover:bg-[var(--yellow)]',
            danger: 'bg-success hover:bg-success'
        };
        return classes[type] || classes.info;
    }

    getCancelButtonClass(type) {
        const classes = {
            info: 'bg-danger hover:bg-danger',
            warning: 'bg-danger hover:bg-danger',
            danger: 'bg-danger hover:bg-danger'
        };
        return classes[type] || classes.info;
    }

    createModal() {
        // Check if modal already exists
        if (document.getElementById(this.options.id)) {
            this.modalElement = document.getElementById(this.options.id);
            return;
        }

        const modal = document.createElement('div');
        modal.id = this.options.id;
        modal.className = 'age-verification-overlay';
        modal.style.display = 'none';

        const iconHTML = this.options.showIcon ? this.getIconSVG(this.options.type) : '';
        
        modal.innerHTML = `
            <div class="surface border-2 ${this.getBorderClass(this.options.type)} p-8 max-w-md text-center">
                ${iconHTML}
                <h2 class="text-xl font-bold mb-4 ${this.getTitleClass(this.options.type)}">${this.options.title}</h2>
                <p class="text-base mb-6 text">${this.options.message}</p>
                <div class="flex gap-4 justify-center">
                    <button id="${this.options.confirmId}" class="px-6 py-3 ${this.getConfirmButtonClass(this.options.type)} tag-text font-bold text-sm">
                        ${this.options.confirmText}
                    </button>
                    <button id="${this.options.cancelId}" class="px-6 py-3 ${this.getCancelButtonClass(this.options.type)} tag-text font-bold text-sm">
                        ${this.options.cancelText}
                    </button>
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
