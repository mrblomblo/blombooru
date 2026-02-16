class I18n {
    constructor() {
        this.translations = {};
        this.currentLang = window.CURRENT_LANGUAGE || 'en';
        this.loaded = false;
        this.loadPromise = null;
    }

    async load(lang = null) {
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
     * @param {string} key - Dot-notation key (e.g., 'nav.albums')
     * @param {Object} params - Interpolation parameters (e.g., {count: 5})
     * @returns {string} Translated string or the key itself if not found
     */
    t(key, params = {}) {
        const keys = key.split('.');
        let value = this.translations;

        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                return key;
            }
        }

        if (typeof value !== 'string') {
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

// Core functionality
class Blombooru {
    constructor() {
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

        // Load settings from cookie
        const savedRating = this.getCookie('rating_filter');
        if (savedRating) {
            this.setRatingFilter(savedRating);
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

        // Rating filter
        const ratingInputs = document.querySelectorAll('input[name="rating"]');
        ratingInputs.forEach(input => {
            input.addEventListener('change', (e) => {
                this.setRatingFilter(e.target.value);
                this.setCookie('rating_filter', e.target.value, 365);
            });
        });

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

    handleAdminToggle() {
        // If not authenticated, go to admin panel
        if (!this.isAuthenticated) {
            window.location.href = '/admin';
            return;
        }

        // If on admin panel page, don't toggle - it's auto-enabled
        if (window.location.pathname === '/admin') {
            return;
        }

        // Toggle admin mode
        this.toggleAdminMode();
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

    setRatingFilter(rating) {
        document.querySelectorAll('.rating-filter-label').forEach(label => {
            label.classList.remove('checked');
        });

        document.querySelectorAll(`input[name="rating"][value="${rating}"]`).forEach(input => {
            input.checked = true;
            input.nextElementSibling.classList.add('checked');
        });
    }

    performSearch() {
        const searchInput = document.getElementById('search-input');
        const searchInputMobile = document.getElementById('search-input-mobile');

        // Get query from whichever input has a value (prioritize desktop, then mobile)
        const query = (searchInput && searchInput.value.trim()) ||
            (searchInputMobile && searchInputMobile.value.trim()) ||
            '';

        if (query) {
            window.location.href = `/?q=${encodeURIComponent(query)}`;
        } else {
            // If no query, just go to home
            window.location.href = '/';
        }
    }

    async performRandomSearch() {
        let rating = null;
        if (window.SIDEBAR_FILTER_MODE === 'rating') {
            const ratingInput = document.querySelector('input[name="rating"]:checked');
            rating = ratingInput ? ratingInput.value : null;
        }

        try {
            let url = '/api/search/random?q=';
            if (rating) {
                url += `&rating=${rating}`;
            }

            const response = await this.apiCall(url);

            if (response && response.id) {
                window.location.href = `/media/${response.id}`;
            } else {
                this.showNotification(window.i18n.t('gallery.no_results_found'), 'info');
            }
        } catch (error) {
            console.error('Random search error:', error);
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

    showSearchSyntaxGuide() {
        if (!this.searchGuideModal) {
            this.searchGuideModal = new ModalHelper({
                id: 'search-syntax-modal',
                type: 'info',
                title: window.i18n.t('modal.search_syntax.title'),
                message: this.getSearchSyntaxContent(),
                showIcon: false,
                confirmText: window.i18n.t('modal.search_syntax.confirm'),
                cancelText: '',
                confirmId: 'search-guide-confirm'
            });
        }
        this.searchGuideModal.show();
    }

    getSearchSyntaxContent() {
        return `
            <div class="text-left space-y-4 max-h-[60vh] overflow-y-auto pr-2 custom-scrollbar">
                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">${window.i18n.t('search.basic_tags')}</h3>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">tag1 tag2</code>: ${window.i18n.t('search.basic_desc_both')}</li>
                        <li><code class="surface">-tag1</code>: ${window.i18n.t('search.basic_desc_exclude')}</li>
                        <li><code class="surface">tag*</code>: ${window.i18n.t('search.basic_desc_wildcard')}</li>
                        <li><code class="surface">?tag</code>: ${window.i18n.t('search.basic_desc_fuzzy')}</li>
                    </ul>
                </div>

                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">${window.i18n.t('search.ranges')}</h3>
                    <p class="mb-2 text-xs">${window.i18n.t('search.ranges_operators')}: <code>:</code>, <code>..</code>, <code>&gt;=</code>, <code>&gt;</code>, <code>&lt;=</code>, <code>&lt;</code></p>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">id:100</code>: ${window.i18n.t('search.ranges_exact')}</li>
                        <li><code class="surface">id:100..200</code>: ${window.i18n.t('search.ranges_between')}</li>
                        <li><code class="surface">id:&gt;=100</code>: ${window.i18n.t('search.ranges_gte')}</li>
                        <li><code class="surface">id:1,2,3</code>: ${window.i18n.t('search.ranges_in_list')}</li>
                    </ul>
                    <p class="mt-2 text-xs text-secondary">${window.i18n.t('search.ranges_note')}</p>
                </div>

                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">${window.i18n.t('search.meta_qualifiers')}</h3>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">width</code>, <code class="surface">height</code>: ${window.i18n.t('search.meta_dimensions')}</li>
                        <li><code class="surface">filesize</code>: ${window.i18n.t('search.meta_filesize')}</li>
                        <li><code class="surface">date</code>, <code class="surface">age</code>: ${window.i18n.t('search.meta_date')}</li>
                        <li><code class="surface">rating</code>: ${window.i18n.t('search.meta_rating')}</li>
                        <li><code class="surface">source</code>: ${window.i18n.t('search.meta_source')}</li>
                        <li><code class="surface">filetype</code>: ${window.i18n.t('search.meta_filetype')}</li>
                        <li><code class="surface">tagcount</code>, <code class="surface">gentags</code>...: ${window.i18n.t('search.meta_tagcount')}</li>
                    </ul>
                </div>

                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">${window.i18n.t('search.sorting')}</h3>
                    <p class="mb-2 text-sm">${window.i18n.t('search.sorting_desc').replace('order:value', '<code>order:value</code>')}</p>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">id</code> / <code class="surface">id_desc</code>: ${window.i18n.t('search.sorting_newest')}</li>
                        <li><code class="surface">id_asc</code>: ${window.i18n.t('search.sorting_oldest')}</li>
                        <li><code class="surface">filesize</code>: ${window.i18n.t('search.sorting_filesize')}</li>
                        <li><code class="surface">landscape</code> / <code class="surface">portrait</code>: ${window.i18n.t('search.sorting_aspect')}</li>
                    </ul>
                </div>

                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">${window.i18n.t('search.examples')}</h3>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">cat source:none rating:s</code>: ${window.i18n.t('search.example_cat')}</li>
                        <li><code class="surface">landscape filetype:mp4 filesize:&gt;5mb</code>: ${window.i18n.t('search.example_landscape')}</li>
                        <li><code class="surface">id:1..100 order:id_asc</code>: ${window.i18n.t('search.example_id')}</li>
                        <li><code class="surface">?girl? *_eyes -dog</code>: ${window.i18n.t('search.example_fuzzy')}</li>
                        <li><code class="surface">tagcount:&gt;20 arttags:0</code>: ${window.i18n.t('search.example_tagcount')}</li>
                    </ul>
                </div>
            </div>
        `;
    }
}

// Initialize app
const app = new Blombooru();
