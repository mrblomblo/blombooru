// Explicit Thumbnail Blur Helpers
window.shouldBlurExplicit = function () {
    return document.body.dataset.blurExplicit === 'true';
};

window.wrapBlurThumbnail = function (img, media, item) {
    if (!media || media.rating !== 'explicit' || !window.shouldBlurExplicit()) {
        return img;
    }
    const blurWrapper = document.createElement('div');
    blurWrapper.classList.add('blur-wrapper');
    if (media.width && media.height) {
        blurWrapper.style.aspectRatio = `${media.width} / ${media.height}`;
    } else {
        img.addEventListener('load', () => {
            if (img.naturalWidth && img.naturalHeight) {
                blurWrapper.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
            }
        }, { once: true });
    }
    blurWrapper.appendChild(img);
    if (item) {
        item.classList.add('blur-content');
    }
    return blurWrapper;
};

// GIF Gallery Item Hover Preview Helpers
const GIF_BLOB_CACHE_LIMIT = 6;
const gifBlobCache = new Map();

function getCachedGifBlob(mediaId) {
    if (!gifBlobCache.has(mediaId)) return null;
    const entry = gifBlobCache.get(mediaId);
    gifBlobCache.delete(mediaId);
    gifBlobCache.set(mediaId, entry);
    return entry.blob;
}

function setCachedGifBlob(mediaId, blob) {
    if (gifBlobCache.has(mediaId)) {
        const entry = gifBlobCache.get(mediaId);
        entry.blob = blob;
        gifBlobCache.delete(mediaId);
        gifBlobCache.set(mediaId, entry);
        return entry;
    }
    while (gifBlobCache.size >= GIF_BLOB_CACHE_LIMIT) {
        const oldestKey = gifBlobCache.keys().next().value;
        const oldest = gifBlobCache.get(oldestKey);
        if (oldest && oldest.urls) {
            oldest.urls.forEach(url => URL.revokeObjectURL(url));
        }
        gifBlobCache.delete(oldestKey);
    }
    const entry = { blob, urls: new Set() };
    gifBlobCache.set(mediaId, entry);
    return entry;
}

function createGifObjectUrl(mediaId, blob) {
    let entry = gifBlobCache.get(mediaId);
    if (!entry) {
        entry = setCachedGifBlob(mediaId, blob);
    }
    const url = URL.createObjectURL(blob);
    entry.urls.add(url);
    return url;
}

function revokeGifObjectUrl(mediaId, url) {
    if (!url) return;
    URL.revokeObjectURL(url);
    const entry = gifBlobCache.get(mediaId);
    if (entry && entry.urls) {
        entry.urls.delete(url);
    }
}

function clearAllGifBlobCache() {
    gifBlobCache.forEach(entry => {
        if (entry.urls) {
            entry.urls.forEach(url => URL.revokeObjectURL(url));
        }
    });
    gifBlobCache.clear();
}

