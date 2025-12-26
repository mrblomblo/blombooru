class CustomSelect {
    constructor(element) {
        this.element = element;
        this.trigger = element.querySelector('.custom-select-trigger');
        this.dropdown = element.querySelector('.custom-select-dropdown');
        this.valueDisplay = element.querySelector('.custom-select-value');
        this.selectedValue = element.dataset.value || '';
        this.focusedIndex = -1;

        this.init();
        this.initializeExistingOptions();
    }

    init() {
        this.trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });

        document.addEventListener('click', (e) => {
            if (!this.element.contains(e.target)) {
                this.close();
            }
        });

        this.element.addEventListener('keydown', (e) => {
            this.handleKeyboard(e);
        });

        this.dropdown.addEventListener('wheel', (e) => {
            e.stopPropagation();
        });
    }

    initializeExistingOptions() {
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        options.forEach(option => {
            // Remove old listeners to prevent duplicates if called multiple times
            const newOption = option.cloneNode(true);
            option.parentNode.replaceChild(newOption, option);

            this._bindOptionEvents(newOption);

            if (newOption.classList.contains('selected') || newOption.dataset.value === this.selectedValue) {
                newOption.classList.add('selected');
                this.selectedValue = newOption.dataset.value;
                this.element.dataset.value = newOption.dataset.value;
                this.valueDisplay.textContent = newOption.textContent;
            }
        });
    }

    _bindOptionEvents(option) {
        option.addEventListener('click', () => {
            this.selectOption(option);
        });
    }

    toggle() {
        if (this.element.classList.contains('open')) {
            this.close();
        } else {
            this.open();
        }
    }

    open() {
        document.querySelectorAll('.custom-select.open').forEach(select => {
            if (select !== this.element) {
                select.classList.remove('open');
            }
        });

        this.element.classList.add('open');
        this.focusedIndex = -1;

        const selected = this.dropdown.querySelector('.selected');
        if (selected) {
            selected.scrollIntoView({ block: 'nearest' });
        }
    }

    close() {
        this.element.classList.remove('open');
        this.focusedIndex = -1;
        this.clearFocused();
    }

    selectOption(option) {
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        options.forEach(opt => opt.classList.remove('selected'));

        option.classList.add('selected');
        this.selectedValue = option.dataset.value;
        this.element.dataset.value = this.selectedValue;
        this.valueDisplay.textContent = option.textContent;

        this.element.dispatchEvent(new CustomEvent('change', {
            detail: {
                value: this.selectedValue,
                text: option.textContent
            }
        }));

        this.close();
    }

    handleKeyboard(e) {
        const isOpen = this.element.classList.contains('open');
        const options = this.dropdown.querySelectorAll('.custom-select-option');

        switch (e.key) {
            case 'Enter':
            case ' ':
                e.preventDefault();
                if (!isOpen) {
                    this.open();
                } else if (this.focusedIndex >= 0) {
                    this.selectOption(options[this.focusedIndex]);
                }
                break;

            case 'Escape':
                e.preventDefault();
                this.close();
                break;

            case 'ArrowDown':
                e.preventDefault();
                if (!isOpen) {
                    this.open();
                } else {
                    this.focusNext();
                }
                break;

            case 'ArrowUp':
                e.preventDefault();
                if (isOpen) {
                    this.focusPrevious();
                }
                break;
        }
    }

    focusNext() {
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        this.focusedIndex = Math.min(this.focusedIndex + 1, options.length - 1);
        this.updateFocused();
    }

    focusPrevious() {
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        this.focusedIndex = Math.max(this.focusedIndex - 1, 0);
        this.updateFocused();
    }

    updateFocused() {
        this.clearFocused();
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        if (this.focusedIndex >= 0 && options[this.focusedIndex]) {
            const focused = options[this.focusedIndex];
            focused.classList.add('focused');
            focused.scrollIntoView({ block: 'nearest' });
        }
    }

    clearFocused() {
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        options.forEach(opt => opt.classList.remove('focused'));
    }

    setValue(value) {
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        const option = Array.from(options).find(opt => opt.dataset.value === value);
        if (option) {
            this.selectOption(option);
        }
    }

    getValue() {
        return this.selectedValue;
    }

    setOptions(optionsData) {
        this.dropdown.innerHTML = '';
        optionsData.forEach(optionData => {
            this.addOption(optionData.value, optionData.text, optionData.selected);
        });
    }

    /**
     * Add a single option dynamically
     */
    addOption(value, text, isSelected = false) {
        // Prevent duplicates
        if (this.dropdown.querySelector(`[data-value="${value}"]`)) return;

        const option = document.createElement('div');
        option.className = 'custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs';
        option.dataset.value = value;
        option.textContent = text;

        this._bindOptionEvents(option);

        if (isSelected) {
            option.classList.add('selected');
            this.selectedValue = value;
            this.element.dataset.value = value;
            this.valueDisplay.textContent = text;
        }

        this.dropdown.appendChild(option);
    }

    removeOption(value) {
        const option = this.dropdown.querySelector(`[data-value="${value}"]`);
        if (option) {
            option.remove();

            // If we removed the currently selected item, reset to first available or clear
            if (this.selectedValue === value) {
                const firstOption = this.dropdown.querySelector('.custom-select-option');
                if (firstOption) {
                    this.selectOption(firstOption);
                } else {
                    this.selectedValue = '';
                    this.element.dataset.value = '';
                    this.valueDisplay.textContent = '';
                }
            }
        }
    }
}
