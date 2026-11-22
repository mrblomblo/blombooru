// BaseGallery popular tags sidebar and gallery/album card rendering
Object.assign(BaseGallery.prototype, {
    // ==================== Popular Tags ====================

    processTagCounts(items) {
        items.forEach(item => {
            if (item.tags && Array.isArray(item.tags)) {
                item.tags.forEach(tag => {
                    const currentCount = this.tagCounts.get(tag.name) || { count: 0, category: tag.category };
                    this.tagCounts.set(tag.name, {
                        count: currentCount.count + 1,
                        category: tag.category
                    });
                });
            }
        });
    },

    renderPopularTags(tags = null) {
        if (!this.elements.popularTags) return;

        let sortedTags;

        if (tags) {
            // Handle both array of objects and array of [name, data] tuples
            if (Array.isArray(tags) && tags.length > 0) {
                if (Array.isArray(tags[0])) {
                    // Already in tuple format: [[name, {count, category}], ...]
                    sortedTags = tags;
                } else {
                    // Object format: [{name, count/post_count, category}, ...]
                    sortedTags = tags.map(t => [
                        t.name,
                        { count: t.count || t.post_count || 0, category: t.category || 'general' }
                    ]);
                }
            } else {
                sortedTags = [];
            }
        } else {
            sortedTags = Array.from(this.tagCounts.entries())
                .sort((a, b) => b[1].count - a[1].count)
                .slice(0, this.popularTagsLimit || 20);
        }

        if (sortedTags.length === 0) {
            this.elements.popularTags.innerHTML = `<p class="text-secondary">${window.i18n.t('gallery.no_tags_found')}</p>`;
            return;
        }

        const currentParams = new URLSearchParams(window.location.search);
        const currentQuery = currentParams.get('q') || '';
        const currentTags = currentQuery.split(/\s+/).filter(t => t.length > 0);

        this.elements.popularTags.innerHTML = sortedTags.map(([tagName, data]) => {
            const isInQuery = currentTags.includes(tagName);
            const newQuery = isInQuery ? currentQuery :
                (currentQuery ? `${currentQuery} ${tagName}` : tagName);

            const params = new URLSearchParams(window.location.search);
            params.set('q', newQuery);
            params.delete('page');

            return `
                <div class="${isInQuery ? 'popular-tag-item opacity-50' : 'popular-tag-item'}">
                    <a href="/?${params.toString()}" class="popular-tag-name tag ${data.category || 'general'} tag-text" 
                       ${isInQuery ? 'style="pointer-events: none;"' : ''}>
                        ${tagName}
                        <span class="popular-tag-count">${data.count}</span>
                    </a>
                </div>
            `;
        }).join('');
    },

    // ==================== Related Tags / Tags Section ====================

    async refreshTagsSection() {
        const urlParams = new URLSearchParams(window.location.search);
        const searchQuery = (urlParams.get('q') || '').trim();
        const useRelated = (this.popularTagsMode === 'search_related') && searchQuery !== '';

        // Update the section title dynamically
        const titleEl = document.getElementById('popular-tags-title');
        if (titleEl) {
            titleEl.textContent = useRelated
                ? window.i18n.t('gallery.related_tags')
                : window.i18n.t('gallery.popular_tags');
        }

        if (useRelated) {
            await this._fetchRelatedTags(searchQuery);
        } else {
            this.renderPopularTags();
        }
    },

    async _fetchRelatedTags(query) {
        if (!this.elements.popularTags) return;

        this.elements.popularTags.innerHTML =
            `<p class="text-secondary">${window.i18n.t('common.loading')}</p>`;

        try {
            const params = new URLSearchParams({
                q: query,
                limit: this.popularTagsLimit || 20,
            });
            if (this.currentRating) {
                params.set('rating', this.currentRating);
            }
            if (this.selectedCustomFilters && this.selectedCustomFilters.size > 0) {
                this.selectedCustomFilters.forEach(cf => params.append('custom_filter', cf));
            }
            const res = await fetch(`/api/tags/search-related?${params.toString()}`, {
                credentials: 'include'
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.renderPopularTags(data);
        } catch (err) {
            console.error('Error fetching related tags:', err);
            // Fallback to current-page tags
            this.renderPopularTags();
        }
    },

    // ==================== Gallery Item Creation ====================

    createAlbumCard(album) {
        const thumbnails = album.thumbnail_paths || [];
        const ratings = album.thumbnail_ratings || [];
        const shouldBlur = window.shouldBlurExplicit();
        let thumbnailHTML;

        if (thumbnails.length >= 4) {
            thumbnailHTML = `
                <div class="relative aspect-square overflow-hidden w-full">
                    <div class="grid grid-cols-2 gap-0.5 w-full h-full">
                        ${thumbnails.slice(0, 4).map((thumb, idx) => {
                const isExplicit = ratings[idx] === 'explicit' && shouldBlur;
                return `
                            <div class="relative overflow-hidden w-full h-full aspect-square ${isExplicit ? 'album-thumb-blur' : ''}">
                                <img src="${thumb}" class="absolute inset-0 w-full h-full object-cover" loading="lazy" 
                                    onerror="this.src='/static/images/no-thumbnail.png'">
                            </div>
                            `;
            }).join('')}
                    </div>
                </div>
            `;
        } else if (thumbnails.length > 0) {
            const isExplicit = ratings[0] === 'explicit' && shouldBlur;
            thumbnailHTML = `
                <div class="relative aspect-square overflow-hidden w-full ${isExplicit ? 'album-thumb-blur' : ''}">
                    <img src="${thumbnails[0]}" class="absolute inset-0 w-full h-full object-cover" loading="lazy" 
                        onerror="this.src='/static/images/no-thumbnail.png'">
                </div>
            `;
        } else {
            thumbnailHTML = `
                <div class="relative aspect-square surface-light flex items-center justify-center overflow-hidden w-full">
                    <img src="/static/images/no-thumbnail.png" class="absolute inset-0 w-full h-full object-cover" loading="lazy">
                </div>
            `;
        }

        return `
            <a href="/album/${album.id}" data-id="${album.id}" class="album-card block surface border hover:border-primary focus:border-primary focus:outline-none transition-colors">
                ${thumbnailHTML}
                <div class="p-2 border-t">
                    <div class="text-xs font-bold truncate mb-1">${escapeHtml(album.name)}</div>
                    <div class="flex justify-between items-center text-xs text-secondary">
                        <span>${window.i18n.t('common.items_count', { count: album.media_count || 0 })}</span>
                        <span>${album.rating[0].toUpperCase()}</span>
                    </div>
                </div>
            </a>
        `;
    },

    createGalleryItem(media, options = {}) {
        const {
            checkboxClass = 'checkbox',
            preserveQueryParams = true,
            linkUrl = null
        } = options;

        const item = document.createElement('div');
        item.className = `gallery-item ${media.file_type}`;
        if (media.parent_id) item.classList.add('child-item');
        if (media.has_children) item.classList.add('parent-item');
        item.dataset.id = media.id;
        item.dataset.rating = media.rating;

        // Hidden checkbox
        let checkbox = null;
        let indicator = null;

        if (app.isAdminMode) {
            checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = `select-checkbox ${checkboxClass}`;
            checkbox.dataset.id = media.id;
            checkbox.tabIndex = -1; // Not focusable

            // Custom visual indicator (the clickable circle)
            indicator = document.createElement('div');
            indicator.className = 'select-indicator primary-text';
            indicator.innerHTML = window.Icons.check({ size: 24 });

            if (this.selectedItems.has(media.id)) {
                checkbox.checked = true;
                item.classList.add('selected');
            }

            indicator.addEventListener('click', (e) => {
                if (document.body.classList.contains('reorder-active-mode')) return;
                e.preventDefault();
                e.stopPropagation();
                this.toggleItemSelection(item, media.id, e);
            });
        }

        // ==================== Drag Selection Events ====================

        // Start drag on mousedown
        if (app.isAdminMode) {
            item.addEventListener('mousedown', (e) => {
                if (document.body.classList.contains('reorder-active-mode')) return;
                if (e.button === 0) {
                    if (this.isSelectionMode) {
                        e.preventDefault();
                        this.handleMouseDown(item, media.id);
                    }
                }
            });
        }

        // Continue drag on mouseenter
        item.addEventListener('mouseenter', (e) => {
            if (this.dragStartItem) {
                this.handleDragEnter(item, media.id);
            }
        });

        // Image
        const img = document.createElement('img');
        img.classList.add('transition-colors');
        img.alt = media.filename;
        img.loading = 'lazy';
        img.draggable = false;

        const markLoaded = () => {
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    img.classList.add('loaded');
                });
            });
        };

        img.onload = () => {
            if (img.decode) {
                img.decode().then(markLoaded).catch(markLoaded);
            } else {
                markLoaded();
            }
        };

        img.onerror = () => {
            img.classList.add('loaded');
            img.src = '/static/images/no-thumbnail.png';
        };

        img.src = `/api/media/${media.id}/thumbnail${media.hash ? '?v=' + media.hash : ''}`;

        if (img.complete && img.naturalWidth > 0) {
            markLoaded();
        }

        // Link
        const link = document.createElement('a');
        const basePath = linkUrl || `/media/${media.id}`;
        if (preserveQueryParams) {
            const params = new URLSearchParams(window.location.search);
            if (this.currentSort === 'manual' && !params.has('fallback_sort')) {
                this.appendSortParams(params);
            }
            const queryString = params.toString();
            link.href = `${basePath}${queryString ? '?' + queryString : ''}`;
        } else {
            link.href = basePath;
        }

        const blurWrapperOrImg = window.wrapBlurThumbnail(img, media, item);
        link.appendChild(blurWrapperOrImg);

        const targetContainer = (blurWrapperOrImg === img) ? link : blurWrapperOrImg;
        if (window.setupGifPreview) {
            window.setupGifPreview(item, media, targetContainer, img, this.loadedGifs);
        }

        link.addEventListener('click', (e) => {
            if (app.isAdminMode && this.isSelectionMode) {
                e.preventDefault();
                this.toggleItemSelection(item, media.id, e);
            }
        });

        // ==================== Long Press for Mobile ====================
        let longPressTimer = null;
        let longPressTriggered = false;
        const LONG_PRESS_DURATION = 350; // ms

        const startLongPress = (e) => {
            if (document.body.classList.contains('reorder-active-mode')) return;
            longPressTriggered = false;
            item.classList.add('long-pressing');

            longPressTimer = setTimeout(() => {
                longPressTriggered = true;
                item.classList.remove('long-pressing');
                this.toggleItemSelection(item, media.id);

                if (navigator.vibrate) {
                    navigator.vibrate(50);
                }
            }, LONG_PRESS_DURATION);
        };

        const cancelLongPress = () => {
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
            item.classList.remove('long-pressing');
        };

        const endLongPress = (e) => {
            cancelLongPress();

            if (longPressTriggered) {
                e.preventDefault();
                e.stopPropagation();
                longPressTriggered = false;
            }
        };

        if (app.isAdminMode) {
            item.addEventListener('touchstart', startLongPress, { passive: true });
            item.addEventListener('touchend', endLongPress);
            item.addEventListener('touchcancel', cancelLongPress);
            item.addEventListener('touchmove', cancelLongPress, { passive: true });

            item.addEventListener('contextmenu', (e) => {
                if (longPressTriggered) {
                    e.preventDefault();
                }
            });
        }

        // Tooltip
        if (this.tooltipHelper && media.tags && media.tags.length > 0) {
            const isPrimaryTouch = window.matchMedia('(pointer: coarse)').matches;

            if (!isPrimaryTouch) {
                this.tooltipHelper.addToElement(item, media.tags);
            }
        }

        if (checkbox) item.appendChild(checkbox);
        if (indicator) item.appendChild(indicator);
        item.appendChild(link);

        if (media.is_shared) {
            const shareIcon = document.createElement('div');
            shareIcon.className = 'share-icon w-6 h-6 flex items-center justify-center p-0';
            shareIcon.innerHTML = window.Icons.share({ size: 12 });
            item.appendChild(shareIcon);
        }

        return item;
    },
});
