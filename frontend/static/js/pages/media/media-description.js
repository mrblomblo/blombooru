// MediaViewer description markdown editor, preview, and layout controls
Object.assign(MediaViewer.prototype, {
    setupDescriptionTabs() {
        const toggleBtn = this.el('desc-toggle-mode-btn');
        const enlargedToggleBtn = this.el('enlarged-desc-toggle-mode-btn');
        const enlargeBtn = this.el('desc-enlarge-btn');
        const shrinkBtn = this.el('enlarged-desc-shrink-btn');

        if (!this._descEventsInitialized) {
            this._descEventsInitialized = true;

            const handleToggleMode = () => {
                const nextMode = this.descMode === 'preview' ? 'edit' : 'preview';
                this.showDescriptionMode(nextMode);
                if (nextMode === 'edit') {
                    const input = this.isDescEnlarged ? this.el('enlarged-description-input') : this.el('description-input');
                    if (input) input.focus();
                }
            };

            if (toggleBtn) toggleBtn.addEventListener('click', handleToggleMode);
            if (enlargedToggleBtn) enlargedToggleBtn.addEventListener('click', handleToggleMode);

            if (enlargeBtn) enlargeBtn.addEventListener('click', () => this.toggleDescriptionEnlarged());
            if (shrinkBtn) shrinkBtn.addEventListener('click', () => this.toggleDescriptionEnlarged());

            const descriptionInput = this.el('description-input');
            const enlargedInput = this.el('enlarged-description-input');

            if (descriptionInput) {
                descriptionInput.addEventListener('input', () => {
                    if (enlargedInput) enlargedInput.value = descriptionInput.value;
                    this.updateSaveDescriptionButtonVisibility();
                    this.updateDescriptionToggleVisibility();
                    this.autoResizeDescriptionInput();
                });
            }

            if (enlargedInput) {
                enlargedInput.addEventListener('input', () => {
                    if (descriptionInput) descriptionInput.value = enlargedInput.value;
                    this.updateSaveDescriptionButtonVisibility();
                    this.updateDescriptionToggleVisibility();
                    this.autoResizeDescriptionInput();
                });
            }
        }

        // Preview mode by default when a description exists, edit mode when empty
        this.showDescriptionMode(this.currentMedia && this.currentMedia.description ? 'preview' : 'edit');
        this.updateSaveDescriptionButtonVisibility();
        this.updateDescriptionToggleVisibility();
    },

    applyDescriptionLayout() {
        const isEnlarged = Boolean(this.isDescEnlarged);
        const enlargedSection = this.el('enlarged-description-section');
        const sidebarDisplay = this.el('description-display-section');
        const sidebarEdit = this.el('edit-description-section');
        const enlargedDisplay = this.el('enlarged-desc-display-section');
        const enlargedAdmin = this.el('enlarged-desc-admin-section');
        const hasDesc = Boolean(this.currentMedia && this.currentMedia.description);

        if (isEnlarged) {
            if (sidebarDisplay) sidebarDisplay.style.display = 'none';
            if (sidebarEdit) sidebarEdit.style.display = 'none';

            if (app.isAdminMode) {
                if (enlargedSection) enlargedSection.style.display = 'block';
                if (enlargedAdmin) enlargedAdmin.style.display = 'block';
                if (enlargedDisplay) enlargedDisplay.style.display = 'none';
                this.autoResizeDescriptionInput();
            } else if (hasDesc) {
                if (enlargedSection) enlargedSection.style.display = 'block';
                if (enlargedDisplay) enlargedDisplay.style.display = 'block';
                if (enlargedAdmin) enlargedAdmin.style.display = 'none';
            } else {
                if (enlargedSection) enlargedSection.style.display = 'none';
            }
        } else {
            if (enlargedSection) enlargedSection.style.display = 'none';

            if (app.isAdminMode) {
                if (sidebarEdit) sidebarEdit.style.display = 'block';
                if (sidebarDisplay) sidebarDisplay.style.display = 'none';
                this.autoResizeDescriptionInput();
            } else if (hasDesc) {
                if (sidebarDisplay) sidebarDisplay.style.display = 'block';
                if (sidebarEdit) sidebarEdit.style.display = 'none';
            } else {
                if (sidebarDisplay) sidebarDisplay.style.display = 'none';
                if (sidebarEdit) sidebarEdit.style.display = 'none';
            }
        }
    },

    async toggleDescriptionEnlarged() {
        if (this._isTogglingEnlarge) return;
        this._isTogglingEnlarge = true;

        const previousState = this.isDescEnlarged;
        const nextState = !previousState;
        this.isDescEnlarged = nextState;
        if (this.currentMedia) {
            this.currentMedia.description_enlarged = nextState;
        }

        const activeInput = nextState ? this.el('description-input') : this.el('enlarged-description-input');
        const targetInput = nextState ? this.el('enlarged-description-input') : this.el('description-input');
        if (activeInput && targetInput) {
            targetInput.value = activeInput.value;
        }

        this.applyDescriptionLayout();
        this.updateDescriptionToggleVisibility();

        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ description_enlarged: nextState })
            });
        } catch (e) {
            this.isDescEnlarged = previousState;
            if (this.currentMedia) {
                this.currentMedia.description_enlarged = previousState;
            }
            this.applyDescriptionLayout();
            this.updateDescriptionToggleVisibility();
            app.showNotification(e.message, 'error');
        } finally {
            this._isTogglingEnlarge = false;
        }
    },

    updateDescriptionToggleVisibility() {
        const toggleBtn = this.el('desc-toggle-mode-btn');
        const enlargedToggleBtn = this.el('enlarged-desc-toggle-mode-btn');
        const enlargeBtn = this.el('desc-enlarge-btn');
        const shrinkBtn = this.el('enlarged-desc-shrink-btn');
        const input = this.isDescEnlarged ? this.el('enlarged-description-input') : this.el('description-input');
        const hasContent = input ? input.value.trim().length > 0 : false;
        const hasSavedDesc = Boolean(this.currentMedia && this.currentMedia.description && this.currentMedia.description.trim().length > 0);

        if (toggleBtn) toggleBtn.style.display = hasContent ? 'block' : 'none';
        if (enlargedToggleBtn) enlargedToggleBtn.style.display = hasContent ? 'block' : 'none';
        if (enlargeBtn) enlargeBtn.style.display = hasSavedDesc ? 'block' : 'none';
        if (shrinkBtn) shrinkBtn.style.display = this.isDescEnlarged ? 'block' : 'none';
    },

    autoResizeDescriptionInput() {
        const textarea = this.isDescEnlarged ? this.el('enlarged-description-input') : this.el('description-input');
        if (!textarea) return;

        if (!textarea.offsetParent) return;

        textarea.style.height = 'auto';

        const computed = window.getComputedStyle(textarea);
        const borderTop = parseFloat(computed.borderTopWidth) || 0;
        const borderBottom = parseFloat(computed.borderBottomWidth) || 0;
        const borderVertical = borderTop + borderBottom;

        const minHeight = parseFloat(computed.minHeight) || (this.isDescEnlarged ? 112 : 80);
        const maxHeight = parseFloat(computed.maxHeight) || (this.isDescEnlarged ? 512 : 320);

        const totalContentHeight = textarea.scrollHeight + borderVertical;
        const targetHeight = Math.min(Math.max(totalContentHeight, minHeight), maxHeight);

        textarea.style.height = `${targetHeight}px`;
        textarea.style.overflowY = totalContentHeight > maxHeight ? 'auto' : 'hidden';
    },

    updateSaveDescriptionButtonVisibility() {
        const input = this.isDescEnlarged ? this.el('enlarged-description-input') : this.el('description-input');
        const saveBtn = this.el('save-description-btn');
        const enlargedSaveBtn = this.el('enlarged-save-description-btn');

        const currentVal = input ? input.value.trim() : '';
        const savedVal = (this.currentMedia && this.currentMedia.description) ? this.currentMedia.description.trim() : '';
        const isDifferent = currentVal !== savedVal;
        const displayStyle = isDifferent ? 'block' : 'none';

        if (saveBtn) saveBtn.style.display = displayStyle;
        if (enlargedSaveBtn) enlargedSaveBtn.style.display = displayStyle;
    },

    async showDescriptionMode(mode) {
        const sidebarEditPane = this.el('desc-edit-pane');
        const sidebarPreviewPane = this.el('desc-preview-pane');
        const sidebarToggleBtn = this.el('desc-toggle-mode-btn');
        const sidebarPreviewIcon = this.el('desc-preview-icon');
        const sidebarEditIcon = this.el('desc-edit-icon');

        const enlargedEditPane = this.el('enlarged-desc-edit-pane');
        const enlargedPreviewPane = this.el('enlarged-desc-preview-pane');
        const enlargedToggleBtn = this.el('enlarged-desc-toggle-mode-btn');
        const enlargedPreviewIcon = this.el('enlarged-desc-preview-icon');
        const enlargedEditIcon = this.el('enlarged-desc-edit-icon');

        this.descMode = mode;
        const isPreview = mode === 'preview';

        if (sidebarEditPane) sidebarEditPane.style.display = isPreview ? 'none' : 'block';
        if (sidebarPreviewPane) sidebarPreviewPane.style.display = isPreview ? 'block' : 'none';
        if (enlargedEditPane) enlargedEditPane.style.display = isPreview ? 'none' : 'block';
        if (enlargedPreviewPane) enlargedPreviewPane.style.display = isPreview ? 'block' : 'none';

        const updateToggleUI = (btn, previewIcon, editIcon) => {
            if (!btn) return;
            if (isPreview) {
                if (previewIcon) previewIcon.style.display = 'none';
                if (editIcon) editIcon.style.display = 'block';
                const label = window.i18n.t('common.edit');
                btn.title = label;
                btn.setAttribute('aria-label', label);
            } else {
                if (previewIcon) previewIcon.style.display = 'block';
                if (editIcon) editIcon.style.display = 'none';
                const label = window.i18n.t('common.preview');
                btn.title = label;
                btn.setAttribute('aria-label', label);
            }
        };

        updateToggleUI(sidebarToggleBtn, sidebarPreviewIcon, sidebarEditIcon);
        updateToggleUI(enlargedToggleBtn, enlargedPreviewIcon, enlargedEditIcon);

        if (isPreview) {
            await this.renderDescriptionPreview();
        } else {
            this.autoResizeDescriptionInput();
        }
        this.updateDescriptionToggleVisibility();
    },

    async renderDescriptionPreview() {
        const requestId = ++this._descPreviewRequestId;
        const sidebarContent = this.el('desc-preview-content');
        const enlargedContent = this.el('enlarged-desc-preview-content');
        const activeInput = this.isDescEnlarged ? this.el('enlarged-description-input') : this.el('description-input');
        if (!activeInput) return;

        const text = activeInput.value;
        if (!text.trim()) {
            if (sidebarContent) sidebarContent.innerHTML = '';
            if (enlargedContent) enlargedContent.innerHTML = '';
            return;
        }

        if (this.currentMedia && this.currentMedia.description === text && this.currentMedia.description_html) {
            if (sidebarContent) sidebarContent.innerHTML = this.currentMedia.description_html;
            if (enlargedContent) enlargedContent.innerHTML = this.currentMedia.description_html;
            return;
        }
        try {
            const res = await app.apiCall('/api/media/preview-description', {
                method: 'POST',
                body: JSON.stringify({ text })
            });
            if (requestId !== this._descPreviewRequestId) return;
            const html = res.html || '';
            if (sidebarContent) sidebarContent.innerHTML = html;
            if (enlargedContent) enlargedContent.innerHTML = html;
        } catch (e) {
            if (requestId !== this._descPreviewRequestId) return;
            if (sidebarContent) sidebarContent.textContent = text;
            if (enlargedContent) enlargedContent.textContent = text;
            app.showNotification(e.message, 'error');
        }
    },

    async saveDescription() {
        const activeInput = this.isDescEnlarged ? this.el('enlarged-description-input') : this.el('description-input');
        const descriptionValue = activeInput ? activeInput.value.trim() : '';

        try {
            const updated = await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ description: descriptionValue || null })
            });
            this.currentMedia.description = updated.description;
            this.currentMedia.description_html = updated.description_html;
            this.currentMedia.description_enlarged = updated.description_enlarged;

            this.isDescEnlarged = Boolean(updated.description_enlarged);
            this.applyDescriptionLayout();

            const val = updated.description || '';
            const descInput = this.el('description-input');
            const enlargedDescInput = this.el('enlarged-description-input');
            if (descInput) descInput.value = val;
            if (enlargedDescInput) enlargedDescInput.value = val;

            const html = updated.description_html || '';
            const previewContent = this.el('desc-preview-content');
            const enlargedPreviewContent = this.el('enlarged-desc-preview-content');
            if (previewContent) previewContent.innerHTML = html;
            if (enlargedPreviewContent) enlargedPreviewContent.innerHTML = html;

            const displayText = this.el('description-display-text');
            const enlargedDisplayText = this.el('enlarged-desc-display-text');
            if (displayText) displayText.innerHTML = html;
            if (enlargedDisplayText) enlargedDisplayText.innerHTML = html;

            if (updated.description) {
                await this.showDescriptionMode('preview');
            } else {
                await this.showDescriptionMode('edit');
            }
            this.updateSaveDescriptionButtonVisibility();
            this.updateDescriptionToggleVisibility();

            app.showNotification(window.i18n.t('notifications.media.description_updated'), 'success');
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('notifications.media.error_updating_description'));
        }
    },
});
