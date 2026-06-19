class AdminPanel {
    constructor() {
        this.aliasCache = new Set();
        this.tagInputHelper = new TagInputHelper();
        this.validationTimeout = null;

        // Modules
        this.system = new AdminSystem(this);
        this.content = new AdminContent(this);
        this.account = new AdminAccount(this);

        this.themeSelect = null;
        this.languageSelect = null;
        this.statsModule = null;
        window.adminPanel = this;
        this.init();
    }

    async init() {
        await this.checkAuth();

        this.setupTagAutocomplete();
        this.setupEventListeners();
        this.system.loadSettings();
        this.content.loadAITaggerSettings();
        this.content.setupTagManagement();
        this.content.setupAlbumManagement();
        this.content.loadTagStats();
        this.content.loadMediaStats();
        this.content.loadAlbumStats();
        this.system.setupCustomSelects();
        this.system.loadThemes();
        this.system.loadLanguages();
        this.system.loadCustomThemes();
        this.system.setupApiKeyManagement();
        this.system.setupSystemUpdate();

        this.setupStats();
        this.setupTabs();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    setupTagAutocomplete() {
        const tagsSearch = document.getElementById('tag-search-input');
        if (tagsSearch && typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(tagsSearch, {
                multipleValues: true,
                appendSpace: false
            });
        }
    }

    async checkAuth() {
        try {
            const response = await fetch('/api/admin/settings');
            if (response.ok) {
                document.getElementById('settings-section').style.display = 'block';

                app.updateAuthStatus(true);

                return true;
            } else {
                window.location.href = '/login?return=/admin';
                return false;
            }
        } catch (error) {
            console.error('Error checking auth:', error);
            window.location.href = '/login?return=/admin';
            return false;
        }
    }

    setupEventListeners() {
        // Settings form
        const settingsForm = document.getElementById('settings-form');
        if (settingsForm) {
            settingsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.system.saveSettings();
            });
        }

        // AI Tagger settings form
        const aiTaggerForm = document.getElementById('ai-tagger-settings-form');
        if (aiTaggerForm) {
            aiTaggerForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.content.saveAITaggerSettings();
            });
        }

        // Scan media button
        const scanBtn = document.getElementById('scan-media-btn');
        if (scanBtn) {
            scanBtn.addEventListener('click', () => this.content.scanMedia());
        }

        // Thumbnail management buttons
        const generateMissingBtn = document.getElementById('generate-missing-thumbnails-btn');
        if (generateMissingBtn) {
            generateMissingBtn.addEventListener('click', () => this.content.generateMissingThumbnails());
        }

        const regenerateAllBtn = document.getElementById('regenerate-all-thumbnails-btn');
        if (regenerateAllBtn) {
            regenerateAllBtn.addEventListener('click', () => this.content.regenerateAllThumbnails());
        }

        // Add tags form
        const addTagsForm = document.getElementById('add-tags-form');
        if (addTagsForm) {
            addTagsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.content.addNewTags();
            });
        }

        // Change password form
        const changePasswordForm = document.getElementById('change-admin-password-form');
        if (changePasswordForm) {
            changePasswordForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.account.changePassword();
            });
        }

        // Change username form
        const changeUsernameForm = document.getElementById('change-admin-username-form');
        if (changeUsernameForm) {
            changeUsernameForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.account.changeUsername();
            });
        }

        // Redis settings toggle
        const redisEnabled = document.getElementById('redis-enabled');
        if (redisEnabled) {
            redisEnabled.addEventListener('change', (e) => {
                const container = document.getElementById('redis-settings-container');
                if (container) container.style.display = e.target.checked ? 'block' : 'none';
            });
        }

        // Redis test button
        const testRedisBtn = document.getElementById('test-redis-btn');
        if (testRedisBtn) {
            testRedisBtn.addEventListener('click', () => this.system.testRedisConnection());
        }

        // Shared tags settings toggle
        const sharedTagsEnabled = document.getElementById('shared-tags-enabled');
        if (sharedTagsEnabled) {
            sharedTagsEnabled.addEventListener('change', (e) => {
                const container = document.getElementById('shared-tags-settings-container');
                if (container) container.style.display = e.target.checked ? 'block' : 'none';
            });
        }

        // Shared tags test button
        const testSharedTagsBtn = document.getElementById('test-shared-tags-btn');
        if (testSharedTagsBtn) {
            testSharedTagsBtn.addEventListener('click', () => this.system.testSharedTagsConnection());
        }

        // Shared tags sync button
        const syncSharedTagsBtn = document.getElementById('sync-shared-tags-btn');
        if (syncSharedTagsBtn) {
            syncSharedTagsBtn.addEventListener('click', () => this.system.syncSharedTags());
        }
    }

    setupTabs() {
        const tabButtons = document.querySelectorAll('.tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');

        if (tabButtons.length === 0) return;

        const switchTab = (tabId) => {
            tabButtons.forEach(btn => {
                if (btn.dataset.tab === tabId) {
                    btn.classList.add('text-primary', 'border-primary');
                    btn.classList.remove('border-transparent');
                } else {
                    btn.classList.remove('text-primary', 'border-primary');
                    btn.classList.add('border-transparent');
                }
            });

            tabContents.forEach(content => {
                if (content.id === `tab-${tabId}`) {
                    content.classList.remove('hidden');
                } else {
                    content.classList.add('hidden');
                }
            });

            if (tabId === 'stats' && this.statsModule && !this.statsModule.isInitialized) {
                this.statsModule.init();
            }

            localStorage.setItem('admin_active_tab', tabId);
        };

        tabButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                switchTab(btn.dataset.tab);
            });
        });

        // Initialize from URL parameters or local storage
        const urlParams = new URLSearchParams(window.location.search);
        const tabParam = urlParams.get('tab');
        const savedTab = localStorage.getItem('admin_active_tab');
        const defaultTab = 'content';
        let initialTab = defaultTab;

        if (tabParam && document.querySelector(`.tab-btn[data-tab="${tabParam}"]`)) {
            initialTab = tabParam;
            urlParams.delete('tab');
            const newSearch = urlParams.toString();
            const newUrl = window.location.pathname + (newSearch ? '?' + newSearch : '') + window.location.hash;
            window.history.replaceState({}, '', newUrl);
        } else if (savedTab && document.querySelector(`.tab-btn[data-tab="${savedTab}"]`)) {
            initialTab = savedTab;
        }

        switchTab(initialTab);

        // If stats tab is active after initialization, ensure it's loaded
        if (initialTab === 'stats' && this.statsModule) {
            setTimeout(() => {
                if (this.statsModule && !this.statsModule.isInitialized) {
                    this.statsModule.init();
                }
            }, 100);
        }

        // Handle scrolling to hash element if present
        if (window.location.hash) {
            setTimeout(() => {
                try {
                    const targetElement = document.getElementById(window.location.hash.substring(1));
                    if (targetElement) {
                        targetElement.scrollIntoView();
                    }
                } catch (e) {
                    console.error("Error scrolling to hash:", e);
                }
            }, 150);
        }
    }

    setupStats() {
        if (typeof AdminStats !== 'undefined') {
            this.statsModule = new AdminStats();
        }
    }

}

// Initialize admin panel
if (document.getElementById('admin-panel')) {
    const adminPanel = new AdminPanel();
}
