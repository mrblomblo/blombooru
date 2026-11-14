class TagsGallery extends BaseGallery {
    constructor() {
        super({
            gridSelector: '#tags-grid',
            itemSelector: '.tag-card',
            defaultSort: 'post_count',
            defaultOrder: 'desc',
            enableRatingFilter: true,
            enableTooltips: false,
            enableSorting: true,
            enablePagination: true
        });

        this.tagCache = new Map();
        this.searchDebounceTimer = null;
        this.selectedCategories = new Set();
        this.searchInput = document.getElementById('tag-search-input');
        this.allCategories = ['general', 'artist', 'character', 'copyright', 'meta'];
        this.activePanels = [];
        this.activeSelects = [];
        this.rowResizeObserver = null;
        this.setupRowResizeObserver();

        if (this.elements.grid) {
            this.init();
        }
    }

    async init() {
        this.initCommon();
        this.currentPage = parseInt(this.getUrlParam('page', 1), 10);
        if (isNaN(this.currentPage) || this.currentPage < 1) {
            this.currentPage = 1;
        }

        this.initFiltersFromUrl();
        this.setupSearchInput();
        this.setupCategoryFilters();

        await this.loadContent();
    }

    setupRowResizeObserver() {
        if (typeof ResizeObserver === 'undefined') return;
        this.rowResizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                this.updateCardRowMode(entry.target);
            }
        });
        window.addEventListener('resize', () => {
            if (!this.elements.grid) return;
            const cards = this.elements.grid.querySelectorAll('.tag-card');
            cards.forEach(card => this.updateCardRowMode(card));
        });
    }

    updateCardRowMode(card) {
        if (!card) return;
        const isSmallDisplay = window.innerWidth <= 640 || (window.matchMedia && window.matchMedia('(max-width: 640px)').matches);
        if (isSmallDisplay) {
            card.classList.add('is-wrapped');
            return;
        }

        const header = card.querySelector('.tag-header');
        if (!header) return;

        const leftCol = card.querySelector('.tag-left-col');
        const rightCol = card.querySelector('.tag-right-col');
        const tagLink = card.querySelector('.tag-name-link');
        const desktopCount = card.querySelector('.tag-post-count-desktop');
        const catEl = card.querySelector('.tag-cat-element');
        const metaRight = card.querySelector('.tag-meta-right');

        if (!leftCol || !rightCol) return;

        const tagWidth = tagLink ? tagLink.scrollWidth : 0;
        const desktopCountWidth = desktopCount ? desktopCount.scrollWidth : 0;
        const leftWidth = 24 + tagWidth + desktopCountWidth + 16;

        const catWidth = catEl ? (catEl.offsetWidth || catEl.scrollWidth) : 60;
        const ratingEl = card.querySelector('.tag-rating-element');
        const ratingWidth = ratingEl ? (ratingEl.offsetWidth || ratingEl.scrollWidth) : 32;
        const metaRightWidth = metaRight ? (metaRight.offsetWidth || metaRight.scrollWidth) : 0;
        const rightWidth = catWidth + ratingWidth + metaRightWidth + 16;

        const availableWidth = header.clientWidth;
        const requiredWidth = leftWidth + rightWidth + 24;

        if (availableWidth < requiredWidth) {
            card.classList.add('is-wrapped');
        } else {
            card.classList.remove('is-wrapped');
        }
    }

    initFiltersFromUrl() {
        const urlParams = new URLSearchParams(window.location.search);

        // Search query
        const query = urlParams.get('q') || urlParams.get('search') || '';
        if (this.searchInput) {
            this.searchInput.value = query;
        }

        // Category filters
        const categoriesParam = urlParams.get('categories');
        if (categoriesParam === 'none') {
            this.selectedCategories = new Set();
        } else if (categoriesParam) {
            const list = categoriesParam.split(',').map(c => c.trim().toLowerCase()).filter(Boolean);
            this.selectedCategories = new Set(list.filter(c => this.allCategories.includes(c)));
        } else {
            // Default to all categories
            this.selectedCategories = new Set(this.allCategories);
        }

        this.syncCategoryCheckboxesFromState();
    }

    setupSearchInput() {
        if (!this.searchInput) return;

        if (typeof TagAutocomplete !== 'undefined') {
            this.autocomplete = new TagAutocomplete(this.searchInput, {
                multipleValues: false,
                appendSpace: false,
                enableRatingFilter: true,
                ratingFilter: () => this.currentRating,
                onSelect: (tag) => {
                    const tagName = typeof tag === 'object' && tag !== null ? tag.name : tag;
                    this.searchInput.value = tagName;
                    clearTimeout(this.searchDebounceTimer);
                    this.currentPage = 1;
                    this.updateUrlParams({ q: tagName || null, page: null });
                    this.loadContent();
                }
            });
        }

        this.searchInput.addEventListener('input', (e) => {
            const start = e.target.selectionStart;
            const end = e.target.selectionEnd;
            const normalized = e.target.value.replace(/\s+/g, '_');
            if (e.target.value !== normalized) {
                e.target.value = normalized;
                if (start !== null && end !== null) {
                    e.target.setSelectionRange(start, end);
                }
            }

            clearTimeout(this.searchDebounceTimer);
            this.searchDebounceTimer = setTimeout(() => {
                this.currentPage = 1;
                const query = this.searchInput.value.trim();
                this.updateUrlParams({ q: query || null, page: null });
                this.loadContent();
            }, 300);
        });

        this.searchInput.addEventListener('keydown', (e) => {
            if (e.key === ' ') {
                e.preventDefault();
                const start = e.target.selectionStart;
                const end = e.target.selectionEnd;
                e.target.setRangeText('_', start, end, 'end');
                clearTimeout(this.searchDebounceTimer);
                this.searchDebounceTimer = setTimeout(() => {
                    this.currentPage = 1;
                    const query = this.searchInput.value.trim();
                    this.updateUrlParams({ q: query || null, page: null });
                    this.loadContent();
                }, 300);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(this.searchDebounceTimer);
                this.currentPage = 1;
                const query = this.searchInput.value.trim();
                this.updateUrlParams({ q: query || null, page: null });
                this.loadContent();
            }
        });
    }

    setupCategoryFilters() {
        const checkboxes = document.querySelectorAll('.category-filter-checkbox');
        checkboxes.forEach(cb => {
            cb.addEventListener('change', () => {
                const cat = cb.value;
                if (cb.checked) {
                    this.selectedCategories.add(cat);
                } else {
                    this.selectedCategories.delete(cat);
                }

                this.syncCategoryCheckboxesFromState();

                this.currentPage = 1;
                this.syncCategoriesUrlParam();
                this.loadContent();
            });
        });
    }

    syncCategoryCheckboxesFromState() {
        const checkboxes = document.querySelectorAll('.category-filter-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = this.selectedCategories.has(cb.value);
        });
    }

    syncCategoriesUrlParam() {
        let catParam = null;
        if (this.selectedCategories.size === 0) {
            catParam = 'none';
        } else if (this.selectedCategories.size < this.allCategories.length) {
            catParam = Array.from(this.selectedCategories).join(',');
        }
        this.updateUrlParams({ categories: catParam, page: null });
    }


    _cleanupCardComponents() {
        this.activePanels.forEach(p => {
            if (p && typeof p.destroy === 'function') p.destroy();
        });
        this.activePanels = [];

        if (this.activeSelects) {
            this.activeSelects.forEach(s => {
                if (s && typeof s.destroy === 'function') s.destroy();
            });
            this.activeSelects = [];
        }

        if (this.rowResizeObserver) {
            this.rowResizeObserver.disconnect();
        }
    }

    async loadContent() {
        if (this.isLoading) {
            this._reloadRequested = true;
            if (this._abortController) {
                this._abortController.abort();
            }
            return;
        }

        this.isLoading = true;
        this._reloadRequested = false;
        this.showLoading();

        this._cleanupCardComponents();

        if (this.elements.grid) {
            this.elements.grid.innerHTML = '';
        }

        try {
            // Retain cached tags that are currently selected across pages
            for (const [id] of this.tagCache) {
                if (!this.selectedItems.has(id)) {
                    this.tagCache.delete(id);
                }
            }
            const params = new URLSearchParams({
                page: this.currentPage
            });
            this.appendSortParams(params);

            const query = this.searchInput ? this.searchInput.value.trim() : '';
            if (query) {
                params.set('q', query);
            }

            if (this.selectedCategories.size === 0) {
                params.set('categories', 'none');
            } else if (this.selectedCategories.size < this.allCategories.length) {
                params.set('categories', Array.from(this.selectedCategories).join(','));
            }

            if (this.currentRating) {
                params.set('rating', this.currentRating);
            }

            this._abortController = new AbortController();
            const response = await fetch(`/api/tags/list?${params.toString()}`, {
                signal: this._abortController.signal
            });
            if (!response.ok) {
                throw new Error(window.i18n.t('tags_gallery.failed_load_list'));
            }

            const data = await response.json();
            this.totalPages = data.pages || 1;

            if (this.adjustPageIfNeeded(data.pages)) {
                this._reloadRequested = true;
                return;
            }

            const responseItems = data.items || [];
            this.renderTagList(responseItems, data.unfiltered_total);
            this.renderPagination();
            this.updateBulkActionsUI();
        } catch (error) {
            if (error.name === 'AbortError') {
                return;
            }
            console.error('Error loading tags:', error);
            this.showError(window.i18n.t('tags_gallery.failed_load_list'));
        } finally {
            this.isLoading = false;
            this.hideLoading();
            if (this._reloadRequested) {
                this._reloadRequested = false;
                this.loadContent();
            }
        }
    }

    renderTagList(tags, unfilteredTotal = 0) {
        if (!this.elements.grid) return;

        if (tags.length === 0) {
            if (unfilteredTotal > 0) {
                const msg = unfilteredTotal === 1
                    ? window.i18n.t('gallery.tag_hidden_by_filters')
                    : window.i18n.t('gallery.tags_hidden_by_filters', { count: unfilteredTotal });
                this.showEmptyState(msg);
            } else {
                this.showEmptyState(window.i18n.t('gallery.no_tags_found'));
            }
            return;
        }

        tags.forEach(tag => {
            this.tagCache.set(Number(tag.id), tag);
            const element = this.createTagItem(tag);
            this.elements.grid.appendChild(element);
            if (this.rowResizeObserver) {
                this.rowResizeObserver.observe(element);
            }
            this.updateCardRowMode(element);
        });
    }

    createTagItem(tag) {
        const tagId = Number(tag.id);
        const card = document.createElement('div');
        card.className = 'surface border tag-card relative transition-colors';
        card.dataset.id = tagId;
        card.dataset.tagName = tag.name;
        card.dataset.tagRating = tag.rating || 'none';

        const isSelected = app.isAdminMode && this.selectedItems.has(tagId);
        if (isSelected) card.classList.add('selected');

        // Header: flex-wrap allows metadata/actions to sit on the same line,
        // and wrap to a second row when the tag would otherwise get cut off
        const header = document.createElement('div');
        header.className = 'tag-header px-3 py-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 cursor-pointer select-none hover:bg-primary/5 transition-colors';

        // Tag info column (expand icon, tag pill, and desktop usage count)
        const leftCol = document.createElement('div');
        leftCol.className = 'tag-left-col flex items-center gap-2 min-w-0 max-w-full';

        const expandBtn = document.createElement('button');
        expandBtn.type = 'button';
        expandBtn.className = 'tag-expand-btn text-secondary hover:text-primary transition-transform duration-200 cursor-pointer p-0.5 flex items-center justify-center shrink-0';
        expandBtn.setAttribute('aria-label', window.i18n.t('tags_gallery.toggle_details'));
        expandBtn.innerHTML = window.Icons.chevronRight({ size: 14, class: 'tag-chevron transition-transform duration-200' });
        const chevronSvg = expandBtn.querySelector('.tag-chevron') || expandBtn.firstElementChild;

        const safeCat = TagInfoPanel.safeCategory(tag.category);
        const tagLink = document.createElement('a');
        tagLink.href = `/?q=${encodeURIComponent(tag.name)}`;
        tagLink.className = `tag ${safeCat} tag-text text-xs px-2.5 py-0.5 font-medium hover:opacity-80 transition-opacity truncate tag-name-link`;
        tagLink.dataset.tagRating = tag.rating || 'none';
        tagLink.textContent = tag.name;

        // Desktop usage count: visible in 1-row mode directly next to tag name, hidden in 2-row mode
        const postCountDesktop = document.createElement('span');
        postCountDesktop.className = 'tag-post-count-desktop text-xs text-secondary font-mono shrink-0 select-none';
        postCountDesktop.textContent = `(${tag.post_count})`;

        leftCol.appendChild(expandBtn);
        leftCol.appendChild(tagLink);
        leftCol.appendChild(postCountDesktop);
        header.appendChild(leftCol);

        // Right side: category element, mobile usage count, and admin action buttons
        const rightCol = document.createElement('div');
        rightCol.className = 'tag-right-col flex items-center gap-2.5 shrink-0 ml-auto';

        // Meta left group: category dropdown/badge + mobile usage count
        // In 1-row mode, mobile usage count is hidden and this sits before actions.
        // In 2-row mode, rightCol is full-width with justify-between, placing this at the far left!
        const metaLeft = document.createElement('div');
        metaLeft.className = 'tag-meta-left flex items-center gap-2 shrink-0';

        const postCountMobile = document.createElement('span');
        postCountMobile.className = 'tag-post-count-mobile text-xs text-secondary font-mono shrink-0 select-none';
        postCountMobile.textContent = `(${tag.post_count})`;

        let catElement;
        let selectInst = null;
        if (app.isAdminMode) {
            const catSelectDiv = document.createElement('div');
            catSelectDiv.className = 'custom-select tag-cat-element';
            catSelectDiv.dataset.value = safeCat;

            catSelectDiv.innerHTML = `
                <button type="button" class="custom-select-trigger tag ${safeCat} tag-text flex items-center justify-between gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-transparent hover:border-primary/50 transition-colors focus:outline-none cursor-pointer select-none">
                    <span class="custom-select-value">${window.i18n.t('common.tag_category_' + safeCat)}</span>
                    <span class="custom-select-arrow transition-transform duration-200">
                        ${window.Icons.chevronDown({ size: 10 })}
                    </span>
                </button>
                <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50 min-w-25">
                    ${TagInfoPanel.KNOWN_CATEGORIES.map(c => `
                        <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${c === safeCat ? 'selected' : ''}" data-value="${c}">
                            ${window.i18n.t('common.tag_category_' + c)}
                        </div>
                    `).join('')}
                </div>
            `;

            catSelectDiv.addEventListener('mousedown', (e) => e.stopPropagation());
            catSelectDiv.addEventListener('click', (e) => e.stopPropagation());

            selectInst = new CustomSelect(catSelectDiv);
            this.activeSelects.push(selectInst);

            catSelectDiv.addEventListener('change', async (e) => {
                const newCategory = e.detail ? e.detail.value : catSelectDiv.dataset.value;
                const oldCategory = tag.category;
                if (newCategory === oldCategory) return;

                const trigger = catSelectDiv.querySelector('.custom-select-trigger');
                const newSafeCat = TagInfoPanel.safeCategory(newCategory);
                const oldSafeCat = TagInfoPanel.safeCategory(oldCategory);

                try {
                    await app.apiCall(`/api/admin/tags/${tag.id}`, {
                        method: 'PUT',
                        body: JSON.stringify({
                            name: tag.name,
                            category: newCategory
                        })
                    });
                    tag.category = newCategory;
                    this.tagCache.set(tagId, tag);

                    tagLink.className = `tag ${newSafeCat} tag-text text-xs px-2.5 py-0.5 font-medium hover:opacity-80 transition-opacity truncate tag-name-link`;
                    if (trigger) {
                        TagInfoPanel.KNOWN_CATEGORIES.forEach(c => trigger.classList.remove(c));
                        trigger.classList.add(newSafeCat);
                    }
                    if (panel.loaded) {
                        panel.render();
                    }
                    app.showNotification(window.i18n.t('notifications.admin.tag_updated', { old_name: tag.name }), 'success');
                } catch (err) {
                    selectInst.setValue(oldSafeCat, false);
                    if (trigger) {
                        TagInfoPanel.KNOWN_CATEGORIES.forEach(c => trigger.classList.remove(c));
                        trigger.classList.add(oldSafeCat);
                    }
                    app.showNotification(err.message, 'error', window.i18n.t('notifications.admin.error_updating_tag'));
                }
            });

            catElement = catSelectDiv;
        } else {
            const catBadge = document.createElement('span');
            catBadge.className = `tag ${safeCat} tag-text uppercase text-[10px] font-bold tracking-wider px-2 py-0.5 select-none tag-cat-element`;
            catBadge.textContent = window.i18n.t('common.tag_category_' + safeCat);
            catElement = catBadge;
        }

        let ratingElement;
        let ratingSelectInst = null;
        const cleanRating = (typeof TagRating !== 'undefined') ? TagRating.normalize(tag.rating) : (tag.rating || 'none');
        const ratings = [
            { value: 'none', label: window.i18n.t('common.none', { defaultValue: 'None' }), abbr: 'N' },
            { value: 'safe', label: window.i18n.t('common.safe', { defaultValue: 'Safe' }), abbr: 'S' },
            { value: 'questionable', label: window.i18n.t('common.questionable', { defaultValue: 'Questionable' }), abbr: 'Q' },
            { value: 'explicit', label: window.i18n.t('common.explicit', { defaultValue: 'Explicit' }), abbr: 'E' },
        ];
        const currentRatingObj = ratings.find(r => r.value === cleanRating) || ratings[0];

        if (app.isAdminMode) {
            const ratingSelectDiv = document.createElement('div');
            ratingSelectDiv.className = 'custom-select tag-rating-element';
            ratingSelectDiv.dataset.value = cleanRating;

            ratingSelectDiv.innerHTML = `
                <button type="button" class="custom-select-trigger tag rating-${cleanRating} tag-text flex items-center justify-between gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-transparent hover:border-primary/50 transition-colors focus:outline-none cursor-pointer select-none" title="${currentRatingObj.label}">
                    <span class="custom-select-value">${currentRatingObj.abbr}</span>
                    <span class="custom-select-arrow transition-transform duration-200">
                        ${window.Icons.chevronDown({ size: 10 })}
                    </span>
                </button>
                <div class="custom-select-dropdown bg border border-primary max-h-40 overflow-y-auto shadow-lg z-50 min-w-36 whitespace-nowrap">
                    ${ratings.map(r => `
                        <div class="custom-select-option px-3 py-1.5 cursor-pointer hover:surface text-xs ${r.value === cleanRating ? 'selected' : ''}" data-value="${r.value}" data-display="${r.abbr}">
                            ${r.label}
                        </div>
                    `).join('')}
                </div>
            `;

            ratingSelectDiv.addEventListener('mousedown', (e) => e.stopPropagation());
            ratingSelectDiv.addEventListener('click', (e) => e.stopPropagation());

            ratingSelectInst = new CustomSelect(ratingSelectDiv);
            this.activeSelects.push(ratingSelectInst);

            ratingSelectDiv.addEventListener('change', async (e) => {
                const newRating = e.detail ? e.detail.value : ratingSelectDiv.dataset.value;
                const oldRating = tag.rating || 'none';
                if (newRating === oldRating) return;

                const trigger = ratingSelectDiv.querySelector('.custom-select-trigger');
                const oldClean = (typeof TagRating !== 'undefined') ? TagRating.normalize(oldRating) : oldRating;
                const newClean = (typeof TagRating !== 'undefined') ? TagRating.normalize(newRating) : newRating;
                const newObj = ratings.find(r => r.value === newClean) || ratings[0];
                const oldObj = ratings.find(r => r.value === oldClean) || ratings[0];

                try {
                    await app.apiCall(`/api/admin/tags/${tag.id}`, {
                        method: 'PUT',
                        body: JSON.stringify({
                            name: tag.name,
                            category: tag.category,
                            rating: newClean
                        })
                    });
                    tag.rating = newClean;
                    this.tagCache.set(tagId, tag);
                    card.dataset.tagRating = newClean;
                    tagLink.dataset.tagRating = newClean;

                    if (trigger) {
                        ['none', 'safe', 'questionable', 'explicit'].forEach(r => trigger.classList.remove(`rating-${r}`));
                        trigger.classList.add(`rating-${newClean}`);
                        trigger.title = newObj.label;
                    }
                    if (panel && panel.loaded) {
                        panel.render();
                    }
                    app.showNotification(window.i18n.t('notifications.admin.tag_updated', { old_name: tag.name }), 'success');
                } catch (err) {
                    ratingSelectInst.setValue(oldClean, false);
                    if (trigger) {
                        ['none', 'safe', 'questionable', 'explicit'].forEach(r => trigger.classList.remove(`rating-${r}`));
                        trigger.classList.add(`rating-${oldClean}`);
                        trigger.title = oldObj.label;
                    }
                    app.showNotification(err.message, 'error', window.i18n.t('notifications.admin.error_updating_tag'));
                }
            });

            ratingElement = ratingSelectDiv;
        } else {
            const ratingBadge = document.createElement('span');
            const abbr = (typeof TagRating !== 'undefined') ? TagRating.abbr(cleanRating) : (cleanRating.charAt(0).toUpperCase() || 'N');
            ratingBadge.className = `tag rating-${cleanRating} tag-text uppercase text-[10px] font-bold tracking-wider px-2 py-0.5 select-none tag-rating-element`;
            ratingBadge.textContent = abbr;
            ratingBadge.title = currentRatingObj.label;
            ratingBadge.setAttribute('aria-label', currentRatingObj.label);
            ratingElement = ratingBadge;
        }

        metaLeft.appendChild(catElement);
        metaLeft.appendChild(ratingElement);
        metaLeft.appendChild(postCountMobile);
        rightCol.appendChild(metaLeft);

        // Meta right group: edit, remove, checkbox
        const metaRight = document.createElement('div');
        metaRight.className = 'tag-meta-right flex items-center gap-2.5 shrink-0';

        if (app.isAdminMode) {
            // Edit button (primary bg and primary-text icon)
            const editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'bg-primary primary-text hover:opacity-80 transition-opacity cursor-pointer p-1.5 flex items-center justify-center shrink-0';
            editBtn.title = window.i18n.t('common.edit');
            editBtn.setAttribute('aria-label', window.i18n.t('common.edit'));
            editBtn.innerHTML = window.Icons.edit({ size: 14 });
            editBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                TagManageModals.edit({
                    tagId: tag.id,
                    tagName: tag.name,
                    tagCategory: tag.category,
                    tagRating: tag.rating,
                    onSaved: (result) => {
                        tag.name = result.tag_name || tag.name;
                        tag.category = result.category || tag.category;
                        tag.rating = result.rating || tag.rating;
                        tag.aliases = result.aliases || tag.aliases;
                        this.tagCache.set(tagId, tag);

                        card.dataset.tagRating = tag.rating;
                        tagLink.dataset.tagRating = tag.rating;
                        tagLink.textContent = tag.name;
                        tagLink.href = `/?q=${encodeURIComponent(tag.name)}`;
                        const newSafeCat = TagInfoPanel.safeCategory(tag.category);
                        tagLink.className = `tag ${newSafeCat} tag-text text-xs px-2.5 py-0.5 font-medium hover:opacity-80 transition-opacity truncate tag-name-link`;
                        if (selectInst) {
                            selectInst.setValue(newSafeCat, false);
                            const trigger = catElement.querySelector('.custom-select-trigger');
                            if (trigger) {
                                TagInfoPanel.KNOWN_CATEGORIES.forEach(c => trigger.classList.remove(c));
                                trigger.classList.add(newSafeCat);
                            }
                        } else if (catElement) {
                            catElement.className = `tag ${newSafeCat} tag-text uppercase text-[10px] font-bold tracking-wider px-2 py-0.5 select-none tag-cat-element`;
                            catElement.textContent = window.i18n.t('common.tag_category_' + newSafeCat);
                        }
                        if (ratingSelectInst) {
                            ratingSelectInst.setValue(tag.rating, false);
                            const trigger = ratingElement.querySelector('.custom-select-trigger');
                            if (trigger) {
                                ['none', 'safe', 'questionable', 'explicit'].forEach(r => trigger.classList.remove(`rating-${r}`));
                                trigger.classList.add(`rating-${tag.rating}`);
                                const rObj = ratings.find(r => r.value === tag.rating) || ratings[0];
                                trigger.title = rObj.label;
                            }
                        } else if (ratingElement) {
                            const rObj = ratings.find(r => r.value === tag.rating) || ratings[0];
                            const abbr = (typeof TagRating !== 'undefined') ? TagRating.abbr(tag.rating) : (tag.rating.charAt(0).toUpperCase() || 'N');
                            ratingElement.className = `tag rating-${tag.rating} tag-text uppercase text-[10px] font-bold tracking-wider px-2 py-0.5 select-none tag-rating-element`;
                            ratingElement.textContent = abbr;
                            ratingElement.title = rObj.label;
                            ratingElement.setAttribute('aria-label', rObj.label);
                        }
                        if (panel && panel.loaded) {
                            panel.render();
                        }
                    }
                });
            });

            // Remove button (danger bg and tag-text icon)
            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'bg-danger tag-text hover:opacity-80 transition-opacity cursor-pointer p-1.5 flex items-center justify-center shrink-0';
            removeBtn.title = window.i18n.t('common.remove');
            removeBtn.setAttribute('aria-label', window.i18n.t('common.remove'));
            removeBtn.innerHTML = window.Icons.trash({ size: 14 });
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                TagManageModals.remove({
                    tagId: tag.id,
                    tagName: tag.name,
                    tagCategory: tag.category,
                    onDeleted: () => {
                        card.remove();
                        this.tagCache.delete(tagId);
                        this.selectedItems.delete(tagId);
                        this.updateBulkActionsUI();
                        this.updateSelectionModeClass();
                        if (this.elements.grid && this.elements.grid.children.length === 0) {
                            this.loadContent();
                        }
                    }
                });
            });

            // Checkbox (placed to the right of remove button)
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'select-checkbox w-4 h-4 accent-primary cursor-pointer border transition-colors';
            checkbox.dataset.id = tagId;
            checkbox.checked = isSelected;
            checkbox.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleItemSelection(card, tagId, e);
            });

            metaRight.appendChild(editBtn);
            metaRight.appendChild(removeBtn);
            metaRight.appendChild(checkbox);
        }

        rightCol.appendChild(metaRight);
        header.appendChild(rightCol);
        card.appendChild(header);

        // Details Panel
        const detailsPanel = document.createElement('div');
        detailsPanel.className = 'tag-details border-t px-3 py-2 space-y-2.5 text-xs';
        detailsPanel.style.display = 'none';
        card.appendChild(detailsPanel);

        const panel = new TagInfoPanel(tag, detailsPanel, {
            onUpdate: (updatedTag) => {
                Object.assign(tag, updatedTag);
            }
        });
        this.activePanels.push(panel);

        let isExpanded = false;
        const toggleExpand = async () => {
            isExpanded = !isExpanded;
            detailsPanel.style.display = isExpanded ? 'block' : 'none';
            if (chevronSvg) {
                chevronSvg.style.transform = isExpanded ? 'rotate(90deg)' : '';
            }

            if (isExpanded && !panel.loaded) {
                await panel.loadAndRender();
            }
        };

        expandBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleExpand();
        });

        tagLink.addEventListener('click', (e) => {
            if (app.isAdminMode && this.isSelectionMode) {
                e.preventDefault();
                e.stopPropagation();
                this.toggleItemSelection(card, tagId, e);
            } else {
                e.stopPropagation();
            }
        });

        // Drag selection (same behavior as the media gallery)
        if (app.isAdminMode) {
            header.addEventListener('mousedown', (e) => {
                if (e.button !== 0 || !this.isSelectionMode) return;
                if (e.target.closest('button, a, input, select, .custom-select')) return;
                e.preventDefault();
                this.handleMouseDown(card, tagId);
            });
        }

        card.addEventListener('mouseenter', () => {
            if (this.dragStartItem) {
                this.handleDragEnter(card, tagId);
            }
        });

        header.addEventListener('click', (e) => {
            if (this.suppressClick) return;
            if (e.target.closest('button, a, input, select, .custom-select')) return;
            if (app.isAdminMode && (this.isSelectionMode || e.shiftKey || e.ctrlKey || e.metaKey)) {
                this.toggleItemSelection(card, tagId, e);
                return;
            }
            toggleExpand();
        });

        return card;
    }

    // ==================== Bulk Actions ====================

    setupBulkActions() {
        super.setupBulkActions();

        const bind = (id, action) => {
            const btn = document.getElementById(id);
            if (btn) btn.addEventListener('click', () => this.openBulkTagModal(action));
        };

        bind('bulk-tag-category-btn', 'category');
        bind('bulk-tag-rating-btn', 'rating');
        bind('bulk-tag-implies-btn', 'implies');
        bind('bulk-tag-merge-btn', 'merge');
        bind('bulk-tag-remove-btn', 'remove');
    }

    getSelectedTags() {
        return Array.from(this.selectedItems)
            .map(id => this.tagCache.get(Number(id)))
            .filter(Boolean)
            .map(({ id, name, category, rating }) => ({ id, name, category, rating: rating || 'none' }));
    }

    openBulkTagModal(action) {
        if (!app.isAdminMode) return;

        const tags = this.getSelectedTags();
        if (tags.length === 0) return;

        TagBulkModals[action]({
            tags,
            onDone: () => {
                this.clearSelection();
                return this.loadContent();
            }
        });
    }

    clearSelection() {
        super.clearSelection();
        const visibleIds = new Set(
            Array.from(document.querySelectorAll(this.options.itemSelector))
                .map(item => parseInt(item.dataset.id, 10))
        );
        for (const [id] of this.tagCache) {
            if (!visibleIds.has(id)) {
                this.tagCache.delete(id);
            }
        }
    }

    async performGlobalSelection() {
        const btn = document.getElementById('select-all-btn');
        if (!btn) return;

        const originalText = btn.textContent;
        btn.textContent = window.i18n.t('gallery.selecting_all');
        btn.disabled = true;

        try {
            if (this.selectedCategories.size === 0) {
                app.showNotification(window.i18n.t('notifications.gallery.no_items_to_select'), 'info');
                return;
            }

            const params = new URLSearchParams({
                limit: '500000',
                include_aliases: 'false'
            });
            this.appendSortParams(params);

            const query = this.searchInput ? this.searchInput.value.trim() : '';
            if (query) {
                params.set('q', query);
            }

            if (this.selectedCategories.size > 0 && this.selectedCategories.size < this.allCategories.length) {
                params.set('categories', Array.from(this.selectedCategories).join(','));
            }

            if (this.currentRating) {
                params.set('rating', this.currentRating);
            }

            const res = await fetch(`/api/tags/list?${params.toString()}`);
            if (!res.ok) throw new Error('Failed to fetch tags');

            const data = await res.json();
            const allItems = data.items || [];

            if (allItems.length === 0) {
                app.showNotification(window.i18n.t('notifications.gallery.no_items_to_select'), 'info');
                return;
            }

            allItems.forEach(tag => {
                const tagId = Number(tag.id);
                this.tagCache.set(tagId, tag);
                this.selectedItems.add(tagId);
            });

            // Visually update current page items to ensure they look selected
            document.querySelectorAll(this.options.itemSelector).forEach(item => {
                const id = parseInt(item.dataset.id, 10);
                if (this.selectedItems.has(id)) {
                    item.classList.add('selected');
                    const checkbox = item.querySelector('.select-checkbox');
                    if (checkbox) checkbox.checked = true;
                }
            });

            this.updateBulkActionsUI();
            app.showNotification(window.i18n.t('notifications.gallery.items_selected', { count: this.selectedItems.size }), 'success');
        } catch (e) {
            console.error('Global selection failed:', e);
            app.showNotification(window.i18n.t('notifications.gallery.failed_to_select_all'), 'error');
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.tagsGallery = new TagsGallery();
});
