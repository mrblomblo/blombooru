(function (global) {
    'use strict';

    const PRE_SCALE_LIMIT = 512;
    const DCT_SIZE = 64;
    const BLOCK = 16;
    const MIN_COEFFICIENT_SPREAD = 10.0;
    const HEX_RE = /^[0-9a-f]{64}$/i;

    let _dctTable = null;

    function getDctTable() {
        if (_dctTable) return _dctTable;
        const table = new Float32Array(DCT_SIZE * DCT_SIZE);
        const a0 = Math.sqrt(1.0 / DCT_SIZE);
        const ak = Math.sqrt(2.0 / DCT_SIZE);
        for (let k = 0; k < DCT_SIZE; k++) {
            const alpha = k === 0 ? a0 : ak;
            for (let n = 0; n < DCT_SIZE; n++) {
                table[k * DCT_SIZE + n] = alpha * Math.cos((Math.PI * (2 * n + 1) * k) / (2 * DCT_SIZE));
            }
        }
        _dctTable = table;
        return table;
    }

    function rgbaToGreyscale(rgba, width, height) {
        const len = width * height;
        const grey = new Uint8Array(len);
        for (let i = 0, p = 0; i < len; i++, p += 4) {
            grey[i] = (rgba[p] * 19595 + rgba[p + 1] * 38470 + rgba[p + 2] * 7471 + 0x8000) >> 16;
        }
        return grey;
    }

    function linePercentiles1_50_99(line, scratch) {
        const len = line.length;
        for (let i = 0; i < len; i++) scratch[i] = line[i];
        const view = scratch.subarray(0, len);
        view.sort();

        const at = (q) => {
            const pos = ((len - 1) * q) / 100.0;
            const lo = Math.floor(pos);
            const hi = Math.ceil(pos);
            const frac = pos - lo;
            return view[lo] * (1.0 - frac) + view[hi] * frac;
        };
        return [at(1), at(50), at(99)];
    }

    function findSeam(getLine, lineLen, numLines, maxTrim) {
        if (numLines < 8 || maxTrim < 2) return 0;
        const scratch = new Uint8Array(lineLen);
        const line0 = getLine(0);
        const [p1_0, p50_0, p99_0] = linePercentiles1_50_99(line0, scratch);
        if (p99_0 - p1_0 > 8) return 0;

        const barVal = p50_0;
        let seam = -1;
        for (let r = 0; r < maxTrim; r++) {
            const line = getLine(r);
            const [p1, p50, p99] = linePercentiles1_50_99(line, scratch);
            const isBar = (p99 - p1) <= 8 && Math.abs(p50 - barVal) <= 6;
            if (!isBar) {
                seam = r;
                break;
            }
        }
        if (seam < 2) return 0;

        const before = new Uint8Array(getLine(Math.max(0, seam - 2)));
        const seamLine = new Uint8Array(getLine(seam));
        let seamChanged = 0;
        for (let i = 0; i < lineLen; i++) {
            if (Math.abs(seamLine[i] - before[i]) >= 10) seamChanged++;
        }
        const start = (seamChanged / lineLen) >= 0.60 ? seam : seam + 1;
        const endProbe = Math.min(numLines, start + 5);
        if (endProbe <= start) return 0;

        for (let r = start; r < endProbe; r++) {
            const probeLine = getLine(r);
            let diffCount = 0;
            for (let i = 0; i < lineLen; i++) {
                if (Math.abs(probeLine[i] - before[i]) >= 10) diffCount++;
            }
            if ((diffCount / lineLen) < 0.60) return 0;
        }
        return start;
    }

    function trimUniformBorders(grey, w, h) {
        if (w < 32 || h < 32) return { grey, width: w, height: h };

        const maxY = Math.floor(h * 0.35);
        const maxX = Math.floor(w * 0.35);

        const findWithRowSnapshot = (dir) => {
            // findSeam compares line[r] against before=line[seam-2], so keep two distinct buffers
            const bufA = new Uint8Array(dir === 'top' || dir === 'bottom' ? w : h);
            const bufB = new Uint8Array(bufA.length);
            let toggle = false;
            const getter = (idx) => {
                const target = toggle ? bufA : bufB;
                toggle = !toggle;
                if (dir === 'top') {
                    target.set(grey.subarray(idx * w, (idx + 1) * w));
                } else if (dir === 'bottom') {
                    const y = h - 1 - idx;
                    target.set(grey.subarray(y * w, (y + 1) * w));
                } else if (dir === 'left') {
                    for (let y = 0; y < h; y++) target[y] = grey[y * w + idx];
                } else {
                    const x = w - 1 - idx;
                    for (let y = 0; y < h; y++) target[y] = grey[y * w + x];
                }
                return target;
            };
            const numLines = (dir === 'top' || dir === 'bottom') ? Math.min(h, maxY + 7) : Math.min(w, maxX + 7);
            const maxTrim = (dir === 'top' || dir === 'bottom') ? maxY : maxX;
            return findSeam(getter, bufA.length, numLines, maxTrim);
        };

        const top = findWithRowSnapshot('top');
        const bottom = findWithRowSnapshot('bottom');
        const left = findWithRowSnapshot('left');
        const right = findWithRowSnapshot('right');

        if (top === 0 && bottom === 0 && left === 0 && right === 0) {
            return { grey, width: w, height: h };
        }

        const cw = w - left - right;
        const ch = h - top - bottom;
        if (cw < Math.max(32, Math.floor(w / 3)) || ch < Math.max(32, Math.floor(h / 3))) {
            return { grey, width: w, height: h };
        }

        const cropped = new Uint8Array(cw * ch);
        for (let y = 0; y < ch; y++) {
            const srcStart = (top + y) * w + left;
            cropped.set(grey.subarray(srcStart, srcStart + cw), y * cw);
        }
        return { grey: cropped, width: cw, height: ch };
    }

    function lanczosKernel(x) {
        if (x === 0) return 1.0;
        if (x <= -3.0 || x >= 3.0) return 0.0;
        const pix = Math.PI * x;
        return (Math.sin(pix) / pix) * (Math.sin(pix / 3.0) / (pix / 3.0));
    }

    function buildResampleWeights(srcLen, dstLen) {
        const scale = srcLen / dstLen;
        const filterScale = scale > 1.0 ? scale : 1.0;
        const support = 3.0 * filterScale;
        const taps = new Array(dstLen);
        for (let dst = 0; dst < dstLen; dst++) {
            const center = (dst + 0.5) * scale - 0.5;
            const start = Math.max(0, Math.floor(center - support));
            const end = Math.min(srcLen - 1, Math.ceil(center + support));
            const count = end - start + 1;
            const weights = new Float32Array(count);
            let sum = 0.0;
            for (let i = 0; i < count; i++) {
                const w = lanczosKernel((start + i - center) / filterScale);
                weights[i] = w;
                sum += w;
            }
            if (sum !== 0.0) {
                for (let i = 0; i < count; i++) weights[i] /= sum;
            }
            taps[dst] = { start, weights };
        }
        return taps;
    }

    function lanczosResizeGrey(src, srcW, srcH, dstW, dstH) {
        const horizTaps = buildResampleWeights(srcW, dstW);
        const horiz = new Float32Array(dstW * srcH);
        for (let y = 0; y < srcH; y++) {
            const srcRow = y * srcW;
            const dstRow = y * dstW;
            for (let x = 0; x < dstW; x++) {
                const { start, weights } = horizTaps[x];
                let acc = 0.0;
                for (let i = 0; i < weights.length; i++) {
                    acc += src[srcRow + start + i] * weights[i];
                }
                horiz[dstRow + x] = acc;
            }
        }

        const vertTaps = buildResampleWeights(srcH, dstH);
        const out = new Float32Array(dstW * dstH);
        for (let y = 0; y < dstH; y++) {
            const { start, weights } = vertTaps[y];
            const dstRow = y * dstW;
            for (let x = 0; x < dstW; x++) {
                let acc = 0.0;
                for (let i = 0; i < weights.length; i++) {
                    acc += horiz[(start + i) * dstW + x] * weights[i];
                }
                out[dstRow + x] = Math.max(0.0, Math.min(255.0, acc));
            }
        }
        return out;
    }

    function dct2d64(pixels) {
        const table = getDctTable();
        const tmp = new Float32Array(DCT_SIZE * DCT_SIZE);
        const out = new Float32Array(DCT_SIZE * DCT_SIZE);

        for (let r = 0; r < DCT_SIZE; r++) {
            const rowOff = r * DCT_SIZE;
            for (let k = 0; k < DCT_SIZE; k++) {
                const tOff = k * DCT_SIZE;
                let sum = 0.0;
                for (let n = 0; n < DCT_SIZE; n++) {
                    sum += pixels[rowOff + n] * table[tOff + n];
                }
                tmp[rowOff + k] = sum;
            }
        }

        for (let k = 0; k < DCT_SIZE; k++) {
            const tOff = k * DCT_SIZE;
            for (let c = 0; c < DCT_SIZE; c++) {
                let sum = 0.0;
                for (let r = 0; r < DCT_SIZE; r++) {
                    sum += tmp[r * DCT_SIZE + c] * table[tOff + r];
                }
                out[k * DCT_SIZE + c] = sum;
            }
        }
        return out;
    }

    function computePhashFromPixels(rgba, width, height) {
        if (!rgba || width < 1 || height < 1) return null;

        let grey = rgbaToGreyscale(rgba, width, height);
        const trimmed = trimUniformBorders(grey, width, height);
        const resized = lanczosResizeGrey(trimmed.grey, trimmed.width, trimmed.height, DCT_SIZE, DCT_SIZE);
        const dct = dct2d64(resized);

        const block = new Float32Array(BLOCK * BLOCK);
        const oddCols = new Float32Array((BLOCK * BLOCK) / 2);
        let minVal = Infinity;
        let maxVal = -Infinity;
        let oddIdx = 0;

        for (let r = 0; r < BLOCK; r++) {
            for (let c = 0; c < BLOCK; c++) {
                const v = dct[(r + 1) * DCT_SIZE + (c + 1)];
                block[r * BLOCK + c] = v;
                if (v < minVal) minVal = v;
                if (v > maxVal) maxVal = v;
                if ((c & 1) === 1) {
                    oddCols[oddIdx++] = v;
                }
            }
        }

        if (maxVal - minVal < MIN_COEFFICIENT_SPREAD) {
            return null;
        }

        oddCols.sort();
        const mid = oddCols.length >> 1;
        const median = (oddCols[mid - 1] + oddCols[mid]) * 0.5;

        const bytes = new Uint8Array((BLOCK * BLOCK) / 8);
        for (let r = 0; r < BLOCK; r++) {
            for (let c = 0; c < BLOCK; c++) {
                const v = block[r * BLOCK + c];
                const bit = (c & 1) === 1 ? (v > median) : (v > 0.0);
                if (bit) {
                    const bitIdx = r * BLOCK + c;
                    bytes[bitIdx >> 3] |= 1 << (7 - (bitIdx & 7));
                }
            }
        }

        let hex = '';
        for (let i = 0; i < bytes.length; i++) {
            hex += bytes[i].toString(16).padStart(2, '0');
        }
        return hex;
    }

    function drawToScaledRgba(source, srcWidth, srcHeight) {
        if (!srcWidth || !srcHeight) return null;
        const maxSide = Math.max(srcWidth, srcHeight);
        const scale = maxSide > PRE_SCALE_LIMIT ? PRE_SCALE_LIMIT / maxSide : 1.0;
        const w = Math.max(1, Math.round(srcWidth * scale));
        const h = Math.max(1, Math.round(srcHeight * scale));

        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) return null;

        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, w, h);
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(source, 0, 0, w, h);
        return ctx.getImageData(0, 0, w, h);
    }

    async function hashImageFile(file) {
        if (typeof createImageBitmap === 'function') {
            try {
                const bitmap = await createImageBitmap(file);
                try {
                    const imgData = drawToScaledRgba(bitmap, bitmap.width, bitmap.height);
                    if (!imgData) return { status: 'unsupported' };
                    const hash = computePhashFromPixels(imgData.data, imgData.width, imgData.height);
                    return hash ? { status: 'ok', hash } : { status: 'featureless' };
                } finally {
                    bitmap.close();
                }
            } catch (_) {
                // Fall back to HTMLImageElement below
            }
        }

        const url = URL.createObjectURL(file);
        try {
            const img = await new Promise((resolve, reject) => {
                const el = new Image();
                el.onload = () => resolve(el);
                el.onerror = () => reject(new Error('Image decode failed'));
                el.src = url;
            });
            const w = img.naturalWidth || img.width;
            const h = img.naturalHeight || img.height;
            const imgData = drawToScaledRgba(img, w, h);
            if (!imgData) return { status: 'unsupported' };
            const hash = computePhashFromPixels(imgData.data, imgData.width, imgData.height);
            return hash ? { status: 'ok', hash } : { status: 'featureless' };
        } catch (_) {
            return { status: 'unsupported' };
        } finally {
            URL.revokeObjectURL(url);
        }
    }

    async function hashVideoFile(file) {
        const url = URL.createObjectURL(file);
        const video = document.createElement('video');
        video.muted = true;
        video.playsInline = true;
        video.preload = 'auto';

        try {
            await new Promise((resolve, reject) => {
                let done = false;
                const timer = setTimeout(() => {
                    if (!done) {
                        done = true;
                        reject(new Error('Video load timed out'));
                    }
                }, 10000);

                const finish = () => {
                    if (!done) {
                        done = true;
                        clearTimeout(timer);
                        resolve();
                    }
                };
                const fail = () => {
                    if (!done) {
                        done = true;
                        clearTimeout(timer);
                        reject(new Error('Video decode failed'));
                    }
                };

                video.addEventListener('error', fail, { once: true });
                video.addEventListener('loadedmetadata', () => {
                    const targetTime = (Number.isFinite(video.duration) && video.duration > 0.2)
                        ? video.duration * 0.5
                        : 0;
                    if (targetTime > 0) {
                        video.addEventListener('seeked', finish, { once: true });
                        try {
                            video.currentTime = targetTime;
                        } catch (_) {
                            video.addEventListener('loadeddata', finish, { once: true });
                        }
                    } else if (video.readyState >= 2) {
                        finish();
                    } else {
                        video.addEventListener('loadeddata', finish, { once: true });
                    }
                }, { once: true });

                video.src = url;
                video.load();
            });

            const w = video.videoWidth;
            const h = video.videoHeight;
            if (!w || !h) return { status: 'unsupported' };
            const imgData = drawToScaledRgba(video, w, h);
            if (!imgData) return { status: 'unsupported' };
            const hash = computePhashFromPixels(imgData.data, imgData.width, imgData.height);
            return hash ? { status: 'ok', hash } : { status: 'featureless' };
        } catch (_) {
            return { status: 'unsupported' };
        } finally {
            video.removeAttribute('src');
            video.load();
            URL.revokeObjectURL(url);
        }
    }

    function classifyMediaFile(file) {
        const mime = (file.type || '').toLowerCase();
        if (mime.startsWith('image/')) return 'image';
        if (mime.startsWith('video/')) return 'video';

        const name = file.name || '';
        const dot = name.lastIndexOf('.');
        const ext = dot !== -1 ? name.slice(dot + 1).toLowerCase() : '';
        if (!ext) return null;

        if (global.FormatRegistry) {
            if (global.FormatRegistry.isVideo(name)) return 'video';
            if (global.FormatRegistry.isImage(name) || global.FormatRegistry.isGif(name)) return 'image';
        }
        if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'avif', 'svg', 'ico'].includes(ext)) return 'image';
        if (['mp4', 'webm', 'mov', 'm4v'].includes(ext)) return 'video';
        return null;
    }

    async function hashFile(file) {
        if (!file) return { status: 'unsupported' };
        const kind = classifyMediaFile(file);
        if (kind === 'video') return hashVideoFile(file);
        if (kind === 'image') return hashImageFile(file);
        return { status: 'unsupported' };
    }

    function normalizeSimilarToken(token) {
        const trimmed = String(token || '').trim().replace(/^\[+|\]+$/g, '');
        if (!trimmed) return '';
        return HEX_RE.test(trimmed) ? trimmed.toLowerCase() : trimmed;
    }

    function mergeSimilarToQuery(existingQuery, newTokens) {
        const normalizedNew = [];
        for (const t of newTokens || []) {
            const norm = normalizeSimilarToken(t);
            if (norm && !normalizedNew.includes(norm)) normalizedNew.push(norm);
        }
        if (normalizedNew.length === 0) return existingQuery || '';

        const raw = (existingQuery || '').trim();
        if (!raw) {
            return `similar_to:${normalizedNew.join(',')}`;
        }

        const tokenRegex = /(-?)(?:([a-zA-Z0-9_]+):)?("[^"]*"|[^\s"]+)/g;
        const parts = [];
        let merged = false;
        let match;

        while ((match = tokenRegex.exec(raw)) !== null) {
            const fullToken = match[0];
            const isNegated = Boolean(match[1]);
            const key = match[2] ? match[2].toLowerCase() : null;
            const rawVal = match[3] || '';

            if (!merged && !isNegated && key === 'similar_to') {
                const unquoted = rawVal.replace(/^"|"$/g, '');
                const current = unquoted.split(/[,\s\[\]]+/).map(normalizeSimilarToken).filter(Boolean);
                const seen = new Set(current);
                for (const tok of normalizedNew) {
                    if (!seen.has(tok)) {
                        seen.add(tok);
                        current.push(tok);
                    }
                }
                parts.push(`similar_to:${current.join(',')}`);
                merged = true;
            } else {
                parts.push(fullToken);
            }
        }

        if (!merged) {
            parts.push(`similar_to:${normalizedNew.join(',')}`);
        }

        const combined = parts.join(' ');
        return typeof global.canonicalizeQuery === 'function' ? global.canonicalizeQuery(combined) : combined;
    }

    function extractLocalMediaId(dataTransfer) {
        if (!dataTransfer) return null;
        const uriList = dataTransfer.getData('text/uri-list') || dataTransfer.getData('text/plain') || '';
        const firstLine = uriList
            .split(/\r?\n/)
            .map(l => l.trim())
            .find(l => l && !l.startsWith('#'));
        if (!firstLine) return null;

        try {
            const parsed = new URL(firstLine, global.location.origin);
            if (parsed.origin !== global.location.origin) return null;
            const m = parsed.pathname.match(/^\/(?:album\/\d+\/)?media\/(\d+)\/?$/);
            return m ? m[1] : null;
        } catch (_) {
            return null;
        }
    }

    function syncHeaderSearchInputs(sourceInput) {
        const desktop = document.getElementById('search-input');
        const mobile = document.getElementById('search-input-mobile');
        if (sourceInput === desktop && mobile) {
            mobile.value = desktop.value;
        } else if (sourceInput === mobile && desktop) {
            desktop.value = mobile.value;
        }
    }

    function notify(key, fallback, type = 'warning') {
        if (global.app && typeof global.app.showNotification === 'function') {
            const translated = global.i18n ? global.i18n.t(key) : key;
            const message = translated && translated !== key ? translated : fallback;
            global.app.showNotification(message, type);
        }
    }

    const SearchMediaDrop = {
        mergeSimilarToQuery,

        attach(input) {
            if (!input || input.dataset.ndDropAttached === '1') return;
            input.dataset.ndDropAttached = '1';

            const acceptsDrag = (e) => {
                const types = Array.from(e.dataTransfer?.types || []);
                return types.includes('Files') || types.includes('text/uri-list');
            };

            input.addEventListener('dragenter', (e) => {
                if (!acceptsDrag(e)) return;
                e.preventDefault();
                input.classList.add('search-drop-active');
            });

            input.addEventListener('dragover', (e) => {
                if (!acceptsDrag(e)) return;
                e.preventDefault();
                if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
                input.classList.add('search-drop-active');
            });

            input.addEventListener('dragleave', () => {
                input.classList.remove('search-drop-active');
            });

            input.addEventListener('drop', async (e) => {
                input.classList.remove('search-drop-active');
                const files = Array.from(e.dataTransfer?.files || []);

                if (files.length > 0) {
                    e.preventDefault();
                    e.stopPropagation();

                    const results = await Promise.all(files.map(f => hashFile(f)));
                    const hashes = results.filter(r => r.status === 'ok').map(r => r.hash);

                    if (hashes.length > 0) {
                        input.value = mergeSimilarToQuery(input.value, hashes);
                        syncHeaderSearchInputs(input);
                        input.focus();
                    }

                    const failed = results.filter(r => r.status !== 'ok');
                    if (failed.length > 0) {
                        const onlyFeatureless = failed.every(r => r.status === 'featureless');
                        if (onlyFeatureless) {
                            notify(
                                'search.similar_drop_featureless',
                                'Image has too little detail to compute a perceptual hash.'
                            );
                        } else {
                            notify(
                                'search.similar_drop_unsupported',
                                'Could not compute perceptual hash for the dropped file in this browser.'
                            );
                        }
                    }
                    return;
                }

                const mediaId = extractLocalMediaId(e.dataTransfer);
                if (mediaId) {
                    e.preventDefault();
                    e.stopPropagation();
                    input.value = mergeSimilarToQuery(input.value, [mediaId]);
                    syncHeaderSearchInputs(input);
                    input.focus();
                }
            });
        },

        init() {
            ['search-input', 'search-input-mobile', 'search-input-404'].forEach((id) => {
                const el = document.getElementById(id);
                if (el) SearchMediaDrop.attach(el);
            });
        }
    };

    const PdqHasher = {
        computePhashFromPixels,
        drawToScaledRgba,
        trimUniformBorders,
        lanczosResizeGrey,
        dct2d64,
        hashImageFile,
        hashVideoFile,
        hashFile
    };

    global.PdqHasher = PdqHasher;
    global.SearchMediaDrop = SearchMediaDrop;

    if (typeof document !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => SearchMediaDrop.init());
        } else {
            SearchMediaDrop.init();
        }
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { PdqHasher, SearchMediaDrop };
    }
})(typeof window !== 'undefined' ? window : globalThis);
