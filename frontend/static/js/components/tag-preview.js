class TagPreview {
    constructor(containerElement, options = {}) {
        this.container = containerElement;
        this.options = {
            onCategoryChange: options.onCategoryChange || null,
            allowCategoryChange: options.allowCategoryChange !== false,
            resolveAliases: options.resolveAliases !== false,
            ...options
        };
        this.tags = [];
        this.customSelects = [];
    }

    async setTags(tags) {
        const seq = (this._tagUpdateSeq = (this._tagUpdateSeq || 0) + 1);

        if (!tags || tags.length === 0) {
            this.tags = [];
            this.render();
            return;
        }

        const dedupedTags = [];
        const seenNames = new Set();

        for (const t of tags) {
            if (!t || !t.name) continue;
            const lower = t.name.toLowerCase();
            if (!seenNames.has(lower)) {
                seenNames.add(lower);
                dedupedTags.push({ ...t }); // Clone to avoid mutating caller's objects
            }
        }

        if (this.options.resolveAliases) {
            try {
                const names = dedupedTags.map(t => t.name);
                const response = await fetch('/api/tags/batch-validate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ names })
                });

                if (seq !== this._tagUpdateSeq) return;

                if (response.ok) {
                    const data = await response.json();
                    const resolved = data.resolved || {};

                    for (const t of dedupedTags) {
                        const originalName = t.name.toLowerCase();
                        if (resolved[originalName] !== undefined) {
                            if (resolved[originalName] !== null) {
                                t.name = resolved[originalName].name;
                                if (resolved[originalName].category) {
                                    t.category = resolved[originalName].category;
                                }
                                t.is_new = false;
                            } else {
                                t.is_new = true;
                            }
                        }
                    }
                }
            } catch (e) {
                console.error('Failed to resolve aliases in TagPreview', e);
                if (seq !== this._tagUpdateSeq) return;
            }
        }

        // Dedupe again after alias resolution
        this.tags = [];
        const finalSeen = new Set();
        for (const t of dedupedTags) {
            const lower = t.name.toLowerCase();
            if (!finalSeen.has(lower)) {
                finalSeen.add(lower);
                this.tags.push(t);
            }
        }

        this.render();
    }

    getTags() {
        return this.tags;
    }

    static sortTags(tags) {
        const order = { artist: 1, copyright: 2, character: 3, general: 4, meta: 5 };
        return [...tags].sort((a, b) => {
            const catA = order[a.category] || 4;
            const catB = order[b.category] || 4;
            if (catA !== catB) return catA - catB;
            return (a.name || '').localeCompare(b.name || '');
        });
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    render() {
        if (!this.container) return;

        if (!this.tags || this.tags.length === 0) {
            this.container.innerHTML = `<span class="text-secondary italic text-xs">${window.i18n.t('common.none')}</span>`;
            return;
        }

        const sortedTags = TagPreview.sortTags(this.tags);
        const unconfirmedTags = sortedTags.filter(t => t.is_new && !t.user_assigned);
        const categorizedTags = sortedTags.filter(t => !t.is_new || t.user_assigned);

        const tagsByCategory = {};
        for (const tag of categorizedTags) {
            const cat = tag.category || 'general';
            if (!tagsByCategory[cat]) tagsByCategory[cat] = [];
            tagsByCategory[cat].push(tag);
        }

        const categoryOrder = ['artist', 'copyright', 'character', 'general', 'meta'];
        let html = '';

        if (unconfirmedTags.length > 0) {
            html += `
                <div class="flex flex-wrap gap-1 w-full mb-2 pb-2 border-b max-w-full min-w-0">
                    ${unconfirmedTags.map(t => this.renderDropdownTag(t, 'grayscale ' + (t.category || 'general'))).join('')}
                </div>
            `;
        }

        for (const cat of categoryOrder) {
            const catTags = tagsByCategory[cat];
            if (catTags && catTags.length > 0) {
                html += `
                    <div class="flex flex-wrap items-center gap-1 w-full mb-1 max-w-full min-w-0">
                        ${catTags.map(t => (t.is_new && this.options.allowCategoryChange)
                    ? this.renderDropdownTag(t, cat)
                    : `<span class="text-xs tag-text tag ${cat} truncate max-w-full inline-block min-w-0" title="${this.escapeHtml(t.name)}">${this.escapeHtml(t.name)}</span>`
                ).join('')}
                    </div>
                `;
            }
        }

        this.container.innerHTML = html || `<span class="text-secondary italic text-xs">${window.i18n.t('common.none')}</span>`;
        this.setupDropdownEvents();
    }

    renderDropdownTag(tag, colorClass) {
        const cat = tag.category || 'general';
        const actualColorClass = (typeof colorClass === 'string') ? colorClass : cat;
        const grayscaleClass = (!tag.user_assigned) ? 'grayscale' : '';
        return `
            <div class="custom-select booru-tag-select inline-flex max-w-full min-w-0 align-middle shrink" data-value="${cat}" data-tag="${this.escapeHtml(tag.name)}">
                <div class="custom-select-trigger tag-text tag ${actualColorClass} ${grayscaleClass} cursor-pointer select-none max-w-full min-w-0 !inline-flex items-center gap-1 flex-nowrap" style="white-space: nowrap; display: inline-flex;">
                    <span class="text-xs truncate min-w-0 flex-1" title="${this.escapeHtml(tag.name)}">${this.escapeHtml(tag.name)}</span>
                    <span class="custom-select-value" style="display: none;"></span>
                    ${window.Icons.chevronDown({ size: 10, class: 'custom-select-arrow shrink-0 transition-transform duration-200' })}
                </div>
                <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50 min-w-25">
                    <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'general' ? 'selected' : ''}" data-value="general">${window.i18n.t('common.tag_category_general')}</div>
                    <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'artist' ? 'selected' : ''}" data-value="artist">${window.i18n.t('common.tag_category_artist')}</div>
                    <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'character' ? 'selected' : ''}" data-value="character">${window.i18n.t('common.tag_category_character')}</div>
                    <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'copyright' ? 'selected' : ''}" data-value="copyright">${window.i18n.t('common.tag_category_copyright')}</div>
                    <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${cat === 'meta' ? 'selected' : ''}" data-value="meta">${window.i18n.t('common.tag_category_meta')}</div>
                </div>
            </div>
        `;
    }

    setupDropdownEvents() {
        if (!this.container) return;
        const tagSelects = this.container.querySelectorAll('.booru-tag-select');
        if (typeof CustomSelect !== 'undefined') {
            this.customSelects = [];
            tagSelects.forEach(el => {
                const selectInst = new CustomSelect(el);
                this.customSelects.push(selectInst);
                el.addEventListener('change', (e) => {
                    const tagName = el.dataset.tag;
                    const newCategory = e.detail.value;
                    const tag = this.tags.find(t => t.name.toLowerCase() === tagName.toLowerCase());
                    if (tag) {
                        tag.category = newCategory;
                        tag.user_assigned = true;
                        tag.is_new = true;
                        this.render();
                        if (this.options.onCategoryChange) {
                            this.options.onCategoryChange(tag, newCategory);
                        }
                    }
                });
            });
        }
    }
}

window.TagPreview = TagPreview;
