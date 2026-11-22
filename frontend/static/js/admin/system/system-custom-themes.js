// AdminSystem custom theme CRUD and import/export
Object.assign(AdminSystem.prototype, {
    async loadCustomThemes() {
        try {
            const builtinData = await app.apiCall('/api/admin/builtin-themes').catch(e => {
                console.error('Failed to load builtin themes:', e);
                return { themes: [] };
            });
            this._builtinThemes = builtinData.themes || [];
            this._refreshBackupThemeDropdown(
                document.getElementById('custom-theme-backup'),
                'default_dark'
            );

            const customData = await app.apiCall('/api/admin/custom-themes').catch(e => {
                console.error('Failed to load custom themes:', e);
                return { themes: [] };
            });
            this._refreshCustomThemesTable(customData.themes || []);
        } catch (e) {
            console.error('Could not load custom themes:', e);
        }
    },

    _refreshBackupThemeDropdown(selectEl, selectedId) {
        if (!selectEl) return;
        const dropdown = selectEl.querySelector('.custom-select-dropdown');
        if (!dropdown) return;

        const themes = this._builtinThemes || [];
        dropdown.innerHTML = themes.map(t =>
            `<div class="custom-select-option px-3 py-2 cursor-pointer hover:surface text-xs" data-value="${escapeHtml(t.id)}">${escapeHtml(t.name)}</div>`
        ).join('');

        // Preserve existing selection if no explicit selectedId passed, otherwise use the provided one
        const effectiveId = selectedId ?? (this.customThemeBackupSelect?.getValue() || 'default_dark');
        selectEl.dataset.value = effectiveId;

        if (this.customThemeBackupSelect && this.customThemeBackupSelect.element === selectEl) {
            this.customThemeBackupSelect.selectedValue = effectiveId;
            this.customThemeBackupSelect.initializeExistingOptions();
        }
    },

    _refreshCustomThemesTable(themes) {
        const tbody = document.getElementById('custom-themes-tbody');
        if (!tbody) return;

        if (!themes.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="3" class="py-4 px-3 text-xs text-secondary text-center">
                        ${window.i18n.t('admin.settings.custom_themes.no_custom_themes')}
                    </td>
                </tr>`;
            return;
        }

        tbody.innerHTML = '';
        for (const theme of themes) {
            const typeBadge = theme.is_dark
                ? `<span class="text-[10px] px-1.5 py-0.5 surface border">${window.i18n.t('admin.settings.custom_themes.type_dark')}</span>`
                : `<span class="text-[10px] px-1.5 py-0.5 surface border">${window.i18n.t('admin.settings.custom_themes.type_light')}</span>`;
            const activeMark = theme.is_active
                ? ' <span class="text-[10px] text-primary">&#9679;</span>' : '';

            const tr = document.createElement('tr');
            tr.className = 'border-b last:border-b-0';
            tr.innerHTML = `
                <td class="p-2 text-xs break-all"></td>
                <td class="p-2 text-xs">${typeBadge}</td>
                <td class="p-2 text-xs text-right whitespace-nowrap">
                    <button type="button" class="text-success hover:text-success transition-colors mr-2 cursor-pointer"
                        data-action="export" data-theme-id="${escapeHtml(theme.id)}"
                        title="${window.i18n.t('admin.settings.custom_themes.export')}">
                        ${window.Icons.download({ size: 14 })}
                    </button>
                    <button type="button" class="text-primary hover:text-primary transition-colors mr-2 cursor-pointer"
                        data-action="edit" data-theme-id="${escapeHtml(theme.id)}"
                        title="${window.i18n.t('admin.settings.custom_themes.edit')}">
                        ${window.Icons.edit({ size: 14 })}
                    </button>
                    <button type="button" class="text-danger hover:text-danger transition-colors cursor-pointer"
                        data-action="delete" data-theme-id="${escapeHtml(theme.id)}"
                        title="${window.i18n.t('common.delete')}">
                        ${window.Icons.trash({ size: 14 })}
                    </button>
                </td>`;

            // Set the name cell via textContent to avoid XSS
            tr.querySelector('td:first-child').textContent = theme.name;
            if (activeMark) {
                tr.querySelector('td:first-child').insertAdjacentHTML('beforeend', activeMark);
            }

            // Attach theme name to buttons via dataset (not eval'd as JS so should be safe)
            for (const btn of tr.querySelectorAll('button[data-action]')) {
                btn.dataset.themeName = theme.name;
            }

            tbody.appendChild(tr);
        }
    },

    async addCustomTheme() {
        const name = document.getElementById('custom-theme-name')?.value.trim();
        const css = document.getElementById('custom-theme-css')?.value.trim();
        const isDark = this.customThemeIsDarkSelect
            ? this.customThemeIsDarkSelect.getValue() === 'true'
            : true;
        const backupThemeId = this.customThemeBackupSelect
            ? this.customThemeBackupSelect.getValue()
            : 'default_dark';

        if (!name) {
            app.showNotification(window.i18n.t('admin.settings.custom_themes.errors.name_required'), 'error');
            return;
        }
        if (!css) {
            app.showNotification(window.i18n.t('admin.settings.custom_themes.css_required'), 'error');
            return;
        }

        const addBtn = document.getElementById('custom-theme-add-btn');
        if (addBtn) { addBtn.disabled = true; }

        try {
            if (this._editingThemeId) {
                // Update existing theme
                await app.apiCall(`/api/admin/custom-themes/${this._editingThemeId}`, {
                    method: 'PUT',
                    body: JSON.stringify({ name, is_dark: isDark, backup_theme_id: backupThemeId, css }),
                });
                app.showNotification(
                    window.i18n.t('admin.settings.custom_themes.theme_updated', { name }),
                    'success'
                );
            } else {
                // Create new theme
                await app.apiCall('/api/admin/custom-themes', {
                    method: 'POST',
                    body: JSON.stringify({ name, is_dark: isDark, css, backup_theme_id: backupThemeId }),
                });
                app.showNotification(
                    window.i18n.t('admin.settings.custom_themes.theme_added', { name }),
                    'success'
                );
            }
            this._resetThemeForm();
            await this.loadCustomThemes();
            await this.loadThemes();
        } catch (e) {
            const detail = e.message || '';
            app.showNotification(
                detail
                    ? window.i18n.t('admin.settings.custom_themes.invalid_css', { error: detail })
                    : window.i18n.t('admin.settings.custom_themes.invalid_css', { error: 'Unknown error' }),
                'error'
            );
        } finally {
            if (addBtn) { addBtn.disabled = false; }
        }
    },

    async importCustomTheme(file, mode) {
        const isBundle = mode === 'bundle';

        if (!isBundle) {
            // CSS import: populate the form so the user can set name, is_dark,
            // backup theme, etc., before proceeding.
            const css = await file.text();
            const suggestedName = file.name.replace(/\.css$/i, '').replace(/[_-]+/g, ' ').trim();

            document.getElementById('custom-theme-name').value = suggestedName;
            document.getElementById('custom-theme-css').value = css;

            document.getElementById('custom-theme-name')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            return;
        }

        // Bundle import: metadata is embedded in theme.json, import immediately.
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/admin/custom-themes/import', {
                method: 'POST',
                body: formData,
                credentials: 'include',
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Import failed' }));
                throw new Error(err.detail || 'Import failed');
            }
            const result = await response.json();
            const importedName = result.theme?.name || 'Unknown Theme';
            app.showNotification(
                window.i18n.t('admin.settings.custom_themes.theme_added', { name: importedName }),
                'success'
            );
            await this.loadCustomThemes();
            await this.loadThemes();
        } catch (e) {
            app.showNotification(e.message || 'Import failed', 'error');
        }
    },

    _resetThemeForm() {
        this._editingThemeId = null;

        document.getElementById('custom-theme-name').value = '';
        const defaultTemplate = `:root {
  --primary-color: 
  --primary-hover: color-mix(in srgb, var(--primary-color) 70%, var(--background));
  --background: 
  --surface: 
  --surface-hover: color-mix(in srgb, var(--surface) 85%, white);
  --surface-light: 
  --surface-light-hover: color-mix(in srgb, var(--surface-light) 85%, white);
  --text: 
  --text-secondary: 
  --text-tertiary: 
  --tag-text: 
  --primary-text: 
  --border: 

  --white: 
  --black: 
  --green: 
  --orange: 
  --red: 
  --blue: 

  --tag-artist: 
  --tag-character: 
  --tag-copyright: 
  --tag-general: 
  --tag-meta: 
}`;
        document.getElementById('custom-theme-css').value = defaultTemplate;

        if (this.customThemeIsDarkSelect) {
            const el = document.getElementById('custom-theme-is-dark');
            if (el) {
                el.dataset.value = 'true';
                this.customThemeIsDarkSelect.selectedValue = 'true';
                this.customThemeIsDarkSelect.initializeExistingOptions();
            }
        }

        const backupEl = document.getElementById('custom-theme-backup');
        if (backupEl) {
            this._refreshBackupThemeDropdown(backupEl, 'default_dark');
        }

        const addBtn = document.getElementById('custom-theme-add-btn');
        if (addBtn) addBtn.textContent = window.i18n.t('admin.settings.custom_themes.add_theme');

        const importBundleBtn = document.getElementById('custom-theme-import-bundle-btn');
        if (importBundleBtn) importBundleBtn.style.display = '';

        const importCssBtn = document.getElementById('custom-theme-import-css-btn');
        if (importCssBtn) importCssBtn.style.display = '';

        const cancelBtn = document.getElementById('custom-theme-cancel-btn');
        if (cancelBtn) cancelBtn.style.display = 'none';
    },

    async editCustomTheme(themeId) {
        let theme = null;
        try {
            const data = await app.apiCall('/api/admin/custom-themes');
            theme = (data.themes || []).find(t => t.id === themeId);
            if (!theme) return;
        } catch (e) {
            console.error('Could not fetch theme data for edit:', e);
            return;
        }

        let css = '';
        try {
            const cssResp = await fetch(`/data/themes/${themeId}.css?_=${Date.now()}`);
            if (cssResp.ok) css = await cssResp.text();
        } catch (e) {
            console.error('Could not fetch CSS for edit:', e);
        }

        this._editingThemeId = themeId;

        document.getElementById('custom-theme-name').value = theme.name;
        document.getElementById('custom-theme-css').value = css;

        const isDarkVal = theme.is_dark ? 'true' : 'false';
        const isDarkEl = document.getElementById('custom-theme-is-dark');
        if (isDarkEl) {
            isDarkEl.dataset.value = isDarkVal;
            if (this.customThemeIsDarkSelect) {
                this.customThemeIsDarkSelect.selectedValue = isDarkVal;
                this.customThemeIsDarkSelect.initializeExistingOptions();
            }
        }

        const backupEl = document.getElementById('custom-theme-backup');
        if (backupEl) {
            this._refreshBackupThemeDropdown(backupEl, theme.backup_theme_id || 'default_dark');
        }

        const addBtn = document.getElementById('custom-theme-add-btn');
        if (addBtn) addBtn.textContent = window.i18n.t('admin.settings.custom_themes.save_theme');

        const importBundleBtn = document.getElementById('custom-theme-import-bundle-btn');
        if (importBundleBtn) importBundleBtn.style.display = 'none';

        const importCssBtn = document.getElementById('custom-theme-import-css-btn');
        if (importCssBtn) importCssBtn.style.display = 'none';

        const cancelBtn = document.getElementById('custom-theme-cancel-btn');
        if (cancelBtn) cancelBtn.style.display = '';

        document.getElementById('custom-theme-name')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },

    async deleteCustomTheme(themeId, themeName) {
        const modal = new ModalHelper({
            id: 'delete-custom-theme-modal',
            type: 'danger',
            title: window.i18n.t('common.delete'),
            message: window.i18n.t('admin.settings.custom_themes.confirm_delete', { name: themeName }),
            confirmText: window.i18n.t('common.delete'),
            cancelText: window.i18n.t('common.cancel'),
            confirmId: 'delete-custom-theme-confirm',
            cancelId: 'delete-custom-theme-cancel',
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/admin/custom-themes/${themeId}`, { method: 'DELETE' });
                    app.showNotification(
                        window.i18n.t('admin.settings.custom_themes.theme_deleted', { name: themeName }),
                        'success'
                    );
                    // Reset form if theme was being edited
                    if (this._editingThemeId === themeId) this._resetThemeForm();
                    await this.loadCustomThemes();
                    await this.loadThemes();
                } catch (e) {
                    const msg = e.message || '';
                    if (msg.includes('active')) {
                        app.showNotification(window.i18n.t('admin.settings.custom_themes.errors.cannot_delete_active'), 'error');
                    } else {
                        app.showNotification(msg || 'Delete failed', 'error');
                    }
                }
            },
        });
        modal.show();
    },

    async exportCustomTheme(themeId, themeName) {
        try {
            const response = await fetch(`/api/admin/custom-themes/${themeId}/export`, {
                credentials: 'include',
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: 'Export failed' }));
                throw new Error(err.detail || 'Export failed');
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            const safeName = themeName.replace(/[^\w\-]/g, '_');
            a.href = url;
            a.download = `${safeName}.blombooru-theme`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            app.showNotification(e.message || 'Export failed', 'error');
        }
    },
});
