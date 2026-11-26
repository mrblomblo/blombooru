class CustomSelect {
    constructor(element) {
        this.element = element;
        this.trigger = element.querySelector('.custom-select-trigger');
        this.dropdown = element.querySelector('.custom-select-dropdown');
        this.valueDisplay = element.querySelector('.custom-select-value');
        this.selectedValue = element.dataset.value || '';
        this.focusedIndex = -1;
        this.disabled = false;
        this.arrow = element.querySelector('.custom-select-arrow');

        this.init();
        this.initializeExistingOptions();
    }

    init() {
        this._triggerClickHandler = (e) => {
            if (this.disabled) return;
            e.stopPropagation();
            this.toggle();
        };
        this.trigger.addEventListener('click', this._triggerClickHandler);

        this._documentClickHandler = (e) => {
            if (!this.element.contains(e.target)) {
                this.close();
            }
        };
        document.addEventListener('click', this._documentClickHandler);

        this._keydownHandler = (e) => {
            this.handleKeyboard(e);
        };
        this.element.addEventListener('keydown', this._keydownHandler);

        if (this.trigger) {
            this.trigger.setAttribute('role', 'combobox');
            this.trigger.setAttribute('aria-haspopup', 'listbox');
            this.trigger.setAttribute('aria-expanded', 'false');
        }
        if (this.dropdown) {
            this.dropdown.setAttribute('role', 'listbox');
        }

        this.dropdown.addEventListener('wheel', (e) => {
            e.stopPropagation();
        });
    }

    _renderOptionDisplay(targetEl, label, iconName) {
        targetEl.textContent = '';
        if (iconName) {
            const wrapper = document.createElement('span');
            wrapper.className = 'inline-flex items-center gap-1.5 min-w-0 max-w-full';
            wrapper.insertAdjacentHTML(
                'afterbegin',
                window.Icons[iconName]({
                    size: 12,
                    class: 'flex-shrink-0 text-secondary',
                    extra: 'aria-hidden="true"'
                })
            );
            const textSpan = document.createElement('span');
            textSpan.className = 'truncate';
            textSpan.textContent = label;
            wrapper.appendChild(textSpan);
            targetEl.appendChild(wrapper);
        } else {
            targetEl.textContent = label;
        }
    }

    initializeExistingOptions() {
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        options.forEach(option => {
            // Remove old listeners to prevent duplicates if called multiple times
            const newOption = option.cloneNode(true);
            option.parentNode.replaceChild(newOption, option);

            const label = newOption.dataset.display || newOption.dataset.baseLabel || newOption.textContent.trim();
            if (newOption.dataset.icon) {
                newOption.dataset.display = label;
                this._renderOptionDisplay(newOption, label, newOption.dataset.icon);
            }

            this._bindOptionEvents(newOption);

            const isSelected = newOption.classList.contains('selected') || newOption.dataset.value === this.selectedValue;
            newOption.setAttribute('role', 'option');
            newOption.setAttribute('aria-selected', isSelected ? 'true' : 'false');

            if (isSelected) {
                newOption.classList.add('selected');
                this.selectedValue = newOption.dataset.value;
                this.element.dataset.value = newOption.dataset.value;
                this._renderOptionDisplay(this.valueDisplay, label, newOption.dataset.icon || '');
            }
        });
    }

    _bindOptionEvents(option) {
        option.addEventListener('click', () => {
            this.selectOption(option);
        });
    }

    toggle() {
        if (this.disabled) return;

        if (this.element.classList.contains('open')) {
            this.close();
        } else {
            this.open();
        }
    }

    open() {
        if (this.disabled) return;

        document.querySelectorAll('.custom-select.open').forEach(select => {
            if (select !== this.element) {
                select.classList.remove('open');
            }
        });

        this.element.classList.add('open');
        if (this.trigger) {
            this.trigger.setAttribute('aria-expanded', 'true');
        }
        this.focusedIndex = -1;

        if (this.dropdown) {
            this.dropdown.style.left = '';
            this.dropdown.style.right = '';
            let rect = this.dropdown.getBoundingClientRect();
            if (rect.right > window.innerWidth - 8) {
                this.dropdown.style.left = 'auto';
                this.dropdown.style.right = '0';
                rect = this.dropdown.getBoundingClientRect();
            }
            if (rect.left < 8) {
                const parentRect = this.element.getBoundingClientRect();
                this.dropdown.style.left = `${Math.max(0, 8 - parentRect.left)}px`;
                this.dropdown.style.right = 'auto';
            }
        }

        const selected = this.dropdown.querySelector('.selected');
        if (selected) {
            selected.scrollIntoView({ block: 'nearest' });
        }
    }

    close() {
        this.element.classList.remove('open');
        if (this.trigger) {
            this.trigger.setAttribute('aria-expanded', 'false');
        }
        this.focusedIndex = -1;
        this.clearFocused();
        if (this.dropdown) {
            this.dropdown.style.left = '';
            this.dropdown.style.right = '';
        }
    }

    selectOption(option, triggerEvent = true) {
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        options.forEach(opt => {
            opt.classList.remove('selected');
            opt.setAttribute('aria-selected', 'false');
        });

        option.classList.add('selected');
        option.setAttribute('aria-selected', 'true');
        this.selectedValue = option.dataset.value;
        this.element.dataset.value = this.selectedValue;
        const label = option.dataset.display || option.dataset.baseLabel || option.textContent;
        this._renderOptionDisplay(this.valueDisplay, label, option.dataset.icon || '');

        if (triggerEvent) {
            this.element.dispatchEvent(new CustomEvent('change', {
                detail: {
                    value: this.selectedValue,
                    text: label,
                    display: label
                }
            }));
        }

        this.close();
    }

    handleKeyboard(e) {
        if (this.disabled) return;

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

    setValue(value, triggerEvent = false) {
        const options = this.dropdown.querySelectorAll('.custom-select-option');
        const option = Array.from(options).find(opt => opt.dataset.value === value);
        if (option) {
            this.selectOption(option, triggerEvent);
        }
    }

    getValue() {
        return this.selectedValue;
    }

    setDisabled(disabled) {
        this.disabled = disabled;
        this.trigger.disabled = disabled;

        if (disabled) {
            this.trigger.classList.remove('bg', 'hover:border-primary', 'focus:border-primary', 'cursor-pointer');
            this.trigger.classList.add('surface', 'cursor-not-allowed');
            this.valueDisplay.classList.remove('text');
            this.valueDisplay.classList.add('text-tertiary');
            if (this.arrow) {
                this.arrow.classList.remove('text-secondary');
                this.arrow.classList.add('text-tertiary');
            }
            this.close();
            return;
        }

        this.trigger.classList.add('bg', 'hover:border-primary', 'focus:border-primary', 'cursor-pointer');
        this.trigger.classList.remove('surface', 'cursor-not-allowed');
        this.valueDisplay.classList.add('text');
        this.valueDisplay.classList.remove('text-tertiary');
        if (this.arrow) {
            this.arrow.classList.add('text-secondary');
            this.arrow.classList.remove('text-tertiary');
        }
    }

    setOptions(optionsData) {
        this.dropdown.innerHTML = '';
        optionsData.forEach(optionData => {
            this.addOption(optionData.value, optionData.text, optionData.selected, optionData.icon || '');
        });
    }

    /**
     * Add a single option dynamically
     */
    addOption(value, text, isSelected = false, icon = '') {
        // Prevent duplicates
        if (this.dropdown.querySelector(`[data-value="${CSS.escape(value)}"]`)) return;

        const option = document.createElement('div');
        option.className = 'custom-select-option px-3 py-2 cursor-pointer hover:surface text text-xs';
        option.dataset.value = value;
        option.dataset.baseLabel = text;
        option.dataset.display = text;
        if (icon) {
            option.dataset.icon = icon;
        }
        this._renderOptionDisplay(option, text, icon);

        this._bindOptionEvents(option);
        option.setAttribute('role', 'option');
        option.setAttribute('aria-selected', isSelected ? 'true' : 'false');

        if (isSelected) {
            option.classList.add('selected');
            this.selectedValue = value;
            this.element.dataset.value = value;
            this._renderOptionDisplay(this.valueDisplay, text, icon);
        }

        this.dropdown.appendChild(option);
    }

    removeOption(value) {
        const option = this.dropdown.querySelector(`[data-value="${CSS.escape(value)}"]`);
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

    destroy() {
        if (this._documentClickHandler) {
            document.removeEventListener('click', this._documentClickHandler);
            this._documentClickHandler = null;
        }
        if (this._triggerClickHandler && this.trigger) {
            this.trigger.removeEventListener('click', this._triggerClickHandler);
            this._triggerClickHandler = null;
        }
        if (this._keydownHandler && this.element) {
            this.element.removeEventListener('keydown', this._keydownHandler);
            this._keydownHandler = null;
        }
    }
}
