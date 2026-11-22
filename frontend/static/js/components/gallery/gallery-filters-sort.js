// BaseGallery rating filters, custom filters, and sorting controls
Object.assign(BaseGallery.prototype, {
    // ==================== Rating Filter ====================

    setupRatingFilter() {
        document.querySelectorAll('.rating-filter-input').forEach(checkbox => {
            // Prevent unchecking the last selected rating
            checkbox.addEventListener('click', (e) => {
                const val = checkbox.value;
                if (this.selectedRatings.has(val) && this.selectedRatings.size === 1) {
                    e.preventDefault();
                    checkbox.checked = true;
                    return;
                }
            });

            checkbox.addEventListener('change', (e) => {
                const val = e.target.value;
                if (e.target.checked) {
                    this.selectedRatings.add(val);
                } else {
                    if (this.selectedRatings.size > 1) {
                        this.selectedRatings.delete(val);
                    } else {
                        e.target.checked = true;
                        return;
                    }
                }
                const ratingStr = Array.from(this.selectedRatings).join(',');
                this.currentRating = ratingStr;
                this.updateRatingFilterLabels();
                localStorage.setItem('selectedRating', ratingStr);
                window.setCookie('rating_filter', ratingStr, 365);
                this.onRatingChange();
            });
        });

        // Set initial state
        const ratingStr = Array.from(this.selectedRatings).join(',');
        this.currentRating = ratingStr;
        this.updateRatingFilterLabels();
        this.setupCustomFilterButtons();
    },

    setupCustomFilterButtons() {
        document.querySelectorAll('.custom-filter-input').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const val = e.target.value;
                if (e.target.checked) {
                    this.selectedCustomFilters.add(val);
                } else {
                    this.selectedCustomFilters.delete(val);
                }
                const filterArray = Array.from(this.selectedCustomFilters);
                this.currentCustomFilter = filterArray.join(' ');
                this.updateCustomFilterLabels();
                localStorage.setItem('selectedCustomFilter', JSON.stringify(filterArray));
                this.onCustomFilterChange();
            });
        });

        // Set initial state - validate whether buttons for selectedCustomFilters exist
        const availableInputs = document.querySelectorAll('.custom-filter-input');
        if (availableInputs.length > 0) {
            const availableValues = new Set(Array.from(availableInputs).map(input => input.value));
            for (const val of Array.from(this.selectedCustomFilters)) {
                if (!availableValues.has(val)) {
                    this.selectedCustomFilters.delete(val);
                }
            }
        }
        const filterArray = Array.from(this.selectedCustomFilters);
        this.currentCustomFilter = filterArray.join(' ');
        this.updateCustomFilterLabels();
    },

    updateCustomFilterLabels() {
        document.querySelectorAll('.custom-filter-label').forEach(label => {
            label.classList.remove('checked');
        });

        document.querySelectorAll('.custom-filter-input').forEach(checkbox => {
            const isChecked = this.selectedCustomFilters.has(checkbox.value);
            checkbox.checked = isChecked;
            const label = checkbox.nextElementSibling;
            if (label) {
                if (isChecked) {
                    label.classList.add('checked');
                } else {
                    label.classList.remove('checked');
                }
            }
        });
    },

    onCustomFilterChange() {
        this.loadContent();
    },

    freezeFiltersForReorder() {
        this.savedRatings = new Set(this.selectedRatings);
        this.savedCustomFilters = new Set(this.selectedCustomFilters);

        // Force all ratings
        this.selectedRatings = new Set(['safe', 'questionable', 'explicit']);
        this.currentRating = 'safe,questionable,explicit';
        this.updateRatingFilterLabels();

        // Clear custom filters
        this.selectedCustomFilters = new Set();
        this.currentCustomFilter = '';
        this.updateCustomFilterLabels();

        // Disable filter checkboxes in the UI
        document.querySelectorAll('.rating-filter-input, .custom-filter-input').forEach(input => {
            input.disabled = true;
        });
        document.querySelectorAll('.rating-filter-label, .custom-filter-label').forEach(label => {
            label.classList.add('pointer-events-none', 'opacity-50');
        });
    },

    restoreFiltersAfterReorder() {
        let filtersChanged = false;
        if (this.savedRatings) {
            const restoredRating = Array.from(this.savedRatings).join(',');
            if (this.currentRating !== restoredRating) {
                filtersChanged = true;
            }
            this.selectedRatings = new Set(this.savedRatings);
            this.currentRating = restoredRating;
            this.updateRatingFilterLabels();
            this.savedRatings = null;
        }

        if (this.savedCustomFilters) {
            const restoredCustom = Array.from(this.savedCustomFilters).join(' ');
            if (this.currentCustomFilter !== restoredCustom) {
                filtersChanged = true;
            }
            this.selectedCustomFilters = new Set(this.savedCustomFilters);
            this.currentCustomFilter = restoredCustom;
            this.updateCustomFilterLabels();
            this.savedCustomFilters = null;
        }

        // Re-enable filter checkboxes
        document.querySelectorAll('.rating-filter-input, .custom-filter-input').forEach(input => {
            input.disabled = false;
        });
        document.querySelectorAll('.rating-filter-label, .custom-filter-label').forEach(label => {
            label.classList.remove('pointer-events-none', 'opacity-50');
        });

        return filtersChanged;
    },

    updateRatingFilterLabels() {
        document.querySelectorAll('.rating-filter-label').forEach(label => {
            label.classList.remove('checked');
        });

        document.querySelectorAll('.rating-filter-input').forEach(checkbox => {
            const isChecked = this.selectedRatings.has(checkbox.value);
            checkbox.checked = isChecked;
            const label = checkbox.nextElementSibling;
            if (label) {
                if (isChecked) {
                    label.classList.add('checked');
                } else {
                    label.classList.remove('checked');
                }
            }
        });
    },

    onRatingChange() {
        this.loadContent();
    },

    // ==================== Sorting ====================

    setupSorting() {
        if (typeof CustomSelect === 'undefined') {
            console.warn('CustomSelect not loaded');
            return;
        }

        this.sortBySelects = [];
        this.sortOrderToggles = document.querySelectorAll('.js-sort-order-toggle');
        this.sortRandomRegenBtns = document.querySelectorAll('.js-sort-random-regen');
        this.sortEditOrderBtns = document.querySelectorAll('.js-sort-edit-order');

        const sortByElements = document.querySelectorAll('.js-sort-by-select');
        const params = new URLSearchParams(window.location.search);

        sortByElements.forEach(element => {
            const select = new CustomSelect(element);

            if (params.has('sort')) {
                select.setValue(params.get('sort'));
            }

            element.addEventListener('change', (e) => {
                const newValue = e.detail.value;
                this.sortBySelects.forEach(s => {
                    if (s !== select) s.setValue(newValue, false);
                });
                this.handleSortChange(newValue);
            });

            this.sortBySelects.push(select);
        });

        this.sortBySelect = this.sortBySelects[0];

        this.sortOrderToggles.forEach(btn => {
            btn.addEventListener('click', () => this.toggleSortOrder());
        });

        this.sortRandomRegenBtns.forEach(btn => {
            btn.addEventListener('click', () => this.regenerateRandomSeed());
        });

        if (this.currentSort === 'random' && !this.currentRandomSeed) {
            this.currentRandomSeed = String(Date.now());
            this.syncSortUrlParams();
        }

        this.updateSortControlsVisibility();
        this.updateSortOrderToggleState();
        if (this.currentSort === 'random') {
            this.rollSortRandomDice();
        }
    },

    getSortValue() {
        if (this.sortBySelects && this.sortBySelects.length > 0) {
            return this.sortBySelects[0].getValue();
        }
        return this.currentSort;
    },

    getOrderValue() {
        if (this.currentSort === 'manual') {
            return 'asc';
        }
        return this.currentOrder;
    },

    handleSortChange(newSort) {
        const previousSort = this.currentSort;
        if (previousSort !== 'manual') {
            this.lastNonManualSort = previousSort;
            this.lastNonManualOrder = this.currentOrder;
        }
        this.currentSort = newSort;

        if (newSort === 'random') {
            if (!this.currentRandomSeed && !this.savedRandomSeed) {
                this.currentRandomSeed = String(Date.now());
            } else if (!this.currentRandomSeed && this.savedRandomSeed) {
                this.currentRandomSeed = this.savedRandomSeed;
            }
            this.savedRandomSeed = this.currentRandomSeed;
            this.rollSortRandomDice();
        } else {
            if (this.currentRandomSeed) {
                this.savedRandomSeed = this.currentRandomSeed;
            }
        }

        if (newSort === 'manual') {
            this.currentOrder = 'asc';
            this.updateSortOrderToggleState();
        } else if (previousSort === 'manual' && this.lastNonManualOrder) {
            this.currentOrder = this.lastNonManualOrder;
            this.updateSortOrderToggleState();
        }

        this.updateSortControlsVisibility();
        this.syncSortUrlParams();
        this.onSortChange();
    },

    toggleSortOrder() {
        if (this.currentSort === 'random' || this.currentSort === 'manual') return;

        this.currentOrder = this.currentOrder === 'asc' ? 'desc' : 'asc';
        if (this.currentSort !== 'manual') {
            this.lastNonManualOrder = this.currentOrder;
        }
        this.updateSortOrderToggleState();
        this.syncSortUrlParams();
        this.onSortChange();
    },

    regenerateRandomSeed() {
        if (this.currentSort !== 'random') return;

        this.currentRandomSeed = String(Date.now());
        this.savedRandomSeed = this.currentRandomSeed;
        this.rollSortRandomDice();
        this.syncSortUrlParams();
        this.onSortChange();
    },

    rollSortRandomDice() {
        this.sortRandomRegenBtns.forEach(btn => {
            btn.innerHTML = window.Icons.dice();
        });
    },

    updateSortControlsVisibility() {
        const isRandom = this.currentSort === 'random';
        const isManual = this.currentSort === 'manual';

        this.sortOrderToggles.forEach(btn => {
            btn.classList.toggle('hidden', isRandom || isManual);
            btn.disabled = isRandom || isManual;
        });

        this.sortRandomRegenBtns.forEach(btn => {
            btn.classList.toggle('hidden', !isRandom);
        });

        if (this.sortEditOrderBtns) {
            this.sortEditOrderBtns.forEach(btn => {
                btn.classList.toggle('hidden', !isManual);
            });
        }
    },

    updateSortOrderToggleState() {
        this.sortOrderToggles.forEach(btn => {
            btn.dataset.order = this.currentOrder;
            btn.classList.remove('asc', 'desc');
            btn.classList.add(this.currentOrder);
        });
    },

    syncSortUrlParams() {
        const params = {
            sort: this.currentSort,
            order: this.currentOrder,
            seed: this.currentSort === 'random' ? this.currentRandomSeed : null,
            fallback_sort: this.currentSort === 'manual' ? (this.lastNonManualSort || null) : null,
            fallback_order: this.currentSort === 'manual' ? (this.lastNonManualOrder || null) : null
        };
        this.updateUrlParams(params);
    },

    appendSortParams(params) {
        const sort = this.getSortValue();
        params.set('sort', sort);
        params.set('order', sort === 'manual' ? 'asc' : this.getOrderValue());
        if (sort === 'random' && this.currentRandomSeed) {
            params.set('seed', this.currentRandomSeed);
        }
        if (sort === 'manual' && this.lastNonManualSort) {
            params.set('fallback_sort', this.lastNonManualSort);
            params.set('fallback_order', this.lastNonManualOrder || 'desc');
            if (this.lastNonManualSort === 'random' && (this.currentRandomSeed || this.savedRandomSeed)) {
                params.set('seed', this.currentRandomSeed || this.savedRandomSeed);
            }
        }
    },

    onSortChange() {
        this.loadContent();
    },

    addSortOption(value, label) {
        if (this.sortBySelects) {
            this.sortBySelects.forEach(select => select.addOption(value, label));
        }
    },

    removeSortOption(value) {
        if (this.sortBySelects) {
            this.sortBySelects.forEach(select => select.removeOption(value));
        }
    },
});
