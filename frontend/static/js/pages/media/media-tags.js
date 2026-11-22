// MediaViewer tag editing, implications, suggestions, and AI/WD tagger integration
Object.assign(MediaViewer.prototype, {
    getHighlightTags(inputElement) {
        if (!inputElement) return new Set();
        const inputTags = this.tagInputHelper.getPlainTextFromDiv(inputElement).split(/\s+/).filter(t => t.length > 0);
        const highlightTags = new Set();
        for (const t of inputTags) {
            const lower = t.toLowerCase().trim();
            if (!this.originalTags.has(lower)) {
                highlightTags.add(lower);
            }
        }
        return highlightTags;
    },

    handleImplicationExpanded(impliedByMap, impliedTags) {
        const hideActive = this.tagInputHelper ? this.tagInputHelper.isHideImpliedEnabled() : false;
        for (const tagName of (impliedTags || [])) {
            const lower = tagName.toLowerCase().trim();
            if (!lower) continue;
            const groups = (impliedByMap && impliedByMap[lower]) || (impliedByMap && impliedByMap[tagName]) || [];
            const existingGroups = this.impliedTagsMap.get(lower) || [];
            const merged = [...existingGroups];
            for (const g of groups) {
                if (Array.isArray(g) && !merged.some(eg => JSON.stringify(eg) === JSON.stringify(g))) {
                    merged.push(g);
                }
            }
            this.impliedTagsMap.set(lower, merged);
            if (hideActive) {
                this.hiddenImpliedTags.add(lower);
            }
        }
    },

    async applyHideImpliedToEditor(hide) {
        const tagsInput = this.el('tags-input');
        if (!tagsInput || !this.tagInputHelper) return;

        const text = this.tagInputHelper.getPlainTextFromDiv(tagsInput).trim();
        const visibleTags = text ? text.split(/\s+/).filter(Boolean) : [];

        if (hide) {
            const remaining = [];
            for (const t of visibleTags) {
                const lower = t.toLowerCase().trim();
                if (this.impliedTagsMap.has(lower)) {
                    this.hiddenImpliedTags.add(lower);
                } else {
                    remaining.push(t);
                }
            }
            tagsInput.textContent = remaining.join(' ');
        } else {
            const visibleLower = new Set(visibleTags.map(t => t.toLowerCase().trim()));
            for (const hiddenLower of this.hiddenImpliedTags) {
                if (!visibleLower.has(hiddenLower) && this.impliedTagsMap.has(hiddenLower)) {
                    visibleTags.push(hiddenLower);
                    visibleLower.add(hiddenLower);
                }
            }
            this.hiddenImpliedTags.clear();
            tagsInput.textContent = visibleTags.join(' ');
        }

        await this.validateAndStyleTags();
    },

    setupTagInput() {
        const tagsInput = this.el('tags-input');
        if (!tagsInput) return;

        this.tagInputHelper.setupTagInput(tagsInput, 'media-tags-input', {
            onValidate: () => { },
            validationCache: this.tagInputHelper.tagValidationCache,
            getHighlightTags: (inputElement) => this.getHighlightTags(inputElement),
            getImpliedTags: () => this.impliedTagsMap,
            getHiddenImpliedTags: () => this.hiddenImpliedTags,
            getExpandedTriggers: () => this.expandedTriggerTags,
            onImplicationExpanded: (impliedByMap, impliedTags) => {
                this.handleImplicationExpanded(impliedByMap, impliedTags);
            },
            isHideImpliedActive: () => this.tagInputHelper.isHideImpliedEnabled()
        });
    },

    async validateAndStyleTags() {
        const tagsInput = this.el('tags-input');
        if (!tagsInput || !this.tagInputHelper) return;

        this.tagInputHelper.pruneImpliedTags(tagsInput, this.impliedTagsMap, this.hiddenImpliedTags);

        const highlightTags = this.getHighlightTags(tagsInput);

        await this.tagInputHelper.validateAndStyleTags(tagsInput, {
            validationCache: this.tagInputHelper.tagValidationCache,
            highlightTags: highlightTags,
            impliedTags: this.impliedTagsMap
        });
    },

    setupSuggestedTags() {
        // Setup accordion toggle
        const toggle = this.el('suggested-tags-toggle');
        const content = this.el('suggested-tags-content');
        if (toggle && content) {
            const newToggle = toggle.cloneNode(true);
            toggle.parentNode.replaceChild(newToggle, toggle);
            newToggle.addEventListener('click', () => {
                const isHidden = content.style.display === 'none';
                content.style.display = isHidden ? 'block' : 'none';
                const activeChevron = newToggle.querySelector('#suggested-tags-chevron');
                if (activeChevron) {
                    activeChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
                }
            });
        }

        // Setup filter category select (left dropdown)
        const filterSelectEl = this.el('suggested-tags-category-select');
        if (filterSelectEl) {
            this.suggestedCategorySelect = new CustomSelect(filterSelectEl);
            this.suggestedCategorySelect.element.addEventListener('change', (e) => {
                this._suggestedTagsCategory = e.detail.value === 'all' ? null : e.detail.value;
                this.renderSuggestedTagsList();
            });
        }

        // Setup search category select (right dropdown)
        const searchSelectEl = this.el('suggested-tags-search-category-select');
        if (searchSelectEl) {
            this.suggestedSearchCategorySelect = new CustomSelect(searchSelectEl);
            this.suggestedSearchCategorySelect.element.addEventListener('change', (e) => {
                this._suggestedSearchCategory = e.detail.value === 'all' ? null : e.detail.value;
                this.updateSuggestedTags();
            });
        }

        let debounceTimer = null;
        this.el('tags-input')?.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => this.updateSuggestedTags(), 400);
        });
    },

    async updateSuggestedTags() {
        const tagsInput = this.el('tags-input');
        const section = this.el('suggested-tags-section');
        const listEl = this.el('suggested-tags-list');
        if (!tagsInput || !section || !listEl) return;

        if (this._suggestedTagsRetryTimeout) {
            clearTimeout(this._suggestedTagsRetryTimeout);
            this._suggestedTagsRetryTimeout = null;
        }

        const currentTags = this.tagInputHelper.getPlainTextFromDiv(tagsInput)
            .split(/\s+/).map(t => t.trim()).filter(Boolean);

        if (currentTags.length === 0) {
            section.style.display = 'none';
            listEl.innerHTML = '';
            this._suggestedItems = [];
            if (this.suggestedSearchCategorySelect) {
                this.suggestedSearchCategorySelect.setOptions([
                    { value: 'all', text: window.i18n.t('media.tags.search_by'), selected: true }
                ]);
            }
            return;
        }

        // Fetch categories for any tags not yet in cache
        const uncachedTags = currentTags.filter(t => !this.tagCategoryCache.has(t.toLowerCase()));
        if (uncachedTags.length > 0) {
            try {
                const batchResults = await this.tagInputHelper.checkTagsBatch(uncachedTags);
                for (const [lowerName, tagObj] of Object.entries(batchResults)) {
                    if (tagObj && tagObj.category) {
                        this.tagCategoryCache.set(lowerName, tagObj.category);
                    }
                }
            } catch (e) {
                console.error('Error fetching tag categories:', e);
            }
        }

        // Find categories used on the post
        const activeCategories = new Set();
        for (const t of currentTags) {
            const cat = this.tagCategoryCache.get(t.toLowerCase());
            if (cat) {
                activeCategories.add(cat);
            }
        }

        const categoryOrder = ['artist', 'character', 'copyright', 'general', 'meta'];
        const availableSearchCats = categoryOrder.filter(cat => activeCategories.has(cat));

        let currentSearchVal = this.suggestedSearchCategorySelect ? this.suggestedSearchCategorySelect.getValue() : 'all';
        if (!currentSearchVal || (currentSearchVal !== 'all' && !activeCategories.has(currentSearchVal))) {
            currentSearchVal = 'all';
        }
        this._suggestedSearchCategory = currentSearchVal === 'all' ? null : currentSearchVal;

        if (this.suggestedSearchCategorySelect) {
            const searchOptions = [
                {
                    value: 'all',
                    text: window.i18n.t('media.tags.search_by'),
                    selected: currentSearchVal === 'all'
                },
                ...availableSearchCats.map(cat => ({
                    value: cat,
                    text: window.i18n.t(`common.tag_category_${cat}`),
                    selected: currentSearchVal === cat
                }))
            ];
            this.suggestedSearchCategorySelect.setOptions(searchOptions);
        }

        // Filter tags to send to /suggested endpoint based on selected search category
        let tagsToSend = currentTags;
        if (this._suggestedSearchCategory) {
            tagsToSend = currentTags.filter(t => this.tagCategoryCache.get(t.toLowerCase()) === this._suggestedSearchCategory);
        }

        if (tagsToSend.length === 0) {
            this._suggestedItems = [];
            section.style.display = 'block';
            this.renderSuggestedTagsList();
            return;
        }

        if (this._suggestedTagsAbort) {
            this._suggestedTagsAbort.abort();
        }
        this._suggestedTagsAbort = new AbortController();

        const params = new URLSearchParams({ tags: tagsToSend.join(','), limit: '40' });

        try {
            const res = await fetch(`/api/tags/suggested?${params.toString()}`, {
                signal: this._suggestedTagsAbort.signal
            });
            if (!res.ok) return;

            const data = await res.json();

            // If the similarity index is rebuilding in backend, keep section visible and retry
            if (data.status === 'building') {
                section.style.display = 'block';
                if (!this._suggestedItems || this._suggestedItems.length === 0) {
                    listEl.innerHTML = `<p class="text-xs text-secondary py-2 text-center">${window.i18n.t('media.progress.validating') || 'Loading...'}</p>`;
                }
                this._suggestedTagsRetryTimeout = setTimeout(() => {
                    this.updateSuggestedTags();
                }, 1000);
                return;
            }

            const lowerCurrentTags = new Set(currentTags.map(t => t.toLowerCase()));
            this._suggestedItems = (data.items || []).filter(t => !lowerCurrentTags.has(t.name.toLowerCase()));

            // Cache categories of returned suggestions
            for (const item of (data.items || [])) {
                if (item.name && item.category) {
                    this.tagCategoryCache.set(item.name.toLowerCase(), item.category);
                }
            }

            if (this._suggestedItems.length === 0) {
                if (!this._suggestedTagsCategory && !this._suggestedSearchCategory) {
                    section.style.display = 'none';
                    listEl.innerHTML = '';
                    return;
                }
            }

            section.style.display = 'block';
            this.renderSuggestedTagsList();
        } catch (e) {
            if (e.name !== 'AbortError') {
                console.error('Error fetching suggested tags:', e);
            }
        }
    },

    renderSuggestedTagsList() {
        const listEl = this.el('suggested-tags-list');
        const section = this.el('suggested-tags-section');
        if (!listEl || !section) return;

        listEl.innerHTML = '';

        let items = this._suggestedItems || [];
        if (this._suggestedTagsCategory) {
            items = items.filter(t => (t.category || 'general') === this._suggestedTagsCategory);
        }

        if (items.length === 0) {
            listEl.innerHTML = `<p class="text-xs text-secondary py-2 text-center">${window.i18n.t('gallery.no_tags_found')}</p>`;
            return;
        }

        for (const tag of items) {
            const item = document.createElement('div');
            item.className = 'popular-tag-item';

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `popular-tag-name tag ${tag.category} tag-text w-full text-xs px-2 py-1 cursor-pointer hover:opacity-75 transition-opacity`;
            btn.dataset.tagRating = tag.rating || 'none';

            const nameSpan = document.createElement('span');
            nameSpan.className = 'truncate';
            nameSpan.textContent = tag.name;

            const countSpan = document.createElement('span');
            countSpan.className = 'popular-tag-count ml-2 font-bold';
            countSpan.textContent = tag.post_count;

            btn.appendChild(nameSpan);
            btn.appendChild(countSpan);

            btn.addEventListener('click', (e) => {
                e.preventDefault();
                this.appendSuggestedTag(tag.name);
                this._suggestedItems = (this._suggestedItems || []).filter(t => t.name !== tag.name);
                item.remove();
                if (listEl.querySelectorAll('.popular-tag-item').length === 0) {
                    if (!this._suggestedTagsCategory && !this._suggestedSearchCategory) {
                        section.style.display = 'none';
                    } else {
                        listEl.innerHTML = `<p class="text-xs text-secondary py-2 text-center">${window.i18n.t('gallery.no_tags_found')}</p>`;
                    }
                }
            });

            item.appendChild(btn);
            listEl.appendChild(item);
        }
    },

    async appendSuggestedTag(tagName) {
        const tagsInput = this.el('tags-input');
        if (!tagsInput) return;

        const currentText = this.tagInputHelper.getPlainTextFromDiv(tagsInput).trim();
        const currentTags = currentText ? currentText.split(/\s+/) : [];
        const existingTagsSet = new Set([
            ...currentTags.map(t => t.toLowerCase()),
            ...Array.from(this.hiddenImpliedTags || [])
        ]);

        if (!existingTagsSet.has(tagName.toLowerCase())) {
            currentTags.push(tagName);
            tagsInput.textContent = currentTags.join(' ');
            if (this.tagInputHelper) {
                this.tagInputHelper.tagValidationCache.set(tagName.toLowerCase().trim(), true);
                await this.tagInputHelper.expandImplications(tagsInput, {
                    extraTags: Array.from(this.hiddenImpliedTags || []),
                    expandedTriggers: this.expandedTriggerTags,
                    impliedTags: this.impliedTagsMap,
                    onImplicationExpanded: (impliedByMap, impliedTags) => {
                        this.handleImplicationExpanded(impliedByMap, impliedTags);
                    },
                    hideImplied: this.tagInputHelper.isHideImpliedEnabled()
                });
            }
            await this.validateAndStyleTags();
            this.updateSuggestedTags();
        }
    },

    async getTagOrAlias(tagName) {
        if (!tagName || !tagName.trim()) return null;
        const normalized = tagName.toLowerCase().trim();

        try {
            const res = await fetch(`/api/tags/${encodeURIComponent(normalized)}`);
            if (!res.ok) return null;

            const data = await res.json();
            return data.aliased_to || data.name;
        } catch (e) {
            console.error('Error fetching tag:', e);
            return null;
        }
    },

    // ==================== WD Tagger Methods ====================

    async predictWDTags() {
        const btn = this.el('predict-wd-tags-btn');
        if (!btn) return;

        try {
            const downloadModal = new ModelDownloadModal();
            const isReady = await downloadModal.ensureModelReady(this.wdTaggerSettings.modelName);
            if (!isReady) return;

            // Model is ready, perform prediction
            await this.performWDPrediction(btn);

        } catch (e) {
            console.error('Error checking/downloading model:', e);
            app.showNotification(window.i18n.t('notifications.media.error_checking_ai_model', { error: e.message }), 'error');
        }
    },

    async performWDPrediction(btn) {
        this.setButtonState(btn, window.i18n.t('media.progress.predicting'), true);

        try {
            const res = await fetch(`/api/ai-tagger/predict/${this.mediaId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    general_threshold: this.wdTaggerSettings.generalThreshold,
                    character_threshold: this.wdTaggerSettings.characterThreshold,
                    model_name: this.wdTaggerSettings.modelName
                })
            });

            if (!res.ok) {
                const error = await res.json().catch(() => ({}));
                throw new Error(error.detail || 'Prediction failed');
            }

            const result = await res.json();

            // Get current tags from input
            const tagsInput = this.el('tags-input');
            const currentText = this.tagInputHelper.getPlainTextFromDiv(tagsInput).trim();
            const currentTags = currentText ? currentText.split(/\s+/) : [];
            const existingSet = new Set(currentTags.map(t => t.toLowerCase()));

            // Process predicted tags
            const predictedTags = result.tags
                .map(t => t.name.replace(/ /g, '_'))
                .filter(t => !existingSet.has(t.toLowerCase()));

            if (predictedTags.length === 0) {
                app.showNotification(window.i18n.t('notifications.media.no_new_tags_predicted'), 'info');
                this.setButtonState(btn, window.i18n.t('media.tags.predict_tags'), false);
                return;
            }

            // Validate predicted tags against database in batch
            this.setButtonState(btn, window.i18n.t('media.progress.validating'), true);

            const validTags = [];
            try {
                const results = await this.tagInputHelper.checkTagsBatch(predictedTags);
                for (const tag of predictedTags) {
                    const tagObj = results[tag.toLowerCase()];
                    if (tagObj && !existingSet.has(tagObj.name.toLowerCase())) {
                        validTags.push(tagObj.name);
                        existingSet.add(tagObj.name.toLowerCase());
                    }
                }
            } catch (e) {
                console.error('Error validating tags in batch:', e);
                // Fallback
                for (const tag of predictedTags) {
                    const validTag = await this.getTagOrAlias(tag);
                    if (validTag && !existingSet.has(validTag.toLowerCase())) {
                        validTags.push(validTag);
                        existingSet.add(validTag.toLowerCase());
                    }
                }
            }

            if (validTags.length === 0) {
                app.showNotification(window.i18n.t('notifications.media.no_valid_tags_predictions'), 'info');
            } else {
                const allTags = [...currentTags, ...validTags];
                tagsInput.textContent = allTags.join(' ');
                validTags.forEach(t => {
                    if (this.tagInputHelper) {
                        this.tagInputHelper.tagValidationCache.set(t.toLowerCase().trim(), true);
                    }
                });
                await this.validateAndStyleTags();
                this.updateSuggestedTags();
                app.showNotification(window.i18n.t('notifications.media.tags_added', { count: validTags.length }), 'success');
            }

        } catch (e) {
            console.error('Error predicting tags:', e);
            app.showNotification(window.i18n.t('notifications.media.error_predicting_tags', { error: e.message }), 'error');
        } finally {
            this.setButtonState(btn, window.i18n.t('media.tags.predict_tags'), false);
        }
    },

    // ==================== Tag Methods ====================

    async saveTags() {
        const tagsInput = this.el('tags-input');
        if (tagsInput && this.tagInputHelper) {
            this.tagInputHelper.pruneImpliedTags(tagsInput, this.impliedTagsMap, this.hiddenImpliedTags);
            await this.tagInputHelper.expandImplications(tagsInput, {
                extraTags: Array.from(this.hiddenImpliedTags || []),
                expandedTriggers: this.expandedTriggerTags,
                impliedTags: this.impliedTagsMap,
                onImplicationExpanded: (impliedByMap, impliedTags) => {
                    this.handleImplicationExpanded(impliedByMap, impliedTags);
                },
                hideImplied: this.tagInputHelper.isHideImpliedEnabled()
            });
        }
        const validTags = this.tagInputHelper.getValidTagsFromInput(tagsInput);
        const seenLower = new Set(validTags.map(t => t.toLowerCase().trim()));
        const finalTags = [...validTags];
        for (const hiddenLower of (this.hiddenImpliedTags || [])) {
            if (!seenLower.has(hiddenLower)) {
                seenLower.add(hiddenLower);
                finalTags.push(hiddenLower);
            }
        }

        const impliedTagsPayload = {};
        for (const tag of finalTags) {
            const lower = tag.toLowerCase().trim();
            if (this.impliedTagsMap && this.impliedTagsMap.has(lower)) {
                impliedTagsPayload[lower] = this.impliedTagsMap.get(lower) || [];
            }
        }

        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({
                    tags: finalTags,
                    implied_tags: impliedTagsPayload
                })
            });
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('notifications.media.error_updating_tags'));
        }
    },

    // ==================== AI Metadata Tags ====================

    async appendAITags() {
        const btn = this.el('append-ai-tags-btn');
        this.setButtonState(btn, window.i18n.t('common.processing'), true);

        try {
            const res = await fetch(`/api/media/${this.mediaId}/metadata`);
            if (!res.ok) {
                app.showNotification(window.i18n.t('notifications.media.could_not_load_ai_metadata'), 'error');
                return;
            }

            const metadata = await res.json();
            const aiPrompt = AITagUtils.extractAIPrompt(metadata);

            if (!aiPrompt || typeof aiPrompt !== 'string') {
                app.showNotification(window.i18n.t('notifications.media.no_ai_prompt'), 'error');
                return;
            }

            const promptTags = AITagUtils.extractPromptTags(metadata);

            const validTags = [];
            for (const tag of promptTags) {
                const validTag = await this.getTagOrAlias(tag);
                if (validTag) {
                    validTags.push(validTag);
                }
            }

            if (validTags.length === 0) {
                app.showNotification(window.i18n.t('notifications.media.no_valid_tags_ai_prompt'), 'error');
                return;
            }

            const tagsInput = this.el('tags-input');
            const currentText = this.tagInputHelper.getPlainTextFromDiv(tagsInput).trim();
            const currentTags = currentText ? currentText.split(/\s+/) : [];

            const existingTagsSet = new Set(currentTags.map(t => t.toLowerCase()));
            const newTags = validTags.filter(tag => !existingTagsSet.has(tag.toLowerCase()));

            if (newTags.length === 0) {
                app.showNotification(window.i18n.t('notifications.media.ai_tags_already_present'), 'info');
                return;
            }

            const allTags = [...currentTags, ...newTags];
            tagsInput.textContent = allTags.join(' ');

            newTags.forEach(t => {
                if (this.tagInputHelper) {
                    this.tagInputHelper.tagValidationCache.set(t.toLowerCase().trim(), true);
                }
            });

            await this.validateAndStyleTags();
            this.updateSuggestedTags();
            app.showNotification(window.i18n.t('media.ai_tags.appended_count', { count: newTags.length }), 'success');

        } catch (e) {
            console.error('Error appending AI tags:', e);
            app.showNotification(window.i18n.t('media.errors.processing_ai_tags', { error: e.message }), 'error');
        } finally {
            this.setButtonState(btn, window.i18n.t('media.tags.append_ai_tags'), false);
        }
    },
});
