class MediaViewerBase {
    constructor() {
        this.currentMedia = null;
        this.fullscreenViewer = null;
    }

    el(id) {
        return document.getElementById(id);
    }

    initFullscreenViewer() {
        this.fullscreenViewer = new FullscreenMediaViewer();
    }

    // Common rendering methods
    setupAIMetadataToggle() {
        const toggle = this.el('ai-metadata-toggle');

        if (toggle) {
            const newToggle = toggle.cloneNode(true);
            toggle.parentNode.replaceChild(newToggle, toggle);

            newToggle.addEventListener('click', (e) => {
                const content = this.el('ai-metadata-content');
                const chevron = this.el('ai-metadata-chevron');

                if (content) {
                    const isHidden = content.style.display === 'none';
                    content.style.display = isHidden ? 'block' : 'none';

                    if (chevron) {
                        chevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
                    }
                }
            });
        }
    }

    renderInfo(media, options = {}) {
        const { downloadUrl, isShared } = options;

        let infoHTML = `
            <div class="info-row"><span class="flex-shrink-0">${window.i18n.t('media.info.filename')}</span><strong class="truncate ml-4 text-right min-w-0" title="${this.escapeHtml(media.filename)}">${this.escapeHtml(media.filename)}</strong></div>
            <div class="info-row"><span class="flex-shrink-0">${window.i18n.t('media.info.type')}</span><strong class="text-right">${media.file_type}</strong></div>
            <div class="info-row"><span class="flex-shrink-0">${window.i18n.t('media.info.size')}</span><strong class="text-right">${this.formatFileSize(media.file_size)}</strong></div>
            <div class="info-row"><span class="flex-shrink-0">${window.i18n.t('media.info.dimensions')}</span><strong class="text-right">${media.width}x${media.height}</strong></div>
            <div class="info-row"><span class="flex-shrink-0">${window.i18n.t('media.info.rating')}</span><strong class="text-right">${media.rating}</strong></div>
            <div class="info-row"><span class="flex-shrink-0">${window.i18n.t('media.info.uploaded')}</span><strong class="text-right">${new Date(media.uploaded_at).toLocaleDateString()}</strong></div>
            ${media.duration ? `<div class="info-row"><span class="flex-shrink-0">${window.i18n.t('media.info.duration')}</span><strong class="text-right">${this.formatDuration(media.duration)}</strong></div>` : ''}
        `;

        if (media.source) {
            infoHTML += `
                <div class="info-row">
                    <span class="flex-shrink-0 mr-4">${window.i18n.t('media.info.source')}</span>
                    <strong class="truncate min-w-0 text-right flex-1">
                        <a href="${media.source}" target="_blank" rel="noopener noreferrer" 
                           class="text-primary hover:underline block truncate" title="${this.escapeHtml(media.source)}">
                            ${this.escapeHtml(media.source)}
                        </a>
                    </strong>
                </div>
            `;
        }

        this.el('media-info-content').innerHTML = infoHTML;

        // Handle rating select if present (for non-shared views)
        const ratingSelect = this.el('rating-select');
        if (ratingSelect) {
            ratingSelect.value = media.rating;
        }
    }

    renderTags(media, options = {}) {
        const { clickable = true } = options;
        const container = this.el('tags-container');
        const groups = { artist: [], character: [], copyright: [], general: [], meta: [] };

        (media.tags || []).forEach(tag => {
            if (groups[tag.category]) {
                groups[tag.category].push(tag);
            }
        });

        let html = '';
        Object.entries(groups).forEach(([category, tags]) => {
            if (!tags.length) return;

            tags.sort((a, b) => a.name.localeCompare(b.name));

            html += `
                <div class="tag-category">
                    <h4>${category}</h4>
                    <div class="tag-list">
                        ${tags.map(tag =>
                clickable
                    ? `<a href="/?q=${encodeURIComponent(tag.name)}" class="tag ${category} tag-text">${tag.name}</a>`
                    : `<span class="tag ${category} tag-text">${tag.name}</span>`
            ).join('')}
                    </div>
                </div>
            `;
        });

        container.innerHTML = html || '<p class="text-xs text-secondary mb-3">No tags</p>';
    }

