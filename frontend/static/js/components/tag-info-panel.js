class TagInfoPanel {
    static KNOWN_CATEGORIES = ['general', 'artist', 'character', 'copyright', 'meta'];

    static safeCategory(category) {
        return TagInfoPanel.KNOWN_CATEGORIES.includes(category) ? category : 'general';
    }

    constructor(tag, detailsEl, options = {}) {
        this.tag = tag;
        this.detailsEl = detailsEl;
        this.options = options; // { onUpdate }
        this.loaded = false;
        this.relatedData = null;
        this.implicationsData = null;
        this.showAllRelated = false;
        this.autocompletes = [];
    }

    async loadAndRender() {
        if (this.loaded) {
            this.render();
            return;
        }

        this.detailsEl.innerHTML = `
            <div class="py-4 text-center text-secondary">
                <div class="spinner inline-block"></div>
            </div>
        `;

        try {
            const relatedPromise = fetch(`/api/tags/${encodeURIComponent(this.tag.name)}/related?limit=20`)
                .then(r => r.ok ? r.json() : [])
                .catch(() => []);

            const implicationsPromise = (app.isAdminMode)
                ? fetch(`/api/tag-implications/?tag=${encodeURIComponent(this.tag.name)}`)
                    .then(r => r.ok ? r.json() : [])
                    .catch(() => [])
                : Promise.resolve([]);

            const [relData, impData] = await Promise.all([relatedPromise, implicationsPromise]);
            this.relatedData = Array.isArray(relData) ? relData : [];
            this.implicationsData = Array.isArray(impData) ? impData : [];
            this.loaded = true;
            this.render();
        } catch (err) {
            console.error('Error loading tag details:', err);
            this.detailsEl.innerHTML = `<p class="text-xs text-danger p-3">${window.i18n.t('tags_gallery.load_details_failed')}</p>`;
        }
    }

    destroy() {
        this.autocompletes.forEach(ac => {
            if (ac && typeof ac.destroy === 'function') {
                ac.destroy();
            }
        });
        this.autocompletes = [];
    }

    render() {
        this.destroy();
        this.detailsEl.innerHTML = '';

        if (app.isAdminMode) {
            this._renderMetadataRow();
            this._renderRelatedSection();
            this._renderImpliedBySection();
            this._renderImpliesSection();
            this._renderAliasSectionAdmin();
        } else {
            this._renderRelatedSection();
            this._renderImpliedBySection();
            this._renderImpliesSection();
            this._renderAliasSectionUser();
        }
    }

    _renderMetadataRow() {
        const creationDate = this.tag.created_at ? new Date(this.tag.created_at) : null;
        const creationDateStr = creationDate && !isNaN(creationDate.getTime())
            ? `${new Intl.DateTimeFormat(undefined, { dateStyle: 'short' }).format(creationDate)} ${new Intl.DateTimeFormat(undefined, { timeStyle: 'short', hour12: false }).format(creationDate)}`
            : '';

        const metaRow = document.createElement('div');
        metaRow.className = 'flex items-center justify-between text-secondary pb-1';
        metaRow.innerHTML = `
            <span class="text-xs font-mono font-bold">${window.i18n.t('media.relations.parent_id_link', { id: this.tag.id })}</span>
            <span class="text-xs font-mono font-bold">${escapeHtml(creationDateStr)}</span>
        `;
        this.detailsEl.appendChild(metaRow);
    }

    _renderRelatedSection() {
        const related = this.relatedData || [];
        const hasHiddenContent = related.length > 1;

        const row = document.createElement('div');
        row.className = 'flex items-start gap-2 flex-wrap';

        const chevronBtn = document.createElement('button');
        chevronBtn.type = 'button';
        chevronBtn.setAttribute('aria-label', window.i18n.t('tags_gallery.toggle_details'));
        if (hasHiddenContent) {
            chevronBtn.disabled = false;
            chevronBtn.className = 'p-0.5 text-secondary hover:text-primary transition-transform duration-200 cursor-pointer flex items-center justify-center shrink-0 min-h-[22px] h-[22px]';
        } else {
            chevronBtn.disabled = true;
            chevronBtn.className = 'p-0.5 text-secondary opacity-30 cursor-default flex items-center justify-center shrink-0 min-h-[22px] h-[22px]';
        }
        chevronBtn.innerHTML = window.Icons.chevronRight({ size: 14, class: 'related-chevron transition-transform duration-200' });
        const chevronSvg = chevronBtn.querySelector('.related-chevron') || chevronBtn.firstElementChild;

        const label = document.createElement('span');
        label.className = 'font-bold text-secondary shrink-0 select-none min-h-[22px] flex items-center';
        label.textContent = `${window.i18n.t('gallery.related_tags')}:`;

        const itemsContainer = document.createElement('div');
        itemsContainer.className = 'flex items-center gap-1.5 flex-wrap flex-1 min-w-0';

        let showAll = false;
        const renderItems = () => {
            itemsContainer.innerHTML = '';
            if (related.length === 0) {
                itemsContainer.innerHTML = `<span class="text-secondary italic text-xs">(${window.i18n.t('common.none')})</span>`;
                return;
            }

            const visible = showAll ? related : related.slice(0, 1);
            visible.forEach((rel) => {
                const itemSpan = document.createElement('span');
                itemSpan.className = 'inline-flex items-center gap-1 min-w-0';
                const cat = TagInfoPanel.safeCategory(rel.category);
                itemSpan.innerHTML = `
                    <a href="/?q=${encodeURIComponent(rel.name)}" class="tag ${cat} tag-text text-xs px-2 py-0.5 hover:opacity-80 transition-opacity" data-tag-rating="${rel.rating || 'none'}">${escapeHtml(rel.name)}</a>
                    <span class="text-secondary text-[11px] font-mono whitespace-nowrap">(${escapeHtml(String(rel.count))}/${escapeHtml(String(rel.cooccurrence))})</span>
                `;
                itemsContainer.appendChild(itemSpan);
            });

            if (related.length > 1) {
                const moreBtn = document.createElement('button');
                moreBtn.type = 'button';
                moreBtn.className = 'px-1.5 py-0.5 text-[10px] font-bold text-primary border border-primary/40 bg hover:border-primary transition-colors cursor-pointer shrink-0 select-none';
                const remaining = related.length - 1;
                moreBtn.textContent = showAll
                    ? `-${remaining}`
                    : `+ ${remaining}`;
                moreBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showAll = !showAll;
                    if (chevronSvg) chevronSvg.style.transform = showAll ? 'rotate(90deg)' : '';
                    renderItems();
                });
                itemsContainer.appendChild(moreBtn);
            }
        };

        if (hasHiddenContent) {
            const toggle = (e) => {
                e.stopPropagation();
                showAll = !showAll;
                if (chevronSvg) chevronSvg.style.transform = showAll ? 'rotate(90deg)' : '';
                renderItems();
            };
            chevronBtn.addEventListener('click', toggle);
            label.classList.add('cursor-pointer');
            label.addEventListener('click', toggle);
        }

        row.appendChild(chevronBtn);
        row.appendChild(label);
        row.appendChild(itemsContainer);
        renderItems();
        this.detailsEl.appendChild(row);
    }

    _renderImpliedBySection() {
        const currentLower = this.tag.name.toLowerCase();
        const implyingTags = [];
        if (this.implicationsData) {
            this.implicationsData.forEach(imp => {
                const isImplied = imp.implied_tags && imp.implied_tags.some(t => t.name.toLowerCase() === currentLower);
                if (isImplied) {
                    if (imp.target_tags) {
                        imp.target_tags.forEach(target => implyingTags.push(target));
                    }
                    if (imp.target_tag_patterns) {
                        imp.target_tag_patterns.forEach(pat => implyingTags.push({ name: pat, isPattern: true, category: 'general' }));
                    }
                }
            });
        }

        const hasHiddenContent = implyingTags.length > 1;

        const row = document.createElement('div');
        row.className = 'flex items-start gap-2 flex-wrap';

        const chevronBtn = document.createElement('button');
        chevronBtn.type = 'button';
        chevronBtn.setAttribute('aria-label', window.i18n.t('tags_gallery.toggle_details'));
        if (hasHiddenContent) {
            chevronBtn.disabled = false;
            chevronBtn.className = 'p-0.5 text-secondary hover:text-primary transition-transform duration-200 cursor-pointer flex items-center justify-center shrink-0 min-h-[22px] h-[22px]';
        } else {
            chevronBtn.disabled = true;
            chevronBtn.className = 'p-0.5 text-secondary opacity-30 cursor-default flex items-center justify-center shrink-0 min-h-[22px] h-[22px]';
        }
        chevronBtn.innerHTML = window.Icons.chevronRight({ size: 14, class: 'implied-by-chevron transition-transform duration-200' });
        const chevronSvg = chevronBtn.querySelector('.implied-by-chevron') || chevronBtn.firstElementChild;

        const label = document.createElement('span');
        label.className = 'font-bold text-secondary shrink-0 select-none min-h-[22px] flex items-center';
        label.textContent = `${window.i18n.t('tags_gallery.implied_by')}:`;

        const itemsContainer = document.createElement('div');
        itemsContainer.className = 'flex items-center gap-1.5 flex-wrap flex-1 min-w-0';

        let showAll = false;
        const renderItems = () => {
            itemsContainer.innerHTML = '';
            if (implyingTags.length === 0) {
                itemsContainer.innerHTML = `<span class="text-secondary italic text-xs">(${window.i18n.t('common.none')})</span>`;
                return;
            }

            const visible = showAll ? implyingTags : implyingTags.slice(0, 1);
            visible.forEach(t => {
                const tagEl = document.createElement('a');
                tagEl.href = `/?q=${encodeURIComponent(t.name)}`;
                tagEl.className = `tag ${TagInfoPanel.safeCategory(t.category)} tag-text text-xs px-2 py-0.5 hover:opacity-80 transition-opacity`;
                tagEl.dataset.tagRating = t.rating || 'none';
                tagEl.textContent = t.name;
                itemsContainer.appendChild(tagEl);
            });

            if (implyingTags.length > 1) {
                const moreBtn = document.createElement('button');
                moreBtn.type = 'button';
                moreBtn.className = 'px-1.5 py-0.5 text-[10px] font-bold text-primary border border-primary/40 bg hover:border-primary transition-colors cursor-pointer shrink-0 select-none';
                const remaining = implyingTags.length - 1;
                moreBtn.textContent = showAll ? `-${remaining}` : `+ ${remaining}`;
                moreBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showAll = !showAll;
                    if (chevronSvg) chevronSvg.style.transform = showAll ? 'rotate(90deg)' : '';
                    renderItems();
                });
                itemsContainer.appendChild(moreBtn);
            }
        };

        if (hasHiddenContent) {
            const toggle = (e) => {
                e.stopPropagation();
                showAll = !showAll;
                if (chevronSvg) chevronSvg.style.transform = showAll ? 'rotate(90deg)' : '';
                renderItems();
            };
            chevronBtn.addEventListener('click', toggle);
            label.classList.add('cursor-pointer');
            label.addEventListener('click', toggle);
        }

        row.appendChild(chevronBtn);
        row.appendChild(label);
        row.appendChild(itemsContainer);
        renderItems();
        this.detailsEl.appendChild(row);
    }

    _renderImpliesSection() {
        const currentLower = this.tag.name.toLowerCase();
        const impliedEntries = [];
        if (this.implicationsData) {
            this.implicationsData.forEach(imp => {
                const isTarget = imp.target_tags && imp.target_tags.some(t => t.name.toLowerCase() === currentLower);
                if (isTarget && imp.implied_tags) {
                    const isSoleRule = (imp.target_tags.length === 1) && (!imp.target_tag_patterns || imp.target_tag_patterns.length === 0);
                    imp.implied_tags.forEach(t => {
                        impliedEntries.push({
                            implicationId: imp.id,
                            tag: t,
                            totalImpliedCount: imp.implied_tags.length,
                            isSoleRule,
                            imp
                        });
                    });
                }
            });
        }

        const isAdmin = !!app.isAdminMode;
        // In admin mode, content is always expandable (hidden input or tags)
        // In non-admin mode, there is no input row, so content is hidden only if entries.length > 1
        const hasHiddenContent = isAdmin ? true : (impliedEntries.length > 1);

        // If entries === 0 in admin mode, expand by default to show the add input row
        let isExpanded = isAdmin && impliedEntries.length === 0;

        const row = document.createElement('div');
        row.className = 'space-y-1.5';

        const topRow = document.createElement('div');
        topRow.className = 'flex items-start gap-2 flex-wrap';

        const chevronBtn = document.createElement('button');
        chevronBtn.type = 'button';
        chevronBtn.setAttribute('aria-label', window.i18n.t('tags_gallery.toggle_details'));
        if (hasHiddenContent) {
            chevronBtn.disabled = false;
            chevronBtn.className = 'p-0.5 text-secondary hover:text-primary transition-transform duration-200 cursor-pointer flex items-center justify-center shrink-0 min-h-[22px] h-[22px]';
        } else {
            chevronBtn.disabled = true;
            chevronBtn.className = 'p-0.5 text-secondary opacity-30 cursor-default flex items-center justify-center shrink-0 min-h-[22px] h-[22px]';
        }
        chevronBtn.innerHTML = window.Icons.chevronRight({ size: 14, class: 'implies-chevron transition-transform duration-200' });
        const chevronSvg = chevronBtn.querySelector('.implies-chevron') || chevronBtn.firstElementChild;
        if (isExpanded && chevronSvg) {
            chevronSvg.style.transform = 'rotate(90deg)';
        }

        const label = document.createElement('span');
        label.className = 'font-bold text-secondary shrink-0 select-none min-h-[22px] flex items-center';
        label.textContent = `${window.i18n.t('admin.tags_implications.implies_tags')}:`;

        const chipsContainer = document.createElement('div');
        chipsContainer.className = 'flex items-center gap-1.5 flex-wrap flex-1 min-w-0';

        const createChip = ({ implicationId, tag: impTag, totalImpliedCount, isSoleRule, imp }) => {
            const chip = document.createElement('span');
            const cat = TagInfoPanel.safeCategory(impTag.category);
            chip.dataset.tagRating = impTag.rating || 'none';

            if (!isAdmin) {
                chip.className = `inline-flex items-center gap-1.5 tag ${cat} tag-text px-2 py-0.5 text-xs font-medium`;
                chip.innerHTML = `<a href="/?q=${encodeURIComponent(impTag.name)}" class="hover:opacity-80">${escapeHtml(impTag.name)}</a>`;
                return chip;
            }

            if (isSoleRule) {
                chip.className = `inline-flex items-center gap-1.5 tag ${cat} tag-text px-2 py-0.5 text-xs font-medium`;
                chip.innerHTML = `
                    <span>${escapeHtml(impTag.name)}</span>
                    <button type="button" class="remove-implies-btn hover:text-danger cursor-pointer p-0.5 opacity-70 hover:opacity-100 transition-opacity" title="${window.i18n.t('common.remove')}">
                        ${window.Icons.close({ size: 10 })}
                    </button>
                `;
                chip.querySelector('.remove-implies-btn').addEventListener('click', async (e) => {
                    e.stopPropagation();
                    try {
                        if (totalImpliedCount <= 1) {
                            await app.apiCall(`/api/tag-implications/${implicationId}`, { method: 'DELETE' });
                        } else {
                            const remaining = imp.implied_tags
                                .filter(it => it.name.toLowerCase() !== impTag.name.toLowerCase())
                                .map(it => it.name);
                            const targetNames = (imp.target_tags || []).map(tt => tt.name);
                            await app.apiCall(`/api/tag-implications/${implicationId}`, {
                                method: 'PUT',
                                body: JSON.stringify({
                                    target_tags: targetNames,
                                    target_tag_patterns: imp.target_tag_patterns || [],
                                    implied_tags: remaining
                                })
                            });
                        }
                        app.showNotification(window.i18n.t('tags_gallery.implication_removed'), 'success');
                        const impRes = await fetch(`/api/tag-implications/?tag=${encodeURIComponent(this.tag.name)}`);
                        const impJson = impRes.ok ? await impRes.json() : [];
                        this.implicationsData = Array.isArray(impJson) ? impJson : [];
                        this.render();
                    } catch (err) {
                        app.showNotification(err.message, 'error');
                    }
                });
            } else {
                chip.className = `inline-flex items-center gap-1.5 tag ${cat} tag-text px-2 py-0.5 text-xs font-medium opacity-80`;
                chip.title = window.i18n.t('tags_gallery.shared_rule_hint');
                chip.innerHTML = `
                    <span>${escapeHtml(impTag.name)}</span>
                    <span class="text-[10px] font-mono opacity-75">(*)</span>
                `;
            }
            return chip;
        };

        const renderChips = () => {
            chipsContainer.innerHTML = '';
            if (impliedEntries.length === 0) {
                chipsContainer.innerHTML = `<span class="text-secondary italic text-xs">(${window.i18n.t('common.none')})</span>`;
                return;
            }

            const visible = isExpanded ? impliedEntries : impliedEntries.slice(0, 1);
            visible.forEach(entry => chipsContainer.appendChild(createChip(entry)));

            if (impliedEntries.length > 1) {
                const moreBtn = document.createElement('button');
                moreBtn.type = 'button';
                moreBtn.className = 'px-1.5 py-0.5 text-[10px] font-bold text-primary border border-primary/40 bg hover:border-primary transition-colors cursor-pointer shrink-0 select-none';
                const remaining = impliedEntries.length - 1;
                moreBtn.textContent = isExpanded ? `-${remaining}` : `+ ${remaining}`;
                moreBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggleExpand();
                });
                chipsContainer.appendChild(moreBtn);
            }
        };

        let inputRow = null;
        if (isAdmin) {
            inputRow = document.createElement('div');
            inputRow.className = 'pl-5.5 relative max-w-md';
            inputRow.style.display = isExpanded ? 'block' : 'none';

            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'w-full bg px-3 py-1.5 border text-xs focus:outline-none hover:border-primary focus:border-primary transition-colors';
            input.placeholder = window.i18n.t('tags_gallery.add_implied_tag');
            input.autocomplete = 'off';
            input.spellcheck = false;

            const handleAddImplied = async () => {
                const val = input.value.trim().toLowerCase().replace(/\s+/g, '_');
                if (!val) return;
                input.value = '';
                try {
                    await app.apiCall('/api/tag-implications/', {
                        method: 'POST',
                        body: JSON.stringify({
                            target_tags: [this.tag.name],
                            implied_tags: [val]
                        })
                    });
                    app.showNotification(window.i18n.t('tags_gallery.implication_added'), 'success');
                    const impRes = await fetch(`/api/tag-implications/?tag=${encodeURIComponent(this.tag.name)}`);
                    const impJson = impRes.ok ? await impRes.json() : [];
                    this.implicationsData = Array.isArray(impJson) ? impJson : [];
                    this.render();
                } catch (err) {
                    app.showNotification(err.message, 'error');
                }
            };

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    if (input.parentNode && input.parentNode.querySelector('.tag-suggestion.selected')) {
                        return;
                    }
                    e.preventDefault();
                    handleAddImplied();
                }
            });

            inputRow.appendChild(input);

            if (typeof TagAutocomplete !== 'undefined') {
                const ac = new TagAutocomplete(input, {
                    multipleValues: false,
                    appendSpace: false,
                    allowCreate: true,
                    onSelect: () => handleAddImplied()
                });
                this.autocompletes.push(ac);
            }
        }

        const toggleExpand = () => {
            isExpanded = !isExpanded;
            if (inputRow) {
                inputRow.style.display = isExpanded ? 'block' : 'none';
            }
            if (chevronSvg) {
                chevronSvg.style.transform = isExpanded ? 'rotate(90deg)' : '';
            }
            renderChips();
        };

        if (hasHiddenContent) {
            const handleToggle = (e) => {
                e.stopPropagation();
                toggleExpand();
            };
            chevronBtn.addEventListener('click', handleToggle);
            label.classList.add('cursor-pointer');
            label.addEventListener('click', handleToggle);
        }

        topRow.appendChild(chevronBtn);
        topRow.appendChild(label);
        topRow.appendChild(chipsContainer);
        row.appendChild(topRow);
        if (inputRow) {
            row.appendChild(inputRow);
        }
        renderChips();
        this.detailsEl.appendChild(row);
    }

    _renderAliasSectionAdmin() {
        const aliases = this.tag.aliases || [];
        // If aliases === 0 in admin mode, expand by default to show the add alias input row
        let isExpanded = aliases.length === 0;

        const row = document.createElement('div');
        row.className = 'space-y-1.5';

        const topRow = document.createElement('div');
        topRow.className = 'flex items-start gap-2 flex-wrap';

        const chevronBtn = document.createElement('button');
        chevronBtn.type = 'button';
        chevronBtn.disabled = false;
        chevronBtn.setAttribute('aria-label', window.i18n.t('tags_gallery.toggle_details'));
        chevronBtn.className = 'p-0.5 text-secondary hover:text-primary transition-transform duration-200 cursor-pointer flex items-center justify-center shrink-0 min-h-[22px] h-[22px]';
        chevronBtn.innerHTML = window.Icons.chevronRight({ size: 14, class: 'alias-chevron transition-transform duration-200' });
        const chevronSvg = chevronBtn.querySelector('.alias-chevron') || chevronBtn.firstElementChild;
        if (isExpanded && chevronSvg) {
            chevronSvg.style.transform = 'rotate(90deg)';
        }

        const label = document.createElement('span');
        label.className = 'font-bold text-secondary shrink-0 select-none min-h-[22px] flex items-center cursor-pointer';
        label.textContent = `${window.i18n.t('admin.tags_management.tag_aliases')}:`;

        const chipsContainer = document.createElement('div');
        chipsContainer.className = 'flex items-center gap-1.5 flex-wrap flex-1 min-w-0';

        const createAliasChip = (alias) => {
            const chip = document.createElement('span');
            chip.className = 'inline-flex items-center gap-1.5 surface-light border px-2 py-0.5 text-xs text select-none';
            chip.innerHTML = `
                <span>${escapeHtml(alias)}</span>
                <button type="button" class="remove-alias-btn hover:text-danger cursor-pointer p-0.5 opacity-70 hover:opacity-100 transition-opacity" title="${window.i18n.t('common.remove')}">
                    ${window.Icons.close({ size: 10 })}
                </button>
            `;
            chip.querySelector('.remove-alias-btn').addEventListener('click', async (e) => {
                e.stopPropagation();
                try {
                    const fresh = await app.apiCall(`/api/admin/tags/${this.tag.id}`);
                    const updated = (fresh.aliases || []).filter(a => a.toLowerCase() !== alias.toLowerCase());
                    await app.apiCall(`/api/admin/tags/${this.tag.id}`, {
                        method: 'PUT',
                        body: JSON.stringify({
                            name: fresh.name,
                            category: fresh.category,
                            aliases: updated
                        })
                    });
                    this.tag.aliases = updated;
                    app.showNotification(window.i18n.t('tags_gallery.alias_removed', { alias }), 'success');
                    if (this.options.onUpdate) this.options.onUpdate(this.tag);
                    this.render();
                } catch (err) {
                    app.showNotification(err.message, 'error');
                }
            });
            return chip;
        };

        const renderChips = () => {
            chipsContainer.innerHTML = '';
            if (aliases.length === 0) {
                chipsContainer.innerHTML = `<span class="text-secondary italic text-xs">(${window.i18n.t('common.none')})</span>`;
                return;
            }

            const visible = isExpanded ? aliases : aliases.slice(0, 1);
            visible.forEach(alias => chipsContainer.appendChild(createAliasChip(alias)));

            if (aliases.length > 1) {
                const moreBtn = document.createElement('button');
                moreBtn.type = 'button';
                moreBtn.className = 'px-1.5 py-0.5 text-[10px] font-bold text-primary border border-primary/40 bg hover:border-primary transition-colors cursor-pointer shrink-0 select-none';
                const remaining = aliases.length - 1;
                moreBtn.textContent = isExpanded ? `-${remaining}` : `+ ${remaining}`;
                moreBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggleExpand();
                });
                chipsContainer.appendChild(moreBtn);
            }
        };

        // Input row
        const inputRow = document.createElement('div');
        inputRow.className = 'pl-5.5 relative max-w-md';
        inputRow.style.display = isExpanded ? 'block' : 'none';

        const aliasesInput = document.createElement('div');
        aliasesInput.contentEditable = 'true';
        aliasesInput.spellcheck = false;
        aliasesInput.dataset.placeholder = window.i18n.t('tags_gallery.add_alias');
        aliasesInput.className = 'w-full bg px-3 py-1.5 border text-xs min-h-[30px] focus:outline-none hover:border-primary transition-colors focus:border-primary';

        const helper = (window.app && window.app.tagInputHelper) || (typeof TagInputHelper !== 'undefined' ? new TagInputHelper() : null);
        const aliasValidationCache = new Map();

        const checkAliasConflict = async (alias) => {
            const normalized = alias.toLowerCase().trim();
            if (normalized === this.tag.name.toLowerCase() || (this.tag.aliases || []).some(a => a.toLowerCase() === normalized)) {
                return true;
            }
            if (helper) {
                return await helper.checkTagOrAliasExists(normalized);
            }
            return false;
        };

        const inputId = `tag-panel-aliases-${this.tag.id}`;
        if (helper) {
            helper.setupTagInput(aliasesInput, inputId, {
                validationCache: aliasValidationCache,
                checkFunction: checkAliasConflict,
                invertLogic: true,
                expandImplications: false
            });
        }

        const handleAddAliases = async () => {
            const text = helper ? helper.getPlainTextFromDiv(aliasesInput) : (aliasesInput.textContent || '');
            const rawTokens = text.split(/\s+/).filter(t => t.length > 0);
            if (rawTokens.length === 0) return;

            if (helper) {
                await helper.validateAndStyleTags(aliasesInput, {
                    validationCache: aliasValidationCache,
                    checkFunction: checkAliasConflict,
                    invertLogic: true
                });
            }

            const validNewAliases = [];
            let conflictFound = false;

            for (const token of rawTokens) {
                const norm = token.toLowerCase().trim();
                // In invertLogic, true means exists (conflict)
                if (aliasValidationCache.get(norm) === true) {
                    conflictFound = true;
                } else {
                    validNewAliases.push(norm);
                }
            }

            if (conflictFound || validNewAliases.length === 0) {
                aliasesInput.focus();
                app.showNotification(window.i18n.t('notifications.admin.tag_name_conflict'), 'error');
                return;
            }

            try {
                const fresh = await app.apiCall(`/api/admin/tags/${this.tag.id}`);
                const currentAliases = fresh.aliases || [];
                const updated = [...currentAliases];
                for (const a of validNewAliases) {
                    if (!updated.includes(a)) {
                        updated.push(a);
                    }
                }

                await app.apiCall(`/api/admin/tags/${this.tag.id}`, {
                    method: 'PUT',
                    body: JSON.stringify({
                        name: fresh.name,
                        category: fresh.category,
                        aliases: updated
                    })
                });

                this.tag.aliases = updated;
                for (const a of validNewAliases) {
                    aliasValidationCache.set(a, true);
                }
                aliasesInput.innerHTML = '';
                app.showNotification(window.i18n.t('tags_gallery.alias_added', { alias: validNewAliases.join(', ') }), 'success');
                if (this.options.onUpdate) this.options.onUpdate(this.tag);
                this.render();
            } catch (err) {
                app.showNotification(err.message, 'error');
            }
        };

        aliasesInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleAddAliases();
            }
        });

        inputRow.appendChild(aliasesInput);

        const toggleExpand = () => {
            isExpanded = !isExpanded;
            inputRow.style.display = isExpanded ? 'block' : 'none';
            if (chevronSvg) {
                chevronSvg.style.transform = isExpanded ? 'rotate(90deg)' : '';
            }
            renderChips();
        };

        const handleToggle = (e) => {
            e.stopPropagation();
            toggleExpand();
        };

        chevronBtn.addEventListener('click', handleToggle);
        label.addEventListener('click', handleToggle);

        topRow.appendChild(chevronBtn);
        topRow.appendChild(label);
        topRow.appendChild(chipsContainer);
        row.appendChild(topRow);
        row.appendChild(inputRow);
        renderChips();
        this.detailsEl.appendChild(row);
    }

    _renderAliasSectionUser() {
        const aliases = this.tag.aliases || [];
        const hasHiddenContent = aliases.length > 1;

        const row = document.createElement('div');
        row.className = 'flex items-start gap-2 flex-wrap';

        const chevronBtn = document.createElement('button');
        chevronBtn.type = 'button';
        chevronBtn.setAttribute('aria-label', window.i18n.t('tags_gallery.toggle_details'));
        if (hasHiddenContent) {
            chevronBtn.disabled = false;
            chevronBtn.className = 'p-0.5 text-secondary hover:text-primary transition-transform duration-200 cursor-pointer flex items-center justify-center shrink-0 min-h-[22px] h-[22px]';
        } else {
            chevronBtn.disabled = true;
            chevronBtn.className = 'p-0.5 text-secondary opacity-30 cursor-default flex items-center justify-center shrink-0 min-h-[22px] h-[22px]';
        }
        chevronBtn.innerHTML = window.Icons.chevronRight({ size: 14, class: 'alias-chevron transition-transform duration-200' });
        const chevronSvg = chevronBtn.querySelector('.alias-chevron') || chevronBtn.firstElementChild;

        const label = document.createElement('span');
        label.className = 'font-bold text-secondary shrink-0 select-none min-h-[22px] flex items-center';
        label.textContent = `${window.i18n.t('admin.tags_management.tag_aliases')}:`;

        const chipsContainer = document.createElement('div');
        chipsContainer.className = 'flex items-center gap-1.5 flex-wrap flex-1 min-w-0';

        let showAll = false;
        const renderItems = () => {
            chipsContainer.innerHTML = '';
            if (aliases.length === 0) {
                chipsContainer.innerHTML = `<span class="text-secondary italic text-xs">(${window.i18n.t('common.none')})</span>`;
                return;
            }

            const visible = showAll ? aliases : aliases.slice(0, 1);
            visible.forEach(alias => {
                const chip = document.createElement('span');
                chip.className = 'surface-light border px-2 py-0.5 text-xs text select-none';
                chip.textContent = alias;
                chipsContainer.appendChild(chip);
            });

            if (aliases.length > 1) {
                const moreBtn = document.createElement('button');
                moreBtn.type = 'button';
                moreBtn.className = 'px-1.5 py-0.5 text-[10px] font-bold text-primary border border-primary/40 bg hover:border-primary transition-colors cursor-pointer shrink-0 select-none';
                const remaining = aliases.length - 1;
                moreBtn.textContent = showAll ? `-${remaining}` : `+ ${remaining}`;
                moreBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showAll = !showAll;
                    if (chevronSvg) chevronSvg.style.transform = showAll ? 'rotate(90deg)' : '';
                    renderItems();
                });
                chipsContainer.appendChild(moreBtn);
            }
        };

        if (hasHiddenContent) {
            const toggle = (e) => {
                e.stopPropagation();
                showAll = !showAll;
                if (chevronSvg) chevronSvg.style.transform = showAll ? 'rotate(90deg)' : '';
                renderItems();
            };
            chevronBtn.addEventListener('click', toggle);
            label.classList.add('cursor-pointer');
            label.addEventListener('click', toggle);
        }

        row.appendChild(chevronBtn);
        row.appendChild(label);
        row.appendChild(chipsContainer);
        renderItems();
        this.detailsEl.appendChild(row);
    }
}

window.TagInfoPanel = TagInfoPanel;
