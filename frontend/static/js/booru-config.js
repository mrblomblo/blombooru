class BooruConfigManager {
    constructor() {
        this.container = document.getElementById('booru-config-section');
        if (this.container) {
            this.init();
        }
    }

    init() {
        this.tableBody = this.container.querySelector('#booru-config-table tbody');
        this.form = this.container.querySelector('#booru-config-form');

        if (this.form) {
            this.form.addEventListener('submit', (e) => this.handleSubmit(e));
        }

        this.loadConfigs();
    }

    showStatus(message, type = 'info') {
        if (typeof app !== 'undefined' && app.showNotification) {
            app.showNotification(message, type);
        } else {
            console.warn('App notification helper not available:', message);
            alert(message);
        }
    }

    async loadConfigs() {
        if (!this.tableBody) return;

        try {
            const response = await fetch('/api/booru-config/');
            if (!response.ok) throw new Error('Failed to load configs');
            const configs = await response.json();
            this.renderTable(configs);
        } catch (e) {
            console.error('Error loading booru configs:', e);
            this.tableBody.innerHTML = `<tr><td colspan="4" class="text-center py-2 text-danger">${window.i18n.t('admin.settings.booru_config.no_configs')}</td></tr>`;
        }
    }

    renderTable(configs) {
        if (configs.length === 0) {
            this.tableBody.innerHTML = `<tr><td colspan="4" class="text-center py-2 text-secondary text-xs">${window.i18n.t('admin.settings.booru_config.no_configs')}</td></tr>`;
            return;
        }

        this.tableBody.innerHTML = configs.map(config => `
            <tr class="border-b last:border-b-0 hover:surface transition-colors">
                <td class="py-2 px-3 text-xs font-mono">${this.escapeHtml(config.domain)}</td>
                <td class="py-2 px-3 text-xs">${this.escapeHtml(config.username || '-')}</td>
                <td class="py-2 px-3 text-xs">
                    ${config.has_api_key ? `<span class="text-success">${window.i18n.t('admin.settings.booru_config.has_key')}</span>` : `<span class="text-secondary">${window.i18n.t('admin.settings.booru_config.none')}</span>`}
                </td>
                <td class="py-2 px-3 text-xs text-right">
                    <button class="text-danger hover:text-danger" onclick="window.booruConfigManager.deleteConfig('${config.domain}')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    async handleSubmit(e) {
        e.preventDefault();
        const domainInput = this.form.querySelector('[name="domain"]');
        const usernameInput = this.form.querySelector('[name="username"]');
        const apiKeyInput = this.form.querySelector('[name="api_key"]');

        const data = {
            domain: domainInput.value.trim(),
            username: usernameInput.value.trim() || null,
            api_key: apiKeyInput.value.trim() || null
        };

        if (!data.domain) {
            this.showStatus(window.i18n.t('admin.settings.booru_config.error_domain_required'), 'error');
            return;
        }

        try {
            const response = await fetch('/api/booru-config/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message_key || error.detail || 'Failed to save configuration');
            }

            this.showStatus(window.i18n.t('admin.settings.booru_config.save_success'), 'success');

            domainInput.value = '';
            usernameInput.value = '';
            apiKeyInput.value = '';

            this.loadConfigs();
        } catch (e) {
            console.error('Save error:', e);
            const errorMsg = app.translateError(e.message) || window.i18n.t('admin.settings.booru_config.error_save_failed');
            this.showStatus(errorMsg, 'error');
        }
    }

    deleteConfig(domain) {
        new ModalHelper({
            type: 'danger',
            title: window.i18n.t('admin.settings.booru_config.delete_confirm_title') || 'Delete Configuration',
            message: window.i18n.t('admin.settings.booru_config.delete_confirm', { domain }),
            confirmText: window.i18n.t('common.delete'),
            confirmId: 'confirm-delete-config',
            onConfirm: async () => {
                try {
                    const response = await fetch(`/api/booru-config/${encodeURIComponent(domain)}`, {
                        method: 'DELETE'
                    });

                    if (!response.ok) {
                        const error = await response.json();
                        throw new Error(error.message_key || error.detail || 'Failed to delete');
                    }

                    const successMsg = window.i18n.t('admin.settings.booru_config.delete_success', { domain });
                    this.showStatus(successMsg, 'success');
                    this.loadConfigs();
                } catch (e) {
                    const errorMsg = app.translateError(e.message) || window.i18n.t('admin.settings.booru_config.error_delete_failed');
                    this.showStatus(errorMsg, 'error');
                }
            }
        }).show();
    }

    escapeHtml(text) {
        if (!text) return text;
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

if (document.getElementById('booru-config-section')) {
    window.booruConfigManager = new BooruConfigManager();
}
