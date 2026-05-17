class TagImplicationManager {
    constructor() {
        this.form = document.getElementById('tag-implication-form');
        if (!this.form) return;

        this.tableBody = document.querySelector('#tag-implication-table tbody');
        this.targetInput = document.getElementById('tag-implication-target');
        this.impliedInput = document.getElementById('tag-implication-implies');
        this.saveBtn = this.form.querySelector('button[type="submit"]');
        this.cancelBtn = document.getElementById('tag-implication-cancel');
        this.editingId = null;
        this.tagInputHelper = new TagInputHelper();

        this.init();
    }

    init() {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));

        if (this.cancelBtn) {
            this.cancelBtn.addEventListener('click', () => this.resetForm());
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
                    onSelect: () => {
                        setTimeout(() => this.tagInputHelper.validateAndStyleTags(this.impliedInput), 100);
                    }
                });
            }
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

    async loadImplications() {
        if (!this.tableBody) return;

        try {
            const response = await fetch('/api/tag-implications/');
            if (!response.ok) throw new Error('Failed to load');
            const implications = await response.json();
            this.renderTable(implications);
        } catch (e) {
            console.error('Error loading tag implications:', e);
            this.tableBody.innerHTML = `<tr><td colspan="3" class="text-center py-2 text-secondary text-xs">${window.i18n.t('admin.settings.booru_config.no_configs')}</td></tr>`;
        }
    }

    // Build the display string for the target column.
    // Use target_tag_patterns when available since it contains all tokens (concrete and wildcards).
    // Fallback to target_tags for implications that don't have patterns.
    _buildTargetDisplay(imp) {
        if (imp.target_tag_patterns && imp.target_tag_patterns.length > 0) {
            return imp.target_tag_patterns.map(p => this.escapeHtml(p)).join(' ');
        }
        return imp.target_tags.map(t => this.escapeHtml(t.name)).join(' ');
    }

    // Build the raw (unescaped) string used to populate the edit form.
    _buildTargetRaw(imp) {
        if (imp.target_tag_patterns && imp.target_tag_patterns.length > 0) {
            return imp.target_tag_patterns.join(' ');
        }
        return imp.target_tags.map(t => t.name).join(' ');
    }

    renderTable(implications) {
        if (implications.length === 0) {
            this.tableBody.innerHTML = `<tr><td colspan="3" class="text-center py-2 text-secondary text-xs">${window.i18n.t('admin.settings.booru_config.no_configs')}</td></tr>`;
            return;
        }

        this.tableBody.innerHTML = implications.map(imp => `
            <tr class="border-b last:border-b-0 hover:surface transition-colors">
                <td class="py-2 px-3 text-xs font-mono">${this._buildTargetDisplay(imp)}</td>
                <td class="py-2 px-3 text-xs font-mono">${imp.implied_tags.map(t => this.escapeHtml(t.name)).join(' ')}</td>
                <td class="py-2 px-3 text-xs text-right whitespace-nowrap">
                    <button class="text-primary hover:opacity-70 mr-2" title="${window.i18n.t('common.edit')}"
                        onclick="window.tagImplicationManager.editImplication(${imp.id}, '${this.escapeAttr(this._buildTargetRaw(imp))}', '${this.escapeAttr(imp.implied_tags.map(t => t.name).join(' '))}')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                        </svg>
                    </button>
                    <button class="text-danger hover:opacity-70" title="${window.i18n.t('common.delete')}"
                        onclick="window.tagImplicationManager.deleteImplication(${imp.id})">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
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

        const isWildcard = t => t.includes('*') || t.includes('?');
        const concreteTags = allTargetTokens.filter(t => !isWildcard(t));
        const targetTagPatterns = allTargetTokens;

        const url = this.editingId
            ? `/api/tag-implications/${this.editingId}`
            : '/api/tag-implications/';
        const method = this.editingId ? 'PUT' : 'POST';

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

            this.showStatus(window.i18n.t('notifications.save_success'), 'success');
            this.resetForm();
            this.loadImplications();
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
                    this.loadImplications();
                } catch (e) {
                    this.showStatus(e.message, 'error');
                }
            }
        }).show();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Escape a string for use inside an HTML attribute (single-quoted context).
    escapeAttr(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/'/g, '&#039;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }
}

if (document.getElementById('tag-implication-form')) {
    window.tagImplicationManager = new TagImplicationManager();
}
