class UploadSession {
    constructor() {
        this.sessionId = null;
        this.items = new Map();
        this.isUploading = false;
        this.isCommitting = false;
        this.isCancelling = false;
        this.sessionAbortController = new AbortController();
        this.listeners = {
            itemAdded: [],
            itemUpdated: [],
            itemRemoved: [],
            pendingChanged: [],
            sessionCleared: [],
            statusChanged: [],
        };

        window.addEventListener('beforeunload', () => {
            if (this.sessionId && !this.isCommitting && this.items.size > 0) {
                // Use keepalive fetch to clean up session on page reload/close
                fetch(`/api/uploads/sessions/${this.sessionId}`, {
                    method: 'DELETE',
                    keepalive: true
                }).catch(() => { });
            }
        });
    }

    _getSignal(options = {}) {
        const optionSignal = options.signal;
        const sessionSignal = this.sessionAbortController?.signal;

        if (optionSignal && sessionSignal) {
            if (typeof AbortSignal.any === 'function') {
                return AbortSignal.any([optionSignal, sessionSignal]);
            }
            if (optionSignal.aborted) return optionSignal;
            if (sessionSignal.aborted) return sessionSignal;
            const controller = new AbortController();
            const onAbort = () => controller.abort();
            optionSignal.addEventListener('abort', onAbort, { once: true });
            sessionSignal.addEventListener('abort', onAbort, { once: true });
            return controller.signal;
        }
        return optionSignal || sessionSignal;
    }

    abortPendingOperations() {
        if (this.sessionAbortController) {
            this.sessionAbortController.abort();
            this.sessionAbortController = new AbortController();
        }
    }

    on(event, callback) {
        if (this.listeners[event]) {
            this.listeners[event].push(callback);
        }
    }

    emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(cb => {
                try {
                    cb(data);
                } catch (e) {
                    console.error(`Error in upload session event listener for ${event}:`, e);
                }
            });
        }
    }

    async ensureSession(options = {}) {
        if (this.isCancelling) {
            throw new DOMException('Upload session is being cancelled', 'AbortError');
        }
        if (this.sessionId) return this.sessionId;

        const signal = this._getSignal(options);
        const response = await fetch('/api/uploads/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: signal,
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to create upload session');
        }

        const data = await response.json();
        this.sessionId = data.session_id;
        return this.sessionId;
    }

    async uploadFile(file, options = {}) {
        if (this.isCancelling || options.signal?.aborted) {
            throw new DOMException('Upload operation aborted', 'AbortError');
        }
        await this.ensureSession(options);
        if (this.isCancelling || options.signal?.aborted) {
            throw new DOMException('Upload operation aborted', 'AbortError');
        }

        const formData = new FormData();
        formData.append('file', file, file.name);

        if (options.relativePath) {
            formData.append('relative_path', options.relativePath);
        }
        if (options.folderMappingMode) {
            formData.append('folder_mapping_mode', options.folderMappingMode);
        }
        if (options.baseRating) {
            formData.append('base_rating', options.baseRating);
        }
        if (options.baseSource) {
            formData.append('base_source', options.baseSource);
        }
        if (options.baseTags) {
            formData.append('base_tags', options.baseTags);
        }
        if (options.baseAlbumIds && options.baseAlbumIds.length > 0) {
            formData.append('base_album_ids', options.baseAlbumIds.join(','));
        }
        if (options.baseDescription) {
            formData.append('base_description', options.baseDescription);
        }
        if (options.sidecar) {
            formData.append('sidecar', options.sidecar, options.sidecar.name);
        }
        if (options.categoryHints) {
            formData.append('category_hints', JSON.stringify(options.categoryHints));
        }
        if (options.userAssignedTags) {
            formData.append('user_assigned_tags', JSON.stringify(options.userAssignedTags));
        }

        const signal = this._getSignal(options);
        const response = await fetch(`/api/uploads/sessions/${this.sessionId}/files`, {
            method: 'POST',
            body: formData,
            signal: signal,
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Failed to upload file ${file.name}`);
        }

        const item = await response.json();
        if (this.isCancelling || options.signal?.aborted) {
            return null;
        }
        this.items.set(item.item_id, item);
        this.emit('itemAdded', item);
        return item;
    }

    async addUntrackedFile(filePath, options = {}) {
        if (this.isCancelling || options.signal?.aborted) {
            throw new DOMException('Upload operation aborted', 'AbortError');
        }
        await this.ensureSession(options);
        if (this.isCancelling || options.signal?.aborted) {
            throw new DOMException('Upload operation aborted', 'AbortError');
        }

        const payload = {
            file_path: filePath,
            relative_path: options.relativePath || null,
            base_rating: options.baseRating || null,
            base_source: options.baseSource || null,
            base_tags: options.baseTags || null,
            base_album_ids: options.baseAlbumIds ? options.baseAlbumIds.join(',') : null,
            base_description: options.baseDescription || null,
            category_hints: options.categoryHints ? JSON.stringify(options.categoryHints) : null,
            user_assigned_tags: options.userAssignedTags ? JSON.stringify(options.userAssignedTags) : null,
        };

        const signal = this._getSignal(options);
        const response = await fetch(`/api/uploads/sessions/${this.sessionId}/untracked-files`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: signal,
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Failed to add untracked file ${filePath}`);
        }

        const item = await response.json();
        if (this.isCancelling || options.signal?.aborted) {
            return null;
        }
        this.items.set(item.item_id, item);
        this.emit('itemAdded', item);
        return item;
    }

    async analyzeItem(itemId, categoryHints = null) {
        if (!this.sessionId) return null;

        let url = `/api/uploads/sessions/${this.sessionId}/items/${itemId}/analyze`;
        if (categoryHints) {
            url += `?category_hints=${encodeURIComponent(JSON.stringify(categoryHints))}`;
        }

        const response = await fetch(url, {
            method: 'POST',
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to analyze item');
        }

        const updated = await response.json();
        this.items.set(itemId, updated);
        this.emit('itemUpdated', updated);
        return updated;
    }

    async updateItem(itemId, updateData, { silent = false } = {}) {
        if (!this.sessionId) return null;

        const response = await fetch(`/api/uploads/sessions/${this.sessionId}/items/${itemId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to update item');
        }

        const updated = await response.json();
        this.items.set(itemId, updated);
        if (!silent) {
            this.emit('itemUpdated', updated);
        }
        return updated;
    }

    async bulkUpdate(itemIds, updateData, options = { silent: false }) {
        if (!this.sessionId || !itemIds || itemIds.length === 0) return [];

        const payload = {
            item_ids: itemIds,
            rating: updateData.rating || null,
            source: updateData.source !== undefined ? updateData.source : null,
            description: updateData.description !== undefined ? updateData.description : null,
            album_ids: updateData.album_ids || null,
            add_album_ids: updateData.add_album_ids || null,
            remove_album_ids: updateData.remove_album_ids || null,
            add_tags: updateData.add_tags || null,
            remove_tag_names: updateData.remove_tag_names || null,
        };
        if (updateData.suggested_album_path !== undefined) {
            payload.suggested_album_path = updateData.suggested_album_path;
        }

        const response = await fetch(`/api/uploads/sessions/${this.sessionId}/items/bulk-update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            let msg = 'Failed to bulk update items';
            if (typeof err.detail === 'string') {
                msg = err.detail;
            } else if (Array.isArray(err.detail)) {
                msg = err.detail.map(d => `${d.loc?.join('.') || 'field'}: ${d.msg}`).join('; ');
            }
            throw new Error(msg);
        }

        const result = await response.json();
        if (result.items) {
            result.items.forEach(it => {
                this.items.set(it.item_id, it);
                if (!options.silent) {
                    this.emit('itemUpdated', it);
                }
            });
        }
        return result.items || [];
    }

    async deleteItem(itemId) {
        if (!this.sessionId) return;

        const response = await fetch(`/api/uploads/sessions/${this.sessionId}/items/${itemId}`, {
            method: 'DELETE',
        });

        if (response.ok) {
            this.items.delete(itemId);
            this.emit('itemRemoved', itemId);
            if (this.items.size === 0) {
                this.sessionId = null;
                this.emit('sessionCleared', null);
            }
        }
    }

    async fetchPendingEntities() {
        if (!this.sessionId) return { pending_tags: [], pending_albums: [] };

        const response = await fetch(`/api/uploads/sessions/${this.sessionId}/pending`);
        if (!response.ok) {
            return { pending_tags: [], pending_albums: [] };
        }

        const data = await response.json();
        this.emit('pendingChanged', data);
        return data;
    }

    async updatePendingTag(tagName, updateData) {
        if (!this.sessionId) return;

        const response = await fetch(`/api/uploads/sessions/${this.sessionId}/pending/tags/${encodeURIComponent(tagName)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to update pending tag');
        }

        // Refresh session items state
        await this.refreshSession();
        return await this.fetchPendingEntities();
    }

    async updatePendingAlbum(path, updateData) {
        if (!this.sessionId) return;

        const response = await fetch(`/api/uploads/sessions/${this.sessionId}/pending/albums`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: path,
                ...updateData
            }),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to update pending album');
        }

        await this.refreshSession();
        return await this.fetchPendingEntities();
    }

    async setFolderMapping(enabled, rootMode = 'use_root') {
        if (!this.sessionId) return;

        const response = await fetch(`/api/uploads/sessions/${this.sessionId}/folder-mapping`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                enabled: !!enabled,
                root_mode: rootMode
            }),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to update folder mapping');
        }

        await this.refreshSession();
        return await this.fetchPendingEntities();
    }

    async refreshSession() {
        if (!this.sessionId) return;

        const response = await fetch(`/api/uploads/sessions/${this.sessionId}`);
        if (response.ok) {
            const data = await response.json();
            this.items.clear();
            (data.items || []).forEach(it => {
                this.items.set(it.item_id, it);
                this.emit('itemUpdated', it);
            });
        }
    }

    async commit() {
        if (!this.sessionId || this.items.size === 0) {
            throw new Error('No items in upload session to commit');
        }

        this.isCommitting = true;
        this.emit('statusChanged', { isCommitting: true });

        try {
            const response = await fetch(`/api/uploads/sessions/${this.sessionId}/commit`, {
                method: 'POST',
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || 'Failed to commit upload session');
            }

            const result = await response.json();
            this.items.clear();
            this.sessionId = null;
            this.emit('sessionCleared', result);
            return result;
        } finally {
            this.isCommitting = false;
            this.emit('statusChanged', { isCommitting: false });
        }
    }

    async cancelSession() {
        this.isCancelling = true;
        this.abortPendingOperations();

        const targetSessionId = this.sessionId;
        this.sessionId = null;
        this.items.clear();
        this.emit('sessionCleared', null);

        if (targetSessionId) {
            try {
                await fetch(`/api/uploads/sessions/${targetSessionId}`, {
                    method: 'DELETE',
                });
            } catch (e) {
                console.warn('Error deleting upload session:', e);
            }
        }
        this.isCancelling = false;
    }

    getItem(itemId) {
        return this.items.get(itemId);
    }

    getAllItems() {
        return Array.from(this.items.values());
    }

    getItemCount() {
        return this.items.size;
    }
}

window.UploadSession = UploadSession;
