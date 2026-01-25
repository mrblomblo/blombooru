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

    init() {
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

        // Search form
        const searchForm = document.getElementById('search-form');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => {
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
                    newMode ? 'Admin mode enabled' : 'Admin mode disabled',
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
            info: 'Info',
            success: 'Success',
            error: 'Error'
        };
        const notificationTitle = title || defaultTitles[type] || 'Info';
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
        const query = searchInput.value;

        if (query) {
            window.location.href = `/?q=${encodeURIComponent(query)}`;
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
            throw new Error(error.detail || 'API call failed');
        }

        return response.json();
    }

    showSearchSyntaxGuide() {
        if (!this.searchGuideModal) {
            this.searchGuideModal = new ModalHelper({
                id: 'search-syntax-modal',
                type: 'info',
                title: 'Search Syntax Guide',
                message: this.getSearchSyntaxContent(),
                showIcon: false,
                confirmText: 'Got it',
                cancelText: 'Close',
                cancelId: 'search-guide-close',
                confirmId: 'search-guide-confirm'
            });
        }
        this.searchGuideModal.show();
    }

    getSearchSyntaxContent() {
        return `
            <div class="text-left space-y-4 max-h-[60vh] overflow-y-auto pr-2 custom-scrollbar">
                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">Basic Tags</h3>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">tag1 tag2</code>: Find media with both tags</li>
                        <li><code class="surface">-tag1</code>: Exclude media with tag</li>
                        <li><code class="surface">tag*</code>: Wildcard search (e.g., <code class="surface">tag_name</code>)</li>
                        <li><code class="surface">?tag</code>: Fuzzy search (one or zero chars before)</li>
                    </ul>
                </div>

                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">Ranges</h3>
                    <p class="mb-2 text-xs">Operators: <code>:</code>, <code>..</code>, <code>&gt;=</code>, <code>&gt;</code>, <code>&lt;=</code>, <code>&lt;</code></p>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">id:100</code>: Exact match</li>
                        <li><code class="surface">id:100..200</code>: Between inclusive</li>
                        <li><code class="surface">id:&gt;=100</code>: Greater than or equal</li>
                        <li><code class="surface">id:1,2,3</code>: In list</li>
                    </ul>
                    <p class="mt-2 text-xs text-secondary">Note: Ranges can also be used with most meta qualifiers.</p>
                </div>

                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">Meta Qualifiers</h3>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">width</code>, <code class="surface">height</code>: Image dimensions (pixels)</li>
                        <li><code class="surface">filesize</code>: File size (kb, mb, gb)</li>
                        <li><code class="surface">date</code>, <code class="surface">age</code>: Upload date or relative age</li>
                        <li><code class="surface">rating</code>: <code class="surface">s</code> (safe), <code class="surface">q</code> (questionable), <code class="surface">e</code> (explicit)</li>
                        <li><code class="surface">source</code>: Source URL or <code class="surface">none</code></li>
                        <li><code class="surface">filetype</code>: Extension (png, gif, etc)</li>
                        <li><code class="surface">tagcount</code>, <code class="surface">gentags</code>...: Number of tags</li>
                    </ul>
                </div>

                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">Sorting</h3>
                    <p class="mb-2 text-sm">Use <code>order:value</code> (e.g., <code>order:id_desc</code>)</p>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">id</code> / <code class="surface">id_desc</code>: Newest first (default)</li>
                        <li><code class="surface">id_asc</code>: Oldest first</li>
                        <li><code class="surface">filesize</code>: Largest files first</li>
                        <li><code class="surface">landscape</code> / <code class="surface">portrait</code>: Aspect ratio</li>
                    </ul>
                </div>

                <div class="bg p-2 border-2 border-info">
                    <h3 class="font-bold text-lg mb-2 text-info">Example Searches</h3>
                    <ul class="list-disc pl-5 space-y-1 text-sm">
                        <li><code class="surface">cat source:none rating:s</code>: Safe cat images without a source</li>
                        <li><code class="surface">landscape filetype:mp4 filesize:&gt;5mb</code>: High-quality landscape videos</li>
                        <li><code class="surface">id:1..100 order:id_asc</code>: First 100 uploads, oldest first</li>
                        <li><code class="surface">?girl? *_eyes -dog</code>: Searching for one or more girls with any color eyes, no dogs</li>
                        <li><code class="surface">tagcount:&gt;20 arttags:0</code>: Posts with many tags but no artist info</li>
                    </ul>
                </div>
            </div>
        `;
    }
}

// Initialize app
const app = new Blombooru();