window.setupGifPreview = function (item, media, targetContainer, thumbnailImg, trackerSet = null) {
    if (!item || !media || media.file_type !== 'gif' || !item.classList.contains('gif')) {
        return;
    }
    if (window.matchMedia && !window.matchMedia('(hover: hover)').matches) {
        return;
    }

    const fileUrl = `/api/media/${media.id}/file${media.hash ? '?v=' + media.hash : ''}`;
    const thumb = thumbnailImg || item.querySelector('a img:not(.gif-preview)');

    let gifImg = null;
    let hoverTimer = null;
    let currentToken = 0;
    let currentBlobUrl = null;
    let abortController = null;

    const stopPlay = () => {
        clearTimeout(hoverTimer);
        ++currentToken;

        if (abortController) {
            abortController.abort();
            abortController = null;
        }

        if (thumb) {
            thumb.style.display = '';
        }

        if (gifImg) {
            gifImg.onload = null;
            gifImg.onerror = null;
            gifImg.style.display = 'none';
            gifImg.removeAttribute('src');
        }

        if (currentBlobUrl) {
            revokeGifObjectUrl(media.id, currentBlobUrl);
            currentBlobUrl = null;
        }
    };

    const activateGif = (token) => {
        if (token !== currentToken || !item.isConnected || !gifImg) return;
        gifImg.style.display = 'block';
        if (thumb) {
            thumb.style.display = 'none';
        }
    };

    const loadAndActivate = (url, token) => {
        if (!gifImg) return;
        gifImg.src = url;
        if (gifImg.decode) {
            gifImg.decode().then(() => {
                activateGif(token);
            }).catch(() => {
                if (token === currentToken) {
                    if (gifImg) gifImg.style.display = 'none';
                    if (thumb) thumb.style.display = '';
                }
            });
        } else {
            gifImg.onload = () => activateGif(token);
            gifImg.onerror = () => {
                if (token === currentToken && thumb) {
                    thumb.style.display = '';
                }
            };
        }
    };

    const executePlay = () => {
        const token = ++currentToken;

        if (!gifImg) {
            gifImg = document.createElement('img');
            gifImg.className = 'gif-preview loaded';
            gifImg.alt = thumb?.alt || media.filename || '';
            gifImg.draggable = false;
            gifImg.style.display = 'none';
            targetContainer.appendChild(gifImg);
            item._gifImg = gifImg;

            if (trackerSet && typeof trackerSet.add === 'function') {
                trackerSet.add(item);
            }
        }

        const cachedBlob = getCachedGifBlob(media.id);
        if (cachedBlob) {
            if (currentBlobUrl) {
                revokeGifObjectUrl(media.id, currentBlobUrl);
                currentBlobUrl = null;
            }
            currentBlobUrl = createGifObjectUrl(media.id, cachedBlob);
            loadAndActivate(currentBlobUrl, token);
            return;
        }

        abortController = new AbortController();

        fetch(fileUrl, { signal: abortController.signal })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP error ${res.status}`);
                return res.blob();
            })
            .then(blob => {
                if (token !== currentToken) return;
                setCachedGifBlob(media.id, blob);
                if (currentBlobUrl) {
                    revokeGifObjectUrl(media.id, currentBlobUrl);
                    currentBlobUrl = null;
                }
                currentBlobUrl = createGifObjectUrl(media.id, blob);
                loadAndActivate(currentBlobUrl, token);
            })
            .catch(err => {
                if (err.name === 'AbortError') return;
                if (token === currentToken && thumb) {
                    thumb.style.display = '';
                }
            });
    };

    const startPlay = () => {
        if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        if (navigator.connection && navigator.connection.saveData) return;
        if (document.body.classList.contains('reorder-active-mode') ||
            document.body.classList.contains('is-dragging') ||
            item.closest('.selection-mode')) {
            return;
        }

        clearTimeout(hoverTimer);
        hoverTimer = setTimeout(executePlay, 150);
    };

    item.addEventListener('mouseenter', startPlay);
    item.addEventListener('mouseleave', stopPlay);
    item.addEventListener('focusin', startPlay);
    item.addEventListener('focusout', stopPlay);

    item._unloadGif = () => {
        clearTimeout(hoverTimer);
        ++currentToken;

        if (abortController) {
            abortController.abort();
            abortController = null;
        }

        if (currentBlobUrl) {
            revokeGifObjectUrl(media.id, currentBlobUrl);
            currentBlobUrl = null;
        }

        if (thumb) {
            thumb.style.display = '';
        }
        if (gifImg) {
            gifImg.onload = null;
            gifImg.onerror = null;
            gifImg.removeAttribute('src');
            gifImg.remove();
            gifImg = null;
            delete item._gifImg;
        }
    };
};

window.unloadAllGifs = function (trackerSet = null, container = null) {
    if (trackerSet && typeof trackerSet.forEach === 'function') {
        trackerSet.forEach(item => {
            if (item && typeof item._unloadGif === 'function') {
                item._unloadGif();
            }
        });
        trackerSet.clear();
    }

    clearAllGifBlobCache();

    const root = container || document;
    const orphanGifs = root.querySelectorAll('.gif-preview');
    orphanGifs.forEach(gif => {
        gif.onload = null;
        gif.onerror = null;
        gif.removeAttribute('src');
        gif.remove();
    });

    root.querySelectorAll('.gallery-item img:not(.gif-preview)').forEach(img => {
        if (img.style.display === 'none') {
            img.style.display = '';
        }
    });
};
