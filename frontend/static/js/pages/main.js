class I18n {
    constructor() {
        this.currentLang = window.CURRENT_LANGUAGE || 'en';
        this.loadPromise = null;

        // Use inlined translations from the data block if available
        const translationsDataTag = document.getElementById('translations-data');
        if (translationsDataTag) {
            try {
                this.translations = JSON.parse(translationsDataTag.textContent);
                this.loaded = true;
            } catch (e) {
                console.error("Failed to parse inline translations data:", e);
                this.translations = {};
                this.loaded = false;
            }
        } else {
            this.translations = {};
            this.loaded = false;
        }
    }

    async load(lang = null) {
        if (this.loaded && (!lang || lang === this.currentLang)) {
            return;
        }

        if (this.loadPromise) {
            return this.loadPromise;
        }

        this.loadPromise = (async () => {
            try {
                const targetLang = lang || this.currentLang;
                const response = await fetch(`/api/admin/translations?lang=${targetLang}`);
                if (response.ok) {
                    this.translations = await response.json();
                    this.currentLang = targetLang;
                    this.loaded = true;
                    window.dispatchEvent(new CustomEvent('i18n-loaded'));
                }
            } catch (error) {
                console.error('Error loading translations:', error);
            }
        })();

        return this.loadPromise;
    }

    /**
     * Get a translation string by dot-notation key
     * @param {string} key - Dot-notation key (e.g., 'common.albums')
     * @param {Object} params - Interpolation parameters (e.g., {count: 5})
     * @returns {string} Translated string or the key itself if not found
     */
    t(key, params = {}) {
        if (!key) return '';
        if (typeof key === 'object') {
            return this.t(key.key || key.message, { ...key.params, ...params });
        }
        if (typeof key === 'string' && key.includes(':::')) {
            const [baseKey, arg] = key.split(':::');
            const mergedParams = { error: arg, filename: arg, ...params };
            return this.t(baseKey, mergedParams);
        }

        const keys = key.split('.');
        let value = this.translations;

        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                return key;
            }
        }

        if (typeof value !== 'string' || value === "") {
            return key;
        }

        // Handle interpolation: {name} -> replaced with params.name
        if (params && Object.keys(params).length > 0) {
            return value.replace(/\{(\w+)\}/g, (match, paramKey) => {
                return params[paramKey] !== undefined ? params[paramKey] : match;
            });
        }

        return value;
    }
}

window.i18n = new I18n();

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

// Core functionality
class Blombooru {
    constructor() {
        this.autoScroll = window.autoScroll;
        this.isAdminMode = this.getCookie('admin_mode') === 'true';
        this.isAuthenticated = !!this.getCookie('admin_token');
        this.currentPage = 1;
        this.isLoading = false;
        this.hasMore = true;

        this.init();
    }

    async init() {
        await window.i18n.load();

        this.setupEventListeners();
        this.updateUI();

        // Load settings from localStorage or cookie
        const savedRating = localStorage.getItem('selectedRating') || this.getCookie('rating_filter');
        if (savedRating) {
            this.setRatingFilter(savedRating);
            localStorage.setItem('selectedRating', savedRating);
            this.setCookie('rating_filter', savedRating, 365);
        }

        // Check albums visibility
        this.checkAlbumsVisibility();
    }

    async checkAlbumsVisibility() {
        const navItem = document.getElementById('nav-albums-item');
        if (!navItem) return;

        try {
            // Only check if we're not already on an albums page (to avoid flickering if we are)
            if (!window.location.pathname.startsWith('/album')) {
                const response = await fetch('/api/albums?limit=100&root_only=true');
                if (response.ok) {
                    const data = await response.json();
                    const hasContent = data.items && data.items.some(album => album.media_count > 0);

                    if (!hasContent) {
                        navItem.style.display = 'none';
                    } else {
                        navItem.style.display = 'block';
                    }
                }
            }
        } catch (error) {
            console.error('Error checking albums visibility:', error);
        }
    }

