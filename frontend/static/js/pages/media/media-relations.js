// MediaViewer parent/child hierarchy carousel, reorder, and relation manager modal
Object.assign(MediaViewer.prototype, {
    // ==================== Hierarchy Methods ====================
    async renderHierarchy(items) {
        const hierarchyMediaEl = this.el('hierarchy-media');
        const hierarchySection = this.el('hierarchy-media-section');
        const titleEl = this.el('hierarchy-media-title');

        if (!hierarchyMediaEl || !hierarchySection) return;

        if (!items || items.length === 0) {
            hierarchySection.style.display = 'none';
            return;
        }

        // Set dynamic title
        if (this.currentMedia.parent_id) {
            titleEl.textContent = window.i18n.t('media.relations.belongs_to_parent');
        } else {
            const childCount = items.length;
            titleEl.textContent = childCount === 1
                ? window.i18n.t('media.relations.has_one_child')
                : window.i18n.t('media.relations.has_children', { count: childCount });
        }

        const params = new URLSearchParams(window.location.search);
        params.delete('q');
        const queryString = params.toString();
        hierarchySection.style.display = 'block';

        const itemAlbumStatus = {};
        if (this.albumId) {
            const targetAlbumId = parseInt(this.albumId, 10);
            await Promise.all(items.map(async (media) => {
                try {
                    const res = await fetch(`/api/media/${media.id}/albums`);
                    if (res.ok) {
                        const data = await res.json();
                        const inAlbum = (data.albums || []).some(a => a.id === targetAlbumId);
                        itemAlbumStatus[media.id] = inAlbum;
                    }
                } catch (e) {
                    console.error(`Error checking album membership for media ${media.id}:`, e);
                }
            }));
        }

        hierarchyMediaEl.innerHTML = '';
        items.forEach(media => {
            const inAlbum = this.albumId ? (itemAlbumStatus[media.id] ?? false) : false;
            const item = this.createRelatedMediaItem(media, queryString, inAlbum);
            item.style.flex = '0 0 auto';
            item.style.width = '120px';
            hierarchyMediaEl.appendChild(item);
        });

        this.setupHierarchyToggle();
        this.setupCarousel();
        this.updateHierarchyEditOrderButton(items);
        this.setupHierarchyReorder();
    },

    updateHierarchyEditOrderButton(items) {
        const editOrderBtn = this.el('hierarchy-edit-order-btn');
        const titleEl = this.el('hierarchy-media-title');
        if (!editOrderBtn) return;

        const canReorder = Boolean(
            app.isAdminMode &&
            this.currentMedia &&
            !this.currentMedia.parent_id &&
            Array.isArray(items) &&
            items.length > 1
        );
        editOrderBtn.style.display = canReorder ? 'inline-flex' : 'none';
        if (titleEl) {
            titleEl.classList.toggle('mr-10', canReorder);
        }
    },

    setupHierarchyReorder() {
        if (typeof ManualReorder === 'undefined') return;

        if (!this._hierarchyReorder) {
            this._hierarchyReorder = new ManualReorder({
                dragClasses: ['opacity-30'],
                sections: [
                    {
                        name: window.i18n.t('media.relations.title'),
                        grid: () => this.el('hierarchy-media'),
                        itemSelector: '.gallery-item',
                        idExtractor: (el) => parseInt(el.dataset.id),
                        saveEndpoint: `/api/media/${this.mediaId}/children/reorder`,
                        clearEndpoint: `/api/media/${this.mediaId}/children/reorder`,
                        savePayloadKey: 'media_ids'
                    }
                ],
                onActivate: () => {
                    const content = this.el('hierarchy-media-content');
                    const chevron = this.el('hierarchy-media-chevron');
                    if (content && content.style.display === 'none') {
                        content.style.display = 'block';
                        if (chevron) chevron.style.transform = 'rotate(180deg)';
                    }
                    if (this.tooltipHelper && typeof this.tooltipHelper.hide === 'function') {
                        this.tooltipHelper.hide();
                    }
                },
                onSaveSuccess: async () => {
                    await this.reloadHierarchy();
                },
                onClearSuccess: async () => {
                    await this.reloadHierarchy();
                },
                onCancel: () => {
                    this.renderHierarchy(this.currentMedia?.hierarchy || []);
                }
            });
        }

        const editOrderBtn = this.el('hierarchy-edit-order-btn');
        if (editOrderBtn && editOrderBtn.dataset.reorderBound !== 'true') {
            editOrderBtn.dataset.reorderBound = 'true';
            editOrderBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.activateHierarchyReorder();
            });
        }
    },

    activateHierarchyReorder() {
        this.setupHierarchyReorder();
        if (this._hierarchyReorder && !this._hierarchyReorder.isActive) {
            this.el('hierarchy-media-section')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            this._hierarchyReorder.activate();
        }
    },

    async reloadHierarchy() {
        try {
            const res = await fetch(`/api/media/${this.mediaId}`);
            if (!res.ok) return;
            const updated = await res.json();
            this.currentMedia = updated;
            this.relationChildIds = new Set();
            if (this.currentMedia.hierarchy && !this.currentMedia.parent_id) {
                this.currentMedia.hierarchy.forEach(item => this.relationChildIds.add(item.id));
            }
            await this.renderHierarchy(this.currentMedia.hierarchy);
            this.renderRelationStatusDisplay();
        } catch (e) {
            console.error('Error reloading hierarchy:', e);
        }
    },

    setupHierarchyToggle() {
        const toggle = this.el('hierarchy-media-toggle');
        const content = this.el('hierarchy-media-content');

        if (!toggle || !content) return;

        // Reset display if needed (default to visible)
        content.style.display = 'block';

        const newToggle = toggle.cloneNode(true);
        toggle.parentNode.replaceChild(newToggle, toggle);

        const liveChevron = newToggle.querySelector('#hierarchy-media-chevron');
        if (liveChevron) {
            liveChevron.style.transform = content.style.display === 'none' ? 'rotate(0deg)' : 'rotate(180deg)';
        }

        newToggle.addEventListener('click', () => {
            if (document.body.classList.contains('reorder-active-mode')) return;
            const isHidden = content.style.display === 'none';
            content.style.display = isHidden ? 'block' : 'none';
            if (liveChevron) {
                liveChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });
    },

    setupCarousel() {
        this._setupHorizontalCarousel(
            this.el('hierarchy-media'),
            this.el('hierarchy-prev-btn'),
            this.el('hierarchy-next-btn')
        );
    },

    _setupHorizontalCarousel(container, prevBtn, nextBtn) {
        if (!container) return;

        // Prevent native drag on images and links within the carousel
        container.querySelectorAll('a, img').forEach(el => {
            el.draggable = false;
        });

        const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const scrollBehavior = prefersReducedMotion ? 'auto' : 'smooth';

        // Update buttons visibility and redirect focus if the focused control becomes disabled
        const updateButtons = () => {
            const prevDisabled = container.scrollLeft <= 0;
            const nextDisabled = container.scrollLeft + container.clientWidth >= container.scrollWidth - 1;

            if (prevBtn) {
                if (prevDisabled && document.activeElement === prevBtn && nextBtn && !nextDisabled) {
                    nextBtn.focus();
                }
                prevBtn.disabled = prevDisabled;
                prevBtn.style.pointerEvents = prevDisabled ? 'none' : 'auto';
            }
            if (nextBtn) {
                if (nextDisabled && document.activeElement === nextBtn && prevBtn && !prevDisabled) {
                    prevBtn.focus();
                }
                nextBtn.disabled = nextDisabled;
                nextBtn.style.pointerEvents = nextDisabled ? 'none' : 'auto';
            }
        };

        if (prevBtn) {
            prevBtn.onclick = () => {
                container.scrollBy({ left: -300, behavior: scrollBehavior });
            };
        }

        if (nextBtn) {
            nextBtn.onclick = () => {
                container.scrollBy({ left: 300, behavior: scrollBehavior });
            };
        }

        if (container._carouselUpdateButtons) {
            container.removeEventListener('scroll', container._carouselUpdateButtons);
            window.removeEventListener('resize', container._carouselUpdateButtons);
        }
        container._carouselUpdateButtons = updateButtons;
        container.addEventListener('scroll', updateButtons);
        window.addEventListener('resize', updateButtons);
        setTimeout(updateButtons, 100);

        if (container.dataset.carouselBound === 'true') {
            return;
        }
        container.dataset.carouselBound = 'true';

        // Click & Drag logic
        let isDown = false;
        let startX;
        let scrollLeft;
        let hasDragged = false;
        const dragThreshold = 5;

        container.addEventListener('mousedown', (e) => {
            if (document.body.classList.contains('reorder-active-mode')) return;
            isDown = true;
            hasDragged = false;
            container.classList.add('grabbing');
            startX = e.pageX - container.offsetLeft;
            scrollLeft = container.scrollLeft;
        });

        container.addEventListener('mouseleave', () => {
            isDown = false;
            container.classList.remove('grabbing');
        });

        container.addEventListener('mouseup', () => {
            isDown = false;
            container.classList.remove('grabbing');
        });

        container.addEventListener('mousemove', (e) => {
            if (!isDown || document.body.classList.contains('reorder-active-mode')) return;
            e.preventDefault();
            const x = e.pageX - container.offsetLeft;
            const walk = x - startX;

            if (Math.abs(walk) > dragThreshold) {
                hasDragged = true;
            }

            container.scrollLeft = scrollLeft - walk;
        });

        // Prevent click navigation if user was dragging
        container.addEventListener('click', (e) => {
            if (hasDragged) {
                e.preventDefault();
                e.stopPropagation();
                hasDragged = false;
            }
        }, true);
    },

    // ==================== Relation Manager Methods ====================

    setupRelationManager() {
        this.renderRelationStatusDisplay();

        // Track current children IDs for badge/removal functionality
        this.relationChildIds = new Set();
        if (this.currentMedia.hierarchy) {
            this.currentMedia.hierarchy.forEach(item => {
                if (!this.currentMedia.parent_id) {
                    this.relationChildIds.add(item.id);
                }
            });
        }

        this.el('manage-relations-btn')?.addEventListener('click', () => {
            this.openRelationModal();
        });
    },

    renderRelationStatusDisplay() {
        const container = this.el('relation-status-display');
        if (!container) return;

        const hasParent = !!this.currentMedia.parent_id;
        const hasChildren = this.currentMedia.has_children;
        const childCount = this.currentMedia.hierarchy?.length || 0;

        if (hasParent) {
            container.innerHTML = `
                <div class="flex items-center justify-between">
                    <span class="text-xs">${window.i18n.t('media.relations.parent_label')} <a href="/media/${this.currentMedia.parent_id}" class="hover:text-primary">${window.i18n.t('media.relations.parent_id_link', { id: this.currentMedia.parent_id })}</a></span>
                </div>
            `;
        } else if (hasChildren) {
            container.innerHTML = `
                <span class="text-xs">${childCount === 1 ? window.i18n.t('media.relations.children_count', { count: childCount }) : window.i18n.t('media.relations.children_count_plural', { count: childCount })}</span>
            `;
        } else {
            container.innerHTML = `<p class="text-xs text-secondary">${window.i18n.t('media.relations.no_relations')}</p>`;
        }
    },

    _buildRelationStatusHtml() {
        const hasParent = !!this.currentMedia.parent_id;
        const hasChildren = this.currentMedia.has_children;
        const childCount = this.relationChildIds.size;

        const infoIcon = window.Icons.infoCircle({ class: 'inline-block w-4 h-4 mr-1' });

        if (hasParent) {
            return `
                <div class="flex items-center justify-between flex-wrap gap-2">
                    <div>
                        <span class="font-medium">${window.i18n.t('media.relations.current_parent_label')}</span>
                        <a href="/media/${this.currentMedia.parent_id}" target="_blank" class="text-primary hover:underline ml-1">
                            ID ${this.currentMedia.parent_id}
                        </a>
                    </div>
                    <button id="relation-remove-parent-btn" class="btn-danger px-3 py-1 cursor-pointer">
                        ${window.i18n.t('media.relations.remove_parent_button')}
                    </button>
                </div>
                <p class="text-xs text-secondary mt-2">${infoIcon}${window.i18n.t('media.relations.info_has_parent')}</p>
            `;
        } else if (hasChildren) {
            return `
                <div class="flex items-center justify-between flex-wrap gap-2">
                    <span><span class="font-medium">${window.i18n.t('media.relations.children_label')}</span> ${childCount === 1 ? window.i18n.t('media.relations.children_items', { count: childCount }) : window.i18n.t('common.items_count', { count: childCount })}</span>
                    ${childCount > 1 ? `<button id="relation-reorder-children-btn" type="button" class="btn px-3 py-1 cursor-pointer">${window.i18n.t('gallery.sort_edit_order')}</button>` : ''}
                </div>
                <p class="text-xs text-secondary mt-2">${infoIcon}${window.i18n.t('media.relations.info_has_children')}</p>
            `;
        } else {
            return `<p class="text-secondary">${infoIcon}${window.i18n.t('media.relations.info_no_relations')}</p>`;
        }
    },

    openRelationModal() {
        const currentId = parseInt(this.mediaId);
        const isCurrentItemParent = this.currentMedia.has_children ||
            (this.currentMedia.hierarchy &&
                this.currentMedia.hierarchy.length > 0 &&
                !this.currentMedia.parent_id);

        // Build extra action buttons for relation management
        const extraButtons = [
            { id: 'relation-set-parent-btn', text: window.i18n.t('media.relations.set_parent'), className: 'btn-primary', onClick: () => this.setSelectedAsParent() },
            { id: 'relation-add-child-btn', text: window.i18n.t('media.relations.add_child'), className: 'btn-primary', onClick: () => this.addSelectedAsChildren() },
            { id: 'relation-add-children-btn', text: window.i18n.t('media.relations.add_children'), className: 'btn-primary', onClick: () => this.addSelectedAsChildren() },
            { id: 'relation-remove-children-btn', text: window.i18n.t('media.relations.remove_selected'), className: 'btn-danger', onClick: () => this.removeSelectedChildren() },
        ];

        // Destroy any previous picker instance
        if (this._relationPicker) {
            this._relationPicker.destroy();
        }

        this._relationPicker = new MediaPickerModal({
            title: window.i18n.t('media.relations.title'),
            mode: 'multi',
            excludeIds: [currentId],
            statusHtml: this._buildRelationStatusHtml(),
            extraButtons: extraButtons,
            confirmText: window.i18n.t('common.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            filterFn: (item) => {
                // Items already parented to someone else are not eligible
                if (item.parent_id && item.parent_id !== currentId) return false;
                // If current is a parent, other parents cannot become children
                if (isCurrentItemParent && item.has_children) return false;
                return true;
            },
            getInitialItems: async () => {
                return await this._getRelatedItemsForModal();
            },
            badgeFn: (media) => {
                const isParent = media.id === this.currentMedia.parent_id;
                const isChild = this.relationChildIds.has(media.id);
                if (isParent) return { text: window.i18n.t('media.relations.parent_badge'), className: 'bg-[var(--parent-outline)] tag-text' };
                if (isChild) return { text: window.i18n.t('media.relations.child_badge'), className: 'bg-[var(--child-outline)] tag-text' };
                return null;
            },
            showSelectionOrder: !this.currentMedia.parent_id,
            selectionOrderFilter: (id) => !this.relationChildIds.has(id),
            onCancel: () => { },
        });

        // Override the footer update to add relation-specific button logic
        const originalUpdateFooter = this._relationPicker._updateFooter.bind(this._relationPicker);
        this._relationPicker._updateFooter = () => {
            originalUpdateFooter();
            this._updateRelationActionButtons();
        };

        this._relationPicker.open();

        // Attach remove-parent listener in the status bar
        const removeParentBtn = this._relationPicker.root?.querySelector('#relation-remove-parent-btn');
        if (removeParentBtn) {
            removeParentBtn.addEventListener('click', () => this.removeParent());
        }

        // Attach reorder-children listener in the status bar
        const reorderChildrenBtn = this._relationPicker.root?.querySelector('#relation-reorder-children-btn');
        if (reorderChildrenBtn) {
            reorderChildrenBtn.addEventListener('click', () => {
                this.closeRelationModal();
                this.activateHierarchyReorder();
            });
        }
    },

    closeRelationModal() {
        if (this._relationPicker) {
            this._relationPicker.close();
        }
    },

    _updateRelationActionButtons() {
        const picker = this._relationPicker;
        if (!picker || !picker.root) return;

        const selectedCount = picker.selectedItems.size;
        const hasParent = !!this.currentMedia.parent_id;
        const hasChildren = this.currentMedia.has_children;

        const setParentBtn = picker.getButton('relation-set-parent-btn');
        const addChildBtn = picker.getButton('relation-add-child-btn');
        const addChildrenBtn = picker.getButton('relation-add-children-btn');
        const removeChildrenBtn = picker.getButton('relation-remove-children-btn');

        // Hide all first
        if (setParentBtn) setParentBtn.style.display = 'none';
        if (addChildBtn) addChildBtn.style.display = 'none';
        if (addChildrenBtn) addChildrenBtn.style.display = 'none';
        if (removeChildrenBtn) removeChildrenBtn.style.display = 'none';

        // Also hide the generic confirm button (relation manager uses its own buttons)
        const confirmBtn = picker.root.querySelector('.mpicker-confirm-btn');
        if (confirmBtn) confirmBtn.style.display = 'none';

        if (selectedCount === 0) return;

        const selectedIds = [...picker.selectedItems.keys()];
        const selectedChildIds = selectedIds.filter(id => this.relationChildIds.has(id));
        const nonChildSelected = selectedIds.filter(id => !this.relationChildIds.has(id));

        if (hasParent) {
            if (selectedCount === 1) {
                const selectedId = selectedIds[0];
                if (selectedId !== this.currentMedia.parent_id) {
                    if (setParentBtn) setParentBtn.style.display = 'block';
                }
            }
        } else if (hasChildren) {
            if (selectedChildIds.length > 0) {
                if (removeChildrenBtn) {
                    removeChildrenBtn.style.display = 'block';
                    removeChildrenBtn.textContent = window.i18n.t('media.relations.remove_children', { count: selectedChildIds.length });
                }
            }
            if (nonChildSelected.length > 0) {
                if (nonChildSelected.length === 1) {
                    if (addChildBtn) addChildBtn.style.display = 'block';
                } else {
                    if (addChildrenBtn) {
                        addChildrenBtn.style.display = 'block';
                        addChildrenBtn.textContent = window.i18n.t('media.relations.add_children_count', { count: nonChildSelected.length });
                    }
                }
            }
        } else {
            if (selectedCount === 1) {
                if (setParentBtn) setParentBtn.style.display = 'block';
                if (addChildBtn) addChildBtn.style.display = 'block';
            } else {
                if (addChildrenBtn) {
                    addChildrenBtn.style.display = 'block';
                    addChildrenBtn.textContent = window.i18n.t('media.relations.add_children_count', { count: selectedCount });
                }
            }
        }
    },

    async _getRelatedItemsForModal() {
        const items = [];
        const addedIds = new Set();
        const currentId = parseInt(this.mediaId);

        // Add hierarchy items first (parent/siblings or children)
        if (this.currentMedia.hierarchy) {
            this.currentMedia.hierarchy.forEach(item => {
                if (item.id !== currentId && !addedIds.has(item.id)) {
                    items.push(item);
                    addedIds.add(item.id);
                }
            });
        }

        // Add parent if exists
        if (this.currentMedia.parent_id && !addedIds.has(this.currentMedia.parent_id)) {
            try {
                const res = await fetch(`/api/media/${this.currentMedia.parent_id}`);
                if (res.ok) {
                    const parent = await res.json();
                    items.unshift(parent);
                    addedIds.add(parent.id);
                }
            } catch (e) {
                console.error('Error loading parent:', e);
            }
        }

        // Get related items using TF-IDF similarity
        try {
            const res = await fetch(`/api/media/${currentId}/related?limit=20`, {
                credentials: 'include'
            });
            if (res.ok) {
                const data = await res.json();
                (data.items || []).forEach(item => {
                    if (item.id !== currentId && !addedIds.has(item.id)) {
                        items.push(item);
                        addedIds.add(item.id);
                    }
                });
            }
        } catch (e) {
            console.error('Error loading related items for related media section:', e);
        }

        return items;
    },

    async setSelectedAsParent() {
        const picker = this._relationPicker;
        if (!picker || picker.selectedItems.size !== 1) return;

        const parentId = [...picker.selectedItems.keys()][0];

        try {
            await app.apiCall(`/api/media/${this.mediaId}`, {
                method: 'PATCH',
                body: JSON.stringify({ parent_id: parentId })
            });

            app.showNotification(window.i18n.t('notifications.media.parent_set'), 'success');
            this.closeRelationModal();
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('media.errors.setting_parent'));
        }
    },

    async addSelectedAsChildren() {
        const picker = this._relationPicker;
        if (!picker) return;

        const selectedIds = [...picker.selectedItems.keys()].filter(id =>
            !this.relationChildIds.has(id)
        );

        if (selectedIds.length === 0) return;

        try {
            for (const childId of selectedIds) {
                await app.apiCall(`/api/media/${childId}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ parent_id: parseInt(this.mediaId) })
                });
            }

            app.showNotification(selectedIds.length === 1 ? window.i18n.t('media.relations.added_children_success', { count: selectedIds.length }) : window.i18n.t('media.relations.added_children_success_plural', { count: selectedIds.length }), 'success');
            this.closeRelationModal();
            location.reload();
        } catch (e) {
            app.showNotification(e.message, 'error', window.i18n.t('media.errors.adding_children'));
        }
    },

    async removeSelectedChildren() {
        const picker = this._relationPicker;
        if (!picker) return;

        const selectedChildIds = [...picker.selectedItems.keys()].filter(id =>
            this.relationChildIds.has(id)
        );

        if (selectedChildIds.length === 0) return;

        const modal = new ModalHelper({
            id: 'remove-children-modal',
            type: 'warning',
            title: window.i18n.t('modal.remove_children.title'),
            message: window.i18n.t('modal.remove_children.message', { count: selectedChildIds.length }),
            confirmText: window.i18n.t('common.yes_remove'),
            cancelText: window.i18n.t('common.cancel'),
            onConfirm: async () => {
                try {
                    for (const childId of selectedChildIds) {
                        await app.apiCall(`/api/media/${childId}`, {
                            method: 'PATCH',
                            body: JSON.stringify({ parent_id: null })
                        });
                    }

                    app.showNotification(selectedChildIds.length === 1 ? window.i18n.t('media.relations.removed_children_success', { count: selectedChildIds.length }) : window.i18n.t('media.relations.removed_children_success_plural', { count: selectedChildIds.length }), 'success');
                    this.closeRelationModal();
                    location.reload();
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('media.errors.removing_children'));
                }
            }
        });
        modal.show();
    },

    async removeParent() {
        const modal = new ModalHelper({
            id: 'remove-parent-modal',
            type: 'warning',
            title: window.i18n.t('modal.remove_parent.title'),
            message: window.i18n.t('modal.remove_parent.message'),
            confirmText: window.i18n.t('common.yes_remove'),
            cancelText: window.i18n.t('common.cancel'),
            onConfirm: async () => {
                try {
                    await app.apiCall(`/api/media/${this.mediaId}`, {
                        method: 'PATCH',
                        body: JSON.stringify({ parent_id: null })
                    });

                    app.showNotification(window.i18n.t('notifications.media.parent_removed'), 'success');
                    this.closeRelationModal();
                    location.reload();
                } catch (e) {
                    app.showNotification(e.message, 'error', window.i18n.t('media.errors.removing_parent'));
                }
            }
        });
        modal.show();
    },
});
