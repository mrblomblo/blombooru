// AdminSystem updates, changelog, and full backup restore
Object.assign(AdminSystem.prototype, {
    setupSystemUpdate() {
        if (document.getElementById('btn-check-updates')) {
            document.getElementById('btn-check-updates').addEventListener('click', () => this.checkUpdateStatus());
        }
        document.getElementById('btn-update-now')?.addEventListener('click', () => this.performUpdate());
        document.getElementById('btn-view-changelog')?.addEventListener('click', () => this.showChangelog());

        this.updateData = null;
    },

    async checkUpdateStatus() {
        const initialState = document.getElementById('update-initial-state');
        const loading = document.getElementById('update-loading');
        const statusDiv = document.getElementById('update-status');

        if (!loading || !statusDiv) return;

        if (initialState) initialState.classList.add('hidden');
        loading.classList.remove('hidden');
        loading.style.display = 'block';
        statusDiv.style.display = 'none';

        try {
            const response = await fetch('/api/system/update/check');
            if (!response.ok) throw new Error('Failed to check for updates');

            const status = await response.json();
            this.updateData = status;

            loading.style.display = 'none';
            loading.classList.add('hidden');
            statusDiv.style.display = 'block';

            const currentEl = document.getElementById('current-version-display');
            if (currentEl) currentEl.textContent = status.current_version;

            const latestEl = document.getElementById('latest-version-display');
            if (latestEl) latestEl.textContent = status.latest_version;

            const noticesDiv = document.getElementById('update-notices');
            if (noticesDiv) {
                if (status.notices && status.notices.length > 0) {
                    noticesDiv.classList.remove('hidden');
                    noticesDiv.innerHTML = status.notices.map(n => {
                        const translated = window.i18n.t(n);
                        return `<div class="bg text-xs p-2 mb-1 border-l-4 border-warning text-warning font-bold">${escapeHtml(translated)}</div>`;
                    }).join('');
                } else {
                    noticesDiv.classList.add('hidden');
                }
            }

            // Update instructions for Docker users
            const instructionsDiv = document.getElementById('update-instructions');
            const commandText = document.getElementById('update-command-text');
            if (instructionsDiv && commandText && status.update_available) {
                if (status.deployment_type === 'ghcr') {
                    instructionsDiv.classList.remove('hidden');
                    commandText.textContent = 'docker compose up -d --pull always';
                } else if (status.deployment_type === 'docker_local') {
                    instructionsDiv.classList.remove('hidden');
                    commandText.textContent = 'docker compose down && docker compose -f docker-compose.dev.yml up --build';
                } else {
                    instructionsDiv.classList.add('hidden');
                }
            } else if (instructionsDiv) {
                instructionsDiv.classList.add('hidden');
            }

            // Config files notice
            const configNotice = document.getElementById('config-files-notice');
            const configMessage = document.getElementById('config-files-message');
            const configLinks = document.getElementById('config-files-links');
            if (configNotice && status.config_files_changed && status.update_available) {
                configNotice.classList.remove('hidden');
                const fileNames = (status.changed_config_files || []).join(', ');
                const msg = window.i18n.t('admin.update.config_files_changed', { files: fileNames });
                if (configMessage) configMessage.textContent = msg;
                if (configLinks) {
                    configLinks.innerHTML = Object.entries(status.asset_urls || {}).map(([name, url]) =>
                        `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" class="btn-dark px-3 py-1 text-[10px] cursor-pointer">${escapeHtml(name)}</a>`
                    ).join('');
                }
            } else if (configNotice) {
                configNotice.classList.add('hidden');
            }

            // Update Now button (only for local/non-Docker)
            const updateBtn = document.getElementById('btn-update-now');
            if (updateBtn) {
                if (status.update_available && status.deployment_type === 'local') {
                    updateBtn.style.display = 'block';
                    updateBtn.disabled = false;
                } else if (!status.update_available && status.deployment_type === 'local') {
                    updateBtn.style.display = 'block';
                    updateBtn.disabled = true;
                    updateBtn.textContent = window.i18n.t('admin.messages.already_latest');
                } else {
                    updateBtn.style.display = 'none';
                }
            }

            // View Release button
            const releaseBtn = document.getElementById('btn-view-release');
            if (releaseBtn && status.release_url) {
                releaseBtn.style.display = 'inline-block';
                releaseBtn.href = status.release_url;
            }

            // Up to date message
            if (!status.update_available) {
                const noticesDiv2 = document.getElementById('update-notices');
                if (noticesDiv2) {
                    noticesDiv2.classList.remove('hidden');
                    const msg = window.i18n.t('admin.update.up_to_date');
                    noticesDiv2.innerHTML = `<div class="text-xs tag-text p-2 border border-success bg-success bg-opacity-10">${escapeHtml(msg)}</div>`;
                }
            }

            // Changelog button
            const changelogBtn = document.getElementById('btn-view-changelog');
            if (changelogBtn) {
                const hasContent = (status.releases && status.releases.length > 0) || (status.commits && status.commits.length > 0);
                if (hasContent && status.update_available) {
                    changelogBtn.style.display = 'block';
                    const count = (status.commits || []).length;
                    changelogBtn.textContent = window.i18n.t('admin.messages.view_changelog', { count });
                } else {
                    changelogBtn.style.display = 'none';
                }
            }

        } catch (e) {
            console.error(e);
            if (loading) {
                loading.textContent = window.i18n.t('admin.messages.update_error', { error: e.message });
                loading.classList.remove('hidden');
                loading.classList.add('text-danger');
            }
        }
    },

    showChangelog() {
        if (!this.updateData) return;
        const { releases, commits, compare_url, current_version, latest_version } = this.updateData;
        if ((!releases || releases.length === 0) && (!commits || commits.length === 0)) return;

        if (typeof ModalHelper === 'undefined') {
            console.error('ModalHelper not available');
            return;
        }

        const t = (key, params) => window.i18n.t(key, params);

        const extractWhatsChanged = (body) => {
            if (!body) return '';
            const marker = "## What's Changed";
            const idx = body.indexOf(marker);
            if (idx === -1) return '';
            const afterMarker = body.substring(idx + marker.length);
            const nextHeading = afterMarker.indexOf('\n## ');
            let section = nextHeading !== -1 ? afterMarker.substring(0, nextHeading) : afterMarker;
            // Strip the "**Full Changelog**: ..." line
            section = section.replace(/\*\*Full Changelog\*\*:.*$/gm, '').trim();
            return section;
        };

        const parseMarkdownList = (text) => {
            const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
            const listItems = lines.map(line => {
                // Strip leading "* " or "- "
                const cleaned = line.replace(/^[\*\-]\s+/, '');
                return `<li class="mb-1 last:mb-0">${escapeHtml(cleaned)}</li>`;
            });
            return `<ul class="list-disc list-inside text-xs">${listItems.join('')}</ul>`;
        };

        // What's Changed Tab
        let changesHtml = '';
        if (releases && releases.length > 0) {
            for (const rel of releases) {
                const changes = extractWhatsChanged(rel.body);
                if (!changes) continue;
                changesHtml += `
                <div class="bg p-2 border-b last:border-0 text-left">
                    <div class="mb-2">
                        <a href="${escapeHtml(rel.url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" class="font-mono text-xs bg-primary primary-text px-1 hover:bg-primary transition-colors">${escapeHtml(rel.tag)}</a>
                    </div>
                    ${parseMarkdownList(changes)}
                </div>`;
            }
        }

        // Commits Tab
        let commitsHtml = '';
        if (commits && commits.length > 0) {
            for (const c of commits) {
                commitsHtml += `
                <div class="border-b last:border-0 text-left">
                    <div class="flex items-center bg p-2 gap-2">
                        <a href="https://github.com/mrblomblo/blombooru/commit/${escapeHtml(c.hash)}" target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" class="font-mono text-xs bg-primary primary-text px-1 hover:bg-primary transition-colors">${escapeHtml(c.hash)}</a>
                        <span class="text-xs">${escapeHtml(c.message)}</span>
                    </div>
                </div>`;
            }
        }

        const hasChanges = changesHtml.length > 0;
        const hasCommits = commitsHtml.length > 0;

        const tabLabelChanges = t('admin.update.tab_whats_changed');
        const tabLabelCommits = t('admin.update.tab_commits', { count: (commits || []).length });
        const noReleasesMsg = t('admin.update.no_release_notes');
        const noCommitsMsg = t('admin.update.no_commits');
        const fullChangelogMsg = t('admin.update.view_full_changelog', { current: current_version, latest: latest_version });

        // Build tabbed UI
        const tabsHtml = `
        <div>
            ${(hasChanges && hasCommits) ? `
            <div class="flex border-b mb-3" id="changelog-tabs">
                <button class="px-3 py-1 text-xs font-bold border-b-2 border-primary text-primary cursor-pointer" data-tab="changes">${escapeHtml(tabLabelChanges)}</button>
                <button class="px-3 py-1 text-xs text-secondary hover:text-primary cursor-pointer" data-tab="commits">${escapeHtml(tabLabelCommits)}</button>
            </div>` : ''}
            <div class="max-h-80 overflow-y-auto custom-scrollbar">
                <div id="tab-changes" ${!hasChanges ? 'style="display:none"' : ''}>${changesHtml || `<div class="text-xs text-secondary">${escapeHtml(noReleasesMsg)}</div>`}</div>
                <div id="tab-commits" style="display:${hasChanges ? 'none' : 'block'}">${commitsHtml || `<div class="text-xs text-secondary">${escapeHtml(noCommitsMsg)}</div>`}</div>
            </div>
            ${compare_url ? `<div class="mt-3 pt-2 border-t text-center"><a href="${escapeHtml(compare_url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" class="text-xs text-primary hover:text-primary transition-colors">${escapeHtml(fullChangelogMsg)}</a></div>` : ''}
        </div>`;

        const modal = new ModalHelper({
            id: 'changelog-modal',
            type: 'info',
            confirmId: 'changelog-confirm-btn',
            title: window.i18n.t('modal.changelog.title'),
            message: tabsHtml,
            confirmText: window.i18n.t('common.got_it'),
            cancelText: '',
            onConfirm: () => {
                modal.destroy();
            }
        });

        modal.show();

        // Wire up tab switching
        const tabContainer = document.getElementById('changelog-tabs');
        if (tabContainer) {
            tabContainer.querySelectorAll('button').forEach(btn => {
                btn.addEventListener('click', () => {
                    const tabName = btn.dataset.tab;
                    // Update active tab styles
                    tabContainer.querySelectorAll('button').forEach(b => {
                        b.classList.remove('border-b-2', 'border-primary', 'text-primary');
                        b.classList.add('text-secondary');
                    });
                    btn.classList.add('border-b-2', 'border-primary', 'text-primary');
                    btn.classList.remove('text-secondary');
                    // Show/hide tab content
                    document.getElementById('tab-changes').style.display = tabName === 'changes' ? 'block' : 'none';
                    document.getElementById('tab-commits').style.display = tabName === 'commits' ? 'block' : 'none';
                });
            });
        }
    },

    async performUpdate() {
        if (typeof ModalHelper === 'undefined') {
            console.error('ModalHelper not available');
            if (!confirm(window.i18n.t('notifications.admin.update_confirm', { target: 'latest' }))) return;
            this._execute_update();
            return;
        }

        const modal = new ModalHelper({
            id: 'update-confirm-modal',
            type: 'warning',
            confirmId: 'update-confirm-yes',
            cancelId: 'update-confirm-no',
            title: window.i18n.t('common.system_update'),
            message: window.i18n.t('modal.system_update.message', { target: 'latest' }),
            confirmText: window.i18n.t('modal.system_update.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            onConfirm: () => {
                this._execute_update();
                modal.destroy();
            },
            onCancel: () => {
                modal.destroy();
            }
        });

        modal.show();
    },

    async _execute_update() {
        const resultDiv = document.getElementById('update-result');
        const resultLog = document.getElementById('update-result-log');
        if (resultDiv) resultDiv.classList.remove('hidden');
        if (resultLog) resultLog.textContent = window.i18n.t('admin.messages.update_started');

        try {
            const response = await app.apiCall('/api/system/update/perform', {
                method: 'POST',
                body: JSON.stringify({ target: 'latest' })
            });

            if (resultLog) {
                resultLog.textContent = (response.log || '') + "\n\n" + (response.message || '');
            }

            if (response.success) {
                app.showNotification(
                    window.i18n.t('notifications.admin.update_initiated'),
                    'success'
                );
            }
        } catch (e) {
            if (resultLog) resultLog.textContent += `\nError: ${e.message}`;
            app.showNotification(
                window.i18n.t('notifications.admin.update_failed', { error: e.message }),
                'error'
            );
        }
    },

    async uploadFullBackup(file) {
        const statusDiv = document.getElementById('full-import-status');
        const progressDiv = document.getElementById('full-import-progress');

        statusDiv.style.display = 'block';
        progressDiv.innerHTML = `
            <div class="bg-primary primary-text p-3 mb-2">
                <strong>${window.i18n.t('admin.messages.uploading_importing_backup')}</strong><br>
                <div class="loader mt-2"></div>
                <span class="text-xs">${window.i18n.t('admin.messages.upload_warning_strong')}</span>
            </div>
            `;

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/admin/import/full', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Import failed');
            }

            const result = await response.json();

            progressDiv.innerHTML = `
                <div class="bg-success p-3 mb-2 tag-text">
                    <strong>${window.i18n.t('admin.messages.import_completed')}</strong>
                </div>
            `;

            // Reload all stats
            this.app.content.loadTagStats();
            this.app.content.loadMediaStats();
            this.app.content.loadAlbumStats();

        } catch (error) {
            progressDiv.innerHTML = `
                <div class="bg-danger p-3 tag-text">
                    <strong>Error:</strong> ${error.message}
                </div>
                `;
        }
    },
});
