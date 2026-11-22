// UploadMediaEditor near-duplicate relations and update-post integration
Object.assign(UploadMediaEditor.prototype, {
    renderNearDuplicatesHtml(item) {
        if (typeof NearDuplicateView === 'undefined') return '';
        return NearDuplicateView.renderPanel(item, this.session, NearDuplicateView._panelExpanded !== false);
    },

    getNearDuplicateHandlers() {
        return {
            onSelect: (itemId) => {
                if (this.options.onSelectItem) this.options.onSelectItem(itemId);
            },
            onRemove: (itemId) => this.removeQueuedItem(itemId),
            onUpdatePost: (target) => this.openUpdatePost(target),
            onRelate: (target, kind) => this.toggleRelation(target, kind),
        };
    },

    async toggleRelation(target, kind) {
        const itemId = this.activeItemId || Array.from(this.selectedIds)[0];
        const item = this.session.getItem(itemId);
        if (!item) return;

        try {
            if (target.kind === 'queue') {
                const liveTarget = this.session.getItem(target.item_id);
                if (!liveTarget) return;

                if (kind === 'child') {
                    const isAlreadyChild = item.parent_item_id === liveTarget.item_id;
                    await this.session.updateItem(itemId, {
                        parent_item_id: isAlreadyChild ? null : liveTarget.item_id,
                        parent_media_id: null,
                        child_media_ids: [],
                    }, { silent: true });
                } else if (kind === 'sibling') {
                    if (liveTarget.parent_media_id) {
                        const targetParentId = Number(liveTarget.parent_media_id);
                        const isAlreadySibling = Number(item.parent_media_id) === targetParentId;
                        await this.session.updateItem(itemId, {
                            parent_media_id: isAlreadySibling ? null : targetParentId,
                            parent_item_id: null,
                            child_media_ids: [],
                        }, { silent: true });
                    } else if (liveTarget.parent_item_id) {
                        const isAlreadySibling = item.parent_item_id === liveTarget.parent_item_id;
                        await this.session.updateItem(itemId, {
                            parent_item_id: isAlreadySibling ? null : liveTarget.parent_item_id,
                            parent_media_id: null,
                            child_media_ids: [],
                        }, { silent: true });
                    }
                } else if (kind === 'parent') {
                    const isAlreadyParent = liveTarget.parent_item_id === itemId;
                    await this.session.updateItem(liveTarget.item_id, {
                        parent_item_id: isAlreadyParent ? null : itemId,
                        parent_media_id: null,
                        child_media_ids: [],
                    }, { silent: true });
                }
            } else {
                let parent = item.parent_media_id || null;
                let children = (item.child_media_ids || []).map(Number);

                if (kind === 'child' || kind === 'sibling') {
                    const targetParentId = Number(kind === 'sibling' ? target.parent_id : target.media_id);
                    if (!targetParentId) return;
                    parent = parent === targetParentId ? null : targetParentId;
                    children = [];
                } else {
                    const targetId = Number(target.media_id);
                    parent = null;
                    children = children.includes(targetId) ? children.filter(id => id !== targetId) : [...children, targetId];
                }

                await this.session.updateItem(itemId, {
                    parent_media_id: parent,
                    parent_item_id: null,
                    child_media_ids: children,
                }, { silent: true });
            }
            this.refreshNearDuplicatesRelations();
        } catch (e) {
            if (window.app && typeof window.app.showNotification === 'function') {
                window.app.showNotification(e.message, 'error');
            }
        }
    },

    openUpdatePost(target) {
        const itemId = this.activeItemId || Array.from(this.selectedIds)[0];
        const item = this.session.getItem(itemId);
        if (!item || typeof UpdatePostUrlImport === 'undefined') return;

        const modal = new UpdatePostUrlImport(
            target.media_id,
            { width: target.width, height: target.height, filename: target.filename },
            {
                title: window.i18n.t('media.actions.update_post'),
                staged: { sessionId: this.session.sessionId, item, albums: this.allAlbums },
                onApplied: async () => {
                    await this.session.deleteItem(item.item_id);
                    if (this.options.onItemsDeleted) {
                        this.options.onItemsDeleted([item.item_id]);
                    }
                },
            }
        );
        modal.build(() => {
            modal.hide();
            document.body.style.overflow = '';
        });
    },

    removeQueuedItem(itemId) {
        const doDelete = () => {
            this.session.deleteItem(itemId);
            if (this.options.onItemsDeleted) {
                this.options.onItemsDeleted([itemId]);
            }
        };
        if (typeof ModalHelper !== 'undefined') {
            new ModalHelper({
                type: 'danger',
                title: window.i18n.t('upload.preview.remove_item_title'),
                message: window.i18n.t('upload.preview.remove_confirm'),
                confirmText: window.i18n.t('common.yes'),
                cancelText: window.i18n.t('common.cancel'),
                onConfirm: doDelete
            }).show();
        } else {
            doDelete();
        }
    },

    bindNearDuplicates(item) {
        if (typeof NearDuplicateView === 'undefined') return;
        const slot = this.container.querySelector('#editor-near-duplicates-slot');
        if (slot) NearDuplicateView.bindPanel(slot, item, this.session, this.getNearDuplicateHandlers());
    },

    refreshNearDuplicates() {
        if (this.selectedIds.size !== 1) return;
        const itemId = this.activeItemId || Array.from(this.selectedIds)[0];
        const item = this.session.getItem(itemId);
        const slot = this.container.querySelector('#editor-near-duplicates-slot');
        if (!item || !slot) return;
        const scroller = slot.querySelector('.nd-scroll');
        const scrollLeft = scroller ? scroller.scrollLeft : 0;
        const scrollY = window.scrollY;
        slot.innerHTML = this.renderNearDuplicatesHtml(item);
        this.bindNearDuplicates(item);
        const nextScroller = slot.querySelector('.nd-scroll');
        if (nextScroller && scrollLeft) nextScroller.scrollLeft = scrollLeft;
        if (window.scrollY !== scrollY) window.scrollTo(window.scrollX, scrollY);
    },

    refreshNearDuplicatesRelations() {
        if (this.selectedIds.size !== 1) return;
        const itemId = this.activeItemId || Array.from(this.selectedIds)[0];
        const item = this.session.getItem(itemId);
        const slot = this.container.querySelector('#editor-near-duplicates-slot');
        if (!item || !slot) return;
        if (typeof NearDuplicateView === 'undefined' || !NearDuplicateView.updateRelations(slot, item, this.session, this.getNearDuplicateHandlers())) {
            this.refreshNearDuplicates();
        }
    },
});
