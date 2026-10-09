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
                    <h2 class="text-base sm:text-lg font-bold truncate">${window.i18n.t('modal.update_post.from_url')}</h2>
                </div>

                <!-- Body -->
                <div class="flex-1 overflow-auto p-4">
                    <!-- URL input -->
                    <div class="flex gap-2 mb-3">
                        <input id="upm-url-input" type="url"
                            class="flex-1 bg px-3 py-2 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                            placeholder="${window.i18n.t('common.url_placeholder')}"
                            value="${escapeHtml(this.currentMedia?.source || '')}">
                        <button id="upm-url-fetch" class="btn-primary whitespace-nowrap cursor-pointer">
                            ${window.i18n.t('admin.media_management.url_import.fetch')}
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
                            <button id="upm-url-apply" class="flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn-primary text-sm font-medium cursor-pointer" style="display:none;">
                                ${window.i18n.t('modal.update_post.apply')}
                            </button>
                            <button id="upm-url-cancel" class="flex-1 sm:flex-none min-h-[48px] sm:min-h-0 px-5 py-3 sm:py-2 btn text-sm font-medium cursor-pointer">
                                ${window.i18n.t('common.cancel')}
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
        this._setStatus(window.i18n.t('admin.media_management.url_import.fetching'));
        this._modal.querySelector('#upm-url-preview').style.display = 'none';
        this._modal.querySelector('#upm-url-apply').style.display = 'none';
        this._modal.querySelector('#upm-url-fetch').disabled = true;

        try {
            const res = await fetch('/api/media/url-import/fetch', {
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
            this._setStatus(window.i18n.t(e.message), 'error');
        } finally {
            this._isFetching = false;
            const fetchBtn = this._modal?.querySelector('#upm-url-fetch');
            if (fetchBtn) fetchBtn.disabled = false;
        }
    }

    // ==================== Tag helpers ====================

    _sortPostTags(tags) {
        if (!tags) return [];
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
            <div class="custom-select booru-tag-select inline-block align-middle" data-value="${tag.category}" data-tag="${escapeHtml(tag.name)}">
                <div class="custom-select-trigger tag-text tag ${colorClass} cursor-pointer select-none" style="display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;">
                    <span class="text-xs">${escapeHtml(tag.name)}</span>
                    <span class="custom-select-value" style="display: none;"></span>
                    ${window.Icons.chevronDown({ size: 10, class: 'custom-select-arrow flex-shrink-0 transition-transform duration-200', style: 'display: block;' })}
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

    _truncateUrl(url, maxLen = 30) {
        try {
            const parsed = new URL(url);
            const display = parsed.hostname + parsed.pathname;
            return display.length > maxLen ? display.substring(0, maxLen) + '…' : display;
        } catch {
            return url.length > maxLen ? url.substring(0, maxLen) + '…' : url;
        }
    }

    // ==================== Preview ====================

    _renderPreview(post) {
        const preview = this._modal.querySelector('#upm-url-preview');
        if (!preview) return;

        // Resolution comparison
        const cw = this.currentMedia?.width ?? 0;
        const ch = this.currentMedia?.height ?? 0;
        let resolutionHtml = '';
        let autoCheckFile = false;

        if (post.width && post.height) {
            if (post.width > cw || post.height > ch) {
                resolutionHtml = `<span class="text-success">${window.i18n.t('modal.update_post.resolution_upgrade', { w: post.width, h: post.height, cw, ch })}</span>`;
                autoCheckFile = true;
            } else if (post.width === cw && post.height === ch) {
                resolutionHtml = `<span class="text-secondary">${window.i18n.t('modal.update_post.resolution_same', { w: post.width, h: post.height })}</span>`;
            } else {
                resolutionHtml = `<span class="text-warning">${window.i18n.t('modal.update_post.resolution_smaller', { w: post.width, h: post.height })}</span>`;
            }
        }

        const proxyUrl = `/api/media/url-import/proxy?url=${encodeURIComponent(post.file_url)}`;
        const previewImgUrl = post.preview_url ? `/api/media/url-import/proxy?url=${encodeURIComponent(post.preview_url)}` : proxyUrl;

        let previewHtml = '';
        if (post.is_video && !post.preview_url) {
            previewHtml = `<div class="w-32 h-32 surface border relative overflow-hidden" style="background-image: linear-gradient(90deg, var(--surface) 0%, color-mix(in srgb, var(--surface-light), var(--surface) 40%) 50%, var(--surface) 100%); background-size: 200% 100%; animation: skeleton-wave 2s infinite linear;" id="upm-thumb-wrap">
                    <video src="${previewImgUrl}" class="w-full h-full object-contain cursor-pointer opacity-0 transition-opacity duration-300" muted
                        onloadeddata="this.style.opacity='1'; this.closest('#upm-thumb-wrap').style.animation='none'; this.closest('#upm-thumb-wrap').style.backgroundImage='none';"
                        onerror="this.style.display='none'; this.closest('#upm-thumb-wrap').style.animation='none'; this.closest('#upm-thumb-wrap').style.backgroundImage='none';"></video>
               </div>`;
        } else {
            previewHtml = `<div class="w-32 h-32 surface border relative overflow-hidden" style="background-image: linear-gradient(90deg, var(--surface) 0%, color-mix(in srgb, var(--surface-light), var(--surface) 40%) 50%, var(--surface) 100%); background-size: 200% 100%; animation: skeleton-wave 2s infinite linear;" id="upm-thumb-wrap">
                    <img src="${previewImgUrl}" alt="Preview" class="w-full h-full object-contain cursor-pointer opacity-0 transition-opacity duration-300"
                        onload="this.style.opacity='1'; this.closest('#upm-thumb-wrap').style.animation='none'; this.closest('#upm-thumb-wrap').style.backgroundImage='none';"
                        onerror="this.style.display='none'; this.closest('#upm-thumb-wrap').style.animation='none'; this.closest('#upm-thumb-wrap').style.backgroundImage='none';">
               </div>`;
        }

        let infoHtml = '';
        let tagsEditorHtml = '';

        if (post.is_booru_post) {
            infoHtml = `
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs mb-3">
                    <div class="flex items-center gap-2">
                        <span class="text-secondary shrink-0">${window.i18n.t('media.info.rating')}</span>
                        <div id="upm-rating-select" class="custom-select w-32" data-value="${post.rating || 'safe'}">
                            <div class="custom-select-trigger w-full flex items-center justify-between gap-2 px-2 py-1 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors">
                                <span class="custom-select-value text capitalize">${post.rating || 'safe'}</span>
                                ${window.Icons.selectArrow({ size: 10, class: 'custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary' })}
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
                                <a href="${escapeHtml(post.source)}" target="_blank" class="text-primary hover:underline block truncate" title="${escapeHtml(post.source)}">
                                    ${escapeHtml(post.source)}
                                </a>
                               </strong>`
                    : '<span class="text-secondary ml-1">...</span>'
                }
                    </div>
                    <div>
                        <span class="text-secondary">${window.i18n.t('media.info.dimensions')}</span>
                        <span class="font-medium ml-1">${post.width || '?'}x${post.height || '?'}</span>
                        ${resolutionHtml ? `<span class="ml-1 text-xs">${resolutionHtml}</span>` : ''}
                    </div>
                    ${post.file_size ? `
                    <div>
                        <span class="text-secondary">${window.i18n.t('media.info.size')}</span>
                        <span class="font-medium ml-1">${formatFileSize(post.file_size, { mode: 'compact', fallback: '-' })}</span>
                    </div>` : ''}
                </div>
                <div class="mb-3">
                    <div class="text-xs font-bold mb-1">${window.i18n.t('common.tags')}</div>
                    <div id="upm-tags-preview" class="p-2 surface border flex flex-wrap gap-2">
                    </div>
                </div>
            `;

            const tagsText = this._getTagsText(post.tags || []);
            tagsEditorHtml = `
                <div class="mt-3 relative">
                    <label class="text-xs font-bold block mb-1">${window.i18n.t('media.tags.edit_tags')}</label>
                    <div id="upm-tags-input"
                        class="bg w-full px-3 py-2 border text-xs focus:outline-none focus:border-primary hover:border-primary transition-colors"
                        contenteditable="true"
                        style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;">${escapeHtml(tagsText)}</div>
                </div>
            `;
        } else {
            infoHtml = `
                <div class="flex-1 min-w-0 text-xs space-y-2">
                    <div><strong>${window.i18n.t('media.info.filename')}:</strong> ${escapeHtml(post.filename)}</div>
                    <div><strong>${window.i18n.t('media.info.type')}:</strong> ${escapeHtml(post.content_type)}</div>
                    <div><strong>${window.i18n.t('media.info.size')}:</strong> ${formatFileSize(post.file_size, { mode: 'compact', fallback: '-' })}</div>
                    <div class="break-all"><strong>${window.i18n.t('media.info.source')}:</strong> ${escapeHtml(this._truncateUrl(post.file_url, 80))}</div>
                </div>
            `;
        }

        preview.innerHTML = `
            <div class="bg p-4 border">
                <div class="flex flex-col sm:flex-row gap-4">
                    <div class="flex-shrink-0">
                        ${previewHtml}
                    </div>
                    <div class="flex-1 min-w-0">
                        ${infoHtml}
                    </div>
                </div>
                ${tagsEditorHtml}


                <!-- Update options -->
                <div class="mt-3 flex flex-col gap-1.5">
                    <p class="text-xs font-bold text-secondary uppercase tracking-wide mb-1">
                        ${window.i18n.t('modal.update_post.what_to_update')}
                    </p>
                    <div class="grid grid-cols-2 md:grid-cols-3 gap-2">
                        ${post.is_booru_post ? this._checkboxRow('upm-upd-tags', window.i18n.t('common.tags'), true) : ''}
                        ${post.is_booru_post ? this._checkboxRow('upm-upd-rating', window.i18n.t('media.info.rating'), true) : ''}
                        ${this._checkboxRow('upm-upd-file', window.i18n.t('modal.update_post.update_file'), autoCheckFile)}
                        ${this._checkboxRow('upm-upd-source', window.i18n.t('media.info.source_url'), true)}
                        ${post.is_booru_post ? this._checkboxRow('upm-upd-desc', window.i18n.t('common.description'), false) : ''}
                        ${this._checkboxRow('upm-upd-filename', window.i18n.t('media.info.filename'), false)}
                    </div>
                </div>

                <!-- Tag mode -->
                ${post.is_booru_post ? `
                <div id="upm-tag-mode-section" class="mt-3">
                    <p class="text-xs font-bold text-secondary uppercase tracking-wide mb-2">
                        ${window.i18n.t('modal.update_post.tag_mode')}
                    </p>
                    <div class="grid grid-cols-1 gap-2">
                        <label>
                            <input type="radio" name="upm-tag-mode" id="upm-merge-tags" class="hidden" checked>
                            <span class="block text-center px-3 py-1 border cursor-pointer bg hover:border-primary transition-colors text-xs">
                                ${window.i18n.t('modal.update_post.merge_tags')}
                            </span>
                        </label>
                        <label>
                            <input type="radio" name="upm-tag-mode" id="upm-replace-tags" class="hidden">
                            <span class="block text-center px-3 py-1 border cursor-pointer bg hover:border-primary transition-colors text-xs">
                                ${window.i18n.t('modal.update_post.replace_tags')}
                            </span>
                        </label>
                    </div>
                </div>` : ''}
            </div>
        `;

        preview.style.display = '';

        this._modal.querySelector('#upm-url-apply').style.display = '';

        if (post.is_booru_post) {
            const tagsPreviewContainer = preview.querySelector('#upm-tags-preview');
            if (tagsPreviewContainer && typeof TagPreview !== 'undefined') {
                this.tagPreview = new TagPreview(tagsPreviewContainer, {
                    allowCategoryChange: true,
                    onCategoryChange: (tag, newCategory) => {
                        if (this._fetchedPost && this._fetchedPost.tags) {
                            const existing = this._fetchedPost.tags.find(t => t.name.toLowerCase() === tag.name.toLowerCase());
                            if (existing) {
                                existing.category = newCategory;
                                existing.user_assigned = true;
                                existing.is_new = true;
                            }
                        }
                    }
                });
                this.tagPreview.setTags(post.tags);
            }

            const ratingSelectEl = preview.querySelector('#upm-rating-select');
            if (ratingSelectEl && typeof CustomSelect !== 'undefined') {
                new CustomSelect(ratingSelectEl);
            }

            const tagsInput = preview.querySelector('#upm-tags-input');
            if (tagsInput && typeof TagInputHelper !== 'undefined') {
                this.tagInputHelper = new TagInputHelper();
                this.tagInputHelper.setupTagInput(tagsInput, 'upm-tags', {
                    validateDelay: 500,
                    onValidate: () => {
                        if (this._fetchedPost) {
                            this.updateTagsPreview();
                        }
                    }
                });
                setTimeout(() => this.tagInputHelper.validateAndStyleTags(tagsInput), 200);
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
        }

        const thumb = preview.querySelector('img, video');
        if (thumb && post.file_url) {
            const proxyUrl = `/api/media/url-import/proxy?url=${encodeURIComponent(post.file_url)}`;
            const isVideo = post.is_video || (post.is_booru_post && window.FormatRegistry.isVideo(post.file_url));
            thumb.style.cursor = 'pointer';
            thumb.addEventListener('click', () => {
                this._openFullscreen(proxyUrl, isVideo);
            });
        }
    }

    updateTagsPreview() {
        if (!this.tagPreview || !this._fetchedPost) return;
        const tagsInput = this._modal.querySelector('#upm-tags-input');

        let currentTagNames = [];
        if (this.tagInputHelper) {
            const text = this.tagInputHelper.getPlainTextFromDiv(tagsInput);
            currentTagNames = text.split(/\s+/).filter(t => t.length > 0);
        } else {
            const text = tagsInput.innerText || tagsInput.textContent || '';
            currentTagNames = text.trim().split(/\s+/).filter(t => t.length > 0);
        }

        const newTagsList = currentTagNames.map(n => {
            const existing = (this._fetchedPost.tags || []).find(t => t.name.toLowerCase() === n.toLowerCase());
            return existing ? existing : { name: n };
        });

        this.tagPreview.setTags(newTagsList);
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
                app.showNotification(window.i18n.t('modal.update_post.error_no_changes'), 'error');
            }
            return;
        }

        this._isApplying = true;
        const applyBtn = q('upm-url-apply');
        if (applyBtn) {
            applyBtn.disabled = true;
            applyBtn.textContent = window.i18n.t('modal.update_post.applying');
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
                        throw new Error(window.i18n.t('modal.update_post.error_identical_file'));
                    }
                    throw new Error(window.i18n.t('modal.update_post.error_duplicate_file'));
                }
                throw new Error(detail);
            }

            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(window.i18n.t('modal.update_post.success'), 'success');
            }

            this.hide();
            document.body.style.overflow = '';
            setTimeout(() => window.location.reload(), 800);
        } catch (e) {
            if (typeof app !== 'undefined' && app.showNotification) {
                app.showNotification(window.i18n.t(e.message), 'error');
            }
        } finally {
            this._isApplying = false;
            if (applyBtn) {
                applyBtn.disabled = false;
                applyBtn.textContent = window.i18n.t('modal.update_post.apply');
            }
        }
    }
}
