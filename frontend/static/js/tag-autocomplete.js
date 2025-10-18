class TagAutocomplete {
    constructor(input, options = {}) {
        this.input = input;
        this.isContentEditable = input.getAttribute('contenteditable') === 'true';
        this.options = {
            onSelect: null,
            multipleValues: false,
            containerClasses: '',
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
        
        // Add event listeners
        this.input.addEventListener('input', this.onInput.bind(this));
        this.input.addEventListener('keydown', this.onKeydown.bind(this));
        document.addEventListener('click', (e) => {
            if (!this.input.contains(e.target) && !this.suggestionsEl.contains(e.target)) {
                this.hideSuggestions();
            }
        });
    }
    
    async onInput() {
        const query = this.getCurrentQuery();
        if (query.length < 1) {
            this.hideSuggestions();
            return;
        }
        
        try {
            const suggestions = await this.fetchSuggestions(query);
            this.showSuggestions(suggestions);
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
    
    showSuggestions(suggestions) {
        if (!suggestions.length) {
            this.hideSuggestions();
            return;
        }

        // Check if this is an alias result
        if (suggestions.length === 1 && suggestions[0].is_alias) {
            const tag = suggestions[0];
            this.suggestionsEl.innerHTML = `
                <div class="tag-suggestion tag-alias-info" data-index="0" data-name="${this.escapeHtml(tag.name)}">
                    <span style="display: flex; align-items: center; gap: 0.5rem;">
                        <span class="text-secondary italic">${this.escapeHtml(tag.alias_name)}</span>
                        <span class="text-secondary">&#8594;</span>
                        <span class="tag-name">${this.escapeHtml(tag.name)}</span>
                    </span>
                    <span class="tag-count">${this.escapeHtml(String(tag.count))}</span>
                </div>
            `;
        } else {
            // Normal suggestions
            this.suggestionsEl.innerHTML = suggestions.map((tag, index) => `
                <div class="tag-suggestion" data-index="${index}" data-name="${this.escapeHtml(tag.name)}">
                    <span>
                        <span class="tag-category ${this.escapeHtml(tag.category)}">${this.escapeHtml(tag.category)}</span>
                        <span class="tag-name">${this.escapeHtml(tag.name)}</span>
                    </span>
                    <span class="tag-count">${this.escapeHtml(String(tag.count))}</span>
                </div>
            `).join('');
        }

        this.suggestionsEl.classList.remove('hidden');

        // Add click handlers
        this.suggestionsEl.querySelectorAll('.tag-suggestion').forEach(el => {
            el.addEventListener('click', (e) => {
                e.preventDefault();
                this.selectSuggestion(el.dataset.name);
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
            
            const newValue = lastSpace === -1
                ? tagName + (afterCursor.startsWith(' ') ? '' : ' ') + afterCursor
                : beforeCursor.substring(0, lastSpace + 1) + tagName + (afterCursor.startsWith(' ') ? '' : ' ') + afterCursor;
            
            this.setInputValue(newValue);
            
            // Set cursor position after the inserted tag
            const newCursorPos = lastSpace === -1 
                ? tagName.length + 1 
                : lastSpace + 1 + tagName.length + 1;
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
                    this.selectSuggestion(selected.dataset.name);
                }
                break;
                
            case 'Escape':
                e.preventDefault();
                this.hideSuggestions();
                break;
        }
    }
}
