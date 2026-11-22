// MediaViewer album membership, album strip, related media, navigation, fullscreen, and keybindings
Object.assign(MediaViewer.prototype, {
    async loadRelatedMedia() {
        if (!this.currentMedia || !this.currentMedia.tags || !this.currentMedia.tags.length) {
            this.hideRelatedMedia();
            return;
        }

        const relatedMediaEl = this.el('related-media');
        const relatedMediaSection = this.el('related-media-section') || relatedMediaEl?.parentElement;
        const relatedMediaLoading = this.el('related-media-loading');

        if (relatedMediaSection) relatedMediaSection.style.display = 'block';
        if (relatedMediaLoading) relatedMediaLoading.style.display = 'block';
        if (relatedMediaEl) relatedMediaEl.style.display = 'none';

        try {
            const currentMediaId = parseInt(this.mediaId);
            const params = new URLSearchParams({ limit: '12' });
            if (this.albumId) {
                params.set('album_id', this.albumId);
            }

            const urlParams = new URLSearchParams(window.location.search);
            const sidebarMode = document.body.dataset.sidebarMode || window.SIDEBAR_FILTER_MODE || 'rating';

            if (sidebarMode !== 'custom' && sidebarMode !== 'off') {
                let rating = urlParams.get('rating');
                if (rating === null) {
                    rating = localStorage.getItem('selectedRating') || 'safe';
                }
                if (rating) {
                    params.set('rating', rating);
                }
            }

            if (sidebarMode === 'custom' || sidebarMode === 'both') {
                const rawCustomFilter = localStorage.getItem('selectedCustomFilter') || '';
                try {
                    const parsed = JSON.parse(rawCustomFilter);
                    if (Array.isArray(parsed)) {
                        parsed.forEach(cf => { if (cf) params.append('custom_filter', cf); });
                    } else if (parsed) {
                        params.append('custom_filter', parsed);
                    }
                } catch {
                    if (rawCustomFilter) params.append('custom_filter', rawCustomFilter);
                }
            }

            const res = await fetch(`/api/media/${currentMediaId}/related?${params.toString()}`, {
                credentials: 'include'
            });

            if (!res.ok) {
                this.hideRelatedMedia();
                return;
            }

            const data = await res.json();
            const items = (data.items || []).filter(i => i.id !== currentMediaId);

            if (items.length > 0) {
                this.renderRelatedMedia(items);
            } else {
                this.hideRelatedMedia();
            }
        } catch (e) {
            console.error('related error', e);
            this.hideRelatedMedia();
        }
    },

    renderRelatedMedia(items) {
        const relatedMediaEl = this.el('related-media');
        const relatedMediaSection = this.el('related-media-section') || relatedMediaEl?.parentElement;
        const relatedMediaLoading = this.el('related-media-loading');
        const params = new URLSearchParams(window.location.search);
        params.delete('q');
        const queryString = params.toString();

        if (relatedMediaSection) relatedMediaSection.style.display = 'block';
        if (relatedMediaLoading) relatedMediaLoading.style.display = 'none';
        if (relatedMediaEl) {
            this.unloadAllGifs();
            relatedMediaEl.style.display = 'grid';
            relatedMediaEl.classList.add('grid');
            relatedMediaEl.innerHTML = '';
        }

        items.forEach(media => {
            const item = this.createRelatedMediaItem(media, queryString);
            relatedMediaEl.appendChild(item);
        });
    },

    createRelatedMediaItem(media, queryString, inAlbum = null) {
        const item = document.createElement('div');
        item.className = `gallery-item ${media.file_type}`;
        if (media.parent_id) item.classList.add('child-item');
        if (media.has_children) item.classList.add('parent-item');
        item.dataset.id = media.id;
        item.dataset.rating = media.rating;

        const link = document.createElement('a');
        const useAlbumPath = this.albumId && (inAlbum === true || inAlbum === null);
        const basePath = useAlbumPath ? `/album/${this.albumId}/media/${media.id}` : `/media/${media.id}`;
        link.href = `${basePath}${queryString ? '?' + queryString : ''}`;

        const img = document.createElement('img');
        img.alt = media.filename;
        img.loading = 'lazy';
        img.className = 'transition-colors';

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
            console.error(window.i18n.t('media.errors.failed_load_thumbnail', { id: media.id }));
            img.classList.add('loaded');
            img.src = '/static/images/no-thumbnail.png';
        };

        img.src = `/api/media/${media.id}/thumbnail${media.hash ? '?v=' + media.hash : ''}`;

        if (img.complete && img.naturalWidth > 0) {
            markLoaded();
        }

        const blurWrapperOrImg = window.wrapBlurThumbnail(img, media, item);
        link.appendChild(blurWrapperOrImg);

        const targetContainer = (blurWrapperOrImg === img) ? link : blurWrapperOrImg;
        if (window.setupGifPreview) {
            window.setupGifPreview(item, media, targetContainer, img, this.loadedGifs);
        }

        item.appendChild(link);

        if (media.is_shared) {
            const shareIcon = document.createElement('div');
            shareIcon.className = 'share-icon w-6 h-6 flex items-center justify-center p-0';
            shareIcon.innerHTML = window.Icons.share({ size: 12 });
            item.appendChild(shareIcon);
        }

        // Add tooltip functionality
        if (this.tooltipHelper && media.tags && media.tags.length > 0) {
            const isPrimaryTouch = window.matchMedia('(pointer: coarse)').matches;

            if (!isPrimaryTouch) {
                this.tooltipHelper.addToElement(item, media.tags);
            }
        }

        return item;
    },

    hideRelatedMedia() {
        const relatedMediaEl = this.el('related-media');
        const relatedMediaSection = this.el('related-media-section') || relatedMediaEl?.parentElement;
        if (relatedMediaSection) {
            relatedMediaSection.style.display = 'none';
        }
    },

    // ==================== Album Methods ====================

    async setupBackToAlbum() {
        if (!this.albumId) return;

        const section = this.el('back-to-album-section');
        const btn = this.el('back-to-album-btn');
        const textEl = this.el('back-to-album-text');
        if (!section || !btn) return;

        const params = new URLSearchParams(window.location.search);
        const queryString = params.toString();
        btn.href = `/album/${this.albumId}${queryString ? '?' + queryString : ''}`;
        section.style.display = 'block';

        try {
            const res = await fetch(`/api/albums/${this.albumId}`);
            if (res.ok) {
                const album = await res.json();
                if (album && album.name && textEl) {
                    const escapeDiv = document.createElement('div');
                    escapeDiv.textContent = album.name;
                    const boldName = `<span class="font-bold">${escapeDiv.innerHTML}</span>`;
                    const translated = window.i18n.t('media.back_to_album_named', { name: boldName });
                    textEl.innerHTML = (translated && translated !== 'media.back_to_album_named')
                        ? translated
                        : `${window.i18n.t('media.back_to_album')} (${boldName})`;
                }
            }
        } catch (e) {
        }
    },

    _getResolvedAlbumId() {
        const albumMatch = window.location.pathname.match(/\/album\/(\d+)\/media\//);
        if (albumMatch) return parseInt(albumMatch[1], 10);
        if (this.albumId) return parseInt(this.albumId, 10);
        return null;
    },

    _appendNavigationContextParams(queryParams) {
        const urlParams = new URLSearchParams(window.location.search);

        const q = urlParams.get('q') || '';
        if (q) queryParams.set('q', q);

        const sidebarMode = document.body.dataset.sidebarMode || window.SIDEBAR_FILTER_MODE || 'rating';
        if (sidebarMode === 'custom' || sidebarMode === 'both') {
            const rawCustomFilter = localStorage.getItem('selectedCustomFilter') || '';
            try {
                const parsed = JSON.parse(rawCustomFilter);
                if (Array.isArray(parsed)) {
                    parsed.forEach(cf => { if (cf) queryParams.append('custom_filter', cf); });
                } else if (parsed) {
                    queryParams.append('custom_filter', parsed);
                }
            } catch {
                if (rawCustomFilter) queryParams.append('custom_filter', rawCustomFilter);
            }
        }

        let rating = urlParams.get('rating');
        if (sidebarMode !== 'custom' && sidebarMode !== 'off') {
            if (rating === null) {
                rating = localStorage.getItem('selectedRating') || 'safe';
            }
        }

        if (rating) {
            queryParams.set('rating', rating);
        }

        const sort = urlParams.get('sort');
        if (sort) queryParams.set('sort', sort);

        const order = urlParams.get('order');
        if (order) queryParams.set('order', order);

        const seed = urlParams.get('seed');
        if (seed) queryParams.set('seed', seed);

        const fallbackSort = urlParams.get('fallback_sort');
        if (fallbackSort) queryParams.set('fallback_sort', fallbackSort);

        const fallbackOrder = urlParams.get('fallback_order');
        if (fallbackOrder) queryParams.set('fallback_order', fallbackOrder);
    },

    async loadMediaAlbums() {
        const section = this.el('media-albums-section');
        const listEl = this.el('media-albums-list');
        if (!section || !listEl) return;

        try {
            const res = await fetch(`/api/media/${this.mediaId}/albums`);
            if (!res.ok) {
                section.style.display = 'none';
                return;
            }
            const data = await res.json();
            this.renderMediaAlbums(data.albums || []);
        } catch (e) {
            console.error('Error loading media albums:', e);
            section.style.display = 'none';
        }
    },

    renderMediaAlbums(albums) {
        const section = this.el('media-albums-section');
        const listEl = this.el('media-albums-list');
        if (!section || !listEl) return;

        if (!albums || albums.length === 0) {
            listEl.innerHTML = '';
            section.style.display = 'none';
            return;
        }

        const activeAlbumId = this._getResolvedAlbumId();
        const currentMediaId = parseInt(this.mediaId, 10);

        const openAlbumLabel = window.i18n.t('media.open_album');

        listEl.innerHTML = albums.map(album => {
            const isActive = activeAlbumId === album.id;
            const parentPathHtml = album.parent_path
                ? `<span class="block text-[10px] text-secondary truncate">${escapeHtml(album.parent_path)}</span>`
                : '';

            const fullAlbumTitle = album.parent_path ? `${album.parent_path} > ${album.name}` : album.name;
            const openAriaLabel = `${openAlbumLabel}: ${album.name}`;

            return `
                <li class="media-album-item flex items-center border-b last:border-b-0 transition-colors ${isActive ? 'is-active bg-primary/10 hover:bg-primary/15' : 'hover:surface'}">
                    <a href="/album/${album.id}/media/${currentMediaId}"
                        class="flex items-center gap-2 flex-1 min-w-0 py-1.5 pl-2 pr-1 focus-visible:outline-2 focus-visible:outline-primary"
                        title="${escapeAttr(fullAlbumTitle)}"${isActive ? ' aria-current="true"' : ''}>
                        <span class="shrink-0 transition-colors ${isActive ? 'text-primary' : 'text-secondary'}">
                            ${window.Icons.folder({ size: 14, extra: 'aria-hidden="true"' })}
                        </span>
                        <span class="flex-1 min-w-0">
                            <span class="block text-xs truncate ${isActive ? 'font-bold text-primary' : 'font-medium text'}">${escapeHtml(album.name)}</span>
                            ${parentPathHtml}
                        </span>
                    </a>
                    <a href="/album/${album.id}"
                        class="flex items-center justify-center p-1.5 min-w-6 min-h-6 text-secondary hover:text-primary transition-colors shrink-0 focus-visible:outline-2 focus-visible:outline-primary"
                        title="${escapeAttr(openAlbumLabel)}"
                        aria-label="${escapeAttr(openAriaLabel)}">
                        ${window.Icons.grid({ size: 14, extra: 'aria-hidden="true"' })}
                    </a>
                </li>
            `;
        }).join('');

        section.style.display = 'block';
        this.setupMediaAlbumsToggle();
    },

    setupMediaAlbumsToggle() {
        const toggle = this.el('media-albums-toggle');
        const content = this.el('media-albums-content');
        if (!toggle || !content) return;

        const isCollapsed = localStorage.getItem('mediaAlbumsCollapsed') === 'true';
        content.style.display = isCollapsed ? 'none' : 'block';

        const newToggle = toggle.cloneNode(true);
        toggle.parentNode.replaceChild(newToggle, toggle);
        newToggle.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');

        const liveChevron = newToggle.querySelector('#media-albums-chevron');
        if (liveChevron) {
            liveChevron.style.transform = isCollapsed ? 'rotate(0deg)' : 'rotate(180deg)';
        }

        newToggle.addEventListener('click', () => {
            const isHidden = content.style.display === 'none';
            content.style.display = isHidden ? 'block' : 'none';
            newToggle.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
            localStorage.setItem('mediaAlbumsCollapsed', isHidden ? 'false' : 'true');
            if (liveChevron) {
                liveChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            }
        });
    },

    async loadAlbumStrip() {
        const albumId = this._getResolvedAlbumId();
        const section = this.el('album-media-section');
        if (!albumId || !section) return;

        const queryParams = new URLSearchParams();
        queryParams.set('album_id', albumId);
        this._appendNavigationContextParams(queryParams);

        try {
            const res = await fetch(`/api/media/${this.mediaId}/album-context?${queryParams.toString()}`);
            if (!res.ok) {
                section.style.display = 'none';
                return;
            }
            const data = await res.json();
            this.renderAlbumStrip(data);
        } catch (e) {
            console.error('Error loading album strip:', e);
            section.style.display = 'none';
        }
    },

    renderAlbumStrip(data) {
        const section = this.el('album-media-section');
        const stripEl = this.el('album-media');
        const titleEl = this.el('album-media-title');

        if (!section || !stripEl || !titleEl) return;

        const items = data && Array.isArray(data.items) ? data.items : [];
        if (items.length <= 1 || !data.album) {
            stripEl.innerHTML = '';
            section.style.display = 'none';
            return;
        }

        const titleText = escapeHtml(data.album.name);
        titleEl.innerHTML = `${titleText}`;

        const queryString = new URLSearchParams(window.location.search).toString();
        const currentId = parseInt(this.mediaId, 10);

        stripEl.innerHTML = '';
        let currentItemEl = null;

        items.forEach((media) => {
            const item = this.createRelatedMediaItem(media, queryString, true);
            item.setAttribute('role', 'listitem');
            item.style.flex = '0 0 auto';
            item.style.width = '120px';

            if (media.id === currentId) {
                item.classList.add('album-strip-current');
                const link = item.querySelector('a');
                if (link) link.setAttribute('aria-current', 'page');
                currentItemEl = item;
            }

            stripEl.appendChild(item);
        });

        section.style.display = 'block';
        this.setupAlbumStripToggle();
        this._setupHorizontalCarousel(
            stripEl,
            this.el('album-strip-prev-btn'),
            this.el('album-strip-next-btn')
        );

        if (currentItemEl) {
            this._centerAlbumStripCurrentItem(stripEl);
            requestAnimationFrame(() => {
                this._centerAlbumStripCurrentItem(stripEl);
            });
        }
    },

    _centerAlbumStripCurrentItem(stripEl) {
        if (!stripEl) return;
        const currentItemEl = stripEl.querySelector('.album-strip-current');
        if (!currentItemEl) return;

        const stripRect = stripEl.getBoundingClientRect();
        const itemRect = currentItemEl.getBoundingClientRect();
        if (stripRect.width <= 0 || itemRect.width <= 0) return;

        const maxScroll = Math.max(0, stripEl.scrollWidth - stripEl.clientWidth);
        const targetLeft = stripEl.scrollLeft + (itemRect.left - stripRect.left) - (stripRect.width - itemRect.width) / 2;
        const clampedLeft = Math.min(maxScroll, Math.max(0, targetLeft));

        const prevBehavior = stripEl.style.scrollBehavior;
        stripEl.style.scrollBehavior = 'auto';
        stripEl.scrollLeft = clampedLeft;
        stripEl.style.scrollBehavior = prevBehavior;

        if (typeof stripEl._carouselUpdateButtons === 'function') {
            stripEl._carouselUpdateButtons();
        }
    },

    setupAlbumStripToggle() {
        const toggle = this.el('album-media-toggle');
        const content = this.el('album-media-content');
        if (!toggle || !content) return;

        const isCollapsed = localStorage.getItem('albumStripCollapsed') === 'true';
        content.style.display = isCollapsed ? 'none' : 'block';

        const newToggle = toggle.cloneNode(true);
        toggle.parentNode.replaceChild(newToggle, toggle);
        newToggle.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');

        const liveChevron = newToggle.querySelector('#album-media-chevron');
        if (liveChevron) {
            liveChevron.style.transform = isCollapsed ? 'rotate(0deg)' : 'rotate(180deg)';
        }

        newToggle.addEventListener('click', () => {
            const isHidden = content.style.display === 'none';
            content.style.display = isHidden ? 'block' : 'none';
            newToggle.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
            localStorage.setItem('albumStripCollapsed', isHidden ? 'false' : 'true');
            if (liveChevron) {
                liveChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            }
            if (isHidden) {
                const stripEl = this.el('album-media');
                this._centerAlbumStripCurrentItem(stripEl);
                stripEl?.dispatchEvent(new Event('scroll'));
            }
        });
    },

    async setupMediaNavigation() {
        const navBar = document.getElementById('media-nav-bar');
        const prevBtn = document.getElementById('nav-prev-btn');
        const nextBtn = document.getElementById('nav-next-btn');
        const prevThumb = document.getElementById('nav-prev-thumb');
        const nextThumb = document.getElementById('nav-next-thumb');
        const prevIdText = document.getElementById('nav-prev-id-text');
        const nextIdText = document.getElementById('nav-next-id-text');

        if (!prevBtn && !nextBtn) return;

        const albumId = this._getResolvedAlbumId();
        const mode = albumId ? 'album' : 'search';

        const queryParams = new URLSearchParams();
        queryParams.set('mode', mode);
        if (albumId) queryParams.set('album_id', albumId);
        this._appendNavigationContextParams(queryParams);

        try {
            const res = await fetch(`/api/media/${this.mediaId}/adjacent?${queryParams.toString()}`);
            if (!res.ok) return;

            const data = await res.json();
            const { prev_id, prev_hash, prev_rating, next_id, next_hash, next_rating } = data;
            const shouldBlur = window.shouldBlurExplicit();

            if (!prev_id && !next_id) {
                if (navBar) navBar.style.display = 'none';
                return;
            }

            if (navBar) navBar.style.display = 'flex';

            const buildNavUrl = (targetId) => {
                const navParams = new URLSearchParams(window.location.search);
                const queryStr = navParams.toString();
                const basePath = mode === 'album' && albumId ? `/album/${albumId}/media/${targetId}` : `/media/${targetId}`;
                return `${basePath}${queryStr ? '?' + queryStr : ''}`;
            };

            if (prevBtn) {
                if (prev_id) {
                    prevBtn.href = buildNavUrl(prev_id);
                    prevBtn.style.visibility = 'visible';
                    if (prevIdText) prevIdText.textContent = prev_id;
                    if (prevThumb) {
                        prevThumb.src = `/api/media/${prev_id}/thumbnail${prev_hash ? '?v=' + prev_hash : ''}`;
                    }
                    if (prev_rating === 'explicit' && shouldBlur) {
                        prevBtn.classList.add('blur-content');
                    } else {
                        prevBtn.classList.remove('blur-content');
                    }
                } else {
                    prevBtn.style.visibility = 'hidden';
                    prevBtn.classList.remove('blur-content');
                }
            }

            if (nextBtn) {
                if (next_id) {
                    nextBtn.href = buildNavUrl(next_id);
                    nextBtn.style.visibility = 'visible';
                    if (nextIdText) nextIdText.textContent = next_id;
                    if (nextThumb) {
                        nextThumb.src = `/api/media/${next_id}/thumbnail${next_hash ? '?v=' + next_hash : ''}`;
                    }
                    if (next_rating === 'explicit' && shouldBlur) {
                        nextBtn.classList.add('blur-content');
                    } else {
                        nextBtn.classList.remove('blur-content');
                    }
                } else {
                    nextBtn.style.visibility = 'hidden';
                    nextBtn.classList.remove('blur-content');
                }
            }

            this.prevNavUrl = prev_id ? buildNavUrl(prev_id) : null;
            this.nextNavUrl = next_id ? buildNavUrl(next_id) : null;

        } catch (e) {
            console.error('Error fetching adjacent media:', e);
        }
    },

    isAnyModalOpen() {
        const candidateModals = document.querySelectorAll(
            '.modal, .age-verification-overlay, [id*="modal"], .mpicker-backdrop, dialog[open]'
        );
        for (const el of candidateModals) {
            const target = el.classList.contains('mpicker-backdrop') ? el.parentElement : el;
            if (!target) continue;
            const style = window.getComputedStyle(target);
            if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0' && (target.offsetWidth > 0 || target.offsetHeight > 0)) {
                return true;
            }
        }
        return false;
    },

    setupKeybindings() {
        document.addEventListener('keydown', (e) => {
            const activeEl = document.activeElement;
            const isTyping = activeEl && (
                activeEl.tagName === 'INPUT' ||
                activeEl.tagName === 'TEXTAREA' ||
                activeEl.isContentEditable ||
                activeEl.closest('.modal, .age-verification-overlay, [id*="modal"], .mpicker-backdrop')
            );
            if (isTyping || this.isAnyModalOpen()) return;

            if (window.keybindings && window.keybindings.matches(e, 'media_fullscreen')) {
                e.preventDefault();
                this.toggleFullscreen();
                return;
            }

            const containerVideo = this.el('media-container')?.querySelector('video');
            const overlayVideo = document.getElementById('fullscreen-video');
            const activeVideo = (overlayVideo && overlayVideo.style.display !== 'none') ? overlayVideo : containerVideo;

            if (activeVideo) {
                if (document.activeElement !== activeVideo) {
                    try { activeVideo.focus(); } catch (_) { }
                }

                if (e.code === 'Space' || e.key === ' ') {
                    e.preventDefault();
                    if (activeVideo.paused) {
                        activeVideo.play().catch(() => { });
                    } else {
                        activeVideo.pause();
                    }
                    return;
                }

                const isNativeFullscreen = !!(
                    document.fullscreenElement ||
                    document.webkitFullscreenElement ||
                    document.mozFullScreenElement ||
                    document.msFullscreenElement ||
                    (activeVideo && activeVideo.webkitDisplayingFullscreen)
                );

                const isPlaying = !activeVideo.paused && !activeVideo.ended && activeVideo.readyState > 2;

                if (isNativeFullscreen || isPlaying) return;
            }

            const fullscreenOverlay = document.getElementById('fullscreen-overlay');
            if (fullscreenOverlay && fullscreenOverlay.classList.contains('active')) return;

            if (window.keybindings && window.keybindings.matches(e, 'media_nav_prev') && this.prevNavUrl) {
                e.preventDefault();
                window.location.href = this.prevNavUrl;
            } else if (window.keybindings && window.keybindings.matches(e, 'media_nav_next') && this.nextNavUrl) {
                e.preventDefault();
                window.location.href = this.nextNavUrl;
            }
        });

        const handleFSChange = () => {
            const fsEl = document.fullscreenElement ||
                document.webkitFullscreenElement ||
                document.mozFullScreenElement ||
                document.msFullscreenElement;

            if (fsEl) {
                const vid = fsEl.tagName === 'VIDEO' ? fsEl : fsEl.querySelector('video');
                if (vid) {
                    try { vid.focus(); } catch (_) { }
                }
            }
        };

        ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(evt => {
            document.addEventListener(evt, handleFSChange);
        });
    },

    toggleFullscreen() {
        const nativeFullscreenEl = document.fullscreenElement ||
            document.webkitFullscreenElement ||
            document.mozFullScreenElement ||
            document.msFullscreenElement;

        const overlay = document.getElementById('fullscreen-overlay');
        const isOverlayActive = overlay && overlay.classList.contains('active');

        if (nativeFullscreenEl) {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
            return;
        }

        const containerVideo = this.el('media-container')?.querySelector('video');
        const overlayVideo = document.getElementById('fullscreen-video');
        const activeVideo = (overlayVideo && overlayVideo.style.display !== 'none') ? overlayVideo : containerVideo;

        if (activeVideo && activeVideo.webkitDisplayingFullscreen) {
            if (activeVideo.webkitExitFullscreen) {
                activeVideo.webkitExitFullscreen();
            }
            return;
        }

        if (isOverlayActive) {
            if (this.fullscreenViewer) {
                this.fullscreenViewer.close();
            }
            return;
        }

        if (!this.currentMedia) return;

        if (this.currentMedia.file_type === 'video') {
            const videoEl = containerVideo || overlayVideo;
            if (videoEl) {
                const focusVideo = () => {
                    try {
                        videoEl.focus();
                    } catch (_) { }
                };

                if (videoEl.requestFullscreen) {
                    videoEl.requestFullscreen().then(focusVideo).catch(() => {
                        this.openFullscreenViewer();
                    });
                    focusVideo();
                } else if (videoEl.webkitRequestFullscreen) {
                    videoEl.webkitRequestFullscreen();
                    focusVideo();
                } else if (videoEl.webkitEnterFullscreen) {
                    videoEl.webkitEnterFullscreen();
                    focusVideo();
                } else if (videoEl.msRequestFullscreen) {
                    videoEl.msRequestFullscreen();
                    focusVideo();
                } else {
                    this.openFullscreenViewer();
                }
            } else {
                this.openFullscreenViewer();
            }
        } else {
            this.openFullscreenViewer();
        }
    },

    openFullscreenViewer() {
        if (!this.currentMedia || !this.fullscreenViewer) return;
        const isVideo = this.currentMedia.file_type === 'video';
        const fileUrl = `/api/media/${this.currentMedia.id}/file${this.currentMedia.hash ? '?v=' + this.currentMedia.hash : ''}`;
        this.fullscreenViewer.open(fileUrl, isVideo);
    },

    async addToAlbums() {
        try {
            // Get current album IDs to pre-select
            const res = await fetch(`/api/media/${this.mediaId}/albums`);
            const data = await res.json();
            const currentAlbumIds = (data.albums || []).map(a => a.id);

            const result = await AlbumPicker.pick({
                title: window.i18n.t('common.add_to_albums'),
                multiSelect: true,
                preSelected: currentAlbumIds
            });

            if (!result) return;
            const { ids: selectedIds } = result;

            // Determine added and removed albums
            const addedIds = selectedIds.filter(id => !currentAlbumIds.includes(id));
            const removedIds = currentAlbumIds.filter(id => !selectedIds.includes(id));

            if (addedIds.length === 0 && removedIds.length === 0) return;

            try {
                // Process additions
                for (const albumId of addedIds) {
                    await app.apiCall(`/api/albums/${albumId}/media`, {
                        method: 'POST',
                        body: JSON.stringify({ media_ids: [parseInt(this.mediaId)] })
                    });
                }

                // Process removals
                for (const albumId of removedIds) {
                    await app.apiCall(`/api/albums/${albumId}/media`, {
                        method: 'DELETE',
                        body: JSON.stringify({ media_ids: [parseInt(this.mediaId)] })
                    });
                }

                app.showNotification(window.i18n.t('notifications.media.albums_updated'), 'success');
                await this.loadMediaAlbums();
                if (this.albumId) {
                    await Promise.all([
                        this.setupMediaNavigation(),
                        this.loadAlbumStrip(),
                    ]);
                }
            } catch (error) {
                app.showNotification(error.message, 'error', window.i18n.t('notifications.media.error_updating_albums'));
            }
        } catch (error) {
            console.error('Error opening album picker:', error);
            app.showNotification(window.i18n.t('notifications.media.error_opening_album_picker'), 'error');
        }
    },

    async removeFromAlbum(albumId) {
        try {
            await app.apiCall(`/api/albums/${albumId}/media`, {
                method: 'DELETE',
                body: JSON.stringify({ media_ids: [parseInt(this.mediaId)] })
            });

            app.showNotification(window.i18n.t('notifications.media.removed_from_album'), 'success');
            await this.loadMediaAlbums();
            if (this.albumId) {
                await Promise.all([
                    this.setupMediaNavigation(),
                    this.loadAlbumStrip(),
                ]);
            }
        } catch (error) {
            app.showNotification(error.message, 'error', window.i18n.t('notifications.media.error_removing_from_album'));
        }
    },
});
