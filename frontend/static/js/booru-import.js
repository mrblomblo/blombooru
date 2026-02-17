class BooruImporter {
    constructor(uploader) {
        this.uploader = uploader;
        this.tagInputHelper = new TagInputHelper();
        this.currentPost = null;
        this.isFetching = false;
        this.isImporting = false;

        this.container = document.getElementById('booru-import-section');
        if (this.container) {
            this.init();
        }
    }

    init() {
        this.urlInput = this.container.querySelector('#booru-url-input');
        this.fetchBtn = this.container.querySelector('#booru-fetch-btn');
        this.previewArea = this.container.querySelector('#booru-preview-area');
        this.statusArea = this.container.querySelector('#booru-status');
        this.autoCreateCheckbox = this.container.querySelector('#booru-auto-create-tags');

        if (this.fetchBtn) {
            this.fetchBtn.addEventListener('click', () => this.fetchPost());
        }

        if (this.urlInput) {
            this.urlInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.fetchPost();
                }
            });

            this.urlInput.addEventListener('paste', () => {
                setTimeout(() => this.fetchPost(), 100);
            });
        }
    }

    showStatus(message, type = 'info') {
        if (!this.statusArea) return;
        const colorClass = type === 'error' ? 'text-danger' : type === 'success' ? 'text-success' : 'text-secondary';
        this.statusArea.innerHTML = `<p class="text-xs ${colorClass}">${message}</p>`;
        this.statusArea.style.display = 'block';
    }

    clearStatus() {
        if (!this.statusArea) {
            return;
        }
        this.statusArea.style.display = 'none';
        this.statusArea.innerHTML = '';
    }

    _t(keyOrString) {
        if (!keyOrString) return '';
        if (keyOrString.includes(':::')) {
            const [key, arg] = keyOrString.split(':::');
            return window.i18n.t(key, { error: arg });
        }
        return window.i18n.t(keyOrString);
    }

    async fetchPost() {
        const url = this.urlInput?.value?.trim();
        if (!url) return;

        if (this.isFetching) return;
        this.isFetching = true;
        this.clearStatus();
        this.hidePreview();

        this.showStatus(window.i18n.t('admin.media_management.booru_import.fetching'), 'info');
        this.fetchBtn.disabled = true;

        try {
            const response = await fetch('/api/booru-import/fetch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));

                if (response.status === 403 || (error.detail && error.detail.includes('403'))) {
                    throw new Error(window.i18n.t('errors.error_403'));
                }

                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            this.currentPost = await response.json();
            this.currentPost._originalUrl = url;
            this.renderPreview();
            this.clearStatus();
        } catch (e) {
            console.error('Booru fetch error:', e);
            this.showStatus(
                window.i18n.t('admin.media_management.booru_import.fetch_error') + ': ' + this._t(e.message),
                'error'
            );
        } finally {
            this.isFetching = false;
            if (this.fetchBtn) this.fetchBtn.disabled = false;
        }
    }

    renderPreview() {
        if (!this.previewArea || !this.currentPost) return;

        const post = this.currentPost;

        const sortedTags = this.sortPostTags(post.tags);
        const tagsText = sortedTags.map(t => t.name).join(' ');

        const tagsByCategory = {};
        for (const tag of sortedTags) {
            if (!tagsByCategory[tag.category]) {
                tagsByCategory[tag.category] = [];
            }
            tagsByCategory[tag.category].push(tag.name);
        }

        const categoryOrder = ['artist', 'copyright', 'character', 'general', 'meta'];
        let tagCategoryHtml = '';
        for (const cat of categoryOrder) {
            const catTags = tagsByCategory[cat];
            if (catTags && catTags.length > 0) {
                tagCategoryHtml += `
                    <div class="flex flex-wrap gap-1 w-full">
                        ${catTags.map(t => `<span class="text-xs tag-text tag ${cat}">${this.escapeHtml(t)}</span>`).join('')}
                    </div>
                `;
            }
        }

        this.previewArea.innerHTML = `
            <div class="bg p-4 border">
                <div class="flex flex-col sm:flex-row gap-4">
                    <!-- Thumbnail -->
                    <div class="flex-shrink-0">
                        ${post.preview_url
                ? `<img src="/api/booru-import/proxy-image?url=${encodeURIComponent(post.preview_url)}" alt="Preview" 
                                    class="w-32 h-32 object-contain surface border" 
                                    onerror="this.style.display='none'">`
                : '<div class="w-32 h-32 surface border flex items-center justify-center text-xs text-secondary">' + window.i18n.t('upload.preview.none') + '</div>'
            }
                    </div>

                    <!-- Info -->
                    <div class="flex-1 min-w-0">
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs mb-3">
                            <div class="flex items-center gap-2">
                                <span class="text-secondary shrink-0">${window.i18n.t('media.info.rating')}</span>
                                <div id="booru-rating-select" class="custom-select w-32" data-value="${post.rating}">
                                    <div class="custom-select-trigger w-full flex items-center justify-between gap-2 px-2 py-1 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors">
                                        <span class="custom-select-value capitalize">${post.rating}</span>
                                        <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                                    </div>
                                    <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50">
                                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs ${post.rating === 'safe' ? 'selected' : ''}" data-value="safe">Safe</div>
                                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs ${post.rating === 'questionable' ? 'selected' : ''}" data-value="questionable">Questionable</div>
                                        <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs ${post.rating === 'explicit' ? 'selected' : ''}" data-value="explicit">Explicit</div>
                                    </div>
                                </div>
                            </div>
                            <div class="flex items-center min-w-0">
                                <span class="text-secondary shrink-0 mr-1">${window.i18n.t('media.info.source')}</span>
                                ${post.source
                ? `<strong class="truncate min-w-0 flex-1 font-normal text-right">
                                        <a href="${this.escapeHtml(post.source)}" target="_blank" class="text-primary hover:underline block truncate" title="${this.escapeHtml(post.source)}">
                                            ${this.escapeHtml(post.source)}
                                        </a>
                                       </strong>`
                : '<span class="text-secondary ml-1">...</span>'
            }
                            </div>
                            <div>
                                <span class="text-secondary">${window.i18n.t('media.info.dimensions')}</span>
                                <span class="font-medium ml-1">${post.width}×${post.height}</span>
                            </div>
                            <div>
                                <span class="text-secondary">${window.i18n.t('media.info.size')}</span>
                                <span class="font-medium ml-1">${this.formatFileSize(post.file_size)}</span>
                            </div>
                        </div>

                        <!-- Tags by category -->
                        <div class="mb-3">
                            <div class="text-xs font-bold mb-1">${window.i18n.t('media.tags.title')}</div>
                            <div class="max-h-40 overflow-y-auto p-2 surface border flex flex-wrap gap-2">
                                ${tagCategoryHtml}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Editable tags input -->
                <div class="mt-3 relative">
                    <label class="text-xs font-bold block mb-1">${window.i18n.t('media.tags.edit_tags')}</label>
                    <div id="booru-tags-input" 
                        class="bg w-full px-3 py-2 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                        contenteditable="true"
                        style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;">${this.escapeHtml(tagsText)}</div>
                </div>

                <!-- Actions -->
                <div class="flex flex-col sm:flex-row gap-2 mt-4">
                    <button id="booru-cancel-btn"
                            class="px-4 py-2 border text-xs font-medium transition-colors hover:text-danger hover:border-danger">
                        ${window.i18n.t('common.cancel')}
                    </button>
                    <button id="booru-import-btn"
                            class="flex-1 px-4 py-2 bg-primary primary-text text-xs font-medium transition-colors hover:bg-primary">
                        ${window.i18n.t('admin.media_management.booru_import.import_now')}
                    </button>
                    <button id="booru-queue-btn"
                            class="flex-1 px-4 py-2 surface-light text text-xs font-medium transition-colors hover:surface border">
                        ${window.i18n.t('admin.media_management.booru_import.add_to_queue')}
                    </button>
                </div>
            </div>
        `;

        this.previewArea.style.display = 'block';

        const ratingSelectEl = this.previewArea.querySelector('#booru-rating-select');
        if (ratingSelectEl && typeof CustomSelect !== 'undefined') {
            new CustomSelect(ratingSelectEl);
        }

        // Setup fullscreen click on image
        const img = this.previewArea.querySelector('img');
        if (img) {
            img.style.cursor = 'pointer';
            img.addEventListener('click', () => {
                if (this.uploader && this.uploader.fullscreenViewer) {
                    const isVideo = post.file_url.endsWith('.mp4') || post.file_url.endsWith('.webm'); // Could be better
                    this.uploader.fullscreenViewer.open(`/api/booru-import/proxy-image?url=${encodeURIComponent(post.file_url)}`, isVideo);
                }
            });
        }

        const tagsInput = this.previewArea.querySelector('#booru-tags-input');
        if (tagsInput && this.tagInputHelper) {
            this.tagInputHelper.setupTagInput(tagsInput, 'booru-import-tags', {
                validateDelay: 500,
            });
            setTimeout(() => {
                this.tagInputHelper.validateAndStyleTags(tagsInput);
            }, 200);
        }

        if (tagsInput && typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(tagsInput, {
                multipleValues: true,
                containerClasses: 'surface border border-color shadow-lg z-50',
            });
        }

        const importBtn = this.previewArea.querySelector('#booru-import-btn');
        const queueBtn = this.previewArea.querySelector('#booru-queue-btn');
        const cancelBtn = this.previewArea.querySelector('#booru-cancel-btn');

        if (importBtn) {
            importBtn.addEventListener('click', () => this.importNow());
        }
        if (queueBtn) {
            queueBtn.addEventListener('click', () => this.addToQueue());
        }
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.cancel());
        }
    }

    hidePreview() {
        if (this.previewArea) {
            this.previewArea.style.display = 'none';
            this.previewArea.innerHTML = '';
        }
    }

    getEditedTags() {
        const tagsInput = this.previewArea?.querySelector('#booru-tags-input');
        if (!tagsInput) return [];
        const text = this.tagInputHelper.getPlainTextFromDiv(tagsInput);
        return text.split(/\s+/).filter(t => t.length > 0);
    }

    getCategoryHints() {
        if (!this.currentPost) return {};
        const hints = {};
        const currentTags = this.getEditedTags(); // List of tag strings
        const currentTagSet = new Set(currentTags.map(t => t.toLowerCase()));

        for (const tag of this.currentPost.tags) {
            // Only add hint if the tag is still present in the editor
            if (currentTagSet.has(tag.name.toLowerCase())) {
                hints[tag.name.toLowerCase()] = tag.category;
            }
        }
        return hints;
    }

    cancel() {
        this.hidePreview();
        this.currentPost = null;
        if (this.urlInput) this.urlInput.value = '';
        this.clearStatus();
    }

    async importNow() {
        if (this.isImporting || !this.currentPost) return;

        this.isImporting = true;
        const importBtn = this.previewArea?.querySelector('#booru-import-btn');
        if (importBtn) {
            importBtn.disabled = true;
            importBtn.textContent = window.i18n.t('admin.media_management.booru_import.importing');
        }

        try {
            const tags = this.getEditedTags();
            const autoCreate = this.autoCreateCheckbox?.checked || false;
            const ratingSelect = this.previewArea?.querySelector('#booru-rating-select');
            const rating = ratingSelect ? ratingSelect.dataset.value : this.currentPost.rating;

            const response = await fetch('/api/booru-import/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: this.currentPost._originalUrl,
                    tags: tags,
                    rating: rating,
                    source: this.currentPost.source || this.currentPost.booru_url,
                    auto_create_tags: autoCreate,
                    category_hints: this.getCategoryHints(),
                }),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));

                if (response.status === 403 || (error.detail && error.detail.includes('403'))) {
                    throw new Error(window.i18n.t('errors.error_403'));
                }

                throw new Error(error.detail || window.i18n.t('admin.media_management.booru_import.fetch_error'));
            }

            this.showStatus(
                window.i18n.t('admin.media_management.booru_import.import_success'),
                'success'
            );

            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(
                    window.i18n.t('admin.media_management.booru_import.import_success'),
                    'success'
                );
            }

            // Reset
            this.hidePreview();
            this.currentPost = null;
            if (this.urlInput) this.urlInput.value = '';

        } catch (e) {
            console.error('Booru import error:', e);
            const errorMsg = e.message.includes('duplicate')
                ? window.i18n.t('admin.media_management.booru_import.already_exists')
                : this._t(e.message);
            this.showStatus(errorMsg, 'error');

            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(errorMsg, 'error');
            }
        } finally {
            this.isImporting = false;
            if (importBtn) {
                importBtn.disabled = false;
                importBtn.textContent = window.i18n.t('admin.media_management.booru_import.import_now');
            }
        }
    }

    async addToQueue() {
        if (!this.currentPost || !this.uploader) return;

        const post = this.currentPost;

        if (!post.file_url) {
            this.showStatus(window.i18n.t('admin.media_management.booru_import.no_downloadable_file'), 'error');
            return;
        }

        const queueBtn = this.previewArea?.querySelector('#booru-queue-btn');
        if (queueBtn) {
            queueBtn.disabled = true;
            queueBtn.textContent = window.i18n.t('common.loading');
        }

        try {
            // Download the file as a blob via backend proxy to avoid CORS issues
            const proxyUrl = `/api/booru-import/proxy-image?url=${encodeURIComponent(post.file_url)}`;
            const response = await fetch(proxyUrl);
            if (!response.ok) {
                if (response.status === 403) {
                    throw new Error(window.i18n.t('errors.error_403'));
                }
                throw new Error(window.i18n.t('admin.media_management.booru_import.error_download_failed', { error: `HTTP ${response.status}` }));
            }

            const blob = await response.blob();
            const file = new File([blob], post.filename, { type: blob.type });

            const tags = this.getEditedTags();
            const ratingSelect = this.previewArea?.querySelector('#booru-rating-select');
            const rating = ratingSelect ? ratingSelect.dataset.value : post.rating;

            await this.uploader.addBooruImport(file, {
                rating: rating,
                source: post.source || post.booru_url,
                tags: tags,
                categoryHints: this.getCategoryHints(),
                autoCreateTags: this.autoCreateCheckbox?.checked || false,
            });

            this.showStatus(
                window.i18n.t('admin.media_management.booru_import.added_to_queue'),
                'success'
            );

            // Reset
            this.hidePreview();
            this.currentPost = null;
            if (this.urlInput) this.urlInput.value = '';

        } catch (e) {
            console.error('Error adding to queue:', e);
            this.showStatus(e.message, 'error');
        } finally {
            if (queueBtn) {
                queueBtn.disabled = false;
                queueBtn.textContent = window.i18n.t('admin.media_management.booru_import.add_to_queue');
            }
        }
    }

    capitalizeFirst(str) {
        return str ? str.charAt(0).toUpperCase() + str.slice(1) : '';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    truncateUrl(url, maxLen = 30) {
        try {
            const parsed = new URL(url);
            const display = parsed.hostname + parsed.pathname;
            return display.length > maxLen ? display.substring(0, maxLen) + '…' : display;
        } catch {
            return url.length > maxLen ? url.substring(0, maxLen) + '…' : url;
        }
    }

    formatFileSize(bytes) {
        if (!bytes) return '...';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    sortPostTags(tags) {
        const order = { 'artist': 1, 'copyright': 2, 'character': 3, 'general': 4, 'meta': 5 };
        return [...tags].sort((a, b) => {
            const catA = order[a.category] || 4;
            const catB = order[b.category] || 4;
            if (catA !== catB) return catA - catB;
            return a.name.localeCompare(b.name);
        });
    }
}

function initBooruImporter() {
    if (document.getElementById('booru-import-section')) {
        window.booruImporter = new BooruImporter(window.uploaderInstance);
    }
}

if (document.getElementById('booru-import-section')) {
    if (window.uploaderInstance) {
        initBooruImporter();
    } else {
        const checkInterval = setInterval(() => {
            if (window.uploaderInstance) {
                clearInterval(checkInterval);
                initBooruImporter();
            }
        }, 100);
        setTimeout(() => clearInterval(checkInterval), 10000);
    }
}
