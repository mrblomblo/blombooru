const CACHE_NAME = 'blombooru-__APP_VERSION__';
const IS_DEBUG = __DEBUG__;

const STATIC_ASSETS = [
    '/static/css/tailwind.css',
    '/static/css/main.css',
    '/static/css/themes/autumn.css',
    '/static/css/themes/ctp_frappe.css',
    '/static/css/themes/ctp_latte.css',
    '/static/css/themes/ctp_macchiato.css',
    '/static/css/themes/ctp_mocha.css',
    '/static/css/themes/default_dark.css',
    '/static/css/themes/default_light.css',
    '/static/css/themes/dracula.css',
    '/static/css/themes/everforest_dark_hard.css',
    '/static/css/themes/everforest_light_soft.css',
    '/static/css/themes/green.css',
    '/static/css/themes/gruvbox_dark_hard.css',
    '/static/css/themes/gruvbox_light_soft.css',
    '/static/css/themes/nord_polar_night.css',
    '/static/css/themes/nord_snow_storm.css',
    '/static/css/themes/oled.css',
    '/static/css/themes/rose_pine.css',
    '/static/css/themes/rose_pine_dawn.css',
    '/static/css/themes/rose_pine_moon.css',
    '/static/css/themes/vapor.css',
    '/static/images/no-thumbnail.png',
    '/static/images/pwa-icon.png',
    '/static/images/pwa-icon-192.png',
    '/static/locales/en.json',
    '/static/locales/ru.json',
    '/static/locales/sv.json',
    '/static/locales/zh-cn.json',
    '/static/js/format-registry.js',
    '/static/js/pages/login.js',
    '/static/js/pages/main.js',
    '/static/js/pages/gallery.js',
    '/static/js/pages/albums.js',
    '/static/js/pages/album.js',
    '/static/js/pages/media.js',
    '/static/js/pages/shared.js',
    '/static/js/pages/tags-gallery.js',
    '/static/js/components/modal-helper.js',
    '/static/js/components/model-download-modal.js',
    '/static/js/components/tag-autocomplete.js',
    '/static/js/components/tooltip-helper.js',
    '/static/js/components/custom-select.js',
    '/static/js/components/album-picker.js',
    '/static/js/components/album-tree.js',
    '/static/js/components/tag-input-helper.js',
    '/static/js/components/tag-preview.js',
    '/static/js/components/search-query.js',
    '/static/js/components/changelog-modal.js',
    '/static/js/components/acknowledgements-modal.js',
    '/static/js/components/keybinding-manager.js',
    '/static/js/components/ai-tag-utils.js',
    '/static/js/components/fullscreen-mediaviewer.js',
    '/static/js/components/media-viewer-base.js',
    '/static/js/components/media-picker-modal.js',
    '/static/js/components/icons.js',
    '/static/js/components/base-gallery.js',
    '/static/js/bulk/bulk-tag-modal-base.js',
    '/static/js/bulk/bulk-manage-tags-modal.js',
    '/static/js/bulk/bulk-manual-tag-editor-modal.js',
    '/static/js/bulk/bulk-ai-tags-modal.js',
    '/static/js/bulk/bulk-wd-tagger-modal.js',
    '/static/js/bulk/bulk-rating-modal.js',
    '/static/js/update-post/update-post-modal-base.js',
    '/static/js/update-post/update-post-modal.js',
    '/static/js/update-post/update-post-url-import.js',
    '/static/js/update-post/update-post-device-upload.js',
    '/static/js/upload/upload-session.js',
    '/static/js/upload/upload-queue-grid.js',
    '/static/js/upload/upload-media-editor.js',
    '/static/js/upload/pending-entities-panel.js',
    '/static/js/upload/upload-uploader-shell.js',
    '/static/js/admin/admin.js',
    '/static/js/admin/upload.js',
    '/static/js/admin/booru-config.js',
    '/static/js/admin/url-import.js',
    '/static/js/admin/tag-implications.js',
    '/static/js/admin/stats.js',
    '/static/js/admin/system.js',
    '/static/js/admin/content.js',
    '/static/js/admin/account.js',
    '/static/js/admin/api-key-manage-modal.js',
    '/static/js/admin/keybindings.js',
    '/static/js/vendor/chart.min.js',
    '/static/favicon.ico'
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    if (IS_DEBUG) return;
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;

    if (IS_DEBUG) {
        return;
    }

    const url = new URL(event.request.url);

    // Don't intercept media file/thumbnail requests.
    if (url.pathname.match(/^\/api\/(media|shared)\/[^/]+\/(file|thumbnail)$/)) {
        return;
    }

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
                return caches.match(event.request).then(
                    (cached) => cached || Response.error()
                );
            })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((cacheName) => IS_DEBUG || cacheName !== CACHE_NAME)
                    .map((cacheName) => caches.delete(cacheName))
            );
        }).then(() => {
            return self.clients.claim();
        })
    );
});
