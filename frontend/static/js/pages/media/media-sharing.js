// MediaViewer public sharing and share settings controls
Object.assign(MediaViewer.prototype, {
    // ==================== Share Methods ====================

    async shareMedia() {
        try {
            const res = await app.apiCall(`/api/media/${this.mediaId}/share`, { method: 'POST' });
            this.showShareLink(res.share_url.split('/').pop(), res.share_ai_metadata);
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('media.errors.creating_share_link'));
        }
    },

    copyShareLink() {
        this.el('share-link-input').select();
        document.execCommand('copy');
        app.showNotification(window.i18n.t('notifications.media.link_copied'), 'success');
    },

    async unshareMedia() {
        const modal = new ModalHelper({
            id: 'unshare-modal',
            type: 'warning',
            title: window.i18n.t('modal.unshare_media.title'),
            message: window.i18n.t('modal.unshare_media.message'),
            confirmText: window.i18n.t('modal.unshare_media.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            confirmId: 'unshare-confirm-yes',
            cancelId: 'unshare-confirm-no',
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/media/${this.mediaId}/share`, { method: 'DELETE' });
                    this.el('share-link-section').style.display = 'none';

                    // Reset share button
                    const btn = this.el('share-btn');
                    const btnText = this.el('share-btn-text');
                    if (btn) {
                        btn.style.removeProperty('display');
                        btn.classList.remove('unshare-mode', 'border-danger', 'text-danger', 'hover:bg-danger', 'hover:tag-text');
                        btn.classList.add('surface-light', 'hover:surface-light');
                        btnText.innerHTML = window.i18n.t('common.share');
                    }

                    app.showNotification(window.i18n.t('notifications.media.media_unshared'), 'success');
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('media.errors.removing_share'));
                }
            }
        });
        modal.show();
    },

    async updateShareSettings(updates) {
        try {
            await app.apiCall(`/api/media/${this.mediaId}/share-settings`, {
                method: 'PATCH',
                body: JSON.stringify(updates)
            });
        } catch (err) {
            app.showNotification(err.message, 'error', window.i18n.t('media.errors.updating_share_settings'));
            const toggle = this.el('share-ai-metadata-toggle');
            const languageSelect = this.el('share-language-select');
            if (toggle) toggle.checked = !toggle.checked;
            if (languageSelect) languageSelect.value = 'default';
        }
    },

    showShareLink(uuid, shareAIMetadata) {
        const baseUrl = this.externalShareUrl || window.location.origin;
        // Remove trailing slash if present to avoid double slashes
        const cleanBaseUrl = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;

        this.el('share-link-input').value = `${cleanBaseUrl}/shared/${uuid}`;
        this.el('share-link-section').style.display = 'block';

        // Update share button to unshare mode
        const btn = this.el('share-btn');
        const btnText = this.el('share-btn-text');
        if (btn) {
            btn.style.removeProperty('display');
            btn.classList.add('unshare-mode', 'border-danger', 'text-danger', 'hover:bg-danger', 'hover:tag-text');
            btn.classList.remove('surface-light', 'hover:surface-light');
            btnText.innerHTML = window.i18n.t('common.unshare');
        }

        const aiMetadataToggle = this.el('share-ai-metadata-toggle');
        if (aiMetadataToggle) {
            aiMetadataToggle.checked = shareAIMetadata || false;
        }
    },
});
