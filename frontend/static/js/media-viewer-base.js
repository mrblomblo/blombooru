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
    renderInfo(media, options = {}) {
        const { downloadUrl, isShared } = options;
        
        let infoHTML = `
            <div class="info-row"><span>Filename</span><strong>${media.filename}</strong></div>
            <div class="info-row"><span>Type</span><strong>${media.file_type}</strong></div>
            <div class="info-row"><span>Size</span><strong>${this.formatFileSize(media.file_size)}</strong></div>
            <div class="info-row"><span>Dimensions</span><strong>${media.width}x${media.height}</strong></div>
            <div class="info-row"><span>Rating</span><strong>${media.rating}</strong></div>
            <div class="info-row"><span>Uploaded</span><strong>${new Date(media.uploaded_at).toLocaleDateString()}</strong></div>
            ${media.duration ? `<div class="info-row"><span>Duration</span><strong>${this.formatDuration(media.duration)}</strong></div>` : ''}
        `;

        if (media.source) {
            infoHTML += `
                <div class="info-row">
                    <span>Source</span>
                    <strong>
                        <a href="${media.source}" target="_blank" rel="noopener noreferrer" 
                           class="text-primary hover:underline" style="word-break: break-all;">
                            ${media.source}
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
            const res = await fetch(`/api/media/${media.id}/metadata`);
            if (!res.ok) {
                this.hideAIMetadata(section, appendBtn, aiMetadataShareToggle);
                return;
            }

            const metadata = await res.json();
            const aiData = this.extractAIData(metadata);

            if (!aiData || Object.keys(aiData).length === 0) {
                this.hideAIMetadata(section, appendBtn, aiMetadataShareToggle);
                return;
            }

            // Show controls if specified
            if (showControls) {
                if (aiMetadataShareToggle) {
                    aiMetadataShareToggle.style.display = 'block';
                }
                if (appendBtn && aiData) {
                    appendBtn.style.display = 'block';
                }
            }

            content.innerHTML = this.generateAIMetadataHTML(aiData);
            section.style.display = 'block';
            this.setupExpandableListeners();
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

    extractAIData(metadata) {
        // Check for AI parameters in common fields
        const locations = [
            metadata.parameters,
            metadata.Parameters,
            metadata.prompt
        ];

        for (const location of locations) {
            if (location) {
                return typeof location === 'string' ? JSON.parse(location) : location;
            }
        }
        
        return null;
    }

    generateAIMetadataHTML(aiData) {
        let html = '';

        Object.entries(aiData).forEach(([key, value]) => {
            const sectionTitle = this.formatKey(key);

            html += `<div class="ai-section mb-3">`;
            html += `<h4 class="text-xs font-bold text-[var(--primary-color)] mb-2">${sectionTitle}</h4>`;
            
            if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                html += `<div class="ml-2">`;
                Object.entries(value).forEach(([subKey, subValue]) => {
                    html += `
                        <div class="ai-data-row">
                            <span class="text-secondary">${this.formatKey(subKey)}:</span>
                            <div class="text">${this.formatValue(subValue, true)}</div>
                        </div>
                    `;
                });
                html += `</div>`;
            } else {
                html += `<div class="text ml-2">${this.formatValue(value, true)}</div>`;
            }

            html += `</div>`;
        });

        return html;
    }

    setupExpandableListeners() {
        document.querySelectorAll('.expandable-text').forEach(container => {
            const newContainer = container.cloneNode(true);
            container.parentNode.replaceChild(newContainer, container);

            newContainer.addEventListener('click', function(e) {
                const selection = window.getSelection();
                if (selection && selection.toString().length > 0) {
                    return;
                }

                const id = this.id.replace('-container', '');
                window.toggleExpand(id);
            });

            newContainer.addEventListener('dblclick', function(e) {
                e.stopPropagation();
            });
        });
    }

    // Utility methods
    formatKey(key) {
        return key
            .replace(/_/g, ' ')
            .replace(/([A-Z])/g, ' $1')
            .trim()
            .replace(/\b\w/g, c => c.toUpperCase())
            .replace(/Cfgscale/g, 'CFG Scale')
            .replace(/Cfg Scale/g, 'CFG Scale')
            .replace(/Vae/g, 'VAE')
            .replace(/Aspectratio/g, 'Aspect Ratio')
            .replace(/Aspect Ratio/g, 'Aspect Ratio')
            .replace(/Automaticvae/g, 'Automatic VAE')
            .replace(/Automatic Vae/g, 'Automatic VAE')
            .replace(/Negativeprompt/g, 'Negative Prompt')
            .replace(/Negative Prompt/g, 'Negative Prompt');
    }

    formatValue(value, isExpandable = true) {
        if (typeof value === 'boolean') {
            return value ? 'Yes' : 'No';
        }
        
        if (typeof value === 'string') {
            const escaped = value.replace(/</g, '&lt;').replace(/>/g, '&gt;');

            if (isExpandable && escaped.length > 100) {
                const id = 'expand-' + Math.random().toString(36).substr(2, 9);
                return `
                    <div class="expandable-text" id="${id}-container" style="cursor: pointer; user-select: text;">
                        <span class="text-truncated" id="${id}-truncated">${escaped.substring(0, 100)}...<br><span class="expand-indicator" style="user-select: none;">[click to expand]</span></span>
                        <span class="text-full" id="${id}-full" style="display: none;">${escaped}<br><span class="expand-indicator" style="user-select: none;">[click to collapse]</span></span>
                    </div>
                `;
            }
            return escaped;
        }
        
        if (Array.isArray(value)) {
            return value.join(', ');
        }
        
        return String(value);
    }

    formatFileSize(bytes) {
        if (!bytes) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
    }

    formatDuration(seconds) {
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${minutes}:${String(secs).padStart(2, '0')}`;
    }

    getPlainTextFromDiv(div) {
        return div.textContent || '';
    }

    getCursorPosition(element) {
        const selection = window.getSelection();
        if (selection.rangeCount === 0) return 0;
        
        const range = selection.getRangeAt(0);
        const preCaretRange = range.cloneRange();
        preCaretRange.selectNodeContents(element);
        preCaretRange.setEnd(range.endContainer, range.endOffset);
        
        return preCaretRange.toString().length;
    }

    setCursorPosition(element, offset) {
        const selection = window.getSelection();
        const range = document.createRange();
        
        let currentOffset = 0;
        let found = false;
        
        function traverseNodes(node) {
            if (found) return;
            
            if (node.nodeType === Node.TEXT_NODE) {
                const nodeLength = node.textContent.length;
                if (currentOffset + nodeLength >= offset) {
                    range.setStart(node, offset - currentOffset);
                    range.collapse(true);
                    found = true;
                    return;
                }
                currentOffset += nodeLength;
            } else {
                for (let child of node.childNodes) {
                    traverseNodes(child);
                    if (found) return;
                }
            }
        }
        
        try {
            traverseNodes(element);
            if (!found && element.lastChild) {
                range.setStartAfter(element.lastChild);
                range.collapse(true);
            }
            selection.removeAllRanges();
            selection.addRange(range);
        } catch (e) {
            console.error('Error setting cursor:', e);
        }
    }
}

// Global function for expand/collapse functionality
window.toggleExpand = function(id) {
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
