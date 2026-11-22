class AdminContent {
    constructor(adminPanel) {
        this.app = adminPanel;
        this.isScanning = false;
        this.scanAbortController = null;
        this._scanOriginalText = null;
        this.registerMaintenanceJobs();
    }

    registerMaintenanceJobs() {
        const runner = window.maintenanceJobRunner;
        if (!runner) return;

        runner.register('near_duplicate_backfill', {
            startUrl: '/api/admin/near-duplicates/backfill',
            statusUrl: '/api/admin/near-duplicates',
            extractStatus: (data) => (data && data.backfill) || {},
            buttonId: 'near-duplicates-backfill-btn',
            statusDivId: 'near-duplicates-backfill-status',
            resultDivId: 'near-duplicates-backfill-result',
            startErrorMessage: () => window.i18n.t('admin.near_duplicates.error_start'),
            progressLabel: () => window.i18n.t('admin.near_duplicates.hashing'),
            progressStats: (backfill) => [
                [window.i18n.t('admin.maintenance.hashed'), backfill.hashed || 0],
                [window.i18n.t('admin.maintenance.failed'), backfill.failed || 0],
            ],
            renderProgress: (backfill) => {
                if (!backfill.total) return null;
                return runner.formatProgress(
                    window.i18n.t('admin.near_duplicates.hashing'),
                    { ...backfill, current: backfill.processed || 0 },
                    [
                        [window.i18n.t('admin.maintenance.hashed'), backfill.hashed || 0],
                        [window.i18n.t('admin.maintenance.failed'), backfill.failed || 0],
                    ]
                );
            },
            onComplete: (backfill) => {
                const message = backfill.total
                    ? window.i18n.t('admin.near_duplicates.done', {
                        hashed: backfill.hashed || 0,
                        failed: backfill.failed || 0,
                    })
                    : window.i18n.t('admin.near_duplicates.done_nothing');
                return { message, type: 'success' };
            },
        });

        runner.register('transcode_media', {
            startUrl: '/api/admin/transcode-media',
            statusUrl: '/api/admin/transcode-media/status',
            buttonId: 'transcode-media-btn',
            statusDivId: 'transcode-media-status',
            resultDivId: 'transcode-media-result',
            progressLabel: () => window.i18n.t('admin.media_management.maintenance.transcoding.transcoding'),
            progressStats: (status) => [
                [window.i18n.t('admin.maintenance.transcoded'), status.transcoded || 0],
                [window.i18n.t('admin.maintenance.skipped'), (status.skipped || 0) + (status.already_transcoded || 0)],
            ],
            onComplete: async (status) => {
                const finalStatus = status.last_result || status;
                const message = window.i18n.t('admin.media_management.maintenance.transcoding.done', {
                    transcoded: finalStatus.transcoded,
                    skipped: finalStatus.skipped + finalStatus.already_transcoded,
                    failed: finalStatus.failed,
                });
                await this.loadMediaStats();
                return { message, type: 'success' };
            },
        });

        runner.register('generate_missing_thumbnails', {
            startUrl: '/api/admin/generate-missing-thumbnails?background=true',
            statusUrl: '/api/admin/maintenance/status/generate_missing_thumbnails',
            buttonId: 'generate-missing-thumbnails-btn',
            disableButtonIds: ['regenerate-all-thumbnails-btn'],
            statusDivId: 'thumbnail-regen-status',
            resultDivId: 'thumbnail-regen-result',
            processingButtonText: () => window.i18n.t('admin.media_management.maintenance.thumbnails.generating'),
            progressLabel: () => window.i18n.t('admin.media_management.maintenance.thumbnails.generating'),
            progressStats: (status) => [
                [window.i18n.t('admin.maintenance.generated'), status.generated || 0],
                [window.i18n.t('admin.maintenance.skipped'), status.skipped || 0],
                [window.i18n.t('admin.maintenance.failed'), status.failed || 0],
            ],
            onComplete: (status) => {
                const result = status.result || status;
                const message = window.i18n.t('admin.media_management.maintenance.thumbnails.done_missing', {
                    orphans_deleted: result.orphans_deleted || 0,
                    generated: result.generated || 0,
                    skipped: result.skipped || 0,
                    failed: result.failed || 0,
                });
                return { message, type: 'success' };
            },
        });

        runner.register('regenerate_all_thumbnails', {
            startUrl: '/api/admin/regenerate-all-thumbnails?background=true',
            statusUrl: '/api/admin/maintenance/status/regenerate_all_thumbnails',
            buttonId: 'regenerate-all-thumbnails-btn',
            disableButtonIds: ['generate-missing-thumbnails-btn'],
            statusDivId: 'thumbnail-regen-status',
            resultDivId: 'thumbnail-regen-result',
            processingButtonText: () => window.i18n.t('admin.media_management.maintenance.thumbnails.generating'),
            progressLabel: () => window.i18n.t('admin.media_management.maintenance.thumbnails.generating'),
            progressStats: (status) => [
                [window.i18n.t('admin.maintenance.generated'), status.generated || 0],
                [window.i18n.t('admin.maintenance.failed'), status.failed || 0],
            ],
            onComplete: (status) => {
                const result = status.result || status;
                const message = window.i18n.t('admin.media_management.maintenance.thumbnails.done_all', {
                    deleted: result.deleted || 0,
                    generated: result.generated || 0,
                    failed: result.failed || 0,
                });
                return { message, type: 'success' };
            },
        });

        runner.register('relink_media', {
            startUrl: '/api/admin/relink-media?background=true',
            statusUrl: '/api/admin/maintenance/status/relink_media',
            buttonId: 'relink-media-btn',
            statusDivId: 'relink-media-status',
            resultDivId: 'relink-media-result',
            processingButtonText: () => window.i18n.t('admin.media_management.maintenance.relink.relinking'),
            progressLabel: () => window.i18n.t('admin.media_management.maintenance.relink.relinking'),
            progressStats: (status) => [
                [window.i18n.t('admin.maintenance.relinked'), status.relinked || 0],
                [window.i18n.t('admin.maintenance.remaining'), status.unresolved || 0],
            ],
            onComplete: async (status) => {
                const result = status.result || status;
                let msg = result.relinked > 0
                    ? window.i18n.t('admin.media_management.maintenance.relink.done_relinked', { count: result.relinked })
                    : window.i18n.t('admin.media_management.maintenance.relink.done_none');

                if (result.unresolved > 0) {
                    const unresolvedMsg = window.i18n.t('admin.media_management.maintenance.relink.unresolved_warning', { count: result.unresolved });
                    msg += ` ${unresolvedMsg}`;
                }

                if (result.relinked > 0) {
                    await this.loadMediaStats();
                }

                const type = result.relinked > 0 ? 'success' : (result.unresolved > 0 ? 'warning' : 'info');
                return { message: msg, type };
            },
        });

        runner.register('apply_aliases', {
            startUrl: '/api/admin/simulate-apply-aliases?background=true',
            statusUrl: '/api/admin/maintenance/status/apply_aliases',
            buttonId: 'apply-aliases-btn',
            statusDivId: 'apply-aliases-status',
            resultDivId: 'apply-aliases-result',
            progressLabel: () => window.i18n.t('admin.tags_management.apply_aliases_processing'),
            onComplete: (status) => {
                const affectedMedia = (status.result && status.result.affected_media) || [];
                if (affectedMedia.length === 0) {
                    return {
                        message: window.i18n.t('admin.tags_management.apply_aliases_no_affected'),
                        type: 'info',
                    };
                }
                if (typeof BulkManualTagEditorModal !== 'undefined') {
                    const affectedIds = affectedMedia.map((m) => m.media_id);
                    const prefillTags = {};
                    const removeTags = {};
                    affectedMedia.forEach((m) => {
                        if (m.added_tags && m.added_tags.length) {
                            prefillTags[m.media_id] = m.added_tags;
                        }
                        if (m.removed_tags && m.removed_tags.length) {
                            removeTags[m.media_id] = m.removed_tags;
                        }
                    });

                    const modal = new BulkManualTagEditorModal({
                        prefillTags,
                        removeTags,
                        onSave: async () => {
                            try {
                                await fetch('/api/admin/cleanup-aliased-tags', { method: 'POST' });
                            } catch (e) {
                                console.error('Error cleaning up aliased tags:', e);
                            }
                        },
                    });
                    modal.show(affectedIds);
                    return {
                        message: window.i18n.t('admin.maintenance.found_affected', { count: affectedMedia.length }),
                        type: 'success',
                    };
                }
                console.error('BulkManualTagEditorModal is not loaded');
                return {
                    message: `Found ${affectedMedia.length} affected media items, but bulk editor is not loaded.`,
                    type: 'error',
                };
            },
        });

        runner.register('apply_tag_ratings', {
            startUrl: '/api/admin/simulate-apply-tag-ratings?background=true',
            statusUrl: '/api/admin/maintenance/status/apply_tag_ratings',
            buttonId: 'apply-tag-ratings-btn',
            statusDivId: 'apply-tag-ratings-status',
            resultDivId: 'apply-tag-ratings-result',
            progressLabel: () => window.i18n.t('admin.tags_management.apply_tag_ratings_processing'),
            onComplete: (status) => {
                const affectedMedia = (status.result && status.result.affected_media) || [];
                if (affectedMedia.length === 0) {
                    return {
                        message: window.i18n.t('admin.tags_management.apply_tag_ratings_no_affected'),
                        type: 'info',
                    };
                }
                if (typeof BulkRatingModal !== 'undefined') {
                    const affectedIds = affectedMedia.map((m) => m.media_id);
                    const prefillRatings = {};
                    affectedMedia.forEach((m) => {
                        if (m.new_rating) {
                            prefillRatings[m.media_id] = m.new_rating;
                        }
                    });

                    const modal = new BulkRatingModal({
                        prefillRatings,
                        onSave: () => {
                            window.adminPanel.content.loadTagStats();
                        },
                    });
                    modal.show(affectedIds);
                    return {
                        message: window.i18n.t('admin.maintenance.found_affected', { count: affectedMedia.length }),
                        type: 'success',
                    };
                }
                console.error('BulkRatingModal is not loaded');
                return {
                    message: `Found ${affectedMedia.length} affected media items, but bulk rating editor is not loaded.`,
                    type: 'error',
                };
            },
        });

        runner.register('recalculate_album_metrics', {
            startUrl: '/api/albums/recalculate?background=true',
            statusUrl: '/api/admin/maintenance/status/recalculate_album_metrics',
            buttonId: 'recalculate-album-metrics-btn',
            statusDivId: 'recalculate-album-metrics-status',
            resultDivId: 'recalculate-album-metrics-result',
            initialProgressText: () => window.i18n.t('admin.albums_management.maintenance.recalculate_metrics_processing'),
            onComplete: async () => {
                await this.loadAlbumStats();
                if (this.albumTree) {
                    await this.albumTree.loadAlbums();
                    this.albumTree.render();
                }
                return {
                    message: window.i18n.t('admin.albums_management.maintenance.metrics_recalculated'),
                    type: 'success',
                };
            },
        });

        runner.register('prune_albums', {
            startUrl: '/api/albums/prune?background=true',
            statusUrl: '/api/admin/maintenance/status/prune_albums',
            buttonId: 'prune-albums-btn',
            statusDivId: 'prune-albums-status',
            resultDivId: 'prune-albums-result',
            initialProgressText: () => window.i18n.t('admin.albums_management.maintenance.prune_albums_processing'),
            onComplete: async (status) => {
                const result = status.result || {};
                await this.loadAlbumStats();
                if (this.albumTree) {
                    await this.albumTree.loadAlbums();
                    this.albumTree.render();
                }
                await this.loadAlbums();
                return {
                    message: window.i18n.t('admin.albums_management.maintenance.albums_pruned', {
                        count: result.count || 0,
                    }),
                    type: 'success',
                };
            },
        });
    }

    async checkMaintenanceStatuses() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.checkAll();
        }
    }

    cancelScan() {
        if (this.scanAbortController) {
            this.scanAbortController.abort();
            this.scanAbortController = null;
        }
        this.isScanning = false;
        const scanBtn = document.getElementById('scan-media-btn');
        if (scanBtn && this._scanOriginalText) {
            scanBtn.disabled = false;
            scanBtn.textContent = this._scanOriginalText;
        }
    }

    async scanMedia() {
        const scanBtn = document.getElementById('scan-media-btn');
        const originalText = scanBtn.textContent;
        this._scanOriginalText = originalText;
        this.isScanning = true;
        this.scanAbortController = new AbortController();
        const signal = this.scanAbortController.signal;

        scanBtn.disabled = true;
        scanBtn.textContent = window.i18n.t('admin.actions.scanning');

        try {
            const result = await app.apiCall('/api/admin/scan-media', {
                method: 'POST'
            });

            if (signal.aborted || (window.uploaderInstance?.isAborted?.())) {
                return;
            }

            if (result.new_files === 0) {
                app.showNotification(window.i18n.t('notifications.admin.no_untracked_media'), 'info');
                scanBtn.disabled = false;
                scanBtn.textContent = originalText;
                return;
            }

            // Show loading message
            scanBtn.textContent = window.i18n.t('admin.messages.scan_loading', { count: result.new_files });

            // Get the uploader instance
            const uploader = window.uploaderInstance;
            if (!uploader) {
                app.showNotification(window.i18n.t('notifications.admin.refresh_and_retry'), 'error', window.i18n.t('notifications.admin.uploader_not_initialized'));
                scanBtn.disabled = false;
                scanBtn.textContent = originalText;
                return;
            }

            // Fetch and add each file to the uploader
            let loadedCount = 0;
            let queuedCount = 0;
            let duplicateCount = 0;
            let skippedCount = 0;

            for (const filePath of result.files) {
                if (signal.aborted || uploader.isAborted?.()) {
                    break;
                }
                try {
                    // Check if file is already in the upload queue
                    if (uploader.isFileQueued(filePath)) {
                        queuedCount++;
                        continue;
                    }

                    scanBtn.textContent = window.i18n.t('admin.messages.scan_progress', { current: loadedCount + 1, total: result.new_files });

                    // Add to uploader
                    await uploader.addScannedFile(filePath, null, { signal });
                    if (signal.aborted || uploader.isAborted?.()) {
                        break;
                    }
                    loadedCount++;

                } catch (error) {
                    if (error.name === 'AbortError' || signal.aborted || uploader.isAborted?.()) {
                        break;
                    }
                    if (uploader.isDuplicateError?.(error)) {
                        console.warn(`File ${filePath} is a duplicate, skipping:`, error);
                        duplicateCount++;
                    } else {
                        console.error(`Error loading file ${filePath}:`, error);
                        skippedCount++;
                        if (uploader.isSystemicError?.(error)) {
                            break;
                        }
                    }
                }
            }

            if (signal.aborted || uploader.isAborted?.()) {
                return;
            }

            // Show results
            const messages = [];
            if (loadedCount > 0) {
                messages.push(window.i18n.t('admin.messages.scan_loaded', { count: loadedCount }));
            }
            if (queuedCount > 0) {
                messages.push(window.i18n.t('admin.messages.scan_queued', { count: queuedCount }));
            }
            if (duplicateCount > 0) {
                messages.push(window.i18n.t('upload.progress.duplicates_skipped', { count: duplicateCount }));
            }
            if (skippedCount > 0) {
                messages.push(window.i18n.t('admin.messages.scan_skipped', { count: skippedCount }));
            }
            if (loadedCount > 0) {
                messages.push('\n' + window.i18n.t('admin.messages.scan_ready_hint'));
            }

            const message = messages.join('\n');
            const notificationType = loadedCount > 0 ? 'success' : ((duplicateCount > 0 || queuedCount > 0) ? 'info' : 'warning');
            app.showNotification(message, notificationType);

        } catch (error) {
            if (error.name === 'AbortError' || signal.aborted || (window.uploaderInstance?.isAborted?.())) {
                return;
            }
            console.error('Scan error:', error);
            app.showNotification(error.message, 'error', window.i18n.t('notifications.admin.error_scanning_media'));
        } finally {
            this.isScanning = false;
            this.scanAbortController = null;
            scanBtn.disabled = false;
            scanBtn.textContent = originalText;
        }
    }

    async generateMissingThumbnails() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.start('generate_missing_thumbnails');
        }
    }

    async regenerateAllThumbnails() {
        const modal = new ModalHelper({
            id: 'regenerate-thumbnails-modal',
            type: 'danger',
            title: window.i18n.t('modal.regenerate_thumbnails.title'),
            message: window.i18n.t('modal.regenerate_thumbnails.message'),
            confirmText: window.i18n.t('modal.regenerate_thumbnails.confirm'),
            cancelText: window.i18n.t('common.cancel'),
            confirmId: 'regenerate-thumbnails-confirm-yes',
            cancelId: 'regenerate-thumbnails-confirm-no',
            onConfirm: async () => {
                if (window.maintenanceJobRunner) {
                    await window.maintenanceJobRunner.start('regenerate_all_thumbnails');
                }
            }
        });

        modal.show();
    }

    async relinkMedia() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.start('relink_media');
        }
    }

    async checkTranscodeStatus() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.checkJob('transcode_media');
        }
    }

    async pollTranscodeJob() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.poll('transcode_media');
        }
    }

    async transcodeMedia() {
        if (window.maintenanceJobRunner) {
            await window.maintenanceJobRunner.start('transcode_media');
        }
    }

    async loadMediaStats() {
        try {
            const response = await fetch('/api/admin/media-stats');
            const stats = await response.json();

            const totalMediaEl = document.getElementById('total-media');
            const totalImagesEl = document.getElementById('total-images');
            const totalGifsEl = document.getElementById('total-gifs');
            const totalVideosEl = document.getElementById('total-videos');

            if (totalMediaEl) totalMediaEl.textContent = stats.total_media;
            if (totalImagesEl) totalImagesEl.textContent = stats.total_images;
            if (totalGifsEl) totalGifsEl.textContent = stats.total_gifs;
            if (totalVideosEl) totalVideosEl.textContent = stats.total_videos;
        } catch (error) {
            console.error('Error loading media stats:', error);
        }
    }
}
