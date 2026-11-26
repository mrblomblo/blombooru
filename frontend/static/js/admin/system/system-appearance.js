// AdminSystem custom background picker/preview and custom navigation buttons
Object.assign(AdminSystem.prototype, {
    _openBgMediaPicker() {
        if (this._bgPicker) this._bgPicker.destroy();

        this._bgPicker = new MediaPickerModal({
            title: window.i18n.t('admin.settings.custom_background.select_media'),
            mode: 'single',
            getInitialItems: async () => {
                const params = new URLSearchParams({
                    sort: 'uploaded_at',
                    order: 'desc',
                    limit: 24,
                    page: 1,
                });
                const res = await fetch(`/api/search?${params.toString()}`, {
                    credentials: 'include'
                });
                if (!res.ok) return [];
                const data = await res.json();
                return data.items || [];
            },
            onSelect: (items) => {
                if (items.length > 0) {
                    this._setBgMediaId(items[0].id);
                }
            },
        });
        this._bgPicker.open();
    },

    _setBgMediaId(id) {
        this._customBgMediaId = id;
        const previewImg = document.getElementById('custom-bg-preview-img');
        const previewText = document.getElementById('custom-bg-preview-text');
        const removeBtn = document.getElementById('custom-bg-remove-btn');
        const selectBtn = document.getElementById('custom-bg-select-btn');

        if (id) {
            if (previewImg) {
                previewImg.src = `/api/media/${id}/thumbnail`;
                previewImg.style.display = '';
            }
            if (previewText) previewText.style.display = 'none';
            if (removeBtn) removeBtn.style.display = '';
            if (selectBtn) selectBtn.textContent = window.i18n.t('admin.settings.custom_background.change_media');
        } else {
            if (previewImg) { previewImg.src = ''; previewImg.style.display = 'none'; }
            if (previewText) previewText.style.display = '';
            if (removeBtn) removeBtn.style.display = 'none';
            if (selectBtn) selectBtn.textContent = window.i18n.t('admin.settings.custom_background.select_media');
        }

        this._applyBgPreview();
    },

    _applyBgPreview() {
        const bgEnabled = document.getElementById('custom-bg-enabled');
        const enabled = bgEnabled ? bgEnabled.checked : false;

        const el = document.getElementById('custom-background');

        if (!this._settingsLoaded) return;

        if (!enabled || !this._customBgMediaId) {
            if (el) el.style.display = 'none';
            return;
        }

        const get = (id, fallback) => {
            const elem = document.getElementById(id);
            if (!elem) return fallback;
            const val = parseInt(elem.value);
            return isNaN(val) ? fallback : val;
        };

        const opacity = get('custom-bg-opacity', 30);
        const blur = get('custom-bg-blur', 0);
        const brightness = get('custom-bg-brightness', 100);
        const saturation = get('custom-bg-saturation', 100);
        const contrast = get('custom-bg-contrast', 100);
        const zoom = get('custom-bg-zoom', 100);
        const posX = get('custom-bg-position-x', 50);
        const posY = get('custom-bg-position-y', 50);
        const size = this.customBgSizeSelect ? this.customBgSizeSelect.getValue() : 'cover';

        const bgSize = size === 'tile' ? 'auto' : size;
        const bgRepeat = size === 'tile' ? 'repeat' : 'no-repeat';

        // Create the div if it doesn't exist yet (e.g. first time enabling)
        let div = el;
        if (!div) {
            div = document.createElement('div');
            div.id = 'custom-background';
            document.body.insertBefore(div, document.body.firstChild);
        }

        const z = zoom / 100.0;
        const isIntrinsic = size === 'tile' || size === 'auto';
        const invZ = (isIntrinsic && z > 0 && z < 1.0) ? (1.0 / z) : 1.0;

        div.style.display = '';
        div.style.position = 'fixed';
        div.style.width = `${100 * invZ}%`;
        div.style.height = `${100 * invZ}%`;
        div.style.left = `${posX * (1.0 - invZ)}%`;
        div.style.top = `${posY * (1.0 - invZ)}%`;
        div.style.zIndex = '-1';
        div.style.pointerEvents = 'none';
        div.style.backgroundImage = `url('/api/media/${this._customBgMediaId}/file')`;
        div.style.backgroundSize = bgSize;
        div.style.backgroundPosition = `${posX}% ${posY}%`;
        div.style.backgroundRepeat = bgRepeat;
        div.style.transformOrigin = `${posX}% ${posY}%`;
        div.style.transform = `scale(${z})`;
        div.style.opacity = (opacity / 100).toFixed(2);
        div.style.filter = `blur(${blur}px) brightness(${brightness}%) saturate(${saturation}%) contrast(${contrast}%)`;
    },

    async saveCustomBackground() {
        const bgEnabled = document.getElementById('custom-bg-enabled');
        const isChecked = bgEnabled ? bgEnabled.checked : false;

        if (isChecked && !this._customBgMediaId) {
            if (bgEnabled) bgEnabled.checked = false;
            const bgOptions = document.getElementById('custom-bg-options');
            if (bgOptions) bgOptions.style.display = 'none';
            this._applyBgPreview();
        }

        const bgSettings = {
            enabled: document.getElementById('custom-bg-enabled')?.checked || false,
            media_id: this._customBgMediaId || null,
            blur: parseInt(document.getElementById('custom-bg-blur')?.value || '0'),
            brightness: parseInt(document.getElementById('custom-bg-brightness')?.value || '100'),
            saturation: parseInt(document.getElementById('custom-bg-saturation')?.value || '100'),
            contrast: parseInt(document.getElementById('custom-bg-contrast')?.value || '100'),
            zoom: parseInt(document.getElementById('custom-bg-zoom')?.value || '100'),
            size: this.customBgSizeSelect ? this.customBgSizeSelect.getValue() : 'cover',
            position_x: parseInt(document.getElementById('custom-bg-position-x')?.value || '50'),
            position_y: parseInt(document.getElementById('custom-bg-position-y')?.value || '50'),
            opacity: parseInt(document.getElementById('custom-bg-opacity')?.value || '30')
        };

        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify({ custom_background: bgSettings })
            });

            app.showNotification(window.i18n.t('notifications.admin.theming_saved') || window.i18n.t('notifications.admin.settings_updated'), 'success');
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_saving_settings'));
        }
    },

    cleanupCustomButtons() {
        this._teardownCustomButtonDragState();

        if (this.customButtonInstances) {
            this.customButtonInstances.forEach(instance => {
                if (instance.autocomplete) instance.autocomplete.destroy();
            });
            this.customButtonInstances = [];
        }
    },

    _getCustomButtonDragClasses() {
        return ['opacity-30', 'ring-2', 'ring-primary'];
    },

    _hideCustomButtonAutocompletes() {
        if (!this.customButtonInstances) return;
        this.customButtonInstances.forEach(instance => {
            if (instance.autocomplete && typeof instance.autocomplete.hideSuggestions === 'function') {
                instance.autocomplete.hideSuggestions();
            }
        });
    },

    _teardownCustomButtonDragState() {
        window.autoScroll?.stop();

        if (this._customButtonAnnounceTimer) {
            clearTimeout(this._customButtonAnnounceTimer);
            this._customButtonAnnounceTimer = null;
        }

        if (this._customButtonDocMouseUp) {
            document.removeEventListener('mouseup', this._customButtonDocMouseUp);
            this._customButtonDocMouseUp = null;
        }

        if (this._customButtonDocTouchMove) {
            document.removeEventListener('touchmove', this._customButtonDocTouchMove);
            this._customButtonDocTouchMove = null;
        }

        if (this._customButtonDocTouchEnd) {
            document.removeEventListener('touchend', this._customButtonDocTouchEnd);
            document.removeEventListener('touchcancel', this._customButtonDocTouchEnd);
            this._customButtonDocTouchEnd = null;
        }

        const dragClasses = this._getCustomButtonDragClasses();

        if (this._draggedCustomButtonRow) {
            this._draggedCustomButtonRow.classList.remove(...dragClasses);
            this._draggedCustomButtonRow.removeAttribute('draggable');
            this._draggedCustomButtonRow = null;
        }

        if (this._customButtonDragArmedRow) {
            this._customButtonDragArmedRow.removeAttribute('draggable');
            this._customButtonDragArmedRow = null;
        }

        if (this._touchDraggedCustomButtonRow) {
            this._touchDraggedCustomButtonRow.classList.remove(...dragClasses);
            this._touchDraggedCustomButtonRow = null;
        }
        this._touchCustomButtonId = null;

        if (this._kbGrabbedCustomButtonRow) {
            this._kbGrabbedCustomButtonRow.classList.remove('ring-2', 'ring-primary');
            const handle = this._kbGrabbedCustomButtonRow.querySelector('.custom-button-drag-handle');
            if (handle) handle.setAttribute('aria-pressed', 'false');
            this._kbGrabbedCustomButtonRow = null;
            this._kbOriginalNextSibling = null;
        }

        document.body.classList.remove('is-dragging', 'custom-buttons-dragging');
    },

    _moveCustomButtonRow(container, row, referenceNode) {
        if (typeof container.moveBefore === 'function') {
            container.moveBefore(row, referenceNode);
        } else {
            container.insertBefore(row, referenceNode);
        }
    },

    _moveCustomButtonRowWithFlip(container, row, referenceNode, options = {}) {
        const { animateMovedRow = false } = options;
        if (!container || !row) return false;
        if (referenceNode === row || row.nextElementSibling === referenceNode) return false;

        const rows = Array.from(container.querySelectorAll('.custom-button-row'));
        const oldTops = new Map();
        rows.forEach(el => {
            oldTops.set(el, el.getBoundingClientRect().top);
        });

        this._isMovingCustomButton = true;
        try {
            this._moveCustomButtonRow(container, row, referenceNode);
        } finally {
            this._isMovingCustomButton = false;
        }

        if (animateMovedRow) {
            row.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        }

        const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (!reducedMotion) {
            rows.forEach(el => {
                if (!animateMovedRow && el === row) return;
                if (el._flipAnim) {
                    el._flipAnim.cancel();
                    el._flipAnim = null;
                }
                const newTop = el.getBoundingClientRect().top;
                const dy = oldTops.get(el) - newTop;
                if (Math.abs(dy) > 0.5 && typeof el.animate === 'function') {
                    const anim = el.animate(
                        [{ transform: `translateY(${dy}px)` }, { transform: 'translateY(0)' }],
                        { duration: 150, easing: 'cubic-bezier(0.2, 0, 0, 1)' }
                    );
                    el._flipAnim = anim;
                    anim.onfinish = () => { if (el._flipAnim === anim) el._flipAnim = null; };
                    anim.oncancel = () => { if (el._flipAnim === anim) el._flipAnim = null; };
                }
            });
        }

        return true;
    },

    _syncCustomButtonsOrder(container) {
        if (!container) return;
        const ordered = Array.from(container.querySelectorAll('.custom-button-row'))
            .map(row => row._customButtonData)
            .filter(Boolean);
        if (ordered.length === this.customButtons.length) {
            this.customButtons = ordered;
        }
    },

    _updateCustomButtonDropTarget(container, draggedRow, clientY) {
        if (!container || !draggedRow) return;

        const siblings = Array.from(container.querySelectorAll('.custom-button-row'))
            .filter(r => r !== draggedRow);
        if (siblings.length === 0) return;

        const containerRect = container.getBoundingClientRect();
        const pointerY = clientY - containerRect.top - container.clientTop + container.scrollTop;

        let nextTarget = null;
        for (const sibling of siblings) {
            const midpoint = sibling.offsetTop + sibling.offsetHeight / 2;
            if (pointerY < midpoint) {
                nextTarget = sibling;
                break;
            }
        }

        if (this._moveCustomButtonRowWithFlip(container, draggedRow, nextTarget)) {
            this._syncCustomButtonsOrder(container);
        }
    },

    _announceCustomButtonStatus(message) {
        const wrapper = document.getElementById('custom-buttons-container');
        if (!wrapper) return;
        let liveRegion = document.getElementById('custom-buttons-live-region');
        if (!liveRegion) {
            liveRegion = document.createElement('div');
            liveRegion.id = 'custom-buttons-live-region';
            liveRegion.className = 'sr-only';
            liveRegion.setAttribute('aria-live', 'polite');
            liveRegion.setAttribute('aria-atomic', 'true');
            wrapper.appendChild(liveRegion);
        }

        liveRegion.textContent = '';
        if (this._customButtonAnnounceTimer) {
            clearTimeout(this._customButtonAnnounceTimer);
        }
        this._customButtonAnnounceTimer = setTimeout(() => {
            liveRegion.textContent = message;
            this._customButtonAnnounceTimer = null;
        }, 350);
    },

    _setupCustomButtonsContainerEvents(container) {
        const dropZone = document.getElementById('custom-buttons-container') || container;
        if (dropZone.dataset.reorderContainerBound === 'true') return;
        dropZone.dataset.reorderContainerBound = 'true';

        dropZone.addEventListener('dragover', (e) => {
            if (!this._draggedCustomButtonRow) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';

            window.autoScroll?.check(e.clientX, e.clientY, {
                onScroll: (x, y) => this._updateCustomButtonDropTarget(container, this._draggedCustomButtonRow, y)
            });
            this._updateCustomButtonDropTarget(container, this._draggedCustomButtonRow, e.clientY);
        });

        dropZone.addEventListener('dragenter', (e) => {
            if (!this._draggedCustomButtonRow) return;
            e.preventDefault();
        });

        dropZone.addEventListener('drop', (e) => {
            if (!this._draggedCustomButtonRow) return;
            e.preventDefault();
            window.autoScroll?.stop();
        });

        container.addEventListener('focusin', (e) => {
            const handle = e.target.closest('.custom-button-drag-handle');
            if (!handle || !handle.matches(':focus-visible')) return;
            const row = handle.closest('.custom-button-row');
            if (row && !row._flipAnim) {
                row.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            }
        });
    },

    _releaseKeyboardGrabCustomButton(announce = false) {
        if (!this._kbGrabbedCustomButtonRow) return;
        const row = this._kbGrabbedCustomButtonRow;
        const handle = row.querySelector('.custom-button-drag-handle');
        row.classList.remove('ring-2', 'ring-primary');
        if (handle) handle.setAttribute('aria-pressed', 'false');
        this._kbGrabbedCustomButtonRow = null;
        this._kbOriginalNextSibling = null;

        if (announce) {
            const container = document.getElementById('custom-buttons-list');
            const rows = container ? Array.from(container.querySelectorAll('.custom-button-row')) : [];
            const pos = rows.indexOf(row) + 1;
            const label = (row._customButtonData?.title || '').trim() || `#${pos}`;
            this._announceCustomButtonStatus(`${label}: ${pos} / ${rows.length}`);
        }
    },

    _bindCustomButtonDragEvents(container, row, handle) {
        const dragClasses = this._getCustomButtonDragClasses();

        // Arm HTML5 dragging only when grabbing the left handle with primary mouse button
        handle.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            this._customButtonDragArmedRow = row;
            row.setAttribute('draggable', 'true');

            if (!this._customButtonDocMouseUp) {
                this._customButtonDocMouseUp = () => {
                    if (!this._draggedCustomButtonRow && this._customButtonDragArmedRow) {
                        this._customButtonDragArmedRow.removeAttribute('draggable');
                        this._customButtonDragArmedRow = null;
                    }
                    if (this._customButtonDocMouseUp) {
                        document.removeEventListener('mouseup', this._customButtonDocMouseUp);
                        this._customButtonDocMouseUp = null;
                    }
                };
                document.addEventListener('mouseup', this._customButtonDocMouseUp);
            }
        });

        row.addEventListener('dragstart', (e) => {
            if (this._customButtonDragArmedRow !== row) {
                e.preventDefault();
                return;
            }

            this._releaseKeyboardGrabCustomButton(false);
            this._hideCustomButtonAutocompletes();
            if (row.contains(document.activeElement) && document.activeElement !== handle) {
                document.activeElement.blur();
            }

            this._draggedCustomButtonRow = row;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', '');

            document.body.classList.add('is-dragging', 'custom-buttons-dragging');

            setTimeout(() => {
                if (this._draggedCustomButtonRow === row) {
                    row.classList.add(...dragClasses);
                }
            }, 0);
        });

        row.addEventListener('dragend', () => {
            window.autoScroll?.stop();
            row.classList.remove(...dragClasses);
            row.removeAttribute('draggable');
            document.body.classList.remove('is-dragging', 'custom-buttons-dragging');
            this._draggedCustomButtonRow = null;
            this._customButtonDragArmedRow = null;
            this._syncCustomButtonsOrder(container);
        });

        // Touch drag directly on the dedicated handle
        handle.addEventListener('touchstart', (e) => {
            if (this._touchCustomButtonId !== null) return;
            const touch = e.changedTouches[0];
            if (!touch) return;

            e.preventDefault();
            this._releaseKeyboardGrabCustomButton(false);
            this._hideCustomButtonAutocompletes();
            if (row.contains(document.activeElement) && document.activeElement !== handle) {
                document.activeElement.blur();
            }

            this._touchCustomButtonId = touch.identifier;
            this._touchDraggedCustomButtonRow = row;

            document.body.classList.add('is-dragging', 'custom-buttons-dragging');
            row.classList.add(...dragClasses);
            if (navigator.vibrate) {
                navigator.vibrate(25);
            }

            this._customButtonDocTouchMove = (moveEvent) => {
                if (this._touchDraggedCustomButtonRow !== row) return;
                const activeTouch = Array.from(moveEvent.touches).find(t => t.identifier === this._touchCustomButtonId);
                if (!activeTouch) return;

                moveEvent.preventDefault();
                window.autoScroll?.check(activeTouch.clientX, activeTouch.clientY, {
                    onScroll: (x, y) => this._updateCustomButtonDropTarget(container, row, y)
                });
                this._updateCustomButtonDropTarget(container, row, activeTouch.clientY);
            };

            this._customButtonDocTouchEnd = (endEvent) => {
                const ended = Array.from(endEvent.changedTouches).some(t => t.identifier === this._touchCustomButtonId);
                if (!ended) return;

                window.autoScroll?.stop();
                row.classList.remove(...dragClasses);
                document.body.classList.remove('is-dragging', 'custom-buttons-dragging');
                this._syncCustomButtonsOrder(container);
                this._touchCustomButtonId = null;
                this._touchDraggedCustomButtonRow = null;

                if (this._customButtonDocTouchMove) {
                    document.removeEventListener('touchmove', this._customButtonDocTouchMove);
                    this._customButtonDocTouchMove = null;
                }
                if (this._customButtonDocTouchEnd) {
                    document.removeEventListener('touchend', this._customButtonDocTouchEnd);
                    document.removeEventListener('touchcancel', this._customButtonDocTouchEnd);
                    this._customButtonDocTouchEnd = null;
                }
            };

            document.addEventListener('touchmove', this._customButtonDocTouchMove, { passive: false });
            document.addEventListener('touchend', this._customButtonDocTouchEnd);
            document.addEventListener('touchcancel', this._customButtonDocTouchEnd);
        }, { passive: false });

        // Keyboard grab-move-drop + Alt+Arrow reordering on the handle
        handle.addEventListener('keydown', (e) => {
            const isGrabbed = this._kbGrabbedCustomButtonRow === row;

            if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                if (isGrabbed) {
                    this._releaseKeyboardGrabCustomButton(true);
                } else {
                    this._releaseKeyboardGrabCustomButton(false);
                    this._hideCustomButtonAutocompletes();
                    this._kbGrabbedCustomButtonRow = row;
                    this._kbOriginalNextSibling = row.nextElementSibling;
                    row.classList.add('ring-2', 'ring-primary');
                    handle.setAttribute('aria-pressed', 'true');
                    const rows = Array.from(container.querySelectorAll('.custom-button-row'));
                    const pos = rows.indexOf(row) + 1;
                    const label = (row._customButtonData?.title || '').trim() || `#${pos}`;
                    this._announceCustomButtonStatus(`${label}: ${pos} / ${rows.length}`);
                }
                return;
            }

            if (e.key === 'Escape' && isGrabbed) {
                e.preventDefault();
                const originalNext = this._kbOriginalNextSibling;
                const moved = this._moveCustomButtonRowWithFlip(
                    container,
                    row,
                    originalNext && originalNext.parentNode === container ? originalNext : null,
                    { animateMovedRow: true }
                );
                if (moved) {
                    this._syncCustomButtonsOrder(container);
                }
                this._releaseKeyboardGrabCustomButton(false);
                handle.focus({ preventScroll: true });
                return;
            }

            if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && (isGrabbed || e.altKey)) {
                e.preventDefault();
                let referenceNode = undefined;
                if (e.key === 'ArrowUp') {
                    const prev = row.previousElementSibling;
                    if (prev) referenceNode = prev;
                } else {
                    const next = row.nextElementSibling;
                    if (next) referenceNode = next.nextElementSibling;
                }

                if (referenceNode !== undefined) {
                    const moved = this._moveCustomButtonRowWithFlip(container, row, referenceNode, { animateMovedRow: true });
                    if (moved) {
                        this._syncCustomButtonsOrder(container);
                        handle.focus({ preventScroll: true });
                        const rows = Array.from(container.querySelectorAll('.custom-button-row'));
                        const pos = rows.indexOf(row) + 1;
                        const label = (row._customButtonData?.title || '').trim() || `#${pos}`;
                        this._announceCustomButtonStatus(`${label}: ${pos} / ${rows.length}`);
                    }
                }
            }
        });

        handle.addEventListener('blur', () => {
            if (this._isMovingCustomButton) return;
            if (this._kbGrabbedCustomButtonRow === row) {
                this._releaseKeyboardGrabCustomButton(false);
            }
        });
    },

    addCustomButton() {
        this.customButtons.push({ title: '', tags: '' });
        this.renderCustomButtons();
    },

    removeCustomButton(index) {
        this.customButtons.splice(index, 1);
        this.renderCustomButtons();
    },

    updateCustomButton(index, field, value) {
        if (this.customButtons[index]) {
            this.customButtons[index][field] = value;
        }
    },

    renderCustomButtons() {
        const container = document.getElementById('custom-buttons-list');
        if (!container) return;

        container.classList.add('relative');
        this._setupCustomButtonsContainerEvents(container);

        this.cleanupCustomButtons();
        container.innerHTML = '';

        this.customButtons.forEach((btn) => {
            const row = document.createElement('div');
            row.className = 'custom-button-row surface border p-2 flex gap-2 items-stretch relative';
            row._customButtonData = btn;

            const handle = document.createElement('div');
            handle.setAttribute('role', 'button');
            handle.tabIndex = 0;
            handle.className = 'custom-button-drag-handle flex items-center justify-center flex-shrink-0 self-stretch -my-2 py-2 min-h-[34px] px-1 text-secondary cursor-grab active:cursor-grabbing select-none transition-colors';
            handle.setAttribute('aria-pressed', 'false');
            handle.innerHTML = window.Icons.gripVertical({ size: 16 });

            const fieldsWrapper = document.createElement('div');
            fieldsWrapper.className = 'flex-1 min-w-0 flex flex-col sm:flex-row gap-2 sm:items-start';

            const titleInput = document.createElement('input');
            titleInput.type = 'text';
            titleInput.placeholder = window.i18n.t('admin.settings.button_title');
            titleInput.value = btn.title || '';
            titleInput.className = 'w-full sm:w-1/3 min-w-0 bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary';
            const syncTitle = (e) => {
                btn.title = e.target.value;
            };
            titleInput.addEventListener('input', syncTitle);
            titleInput.addEventListener('change', syncTitle);

            const tagContainer = document.createElement('div');
            tagContainer.className = 'w-full sm:flex-1 min-w-0 relative';

            const tagInput = document.createElement('div');
            tagInput.contentEditable = true;
            tagInput.className = 'w-full bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary';
            tagInput.setAttribute('data-placeholder', window.i18n.t('admin.settings.button_tags'));
            tagInput.style.minHeight = '34px';
            tagInput.style.maxHeight = '100px';
            tagInput.style.overflowY = 'auto';
            tagInput.style.whiteSpace = 'pre-wrap';
            tagInput.style.overflowWrap = 'break-word';
            tagInput.textContent = btn.tags || '';

            if (!btn.tags) tagInput.classList.add('empty');

            const instance = { autocomplete: null };

            tagInput.addEventListener('input', () => {
                const text = tagInput.textContent || '';
                btn.tags = text;
                if (!text) tagInput.classList.add('empty');
                else tagInput.classList.remove('empty');
            });

            // Prevent Enter key from adding new lines
            tagInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                }
            });

            tagContainer.appendChild(tagInput);

            if (typeof TagAutocomplete !== 'undefined') {
                const autocomplete = new TagAutocomplete(tagInput, {
                    multipleValues: true,
                    enableQualifiers: true,
                    containerClasses: 'max-h-40 overflow-y-auto w-full bg border border-primary shadow-lg z-10'
                });
                instance.autocomplete = autocomplete;
            }

            this.customButtonInstances.push(instance);

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn-danger p-2 flex items-center justify-center flex-shrink-0 self-center sm:self-start text-xs cursor-pointer h-[34px] w-[34px]';
            removeBtn.title = window.i18n.t('common.delete');
            removeBtn.innerHTML = window.Icons.trash({ size: 14 });
            removeBtn.onclick = () => {
                const currentIndex = this.customButtons.indexOf(btn);
                if (currentIndex !== -1) {
                    this.removeCustomButton(currentIndex);
                }
            };

            this._bindCustomButtonDragEvents(container, row, handle);

            fieldsWrapper.appendChild(titleInput);
            fieldsWrapper.appendChild(tagContainer);

            row.appendChild(handle);
            row.appendChild(fieldsWrapper);
            row.appendChild(removeBtn);
            container.appendChild(row);
        });
    },
});
