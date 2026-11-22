// AdminSystem API key management
Object.assign(AdminSystem.prototype, {
    getApiKeyPermissionIcon(permission, size = 16) {
        if (permission === 'write') {
            const title = window.i18n.t('admin.api_access.level_write');
            return `<span title="${escapeHtml(title)}" class="inline-flex items-center">
                ${window.Icons.upload({ size: size, class: 'text-warning shrink-0' })}
            </span>`;
        }
        if (permission === 'admin') {
            const title = window.i18n.t('admin.api_access.level_admin');
            return `<span title="${escapeHtml(title)}" class="inline-flex items-center">
                ${window.Icons.shield({ size: size, class: 'text-danger shrink-0' })}
            </span>`;
        }
        const title = window.i18n.t('admin.api_access.level_read');
        return `<span title="${escapeHtml(title)}" class="inline-flex items-center">
            ${window.Icons.eye({ size: size, class: 'text-success shrink-0' })}
        </span>`;
    },

    showApiKeyNameModal() {
        const inputId = 'api-key-name-input';
        let selectedPermission = 'read';

        const modal = new ModalHelper({
            id: 'api-key-name-modal',
            confirmId: 'api-key-name-confirm-btn',
            cancelId: 'api-key-name-cancel-btn',
            title: window.i18n.t('modal.api_key_name.title'),
            message: `
                <div class="text-left">
                    <label class="block text-xs font-bold mb-1 text-secondary">${window.i18n.t('modal.api_key_name.title')}</label>
                    <input type="text" id="${inputId}" 
                        class="w-full bg px-3 py-2 mb-4 border text-xs hover:border-primary transition-colors focus:outline-none focus:border-primary"
                        placeholder="${window.i18n.t('modal.api_key_name.placeholder')}"
                        maxlength="64"
                        autocomplete="off">

                    <label class="block text-xs font-bold mb-2 text-secondary">${window.i18n.t('modal.manage_api_key.title')}</label>
                    <div class="flex flex-col gap-2.5 mb-2" id="new-api-key-levels">
                        <!-- Read-Only -->
                        <button type="button" class="new-akm-level text-left p-3.5 bg hover:border-primary transition-all border flex items-start gap-3 cursor-pointer border-primary surface" data-level="read">
                            <div class="mt-0.5 text-success shrink-0">
                                ${window.Icons.eye({ size: 18 })}
                            </div>
                            <div class="flex-1">
                                <div class="font-bold text-xs text mb-0.5">${window.i18n.t('modal.manage_api_key.level_read_title')}</div>
                                <div class="text-[11px] text-secondary opacity-80 leading-relaxed">${window.i18n.t('modal.manage_api_key.level_read_desc')}</div>
                            </div>
                        </button>

                        <!-- Upload & Edit -->
                        <button type="button" class="new-akm-level text-left p-3.5 bg hover:border-primary transition-all border flex items-start gap-3 cursor-pointer" data-level="write">
                            <div class="mt-0.5 text-warning shrink-0">
                                ${window.Icons.upload({ size: 18 })}
                            </div>
                            <div class="flex-1">
                                <div class="font-bold text-xs text mb-0.5">${window.i18n.t('modal.manage_api_key.level_write_title')}</div>
                                <div class="text-[11px] text-secondary opacity-80 leading-relaxed">${window.i18n.t('modal.manage_api_key.level_write_desc')}</div>
                            </div>
                        </button>

                        <!-- Full Admin -->
                        <button type="button" class="new-akm-level text-left p-3.5 bg hover:border-primary transition-all border flex items-start gap-3 cursor-pointer" data-level="admin">
                            <div class="mt-0.5 text-danger shrink-0">
                                ${window.Icons.shield({ size: 18 })}
                            </div>
                            <div class="flex-1">
                                <div class="font-bold text-xs text mb-0.5">${window.i18n.t('modal.manage_api_key.level_admin_title')}</div>
                                <div class="text-[11px] text-secondary opacity-80 leading-relaxed">${window.i18n.t('modal.manage_api_key.level_admin_desc')}</div>
                            </div>
                        </button>
                    </div>
                </div>
            `,
            confirmText: window.i18n.t('modal.api_key_name.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            onConfirm: () => {
                const nameInput = document.getElementById(inputId);
                const name = nameInput ? nameInput.value.trim() : '';
                this.generateApiKey(name, selectedPermission);
                modal.destroy();
            },
            onCancel: () => {
                modal.destroy();
            }
        });

        modal.show();

        // Level selector bindings
        const levelsContainer = document.getElementById('new-api-key-levels');
        if (levelsContainer) {
            levelsContainer.querySelectorAll('.new-akm-level').forEach(card => {
                card.addEventListener('click', () => {
                    selectedPermission = card.dataset.level || 'read';
                    levelsContainer.querySelectorAll('.new-akm-level').forEach(c => {
                        if (c === card) {
                            c.classList.add('border-primary', 'surface');
                        } else {
                            c.classList.remove('border-primary', 'surface');
                        }
                    });
                });
            });
        }

        // Focus and clear input
        const input = document.getElementById(inputId);
        if (input) {
            input.value = '';
            input.focus();
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    modal.confirm();
                }
            });
        }
    },

    setupApiKeyManagement() {
        this.apiKeys = [];
        this.apiKeyManageModal = null;
        this.loadApiKeys();

        document.getElementById('generate-api-key-btn')?.addEventListener('click', () => {
            this.showApiKeyNameModal();
        });

        document.getElementById('copy-api-key-btn')?.addEventListener('click', () => {
            const input = document.getElementById('new-api-key-value');
            input.select();
            document.execCommand('copy');
            app.showNotification(window.i18n.t('notifications.admin.api_key_copied'), 'success');
        });
    },

    async loadApiKeys() {
        try {
            const response = await fetch('/api/admin/api-keys');
            if (response.ok) {
                const keys = await response.json();
                this.apiKeys = keys;
                this.renderApiKeys(keys);
            }
        } catch (e) { console.error(e); }
    },

    renderApiKeys(keys) {
        const listContainer = document.getElementById('api-keys-list');
        if (!listContainer) return;

        if (keys.length === 0) {
            listContainer.innerHTML = `<div class="bg p-6 text-center text-xs text-secondary opacity-70">${window.i18n.t('notifications.admin.no_active_api_keys')}</div>`;
            return;
        }

        listContainer.innerHTML = keys.map(key => {
            const level = key.permission || 'read';
            const iconSvg = this.getApiKeyPermissionIcon(level, 16);

            return `
            <div class="bg p-2 border-b last:border-b-0 flex justify-between items-center">
                <div class="flex-1 min-w-0 pr-2">
                    <div class="flex items-center gap-1 mb-1.5">
                        ${iconSvg}
                        <span class="font-bold text-xs truncate text">${escapeHtml(key.name || 'Unnamed Key')}</span>
                    </div>
                    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-secondary">
                        <span class="font-mono bg surface px-1 border">${escapeHtml(key.key_prefix)}...</span>
                        <div>
                            <span> ${window.i18n.t('admin.api_access.created_at')} <strong>${new Date(key.created_at).toLocaleDateString()}</strong></span>
                            <span> ${window.i18n.t('admin.api_access.last_used')} <strong>${key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : window.i18n.t('common.never')}</strong></span>
                        </div>
                    </div>
                </div>
                <div class="flex-shrink-0">
                    <button class="btn px-3 py-1 text-[10px] uppercase font-bold tracking-wider cursor-pointer" 
                        onclick="window.adminPanel.system.manageApiKey(${key.id})">
                        ${window.i18n.t('common.manage')}
                    </button>
                </div>
            </div>
            `;
        }).join('');
    },

    manageApiKey(keyId) {
        const key = (this.apiKeys || []).find(k => k.id === keyId);
        if (!key) return;

        if (!this.apiKeyManageModal && typeof ApiKeyManageModal !== 'undefined') {
            this.apiKeyManageModal = new ApiKeyManageModal({
                onUpdate: (updatedKey) => {
                    const idx = (this.apiKeys || []).findIndex(k => k.id === updatedKey.id);
                    if (idx !== -1) {
                        this.apiKeys[idx] = { ...this.apiKeys[idx], ...updatedKey };
                        this.renderApiKeys(this.apiKeys);
                    }
                },
                onRevoke: (id) => {
                    this.revokeApiKey(id, true);
                }
            });
        }

        if (this.apiKeyManageModal) {
            this.apiKeyManageModal.show(key);
        }
    },

    async generateApiKey(name, permission = 'read') {
        try {
            const response = await app.apiCall('/api/admin/api-keys', {
                method: 'POST',
                body: JSON.stringify({ name: name, permission: permission })
            });

            // Show result
            const display = document.getElementById('new-api-key-display');
            if (display) display.style.display = 'block';

            const input = document.getElementById('new-api-key-value');
            if (input) input.value = response.key;

            // Reload list
            this.loadApiKeys();

            app.showNotification(window.i18n.t('notifications.admin.api_key_generated'), 'success');
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_generating_api_key'));
        }
    },

    async revokeApiKey(keyId, fromManageModal = false) {
        const modal = new ModalHelper({
            id: 'revoke-api-key-modal',
            type: 'danger',
            confirmId: 'revoke-api-key-confirm-yes',
            cancelId: 'revoke-api-key-confirm-no',
            title: window.i18n.t('modal.revoke_api_key.title'),
            message: window.i18n.t('modal.revoke_api_key.message'),
            confirmText: window.i18n.t('modal.revoke_api_key.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/admin/api-keys/${keyId}`, {
                        method: 'DELETE'
                    });

                    this.loadApiKeys();
                    app.showNotification(window.i18n.t('notifications.admin.api_key_revoked'), 'success');
                } catch (error) {
                    app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_revoking_api_key'));
                } finally {
                    modal.destroy();
                }
            },
            onCancel: () => {
                modal.destroy();
                if (fromManageModal && this.apiKeyManageModal) {
                    const key = (this.apiKeys || []).find(k => k.id === keyId);
                    if (key) {
                        this.apiKeyManageModal.show(key);
                    }
                }
            }
        });

        modal.show();
    },
});
