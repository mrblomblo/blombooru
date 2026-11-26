// AdminContent AI tagger (ONNX / WD Tagger) settings, custom model management, and testing
(function () {
    const WD_FALLBACK_CONFIG = {
        batch_size: 1,
        temperature: 1.0,
        input_size: 448,
        input_layout: 'nhwc',
        color_space: 'bgr',
        resize_mode: 'pad_white',
        interpolation: 'bicubic',
        normalization: 'none_255',
        norm_mean: [0.5, 0.5, 0.5],
        norm_std: [0.5, 0.5, 0.5],
        output_activation: 'none',
        output_index: 0
    };

    const WD_NUMERIC_PARAMS = {
        batch_size: { id: 'wd-param-batch-size', type: 'int', min: 1, max: 64, fallback: 1 },
        temperature: { id: 'wd-param-temperature', type: 'float', min: 0.05, max: 5.0, fallback: 1.0, decimals: 4 },
        input_size: { id: 'wd-param-input-size', type: 'int', min: 64, max: 2048, fallback: 448 },
        output_index: { id: 'wd-param-output-index', type: 'int', min: 0, max: 15, fallback: 0 }
    };

    const WD_SELECT_PARAMS = {
        input_layout: 'wd-param-input-layout',
        color_space: 'wd-param-color-space',
        resize_mode: 'wd-param-resize-mode',
        interpolation: 'wd-param-interpolation',
        normalization: 'wd-param-normalization',
        output_activation: 'wd-param-output-activation'
    };

    const WD_VEC3_PARAMS = {
        norm_mean: { prefix: 'wd-param-norm-mean-', min: -10.0, max: 10.0, fallback: [0.5, 0.5, 0.5], decimals: 6 },
        norm_std: { prefix: 'wd-param-norm-std-', min: 0.001, max: 10.0, fallback: [0.5, 0.5, 0.5], decimals: 6 }
    };

    const WEIGHT_EXTS = ['.data', '.onnx_data', '.pb', '.bin', '.weights'];
    const LABEL_EXTS = ['.csv', '.json', '.txt'];
    const CONFIG_JSON_NAMES = ['config.json', 'preprocessor_config.json', 'model_config.json'];

    function clampNumber(rawVal, { type = 'float', min, max, fallback, decimals = 4 }) {
        const num = (rawVal === '' || rawVal === null || rawVal === undefined) ? NaN : Number(rawVal);
        const base = Number.isFinite(num) ? (type === 'int' ? Math.round(num) : num) : fallback;
        const clamped = Math.max(min, Math.min(max, base));
        return type === 'int' ? clamped : Number(clamped.toFixed(decimals));
    }

    function classifyUploadRole(filename) {
        const lower = (filename || '').toLowerCase();
        if (CONFIG_JSON_NAMES.includes(lower)) return 'config';
        if (lower.endsWith('.onnx')) return 'model';
        if (LABEL_EXTS.some(ext => lower.endsWith(ext))) return 'labels';
        if (WEIGHT_EXTS.some(ext => lower.endsWith(ext))) return 'weights';
        return 'other';
    }

    Object.assign(AdminContent.prototype, {
        initWDAdvancedControls() {
            if (!this.wdModelsMap) {
                this.wdModelsMap = new Map();
            }

            if (!this.wdParamSelects) {
                this.wdParamSelects = {};
                for (const [paramKey, elemId] of Object.entries(WD_SELECT_PARAMS)) {
                    const el = document.getElementById(elemId);
                    if (el) {
                        this.wdParamSelects[paramKey] = new CustomSelect(el);
                        if (paramKey === 'normalization') {
                            el.addEventListener('change', (e) => {
                                this._toggleCustomNormRow(e.detail?.value || this.wdParamSelects.normalization.getValue());
                            });
                        }
                    }
                }
            }

            if (!this.wdAdvancedEventsBound) {
                this.wdAdvancedEventsBound = true;

                document.querySelectorAll('.wd-param-reset-btn').forEach(btn => {
                    btn.addEventListener('click', () => this.resetSingleWDParam(btn.dataset.param));
                });

                const resetAllBtn = document.getElementById('wd-reset-model-defaults-btn');
                if (resetAllBtn) {
                    resetAllBtn.addEventListener('click', () => this.resetAllWDParams());
                }

                const testBtn = document.getElementById('test-ai-tagger-btn');
                if (testBtn) {
                    testBtn.addEventListener('click', () => this.testAITaggerModel());
                }

                this.initCustomModelUploader();
            }
        },

        _toggleCustomNormRow(normMode) {
            const row = document.getElementById('wd-custom-norm-row');
            if (row) row.style.display = normMode === 'custom' ? 'grid' : 'none';
        },

        _setWDParamField(paramName, value, triggerSelectEvent = false) {
            if (paramName in WD_NUMERIC_PARAMS) {
                const el = document.getElementById(WD_NUMERIC_PARAMS[paramName].id);
                if (el && value !== undefined && value !== null) el.value = value;
                return;
            }
            if (paramName in WD_VEC3_PARAMS) {
                const spec = WD_VEC3_PARAMS[paramName];
                const vec = Array.isArray(value) && value.length === 3 ? value : spec.fallback;
                for (let i = 0; i < 3; i++) {
                    const el = document.getElementById(`${spec.prefix}${i}`);
                    if (el) el.value = vec[i];
                }
                return;
            }
            if (this.wdParamSelects?.[paramName] && value) {
                this.wdParamSelects[paramName].setValue(value, triggerSelectEvent);
            }
        },

        populateWDAdvancedParams(config, fixedBatchOne = false) {
            const cfg = { ...WD_FALLBACK_CONFIG, ...(config || {}) };

            const fixedHint = document.getElementById('wd-fixed-batch-hint');
            if (fixedHint) fixedHint.style.display = fixedBatchOne ? 'block' : 'none';

            for (const key of Object.keys(WD_NUMERIC_PARAMS)) this._setWDParamField(key, cfg[key]);
            for (const key of Object.keys(WD_VEC3_PARAMS)) this._setWDParamField(key, cfg[key]);
            for (const key of Object.keys(WD_SELECT_PARAMS)) this._setWDParamField(key, cfg[key], false);
            this._toggleCustomNormRow(cfg.normalization);
        },

        _getSelectedModelMeta() {
            const modelId = this.wdModelSelect ? this.wdModelSelect.getValue() : null;
            return modelId ? (this.wdModelsMap?.get(modelId) || null) : null;
        },

        resetSingleWDParam(paramName) {
            if (!paramName) return;
            const meta = this._getSelectedModelMeta();
            const defaults = { ...WD_FALLBACK_CONFIG, ...(meta?.default_config || {}) };
            this._setWDParamField(paramName, defaults[paramName], true);
        },

        resetAllWDParams() {
            const meta = this._getSelectedModelMeta();
            this.populateWDAdvancedParams(meta?.default_config || WD_FALLBACK_CONFIG, Boolean(meta?.fixed_batch_one));
        },

        collectClampedWDFormValues() {
            const modelName = this.wdModelSelect ? this.wdModelSelect.getValue() : null;
            const meta = this._getSelectedModelMeta();
            const baseCfg = {
                ...WD_FALLBACK_CONFIG,
                ...(meta?.default_config || {}),
                ...(meta?.effective_config || {})
            };

            const generalEl = document.getElementById('wd-general-threshold');
            const charEl = document.getElementById('wd-character-threshold');

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

            const inferenceConfig = {};
            for (const [key, spec] of Object.entries(WD_NUMERIC_PARAMS)) {
                const el = document.getElementById(spec.id);
                inferenceConfig[key] = clampNumber(el ? el.value : '', { ...spec, fallback: baseCfg[key] });
            }
            for (const [key, spec] of Object.entries(WD_VEC3_PARAMS)) {
                const baseVec = Array.isArray(baseCfg[key]) && baseCfg[key].length === 3 ? baseCfg[key] : spec.fallback;
                inferenceConfig[key] = [0, 1, 2].map(i => {
                    const el = document.getElementById(`${spec.prefix}${i}`);
                    return clampNumber(el ? el.value : '', { ...spec, fallback: baseVec[i] });
                });
            }
            for (const key of Object.keys(WD_SELECT_PARAMS)) {
                inferenceConfig[key] = this.wdParamSelects?.[key] ? this.wdParamSelects[key].getValue() : baseCfg[key];
            }

            return {
                model_name: modelName,
                general_threshold: clampNumber(generalEl ? generalEl.value : '', { min: 0.0, max: 1.0, fallback: 0.35 }),
                character_threshold: clampNumber(charEl ? charEl.value : '', { min: 0.0, max: 1.0, fallback: 0.85 }),
                blacklisted_tags: blacklistedTags,
                blacklisted_categories: blacklistedCategories,
                inference_config: inferenceConfig
            };
        },

        async loadAITaggerSettings() {
            try {
                const res = await fetch('/api/ai-tagger/settings');
                if (!res.ok) return;
                const data = await res.json();

                this.initWDAdvancedControls();

                const generalEl = document.getElementById('wd-general-threshold');
                if (generalEl && data.general_threshold != null) generalEl.value = data.general_threshold;

                const charEl = document.getElementById('wd-character-threshold');
                if (charEl && data.character_threshold != null) charEl.value = data.character_threshold;

                const blacklistEl = document.getElementById('wd-blacklisted-tags');
                if (blacklistEl && data.blacklisted_tags) {
                    blacklistEl.textContent = data.blacklisted_tags.join(' ');
                    setTimeout(() => this.app.tagInputHelper.validateAndStyleTags(blacklistEl), 100);
                }

                const blacklistedCategories = new Set(data.blacklisted_categories || []);
                document.querySelectorAll('.wd-category-btn').forEach(btn => {
                    const cat = btn.dataset.category;
                    this.setCategoryButtonState(btn, blacklistedCategories.has(cat));
                    if (!btn.dataset.bound) {
                        btn.dataset.bound = 'true';
                        btn.addEventListener('click', () => {
                            this.setCategoryButtonState(btn, !btn.classList.contains('bg-danger'));
                        });
                    }
                });

                this.wdModelsMap.clear();
                const modelsList = Array.isArray(data.models) ? data.models : [];
                modelsList.forEach(m => this.wdModelsMap.set(m.id, m));

                const dropdown = document.getElementById('wd-model-dropdown');
                if (dropdown) {
                    dropdown.innerHTML = '';
                    modelsList.forEach(model => {
                        const opt = document.createElement('div');
                        opt.className = 'custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs';
                        opt.dataset.value = model.id;
                        opt.dataset.display = model.display_name || model.id;
                        if (model.is_custom) opt.dataset.icon = 'wrench';
                        opt.textContent = model.display_name || model.id;
                        dropdown.appendChild(opt);
                    });
                }

                const modelSelectEl = document.getElementById('wd-model-select');
                if (modelSelectEl) {
                    if (this.wdModelSelect) this.wdModelSelect.destroy();
                    this.wdModelSelect = new CustomSelect(modelSelectEl);
                    if (!this.wdModelSelectChangeBound) {
                        this.wdModelSelectChangeBound = true;
                        modelSelectEl.addEventListener('change', (e) => {
                            this.onWDModelSelectionChange(e.detail?.value || this.wdModelSelect.getValue());
                        });
                    }
                    if (data.model_name && this.wdModelsMap.has(data.model_name)) {
                        this.wdModelSelect.setValue(data.model_name, false);
                    } else if (modelsList.length > 0) {
                        this.wdModelSelect.setValue(modelsList[0].id, false);
                    }
                }

                const actionBtn = document.getElementById('wd-model-action-btn');
                if (actionBtn && !this.wdModelActionBtnBound) {
                    this.wdModelActionBtnBound = true;
                    actionBtn.addEventListener('click', () => this.handleWDModelAction());
                }

                const initialModel = this.wdModelSelect ? this.wdModelSelect.getValue() : data.model_name;
                if (initialModel) {
                    await this.onWDModelSelectionChange(initialModel);
                }
            } catch (e) {
                console.error('Error loading AI Tagger settings:', e);
            }
        },

        async onWDModelSelectionChange(modelId) {
            const meta = modelId ? this.wdModelsMap.get(modelId) : null;
            if (meta) {
                this.populateWDAdvancedParams(meta.effective_config || meta.default_config, Boolean(meta.fixed_batch_one));
            }
            await this.updateWDModelActionBtn(modelId);
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
                const isCustom = Boolean(status.is_custom);
                const isDownloaded = isCustom || Boolean(status.is_downloaded);
                const displayName = status.display_name || modelName;
                this.wdModelActionState = { modelName, displayName, isDownloaded, isCustom };

                if (this.wdModelsMap.has(modelName)) {
                    const existing = this.wdModelsMap.get(modelName);
                    existing.is_downloaded = isDownloaded;
                    if (status.default_config) existing.default_config = status.default_config;
                    if (status.effective_config) existing.effective_config = status.effective_config;
                    existing.fixed_batch_one = Boolean(status.fixed_batch_one);
                }

                btn.style.display = 'flex';
                if (isDownloaded) {
                    const label = window.i18n.t('common.delete');
                    btn.className = 'btn-danger p-2 flex items-center justify-center flex-shrink-0 text-xs cursor-pointer';
                    btn.title = label;
                    btn.setAttribute('aria-label', label);
                    btn.innerHTML = window.Icons.trash({ size: 14, extra: 'aria-hidden="true"' });
                } else {
                    const label = window.i18n.t('common.download');
                    btn.className = 'btn-primary p-2 flex items-center justify-center flex-shrink-0 text-xs cursor-pointer';
                    btn.title = label;
                    btn.setAttribute('aria-label', label);
                    btn.innerHTML = window.Icons.download({ size: 14, extra: 'aria-hidden="true"' });
                }
            } catch (e) {
                console.error('Error checking model status:', e);
                btn.style.display = 'none';
                this.wdModelActionState = null;
            }
        },

        async handleWDModelAction() {
            if (!this.wdModelActionState?.modelName) return;
            const { modelName, displayName, isDownloaded, isCustom } = this.wdModelActionState;

            if (isDownloaded) {
                const modal = new ModalHelper({
                    id: 'delete-model-modal',
                    type: 'danger',
                    title: window.i18n.t('modal.delete_model.title'),
                    message: window.i18n.t('modal.delete_model.message', { modelName: displayName }),
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
                                const err = await res.json().catch(() => ({}));
                                throw new Error(err.detail || window.i18n.t('notifications.error_occurred'));
                            }
                            const respData = await res.json();
                            app.showNotification(window.i18n.t('notifications.admin.model_deleted'), 'success');

                            if (isCustom) {
                                this.wdModelsMap.delete(modelName);
                                if (this.wdModelSelect) {
                                    this.wdModelSelect.removeOption(modelName);
                                    if (respData.active_model && this.wdModelsMap.has(respData.active_model)) {
                                        this.wdModelSelect.setValue(respData.active_model, false);
                                    }
                                    await this.onWDModelSelectionChange(this.wdModelSelect.getValue());
                                }
                            } else {
                                await this.updateWDModelActionBtn(modelName);
                            }
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

        initCustomModelUploader() {
            this.wdStagedModelFiles = [];
            const area = document.getElementById('wd-custom-model-upload-area');
            const input = document.getElementById('wd-custom-model-files');
            const uploadBtn = document.getElementById('wd-upload-custom-model-btn');

            if (area && input) {
                area.addEventListener('click', (e) => {
                    if (e.target !== input) input.click();
                });
                area.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        input.click();
                    }
                });
                area.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    area.classList.add('drag-over');
                });
                area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
                area.addEventListener('drop', (e) => {
                    e.preventDefault();
                    area.classList.remove('drag-over');
                    if (e.dataTransfer?.files?.length) {
                        this.addCustomModelFiles(e.dataTransfer.files);
                    }
                });
                input.addEventListener('change', () => {
                    if (input.files?.length) {
                        this.addCustomModelFiles(input.files);
                        input.value = '';
                    }
                });
            }

            if (uploadBtn) {
                uploadBtn.addEventListener('click', () => this.uploadCustomModel());
            }
        },

        addCustomModelFiles(fileList) {
            const nameInput = document.getElementById('wd-custom-model-name');

            for (const file of Array.from(fileList)) {
                const role = classifyUploadRole(file.name);
                if (role === 'other') {
                    app.showNotification(
                        window.i18n.t('admin.ai_tagger.unsupported_file_type', { filename: file.name }),
                        'error'
                    );
                    continue;
                }
                const lower = file.name.toLowerCase();
                this.wdStagedModelFiles = this.wdStagedModelFiles.filter(
                    existing => existing.name.toLowerCase() !== lower
                );
                this.wdStagedModelFiles.push(file);

                if (role === 'model' && nameInput && !nameInput.value.trim()) {
                    const stem = file.name.replace(/\.onnx$/i, '').trim();
                    if (stem && stem.toLowerCase() !== 'model') {
                        nameInput.value = stem;
                    }
                }
            }
            this.renderStagedCustomModelFiles();
        },

        renderStagedCustomModelFiles() {
            const listEl = document.getElementById('wd-custom-model-file-list');
            if (!listEl) return;
            listEl.innerHTML = '';

            const roleLabels = {
                model: window.i18n.t('common.model'),
                labels: window.i18n.t('admin.ai_tagger.file_role_labels'),
                config: window.i18n.t('admin.ai_tagger.file_role_config'),
                weights: window.i18n.t('admin.ai_tagger.file_role_weights')
            };

            this.wdStagedModelFiles.forEach((file, idx) => {
                const role = classifyUploadRole(file.name);
                const li = document.createElement('li');
                li.className = 'flex items-center justify-between gap-2 px-3 py-1.5 surface border';

                const left = document.createElement('div');
                left.className = 'flex items-center gap-2 min-w-0';

                const badge = document.createElement('span');
                badge.className = 'px-1.5 py-0.5 border border-primary text-[10px] uppercase font-bold shrink-0';
                badge.textContent = roleLabels[role] || role;

                const fname = document.createElement('span');
                fname.className = 'font-mono truncate';
                fname.textContent = file.name;

                const size = document.createElement('span');
                size.className = 'text-secondary shrink-0';
                size.textContent = `(${formatFileSize(file.size)})`;

                left.appendChild(badge);
                left.appendChild(fname);
                left.appendChild(size);

                const removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.className = 'btn p-1 text-secondary hover:text-danger shrink-0 cursor-pointer';
                removeBtn.setAttribute('aria-label', `${window.i18n.t('common.remove')}: ${file.name}`);
                removeBtn.innerHTML = window.Icons.close({ size: 12, extra: 'aria-hidden="true"' });
                removeBtn.addEventListener('click', () => {
                    this.wdStagedModelFiles.splice(idx, 1);
                    this.renderStagedCustomModelFiles();
                });

                li.appendChild(left);
                li.appendChild(removeBtn);
                listEl.appendChild(li);
            });
        },

        uploadCustomModel() {
            const files = this.wdStagedModelFiles || [];
            const modelCount = files.filter(f => classifyUploadRole(f.name) === 'model').length;
            const labelCount = files.filter(f => classifyUploadRole(f.name) === 'labels').length;

            if (modelCount !== 1 || labelCount < 1) {
                app.showNotification(window.i18n.t('admin.ai_tagger.select_onnx_and_labels_error'), 'error');
                return;
            }

            const uploadBtn = document.getElementById('wd-upload-custom-model-btn');
            const statusBox = document.getElementById('wd-custom-model-upload-status');
            const progressTrack = document.getElementById('wd-custom-model-progress-track');
            const progressBar = document.getElementById('wd-custom-model-progress');
            const statusText = document.getElementById('wd-custom-model-status-text');
            const nameInput = document.getElementById('wd-custom-model-name');

            const setProgress = (pct, validating = false) => {
                if (progressBar) {
                    progressBar.style.width = `${pct}%`;
                    progressBar.classList.toggle('animate-pulse', validating);
                }
                if (progressTrack) {
                    progressTrack.setAttribute('aria-valuenow', String(pct));
                }
            };

            const formData = new FormData();
            files.forEach(f => formData.append('files', f, f.name));
            formData.append('name', nameInput ? nameInput.value.trim() : '');

            if (uploadBtn) uploadBtn.disabled = true;
            if (statusBox) statusBox.style.display = 'block';
            setProgress(0, false);
            if (statusText) statusText.textContent = window.i18n.t('admin.ai_tagger.uploading_progress', { percent: 0 });

            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/ai-tagger/custom-models');

            xhr.upload.addEventListener('progress', (e) => {
                if (!e.lengthComputable) return;
                const pct = Math.min(100, Math.round((e.loaded / e.total) * 100));
                if (pct >= 100) {
                    setProgress(100, true);
                    if (statusText) statusText.textContent = window.i18n.t('admin.ai_tagger.validating_model');
                } else {
                    setProgress(pct, false);
                    if (statusText) {
                        statusText.textContent = window.i18n.t('admin.ai_tagger.uploading_progress', { percent: pct });
                    }
                }
            });

            xhr.upload.addEventListener('load', () => {
                setProgress(100, true);
                if (statusText) statusText.textContent = window.i18n.t('admin.ai_tagger.validating_model');
            });

            xhr.addEventListener('load', async () => {
                if (uploadBtn) uploadBtn.disabled = false;
                if (statusBox) statusBox.style.display = 'none';

                let body = {};
                try {
                    body = JSON.parse(xhr.responseText || '{}');
                } catch (_) {
                    body = {};
                }

                if (xhr.status >= 200 && xhr.status < 300 && body.model) {
                    this.wdStagedModelFiles = [];
                    this.renderStagedCustomModelFiles();
                    if (nameInput) nameInput.value = '';

                    const newModel = body.model;
                    this.wdModelsMap.set(newModel.id, newModel);

                    if (this.wdModelSelect) {
                        this.wdModelSelect.addOption(newModel.id, newModel.display_name, true, 'wrench');
                        await this.onWDModelSelectionChange(newModel.id);
                    }

                    app.showNotification(
                        window.i18n.t('admin.ai_tagger.custom_model_uploaded', { name: newModel.display_name }),
                        'success'
                    );
                    if (Array.isArray(body.warnings) && body.warnings.length > 0) {
                        app.showNotification(body.warnings.join(' '), 'warning');
                    }
                } else {
                    app.showNotification(body.detail || window.i18n.t('notifications.upload_failed'), 'error');
                }
            });

            xhr.addEventListener('error', () => {
                if (uploadBtn) uploadBtn.disabled = false;
                if (statusBox) statusBox.style.display = 'none';
                app.showNotification(window.i18n.t('common.network_error'), 'error');
            });

            xhr.send(formData);
        },

        async testAITaggerModel() {
            const testBtn = document.getElementById('test-ai-tagger-btn');
            if (!testBtn) return;

            const payload = this.collectClampedWDFormValues();
            if (!payload.model_name) return;

            const meta = this.wdModelsMap.get(payload.model_name);
            if (!meta?.is_custom) {
                const downloadModal = new ModelDownloadModal();
                const isReady = await downloadModal.ensureModelReady(payload.model_name);
                if (!isReady) return;
                await this.updateWDModelActionBtn(payload.model_name);
            }

            const origText = testBtn.textContent;
            testBtn.disabled = true;
            testBtn.textContent = window.i18n.t('admin.actions.testing');

            try {
                const res = await fetch('/api/ai-tagger/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(data.detail || window.i18n.t('notifications.error_occurred'));
                }
                this.renderWDTestResult(data, null);
            } catch (e) {
                this.renderWDTestResult(null, e.message);
            } finally {
                testBtn.disabled = false;
                testBtn.textContent = origText;
            }
        },

        renderWDTestResult(data, errorMessage) {
            const panel = document.getElementById('wd-model-test-result');
            if (!panel) return;

            panel.innerHTML = '';
            panel.style.display = 'block';

            const header = document.createElement('div');
            header.className = 'flex items-center justify-between gap-2 pb-2 border-b';

            const titleWrap = document.createElement('div');
            titleWrap.className = 'font-bold text-xs flex items-center gap-2';
            titleWrap.textContent = window.i18n.t('admin.ai_tagger.test_result_title');

            const closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.className = 'btn p-1 text-secondary hover:text cursor-pointer';
            closeBtn.setAttribute('aria-label', window.i18n.t('common.close'));
            closeBtn.innerHTML = window.Icons.close({ size: 12, extra: 'aria-hidden="true"' });
            closeBtn.addEventListener('click', () => {
                panel.style.display = 'none';
                panel.innerHTML = '';
            });

            header.appendChild(titleWrap);
            header.appendChild(closeBtn);
            panel.appendChild(header);

            if (errorMessage) {
                panel.classList.add('border-danger');
                const errEl = document.createElement('div');
                errEl.className = 'text-danger font-mono break-words';
                errEl.textContent = errorMessage;
                panel.appendChild(errEl);
                return;
            }

            panel.classList.remove('border-danger');

            const eff = data.effective_settings || {};
            const inf = eff.inference_config || {};

            const bodyLayout = document.createElement('div');
            bodyLayout.className = 'flex flex-col sm:flex-row gap-4 items-start';

            const thumb = document.createElement('img');
            thumb.src = '/static/images/no-thumbnail.png';
            thumb.alt = 'no-thumbnail.png';
            thumb.width = 112;
            thumb.height = 112;
            thumb.className = 'w-28 h-28 shrink-0 border surface object-contain';
            bodyLayout.appendChild(thumb);

            const detailsCol = document.createElement('div');
            detailsCol.className = 'flex-1 min-w-0 space-y-3';

            const metaGrid = document.createElement('div');
            metaGrid.className = 'flex flex-wrap gap-2 text-[11px] font-mono text-secondary';
            [
                `model=${data.display_name || data.model_used}`,
                `time=${data.inference_time_ms}ms`,
                `provider=${data.provider || 'CPUExecutionProvider'}`,
                `general_threshold=${eff.general_threshold}`,
                `character_threshold=${eff.character_threshold}`,
                `batch_size=${inf.batch_size}`,
                `temperature=${inf.temperature}`,
                `input_size=${inf.input_size}`,
                `input_layout=${inf.input_layout}`,
                `output_activation=${data.resolved_activation || inf.output_activation}`
            ].forEach(item => {
                const pill = document.createElement('span');
                pill.className = 'px-2 py-0.5 surface border';
                pill.textContent = item;
                metaGrid.appendChild(pill);
            });
            detailsCol.appendChild(metaGrid);

            if (Array.isArray(data.warnings) && data.warnings.length > 0) {
                const warnList = document.createElement('ul');
                warnList.className = 'space-y-1 text-warning';
                data.warnings.forEach(w => {
                    const li = document.createElement('li');
                    li.textContent = w;
                    warnList.appendChild(li);
                });
                detailsCol.appendChild(warnList);
            }

            const validTagCats = new Set(['general', 'character', 'copyright', 'artist', 'meta']);
            const makeTagBadge = (t, extraClass = '') => {
                const span = document.createElement('span');
                const rawCat = (t.category || 'general').toLowerCase();
                const cat = validTagCats.has(rawCat) ? rawCat : 'general';
                span.className = `tag ${cat} tag-text${extraClass ? ' ' + extraClass : ''}`;
                span.textContent = `${t.name} (${(Number(t.confidence || 0) * 100).toFixed(1)}%)`;
                return span;
            };

            const tags = Array.isArray(data.tags) ? data.tags : [];
            if (tags.length > 0) {
                const tagsWrap = document.createElement('div');
                tagsWrap.className = 'flex flex-wrap gap-1.5 pt-1';
                tags.forEach(t => tagsWrap.appendChild(makeTagBadge(t)));
                detailsCol.appendChild(tagsWrap);
            } else {
                const emptyMsg = document.createElement('div');
                emptyMsg.className = 'text-secondary italic';
                emptyMsg.textContent = window.i18n.t('admin.ai_tagger.test_no_tags');
                detailsCol.appendChild(emptyMsg);

                if (Array.isArray(data.top_raw_tags) && data.top_raw_tags.length > 0) {
                    const rawContainer = document.createElement('div');
                    rawContainer.className = 'pt-2 border-t space-y-1.5';

                    const rawTitle = document.createElement('div');
                    rawTitle.className = 'text-[11px] font-bold text-secondary';
                    rawTitle.textContent = window.i18n.t('admin.ai_tagger.test_top_raw_tags');
                    rawContainer.appendChild(rawTitle);

                    const rawWrap = document.createElement('div');
                    rawWrap.className = 'flex flex-wrap gap-1.5';
                    data.top_raw_tags.slice(0, 8).forEach(t => rawWrap.appendChild(makeTagBadge(t, 'opacity-75')));
                    rawContainer.appendChild(rawWrap);
                    detailsCol.appendChild(rawContainer);
                }
            }

            bodyLayout.appendChild(detailsCol);
            panel.appendChild(bodyLayout);
        },

        async saveAITaggerSettings() {
            const btn = document.getElementById('save-ai-tagger-btn');
            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = window.i18n.t('modal.buttons.saving');

            const payload = this.collectClampedWDFormValues();

            try {
                const res = await fetch('/api/ai-tagger/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || window.i18n.t('notifications.admin.error_saving_settings'));
                }

                const savedData = await res.json();
                if (Array.isArray(savedData.models)) {
                    savedData.models.forEach(m => this.wdModelsMap.set(m.id, m));
                    if (payload.model_name && this.wdModelsMap.has(payload.model_name)) {
                        const updatedMeta = this.wdModelsMap.get(payload.model_name);
                        this.populateWDAdvancedParams(updatedMeta.effective_config, Boolean(updatedMeta.fixed_batch_one));
                    }
                }

                const generalEl = document.getElementById('wd-general-threshold');
                if (generalEl && savedData.general_threshold != null) generalEl.value = savedData.general_threshold;
                const charEl = document.getElementById('wd-character-threshold');
                if (charEl && savedData.character_threshold != null) charEl.value = savedData.character_threshold;

                app.showNotification(window.i18n.t('admin.ai_tagger.settings_saved'), 'success');
            } catch (e) {
                app.showNotification(e.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    });
})();
