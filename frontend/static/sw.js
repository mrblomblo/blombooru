const CACHE_NAME = 'blombooru-1-24-0';
const STATIC_ASSETS = [
    '/static/css/tailwind.css',
    '/static/css/main.css',
    '/static/images/no-thumbnail.png',
    '/static/images/pwa-icon.png',
    '/static/images/pwa-icon-192.png',
    '/static/js/admin.js',
    '/static/js/ai-tag-utils.js',
    '/static/js/album-picker.js',
    '/static/js/album.js',
    '/static/js/albums.js',
    '/static/js/base-gallery.js',
    '/static/js/bulk-ai-tags-modal.js',
    '/static/js/bulk-tag-modal-base.js',
    '/static/js/bulk-wd-tagger-modal.js',
    '/static/js/custom-select.js',
    '/static/js/fullscreen-mediaviewer.js',
    '/static/js/gallery.js',
    '/static/js/login.js',
    '/static/js/main.js',
    '/static/js/media-viewer-base.js',
    '/static/js/media.js',
    '/static/js/modal-helper.js',
    '/static/js/shared.js',
    '/static/js/tag-autocomplete.js',
    '/static/js/tag-input-helper.js',
    '/static/js/tooltip-helper.js',
    '/static/js/upload.js',
    '/static/favicon.ico'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    // Network-first for navigation and API
    if (event.request.mode === 'navigate' || url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request)
                .catch(() => {
                    return caches.match(event.request);
                })
        );
        return;
    }

    // Cache-first for static assets
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(event.request).then((response) => {
                return response || fetch(event.request).then((fetchResponse) => {
                    return caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, fetchResponse.clone());
                        return fetchResponse;
                    });
                });
            })
        );
        return;
    }

    // Default: Network with cache fallback
    event.respondWith(
        fetch(event.request)
            .catch(() => {
                return caches.match(event.request);
            })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});