    async renderAIMetadata(media, options = {}) {
        const { showControls = false } = options;
        const section = this.el('ai-metadata-section');
        const content = this.el('ai-metadata-content');
        const appendBtn = this.el('append-ai-tags-btn');
        const aiMetadataShareToggle = this.el('ai-metadata-share-toggle');

        try {
            let url = `/api/media/${media.id}/metadata`;
            if (options.isShared && media.share_uuid) {
                url = `/api/shared/${media.share_uuid}/metadata`;
            } else if (options.isShared && this.shareUuid) {
                // Fallback if media object doesn't have share_uuid but the viewer does
                url = `/api/shared/${this.shareUuid}/metadata`;
            }

            const res = await fetch(url);
            if (!res.ok) {
                this.hideAIMetadata(section, appendBtn, aiMetadataShareToggle);
                return;
            }

            const metadata = await res.json();
            const aiData = AITagUtils.extractAIData(metadata);

            if (!aiData || Object.keys(aiData).length === 0) {
                this.hideAIMetadata(section, appendBtn, aiMetadataShareToggle);
                return;
            }

            if (showControls) {
                if (aiMetadataShareToggle) aiMetadataShareToggle.style.display = 'block';
                if (appendBtn) appendBtn.style.display = 'block';
            }

            const generatedHTML = this.generateAIMetadataHTML(aiData);
            content.innerHTML = generatedHTML;
            section.style.display = 'block';
            this.setupAIMetadataEvents(content);
        } catch (e) {
            console.error('Error rendering AI metadata:', e);
            this.hideAIMetadata(section, appendBtn, aiMetadataShareToggle);
        }
    }

    hideAIMetadata(section, appendBtn, aiMetadataShareToggle) {
        if (section) section.style.display = 'none';
        if (appendBtn) appendBtn.style.display = 'none';
        if (aiMetadataShareToggle) aiMetadataShareToggle.style.display = 'none';
    }

    generateAIMetadataHTML(aiData) {
        let html = '';

        for (const [key, value] of Object.entries(aiData)) {
            const sectionTitle = this.escapeHtml(this.formatKey(key));

            html += `<div class="ai-section mb-3">`;
            html += `<h4 class="text-xs font-bold text-primary mb-2">${sectionTitle}</h4>`;

            if (this.isPlainObject(value)) {
                html += `<div class="ml-2">`;
                for (const [subKey, subValue] of Object.entries(value)) {
                    html += `
                    <div class="ai-data-row">
                        <span class="text-secondary">${this.escapeHtml(this.formatKey(subKey))}:</span>
                        <div class="text">${this.formatValue(subValue, true)}</div>
                    </div>
                `;
                }
                html += `</div>`;
            } else {
                html += `<div class="text ml-2">${this.formatValue(value, true)}</div>`;
            }

            html += `</div>`;
        }

        return html;
    }

    setupAIMetadataEvents(content) {
        if (!content) {
            content = this.el('ai-metadata-content');
        }
        if (!content) return;

        // Use a namespaced handler reference for clean removal
        if (this._aiMetadataClickHandler) {
            content.removeEventListener('click', this._aiMetadataClickHandler);
        }

        this._aiMetadataClickHandler = (e) => {
            const btn = e.target.closest('.ai-toggle-btn');
            if (!btn) return;

            const wrapper = btn.closest('.ai-expandable-wrapper');
            const textDiv = wrapper?.querySelector('.ai-text-content');

            if (textDiv) {
                const isCollapsed = textDiv.classList.contains('is-collapsed');

                if (isCollapsed) {
                    textDiv.classList.remove('is-collapsed');
                    btn.classList.add('is-expanded');
                    btn.textContent = 'Show less';
                } else {
                    textDiv.classList.add('is-collapsed');
                    btn.classList.remove('is-expanded');
                    btn.textContent = 'Show more';
                }
            }
        };

        content.addEventListener('click', this._aiMetadataClickHandler);
    }

