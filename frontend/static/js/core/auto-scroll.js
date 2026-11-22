class AutoScrollEngine {
    constructor(options = {}) {
        this.scrollEl = options.scrollEl || null;
        this.topZone = options.topZone !== undefined ? options.topZone : 100;
        this.bottomZone = options.bottomZone !== undefined ? options.bottomZone : 100;
        this.minSpeed = options.minSpeed !== undefined ? options.minSpeed : 4;
        this.maxSpeed = options.maxSpeed !== undefined ? options.maxSpeed : 22;

        this._speed = 0;
        this._rafId = null;
        this._lastPointerX = 0;
        this._lastPointerY = 0;
        this._onScroll = null;
    }

    getScrollElement(customEl = null) {
        if (customEl) {
            if (typeof customEl === 'function') return customEl();
            return customEl;
        }
        if (this.scrollEl) {
            if (typeof this.scrollEl === 'function') return this.scrollEl();
            return this.scrollEl;
        }
        return document.getElementById('main-scroll') || document.scrollingElement || document.documentElement || window;
    }

    check(clientX, clientY, options = {}) {
        const scrollEl = this.getScrollElement(options.scrollEl);
        if (!scrollEl) return;

        const viewportHeight = window.innerHeight;
        const topZone = options.topZone !== undefined ? options.topZone : this.topZone;
        const bottomZone = options.bottomZone !== undefined ? options.bottomZone : this.bottomZone;
        const minSpeed = options.minSpeed !== undefined ? options.minSpeed : this.minSpeed;
        const maxSpeed = options.maxSpeed !== undefined ? options.maxSpeed : this.maxSpeed;

        let bottomLimit = viewportHeight;
        if (options.bottomElement) {
            const rect = options.bottomElement.getBoundingClientRect();
            if (rect.top > 0 && rect.top < viewportHeight) {
                bottomLimit = rect.top;
            }
        } else if (typeof options.bottomLimit === 'function') {
            bottomLimit = options.bottomLimit();
        } else if (typeof options.bottomLimit === 'number') {
            bottomLimit = options.bottomLimit;
        } else {
            const bar = document.querySelector('.manual-reorder-bar:not(.hidden)');
            if (bar && bar.offsetParent !== null) {
                const rect = bar.getBoundingClientRect();
                if (rect.top > 0 && rect.top < viewportHeight) {
                    bottomLimit = rect.top;
                }
            }
        }

        if (clientY < topZone) {
            const ratio = Math.max(0, Math.min(1, (topZone - clientY) / topZone));
            const speed = -Math.round(minSpeed + ratio * (maxSpeed - minSpeed));
            this.start(scrollEl, speed, clientX, clientY, options.onScroll);
        } else if (clientY > bottomLimit - bottomZone) {
            const dist = clientY - (bottomLimit - bottomZone);
            const ratio = Math.max(0, Math.min(1, dist / bottomZone));
            const speed = Math.round(minSpeed + ratio * (maxSpeed - minSpeed));
            this.start(scrollEl, speed, clientX, clientY, options.onScroll);
        } else {
            this.stop();
        }
    }

    start(scrollEl, speed, clientX, clientY, onScroll = null) {
        this._speed = speed;
        this._lastPointerX = clientX;
        this._lastPointerY = clientY;
        if (onScroll !== undefined && onScroll !== null) {
            this._onScroll = onScroll;
        }

        if (this._rafId) return;

        const step = () => {
            if (!this._speed) {
                this._rafId = null;
                return;
            }

            const isWindow = scrollEl === window || scrollEl === document.documentElement || scrollEl === document.body;
            const currentTop = isWindow ? window.scrollY : scrollEl.scrollTop;
            const maxScroll = isWindow
                ? Math.max(0, document.documentElement.scrollHeight - window.innerHeight)
                : Math.max(0, scrollEl.scrollHeight - scrollEl.clientHeight);

            if (isWindow) {
                window.scrollBy(0, this._speed);
            } else {
                scrollEl.scrollTop += this._speed;
            }

            const newTop = isWindow ? window.scrollY : scrollEl.scrollTop;

            if (this._onScroll) {
                this._onScroll(this._lastPointerX, this._lastPointerY);
            }

            if (newTop === currentTop && (
                (this._speed < 0 && currentTop <= 0) ||
                (this._speed > 0 && currentTop >= maxScroll)
            )) {
                this.stop();
                return;
            }

            this._rafId = requestAnimationFrame(step);
        };

        this._rafId = requestAnimationFrame(step);
    }

    updatePointer(clientX, clientY) {
        this._lastPointerX = clientX;
        this._lastPointerY = clientY;
    }

    stop() {
        if (this._rafId) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }
        this._speed = 0;
        this._onScroll = null;
    }

    get isScrolling() {
        return this._speed !== 0;
    }
}

window.AutoScrollEngine = AutoScrollEngine;
window.autoScroll = new AutoScrollEngine();
