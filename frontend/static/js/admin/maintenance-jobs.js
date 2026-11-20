class MaintenanceJobRunner {
    constructor() {
        this.configs = new Map();
        this.activeJobs = new Set();
        this.startingJobs = new Set();
        this.originalTexts = new Map();
    }

    register(jobName, config) {
        this.configs.set(jobName, config);
    }

    isRunning(jobName) {
        return this.activeJobs.has(jobName) || this.startingJobs.has(jobName);
    }

    _getButtons(config) {
        const primaryBtn = config.buttonId ? document.getElementById(config.buttonId) : null;
        const extraBtns = (config.disableButtonIds || [])
            .map((id) => document.getElementById(id))
            .filter(Boolean);
        return { primaryBtn, extraBtns };
    }

    _setRunningUI(config, showProcessingBanner = false) {
        const { primaryBtn, extraBtns } = this._getButtons(config);
        const processingText = config.processingButtonText
            ? config.processingButtonText()
            : window.i18n.t('common.processing');

        if (primaryBtn) {
            if (!this.originalTexts.has(config.buttonId)) {
                this.originalTexts.set(config.buttonId, primaryBtn.textContent);
            }
            primaryBtn.disabled = true;
            primaryBtn.textContent = processingText;
        }
        extraBtns.forEach((b) => {
            b.disabled = true;
        });

        const statusDiv = config.statusDivId ? document.getElementById(config.statusDivId) : null;
        const resultDiv = config.resultDivId ? document.getElementById(config.resultDivId) : null;
        if (statusDiv) statusDiv.style.display = 'block';
        if (showProcessingBanner && resultDiv) {
            const bannerText = this._getDefaultBannerText(config, processingText);
            resultDiv.innerHTML = `<div class="bg-primary primary-text p-3"><strong>${escapeHtml(bannerText)}</strong></div>`;
        }
    }

    _getDefaultBannerText(config, processingText) {
        if (config.initialProgressText) return config.initialProgressText();
        if (config.progressLabel) return config.progressLabel();
        return processingText;
    }

    formatProgress(label, status, stats = []) {
        const cleanLabel = (label || window.i18n.t('common.processing')).replace(/\.{3}$|…$/, '');
        const fileInfo = status.current_file ? ` (${status.current_file})` : '';
        let text = `${cleanLabel}: ${status.current || 0}/${status.total}${fileInfo}`;
        const statParts = (stats || [])
            .filter(([statLabel, val]) => statLabel && val !== undefined && val !== null)
            .map(([statLabel, val]) => `${statLabel}: ${val}`);
        if (statParts.length > 0) {
            text += ` - ${statParts.join(', ')}`;
        }
        return text;
    }

    _buildProgressText(config, status, defaultBannerText) {
        if (config.renderProgress) {
            return config.renderProgress(status) || defaultBannerText;
        }
        if (!status.total) {
            return defaultBannerText;
        }
        const label = config.progressLabel ? config.progressLabel() : window.i18n.t('common.processing');
        const stats = config.progressStats ? config.progressStats(status) : [];
        return this.formatProgress(label, status, stats);
    }

    _isButtonLockedByActiveJob(buttonId) {
        for (const activeName of [...this.activeJobs, ...this.startingJobs]) {
            const cfg = this.configs.get(activeName);
            if (!cfg) continue;
            if (cfg.buttonId === buttonId || (cfg.disableButtonIds || []).includes(buttonId)) {
                return true;
            }
        }
        return false;
    }

    _restoreButtons(config) {
        const { primaryBtn, extraBtns } = this._getButtons(config);
        if (primaryBtn && !this._isButtonLockedByActiveJob(config.buttonId)) {
            primaryBtn.disabled = false;
            if (this.originalTexts.has(config.buttonId)) {
                primaryBtn.textContent = this.originalTexts.get(config.buttonId);
            }
        }
        extraBtns.forEach((b) => {
            if (!this._isButtonLockedByActiveJob(b.id)) {
                b.disabled = false;
            }
        });
    }

    _translateDetail(detail) {
        if (typeof detail !== 'string') return 'API call failed';
        const adminKey = `notifications.admin.${detail}`;
        const adminTranslated = window.i18n.t(adminKey);
        if (adminTranslated !== adminKey) {
            return adminTranslated;
        }
        const directTranslated = window.i18n.t(detail);
        if (directTranslated !== detail) {
            return directTranslated;
        }
        return detail;
    }

    _renderOutcome(resultDiv, message, type) {
        const cls =
            type === 'error'
                ? 'bg-danger p-3 tag-text'
                : type === 'warning'
                    ? 'bg-warning p-3 tag-text'
                    : type === 'info'
                        ? 'bg-primary primary-text p-3'
                        : 'bg-success p-3 tag-text';
        if (resultDiv && message) {
            resultDiv.innerHTML = `<div class="${cls}"><strong>${escapeHtml(message)}</strong></div>`;
        }
    }

    async start(jobName) {
        const config = this.configs.get(jobName);
        if (!config || this.isRunning(jobName)) return;

        this.startingJobs.add(jobName);
        this._setRunningUI(config, true);

        const resultDiv = config.resultDivId ? document.getElementById(config.resultDivId) : null;

        try {
            const res = await fetch(config.startUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });

            if (res.status === 409) {
                const statusData = await app.apiCall(config.statusUrl);
                const status = config.extractStatus ? config.extractStatus(statusData) : statusData;
                if (status && status.running) {
                    this.startingJobs.delete(jobName);
                    await this.poll(jobName);
                    return;
                }
                throw new Error(window.i18n.t('common.processing'));
            }

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                const fallbackMsg = config.startErrorMessage ? config.startErrorMessage() : null;
                const msg = errData.detail ? this._translateDetail(errData.detail) : (fallbackMsg || 'API call failed');
                throw new Error(msg);
            }

            await res.json().catch(() => ({}));
            this.startingJobs.delete(jobName);
            await this.poll(jobName);
        } catch (error) {
            this.startingJobs.delete(jobName);
            if (resultDiv) {
                resultDiv.innerHTML = `<div class="bg-danger p-3 tag-text"><strong>${escapeHtml(window.i18n.t('common.error'))}:</strong> ${escapeHtml(error.message)}</div>`;
            }
            app.showNotification(error.message, 'error');
            this._restoreButtons(config);
        }
    }

    async poll(jobName) {
        const config = this.configs.get(jobName);
        if (!config || this.activeJobs.has(jobName)) return;

        this.activeJobs.add(jobName);
        this._setRunningUI(config, true);

        const statusDiv = config.statusDivId ? document.getElementById(config.statusDivId) : null;
        const resultDiv = config.resultDivId ? document.getElementById(config.resultDivId) : null;
        const processingText = config.processingButtonText
            ? config.processingButtonText()
            : window.i18n.t('common.processing');
        const defaultBannerText = this._getDefaultBannerText(config, processingText);

        try {
            let finalStatus = null;
            while (true) {
                const data = await app.apiCall(config.statusUrl);
                const status = (config.extractStatus ? config.extractStatus(data) : data) || {};
                if (status.error) {
                    throw new Error(status.error);
                }
                if (!status.running) {
                    finalStatus = status;
                    break;
                }
                if (resultDiv) {
                    const text = this._buildProgressText(config, status, defaultBannerText);
                    resultDiv.innerHTML = `<div class="bg-primary primary-text p-3"><strong>${escapeHtml(text)}</strong></div>`;
                }
                await new Promise((resolve) => setTimeout(resolve, 1000));
            }

            const outcome = config.onComplete ? await config.onComplete(finalStatus) : null;
            const msg = outcome?.message || '';
            const type = outcome?.type || 'success';
            if (msg) {
                this._renderOutcome(resultDiv, msg, type);
                app.showNotification(msg, type);
            } else if (statusDiv) {
                statusDiv.style.display = 'none';
            }
        } catch (error) {
            if (resultDiv) {
                resultDiv.innerHTML = `<div class="bg-danger p-3 tag-text"><strong>${escapeHtml(window.i18n.t('common.error'))}:</strong> ${escapeHtml(error.message)}</div>`;
            }
            app.showNotification(error.message, 'error');
        } finally {
            this.activeJobs.delete(jobName);
            this._restoreButtons(config);
        }
    }

    async checkJob(jobName) {
        const config = this.configs.get(jobName);
        if (!config || this.isRunning(jobName)) return;
        try {
            const data = await app.apiCall(config.statusUrl);
            const status = config.extractStatus ? config.extractStatus(data) : data;
            if (status && status.running) {
                await this.poll(jobName);
            }
        } catch (error) {
            console.error(`Error checking status for maintenance job '${jobName}':`, error);
        }
    }

    async checkAll() {
        try {
            const data = await app.apiCall('/api/admin/maintenance/status');
            const jobs = (data && data.jobs) || {};
            const polls = [];
            for (const [jobName, status] of Object.entries(jobs)) {
                if (status && status.running && this.configs.has(jobName) && !this.isRunning(jobName)) {
                    polls.push(this.poll(jobName));
                }
            }
            if (polls.length > 0) {
                await Promise.all(polls);
            }
        } catch (error) {
            console.error('Error checking maintenance job statuses:', error);
        }
    }
}

window.maintenanceJobRunner = new MaintenanceJobRunner();
