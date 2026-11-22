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
        if (this.customButtonInstances) {
            this.customButtonInstances.forEach(instance => {
                if (instance.autocomplete) instance.autocomplete.destroy();
            });
            this.customButtonInstances = [];
        }
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

        this.cleanupCustomButtons();
        container.innerHTML = '';

        this.customButtons.forEach((btn, index) => {
            const row = document.createElement('div');
            row.className = 'flex gap-2 items-start mb-3';

            const titleInput = document.createElement('input');
            titleInput.type = 'text';
            titleInput.placeholder = window.i18n.t('admin.settings.button_title');
            titleInput.value = btn.title || '';
            titleInput.className = 'w-1/3 bg px-3 py-2 border text-xs focus:outline-none hover:border-primary transition-colors focus:border-primary';
            titleInput.addEventListener('change', (e) => {
                this.updateCustomButton(index, 'title', e.target.value);
            });

            const tagContainer = document.createElement('div');
            tagContainer.className = 'flex-1 relative';

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
                this.updateCustomButton(index, 'tags', text);
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
            removeBtn.className = 'btn-danger p-2 flex items-center justify-center flex-shrink-0 text-xs cursor-pointer h-[34px] w-[34px]';
            removeBtn.title = window.i18n.t('common.delete');
            removeBtn.innerHTML = window.Icons.trash({ size: 14 });
            removeBtn.onclick = () => this.removeCustomButton(index);

            row.appendChild(titleInput);
            row.appendChild(tagContainer);
            row.appendChild(removeBtn);
            container.appendChild(row);
        });
    },
});
