// AdminContent AI tagger (WD Tagger) and near-duplicate settings/backfill
Object.assign(AdminContent.prototype, {
    async loadAITaggerSettings() {
        try {
            const res = await fetch('/api/ai-tagger/settings');
            if (!res.ok) return;
            const data = await res.json();

            const generalEl = document.getElementById('wd-general-threshold');
            if (generalEl && data.general_threshold != null) generalEl.value = data.general_threshold;

            const charEl = document.getElementById('wd-character-threshold');
            if (charEl && data.character_threshold != null) charEl.value = data.character_threshold;

            const blacklistEl = document.getElementById('wd-blacklisted-tags');
            if (blacklistEl && data.blacklisted_tags) {
                blacklistEl.textContent = data.blacklisted_tags.join(' ');
                setTimeout(() => this.app.tagInputHelper.validateAndStyleTags(blacklistEl), 100);
            }

            // Init blacklisted category buttons
            const blacklistedCategories = new Set(data.blacklisted_categories || []);
            document.querySelectorAll('.wd-category-btn').forEach(btn => {
                const cat = btn.dataset.category;
                const isBlacklisted = blacklistedCategories.has(cat);
                this.setCategoryButtonState(btn, isBlacklisted);
                if (!btn.dataset.bound) {
                    btn.dataset.bound = 'true';
                    btn.addEventListener('click', () => {
                        const nowBlacklisted = !btn.classList.contains('bg-danger');
                        this.setCategoryButtonState(btn, nowBlacklisted);
                    });
                }
            });

            // Populate model dropdown
            const dropdown = document.getElementById('wd-model-dropdown');
            if (dropdown && data.available_models) {
                dropdown.innerHTML = '';
                data.available_models.forEach(model => {
                    const opt = document.createElement('div');
                    opt.className = 'custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs';
                    opt.dataset.value = model;
                    opt.textContent = model;
                    dropdown.appendChild(opt);
                });
            }

            // Init custom select for model
            const modelSelectEl = document.getElementById('wd-model-select');
            if (modelSelectEl) {
                this.wdModelSelect = new CustomSelect(modelSelectEl);
                modelSelectEl.addEventListener('change', (e) => {
                    this.updateWDModelActionBtn(e.detail?.value || this.wdModelSelect.getValue());
                });
                if (data.model_name) this.wdModelSelect.setValue(data.model_name);
            }

            const actionBtn = document.getElementById('wd-model-action-btn');
            if (actionBtn && !this.wdModelActionBtnBound) {
                this.wdModelActionBtnBound = true;
                actionBtn.addEventListener('click', () => this.handleWDModelAction());
            }

            const initialModel = data.model_name || (this.wdModelSelect ? this.wdModelSelect.getValue() : null);
            if (initialModel) {
                await this.updateWDModelActionBtn(initialModel);
            }
        } catch (e) {
            console.error('Error loading AI Tagger settings:', e);
        }
    },

    setCategoryButtonState(btn, isBlacklisted) {
        if (isBlacklisted) {
            btn.classList.remove('bg', 'hover:border-primary');
            btn.classList.add('bg-danger', 'border-danger', 'tag-text', 'hover:bg-danger');
        } else {
            btn.classList.remove('bg-danger', 'border-danger', 'tag-text', 'hover:bg-danger');
            btn.classList.add('bg', 'hover:border-primary');
        }
    },

    async updateWDModelActionBtn(modelName) {
        const btn = document.getElementById('wd-model-action-btn');
        if (!btn) return;

        if (!modelName) {
            btn.style.display = 'none';
            this.wdModelActionState = null;
            return;
        }

        try {
            const res = await fetch(`/api/ai-tagger/model-status/${encodeURIComponent(modelName)}`);
            if (!res.ok) {
                btn.style.display = 'none';
                this.wdModelActionState = null;
                return;
            }
            const status = await res.json();
            const isDownloaded = Boolean(status.is_downloaded);
            this.wdModelActionState = { modelName, isDownloaded };

            btn.style.display = 'flex';
            if (isDownloaded) {
                btn.className = 'btn-danger p-2 flex items-center justify-center flex-shrink-0 text-xs';
                btn.title = window.i18n.t('common.delete');
                btn.innerHTML = window.Icons.trash({ size: 14 });
            } else {
                btn.className = 'btn-primary p-2 flex items-center justify-center flex-shrink-0 text-xs';
                btn.title = window.i18n.t('common.download');
                btn.innerHTML = window.Icons.download({ size: 14 });
            }
        } catch (e) {
            console.error('Error checking model status:', e);
            btn.style.display = 'none';
            this.wdModelActionState = null;
        }
    },

    async handleWDModelAction() {
        if (!this.wdModelActionState || !this.wdModelActionState.modelName) return;
        const { modelName, isDownloaded } = this.wdModelActionState;

        if (isDownloaded) {
            const modal = new ModalHelper({
                id: 'delete-model-modal',
                type: 'danger',
                title: window.i18n.t('modal.delete_model.title'),
                message: window.i18n.t('modal.delete_model.message', { modelName }),
                confirmText: window.i18n.t('common.delete'),
                cancelText: window.i18n.t('common.cancel'),
                confirmId: 'delete-model-confirm-yes',
                cancelId: 'delete-model-confirm-no',
                onConfirm: async () => {
                    const btn = document.getElementById('wd-model-action-btn');
                    if (btn) btn.disabled = true;
                    try {
                        const res = await fetch(`/api/ai-tagger/model/${encodeURIComponent(modelName)}`, {
                            method: 'DELETE'
                        });
                        if (!res.ok) {
                            const err = await res.json();
                            throw new Error(err.detail || 'Failed to delete model');
                        }
                        app.showNotification(window.i18n.t('notifications.admin.model_deleted'), 'success');
                        await this.updateWDModelActionBtn(modelName);
                    } catch (e) {
                        app.showNotification(e.message, 'error');
                    } finally {
                        if (btn) btn.disabled = false;
                    }
                }
            });
            modal.show();
        } else {
            const downloadModal = new ModelDownloadModal();
            const isReady = await downloadModal.ensureModelReady(modelName);
            if (isReady) {
                await this.updateWDModelActionBtn(modelName);
            }
        }
    },

    async saveAITaggerSettings() {
        const btn = document.getElementById('save-ai-tagger-btn');
        const originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = window.i18n.t('admin.actions.testing');

        const generalEl = document.getElementById('wd-general-threshold');
        const charEl = document.getElementById('wd-character-threshold');
        const modelName = this.wdModelSelect ? this.wdModelSelect.getValue() : null;

        let blacklistedTags = [];
        const blacklistEl = document.getElementById('wd-blacklisted-tags');
        if (blacklistEl) {
            const text = this.app.tagInputHelper.getPlainTextFromDiv(blacklistEl);
            blacklistedTags = text.split(/\s+/).filter(t => t.length > 0);
        }

        const blacklistedCategories = [];
        document.querySelectorAll('.wd-category-btn').forEach(btn => {
            if (btn.classList.contains('bg-danger') && btn.dataset.category) {
                blacklistedCategories.push(btn.dataset.category);
            }
        });

        const body = {};
        if (generalEl && generalEl.value) body.general_threshold = parseFloat(generalEl.value);
        if (charEl && charEl.value) body.character_threshold = parseFloat(charEl.value);
        if (modelName) body.model_name = modelName;
        body.blacklisted_tags = blacklistedTags;
        body.blacklisted_categories = blacklistedCategories;

        try {
            const res = await fetch('/api/ai-tagger/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to save settings');
            }

            app.showNotification(window.i18n.t('admin.ai_tagger.settings_saved'), 'success');
        } catch (e) {
            app.showNotification(e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    },

    async loadNearDuplicateSettings() {
        if (!document.getElementById('near-duplicates-settings-form')) return;
        try {
            const res = await fetch('/api/admin/near-duplicates');
            if (!res.ok) return;
            const data = await res.json();

            const enabledEl = document.getElementById('near-duplicates-enabled');
            if (enabledEl) enabledEl.checked = !!data.enabled;
            const distanceEl = document.getElementById('near-duplicates-max-distance');
            if (distanceEl && data.max_distance != null) distanceEl.value = data.max_distance;
        } catch (e) {
            console.error('Failed to load near-duplicate settings:', e);
        }
    },

    async saveNearDuplicateSettings() {
        const btn = document.getElementById('save-near-duplicates-btn');
        const originalText = btn.textContent;
        btn.disabled = true;

        const enabledEl = document.getElementById('near-duplicates-enabled');
        const distanceEl = document.getElementById('near-duplicates-max-distance');
        const body = { enabled: !!(enabledEl && enabledEl.checked) };
        if (distanceEl && distanceEl.value !== '') {
            body.max_distance = Math.max(0, Math.min(64, parseInt(distanceEl.value, 10) || 0));
        }

        try {
            const res = await fetch('/api/admin/near-duplicates', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(typeof err.detail === 'string' ? err.detail : 'Failed to save settings');
            }
            const data = await res.json();
            if (distanceEl) distanceEl.value = data.max_distance;
            app.showNotification(window.i18n.t('admin.settings.settings_saved'), 'success');
        } catch (e) {
            app.showNotification(e.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    },

    async checkNearDuplicateBackfillStatus() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.checkJob('near_duplicate_backfill');
        }
    },

    async startNearDuplicateBackfill() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.start('near_duplicate_backfill');
        }
    },

    async pollNearDuplicateBackfill() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.poll('near_duplicate_backfill');
        }
    },
});
