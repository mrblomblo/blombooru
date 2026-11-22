// Core functionality
class Blombooru {
    constructor() {
        this.autoScroll = window.autoScroll;
        this.isAdminMode = window.getCookie('admin_mode') === 'true';
        this.isAuthenticated = !!window.getCookie('admin_token');
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
        const savedRating = localStorage.getItem('selectedRating') || window.getCookie('rating_filter');
        if (savedRating) {
            this.setRatingFilter(savedRating);
            localStorage.setItem('selectedRating', savedRating);
            window.setCookie('rating_filter', savedRating, 365);
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
                this.toggleAdminMode();
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

        // Search inputs sync
        const searchInput = document.getElementById('search-input');
        const searchInputMobile = document.getElementById('search-input-mobile');
        if (searchInput && searchInputMobile) {
            searchInput.addEventListener('input', () => {
                searchInputMobile.value = searchInput.value;
            });
            searchInputMobile.addEventListener('input', () => {
                searchInput.value = searchInputMobile.value;
            });
        }

        // Search form (desktop)
        const searchForm = document.getElementById('search-form');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.performSearch(searchInput);
            });
        }

        // Search form (mobile)
        const searchFormMobile = document.getElementById('search-form-mobile');
        if (searchFormMobile) {
            searchFormMobile.addEventListener('submit', (e) => {
                e.preventDefault();
                this.performSearch(searchInputMobile);
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

        notification.setAttribute('role', type === 'error' ? 'alert' : 'status');
        notification.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');

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

    performSearch(sourceInput = null) {
        const searchInput = document.getElementById('search-input');
        const searchInputMobile = document.getElementById('search-input-mobile');

        let targetInput = sourceInput;
        if (!targetInput) {
            if (document.activeElement === searchInputMobile) {
                targetInput = searchInputMobile;
            } else if (document.activeElement === searchInput) {
                targetInput = searchInput;
            } else if (searchInputMobile && (searchInputMobile.checkVisibility ? searchInputMobile.checkVisibility() : searchInputMobile.offsetParent !== null)) {
                targetInput = searchInputMobile;
            } else {
                targetInput = searchInput || searchInputMobile;
            }
        }

        const rawQuery = (targetInput && targetInput.value) ? targetInput.value.trim() : '';

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
            this.showNotification(`${window.i18n.t('gallery.error_label')} ${error.message}`, 'error');
        }
    }

    async apiCall(endpoint, options = {}) {
        const headers = { ...options.headers };
        const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
        if (!isFormData && !headers['Content-Type'] && !headers['content-type']) {
            headers['Content-Type'] = 'application/json';
        }

        const fetchOptions = {
            ...options,
            headers
        };

        const response = await fetch(endpoint, fetchOptions);

        if (!response.ok) {
            if (response.status === 401 && window.location.pathname.startsWith('/admin')) {
                window.location.href = `/login?return=${encodeURIComponent(window.location.pathname + window.location.search)}`;
                // Never resolve so callers do not run with undefined while the page unloads
                return new Promise(() => { });
            }

            let errorData = null;
            try {
                errorData = await response.json();
            } catch {
                // Non-JSON response
            }

            let errorMessage = (errorData && errorData.detail)
                ? (typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail))
                : `HTTP ${response.status}: ${response.statusText || 'API call failed'}`;

            // Check if error detail is an i18n key (starts with error_, exists in notifications.admin, or is a direct key)
            if (typeof errorMessage === 'string') {
                const adminTranslated = window.i18n.t(`notifications.admin.${errorMessage}`);
                if (adminTranslated !== `notifications.admin.${errorMessage}`) {
                    errorMessage = adminTranslated;
                } else {
                    const directTranslated = window.i18n.t(errorMessage);
                    if (directTranslated !== errorMessage) {
                        errorMessage = directTranslated;
                    }
                }
            }

            throw new Error(errorMessage);
        }

        if (response.status === 204 || response.headers.get('content-length') === '0') {
            return null;
        }

        const text = await response.text();
        if (!text) return null;
        try {
            return JSON.parse(text);
        } catch {
            throw new Error(`Invalid JSON response (HTTP ${response.status})`);
        }
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

    escapeHtml(text, options) {
        return escapeHtml(text, options);
    }

    escapeAttr(text, options) {
        return escapeAttr(text, options);
    }

    formatFileSize(bytes, options) {
        return formatFileSize(bytes, options);
    }

    formatBytes(bytes, options) {
        return formatBytes(bytes, options);
    }
}

// Initialize app
const app = new Blombooru();
window.app = app;
