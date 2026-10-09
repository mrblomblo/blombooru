class TagAutocomplete {
    constructor(input, options = {}) {
        this.input = input;
        this.isContentEditable = input.getAttribute('contenteditable') === 'true';
        this.options = {
            onSelect: null,
            multipleValues: false,
            containerClasses: '',
            appendSpace: true,
            allowCreate: false,
            enableQualifiers: false,
            ...options
        };

        this._qualifierCache = {};
        this._qualifierAbortController = null;
        this._qualifierDebounceTimer = null;

        this.setupAutocomplete();
    }

    setupAutocomplete() {
        // Create suggestions container
        this.suggestionsEl = document.createElement('div');

        // Build class list with base classes and optional extra classes
        this.suggestionsEl.className = this.options.containerClasses
            ? `tag-suggestions hidden ${this.options.containerClasses}`
            : 'tag-suggestions hidden';

        this.input.parentNode.insertBefore(this.suggestionsEl, this.input.nextSibling);

        // Store bound handlers for cleanup
        this.onInputBound = this.onInput.bind(this);
        this.onKeydownBound = this.onKeydown.bind(this);
        this.onDocumentClickBound = (e) => {
            if (!this.input.contains(e.target) && !this.suggestionsEl.contains(e.target)) {
                this.hideSuggestions();
            }
        };

        // Prevent the input from losing focus when clicking inside the suggestions dropdown
        this.suggestionsEl.addEventListener('mousedown', (e) => {
            e.preventDefault();
        });

        this.input.addEventListener('input', this.onInputBound);
        this.input.addEventListener('keydown', this.onKeydownBound);
        document.addEventListener('click', this.onDocumentClickBound);

        if (this.options.enableQualifiers) {
            this._prefetchQualifierExamples();
        }
    }

    async _prefetchQualifierExamples() {
        try {
            const res = await fetch('/api/search/qualifier-autocomplete?qualifier=album&limit=10');
            if (res.ok) {
                const data = await res.json();
                this._qualifierCache['album'] = data;
                this._qualifierCache['album_tree'] = data;
            }
        } catch (e) {
            // non-blocking
        }
    }

    async onInput() {
        const query = this.getCurrentQuery();
        this._currentQuery = query;
        if (query.length < 1) {
            this.hideSuggestions();
            return;
        }

        if (this.options.enableQualifiers) {
            const qualifierMatch = query.match(/^([~-]?)([a-zA-Z0-9_]+):(.*)$/);
            if (qualifierMatch) {
                const handled = this.handleQualifierInput(qualifierMatch, query);
                if (handled) return;
            }
        }

        try {
            const suggestions = await this.fetchSuggestions(query);
            if (this._currentQuery === query) {
                this.showSuggestions(suggestions, query);
            }
        } catch (error) {
            console.error('Error fetching suggestions:', error);
        }
    }

    getInputValue() {
        if (this.isContentEditable) {
            return this.input.textContent || '';
        }
        return this.input.value;
    }

    setInputValue(value) {
        if (this.isContentEditable) {
            this.input.textContent = value;
        } else {
            this.input.value = value;
        }
    }

    getCursorPosition() {
        if (this.isContentEditable) {
            const selection = window.getSelection();
            if (selection.rangeCount === 0) return 0;

            const range = selection.getRangeAt(0);
            const preCaretRange = range.cloneRange();
            preCaretRange.selectNodeContents(this.input);
            preCaretRange.setEnd(range.endContainer, range.endOffset);

            return preCaretRange.toString().length;
        }
        return this.input.selectionStart;
    }

    setCursorPosition(position) {
        if (this.isContentEditable) {
            const selection = window.getSelection();
            const range = document.createRange();

            let currentOffset = 0;
            let found = false;

            const traverseNodes = (node) => {
                if (found) return;

                if (node.nodeType === Node.TEXT_NODE) {
                    const nodeLength = node.textContent.length;
                    if (currentOffset + nodeLength >= position) {
                        range.setStart(node, position - currentOffset);
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
                traverseNodes(this.input);
                if (!found && this.input.lastChild) {
                    range.setStartAfter(this.input.lastChild);
                    range.collapse(true);
                }
                selection.removeAllRanges();
                selection.addRange(range);
            } catch (e) {
                console.error('Error setting cursor:', e);
            }
        } else {
            this.input.setSelectionRange(position, position);
        }
    }

    getCurrentQuery() {
        if (!this.options.multipleValues) {
            return this.getInputValue().trim();
        }

        const cursorPos = this.getCursorPosition();
        const value = this.getInputValue();
        const beforeCursor = value.substring(0, cursorPos);
        const lastSpace = beforeCursor.lastIndexOf(' ');
        return beforeCursor.substring(lastSpace + 1).trim();
    }

    async fetchSuggestions(query) {
        const response = await fetch(`/api/tags/autocomplete?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('Failed to fetch suggestions');
        return response.json();
    }

    showSuggestions(suggestions, query) {
        const hasResults = suggestions.length > 0;

        const isQualifier = suggestions.some(t => t.is_qualifier);
        const normalizedQuery = query ? query.toLowerCase().replace(/ /g, '_') : '';
        const exactMatchExists = suggestions.some(t => t.name === normalizedQuery || (t.is_alias && t.alias_name === normalizedQuery));
        const hasCreate = !isQualifier && this.options.allowCreate && query && query.length > 0 && !exactMatchExists;

        if (!hasResults && !hasCreate) {
            this.hideSuggestions();
            return;
        }

        let html = '';

        if (hasResults) {
            html = suggestions.map((tag, index) => {
                if (tag.is_alias) {
                    return `
                    <div class="tag-suggestion tag-alias-info" data-index="${index}" data-name="${escapeHtml(tag.name)}">
                        <span style="display: flex; align-items: center; gap: 0.5rem;">
                            <span class="text-secondary italic">${escapeHtml(tag.alias_name)}</span>
                            <span class="text-secondary">&#8594;</span>
                            <span class="tag-name">${escapeHtml(tag.name)}</span>
                        </span>
                        ${tag.count !== undefined && tag.count !== null && tag.count !== '' ? `<span class="tag-count">${escapeHtml(String(tag.count))}</span>` : ''}
                    </div>
                `;
                }
                if (tag.is_qualifier) {
                    const qualifierPart = tag.qualifier_prefix || (tag.name.includes(':') ? tag.name.substring(0, tag.name.indexOf(':') + 1) : tag.name);
                    const valPart = tag.val !== undefined ? tag.val : (tag.name.includes(':') ? tag.name.substring(tag.name.indexOf(':') + 1) : '');
                    const detailPart = tag.detail ? `<span class="tag-count">${escapeHtml(tag.detail)}</span>` : '';
                    return `
                    <div class="tag-suggestion" data-index="${index}" data-name="${escapeHtml(tag.name)}">
                        <span class="tag-name"><code class="bg p-0 font-mono text-xs">${escapeHtml(qualifierPart)}</code>${escapeHtml(valPart)}</span>
                        ${detailPart}
                    </div>
                `;
                }
                return `
                <div class="tag-suggestion" data-index="${index}" data-name="${escapeHtml(tag.name)}">
                    <span>
                        <span class="tag-category"><span class="tag-text ${escapeHtml(tag.category)}">${escapeHtml(tag.category)}</span></span>
                        <span class="tag-name">${escapeHtml(tag.name)}</span>
                    </span>
                    ${tag.count !== undefined && tag.count !== null && tag.count !== '' ? `<span class="tag-count">${escapeHtml(String(tag.count))}</span>` : ''}
                </div>
            `;
            }).join('');
        }

        // Append the "Add new tag" sentinel row when allowCreate is enabled
        if (hasCreate) {
            const createIndex = suggestions.length;
            const queryStr = query.replace(/ /g, '_');
            const escapedQuery = escapeHtml(queryStr);
            const createText = window.i18n.t('admin.tags_management.create_tag');
            html += `
                <div class="tag-suggestion tag-create-new" data-index="${createIndex}" data-name="__create__" data-query="${escapedQuery}">
                    <span>
                        <span class="tag-category"><span class="tag-text meta">${escapeHtml(createText)}</span></span>
                        <span class="tag-name">${escapedQuery}</span>
                    </span>
                    <span class="tag-count">+</span>
                </div>
            `;
        }

        this.suggestionsEl.innerHTML = html;
        this.suggestionsEl.classList.remove('hidden');

        // Add click handlers
        this.suggestionsEl.querySelectorAll('.tag-suggestion').forEach(el => {
            el.addEventListener('click', (e) => {
                e.preventDefault();
                if (el.dataset.name === '__create__') {
                    this.hideSuggestions();
                    // Save current cursor position so it can be restored if the modal is cancelled
                    const savedRange = (this.isContentEditable && window.getSelection().rangeCount > 0)
                        ? window.getSelection().getRangeAt(0).cloneRange()
                        : null;
                    this._openCreateModal(el.dataset.query || this.getCurrentQuery().replace(/ /g, '_'), savedRange);
                } else {
                    this.selectSuggestion(el.dataset.name);
                }
            });
        });
    }

    hideSuggestions() {
        this.suggestionsEl.classList.add('hidden');
        this.suggestionsEl.querySelectorAll('.tag-suggestion.selected').forEach(el => {
            el.classList.remove('selected');
        });
    }

    selectSuggestion(tagName) {
        if (!this.options.multipleValues) {
            this.setInputValue(tagName);
        } else {
            const cursorPos = this.getCursorPosition();
            const value = this.getInputValue();
            const beforeCursor = value.substring(0, cursorPos);
            const afterCursor = value.substring(cursorPos);
            const lastSpace = beforeCursor.lastIndexOf(' ');
            const shouldAppendSpace = this.options.appendSpace;
            const suffix = (shouldAppendSpace && !afterCursor.startsWith(' ')) ? ' ' : '';

            const newValue = lastSpace === -1
                ? tagName + suffix + afterCursor
                : beforeCursor.substring(0, lastSpace + 1) + tagName + suffix + afterCursor;

            this.setInputValue(newValue);

            // Set cursor position after the inserted tag and advance cursor past any appended space
            const increment = shouldAppendSpace ? 1 : 0;
            const newCursorPos = lastSpace === -1
                ? tagName.length + increment
                : lastSpace + 1 + tagName.length + increment;
            this.setCursorPosition(newCursorPos);

            // Trigger input event for validation
            const event = new Event('input', { bubbles: true });
            this.input.dispatchEvent(event);
        }

        this.hideSuggestions();
        this.input.focus();

        if (this.options.onSelect) {
            this.options.onSelect(tagName);
        }
    }

    // Replace the current in-progress word in the input with the created tag name and append a trailing space
    _replaceCurrentQuery(tagName) {
        if (!this.options.multipleValues) {
            this.setInputValue(tagName);
            return;
        }

        const cursorPos = this.getCursorPosition();
        const value = this.getInputValue();

        const beforeCursor = value.substring(0, cursorPos);
        const lastSpace = beforeCursor.lastIndexOf(' ');
        const startIndex = lastSpace === -1 ? 0 : lastSpace + 1;

        let endSpace = value.indexOf(' ', cursorPos);
        if (endSpace === -1) endSpace = value.length;

        const beforeWord = value.substring(0, startIndex);
        const afterWord = value.substring(endSpace).trimStart();

        const newValue = beforeWord + tagName + ' ' + afterWord;

        this.setInputValue(newValue);
        this.setCursorPosition(startIndex + tagName.length + 1);
    }

    _openCreateModal(initialName, savedRange = null) {
        const existing = document.getElementById('tag-autocomplete-create-modal');
        if (existing) existing.remove();

        const categories = [
            { value: 'general', label: window.i18n.t('common.tag_category_general') },
            { value: 'artist', label: window.i18n.t('common.tag_category_artist') },
            { value: 'character', label: window.i18n.t('common.tag_category_character') },
            { value: 'copyright', label: window.i18n.t('common.tag_category_copyright') },
            { value: 'meta', label: window.i18n.t('common.tag_category_meta') },
        ];

        const categoryOptions = categories.map(c =>
            `<div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="${c.value}">${escapeHtml(c.label)}</div>`
        ).join('');

        const titleText = window.i18n.t('admin.tags_management.create_tag');
        const nameLabel = window.i18n.t('admin.tags_management.tag_name');
        const categoryLabel = window.i18n.t('admin.tags_management.tag_category');
        const createText = window.i18n.t('admin.tags_management.create_tag_submit');
        const cancelText = window.i18n.t('common.cancel');
        const tagExistsError = window.i18n.t('notifications.admin.tag_name_conflict');
        const generalLabel = categories[0].label;

        const modal = document.createElement('div');
        modal.id = 'tag-autocomplete-create-modal';
        modal.className = 'age-verification-overlay';
        modal.style.display = 'flex';

        modal.innerHTML = `
            <div class="surface border-2 border-primary p-8 max-w-md w-full">
                <h2 class="text-xl font-bold mb-6 text-primary text-center">${escapeHtml(titleText)}</h2>

                <div class="mb-4">
                    <label class="block text-xs font-bold mb-2">${escapeHtml(nameLabel)}</label>
                    <input type="text" id="tag-create-name" value="${escapeHtml(initialName)}"
                        class="w-full bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary"
                        autocomplete="off" spellcheck="false">
                    <p id="tag-create-name-error" class="text-xs text-danger mt-1" style="display:none;"></p>
                </div>

                <div class="mb-6">
                    <label class="block text-xs font-bold mb-2">${escapeHtml(categoryLabel)}</label>
                    <div id="tag-create-category-select" class="custom-select w-full" data-value="general">
                        <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors focus:border-primary" type="button">
                            <span class="custom-select-value text">${escapeHtml(generalLabel)}</span>
                            ${window.Icons.selectArrow({ size: 12 })}
                        </button>
                        <div class="custom-select-dropdown bg border border-primary max-h-60 overflow-y-auto shadow-lg">
                            ${categoryOptions}
                        </div>
                    </div>
                </div>

                <div class="flex gap-3 justify-center">
                    <button id="tag-create-submit" class="btn-primary px-6 py-3 font-bold text-sm flex-1 cursor-pointer">
                        ${escapeHtml(createText)}
                    </button>
                    <button id="tag-create-cancel" class="btn px-6 py-3 font-bold text-sm flex-1 cursor-pointer">
                        ${escapeHtml(cancelText)}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const categorySelectEl = document.getElementById('tag-create-category-select');
        const categorySelect = (typeof CustomSelect !== 'undefined') ? new CustomSelect(categorySelectEl) : null;

        const nameInput = document.getElementById('tag-create-name');
        const nameError = document.getElementById('tag-create-name-error');

        const submitBtn = document.getElementById('tag-create-submit');

        let _verifyTimer = null;
        let _tagAlreadyExists = false;

        const verifyNameUnique = (value) => {
            clearTimeout(_verifyTimer);
            const normalized = value.trim().toLowerCase().replace(/\s+/g, '_');
            if (!normalized) {
                _tagAlreadyExists = false;
                nameError.style.display = 'none';
                submitBtn.disabled = false;
                submitBtn.style.opacity = '1';
                return;
            }
            _verifyTimer = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/tags/autocomplete?q=${encodeURIComponent(normalized)}`);
                    if (res.ok) {
                        const results = await res.json();
                        const exists = results.some(t => t.name === normalized || (t.is_alias && t.alias_name === normalized));
                        _tagAlreadyExists = exists;
                        if (exists) {
                            nameError.textContent = tagExistsError;
                            nameError.style.display = '';
                            submitBtn.disabled = true;
                            submitBtn.style.opacity = '0.6';
                        } else {
                            nameError.style.display = 'none';
                            submitBtn.disabled = false;
                            submitBtn.style.opacity = '1';
                        }
                    }
                } catch (_) { /* ignore network errors */ }
            }, 300);
        };

        // Normalise name as user types (spaces -> underscores) and verify uniqueness
        nameInput.addEventListener('input', () => {
            const pos = nameInput.selectionStart;
            nameInput.value = nameInput.value.replace(/ /g, '_');
            nameInput.setSelectionRange(pos, pos);
            nameError.style.display = 'none';
            verifyNameUnique(nameInput.value);
        });

        verifyNameUnique(nameInput.value);

        nameInput.focus();
        nameInput.select();

        const closeModal = () => {
            modal.remove();
            document.removeEventListener('keydown', handleEscape);
            this.input.focus();
            // Restore cursor position to where it was before the modal opened
            if (savedRange && this.isContentEditable) {
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(savedRange);
            }
        };

        const doCreate = async () => {
            const newName = nameInput.value.trim().toLowerCase().replace(/\s+/g, '_');
            if (!newName) {
                nameError.textContent = nameLabel;
                nameError.style.display = '';
                return;
            }

            const newCategory = categorySelect ? categorySelect.getValue() : 'general';

            const submitBtn = document.getElementById('tag-create-submit');
            if (submitBtn) { submitBtn.disabled = true; submitBtn.style.opacity = '0.6'; }

            try {
                const res = await fetch('/api/tags/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName, category: newCategory })
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || `HTTP ${res.status}`);
                }

                closeModal();
                this._replaceCurrentQuery(newName);

                const event = new Event('input', { bubbles: true });
                this.input.dispatchEvent(event);

                window.dispatchEvent(new CustomEvent('tagCreated', { detail: { name: newName } }));

                if (this.options.onSelect) {
                    this.options.onSelect(newName);
                }

                if (window.i18n && window.i18n.t && typeof app !== 'undefined' && app.showNotification) {
                    app.showNotification(
                        window.i18n.t('notifications.admin.tag_created', { name: newName }),
                        'success'
                    );
                }
            } catch (e) {
                nameError.textContent = e.message;
                nameError.style.display = '';
                if (submitBtn) { submitBtn.disabled = false; submitBtn.style.opacity = '1'; }
            }
        };

        const handleEscape = (e) => {
            if (e.key === 'Escape') closeModal();
        };

        document.getElementById('tag-create-submit').addEventListener('click', doCreate);
        document.getElementById('tag-create-cancel').addEventListener('click', closeModal);

        nameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); doCreate(); }
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        document.addEventListener('keydown', handleEscape);
    }

    onKeydown(e) {
        const suggestions = this.suggestionsEl.querySelectorAll('.tag-suggestion');

        // If suggestions are not visible, don't handle keyboard events
        if (this.suggestionsEl.classList.contains('hidden') || suggestions.length === 0) {
            return;
        }

        const selected = this.suggestionsEl.querySelector('.tag-suggestion.selected');
        const selectedIndex = selected ? parseInt(selected.dataset.index) : -1;

        const kb = window.keybindings;
        if (kb.matches(e, 'tag_suggestion_next')) {
            e.preventDefault();
            if (suggestions.length > 0) {
                if (selected) selected.classList.remove('selected');
                const nextIndex = selectedIndex < suggestions.length - 1 ? selectedIndex + 1 : 0;
                suggestions[nextIndex].classList.add('selected');
                suggestions[nextIndex].scrollIntoView({ block: 'nearest' });
            }
            return;
        }

        if (kb.matches(e, 'tag_suggestion_prev')) {
            e.preventDefault();
            if (suggestions.length > 0) {
                if (selected) selected.classList.remove('selected');
                const prevIndex = selectedIndex > 0 ? selectedIndex - 1 : suggestions.length - 1;
                suggestions[prevIndex].classList.add('selected');
                suggestions[prevIndex].scrollIntoView({ block: 'nearest' });
            }
            return;
        }

        switch (e.key) {
            case 'Tab':
                e.preventDefault();
                if (suggestions.length > 0) {
                    if (selected) selected.classList.remove('selected');
                    const nextIndex = selectedIndex < suggestions.length - 1 ? selectedIndex + 1 : 0;
                    suggestions[nextIndex].classList.add('selected');
                    suggestions[nextIndex].scrollIntoView({ block: 'nearest' });
                }
                break;

            case 'Enter':
                if (selected) {
                    e.preventDefault();
                    if (selected.dataset.name === '__create__') {
                        this.hideSuggestions();
                        const savedRangeKb = (this.isContentEditable && window.getSelection().rangeCount > 0)
                            ? window.getSelection().getRangeAt(0).cloneRange()
                            : null;
                        this._openCreateModal(selected.dataset.query || this.getCurrentQuery().replace(/ /g, '_'), savedRangeKb);
                    } else {
                        this.selectSuggestion(selected.dataset.name);
                    }
                }
                break;

            case 'Escape':
                e.preventDefault();
                this.hideSuggestions();
                break;
        }
    }

    handleQualifierInput(match, query) {
        const prefix = match[1] || '';
        const rawKey = match[2].toLowerCase();
        const valFilter = match[3];

        const canonicalKey = TagAutocomplete.QUALIFIERS[rawKey]
            ? rawKey
            : TagAutocomplete.QUALIFIER_ALIASES[rawKey];

        if (!canonicalKey || !TagAutocomplete.QUALIFIERS[canonicalKey]) {
            return false;
        }

        const isEntity = TagAutocomplete.ENTITY_QUALIFIERS && TagAutocomplete.ENTITY_QUALIFIERS.has(canonicalKey);

        if (isEntity) {
            this.handleEntityQualifierInput(canonicalKey, prefix, rawKey, valFilter, query);
        } else {
            const suggestions = this.getStaticQualifierSuggestions(canonicalKey, prefix, rawKey, valFilter, query);
            if (suggestions && suggestions.length > 0) {
                this.showSuggestions(suggestions, query);
            } else {
                this.hideSuggestions();
            }
        }
        return true;
    }

    handleEntityQualifierInput(canonicalKey, prefix, rawKey, valFilter, query) {
        // Fast local suggestions for instant UX
        const immediate = this.getImmediateEntitySuggestions(canonicalKey, prefix, rawKey, valFilter);
        if (immediate && immediate.length > 0) {
            this.showSuggestions(immediate, query);
        }

        if (this._qualifierDebounceTimer) {
            clearTimeout(this._qualifierDebounceTimer);
        }

        this._qualifierDebounceTimer = setTimeout(async () => {
            if (this._qualifierAbortController) {
                this._qualifierAbortController.abort();
            }
            this._qualifierAbortController = new AbortController();

            try {
                const suggestions = await this.fetchQualifierSuggestions(
                    canonicalKey,
                    prefix,
                    rawKey,
                    valFilter,
                    query,
                    this._qualifierAbortController.signal
                );
                if (suggestions && this._currentQuery === query) {
                    this.showSuggestions(suggestions, query);
                }
            } catch (e) {
                if (e.name !== 'AbortError') {
                    console.error('Error fetching qualifier suggestions:', e);
                }
            }
        }, 150);
    }

    _parseQualifierValue(canonicalKey, valFilter) {
        const str = (valFilter || '');
        const lastCommaIdx = str.lastIndexOf(',');

        let prefixBeforeCurrent = '';
        let currentRaw = str;
        const usedValues = new Set();

        if (lastCommaIdx !== -1) {
            prefixBeforeCurrent = str.substring(0, lastCommaIdx + 1);
            currentRaw = str.substring(lastCommaIdx + 1);

            const previousTokens = str.substring(0, lastCommaIdx).split(',');
            for (const token of previousTokens) {
                const trimmed = token.trim();
                if (!trimmed) continue;
                const lower = trimmed.toLowerCase();
                usedValues.add(lower);
                usedValues.add(lower.replace(/_/g, ' '));
                usedValues.add(lower.replace(/ /g, '_'));

                const strippedOp = lower.replace(/^[><=!]{1,3}/, '');
                if (strippedOp && strippedOp !== lower) {
                    usedValues.add(strippedOp);
                }
            }
        }

        if (canonicalKey === 'album' || canonicalKey === 'album_tree') {
            const cached = this._qualifierCache['album'] || this._qualifierCache[canonicalKey] || [];
            for (const item of cached) {
                const idStr = String(item.id || '');
                const valLower = (item.value || '').toLowerCase();
                const labelLower = (item.label || '').toLowerCase();

                let matchesUsed = false;
                if (idStr && usedValues.has(idStr)) matchesUsed = true;
                if (valLower && (usedValues.has(valLower) || usedValues.has(valLower.replace(/_/g, ' ')))) matchesUsed = true;
                if (labelLower && usedValues.has(labelLower)) matchesUsed = true;

                if (matchesUsed) {
                    if (idStr) usedValues.add(idStr);
                    if (valLower) {
                        usedValues.add(valLower);
                        usedValues.add(valLower.replace(/_/g, ' '));
                        usedValues.add(valLower.replace(/ /g, '_'));
                    }
                    if (labelLower) usedValues.add(labelLower);
                }
            }
        } else if (canonicalKey === 'rating') {
            const ratingEquivs = {
                's': 'safe', 'safe': 's',
                'q': 'questionable', 'questionable': 'q',
                'e': 'explicit', 'explicit': 'e',
                'g': 'general', 'general': 'g'
            };
            const toAdd = [];
            for (const val of usedValues) {
                if (ratingEquivs[val]) toAdd.push(ratingEquivs[val]);
            }
            for (const val of toAdd) usedValues.add(val);
        }

        return {
            prefixBeforeCurrent,
            currentRaw,
            usedValues
        };
    }

    _isQualifierValueUsed(itemOrVal, usedValues) {
        if (!usedValues || usedValues.size === 0) return false;

        if (typeof itemOrVal === 'string') {
            const val = itemOrVal.trim();
            const lower = val.toLowerCase();
            if (usedValues.has(lower)) return true;
            if (usedValues.has(lower.replace(/_/g, ' '))) return true;
            if (usedValues.has(lower.replace(/ /g, '_'))) return true;

            const strippedOp = lower.replace(/^[><=!]{1,3}/, '');
            if (strippedOp && usedValues.has(strippedOp)) return true;

            if (val.includes(',')) {
                const parts = val.split(',');
                if (parts.some(p => {
                    const pLower = p.trim().toLowerCase();
                    return usedValues.has(pLower) || usedValues.has(pLower.replace(/^[><=!]{1,3}/, ''));
                })) {
                    return true;
                }
            }
            return false;
        }

        if (typeof itemOrVal === 'object' && itemOrVal !== null) {
            const v = (itemOrVal.value || '').toLowerCase();
            const l = (itemOrVal.label || '').toLowerCase();
            const id = itemOrVal.id !== undefined && itemOrVal.id !== null ? String(itemOrVal.id) : '';

            if (v && (usedValues.has(v) || usedValues.has(v.replace(/_/g, ' ')))) return true;
            if (l && (usedValues.has(l) || usedValues.has(l.replace(/ /g, '_')))) return true;
            if (id && usedValues.has(id)) return true;

            if (itemOrVal.detail) {
                const m = itemOrVal.detail.match(/ID:?\s*(\d+)/i);
                if (m && usedValues.has(m[1])) return true;
            }
        }
        return false;
    }

    _formatQualifierDetail(item) {
        if (!item) return '';
        if (item.id !== undefined && item.id !== null) {
            let idText = `ID ${item.id}`;
            if (window.i18n && typeof window.i18n.t === 'function') {
                idText = window.i18n.t('media.relations.parent_id_link', { id: item.id });
            }
            if (item.count !== undefined && item.count !== null && item.count !== '') {
                return `${idText} (${item.count})`;
            }
            return idText;
        }
        return item.detail || '';
    }

    getImmediateEntitySuggestions(canonicalKey, prefix, rawKey, valFilter) {
        const qualifierPrefix = `${prefix}${rawKey}:`;
        const { prefixBeforeCurrent, currentRaw, usedValues } = this._parseQualifierValue(canonicalKey, valFilter);

        const OP_REGEX = /^(.*(?:\.\.|>=|<=|>|<|!=|=<|=>))(.*)$/;
        const opMatch = currentRaw.trim().match(OP_REGEX);
        const hasOp = !!opMatch;
        const operator = hasOp ? opMatch[1] : '';
        const searchTerm = (hasOp ? opMatch[2] : currentRaw).trim().toLowerCase();
        const basePrefix = `${qualifierPrefix}${prefixBeforeCurrent}${operator}`;

        const cached = this._qualifierCache['album'] || this._qualifierCache[canonicalKey] || [];

        const hasExistingValue = !!prefixBeforeCurrent || usedValues.size > 0;
        const allowSpecialKeywords = !hasOp && !hasExistingValue;
        const keywordMatches = [];
        if (allowSpecialKeywords) {
            if (!this._isQualifierValueUsed('any', usedValues) && (!searchTerm || 'any'.startsWith(searchTerm))) {
                keywordMatches.push({
                    name: `${basePrefix}any`,
                    qualifier_prefix: qualifierPrefix,
                    val: `${prefixBeforeCurrent}any`,
                    is_qualifier: true
                });
            }
            if (!this._isQualifierValueUsed('none', usedValues) && (!searchTerm || 'none'.startsWith(searchTerm))) {
                keywordMatches.push({
                    name: `${basePrefix}none`,
                    qualifier_prefix: qualifierPrefix,
                    val: `${prefixBeforeCurrent}none`,
                    is_qualifier: true
                });
            }
        }

        const filteredCache = cached.filter(ex => !this._isQualifierValueUsed(ex, usedValues));

        if (!searchTerm && filteredCache.length > 0) {
            const cachedList = filteredCache.map(ex => ({
                name: `${basePrefix}${ex.value}`,
                qualifier_prefix: qualifierPrefix,
                val: `${prefixBeforeCurrent}${operator}${ex.value}`,
                label: ex.label,
                id: ex.id,
                count: ex.count,
                detail: this._formatQualifierDetail(ex),
                is_qualifier: true
            }));
            return [...keywordMatches, ...cachedList];
        }

        if (searchTerm && filteredCache.length > 0) {
            const matched = filteredCache.filter(ex => {
                const vLower = (ex.value || '').toLowerCase();
                const lLower = (ex.label || '').toLowerCase();
                const idStr = String(ex.id || '');
                return vLower.startsWith(searchTerm) || lLower.startsWith(searchTerm) ||
                       vLower.includes(searchTerm) || lLower.includes(searchTerm) ||
                       (idStr && idStr === searchTerm);
            });

            if (matched.length > 0) {
                const matchedList = matched.map(ex => ({
                    name: `${basePrefix}${ex.value}`,
                    qualifier_prefix: qualifierPrefix,
                    val: `${prefixBeforeCurrent}${operator}${ex.value}`,
                    label: ex.label,
                    id: ex.id,
                    count: ex.count,
                    detail: this._formatQualifierDetail(ex),
                    is_qualifier: true
                }));
                return [...keywordMatches, ...matchedList];
            }
        }

        if (keywordMatches.length > 0) {
            return keywordMatches;
        }

        return null;
    }

    async fetchQualifierSuggestions(canonicalKey, prefix, rawKey, valFilter, query, signal) {
        const qualifierPrefix = `${prefix}${rawKey}:`;
        const { prefixBeforeCurrent, currentRaw, usedValues } = this._parseQualifierValue(canonicalKey, valFilter);

        const OP_REGEX = /^(.*(?:\.\.|>=|<=|>|<|!=|=<|=>))(.*)$/;
        const opMatch = currentRaw.trim().match(OP_REGEX);
        const hasOp = !!opMatch;
        const operator = hasOp ? opMatch[1] : '';
        const searchTerm = (hasOp ? opMatch[2] : currentRaw).trim();
        const basePrefix = `${qualifierPrefix}${prefixBeforeCurrent}${operator}`;

        if (!this._qualifierCache[canonicalKey] && !this._qualifierCache['album']) {
            try {
                const initRes = await fetch(`/api/search/qualifier-autocomplete?qualifier=album&limit=10`, { signal });
                if (initRes.ok) {
                    const data = await initRes.json();
                    this._qualifierCache['album'] = data;
                    this._qualifierCache['album_tree'] = data;
                }
            } catch (e) {
                if (e.name === 'AbortError') throw e;
            }
        }
        const cached = this._qualifierCache['album'] || this._qualifierCache[canonicalKey] || [];
        const initialExamples = cached.filter(ex => !this._isQualifierValueUsed(ex, usedValues));

        const hasExistingValue = !!prefixBeforeCurrent || usedValues.size > 0;
        const allowSpecialKeywords = !hasOp && !hasExistingValue;

        const buildFallback = (targetBase) => {
            const list = [];
            if (allowSpecialKeywords) {
                if (!this._isQualifierValueUsed('any', usedValues)) {
                    list.push({
                        name: `${targetBase}any`,
                        qualifier_prefix: qualifierPrefix,
                        val: `${prefixBeforeCurrent}${operator}any`,
                        is_qualifier: true
                    });
                }
                if (!this._isQualifierValueUsed('none', usedValues)) {
                    list.push({
                        name: `${targetBase}none`,
                        qualifier_prefix: qualifierPrefix,
                        val: `${prefixBeforeCurrent}${operator}none`,
                        is_qualifier: true
                    });
                }
            }
            for (const ex of initialExamples) {
                list.push({
                    name: `${targetBase}${ex.value}`,
                    qualifier_prefix: qualifierPrefix,
                    val: `${prefixBeforeCurrent}${operator}${ex.value}`,
                    label: ex.label,
                    id: ex.id,
                    count: ex.count,
                    detail: this._formatQualifierDetail(ex),
                    is_qualifier: true
                });
            }
            return list;
        };

        if (!searchTerm) {
            return buildFallback(basePrefix);
        }

        let apiResults = [];
        try {
            let url = `/api/search/qualifier-autocomplete?qualifier=${encodeURIComponent(canonicalKey)}&q=${encodeURIComponent(searchTerm)}&limit=10`;
            if (usedValues.size > 0) {
                const excludeParam = Array.from(usedValues).join(',');
                url += `&exclude=${encodeURIComponent(excludeParam)}`;
            }
            const res = await fetch(url, { signal });
            if (res.ok) {
                apiResults = await res.json();
            }
        } catch (e) {
            if (e.name === 'AbortError') throw e;
        }

        const keywordMatches = [];
        if (allowSpecialKeywords) {
            const sLower = searchTerm.toLowerCase();
            if (!this._isQualifierValueUsed('any', usedValues) && 'any'.startsWith(sLower)) {
                keywordMatches.push({
                    name: `${basePrefix}any`,
                    qualifier_prefix: qualifierPrefix,
                    val: `${prefixBeforeCurrent}${operator}any`,
                    is_qualifier: true
                });
            }
            if (!this._isQualifierValueUsed('none', usedValues) && 'none'.startsWith(sLower)) {
                keywordMatches.push({
                    name: `${basePrefix}none`,
                    qualifier_prefix: qualifierPrefix,
                    val: `${prefixBeforeCurrent}${operator}none`,
                    is_qualifier: true
                });
            }
        }

        const filteredApiResults = apiResults.filter(item => !this._isQualifierValueUsed(item, usedValues));

        if (filteredApiResults.length > 0 || keywordMatches.length > 0) {
            const mapped = filteredApiResults.map(item => ({
                name: `${basePrefix}${item.value}`,
                qualifier_prefix: qualifierPrefix,
                val: `${prefixBeforeCurrent}${operator}${item.value}`,
                label: item.label,
                id: item.id,
                count: item.count,
                detail: this._formatQualifierDetail(item),
                is_qualifier: true
            }));
            return [...keywordMatches, ...mapped];
        }

        // If no results are found, show the initial examples without broken text concatenation
        return buildFallback(basePrefix);
    }

    getStaticQualifierSuggestions(canonicalKey, prefix, rawKey, valFilter, query) {
        const qualifierPrefix = `${prefix}${rawKey}:`;
        const { prefixBeforeCurrent, currentRaw, usedValues } = this._parseQualifierValue(canonicalKey, valFilter);
        const rawItems = TagAutocomplete.QUALIFIERS[canonicalKey] || [];
        const hasExistingValue = !!prefixBeforeCurrent || usedValues.size > 0;

        const items = rawItems.filter(val => {
            if (prefixBeforeCurrent && val.includes(',')) return false;
            if (hasExistingValue && (val === 'any' || val === 'none')) return false;
            return !this._isQualifierValueUsed(val, usedValues);
        });

        const valTrimmed = currentRaw.trim();
        const valLower = valTrimmed.toLowerCase();
        const basePrefix = `${qualifierPrefix}${prefixBeforeCurrent}`;

        const buildList = (list, op = '') => list.map(val => ({
            name: `${basePrefix}${op}${val}`,
            qualifier_prefix: qualifierPrefix,
            val: `${prefixBeforeCurrent}${op}${val}`,
            is_qualifier: true
        }));

        if (!valLower) {
            return buildList(items);
        }

        let matched = items.filter(val => {
            const itemLower = val.toLowerCase();
            return itemLower.startsWith(valLower) || itemLower.includes(valLower);
        });

        if (matched.length > 0) {
            matched.sort((a, b) => {
                const aVal = a.toLowerCase();
                const bVal = b.toLowerCase();
                const aStarts = aVal.startsWith(valLower) ? 0 : 1;
                const bStarts = bVal.startsWith(valLower) ? 0 : 1;
                if (aStarts !== bStarts) return aStarts - bStarts;
                return 0;
            });
            return buildList(matched);
        }

        const OP_REGEX = /^(.*(?:\.\.|>=|<=|>|<|!=|=<|=>))(.*)$/;
        const opMatch = valTrimmed.match(OP_REGEX);
        if (opMatch) {
            const operator = opMatch[1];
            const searchTerm = opMatch[2].toLowerCase();

            if (searchTerm) {
                const opMatched = items.filter(val => {
                    const stripped = val.replace(/^[><=!]{1,3}/, '').toLowerCase();
                    return stripped.startsWith(searchTerm) || stripped.includes(searchTerm);
                });
                if (opMatched.length > 0) {
                    return opMatched.map(val => {
                        const cleanVal = val.replace(/^[><=!]{1,3}/, '');
                        return {
                            name: `${basePrefix}${operator}${cleanVal}`,
                            qualifier_prefix: qualifierPrefix,
                            val: `${prefixBeforeCurrent}${operator}${cleanVal}`,
                            is_qualifier: true
                        };
                    });
                }
            }
        }

        // No match -- show the available items for this qualifier (excluding already used ones)
        return buildList(items);
    }

    getQualifierSuggestions(query) {
        if (!query) return null;
        const match = query.match(/^([~-]?)([a-zA-Z0-9_]+):(.*)$/);
        if (!match) return null;
        const prefix = match[1] || '';
        const rawKey = match[2].toLowerCase();
        const valFilter = match[3];
        const canonicalKey = TagAutocomplete.QUALIFIERS[rawKey] ? rawKey : TagAutocomplete.QUALIFIER_ALIASES[rawKey];
        if (!canonicalKey || !TagAutocomplete.QUALIFIERS[canonicalKey]) return null;
        if (TagAutocomplete.ENTITY_QUALIFIERS && TagAutocomplete.ENTITY_QUALIFIERS.has(canonicalKey)) {
            return this.getImmediateEntitySuggestions(canonicalKey, prefix, rawKey, valFilter) || [];
        }
        return this.getStaticQualifierSuggestions(canonicalKey, prefix, rawKey, valFilter, query);
    }

    destroy() {
        if (this._qualifierDebounceTimer) {
            clearTimeout(this._qualifierDebounceTimer);
            this._qualifierDebounceTimer = null;
        }
        if (this._qualifierAbortController) {
            this._qualifierAbortController.abort();
            this._qualifierAbortController = null;
        }
        if (this.onInputBound) {
            this.input.removeEventListener('input', this.onInputBound);
        }
        if (this.onKeydownBound) {
            this.input.removeEventListener('keydown', this.onKeydownBound);
        }
        if (this.onDocumentClickBound) {
            document.removeEventListener('click', this.onDocumentClickBound);
        }

        if (this.suggestionsEl && this.suggestionsEl.parentNode) {
            this.suggestionsEl.parentNode.removeChild(this.suggestionsEl);
        }
    }
}

TagAutocomplete.ENTITY_QUALIFIERS = new Set(['album', 'album_tree']);

TagAutocomplete.QUALIFIERS = {
    child: ['any', 'none', '123', '>100', '1..100'],
    parent: ['none', 'any', '100', '>100', '1..100'],
    album: ['any', 'none'],
    album_tree: ['any', 'none'],
    rating: ['s', 'q', 'e', 'safe', 'questionable', 'explicit', 's,q'],
    tagcount: ['>20', '>=5', '<10', '<=15', '0', '1..10', '!=0'],
    gentags: ['>10', '>=4', '<8', '0', '1..5'],
    arttags: ['0', '>1', '>=1', '1..3'],
    chartags: ['>2', '0', '>=1', '1..5'],
    copytags: ['>1', '0', '>=1', '1..3'],
    metatags: ['>0', '0', '>=1', '1..5'],
    filetype: ['png', 'jpg', 'gif', 'mp4', 'webp', 'image', 'video', 'png,jpg'],
    source: ['none', 'any', 'http', 'twitter', 'pixiv'],
    id: ['100', '1..100', '>100', '<100', '>=100', '<=100', '!=100', '1,2,3'],
    width: ['>=1920', '>1080', '<1000', '1080..3840', '1920'],
    height: ['>=1080', '>720', '<1080', '720..2160', '1080'],
    duration: ['>30', '<=60', '10..60', '>0', '0'],
    filesize: ['>5mb', '<1mb', '1mb..5mb', '<=10mb', '>500kb'],
    date: ['>=2024-01-01', '2024-01-01', '2024-01-01..2024-12-31', '<2023-01-01'],
    age: ['<24h', '<7d', '1w..1mo', '>1y'],
    md5: ['<checksum>'],
    order: [
        'id_desc', 'id_asc', 'date_desc', 'date_asc',
        'filesize_desc', 'filesize_asc', 'width_desc', 'height_desc',
        'mpixels_desc', 'duration_desc', 'duration_asc',
        'landscape', 'portrait', 'rating_asc', 'rating_desc',
        'filename_asc', 'filename_desc', 'filetype_desc', 'filetype_asc',
        'md5_asc', 'tagcount_desc', 'tagcount_asc',
        'random', 'random:42', 'custom'
    ]
};

TagAutocomplete.QUALIFIER_ALIASES = {
    pool: 'album',
    pool_tree: 'album_tree',
    sort: 'order',
    file_size: 'filesize',
    size: 'filesize',
    uploaded_at: 'date',
    created_at: 'date',
    time: 'date',
    tag_count: 'tagcount',
    tags: 'tagcount',
    file_type: 'filetype',
    hash: 'md5'
};
