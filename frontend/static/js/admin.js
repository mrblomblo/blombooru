class AdminPanel {
    constructor() {
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadSettings();
        this.setupTagManagement();
        this.loadTagStats();
    }
    
    setupEventListeners() {
        // Settings form
        const settingsForm = document.getElementById('settings-form');
        if (settingsForm) {
            settingsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.saveSettings();
            });
        }
        
        // Scan media button
        const scanBtn = document.getElementById('scan-media-btn');
        if (scanBtn) {
            scanBtn.addEventListener('click', () => this.scanMedia());
        }
        
        // Login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.login();
            });
        }
    }
    
    async loadSettings() {
        try {
            const response = await fetch('/api/admin/settings');
            
            if (!response.ok) {
                console.log('Not authenticated or settings not available');
                return;
            }
            
            const settings = await response.json();
            
            // Populate form fields
            if (settings.app_name) {
                const appNameInput = document.getElementById('app-name');
                if (appNameInput) appNameInput.value = settings.app_name;
            }
            
            if (settings.default_rating_filter) {
                const ratingInput = document.querySelector(
                    `input[name="default-rating"][value="${settings.default_rating_filter}"]`
                );
                if (ratingInput) ratingInput.checked = true;
            }
            
        } catch (error) {
            console.error('Error loading settings:', error);
        }
    }
    
    async saveSettings() {
        const appName = document.getElementById('app-name').value;
        const defaultRating = document.querySelector('input[name="default-rating"]:checked')?.value;
        
        const settings = {
            app_name: appName,
            default_rating_filter: defaultRating,
        };
        
        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify(settings)
            });
            
            location.reload();
        } catch (error) {
            alert('Error saving settings: ' + error.message);
        }
    }
    
    async scanMedia() {
        const scanBtn = document.getElementById('scan-media-btn');
        scanBtn.disabled = true;
        scanBtn.textContent = 'Scanning...';
        
        try {
            const result = await app.apiCall('/api/admin/scan-media', {
                method: 'POST'
            });
            
            alert(`Scan complete!\nNew files: ${result.new_files}\n${result.files.join('\n')}`);
            
        } catch (error) {
            alert('Error scanning media: ' + error.message);
        } finally {
            scanBtn.disabled = false;
            scanBtn.textContent = 'Scan for New Media';
        }
    }
    
    async login() {
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const errorDiv = document.getElementById('login-error');
        const submitBtn = document.querySelector('#login-form button[type="submit"]');
        
        // Clear previous error
        errorDiv.style.display = 'none';
        submitBtn.disabled = true;
        submitBtn.textContent = 'Logging in...';
        
        try {
            const response = await fetch('/api/admin/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });
            
            if (response.ok) {
                console.log('Login successful, redirecting...');
                window.location.href = '/admin';
            } else {
                const error = await response.json();
                console.error('Login failed:', error);
                errorDiv.textContent = error.detail || 'Invalid username or password';
                errorDiv.style.display = 'block';
                submitBtn.disabled = false;
                submitBtn.textContent = 'Login';
            }
        } catch (error) {
            console.error('Login error:', error);
            errorDiv.textContent = 'Network error. Please try again.';
            errorDiv.style.display = 'block';
            submitBtn.disabled = false;
            submitBtn.textContent = 'Login';
        }
    }

    setupTagManagement() {
        // CSV upload
        const uploadArea = document.getElementById('csv-upload-area');
        const fileInput = document.getElementById('csv-file-input');
        
        uploadArea?.addEventListener('click', () => fileInput?.click());
        
        uploadArea?.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.style.backgroundColor = '#334155';
        });
        
        uploadArea?.addEventListener('dragleave', () => {
            uploadArea.style.backgroundColor = '';
        });
        
        uploadArea?.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.style.backgroundColor = '';
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.uploadCSV(files[0]);
            }
        });
        
        fileInput?.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.uploadCSV(e.target.files[0]);
            }
        });
        
        // Tag search
        const searchBtn = document.getElementById('tag-search-btn');
        const searchInput = document.getElementById('tag-search-input');
        
        searchBtn?.addEventListener('click', () => this.searchTags());
        searchInput?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.searchTags();
            }
        });
        
        // Clear tags
        const clearBtn = document.getElementById('clear-tags-btn');
        clearBtn?.addEventListener('click', () => this.clearAllTags());
    }
    
    async loadTagStats() {
        try {
            const response = await fetch('/api/admin/tag-stats');
            const stats = await response.json();
            
            const totalTagsEl = document.getElementById('total-tags');
            const totalAliasesEl = document.getElementById('total-aliases');
            
            if (totalTagsEl) totalTagsEl.textContent = stats.total_tags;
            if (totalAliasesEl) totalAliasesEl.textContent = stats.total_aliases;
        } catch (error) {
            console.error('Error loading tag stats:', error);
        }
    }
    
    async uploadCSV(file) {
        const statusDiv = document.getElementById('csv-import-status');
        const progressDiv = document.getElementById('csv-import-progress');
        
        statusDiv.style.display = 'block';
        progressDiv.innerHTML = `
            <div class="bg-blue-600 p-3 mb-2 text-white">
                <strong>Uploading and processing...</strong><br>
                <span class="text-xs">This <em>can</em> take a while. Do not refresh the page.</span>
            </div>
        `;
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            
            const response = await fetch('/api/admin/import-tags-csv', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }
            
            const result = await response.json();
            
            let html = `
                <div class="bg-green-600 p-3 mb-2 text-white">
                    <strong>${result.message}</strong>
                </div>
                <div class="text-[#94a3b8] space-y-1">
                    <div>Rows processed: <strong class="text-white">${result.rows_processed}</strong></div>
                    <div>Tags created: <strong class="text-white">${result.tags_created}</strong></div>
                    <div>Tags updated: <strong class="text-white">${result.tags_updated}</strong></div>
                    <div>Aliases created: <strong class="text-white">${result.aliases_created}</strong></div>
            `;
            
            if (result.skipped_long_tags > 0 || result.skipped_long_aliases > 0) {
                html += `
                    <div class="pt-2 border-t border-[#334155] mt-2">
                        <div class="text-yellow-500">Skipped (too long):</div>
                        ${result.skipped_long_tags > 0 ? `<div>Tags: <strong class="text-white">${result.skipped_long_tags}</strong></div>` : ''}
                        ${result.skipped_long_aliases > 0 ? `<div>Aliases: <strong class="text-white">${result.skipped_long_aliases}</strong></div>` : ''}
                    </div>
                `;
            }
            
            html += '</div>';
            
            if (result.errors && result.errors.length > 0) {
                html += `
                    <div class="bg-yellow-600 p-3 mt-2 text-white text-xs">
                        <strong>Warnings (${result.total_errors} total):</strong><br>
                        ${result.errors.slice(0, 5).join('<br>')}
                    </div>
                `;
            }
            
            progressDiv.innerHTML = html;
            
            // Reload stats
            await this.loadTagStats();
            
        } catch (error) {
            progressDiv.innerHTML = `
                <div class="bg-red-600 p-3 text-white">
                    <strong>Error:</strong> ${error.message}
                </div>
            `;
        }
    }
    
    async searchTags() {
        const query = document.getElementById('tag-search-input').value;
        const resultsDiv = document.getElementById('tag-search-results');
        
        if (!query) {
            resultsDiv.innerHTML = '';
            return;
        }
        
        try {
            const response = await fetch(`/api/admin/search-tags?q=${encodeURIComponent(query)}`);
            const data = await response.json();
            
            if (data.tags.length === 0) {
                resultsDiv.innerHTML = '<p class="text-xs text-[#94a3b8] p-3">No tags found</p>';
                return;
            }
            
            resultsDiv.innerHTML = data.tags.map(tag => `
                <div class="bg-[#0f172a] p-3 border-b border-[#334155] flex justify-between items-center">
                    <div>
                        <button class="text-xs text-[#94a3b8] bg-red-600 hover:bg-red-700 text-white px-2 py-1 mr-2" onclick="if(confirm('Delete tag & alias?')) { app.apiCall('/api/admin/tags/${tag.id}', { method: 'DELETE' }).then(() => { alert('Tag deleted'); location.reload(); }).catch(e => alert('Error deleting tag: ' + e.message)); }">&#x2715;</button>
                        <a href="/?q=${encodeURIComponent(tag.name)}" class="tag ${tag.category}">${tag.name}</a>
                        <span class="text-xs text-[#94a3b8] ml-2">(${tag.post_count} posts)</span>
                    </div>
                    <span class="text-xs text-[#94a3b8] uppercase">${tag.category}</span>
                </div>
            `).join('');
            
        } catch (error) {
            console.error('Error searching tags:', error);
            resultsDiv.innerHTML = '<p class="text-xs text-red-500 p-3">Error searching tags</p>';
        }
    }
    
    async clearAllTags() {
        if (!confirm('Are you sure you want to delete ALL tags? This cannot be undone!')) {
            return;
        }
        
        if (!confirm('This will delete all tags and aliases. Are you REALLY sure?')) {
            return;
        }
        
        try {
            await app.apiCall('/api/admin/clear-tags', { method: 'DELETE' });
            alert('All tags cleared successfully');
            await this.loadTagStats();
            document.getElementById('tag-search-results').innerHTML = '';
        } catch (error) {
            alert('Error clearing tags: ' + error.message);
        }
    }
}

// Initialize admin panel
if (document.getElementById('admin-panel')) {
    const adminPanel = new AdminPanel();
}
