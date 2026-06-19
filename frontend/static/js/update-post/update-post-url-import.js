class UpdatePostUrlImport extends UpdatePostModalBase {
    constructor(mediaId, currentMedia) {
        super(mediaId, currentMedia);

        this._fetchedPost = null;
        this._isFetching = false;
        this._isApplying = false;
    }

    build(onBack) {
        this.hide();
        this._fetchedPost = null;
        this._onBack = onBack;

        const modal = document.createElement('div');
        modal.id = 'update-post-modal';
        modal.className = 'fixed inset-0 flex items-end sm:items-center justify-center z-50';
        modal.style.background = 'rgba(0, 0, 0, 0.5)';

        modal.innerHTML = `
            <div class="surface w-full h-full sm:h-auto sm:max-h-[85vh] sm:max-w-4xl sm:mx-4 flex flex-col border-t sm:border shadow-2xl safe-area-bottom">
                <!-- Header -->
                <div class="flex items-center p-4 border-b border-color flex-shrink-0">
                    <h2 class="text-base sm:text-lg font-bold truncate">${this._t('modal.update_post.from_url')}</h2>
                </div>

                <!-- Body -->
                <div class="flex-1 overflow-auto p-4">
                    <!-- URL input -->
                    <div class="flex gap-2 mb-3">
                        <input id="upm-url-input" type="url"
                            class="flex-1 bg px-3 py-2 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                            placeholder="https://danbooru.donmai.us/posts/..."
                            value="${this._escapeHtml(this.currentMedia?.source || '')}">
                        <button id="upm-url-fetch" class="btn-primary whitespace-nowrap">
                            ${this._t('admin.media_management.booru_import.fetch')}
                        </button>
                    </div>

                    <div id="upm-url-status" class="text-xs text-secondary mb-2" style="display:none;"></div>

                    <!-- Preview area (filled by _renderPreview) -->
                    <div id="upm-url-preview" style="display:none;"></div>
                </div>

                <!-- Footer -->
                <div class="flex-shrink-0 p-4 border-t border-color surface">
                    <div class="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3">
                        <div class="flex gap-2 sm:ml-auto">
                            <button id="upm-url-apply" class="flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn-primary text-sm font-medium" style="display:none;">
                                ${this._t('modal.update_post.apply')}
                            </button>
                            <button id="upm-url-cancel" class="flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn text-sm font-medium">
                                ${this._t('common.cancel')}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this._modal = modal;
        document.body.style.overflow = 'hidden';

        const q = (sel) => modal.querySelector(sel);

        q('#upm-url-cancel').addEventListener('click', () => this._onBack());

        q('#upm-url-fetch').addEventListener('click', () => this._fetchBooru());
        q('#upm-url-input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); this._fetchBooru(); }
        });
        q('#upm-url-input').addEventListener('paste', () => {
            setTimeout(() => this._fetchBooru(), 100);
        });
        q('#upm-url-apply').addEventListener('click', () => this._applyFromUrl());

        this._registerEscapeHandler(() => this._onBack());
    }

    // ==================== Fetch & preview ====================

    _setStatus(msg, type = 'info') {
        const el = this._modal?.querySelector('#upm-url-status');
        if (!el) return;
        el.textContent = msg;
        el.className = `text-xs mb-2 ${type === 'error' ? 'text-danger' : 'text-secondary'}`;
        el.style.display = msg ? '' : 'none';
    }

    async _fetchBooru() {
        if (this._isFetching) return;
        const input = this._modal?.querySelector('#upm-url-input');
        const url = input?.value?.trim();
        if (!url) return;

        this._isFetching = true;
        this._setStatus(this._t('admin.media_management.booru_import.fetching'));
        this._modal.querySelector('#upm-url-preview').style.display = 'none';
        this._modal.querySelector('#upm-url-apply').style.display = 'none';
        this._modal.querySelector('#upm-url-fetch').disabled = true;

        try {
            const res = await fetch('/api/booru-import/fetch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || res.statusText);
            }

            this._fetchedPost = await res.json();
            this._fetchedPost._originalUrl = url;
            this._renderPreview(this._fetchedPost);
            this._setStatus('');
        } catch (e) {
            this._setStatus(this._t(e.message), 'error');
        } finally {
            this._isFetching = false;
            const fetchBtn = this._modal?.querySelector('#upm-url-fetch');
            if (fetchBtn) fetchBtn.disabled = false;
        }
    }

    // ==================== Tag helpers ====================

    _sortPostTags(tags) {
        const order = { artist: 1, copyright: 2, character: 3, general: 4, meta: 5 };
        return [...tags].sort((a, b) => {
            const catA = order[a.category] || 4;
            const catB = order[b.category] || 4;
            if (catA !== catB) return catA - catB;
            return a.name.localeCompare(b.name);
        });
    }

    _renderDropdownTag(tag, colorClass) {
        return `
            <div class="custom-select booru-tag-select inline-block align-middle" data-value="${tag.category}" data-tag="${this._escapeHtml(tag.name)}">
                <div class="custom-select-trigger tag-text tag ${colorClass} cursor-pointer select-none" style="display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;">
                    <span class="text-xs">${this._escapeHtml(tag.name)}</span>
                    <span class="custom-select-value" style="display: none;"></span>
                    <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block;"><polyline points="6 9 12 15 18 9"></polyline></svg>
                </div>
                <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50 min-w-[100px]">
                    <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="general">General</div>
                    <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="artist">Artist</div>
                    <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="character">Character</div>
                    <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="copyright">Copyright</div>
                    <div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="meta">Meta</div>
                </div>
            </div>
        `;
    }

    _getTagsText(tags) {
        return this._sortPostTags(tags).map(t => t.name).join(' ');
    }

    // ==================== Preview ====================

    _renderPreview(post) {
        const preview = this._modal.querySelector('#upm-url-preview');
        if (!preview) return;

        const sortedTags = this._sortPostTags(post.tags || []);
        const unconfirmedTags = sortedTags.filter(t => t.is_new && !t.user_assigned);
        const categorizedTags = sortedTags.filter(t => !t.is_new || t.user_assigned);

        const tagsByCategory = {};
        for (const tag of categorizedTags) {
            if (!tagsByCategory[tag.category]) tagsByCategory[tag.category] = [];
            tagsByCategory[tag.category].push(tag);
        }

        const categoryOrder = ['artist', 'copyright', 'character', 'general', 'meta'];
        let tagCategoryHtml = '';

        if (unconfirmedTags.length > 0) {
            tagCategoryHtml += `
                <div class="flex flex-wrap gap-1 w-full mb-3 pb-2 border-b">
                    ${unconfirmedTags.map(t => this._renderDropdownTag(t, 'grayscale ' + t.category)).join('')}
                </div>
            `;
        }

        for (const cat of categoryOrder) {
            const catTags = tagsByCategory[cat];
            if (catTags && catTags.length > 0) {
                tagCategoryHtml += `
                    <div class="flex flex-wrap gap-1 w-full">
                        ${catTags.map(t => t.is_new
                    ? this._renderDropdownTag(t, cat)
                    : `<span class="text-xs tag-text tag ${cat}">${this._escapeHtml(t.name)}</span>`
                ).join('')}
                    </div>
                `;
            }
        }

        const tagsText = this._getTagsText(post.tags || []);

        // Resolution comparison
        const cw = this.currentMedia?.width ?? 0;
        const ch = this.currentMedia?.height ?? 0;
        let resolutionHtml = '';
        let autoCheckFile = false;

        if (post.width && post.height) {
            if (post.width > cw || post.height > ch) {
                resolutionHtml = `<span class="text-success">${this._t('modal.update_post.resolution_upgrade', { w: post.width, h: post.height, cw, ch })}</span>`;
                autoCheckFile = true;
            } else if (post.width === cw && post.height === ch) {
                resolutionHtml = `<span class="text-secondary">${this._t('modal.update_post.resolution_same', { w: post.width, h: post.height })}</span>`;
            } else {
                resolutionHtml = `<span class="text-warning">${this._t('modal.update_post.resolution_smaller', { w: post.width, h: post.height })}</span>`;
            }
        }

        preview.innerHTML = `
            <div class="bg p-4 border">
                <div class="flex flex-col sm:flex-row gap-4">
                    <!-- Thumbnail -->
                    <div class="flex-shrink-0">
                        ${post.preview_url
                ? `<img src="/api/booru-import/proxy-image?url=${encodeURIComponent(post.preview_url)}" alt="Preview"
                                    class="w-32 h-32 object-contain surface border cursor-pointer"
                                    onerror="this.style.display='none'">`
                : `<div class="w-32 h-32 surface border flex items-center justify-center text-xs text-secondary">${this._t('common.none')}</div>`
            }
                    </div>

                    <!-- Info -->
                    <div class="flex-1 min-w-0">
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs mb-3">
                            <div class="flex items-center gap-2">
                                <span class="text-secondary shrink-0">${this._t('media.info.rating')}</span>
                                <div id="upm-rating-select" class="custom-select w-32" data-value="${post.rating || 'safe'}">
                                    <div class="custom-select-trigger w-full flex items-center justify-between gap-2 px-2 py-1 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors">
                                        <span class="custom-select-value text capitalize">${post.rating || 'safe'}</span>
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
                                <span class="text-secondary shrink-0 mr-1">${this._t('media.info.source')}</span>
                                ${post.source
                ? `<strong class="truncate min-w-0 flex-1 font-normal text-right">
                                        <a href="${this._escapeHtml(post.source)}" target="_blank" class="text-primary hover:underline block truncate" title="${this._escapeHtml(post.source)}">
                                            ${this._escapeHtml(post.source)}
                                        </a>
                                       </strong>`
                : '<span class="text-secondary ml-1">...</span>'
            }
                            </div>
                            <div>
                                <span class="text-secondary">${this._t('media.info.dimensions')}</span>
                                <span class="font-medium ml-1">${post.width || '?'}x${post.height || '?'}</span>
                                ${resolutionHtml ? `<span class="ml-1 text-xs">${resolutionHtml}</span>` : ''}
                            </div>
                            ${post.file_size ? `
                            <div>
                                <span class="text-secondary">${this._t('media.info.size')}</span>
                                <span class="font-medium ml-1">${this._formatFileSize(post.file_size)}</span>
                            </div>` : ''}
                        </div>

                        <div class="mb-3">
                            <div class="text-xs font-bold mb-1">${this._t('common.tags')}</div>
                            <div class="p-2 surface border flex flex-wrap gap-2">
                                ${tagCategoryHtml || `<span class="text-xs text-secondary">${this._t('common.no_tags')}</span>`}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Editable tags input -->
                <div class="mt-3 relative">
                    <label class="text-xs font-bold block mb-1">${this._t('media.tags.edit_tags')}</label>
                    <div id="upm-tags-input"
                        class="bg w-full px-3 py-2 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                        contenteditable="true"
                        style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;">${this._escapeHtml(tagsText)}</div>
                </div>

                <!-- Update options -->
                <div class="mt-3 flex flex-col gap-1.5">
                    <p class="text-xs font-bold text-secondary uppercase tracking-wide mb-1">
                        ${this._t('modal.update_post.what_to_update')}
                    </p>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                        ${this._checkboxRow('upm-upd-tags', this._t('common.tags'), true)}
                        ${this._checkboxRow('upm-upd-rating', this._t('media.info.rating'), true)}
                        ${this._checkboxRow('upm-upd-file', this._t('modal.update_post.update_file'), autoCheckFile)}
                        ${this._checkboxRow('upm-upd-source', this._t('media.info.source_url'), true)}
                        ${this._checkboxRow('upm-upd-desc', this._t('media.info.description'), false)}
                        ${this._checkboxRow('upm-upd-filename', this._t('media.info.filename'), false)}
                    </div>
                </div>

                <!-- Tag mode -->
                <div id="upm-tag-mode-section" class="mt-3">
                    <p class="text-xs font-bold text-secondary uppercase tracking-wide mb-2">
                        ${this._t('modal.update_post.tag_mode')}
                    </p>
                    <div class="grid grid-cols-1 gap-2">
                        <label>
                            <input type="radio" name="upm-tag-mode" id="upm-merge-tags" class="hidden" checked>
                            <span class="block text-center px-3 py-1 border cursor-pointer bg hover:border-primary transition-colors text-xs">
                                ${this._t('modal.update_post.merge_tags')}
                            </span>
                        </label>
                        <label>
                            <input type="radio" name="upm-tag-mode" id="upm-replace-tags" class="hidden">
                            <span class="block text-center px-3 py-1 border cursor-pointer bg hover:border-primary transition-colors text-xs">
                                ${this._t('modal.update_post.replace_tags')}
                            </span>
                        </label>
                    </div>
                </div>
            </div>
        `;

        preview.style.display = '';

        this._modal.querySelector('#upm-url-apply').style.display = '';

        const ratingSelectEl = preview.querySelector('#upm-rating-select');
        if (ratingSelectEl && typeof CustomSelect !== 'undefined') {
            new CustomSelect(ratingSelectEl);
        }

        const tagSelects = preview.querySelectorAll('.booru-tag-select');
        if (typeof CustomSelect !== 'undefined') {
            tagSelects.forEach(el => {
                new CustomSelect(el);
                el.addEventListener('change', (e) => {
                    const tagName = el.dataset.tag;
                    const newCategory = e.detail.value;
                    const tag = this._fetchedPost.tags.find(t => t.name === tagName);
                    if (tag) {
                        tag.category = newCategory;
                        tag.user_assigned = true;
                        this._renderPreview(this._fetchedPost);
                    }
                });
            });
        }

        const tagsInput = preview.querySelector('#upm-tags-input');
        if (tagsInput && typeof TagInputHelper !== 'undefined') {
            const helper = new TagInputHelper();
            helper.setupTagInput(tagsInput, 'upm-tags', { validateDelay: 500 });
            setTimeout(() => helper.validateAndStyleTags(tagsInput), 200);
        }
        if (tagsInput && typeof TagAutocomplete !== 'undefined') {
            new TagAutocomplete(tagsInput, {
                multipleValues: true,
                allowCreate: true,
                containerClasses: 'surface border border-color shadow-lg z-50',
            });
        }

        const tagsChk = preview.querySelector('#upm-upd-tags');
        const tagModeSection = this._modal.querySelector('#upm-tag-mode-section');
        if (tagsChk && tagModeSection) {
            tagModeSection.style.display = tagsChk.checked ? '' : 'none';
            tagsChk.addEventListener('change', () => {
                tagModeSection.style.display = tagsChk.checked ? '' : 'none';
            });
        }

        const thumb = preview.querySelector('img');
        if (thumb && post.file_url) {
            const isVideo = /\.(mp4|webm|mov|avi|mkv)$/i.test(post.file_url);
            thumb.addEventListener('click', () => {
                this._openFullscreen(
                    `/api/booru-import/proxy-image?url=${encodeURIComponent(post.file_url)}`,
                    isVideo
                );
            });
        }
    }

    // ==================== Apply ====================

    async _applyFromUrl() {
        if (this._isApplying || !this._fetchedPost) return;

        const q = (id) => this._modal?.querySelector(`#${id}`);

        const updateTags = q('upm-upd-tags')?.checked ?? false;
        const mergeTags = q('upm-merge-tags')?.checked ?? true;
        const updateRating = q('upm-upd-rating')?.checked ?? false;
        const updateFile = q('upm-upd-file')?.checked ?? false;
        const updateSource = q('upm-upd-source')?.checked ?? false;
        const updateDesc = q('upm-upd-desc')?.checked ?? false;
        const updateFilename = q('upm-upd-filename')?.checked ?? false;

        if (!updateTags && !updateRating && !updateFile && !updateSource && !updateDesc && !updateFilename) {
            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(this._t('modal.update_post.error_no_changes'), 'error');
            }
            return;
        }

        this._isApplying = true;
        const applyBtn = q('upm-url-apply');
        if (applyBtn) {
            applyBtn.disabled = true;
            applyBtn.textContent = this._t('modal.update_post.applying');
        }

        const tagsInput = q('upm-tags-input');
        let editedTags = [];
        if (tagsInput) {
            if (typeof TagInputHelper !== 'undefined') {
                const helper = new TagInputHelper();
                const text = helper.getPlainTextFromDiv(tagsInput);
                editedTags = text.split(/\s+/).filter(t => t.length > 0);
            } else {
                const text = tagsInput.innerText || tagsInput.textContent || '';
                editedTags = text.trim().split(/\s+/).filter(t => t.length > 0);
            }
        }

        const categoryHints = {};
        if (this._fetchedPost.tags) {
            const editedSet = new Set(editedTags.map(t => t.toLowerCase()));
            for (const tag of this._fetchedPost.tags) {
                if (editedSet.has(tag.name.toLowerCase())) {
                    categoryHints[tag.name.toLowerCase()] = tag.category;
                }
            }
        }

        const ratingSelectEl = this._modal?.querySelector('#upm-rating-select');
        const rating = ratingSelectEl ? ratingSelectEl.dataset.value : this._fetchedPost.rating;

        const post = this._fetchedPost;

        const body = {
            update_tags: updateTags,
            tags: updateTags ? editedTags : null,
            category_hints: updateTags ? categoryHints : null,
            merge_tags: mergeTags,
            update_rating: updateRating,
            rating: updateRating ? (rating || null) : null,
            update_file: updateFile,
            file_url: updateFile ? (post.file_url || null) : null,
            update_source: updateSource,
            source: updateSource ? (post.source || null) : null,
            update_description: updateDesc,
            description: updateDesc ? (post.description || null) : null,
            update_filename: updateFilename,
            filename: updateFilename ? (post.filename || null) : null
        };

        try {
            const res = await fetch(`/api/media/${this.mediaId}/update-from-source`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                const detail = err.detail || res.statusText;

                if (res.status === 409) {
                    if (detail.includes('identical')) {
                        throw new Error(this._t('modal.update_post.error_identical_file'));
                    }
                    throw new Error(this._t('modal.update_post.error_duplicate_file'));
                }
                throw new Error(detail);
            }

            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(this._t('modal.update_post.success'), 'success');
            }

            this.hide();
            document.body.style.overflow = '';
            setTimeout(() => window.location.reload(), 800);
        } catch (e) {
            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(this._t(e.message), 'error');
            }
        } finally {
            this._isApplying = false;
            if (applyBtn) {
                applyBtn.disabled = false;
                applyBtn.textContent = this._t('modal.update_post.apply');
            }
        }
    }
}
