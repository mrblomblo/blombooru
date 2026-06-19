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
            ...options
        };

        this.setupAutocomplete();
    }

    escapeHtml(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
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
    }

    async onInput() {
        const query = this.getCurrentQuery();
        if (query.length < 1) {
            this.hideSuggestions();
            return;
        }

        try {
            const suggestions = await this.fetchSuggestions(query);
            this.showSuggestions(suggestions, query);
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

        const normalizedQuery = query ? query.toLowerCase().replace(/ /g, '_') : '';
        const exactMatchExists = suggestions.some(t => t.name === normalizedQuery || (t.is_alias && t.alias_name === normalizedQuery));
        const hasCreate = this.options.allowCreate && query && query.length > 0 && !exactMatchExists;

        if (!hasResults && !hasCreate) {
            this.hideSuggestions();
            return;
        }

        let html = '';

        if (hasResults) {
            html = suggestions.map((tag, index) => {
                if (tag.is_alias) {
                    return `
                    <div class="tag-suggestion tag-alias-info" data-index="${index}" data-name="${this.escapeHtml(tag.name)}">
                        <span style="display: flex; align-items: center; gap: 0.5rem;">
                            <span class="text-secondary italic">${this.escapeHtml(tag.alias_name)}</span>
                            <span class="text-secondary">&#8594;</span>
                            <span class="tag-name">${this.escapeHtml(tag.name)}</span>
                        </span>
                        <span class="tag-count">${this.escapeHtml(String(tag.count))}</span>
                    </div>
                `;
                }
                return `
                <div class="tag-suggestion" data-index="${index}" data-name="${this.escapeHtml(tag.name)}">
                    <span>
                        <span class="tag-category"><span class="tag-text ${this.escapeHtml(tag.category)}">${this.escapeHtml(tag.category)}</span></span>
                        <span class="tag-name">${this.escapeHtml(tag.name)}</span>
                    </span>
                    <span class="tag-count">${this.escapeHtml(String(tag.count))}</span>
                </div>
            `;
            }).join('');
        }

        // Append the "Add new tag" sentinel row when allowCreate is enabled
        if (hasCreate) {
            const createIndex = suggestions.length;
            const queryStr = query.replace(/ /g, '_');
            const escapedQuery = this.escapeHtml(queryStr);
            const createText = window.i18n.t('admin.tags_management.create_tag');
            html += `
                <div class="tag-suggestion tag-create-new" data-index="${createIndex}" data-name="__create__" data-query="${escapedQuery}">
                    <span>
                        <span class="tag-category"><span class="tag-text meta">${this.escapeHtml(createText)}</span></span>
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
            `<div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="${c.value}">${this.escapeHtml(c.label)}</div>`
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
                <h2 class="text-xl font-bold mb-6 text-primary text-center">${this.escapeHtml(titleText)}</h2>

                <div class="mb-4">
                    <label class="block text-xs font-bold mb-2">${this.escapeHtml(nameLabel)}</label>
                    <input type="text" id="tag-create-name" value="${this.escapeHtml(initialName)}"
                        class="w-full bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary"
                        autocomplete="off" spellcheck="false">
                    <p id="tag-create-name-error" class="text-xs text-danger mt-1" style="display:none;"></p>
                </div>

                <div class="mb-6">
                    <label class="block text-xs font-bold mb-2">${this.escapeHtml(categoryLabel)}</label>
                    <div id="tag-create-category-select" class="custom-select w-full" data-value="general">
                        <button class="custom-select-trigger w-full flex items-center justify-between gap-3 px-3 py-2 bg border text-xs cursor-pointer focus:outline-none hover:border-primary transition-colors focus:border-primary" type="button">
                            <span class="custom-select-value text">${this.escapeHtml(generalLabel)}</span>
                            <svg class="custom-select-arrow flex-shrink-0 transition-transform duration-200 text-secondary" width="12" height="12" viewBox="0 0 12 12">
                                <path fill="currentColor" d="M6 9L1 4h10z" />
                            </svg>
                        </button>
                        <div class="custom-select-dropdown bg border border-primary max-h-60 overflow-y-auto shadow-lg">
                            ${categoryOptions}
                        </div>
                    </div>
                </div>

                <div class="flex gap-3 justify-center">
                    <button id="tag-create-submit" class="btn-primary px-6 py-3 font-bold text-sm flex-1">
                        ${this.escapeHtml(createText)}
                    </button>
                    <button id="tag-create-cancel" class="btn px-6 py-3 font-bold text-sm flex-1">
                        ${this.escapeHtml(cancelText)}
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

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (suggestions.length > 0) {
                    if (selected) selected.classList.remove('selected');
                    const nextIndex = selectedIndex < suggestions.length - 1 ? selectedIndex + 1 : 0;
                    suggestions[nextIndex].classList.add('selected');
                    suggestions[nextIndex].scrollIntoView({ block: 'nearest' });
                }
                break;

            case 'ArrowUp':
                e.preventDefault();
                if (suggestions.length > 0) {
                    if (selected) selected.classList.remove('selected');
                    const prevIndex = selectedIndex > 0 ? selectedIndex - 1 : suggestions.length - 1;
                    suggestions[prevIndex].classList.add('selected');
                    suggestions[prevIndex].scrollIntoView({ block: 'nearest' });
                }
                break;

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

    destroy() {
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
