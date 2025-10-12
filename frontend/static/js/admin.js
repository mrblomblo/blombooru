class AdminPanel {
    constructor() {
        this.tagValidationCache = new Map();
        this.aliasCache = new Set();
        this.validationTimeout = null;
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadSettings();
        this.setupTagManagement();
        this.loadTagStats();
        this.loadMediaStats();
        this.loadThemes();
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
        
        // Add tags form
        const addTagsForm = document.getElementById('add-tags-form');
        if (addTagsForm) {
            addTagsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.addNewTags();
            });
        }
    }
    
    // Helper methods for tag validation
    getPlainTextFromDiv(div) {
        return div.textContent || '';
    }
    
    getCursorPosition(element) {
        const selection = window.getSelection();
        if (selection.rangeCount === 0) return 0;
        
        const range = selection.getRangeAt(0);
        const preCaretRange = range.cloneRange();
        preCaretRange.selectNodeContents(element);
        preCaretRange.setEnd(range.endContainer, range.endOffset);
        
        return preCaretRange.toString().length;
    }
    
    setCursorPosition(element, offset) {
        const selection = window.getSelection();
        const range = document.createRange();
        
        let currentOffset = 0;
        let found = false;
        
        const traverseNodes = (node) => {
            if (found) return;
            
            if (node.nodeType === Node.TEXT_NODE) {
                const nodeLength = node.textContent.length;
                if (currentOffset + nodeLength >= offset) {
                    range.setStart(node, offset - currentOffset);
                    range.collapse(true);
                    found = true;
                    return;
                }
                currentOffset += nodeLength;
            } else {
                for (let child of node.childNodes) {
                    traverseNodes(child);
                    if (found) return;
                }
            }
        };
        
        try {
            traverseNodes(element);
            if (!found && element.lastChild) {
                range.setStartAfter(element.lastChild);
                range.collapse(true);
            }
            selection.removeAllRanges();
            selection.addRange(range);
        } catch (e) {
            console.error('Error setting cursor:', e);
        }
    }
    
    async checkTagOrAliasExists(tagName) {
        if (!tagName || !tagName.trim()) return false;
        const normalized = tagName.toLowerCase().trim();
        
        try {
            // Check if it's a tag
            const tagRes = await fetch(`/api/tags/${encodeURIComponent(normalized)}`);
            if (tagRes.ok) {
                return true; // Tag exists
            }
            
            // Check if it's an alias
            const aliasRes = await fetch(`/api/admin/check-alias?name=${encodeURIComponent(normalized)}`);
            if (aliasRes.ok) {
                const data = await aliasRes.json();
                return data.exists; // Alias exists
            }
            
            return false;
        } catch (e) {
            console.error('Error checking tag/alias:', e);
            return false;
        }
    }
    
    parseTagWithCategory(tagString) {
        const prefixes = ['artist:', 'copyright:', 'character:', 'meta:'];
        const normalized = tagString.trim().toLowerCase();
        
        for (const prefix of prefixes) {
            if (normalized.startsWith(prefix)) {
                const category = prefix.slice(0, -1); // Remove the colon
                const tagName = normalized.slice(prefix.length).trim();
                return { tagName, category };
            }
        }
        
        // No prefix, default to general
        return { tagName: normalized, category: 'general' };
    }
    
    async validateAndStyleNewTags() {
        const tagsInput = document.getElementById('new-tags-input');
        if (!tagsInput) return;
        
        const text = this.getPlainTextFromDiv(tagsInput);
        const cursorPos = this.getCursorPosition(tagsInput);
        
        // Split by whitespace
        const parts = text.split(/(\s+)/);
        const tags = [];
        
        // Check each non-whitespace part
        for (let part of parts) {
            if (part.trim()) {
                const { tagName } = this.parseTagWithCategory(part);
                
                if (!this.tagValidationCache.has(tagName)) {
                    const exists = await this.checkTagOrAliasExists(tagName);
                    this.tagValidationCache.set(tagName, exists);
                }
                
                // Reverse logic: strike through if exists
                tags.push({ text: part, shouldIgnore: this.tagValidationCache.get(tagName) });
            } else {
                tags.push({ text: part, isWhitespace: true });
            }
        }
        
        // Build styled HTML
        let html = '';
        for (let tag of tags) {
            if (tag.isWhitespace) {
                html += tag.text;
            } else if (tag.shouldIgnore) {
                html += `<span class="invalid-tag">${tag.text}</span>`;
            } else {
                html += tag.text;
            }
        }
        
        // Update content if changed
        if (tagsInput.innerHTML !== html) {
            tagsInput.innerHTML = html || '';
            this.setCursorPosition(tagsInput, cursorPos);
        }
    }
    
    setupNewTagsInput() {
        const tagsInput = document.getElementById('new-tags-input');
        if (!tagsInput) return;
        
        // Handle input events
        tagsInput.addEventListener('input', () => {
            if (this.validationTimeout) {
                clearTimeout(this.validationTimeout);
            }
            this.validationTimeout = setTimeout(() => {
                this.validateAndStyleNewTags();
            }, 300);
        });
        
        // Immediate validation on space
        tagsInput.addEventListener('keyup', (e) => {
            if (e.key === ' ') {
                if (this.validationTimeout) {
                    clearTimeout(this.validationTimeout);
                }
                this.validateAndStyleNewTags();
            }
        });
        
        // Prevent default Enter behavior
        tagsInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
            }
        });
        
        // Paste as plain text
        tagsInput.addEventListener('paste', (e) => {
            e.preventDefault();
            const text = e.clipboardData.getData('text/plain');
            document.execCommand('insertText', false, text);
        });
    }
    
    async addNewTags() {
        const tagsInput = document.getElementById('new-tags-input');
        const statusDiv = document.getElementById('add-tags-status');
        const resultDiv = document.getElementById('add-tags-result');
        
        const text = this.getPlainTextFromDiv(tagsInput);
        const tagStrings = text.split(/\s+/).filter(t => t.length > 0);
        
        if (tagStrings.length === 0) {
            app.showNotification('Please enter at least one tag!', 'error');
            return;
        }
        
        // Parse and filter tags
        const tagsToCreate = [];
        const ignoredTags = [];
        
        for (const tagString of tagStrings) {
            const { tagName, category } = this.parseTagWithCategory(tagString);
            
            // Check if should be ignored
            const shouldIgnore = this.tagValidationCache.get(tagName);
            
            if (shouldIgnore) {
                ignoredTags.push(tagString);
            } else {
                tagsToCreate.push({ name: tagName, category });
            }
        }
        
        if (tagsToCreate.length === 0) {
            app.showNotification('All tags already exist or are aliases.', 'error', 'Nothing to add');
            return;
        }
        
        // Show loading
        statusDiv.style.display = 'block';
        resultDiv.innerHTML = `
            <div class="bg-primary primary-text p-3 mb-2">
                <strong>Adding tags...</strong>
            </div>
        `;
        
        try {
            const response = await app.apiCall('/api/admin/bulk-create-tags', {
                method: 'POST',
                body: JSON.stringify({ tags: tagsToCreate })
            });
            
            let html = `
                <div class="bg-success p-3 mb-2 tag-text">
                    <strong>Tags added successfully!</strong>
                </div>
                <div class="text-secondary space-y-1">
                    <div>Tags created: <strong class="text">${response.created}</strong></div>
                    <div>Tags skipped (already exist): <strong class="text">${response.skipped}</strong></div>
                    <div>Errors: <strong class="text">${response.errors.length}</strong></div>
                </div>
            `;
            
            if (ignoredTags.length > 0) {
                html += `
                    <div class="mt-2 p-2 surface-light border text-xs">
                        <strong>Ignored (already exist or are aliases):</strong><br>
                        ${ignoredTags.join(', ')}
                    </div>
                `;
            }
            
            if (response.errors.length > 0) {
                html += `
                    <div class="mt-2 p-2 bg-warning tag-text text-xs">
                        <strong>Errors:</strong><br>
                        ${response.errors.slice(0, 5).join('<br>')}
                    </div>
                `;
            }
            
            resultDiv.innerHTML = html;
            
            // Clear input and cache
            tagsInput.textContent = '';
            this.tagValidationCache.clear();
            
            // Reload stats
            await this.loadTagStats();
            
        } catch (error) {
            resultDiv.innerHTML = `
                <div class="bg-danger p-3 tag-text">
                    <strong>Error:</strong> ${error.message}
                </div>
            `;
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
        const theme = document.getElementById('theme-select')?.value;

        if (!appName || !defaultRating || !theme) {
            app.showNotification('Please fill in all settings fields!', 'error');
            return;
        }

        const settings = {
            app_name: appName,
            default_rating_filter: defaultRating,
            theme: theme
        };
        
        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify(settings)
            });
            
            location.reload();
        } catch (error) {
            app.showNotification(error.message, 'error', 'Error saving settings');
        }
    }
    
    async scanMedia() {
        const scanBtn = document.getElementById('scan-media-btn');
        const originalText = scanBtn.textContent;
        scanBtn.disabled = true;
        scanBtn.textContent = 'Scanning...';
        
        try {
            const result = await app.apiCall('/api/admin/scan-media', {
                method: 'POST'
            });
            
            if (result.new_files === 0) {
                app.showNotification('No new untracked media files found.', 'info');
                scanBtn.disabled = false;
                scanBtn.textContent = originalText;
                return;
            }
            
            // Show loading message
            scanBtn.textContent = `Loading ${result.new_files} file(s)...`;
            
            // Get the uploader instance
            const uploader = window.uploaderInstance;
            if (!uploader) {
                app.showNotification('Please refresh the page and try again.', 'error', 'Uploader not initialized');
                scanBtn.disabled = false;
                scanBtn.textContent = originalText;
                return;
            }
            
            // Fetch and add each file to the uploader
            let loadedCount = 0;
            let skippedCount = 0;
            
            for (const filePath of result.files) {
                try {
                    scanBtn.textContent = `Loading ${loadedCount + 1}/${result.new_files}...`;
                    
                    // Fetch the file from the server
                    const response = await fetch(`/api/admin/get-untracked-file?path=${encodeURIComponent(filePath)}`);
                    
                    if (!response.ok) {
                        console.error(`Failed to fetch file: ${filePath}`);
                        skippedCount++;
                        continue;
                    }
                    
                    const blob = await response.blob();
                    const filename = filePath.split('/').pop().split('\\').pop(); // Handle both Unix and Windows paths
                    const file = new File([blob], filename, { type: blob.type });
                    
                    // Add to uploader
                    await uploader.addScannedFile(file);
                    loadedCount++;
                    
                } catch (error) {
                    console.error(`Error loading file ${filePath}:`, error);
                    skippedCount++;
                }
            }
            
            // Show results
            let message = `Loaded ${loadedCount} file(s) into the editor.`;
            if (skippedCount > 0) {
                message += `\n${skippedCount} file(s) skipped due to errors.`;
            }
            if (loadedCount > 0) {
                message += '\n\nYou can now edit tags and ratings before submitting.';
            }
            app.showNotification(message, 'success');
            
        } catch (error) {
            console.error('Scan error:', error);
            app.showNotification(error.message, 'error', 'Error scanning media');
        } finally {
            scanBtn.disabled = false;
            scanBtn.textContent = originalText;
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
        // Setup new tags input validation
        this.setupNewTagsInput();
        
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

    async loadMediaStats() {
        try {
            const response = await fetch('/api/admin/media-stats');
            const stats = await response.json();

            const totalMediaEl = document.getElementById('total-media');
            const totalImagesEl = document.getElementById('total-images');
            const totalGifsEl = document.getElementById('total-gifs');
            const totalVideosEl = document.getElementById('total-videos');

            if (totalMediaEl) totalMediaEl.textContent = stats.total_media;
            if (totalImagesEl) totalImagesEl.textContent = stats.total_images;
            if (totalGifsEl) totalGifsEl.textContent = stats.total_gifs;
            if (totalVideosEl) totalVideosEl.textContent = stats.total_videos;
        } catch (error) {
            console.error('Error loading media stats:', error);
        }
    }
    
    async uploadCSV(file) {
        const statusDiv = document.getElementById('csv-import-status');
        const progressDiv = document.getElementById('csv-import-progress');
        
        statusDiv.style.display = 'block';
        progressDiv.innerHTML = `
            <div class="bg-primary primary-text p-3 mb-2">
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
                <div class="bg-success p-3 mb-2 tag-text">
                    <strong>${result.message}</strong>
                </div>
                <div class="text-secondary space-y-1">
                    <div>Rows processed: <strong class="text">${result.rows_processed}</strong></div>
                    <div>Tags created: <strong class="text">${result.tags_created}</strong></div>
                    <div>Tags updated: <strong class="text">${result.tags_updated}</strong></div>
                    <div>Aliases created: <strong class="text">${result.aliases_created}</strong></div>
            `;
            
            if (result.skipped_long_tags > 0 || result.skipped_long_aliases > 0) {
                html += `
                    <div class="pt-2 border-t mt-2">
                        <div class="text-warning">Skipped (too long):</div>
                        ${result.skipped_long_tags > 0 ? `<div>Tags: <strong class="text">${result.skipped_long_tags}</strong></div>` : ''}
                        ${result.skipped_long_aliases > 0 ? `<div>Aliases: <strong class="text">${result.skipped_long_aliases}</strong></div>` : ''}
                    </div>
                `;
            }
            
            html += '</div>';
            
            if (result.errors && result.errors.length > 0) {
                html += `
                    <div class="bg-warning p-3 mt-2 tag-text text-xs">
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
                <div class="bg-danger p-3 tag-text">
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
                resultsDiv.innerHTML = '<p class="text-xs text-secondary p-3">No tags found</p>';
                return;
            }
            
            resultsDiv.innerHTML = data.tags.map(tag => `
                <div class="bg p-3 border-b flex justify-between items-center">
                    <div>
                        <button class="text-xs text-secondary bg-danger hover:bg-danger tag-text px-2 py-1 mr-2" onclick="if(confirm('Delete tag & alias?')) { app.apiCall('/api/admin/tags/${tag.id}', { method: 'DELETE' }).then(() => { app.showNotification('Tag deleted', 'success'); location.reload(); }).catch(e => app.showNotification(e.message, 'error', 'Error deleting tag')); }">&#x2715;</button>
                        <a href="/?q=${encodeURIComponent(tag.name)}" class="tag ${tag.category} tag-text">${tag.name}</a>
                        <span class="text-xs text-secondary ml-2">(${tag.post_count} posts)</span>
                    </div>
                    <span class="text-xs text-secondary uppercase">${tag.category}</span>
                </div>
            `).join('');
            
        } catch (error) {
            console.error('Error searching tags:', error);
            resultsDiv.innerHTML = '<p class="text-xs text-danger p-3">Error searching tags</p>';
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
            app.showNotification('All tags cleared successfully', 'success');
            await this.loadTagStats();
            document.getElementById('tag-search-results').innerHTML = '';
        } catch (error) {
            app.showNotification(error.message, 'error', 'Error clearing tags');
        }
    }

    async loadThemes() {
        try {
            const response = await fetch('/api/admin/themes');
            const data = await response.json();

            const themeSelect = document.getElementById('theme-select');
            if (!themeSelect) return;

            themeSelect.innerHTML = '';

            data.themes.forEach(theme => {
                const option = document.createElement('option');
                option.value = theme.id;

                if (theme.is_dark) {
                    option.textContent = '🌙 ';
                } else {
                    option.textContent = '☀️ ';
                }

                option.textContent += theme.name;

                if (theme.id === data.current_theme) {
                    option.selected = true;
                }

                themeSelect.appendChild(option);
            });

        } catch (error) {
            console.error('Error loading themes:', error);
        }
    }
}

// Initialize admin panel
if (document.getElementById('admin-panel')) {
    const adminPanel = new AdminPanel();
}
