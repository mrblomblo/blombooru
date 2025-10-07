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
        const lastComma = beforeCursor.lastIndexOf(' ');
        return beforeCursor.substring(lastComma + 1).trim();
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
        
        this.suggestionsEl.innerHTML = suggestions.map((tag, index) => `
            <div class="tag-suggestion" data-index="${index}" data-name="${tag.name}">
                <span>
                    <span class="tag-category ${tag.category}">${tag.category}</span>
                    <span class="tag-name">${tag.name}</span>
                </span>
                <span class="tag-count">${tag.count}</span>
            </div>
        `).join('');
        
        this.suggestionsEl.classList.remove('hidden');
        
        // Add click handlers
        this.suggestionsEl.querySelectorAll('.tag-suggestion').forEach(el => {
            el.addEventListener('click', () => this.selectSuggestion(el.dataset.name));
        });
    }
    
    hideSuggestions() {
        this.suggestionsEl.classList.add('hidden');
    }
    
    selectSuggestion(tagName) {
        if (!this.options.multipleValues) {
            this.input.value = tagName;
        } else {
            const cursorPos = this.input.selectionStart;
            const value = this.input.value;
            const beforeCursor = value.substring(0, cursorPos);
            const afterCursor = value.substring(cursorPos);
            const lastComma = beforeCursor.lastIndexOf(',');
            
            const newValue = lastComma === -1
                ? tagName + (afterCursor.startsWith(',') ? '' : ', ') + afterCursor
                : beforeCursor.substring(0, lastComma + 1) + ' ' + tagName + (afterCursor.startsWith(',') ? '' : ', ') + afterCursor;
            
            this.input.value = newValue;
        }
        
        this.hideSuggestions();
        this.input.focus();
        
        if (this.options.onSelect) {
            this.options.onSelect(tagName);
        }
    }
    
    onKeydown(e) {
        const suggestions = this.suggestionsEl.querySelectorAll('.tag-suggestion');
        const selected = this.suggestionsEl.querySelector('.tag-suggestion.selected');
        const selectedIndex = selected ? parseInt(selected.dataset.index) : -1;
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (selectedIndex < suggestions.length - 1) {
                    if (selected) selected.classList.remove('selected');
                    suggestions[selectedIndex + 1].classList.add('selected');
                    suggestions[selectedIndex + 1].scrollIntoView({ block: 'nearest' });
                }
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                if (selectedIndex > 0) {
                    if (selected) selected.classList.remove('selected');
                    suggestions[selectedIndex - 1].classList.add('selected');
                    suggestions[selectedIndex - 1].scrollIntoView({ block: 'nearest' });
                }
                break;
                
            case 'Enter':
                if (selected) {
                    e.preventDefault();
                    this.selectSuggestion(selected.dataset.name);
                }
                break;
                
            case 'Escape':
                this.hideSuggestions();
                break;
        }
    }
}