    setupEventListeners() {
        // Admin mode toggle
        const adminToggle = document.getElementById('admin-mode-toggle');
        if (adminToggle) {
            adminToggle.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleAdminToggle();
            });
        }

        // Logout
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.logout();
            });
        }

        // Search form (desktop)
        const searchForm = document.getElementById('search-form');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.performSearch();
            });
        }

        // Search form (mobile)
        const searchFormMobile = document.getElementById('search-form-mobile');
        if (searchFormMobile) {
            searchFormMobile.addEventListener('submit', (e) => {
                e.preventDefault();
                this.performSearch();
            });
        }

        // Search help buttons
        const helpBtns = [
            document.getElementById('search-help-btn'),
            document.getElementById('search-help-btn-mobile')
        ];

        helpBtns.forEach(btn => {
            if (btn) {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.showSearchSyntaxGuide();
                });
            }
        });

        // Random search buttons
        const randomBtns = [
            document.getElementById('search-random-btn'),
            document.getElementById('search-random-btn-mobile')
        ];

        randomBtns.forEach(btn => {
            if (btn) {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.performRandomSearch();
                });
            }
        });
    }

    async toggleAdminMode() {
        const newMode = !this.isAdminMode;

        try {
            const response = await fetch('/api/admin/toggle-admin-mode?enabled=' + newMode, {
                method: 'POST'
            });

            if (response.ok) {
                this.isAdminMode = newMode;
                this.updateUI();

                // Show notification
                this.showNotification(
                    newMode ? window.i18n.t('notifications.admin_mode_enabled') : window.i18n.t('notifications.admin_mode_disabled'),
                    newMode ? 'success' : 'info'
                );
            }
        } catch (error) {
            console.error('Error toggling admin mode:', error);
        }
    }

    async logout() {
        try {
            await fetch('/api/admin/logout', { method: 'POST' });
            this.isAuthenticated = false;
            window.location.href = '/';
        } catch (error) {
            console.error('Error logging out:', error);
        }
    }

    updateAuthStatus(isAuthenticated) {
        this.isAuthenticated = isAuthenticated;
        this.updateUI();
    }

    updateUI() {
        const body = document.body;
        const logoutBtn = document.getElementById('logout-btn');
        const logoutBtnMobile = document.getElementById('logout-btn-mobile');

        // Update body class
        if (this.isAdminMode) {
            body.classList.add('admin-mode');
        } else {
            body.classList.remove('admin-mode');
        }

        // Show/hide logout button's
        if (logoutBtn) {
            logoutBtn.parentElement.style.display = this.isAuthenticated ? 'inline' : 'none';
            logoutBtnMobile.parentElement.style.display = this.isAuthenticated ? 'inline' : 'none';
        }
    }

    showNotification(message, type = 'info', title = null) {
        // Set default title based on type if none provided
        const defaultTitles = {
            info: window.i18n.t('common.info'),
            success: window.i18n.t('common.success'),
            error: window.i18n.t('common.error')
        };
        const notificationTitle = title || defaultTitles[type] || window.i18n.t('common.info');
        const notification = document.createElement('div');

        const baseClasses = 'fixed top-20 left-1/2 -translate-x-1/2 px-6 py-4 shadow-lg border-2 z-[1000] min-w-[320px] max-w-md cursor-pointer';

        if (type === 'success') {
            notification.className = `${baseClasses} bg-success tag-text`;
            notification.style.borderColor = 'var(--success-hover)';
        } else if (type === 'error') {
            notification.className = `${baseClasses} bg-danger tag-text`;
            notification.style.borderColor = 'var(--danger-hover)';
        } else {
            notification.className = `${baseClasses} surface text`;
            notification.style.borderColor = 'var(--primary-hover)';
        }

        // Create title element
        const titleEl = document.createElement('div');
        titleEl.className = 'font-semibold text-base mb-1';
        titleEl.textContent = notificationTitle;

        // Create message element
        const messageEl = document.createElement('div');
        messageEl.className = 'text-sm opacity-90';
        messageEl.textContent = message;

        notification.appendChild(titleEl);
        notification.appendChild(messageEl);

        notification.style.animation = 'slideIn 0.3s ease-out';

        const dismiss = () => {
            if (notification.classList.contains('removing')) return;
            notification.classList.add('removing');

            notification.style.animation = 'slideOut 0.3s ease-out forwards';
            setTimeout(() => {
                if (notification.parentNode) notification.remove();
            }, 300);
        };

        // Click to dismiss
        notification.addEventListener('click', dismiss);

        document.body.appendChild(notification);

        // Remove after 5 seconds
        setTimeout(dismiss, 5000);
    }

    translateError(error) {
        if (typeof error === 'string') return error;
        if (error.key) return window.i18n.t(error.key, error);
        return JSON.stringify(error);
    }

    setRatingFilter(ratings) {
        document.querySelectorAll('.rating-filter-label').forEach(label => {
            label.classList.remove('checked');
        });

        const ratingList = Array.isArray(ratings) ? ratings : (ratings ? ratings.split(',').map(r => r.trim()) : []);
        ratingList.forEach(rating => {
            document.querySelectorAll(`input[name="rating"][value="${rating}"]`).forEach(input => {
                input.checked = true;
                const label = input.nextElementSibling;
                if (label) label.classList.add('checked');
            });
        });
    }

    performSearch() {
        const searchInput = document.getElementById('search-input');
        const searchInputMobile = document.getElementById('search-input-mobile');

        // Get query from whichever input has a value (prioritize desktop, then mobile)
        const rawQuery = (searchInput && searchInput.value.trim()) ||
            (searchInputMobile && searchInputMobile.value.trim()) ||
            '';

        const query = canonicalizeQuery(rawQuery);
        if (searchInput) searchInput.value = query;
        if (searchInputMobile) searchInputMobile.value = query;

        if (query) {
            window.location.href = `/?q=${encodeURIComponent(query)}`;
        } else {
            // If no query, just go to home
            window.location.href = '/';
        }
    }

    async performRandomSearch() {
        const sidebarMode = document.body.dataset.sidebarMode || window.SIDEBAR_FILTER_MODE || 'rating';
        let rating = '';

        if (sidebarMode === 'rating' || sidebarMode === 'both') {
            const checkedRatings = Array.from(document.querySelectorAll('input[name="rating"]:checked')).map(i => i.value);
            if (checkedRatings.length > 0) {
                rating = Array.from(new Set(checkedRatings)).join(',');
            } else {
                rating = localStorage.getItem('selectedRating') || 'safe';
            }
        }

        let customFilters = [];
        if (sidebarMode === 'custom' || sidebarMode === 'both') {
            const rawCustomFilter = localStorage.getItem('selectedCustomFilter') || '';
            try {
                const parsed = JSON.parse(rawCustomFilter);
                if (Array.isArray(parsed)) customFilters = parsed;
                else if (typeof parsed === 'string' && parsed) customFilters = [parsed];
            } catch {
                if (rawCustomFilter) customFilters = [rawCustomFilter];
            }
        }

        try {
            const params = new URLSearchParams();
            if (rating) {
                params.set('rating', rating);
            }
            customFilters.forEach(cf => {
                if (cf) params.append('custom_filter', cf);
            });

            const queryStr = params.toString();
            const url = `/api/search/random${queryStr ? '?' + queryStr : ''}`;
            const response = await this.apiCall(url);

            if (response && response.id) {
                window.location.href = `/media/${response.id}`;
            } else {
                this.showNotification(window.i18n.t('gallery.no_results_found'), 'info');
            }
        } catch (error) {
            console.error('Random search error:', error);
            this.showNotification(window.i18n.t('gallery.errors.loading_random_media'), 'error');
        }
    }

    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    setCookie(name, value, days) {
        const expires = new Date();
        expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);
        document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/;SameSite=Lax`;
    }

    async apiCall(endpoint, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json'
            }
        };

        const response = await fetch(endpoint, { ...defaultOptions, ...options });

        if (!response.ok) {
            const error = await response.json();
            let errorMessage = error.detail || 'API call failed';

            // Check if error detail is an i18n key (starts with error_ or exists in notifications.admin)
            if (typeof errorMessage === 'string' && (errorMessage.startsWith('error_') || errorMessage.includes('.'))) {
                const translated = window.i18n.t(`notifications.admin.${errorMessage}`);
                if (translated !== `notifications.admin.${errorMessage}`) {
                    errorMessage = translated;
                }
            }

            throw new Error(errorMessage);
        }

        return response.json();
    }

    async showSearchSyntaxGuide() {
        const lang = window.CURRENT_LANGUAGE || 'en';
        if (!this.cachedSearchGuideHtml) {
            this.cachedSearchGuideHtml = {};
        }

        if (!this.cachedSearchGuideHtml[lang]) {
            try {
                const response = await fetch(`/api/search/syntax-guide?lang=${encodeURIComponent(lang)}`);
                if (response.ok) {
                    const data = await response.json();
                    if (data && data.html) {
                        this.cachedSearchGuideHtml[lang] = data.html;
                    }
                }
            } catch (error) {
                console.error('Failed to load search syntax guide:', error);
            }
        }

        const html = this.cachedSearchGuideHtml[lang] || '';
        const content = `<div class="text-left space-y-4 max-h-[60vh] overflow-y-auto custom-scrollbar">${html}</div>`;

        if (!this.searchGuideModal) {
            this.searchGuideModal = new ModalHelper({
                id: 'search-syntax-modal',
                type: 'info',
                maxWidth: 'max-w-2xl',
                title: window.i18n.t('common.search_syntax_guide'),
                message: content,
                showIcon: false,
                confirmText: window.i18n.t('common.got_it'),
                cancelText: window.i18n.t('common.keybindings'),
                confirmId: 'search-guide-confirm',
                cancelId: 'search-guide-keybindings'
            });

            this.setupSearchGuideKeybindingsBtn();
        } else {
            this.searchGuideModal.updateContent({
                message: content
            });
            this.setupSearchGuideKeybindingsBtn();
        }
        this.searchGuideModal.show();
    }

    setupSearchGuideKeybindingsBtn() {
        const keybindingsBtn = document.getElementById('search-guide-keybindings');
        if (keybindingsBtn) {
            keybindingsBtn.onclick = (e) => {
                e.preventDefault();
                if (this.searchGuideModal) {
                    this.searchGuideModal.hide();
                }
                this.showKeybindingsGuide();
            };
        }
    }

    showKeybindingsGuide() {
        const bindings = (window.keybindings && window.keybindings.bindings) || {};
        const content = this.getKeybindingsContent(bindings);

        if (!this.keybindingsModal) {
            this.keybindingsModal = new ModalHelper({
                id: 'keybindings-guide-modal',
                type: 'info',
                title: window.i18n.t('admin.keybindings.title'),
                message: content,
                showIcon: false,
                confirmText: window.i18n.t('common.got_it'),
                cancelText: '',
                confirmId: 'keybindings-guide-confirm',
                onConfirm: () => {
                    this.showSearchSyntaxGuide();
                }
            });
        } else {
            this.keybindingsModal.updateContent({
                message: content
            });
        }
        this.keybindingsModal.show();

        if (window.keybindings && typeof window.keybindings.refresh === 'function') {
            window.keybindings.refresh().catch(() => { });
        }
    }

    getKeybindingsContent(bindings = {}) {
        const groups = [
            {
                context: 'gallery_nav',
                titleKey: 'admin.keybindings.context_gallery_nav',
                actions: [
                    { id: 'gallery_nav_up', labelKey: 'admin.keybindings.actions.gallery_nav_up', default: { code: 'ArrowUp', key: 'ArrowUp' } },
                    { id: 'gallery_nav_down', labelKey: 'admin.keybindings.actions.gallery_nav_down', default: { code: 'ArrowDown', key: 'ArrowDown' } },
                    { id: 'gallery_nav_left', labelKey: 'admin.keybindings.actions.gallery_nav_left', default: { code: 'ArrowLeft', key: 'ArrowLeft' } },
                    { id: 'gallery_nav_right', labelKey: 'admin.keybindings.actions.gallery_nav_right', default: { code: 'ArrowRight', key: 'ArrowRight' } }
                ]
            },
            {
                context: 'media_viewer',
                titleKey: 'admin.keybindings.context_media_viewer',
                actions: [
                    { id: 'media_nav_prev', labelKey: 'admin.keybindings.actions.media_nav_prev', default: { code: 'ArrowLeft', key: 'ArrowLeft' } },
                    { id: 'media_nav_next', labelKey: 'admin.keybindings.actions.media_nav_next', default: { code: 'ArrowRight', key: 'ArrowRight' } },
                    { id: 'media_fullscreen', labelKey: 'admin.keybindings.actions.media_fullscreen', default: { code: 'KeyF', key: 'f' } }
                ]
            },
            {
                context: 'fullscreen_viewer',
                titleKey: 'admin.keybindings.context_fullscreen_viewer',
                actions: [
                    { id: 'fullscreen_zoom_in', labelKey: 'admin.keybindings.actions.fullscreen_zoom_in', default: { code: 'KeyG', key: 'g' } },
                    { id: 'fullscreen_zoom_out', labelKey: 'admin.keybindings.actions.fullscreen_zoom_out', default: { code: 'KeyH', key: 'h' } },
                    { id: 'fullscreen_move_up', labelKey: 'admin.keybindings.actions.fullscreen_move_up', default: { code: 'ArrowUp', key: 'ArrowUp' } },
                    { id: 'fullscreen_move_down', labelKey: 'admin.keybindings.actions.fullscreen_move_down', default: { code: 'ArrowDown', key: 'ArrowDown' } },
                    { id: 'fullscreen_move_left', labelKey: 'admin.keybindings.actions.fullscreen_move_left', default: { code: 'ArrowLeft', key: 'ArrowLeft' } },
                    { id: 'fullscreen_move_right', labelKey: 'admin.keybindings.actions.fullscreen_move_right', default: { code: 'ArrowRight', key: 'ArrowRight' } }
                ]
            },
            {
                context: 'tag_autocomplete',
                titleKey: 'admin.keybindings.context_tag_autocomplete',
                actions: [
                    { id: 'tag_suggestion_prev', labelKey: 'admin.keybindings.actions.tag_suggestion_prev', default: { code: 'ArrowUp', key: 'ArrowUp' } },
                    { id: 'tag_suggestion_next', labelKey: 'admin.keybindings.actions.tag_suggestion_next', default: { code: 'ArrowDown', key: 'ArrowDown' } }
                ]
            }
        ];

        return `
            <div class="text-left space-y-4 max-h-[60vh] overflow-y-auto pr-2 custom-scrollbar">
                ${groups.map(group => `
                    <div class="bg p-2 border-2 border-info">
                        <h3 class="font-bold text-lg mb-2 text-info">
                            ${this.escapeHtml(window.i18n.t(group.titleKey))}
                        </h3>
                        <div class="space-y-1.5">
                            ${group.actions.map(action => {
            const binding = bindings[action.id] || action.default;
            const chipText = binding ? (binding.key || binding.code || '?') : '?';
            const isSingleChar = chipText.length === 1;
            const label = window.i18n.t(action.labelKey);
            return `
                                    <div class="keybinding-row flex items-center justify-between gap-3 px-2 py-1.5 border surface">
                                        <span class="text-xs font-bold text">${this.escapeHtml(label)}</span>
                                        <div class="flex items-center gap-2">
                                            <kbd class="keybinding-chip bg px-1.5 py-0.5 text-xs border font-mono ${isSingleChar ? 'uppercase' : ''}">${this.escapeHtml(chipText)}</kbd>
                                        </div>
                                    </div>
                                `;
        }).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = String(text ?? '');
        return div.innerHTML;
    }
}

// Explicit Thumbnail Blur Helpers
window.shouldBlurExplicit = function () {
    return document.body.dataset.blurExplicit === 'true';
};

window.wrapBlurThumbnail = function (img, media, item) {
    if (!media || media.rating !== 'explicit' || !window.shouldBlurExplicit()) {
        return img;
    }
    const blurWrapper = document.createElement('div');
    blurWrapper.classList.add('blur-wrapper');
    if (media.width && media.height) {
        blurWrapper.style.aspectRatio = `${media.width} / ${media.height}`;
    } else {
        img.addEventListener('load', () => {
            if (img.naturalWidth && img.naturalHeight) {
                blurWrapper.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
            }
        }, { once: true });
    }
    blurWrapper.appendChild(img);
    if (item) {
        item.classList.add('blur-content');
    }
    return blurWrapper;
};

// GIF Gallery Item Hover Preview Helpers
const GIF_BLOB_CACHE_LIMIT = 6;
const gifBlobCache = new Map();

function getCachedGifBlob(mediaId) {
    if (!gifBlobCache.has(mediaId)) return null;
    const entry = gifBlobCache.get(mediaId);
    gifBlobCache.delete(mediaId);
    gifBlobCache.set(mediaId, entry);
    return entry.blob;
}

function setCachedGifBlob(mediaId, blob) {
    if (gifBlobCache.has(mediaId)) {
        const entry = gifBlobCache.get(mediaId);
        entry.blob = blob;
        gifBlobCache.delete(mediaId);
        gifBlobCache.set(mediaId, entry);
        return entry;
    }
    while (gifBlobCache.size >= GIF_BLOB_CACHE_LIMIT) {
        const oldestKey = gifBlobCache.keys().next().value;
        const oldest = gifBlobCache.get(oldestKey);
        if (oldest && oldest.urls) {
            oldest.urls.forEach(url => URL.revokeObjectURL(url));
        }
        gifBlobCache.delete(oldestKey);
    }
    const entry = { blob, urls: new Set() };
    gifBlobCache.set(mediaId, entry);
    return entry;
}

function createGifObjectUrl(mediaId, blob) {
    let entry = gifBlobCache.get(mediaId);
    if (!entry) {
        entry = setCachedGifBlob(mediaId, blob);
    }
    const url = URL.createObjectURL(blob);
    entry.urls.add(url);
    return url;
}

function revokeGifObjectUrl(mediaId, url) {
    if (!url) return;
    URL.revokeObjectURL(url);
    const entry = gifBlobCache.get(mediaId);
    if (entry && entry.urls) {
        entry.urls.delete(url);
    }
}

function clearAllGifBlobCache() {
    gifBlobCache.forEach(entry => {
        if (entry.urls) {
            entry.urls.forEach(url => URL.revokeObjectURL(url));
        }
    });
    gifBlobCache.clear();
}

window.setupGifPreview = function (item, media, targetContainer, thumbnailImg, trackerSet = null) {
    if (!item || !media || media.file_type !== 'gif' || !item.classList.contains('gif')) {
        return;
    }
    if (window.matchMedia && !window.matchMedia('(hover: hover)').matches) {
        return;
    }

    const fileUrl = `/api/media/${media.id}/file${media.hash ? '?v=' + media.hash : ''}`;
    const thumb = thumbnailImg || item.querySelector('a img:not(.gif-preview)');

    let gifImg = null;
    let hoverTimer = null;
    let currentToken = 0;
    let currentBlobUrl = null;
    let abortController = null;

    const stopPlay = () => {
        clearTimeout(hoverTimer);
        ++currentToken;

        if (abortController) {
            abortController.abort();
            abortController = null;
        }

        if (thumb) {
            thumb.style.display = '';
        }

        if (gifImg) {
            gifImg.onload = null;
            gifImg.onerror = null;
            gifImg.style.display = 'none';
            gifImg.removeAttribute('src');
        }

        if (currentBlobUrl) {
            revokeGifObjectUrl(media.id, currentBlobUrl);
            currentBlobUrl = null;
        }
    };

    const activateGif = (token) => {
        if (token !== currentToken || !item.isConnected || !gifImg) return;
        gifImg.style.display = 'block';
        if (thumb) {
            thumb.style.display = 'none';
        }
    };

    const loadAndActivate = (url, token) => {
        if (!gifImg) return;
        gifImg.src = url;
        if (gifImg.decode) {
            gifImg.decode().then(() => {
                activateGif(token);
            }).catch(() => {
                if (token === currentToken) {
                    if (gifImg) gifImg.style.display = 'none';
                    if (thumb) thumb.style.display = '';
                }
            });
        } else {
            gifImg.onload = () => activateGif(token);
            gifImg.onerror = () => {
                if (token === currentToken && thumb) {
                    thumb.style.display = '';
                }
            };
        }
    };

    const executePlay = () => {
        const token = ++currentToken;

        if (!gifImg) {
            gifImg = document.createElement('img');
            gifImg.className = 'gif-preview loaded';
            gifImg.alt = thumb?.alt || media.filename || '';
            gifImg.draggable = false;
            gifImg.style.display = 'none';
            targetContainer.appendChild(gifImg);
            item._gifImg = gifImg;

            if (trackerSet && typeof trackerSet.add === 'function') {
                trackerSet.add(item);
            }
        }

        const cachedBlob = getCachedGifBlob(media.id);
        if (cachedBlob) {
            if (currentBlobUrl) {
                revokeGifObjectUrl(media.id, currentBlobUrl);
                currentBlobUrl = null;
            }
            currentBlobUrl = createGifObjectUrl(media.id, cachedBlob);
            loadAndActivate(currentBlobUrl, token);
            return;
        }

        abortController = new AbortController();

        fetch(fileUrl, { signal: abortController.signal })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP error ${res.status}`);
                return res.blob();
            })
            .then(blob => {
                if (token !== currentToken) return;
                setCachedGifBlob(media.id, blob);
                if (currentBlobUrl) {
                    revokeGifObjectUrl(media.id, currentBlobUrl);
                    currentBlobUrl = null;
                }
                currentBlobUrl = createGifObjectUrl(media.id, blob);
                loadAndActivate(currentBlobUrl, token);
            })
            .catch(err => {
                if (err.name === 'AbortError') return;
                if (token === currentToken && thumb) {
                    thumb.style.display = '';
                }
            });
    };

    const startPlay = () => {
        if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        if (navigator.connection && navigator.connection.saveData) return;
        if (document.body.classList.contains('reorder-active-mode') ||
            document.body.classList.contains('is-dragging') ||
            item.closest('.selection-mode')) {
            return;
        }

        clearTimeout(hoverTimer);
        hoverTimer = setTimeout(executePlay, 150);
    };

    item.addEventListener('mouseenter', startPlay);
    item.addEventListener('mouseleave', stopPlay);
    item.addEventListener('focusin', startPlay);
    item.addEventListener('focusout', stopPlay);

    item._unloadGif = () => {
        clearTimeout(hoverTimer);
        ++currentToken;

        if (abortController) {
            abortController.abort();
            abortController = null;
        }

        if (currentBlobUrl) {
            revokeGifObjectUrl(media.id, currentBlobUrl);
            currentBlobUrl = null;
        }

        if (thumb) {
            thumb.style.display = '';
        }
        if (gifImg) {
            gifImg.onload = null;
            gifImg.onerror = null;
            gifImg.removeAttribute('src');
            gifImg.remove();
            gifImg = null;
            delete item._gifImg;
        }
    };
};

window.unloadAllGifs = function (trackerSet = null, container = null) {
    if (trackerSet && typeof trackerSet.forEach === 'function') {
        trackerSet.forEach(item => {
            if (item && typeof item._unloadGif === 'function') {
                item._unloadGif();
            }
        });
        trackerSet.clear();
    }

    clearAllGifBlobCache();

    const root = container || document;
    const orphanGifs = root.querySelectorAll('.gif-preview');
    orphanGifs.forEach(gif => {
        gif.onload = null;
        gif.onerror = null;
        gif.removeAttribute('src');
        gif.remove();
    });

    root.querySelectorAll('.gallery-item img:not(.gif-preview)').forEach(img => {
        if (img.style.display === 'none') {
            img.style.display = '';
        }
    });
};

// Initialize app
const app = new Blombooru();
