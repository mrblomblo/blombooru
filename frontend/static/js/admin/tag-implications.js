class TagImplicationManager {
    constructor() {
        this.form = document.getElementById('tag-implication-form');
        if (!this.form) return;

        this.tableBody = document.querySelector('#tag-implication-table tbody');
        this.tableScroller = this.tableBody ? this.tableBody.closest('.overflow-y-auto') : null;
        this.targetInput = document.getElementById('tag-implication-target');
        this.impliedInput = document.getElementById('tag-implication-implies');
        this.saveBtn = this.form.querySelector('button[type="submit"]');
        this.cancelBtn = document.getElementById('tag-implication-cancel');
        this.applyAllBtn = document.getElementById('apply-all-implications');
        this.searchBar = document.getElementById('tag-implication-search-bar');
        this.searchInput = document.getElementById('tag-implication-search');
        this.paginationContainer = document.getElementById('tag-implication-pagination');
        this.pageInfo = document.getElementById('tag-implication-page-info');
        this.prevPageBtn = document.getElementById('tag-implication-prev-page');
        this.nextPageBtn = document.getElementById('tag-implication-next-page');
        this.editingId = null;
        this.implications = [];
        this.pageSize = 50;
        this.currentPage = 1;
        this.totalCount = 0;
        this.currentSearch = '';
        this.searchDebounceTimeout = null;
        this.tagInputHelper = new TagInputHelper();

        this.init();
    }

    init() {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));

        if (this.cancelBtn) {
            this.cancelBtn.addEventListener('click', () => this.resetForm());
        }

        if (this.applyAllBtn) {
            this.applyAllBtn.addEventListener('click', () => this.handleApplyAll());
        }

        // Target input: validation + autocomplete.
        // allowWildcards: tokens containing "*" are pattern strings, not real tag names so they are exempt from the red invalid-tag highlight.
        // "?" is a valid character in real tag names so it is not treated as a wildcard.
        if (this.targetInput) {
            this.tagInputHelper.setupTagInput(this.targetInput, 'impl-target', {
                expandImplications: false,
                allowWildcards: true
            });
            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(this.targetInput, {
                    multipleValues: true,
                    allowCreate: true,
                    onSelect: () => {
                        setTimeout(() => this.tagInputHelper.validateAndStyleTags(
                            this.targetInput,
                            { allowWildcards: true }
                        ), 100);
                    }
                });
            }
        }

        // Implied input: standard tag validation + autocomplete
        if (this.impliedInput) {
            this.tagInputHelper.setupTagInput(this.impliedInput, 'impl-implied', { expandImplications: false });
            if (typeof TagAutocomplete !== 'undefined') {
                new TagAutocomplete(this.impliedInput, {
                    multipleValues: true,
                    allowCreate: true,
                    onSelect: () => {
                        setTimeout(() => this.tagInputHelper.validateAndStyleTags(this.impliedInput), 100);
                    }
                });
            }
        }

        if (this.prevPageBtn) {
            this.prevPageBtn.addEventListener('click', () => {
                if (this.currentPage > 1) {
                    this.loadImplications(this.currentPage - 1, this.currentSearch);
                }
            });
        }

        if (this.nextPageBtn) {
            this.nextPageBtn.addEventListener('click', () => {
                const maxPage = Math.ceil(this.totalCount / this.pageSize) || 1;
                if (this.currentPage < maxPage) {
                    this.loadImplications(this.currentPage + 1, this.currentSearch);
                }
            });
        }

        if (this.searchInput) {
            this.searchInput.addEventListener('input', () => {
                clearTimeout(this.searchDebounceTimeout);
                this.searchDebounceTimeout = setTimeout(() => {
                    const query = this.searchInput.value.trim();
                    this.loadImplications(1, query);
                }, 300);
            });
        }

        this.loadImplications();
    }

    showStatus(message, type = 'info') {
        if (typeof app !== 'undefined' && app.showNotification) {
            app.showNotification(message, type);
        } else {
            alert(message);
        }
    }

    async loadImplications(page = 1, search = '') {
        if (!this.tableBody) return;

        this.currentPage = page;
        this.currentSearch = search;
        const offset = (page - 1) * this.pageSize;

        try {
            const params = new URLSearchParams({
                limit: this.pageSize.toString(),
                offset: offset.toString()
            });
            if (search) {
                params.set('search', search);
            }

            const response = await fetch(`/api/tag-implications/?${params.toString()}`);
            if (!response.ok) throw new Error('Failed to load');

            const totalHeader = response.headers.get('X-Total-Count');
            if (totalHeader !== null) {
                this.totalCount = parseInt(totalHeader, 10) || 0;
            }

            const implications = await response.json();
            this.implications = implications;
            this.renderTable(implications);
            this.renderPagination();
            if (this.tableScroller) this.tableScroller.scrollTop = 0;

            // Show search bar once we know there are enough implications to warrant it
            if (this.searchBar) {
                this.searchBar.style.display = (this.totalCount >= 20 || search) ? '' : 'none';
            }
        } catch (e) {
            console.error('Error loading tag implications:', e);
            this.tableBody.innerHTML = `<tr><td colspan="3" class="text-center py-2 text-secondary text-xs">${window.i18n.t('admin.settings.booru_config.no_configs')}</td></tr>`;
            if (this.paginationContainer) this.paginationContainer.style.display = 'none';
        }
    }

    renderPagination() {
        if (!this.paginationContainer) return;

        if (this.totalCount <= this.pageSize && !this.currentSearch) {
            this.paginationContainer.style.display = 'none';
            return;
        }

        this.paginationContainer.style.display = 'flex';
        const start = this.totalCount === 0 ? 0 : (this.currentPage - 1) * this.pageSize + 1;
        const end = Math.min(this.currentPage * this.pageSize, this.totalCount);
        const maxPage = Math.ceil(this.totalCount / this.pageSize) || 1;

        if (this.pageInfo) {
            this.pageInfo.textContent = `${start}-${end} / ${this.totalCount}`;
        }

        if (this.prevPageBtn) {
            this.prevPageBtn.disabled = this.currentPage <= 1;
        }
        if (this.nextPageBtn) {
            this.nextPageBtn.disabled = this.currentPage >= maxPage;
        }
    }

    // Build the display string for the target column.
    // Use target_tag_patterns when available since it contains all tokens (concrete and wildcards).
    // Fallback to target_tags for implications that don't have patterns.
    _buildTargetDisplay(imp) {
        if (imp.target_tag_patterns && imp.target_tag_patterns.length > 0) {
            return imp.target_tag_patterns.map(p => escapeHtml(p)).join(' ');
        }
        return imp.target_tags.map(t => escapeHtml(t.name)).join(' ');
    }

    // Build the raw (unescaped) string used to populate the edit form.
    _buildTargetRaw(imp) {
        if (imp.target_tag_patterns && imp.target_tag_patterns.length > 0) {
            return imp.target_tag_patterns.join(' ');
        }
        return imp.target_tags.map(t => t.name).join(' ');
    }

    // Extract target tokens from an implication object.
    _getTargetTokens(imp) {
        if (imp.target_tag_patterns && imp.target_tag_patterns.length > 0) {
            return imp.target_tag_patterns;
        }
        if (imp.target_tags && imp.target_tags.length > 0) {
            return imp.target_tags.map(t => t.name);
        }
        return [];
    }

    // Normalize a list of tokens: trim, lowercase, deduplicate, sort.
    _normalizeTokens(tokens) {
        return Array.from(new Set(tokens.map(t => t.trim().toLowerCase()).filter(Boolean))).sort();
    }

    // Check if two collections of target tokens match.
    _areTokensEqual(tokensA, tokensB) {
        const a = this._normalizeTokens(tokensA);
        const b = this._normalizeTokens(tokensB);
        if (a.length !== b.length) return false;
        return a.every((token, idx) => token === b[idx]);
    }

    renderTable(implications) {
        if (implications.length === 0) {
            this.tableBody.innerHTML = `<tr><td colspan="3" class="text-center py-2 text-secondary text-xs">${window.i18n.t('admin.settings.booru_config.no_configs')}</td></tr>`;
            return;
        }

        this.tableBody.innerHTML = implications.map(imp => `
            <tr class="border-b last:border-b-0" style="content-visibility: auto; contain-intrinsic-size: auto 37px;">
                <td class="p-2 text-xs font-mono break-all">${this._buildTargetDisplay(imp)}</td>
                <td class="p-2 text-xs font-mono break-all">${imp.implied_tags.map(t => escapeHtml(t.name)).join(' ')}</td>
                <td class="p-2 text-xs text-right whitespace-nowrap">
                    <button class="text-primary hover:text-primary transition-colors mr-2 cursor-pointer" title="${window.i18n.t('common.edit')}"
                        onclick="window.tagImplicationManager.editImplication(${imp.id}, '${escapeAttr(this._buildTargetRaw(imp))}', '${escapeAttr(imp.implied_tags.map(t => t.name).join(' '))}')">
                        ${window.Icons.edit({ size: 14 })}
                    </button>
                    <button class="text-danger hover:text-danger transition-colors cursor-pointer" title="${window.i18n.t('common.delete')}"
                        onclick="window.tagImplicationManager.deleteImplication(${imp.id})">
                        ${window.Icons.trash({ size: 14 })}
                    </button>
                </td>
            </tr>
        `).join('');
    }

    editImplication(id, targetTags, impliedTags) {
        this.editingId = id;
        if (this.targetInput) {
            this.targetInput.textContent = targetTags;
            setTimeout(() => this.tagInputHelper.validateAndStyleTags(
                this.targetInput,
                { allowWildcards: true }
            ), 100);
        }
        if (this.impliedInput) {
            this.impliedInput.textContent = impliedTags;
            setTimeout(() => this.tagInputHelper.validateAndStyleTags(this.impliedInput), 100);
        }
        if (this.cancelBtn) this.cancelBtn.style.display = 'inline-block';
        this.form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    resetForm() {
        this.editingId = null;
        if (this.targetInput) this.targetInput.textContent = '';
        if (this.impliedInput) this.impliedInput.textContent = '';
        if (this.cancelBtn) this.cancelBtn.style.display = 'none';
    }

    async handleSubmit(e) {
        e.preventDefault();

        const targetText = this.tagInputHelper.getPlainTextFromDiv(this.targetInput).trim();
        const impliedText = this.tagInputHelper.getPlainTextFromDiv(this.impliedInput).trim();

        const allTargetTokens = targetText ? targetText.split(/\s+/).filter(t => t.length > 0) : [];
        const impliedTags = impliedText ? impliedText.split(/\s+/).filter(t => t.length > 0) : [];

        if (allTargetTokens.length === 0 || impliedTags.length === 0) {
            this.showStatus(window.i18n.t('notifications.admin.enter_at_least_one_tag'), 'error');
            return;
        }

        // Check if an existing implication already has identical target tags
        let matchingImp = (this.implications || []).find(imp => {
            if (this.editingId && imp.id === this.editingId) return false;
            return this._areTokensEqual(this._getTargetTokens(imp), allTargetTokens);
        });

        if (!matchingImp && allTargetTokens.length > 0) {
            try {
                const checkResp = await fetch(`/api/tag-implications/?search=${encodeURIComponent(allTargetTokens[0])}&limit=20`);
                if (checkResp.ok) {
                    const candidates = await checkResp.json();
                    matchingImp = candidates.find(imp => {
                        if (this.editingId && imp.id === this.editingId) return false;
                        return this._areTokensEqual(this._getTargetTokens(imp), allTargetTokens);
                    });
                }
            } catch (err) {
                console.warn('Could not check for existing matching implication:', err);
            }
        }

        if (matchingImp) {
            const existingImpliedNames = (matchingImp.implied_tags || []).map(t => t.name);
            const normalizedExistingSet = new Set(existingImpliedNames.map(t => t.toLowerCase()));
            const newUniqueImplied = Array.from(new Set(impliedTags.map(t => t.toLowerCase())));
            const missingTags = newUniqueImplied.filter(t => !normalizedExistingSet.has(t));

            if (missingTags.length === 0) {
                this.showStatus(
                    window.i18n.t('admin.tags_implications.already_exists_msg', {
                        target: this._buildTargetRaw(matchingImp)
                    }),
                    'warning'
                );
                return;
            }

            // Ask user if they want to merge the new implied tags into the existing implication
            new ModalHelper({
                id: 'merge-implication-modal',
                type: 'warning',
                title: window.i18n.t('admin.tags_implications.merge_confirm_title'),
                message: window.i18n.t('admin.tags_implications.merge_confirm_msg', {
                    target: escapeHtml(this._buildTargetRaw(matchingImp)),
                    existing: escapeHtml(existingImpliedNames.join(' ')),
                    new: escapeHtml(missingTags.join(' '))
                }),
                confirmText: window.i18n.t('admin.tags_implications.merge_confirm_btn'),
                cancelText: window.i18n.t('common.cancel'),
                confirmId: 'merge-implication-confirm-yes',
                cancelId: 'merge-implication-confirm-no',
                onConfirm: async () => {
                    const mergedImpliedTags = [...existingImpliedNames, ...missingTags];
                    await this.saveImplicationRequest(matchingImp.id, allTargetTokens, mergedImpliedTags, true);
                }
            }).show();
            return;
        }

        await this.saveImplicationRequest(this.editingId, allTargetTokens, impliedTags);
    }

    async saveImplicationRequest(id, allTargetTokens, impliedTags, isMerge = false) {
        const isWildcard = t => t.includes('*') || t.includes('?');
        const concreteTags = allTargetTokens.filter(t => !isWildcard(t));
        const targetTagPatterns = allTargetTokens;

        const url = id
            ? `/api/tag-implications/${id}`
            : '/api/tag-implications/';
        const method = id ? 'PUT' : 'POST';

        try {
            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target_tags: concreteTags,
                    target_tag_patterns: targetTagPatterns,
                    implied_tags: impliedTags
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to save');
            }

            // If we merged while editing a different entry, clean up the other entry
            if (isMerge && this.editingId && this.editingId !== id) {
                await fetch(`/api/tag-implications/${this.editingId}`, { method: 'DELETE' });
            }

            this.showStatus(window.i18n.t('notifications.save_success'), 'success');
            this.resetForm();
            this.loadImplications(this.currentPage, this.currentSearch);
            window.app.content.loadTagStats();
        } catch (e) {
            console.error('Save error:', e);
            this.showStatus(e.message, 'error');
        }
    }

    deleteImplication(id) {
        new ModalHelper({
            type: 'danger',
            title: window.i18n.t('common.delete'),
            message: window.i18n.t('notifications.delete_confirm'),
            confirmText: window.i18n.t('common.delete'),
            confirmId: 'confirm-delete-implication',
            onConfirm: async () => {
                try {
                    const response = await fetch(`/api/tag-implications/${id}`, { method: 'DELETE' });
                    if (!response.ok) throw new Error('Failed to delete');
                    this.showStatus(window.i18n.t('notifications.delete_success'), 'success');
                    if (this.editingId === id) this.resetForm();
                    this.loadImplications(this.currentPage, this.currentSearch);
                    window.app.content.loadTagStats();
                } catch (e) {
                    this.showStatus(e.message, 'error');
                }
            }
        }).show();
    }

    handleApplyAll() {
        new ModalHelper({
            type: 'warning',
            title: window.i18n.t('common.confirm_1_title'),
            message: window.i18n.t('admin.tags_implications.apply_all_confirm_1_msg'),
            confirmText: window.i18n.t('common.yes'),
            cancelText: window.i18n.t('common.no'),
            onConfirm: async () => {
                this.executeApplyAll();
            }
        }).show();
    }

    async executeApplyAll() {
        if (this.applyAllBtn) {
            this.applyAllBtn.disabled = true;
        }

        this.showStatus(window.i18n.t('admin.tags_implications.apply_all_processing'), 'info');
        try {
            const response = await fetch('/api/tag-implications/simulate-apply-all', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to apply implications');
            }

            const data = await response.json();
            const affectedMedia = data.affected_media || [];

            if (affectedMedia.length === 0) {
                this.showStatus(window.i18n.t('admin.tags_implications.apply_all_no_affected'), 'info');
                return;
            }

            if (typeof BulkManualTagEditorModal !== 'undefined') {
                const affectedIds = affectedMedia.map(m => m.media_id);
                const prefillTags = {};
                affectedMedia.forEach(m => {
                    prefillTags[m.media_id] = m.added_tags;
                });

                const modal = new BulkManualTagEditorModal({ prefillTags });
                modal.show(affectedIds);
            } else {
                this.showStatus(`Found ${affectedMedia.length} affected media items, but bulk editor is not loaded.`, 'error');
            }
        } catch (e) {
            console.error('Error applying tag implications:', e);
            this.showStatus(e.message, 'error');
        } finally {
            if (this.applyAllBtn) {
                this.applyAllBtn.disabled = false;
            }
        }
    }
}

if (document.getElementById('tag-implication-form')) {
    window.tagImplicationManager = new TagImplicationManager();
}
