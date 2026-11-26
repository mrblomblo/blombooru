// AdminContent near-duplicate settings and backfill
Object.assign(AdminContent.prototype, {
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
