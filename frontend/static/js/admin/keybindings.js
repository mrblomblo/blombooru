class AdminKeybindings {
    constructor(adminPanel) {
        this.app = adminPanel;
        this._actions = [];
        this._savedBindings = {};
        this._pendingBindings = {};
        this._captureCleanup = null;
    }

    async load() {
        try {
            const res = await app.apiCall('/api/admin/keybindings');
            this._actions = res.actions || [];
            this._savedBindings = JSON.parse(JSON.stringify(res.bindings || {}));
            this._pendingBindings = JSON.parse(JSON.stringify(res.bindings || {}));
            this._render();
            this._bindGlobalEvents();
        } catch (e) {
            console.error('AdminKeybindings: failed to load', e);
        }
    }

    _render() {
        const byContext = {};
        for (const action of this._actions) {
            (byContext[action.context] = byContext[action.context] || []).push(action);
        }

        for (const [context, actions] of Object.entries(byContext)) {
            const container = document.querySelector(
                `#keybindings-context-${context} .keybindings-rows`
            );
            if (!container) continue;
            container.innerHTML = '';
            for (const action of actions) {
                container.appendChild(this._buildRow(action));
            }
        }
    }

    _buildRow(action) {
        const binding = this._pendingBindings[action.id] || action.default;
        const label = window.i18n.t(action.label_key);
        const isDirty = this._isBindingDirty(action.id);

        const row = document.createElement('div');
        row.className = `keybinding-row flex items-center justify-between gap-3 px-1.5 py-1.5 sm:px-3 border transition-colors surface ${isDirty ? 'border-primary' : ''
            }`;
        row.dataset.actionId = action.id;

        const editTitle = window.i18n.t('admin.keybindings.edit');
        const resetTitle = window.i18n.t('admin.keybindings.reset');
        const modifiedLabel = window.i18n.t('admin.keybindings.modified');

        const chipText = binding.key || binding.code || '?';
        const isSingleChar = chipText.length === 1;

        row.innerHTML = `
            <div class="flex items-center gap-2 flex-1">
                <span class="text-xs font-bold text">${escapeHtml(label)}</span>
                ${isDirty ? `<span class="text-[10px] uppercase font-bold px-1.5 py-0.5 border border-primary">${escapeHtml(modifiedLabel)}</span>` : ''}
            </div>
            <div class="flex items-center gap-2">
                <kbd class="keybinding-chip bg px-1.5 py-0.5 text-xs border font-mono ${isSingleChar ? 'uppercase' : ''}"
                     data-action-id="${escapeHtml(action.id)}">${escapeHtml(chipText)}</kbd>


                <button class="btn keybinding-edit-btn p-2 text-xs flex items-center justify-center hover:border-primary transition-colors cursor-pointer"
                        data-action-id="${escapeHtml(action.id)}"
                        title="${escapeHtml(editTitle)}">
                    ${window.Icons.edit({ size: 14 })}
                </button>

                <button class="btn keybinding-reset-btn p-2 text-xs text-secondary flex items-center justify-center hover:border-primary transition-colors cursor-pointer"
                        data-action-id="${escapeHtml(action.id)}"
                        title="${escapeHtml(resetTitle)}">
                    ${window.Icons.reset({ size: 14 })}
                </button>
            </div>
        `;

        this._bindRowEvents(row, action);
        return row;
    }

    _isBindingDirty(actionId) {
        const pending = this._pendingBindings[actionId];
        const saved = this._savedBindings[actionId];
        if (!pending) return false;
        if (!saved) return true;
        return pending.code !== saved.code;
    }

    _refreshRow(actionId) {
        const action = this._actions.find(a => a.id === actionId);
        if (!action) return;
        const row = document.querySelector(`.keybinding-row[data-action-id="${actionId}"]`);
        if (!row) return;

        const newRow = this._buildRow(action);
        row.replaceWith(newRow);
    }

    _bindGlobalEvents() {
        const saveBtn = document.getElementById('keybindings-save-btn');
        if (saveBtn) {
            saveBtn.onclick = () => this.saveAll();
        }

        const resetAllBtn = document.getElementById('keybindings-reset-all-btn');
        if (resetAllBtn) {
            resetAllBtn.onclick = () => this.promptResetAll();
        }
    }

    _bindRowEvents(row, action) {
        const editBtn = row.querySelector('.keybinding-edit-btn');
        if (editBtn) {
            editBtn.onclick = () => this.startCapture(action.id, row, action);
        }

        const resetBtn = row.querySelector('.keybinding-reset-btn');
        if (resetBtn) {
            resetBtn.onclick = () => this.resetOne(action.id);
        }
    }

    startCapture(actionId, row, action) {
        if (this._captureCleanup) this._captureCleanup();

        const promptText = window.i18n.t('admin.keybindings.press_key_prompt');
        const cancelTitle = window.i18n.t('common.cancel');
        const label = window.i18n.t(action.label_key);

        row.className = 'keybinding-row flex items-center justify-between gap-3 px-1.5 py-1.5 sm:px-3 border border-primary surface';
        row.innerHTML = `
            <div class="flex items-center gap-2 flex-1">
                <span class="text-xs font-bold text">${escapeHtml(label)}</span>
                <span class="text-xs text animate-pulse">${escapeHtml(promptText)}</span>
            </div>
            <div class="flex items-center gap-2">
                <button class="btn keybinding-cancel-capture-btn p-2 text-xs text flex items-center justify-center hover:border-danger transition-colors cursor-pointer"
                        title="${escapeHtml(cancelTitle)}">
                    ${window.Icons.close({ size: 14 })}
                </button>
            </div>
        `;

        const cancelBtn = row.querySelector('.keybinding-cancel-capture-btn');
        if (cancelBtn) cancelBtn.onclick = () => cleanup();

        const self = this;

        function onKeydown(e) {
            e.preventDefault();
            e.stopPropagation();

            if (e.code === 'Escape') {
                cleanup();
                return;
            }

            // Reject modifier keys
            if (e.ctrlKey || e.shiftKey || e.altKey || e.metaKey) {
                self._showStatus(window.i18n.t('admin.keybindings.modifier_error'), 'danger');
                return;
            }

            if (['Shift', 'Control', 'Alt', 'Meta', 'AltGraph'].includes(e.key)) {
                return;
            }

            const code = e.code;
            const key = e.key;

            const disallowedCodes = ['Tab', 'Enter', 'NumpadEnter', 'Escape', 'CapsLock', 'ContextMenu'];
            if (disallowedCodes.includes(code) || disallowedCodes.includes(key)) {
                self._showStatus(window.i18n.t('admin.keybindings.disallowed_error'), 'danger');
                return;
            }

            // In-context conflict check against pending bindings
            const conflict = self._findConflict(actionId, code);
            if (conflict) {
                const conflictAction = self._actions.find(a => a.id === conflict);
                const conflictLabel = conflictAction && window.i18n
                    ? window.i18n.t(conflictAction.label_key)
                    : conflict;
                const msg = window.i18n
                    ? window.i18n.t('admin.keybindings.conflict_error', { action: conflictLabel })
                    : `Conflicts with: ${conflictLabel}`;
                self._showStatus(msg, 'danger');
                return;
            }

            // Stage candidate key locally
            self._pendingBindings[actionId] = { code, key };
            cleanup();
        }

        function cleanup() {
            document.removeEventListener('keydown', onKeydown, { capture: true });
            self._captureCleanup = null;
            self._refreshRow(actionId);
        }

        this._captureCleanup = cleanup;
        document.addEventListener('keydown', onKeydown, { capture: true });
    }

    _findConflict(actionId, code) {
        const action = this._actions.find(a => a.id === actionId);
        if (!action) return null;

        for (const other of this._actions) {
            if (other.id === actionId) continue;
            if (other.context !== action.context) continue;
            const otherBinding = this._pendingBindings[other.id] || other.default;
            if (otherBinding && otherBinding.code === code) {
                return other.id;
            }
        }
        return null;
    }

    resetOne(actionId) {
        const action = this._actions.find(a => a.id === actionId);
        if (!action) return;
        this._pendingBindings[actionId] = { ...action.default };
        this._refreshRow(actionId);
    }

    async saveAll() {
        try {
            const res = await app.apiCall('/api/admin/keybindings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bindings: this._pendingBindings }),
            });

            this._savedBindings = JSON.parse(JSON.stringify(res.bindings || this._pendingBindings));
            this._pendingBindings = JSON.parse(JSON.stringify(this._savedBindings));

            // Sync with global runtime instance
            if (window.keybindings) {
                window.keybindings.bindings = { ...this._savedBindings };
            }

            this._showStatus(window.i18n.t('admin.keybindings.saved'), 'success');
            this._render();

        } catch (e) {
            let msg = e.message || 'Error saving keybindings.';
            try {
                const detail = JSON.parse(e.message);
                if (detail && detail.conflicts_with) {
                    const conflictAction = this._actions.find(a => a.id === detail.conflicts_with);
                    const conflictLabel = conflictAction && window.i18n
                        ? window.i18n.t(conflictAction.label_key)
                        : detail.conflicts_with;
                    msg = window.i18n
                        ? window.i18n.t('admin.keybindings.conflict_error', { action: conflictLabel })
                        : `Conflicts with: ${conflictLabel}`;
                }
            } catch (_) { }
            this._showStatus(msg, 'danger');
        }
    }

    promptResetAll() {
        const title = window.i18n
            ? window.i18n.t('admin.keybindings.reset_all_confirm_title')
            : 'Reset All Keyboard Shortcuts';
        const message = window.i18n
            ? window.i18n.t('admin.keybindings.reset_all_confirm_message')
            : 'Are you sure you want to reset all keyboard shortcuts to their default settings?';

        if (typeof ModalHelper !== 'undefined') {
            new ModalHelper({
                type: 'warning',
                title: title,
                message: message,
                confirmText: window.i18n.t('common.yes'),
                cancelText: window.i18n.t('common.no'),
                onConfirm: () => this.resetAll()
            }).show();
        } else if (confirm(message)) {
            this.resetAll();
        }
    }

    async resetAll() {
        try {
            const res = await app.apiCall('/api/admin/keybindings/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });

            this._savedBindings = JSON.parse(JSON.stringify(res.bindings || {}));
            this._pendingBindings = JSON.parse(JSON.stringify(this._savedBindings));

            if (window.keybindings) {
                window.keybindings.bindings = { ...this._savedBindings };
            }

            this._showStatus(window.i18n.t('admin.keybindings.saved'), 'success');
            this._render();

        } catch (e) {
            this._showStatus(e.message, 'danger');
        }
    }

    _showStatus(message, type = 'success') {
        const el = document.getElementById('keybindings-status');
        if (!el) return;
        el.className = `text-xs mt-3 text-${type}`;
        el.textContent = message;
        el.style.display = 'block';
        clearTimeout(this._statusTimer);
        this._statusTimer = setTimeout(() => {
            el.style.display = 'none';
        }, 3500);
    }
}
