// AdminSystem backend connections (Redis, shared tags, booru proxy) and settings
Object.assign(AdminSystem.prototype, {
    async testRedisConnection() {
        const btn = document.getElementById('test-redis-btn');
        const resultDiv = document.getElementById('redis-test-result');
        const originalText = btn.textContent;

        const data = {
            host: document.getElementById('redis-host').value,
            port: parseInt(document.getElementById('redis-port').value),
            db: parseInt(document.getElementById('redis-db').value),
            password: document.getElementById('redis-password').value
        };

        btn.disabled = true;
        btn.textContent = window.i18n.t('admin.actions.testing');
        resultDiv.style.display = 'none';

        try {
            const result = await app.apiCall('/api/admin/test-redis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            resultDiv.style.display = 'block';
            if (result.success) {
                resultDiv.className = 'mt-2 text-xs text-success';
                const message = result.message_key ? window.i18n.t(result.message_key) : result.message;
                resultDiv.textContent = message;
            } else {
                resultDiv.className = 'mt-2 text-xs text-danger';
                const message = result.message_key ? window.i18n.t(result.message_key, { error: result.error }) : result.message;
                resultDiv.textContent = message;
            }
        } catch (error) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'mt-2 text-xs text-danger';
            resultDiv.textContent = 'Error: ' + error.message;
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    },

    async testSharedTagsConnection() {
        const btn = document.getElementById('test-shared-tags-btn');
        const resultDiv = document.getElementById('shared-tags-test-result');
        const originalText = btn.textContent;

        const data = {
            host: document.getElementById('shared-tags-host').value,
            port: parseInt(document.getElementById('shared-tags-port').value || '5432'),
            name: document.getElementById('shared-tags-name').value,
            user: document.getElementById('shared-tags-user').value,
            password: document.getElementById('shared-tags-password').value
        };

        btn.disabled = true;
        btn.textContent = window.i18n.t('admin.actions.testing');
        resultDiv.style.display = 'none';

        try {
            const result = await app.apiCall('/api/admin/test-shared-tag-db', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            resultDiv.style.display = 'block';
            if (result.success) {
                resultDiv.className = 'mt-2 text-xs text-success';
                resultDiv.textContent = result.message || window.i18n.t('common.connection_successful');
            } else {
                resultDiv.className = 'mt-2 text-xs text-danger';
                resultDiv.textContent = result.message || window.i18n.t('common.connection_failed');
            }
        } catch (error) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'mt-2 text-xs text-danger';
            resultDiv.textContent = 'Error: ' + error.message;
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    },

    async testBooruProxy() {
        const proxyInput = document.getElementById('booru-proxy-url');
        const proxyUrl = proxyInput ? proxyInput.value.trim() : '';
        if (!proxyUrl) {
            app.showNotification(window.i18n.t('admin.settings.booru_config.error_proxy_empty'), 'error');
            return;
        }

        const btn = document.getElementById('test-booru-proxy-btn');
        const originalText = btn ? btn.textContent : '';
        if (btn) {
            btn.disabled = true;
            btn.textContent = window.i18n.t('admin.actions.testing');
        }

        try {
            const result = await app.apiCall('/api/booru-config/test-proxy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ proxy_url: proxyUrl })
            });

            if (result.success) {
                const msg = window.i18n.t('admin.settings.booru_config.proxy_test_success', { ip: result.origin_ip || 'unknown' });
                app.showNotification(msg, 'success');
            } else {
                const err = result.error || window.i18n.t('common.connection_failed');
                const msg = window.i18n.t('admin.settings.booru_config.proxy_test_failed', { error: err });
                app.showNotification(msg, 'error');
            }
        } catch (error) {
            const msg = window.i18n.t('admin.settings.booru_config.proxy_test_failed', { error: error.message });
            app.showNotification(msg, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    },

    async syncSharedTags() {
        const btn = document.getElementById('sync-shared-tags-btn');
        const resultDiv = document.getElementById('shared-tags-test-result');
        const originalText = btn.textContent;

        btn.disabled = true;
        btn.textContent = window.i18n.t('admin.shared_tags.syncing');
        resultDiv.style.display = 'none';

        try {
            const result = await app.apiCall('/api/admin/shared-tags/sync', {
                method: 'POST'
            });

            resultDiv.style.display = 'block';
            if (result.success) {
                resultDiv.className = 'mt-2 text-xs text-success';
                resultDiv.innerHTML = `
                    ${window.i18n.t('admin.shared_tags.sync_complete')}<br>
                    ${window.i18n.t('admin.shared_tags.imported_count', { tags: result.tags_imported, aliases: result.aliases_imported })}<br>
                    ${window.i18n.t('admin.shared_tags.exported_count', { tags: result.tags_exported, aliases: result.aliases_exported })}
                `;
            } else {
                resultDiv.className = 'mt-2 text-xs text-danger';
                resultDiv.textContent = result.errors?.join(', ') || window.i18n.t('admin.shared_tags.sync_failed');
            }

            // Refresh status
            this.loadSharedTagsStatus();
        } catch (error) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'mt-2 text-xs text-danger';
            resultDiv.textContent = window.i18n.t('common.error', { error: error.message });
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    },

    async loadSharedTagsStatus() {
        try {
            const result = await app.apiCall('/api/admin/shared-tags/status');
            const statusDiv = document.getElementById('shared-tags-status');
            const connectionStatus = document.getElementById('shared-tags-connection-status');
            const counts = document.getElementById('shared-tags-counts');

            if (statusDiv && result.enabled) {
                statusDiv.style.display = 'block';
                if (result.connected) {
                    connectionStatus.innerHTML = `<span class="text-success">● ${window.i18n.t('common.connected')}</span>`;
                    counts.textContent = `${window.i18n.t('admin.shared_tags.shared_count')}: ${result.shared_tags || 0} tags, ${result.shared_aliases || 0} aliases`;
                } else {
                    connectionStatus.innerHTML = `<span class="text-danger">● ${window.i18n.t('common.disconnected')}</span>`;
                    counts.textContent = result.error || '';
                }
            }
        } catch (error) {
            console.error('Error loading shared tags status:', error);
        }
    },

    async saveBackendSettings() {
        const redisSettings = {
            enabled: document.getElementById('redis-enabled')?.checked || false,
            host: document.getElementById('redis-host')?.value || 'redis',
            port: parseInt(document.getElementById('redis-port')?.value || '6379'),
            db: parseInt(document.getElementById('redis-db')?.value || '0'),
            password: document.getElementById('redis-password')?.value || ''
        };

        const sharedTagsSettings = {
            enabled: document.getElementById('shared-tags-enabled')?.checked || false,
            host: document.getElementById('shared-tags-host')?.value || 'shared-tag-db',
            port: parseInt(document.getElementById('shared-tags-port')?.value || '5432'),
            name: document.getElementById('shared-tags-name')?.value || 'shared_tags',
            user: document.getElementById('shared-tags-user')?.value || 'postgres',
            password: document.getElementById('shared-tags-password')?.value || ''
        };

        const simCats = ['artist', 'character', 'general', 'copyright', 'meta'];
        const similarityWeights = {};
        simCats.forEach(cat => {
            const el = document.getElementById(`sim-weight-${cat}`);
            if (el) {
                let val = parseFloat(el.value);
                if (isNaN(val) || val < 0) {
                    val = parseFloat(el.dataset.simDefault) || 0;
                }
                similarityWeights[cat] = Math.min(99.99, Math.max(0, Math.round(val * 100) / 100));
            }
        });

        const proxyInput = document.getElementById('booru-proxy-url');
        const booruProxyUrl = proxyInput ? proxyInput.value.trim() : null;

        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify({
                    redis: redisSettings,
                    shared_tags: sharedTagsSettings,
                    similarity_weights: similarityWeights,
                    booru_proxy_url: booruProxyUrl || null
                })
            });

            const syncBtn = document.getElementById('sync-shared-tags-btn');
            if (syncBtn) syncBtn.style.display = sharedTagsSettings.enabled ? 'inline-block' : 'none';

            app.showNotification(window.i18n.t('notifications.admin.backend_saved') || window.i18n.t('notifications.admin.settings_updated'), 'success');
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_saving_settings'));
        }
    },
});
