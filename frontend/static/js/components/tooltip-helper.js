class TooltipHelper {
    constructor(options = {}) {
        this.options = {
            id: options.id || 'media-tooltip',
            delay: options.delay || 300,
            maxWidth: options.maxWidth || 300,
            ...options
        };

        this.tooltipElement = null;
        this.activeElement = null;
        this.hoverTimeouts = new Map();
        this.scrollHandler = null;

        this.init();
    }

    init() {
        this.createTooltip();
        this.setupScrollHandler();
    }

    createTooltip() {
        // Check if tooltip already exists
        if (!document.getElementById(this.options.id)) {
            const tooltip = document.createElement('div');
            tooltip.id = this.options.id;
            tooltip.style.cssText = `
                position: absolute;
                background: rgba(0, 0, 0, 0.95);
                color: white;
                padding: 8px 12px;
                font-size: 13px;
                pointer-events: none;
                z-index: 10000;
                max-width: ${this.options.maxWidth}px;
                word-wrap: break-word;
                display: none;
                border: 1px solid rgba(255, 255, 255, 0.1);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
            `;
            document.body.appendChild(tooltip);
        }
        this.tooltipElement = document.getElementById(this.options.id);
        return this.tooltipElement;
    }

    show(element, content) {
        if (!content) return;

        // Handle different content types
        let displayText = '';

        if (typeof content === 'string') {
            displayText = content;
        } else if (Array.isArray(content)) {
            // Assume array of tag objects or strings
            const items = content.map(item => {
                if (typeof item === 'string') return item;
                if (item.name) return item.name;
                return String(item);
            });

            // Sort alphabetically
            items.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
            displayText = items.join(', ');
        } else if (typeof content === 'object' && content.text) {
            displayText = content.text;
        }

        if (!displayText) return;

        this.tooltipElement.textContent = displayText;
        this.tooltipElement.style.display = 'block';
        this.position(element);
        this.activeElement = element;
    }

    position(element) {
        const rect = element.getBoundingClientRect();
        const tooltipRect = this.tooltipElement.getBoundingClientRect();

        // Calculate position (above the element by default)
        let top = rect.top - tooltipRect.height - 10;
        let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);

        // If tooltip would go off top of screen, show below instead
        if (top < 10) {
            top = rect.bottom + 10;
        }

        // Keep tooltip within viewport horizontally
        if (left < 10) {
            left = 10;
        } else if (left + tooltipRect.width > window.innerWidth - 10) {
            left = window.innerWidth - tooltipRect.width - 10;
        }

        // Add scroll offset
        top += window.scrollY;
        left += window.scrollX;

        this.tooltipElement.style.top = `${top}px`;
        this.tooltipElement.style.left = `${left}px`;
    }

    hide() {
        if (this.tooltipElement) {
            this.tooltipElement.style.display = 'none';
        }
        this.activeElement = null;
    }

    // Add hover events to an element
    addToElement(element, contentProvider, options = {}) {
        const delay = options.delay || this.options.delay;

        element.addEventListener('mouseenter', () => {
            // Clear any existing timeout for this element
            if (this.hoverTimeouts.has(element)) {
                clearTimeout(this.hoverTimeouts.get(element));
            }

            // Set new timeout
            const timeoutId = setTimeout(() => {
                const content = typeof contentProvider === 'function'
                    ? contentProvider(element)
                    : contentProvider;

                if (content) {
                    this.show(element, content);
                }

                this.hoverTimeouts.delete(element);
            }, delay);

            this.hoverTimeouts.set(element, timeoutId);
        });

        element.addEventListener('mouseleave', () => {
            // Clear timeout if still pending
            if (this.hoverTimeouts.has(element)) {
                clearTimeout(this.hoverTimeouts.get(element));
                this.hoverTimeouts.delete(element);
            }
            this.hide();
        });
    }

    // Setup scroll handler to reposition tooltip if visible
    setupScrollHandler() {
        this.scrollHandler = () => {
            if (this.activeElement && this.tooltipElement.style.display === 'block') {
                this.position(this.activeElement);
            }
        };

        window.addEventListener('scroll', this.scrollHandler, { passive: true });
    }

    // Cleanup method
    destroy() {
        // Clear all timeouts
        for (const timeoutId of this.hoverTimeouts.values()) {
            clearTimeout(timeoutId);
        }
        this.hoverTimeouts.clear();

        // Remove scroll handler
        if (this.scrollHandler) {
            window.removeEventListener('scroll', this.scrollHandler);
        }

        // Remove tooltip element
        if (this.tooltipElement && this.tooltipElement.parentNode) {
            this.tooltipElement.parentNode.removeChild(this.tooltipElement);
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TooltipHelper;
}
