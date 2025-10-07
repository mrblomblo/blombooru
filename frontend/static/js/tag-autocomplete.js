class TagAutocomplete {
    constructor(input, options = {}) {
        this.input = input;
        this.options = {
            onSelect: null,
            multipleValues: false,
            ...options
        };
        
        this.setupAutocomplete();
    }
    
    setupAutocomplete() {
        // Create suggestions container
        this.suggestionsEl = document.createElement('div');
        this.suggestionsEl.className = 'tag-suggestions hidden';
        this.input.parentNode.insertBefore(this.suggestionsEl, this.input.nextSibling);
        
        // Add event listeners
        this.input.addEventListener('input', this.onInput.bind(this));
        this.input.addEventListener('keydown', this.onKeydown.bind(this));
        document.addEventListener('click', (e) => {
            if (!this.input.contains(e.target) && !this.suggestionsEl.contains(e.target)) {
                this.hideSuggestions();
            }
        });
        
        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            .tag-suggestions {
                position: absolute;
                z-index: 1000;
                background: #1e293b;
                border: 1px solid #334155;
                border-top: none;
                max-height: 200px;
                overflow-y: auto;
                width: 338px;
            }

            .tag-suggestion {
                padding: 0.5rem;
                cursor: pointer;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 1px solid #334155;
            }

            .tag-suggestion:hover,
            .tag-suggestion.selected {
                background: #334155;
            }

            .tag-suggestion.tag-alias-info {
                background: #422006;
                border-left: 3px solid #f59e0b;
            }

            .tag-suggestion.tag-alias-info:hover,
            .tag-suggestion.tag-alias-info.selected {
                background: #78350f;
            }

            .tag-suggestion .tag-name {
                color: #f1f5f9;
            }

            .tag-suggestion .tag-count {
                color: #94a3b8;
                font-size: 0.8em;
            }

            .tag-category {
                display: inline-block;
                padding: 0.1rem 0.3rem;
                border-radius: 2px;
                margin-right: 0.5rem;
                font-size: 0.7em;
                text-transform: uppercase;
            }
        `;
        document.head.appendChild(style);
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
    
    getCurrentQuery() {
        if (!this.options.multipleValues) {
            return this.input.value.trim();
        }
        
        const cursorPos = this.input.selectionStart;
        const value = this.input.value;
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
                <div class="tag-suggestion tag-alias-info" data-index="0" data-name="${tag.name}">
                    <span style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="color: #94a3b8; font-style: italic;">${tag.alias_name}</span>
                        <span style="color: #94a3b8;">→</span>
                        <span class="tag-name">${tag.name}</span>
                    </span>
                    <span class="tag-count">${tag.count}</span>
                </div>
            `;
        } else {
            // Normal suggestions
            this.suggestionsEl.innerHTML = suggestions.map((tag, index) => `
                <div class="tag-suggestion" data-index="${index}" data-name="${tag.name}">
                    <span>
                        <span class="tag-category ${tag.category}">${tag.category}</span>
                        <span class="tag-name">${tag.name}</span>
                    </span>
                    <span class="tag-count">${tag.count}</span>
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
            this.input.value = tagName;
        } else {
            const cursorPos = this.input.selectionStart;
            const value = this.input.value;
            const beforeCursor = value.substring(0, cursorPos);
            const afterCursor = value.substring(cursorPos);
            const lastSpace = beforeCursor.lastIndexOf(' ');
            
            const newValue = lastSpace === -1
                ? tagName + (afterCursor.startsWith(' ') ? '' : ' ') + afterCursor
                : beforeCursor.substring(0, lastSpace + 1) + tagName + (afterCursor.startsWith(' ') ? '' : ' ') + afterCursor;
            
            this.input.value = newValue;
            
            // Set cursor position after the inserted tag
            const newCursorPos = lastSpace === -1 
                ? tagName.length + 1 
                : lastSpace + 1 + tagName.length + 1;
            this.input.setSelectionRange(newCursorPos, newCursorPos);
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
                
            case 'Tab':
                // Allow tab to select the current suggestion
                if (selected) {
                    e.preventDefault();
                    this.selectSuggestion(selected.dataset.name);
                }
                break;
        }
    }
}
