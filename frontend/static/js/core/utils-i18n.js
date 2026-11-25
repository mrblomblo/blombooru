function escapeHtml(text, options = {}) {
    if (text === null || text === undefined) {
        if (typeof options === 'object' && options?.preserveNull) {
            return text;
        }
        return '';
    }
    const str = String(text);
    if (!str) {
        if (typeof options === 'object' && options?.preserveNull) {
            return text;
        }
        return '';
    }

    const mode = typeof options === 'string' ? options : (options?.mode || options?.pattern || 'all');

    if (mode === 'minimal' || mode === 'no-quotes') {
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeAttr(text, options = {}) {
    const opts = typeof options === 'string' ? { pattern: options } : { pattern: 'attr', ...options };
    return escapeHtml(text, opts);
}

function formatFileSize(bytes, options = {}) {
    if (typeof options === 'string') {
        options = { mode: options };
    }
    const mode = options.mode || 'default';
    const fallback = options.fallback !== undefined ? options.fallback : (mode === 'compact' ? '...' : undefined);

    const num = Number(bytes);
    const isLong = mode === 'long' || options.units === 'long';

    if (!num || isNaN(num) || num <= 0) {
        if (fallback !== undefined && (!bytes || isNaN(num))) {
            return fallback;
        }
        return isLong ? '0 Bytes' : '0 B';
    }

    const defaultUnits = isLong
        ? ['Bytes', 'KB', 'MB', 'GB', 'TB']
        : ['B', 'KB', 'MB', 'GB', 'TB'];
    const sizes = Array.isArray(options.units) ? options.units : defaultUnits;

    const defaultDecimals = (mode === 'compact' || mode === 'approx') ? 1 : 2;
    const decimals = typeof options.decimals === 'number' ? options.decimals : defaultDecimals;

    const stripZeros = options.fixed ? false : (options.stripZeros !== undefined ? options.stripZeros : (mode !== 'fixed' && mode !== 'long'));

    const k = 1024;
    const i = Math.min(Math.floor(Math.log(num) / Math.log(k)), sizes.length - 1);
    const value = num / Math.pow(k, i);
    const formatted = stripZeros ? parseFloat(value.toFixed(decimals)) : value.toFixed(decimals);
    return `${formatted} ${sizes[i]}`;
}

function formatBytes(bytes, options = {}) {
    return formatFileSize(bytes, options);
}

function formatDateTime(dateOrIso, fallback = '') {
    if (!dateOrIso) return fallback;
    const d = (dateOrIso instanceof Date) ? dateOrIso : new Date(dateOrIso);
    if (isNaN(d.getTime())) return fallback;
    return `${new Intl.DateTimeFormat(undefined, { dateStyle: 'short' }).format(d)} ${new Intl.DateTimeFormat(undefined, { timeStyle: 'short', hour12: false }).format(d)}`;
}

function toLocalInputDateTime(dateOrIso) {
    if (!dateOrIso) return '';
    const d = (dateOrIso instanceof Date) ? dateOrIso : new Date(dateOrIso);
    if (isNaN(d.getTime())) return '';
    const pad = (n) => String(n).padStart(2, '0');
    const year = String(d.getFullYear()).padStart(4, '0');
    return `${year}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function parseLocalInputDateTime(value) {
    if (!value) return null;
    const trimmed = typeof value === 'string' ? value.trim() : String(value);
    if (!trimmed) return null;
    const d = new Date(trimmed);
    if (isNaN(d.getTime())) return null;
    return d.toISOString();
}

function formatCustomDateOriginBadge(origin) {
    if (!origin) return '';
    const keyMap = {
        sidecar: 'upload.preview.origin_sidecar',
        exif: 'upload.preview.origin_exif',
        booru: 'upload.preview.origin_booru',
        client: 'upload.preview.origin_client',
        explicit: 'upload.preview.origin_explicit'
    };
    const translationKey = keyMap[origin];
    if (translationKey) {
        const label = window.i18n.t(translationKey);
        return `<span class="badge bg-primary primary-text border border-color text-[10px] px-1.5 py-0.5 shrink-0" title="${escapeHtml(label)}">${escapeHtml(label)}</span>`;
    }
    return '';
}

window.escapeHtml = escapeHtml;
window.escapeAttr = escapeAttr;
window.formatFileSize = formatFileSize;
window.formatBytes = formatBytes;
window.formatDateTime = formatDateTime;
window.toLocalInputDateTime = toLocalInputDateTime;
window.parseLocalInputDateTime = parseLocalInputDateTime;
window.formatCustomDateOriginBadge = formatCustomDateOriginBadge;

class I18n {
    constructor() {
        this.currentLang = window.CURRENT_LANGUAGE || 'en';
        this.loadPromise = null;

        // Use inlined translations from the data block if available
        const translationsDataTag = document.getElementById('translations-data');
        if (translationsDataTag) {
            try {
                this.translations = JSON.parse(translationsDataTag.textContent);
                this.loaded = true;
            } catch (e) {
                console.error("Failed to parse inline translations data:", e);
                this.translations = {};
                this.loaded = false;
            }
        } else {
            this.translations = {};
            this.loaded = false;
        }
    }

    async load(lang = null) {
        if (this.loaded && (!lang || lang === this.currentLang)) {
            return;
        }

        if (this.loadPromise) {
            return this.loadPromise;
        }

        this.loadPromise = (async () => {
            try {
                const targetLang = lang || this.currentLang;
                const response = await fetch(`/api/admin/translations?lang=${targetLang}`);
                if (response.ok) {
                    this.translations = await response.json();
                    this.currentLang = targetLang;
                    this.loaded = true;
                    window.dispatchEvent(new CustomEvent('i18n-loaded'));
                }
            } catch (error) {
                console.error('Error loading translations:', error);
            }
        })();

        return this.loadPromise;
    }

    /**
     * Get a translation string by dot-notation key
     * @param {string} key - Dot-notation key (e.g., 'common.albums')
     * @param {Object} params - Interpolation parameters (e.g., {count: 5})
     * @returns {string} Translated string or the key itself if not found
     */
    t(key, params = {}) {
        if (!key) return '';
        if (typeof key === 'object') {
            return this.t(key.key || key.message, { ...key.params, ...params });
        }
        if (typeof key === 'string' && key.includes(':::')) {
            const [baseKey, arg] = key.split(':::');
            const mergedParams = { error: arg, filename: arg, ...params };
            return this.t(baseKey, mergedParams);
        }

        const keys = key.split('.');
        let value = this.translations;

        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                return key;
            }
        }

        if (typeof value !== 'string' || value === "") {
            return key;
        }

        // Handle interpolation: {name} -> replaced with params.name
        if (params && Object.keys(params).length > 0) {
            return value.replace(/\{(\w+)\}/g, (match, paramKey) => {
                return params[paramKey] !== undefined ? params[paramKey] : match;
            });
        }

        return value;
    }
}

window.i18n = new I18n();

window.getCookie = function (name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        const raw = parts.pop().split(';').shift();
        try {
            return decodeURIComponent(raw);
        } catch {
            return raw;
        }
    }
    return null;
};

window.setCookie = function (name, value, days = 365) {
    const expires = new Date();
    expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie = `${name}=${encodeURIComponent(value)};expires=${expires.toUTCString()};path=/;SameSite=Lax`;
};