    // Utility methods

    isPlainObject(value) {
        return typeof value === 'object' &&
            value !== null &&
            !Array.isArray(value) &&
            Object.prototype.toString.call(value) === '[object Object]';
    }

    formatKey(key) {
        // First, handle snake_case and camelCase conversion to spaces
        let formatted = key
            .replace(/_/g, ' ')
            .replace(/([a-z])([A-Z])/g, '$1 $2')
            .trim();

        // Title case each word
        formatted = formatted.replace(/\b\w/g, c => c.toUpperCase());

        // Apply specific formatting rules (only need each once now)
        const replacements = {
            'Cfg Scale': 'CFG Scale',
            'Cfgscale': 'CFG Scale',
            'Vae': 'VAE',
            'Aspectratio': 'Aspect Ratio',
            'Automaticvae': 'Automatic VAE',
            'Negativeprompt': 'Negative Prompt',
            'Loras': 'LoRAs',
            'Lora': 'LoRA'
        };

        for (const [search, replace] of Object.entries(replacements)) {
            formatted = formatted.replace(new RegExp(search, 'g'), replace);
        }

        return formatted;
    }

    escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    formatValue(value, isExpandable = true) {
        if (value === null || value === undefined) {
            return '<span class="text-secondary text-xs italic">Empty</span>';
        }

        if (typeof value === 'boolean') {
            return value
                ? '<span class="text text-xs">Yes</span>'
                : '<span class="text text-xs">No</span>';
        }

        if (Array.isArray(value)) {
            if (value.length === 0) {
                return '<span class="text-secondary text-xs italic">None</span>';
            }

            // Handle arrays of objects (like LoRAs)
            if (value.some(v => this.isPlainObject(v))) {
                const items = value.map(v => {
                    if (this.isPlainObject(v)) {
                        // Format object entries nicely
                        const parts = Object.entries(v)
                            .map(([k, val]) => `${this.escapeHtml(this.formatKey(k))}: ${this.escapeHtml(String(val))}`)
                            .join(', ');
                        return parts;
                    }
                    return this.escapeHtml(String(v));
                });
                return items.map(item => `<div class="text-xs mb-1">${item}</div>`).join('');
            }

            // Simple array of primitives
            return this.escapeHtml(value.map(v => String(v)).join(', '));
        }

        if (this.isPlainObject(value)) {
            try {
                const jsonStr = JSON.stringify(value, null, 2);
                return `<code class="block bg-surface-dark p-2 text-xs overflow-x-auto">${this.escapeHtml(jsonStr)}</code>`;
            } catch {
                return '<span class="text-secondary text-xs italic">[Complex Object]</span>';
            }
        }

        const str = String(value);
        const escaped = this.escapeHtml(str);
        const lineCount = (str.match(/\n/g) || []).length;
        const needsExpansion = isExpandable && (str.length > 200 || lineCount > 4);

        if (needsExpansion) {
            return `
            <div class="ai-expandable-wrapper">
                <div class="ai-text-content is-collapsed">${escaped}</div>
                <button type="button" class="ai-toggle-btn">Show more</button>
            </div>
        `;
        }

        return `<div class="ai-text-content">${escaped}</div>`;
    }

    formatFileSize(bytes) {
        if (!bytes || bytes < 0) return '0 Bytes';
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
        return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
    }

    formatDuration(seconds) {
        if (!seconds || seconds < 0) return '0:00';

        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${minutes}:${String(secs).padStart(2, '0')}`;
    }
}

// Global function for expand/collapse functionality
window.toggleExpand = function (id) {
    const truncated = document.getElementById(id + '-truncated');
    const full = document.getElementById(id + '-full');

    if (full && truncated) {
        if (full.style.display === 'none') {
            truncated.style.display = 'none';
            full.style.display = 'inline';
        } else {
            truncated.style.display = 'inline';
            full.style.display = 'none';
        }
    }
};
