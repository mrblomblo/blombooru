class NearDuplicateView {
    static t(key, params) {
        return window.i18n.t(`upload.near_duplicates.${key}`, params);
    }

    static formatDuration(seconds) {
        if (!seconds || seconds < 0) return '-';
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${minutes}:${String(secs).padStart(2, '0')}`;
    }

    static formatLabel(mimeType, filename) {
        const fromMime = mimeType && mimeType.split('/')[1];
        if (fromMime) {
            return fromMime.replace(/^x-/, '').split('+')[0].toUpperCase();
        }
        const ext = filename && filename.includes('.') ? filename.split('.').pop() : '';
        return ext ? ext.toUpperCase() : '-';
    }

    static typeLabel(entry) {
        return `${escapeHtml(entry.file_type || '-')} · ${escapeHtml(NearDuplicateView.formatLabel(entry.mime_type, entry.filename))}`;
    }

    static pixels(entry) {
        return entry.width && entry.height ? entry.width * entry.height : 0;
    }

    static percentDelta(value, reference) {
        if (!value || !reference) return null;
        const delta = Math.round((value / reference - 1) * 100);
        if (delta === 0) return '±0%';
        return `${delta > 0 ? '+' : '-'}${Math.abs(delta)}%`;
    }

    /* Normalise the current item and its matches into one flat list of comparison entries. */
    static buildEntries(item, matches, session) {
        const queueBase = `/api/uploads/sessions/${session.sessionId}/items`;
        const self = {
            kind: 'self',
            key: item.item_id,
            item_id: item.item_id,
            filename: item.filename,
            file_type: item.file_type,
            mime_type: item.mime_type,
            width: item.width,
            height: item.height,
            file_size: item.file_size,
            duration: item.duration,
            thumbUrl: `${queueBase}/${item.item_id}/thumbnail`,
            fileUrl: `${queueBase}/${item.item_id}/file`,
        };
        const existing = (matches.existing || []).map(m => ({
            ...m,
            kind: 'existing',
            key: `post-${m.media_id}`,
            thumbUrl: m.thumbnail_url,
            fileUrl: m.file_url,
        }));
        const queue = (matches.queue || []).map(m => ({
            ...m,
            kind: 'queue',
            key: m.item_id,
            thumbUrl: `${queueBase}/${m.item_id}/thumbnail`,
            fileUrl: `${queueBase}/${m.item_id}/file`,
        }));
        const relation = {
            parent: item.parent_media_id || null,
            children: (item.child_media_ids || []).map(Number),
        };
        return { self, existing, queue, relation, all: [self, ...existing, ...queue] };
    }

    /* None if all values are equal. */
    static bestKeys(entries, valueFn) {
        const values = entries.map(e => ({ key: e.key, value: valueFn(e) })).filter(v => v.value > 0);
        if (values.length < 2) return new Set();
        const max = Math.max(...values.map(v => v.value));
        if (values.every(v => v.value === max)) return new Set();
        return new Set(values.filter(v => v.value === max).map(v => v.key));
    }

    static renderSimilarity(entry) {
        if (entry.kind === 'self') return '<span class="text-secondary">-</span>';
        const t = NearDuplicateView.t;
        return `
            <div class="flex items-center justify-between gap-2" title="${escapeHtml(t('distance_hint', { distance: entry.distance }))}">
                <span class="font-bold">${Number(entry.similarity).toFixed(1)}%</span>
                <span class="text-secondary text-right">${escapeHtml(t(`confidence_${entry.confidence || 'similar'}`))}</span>
            </div>`;
    }

    static valueWithDelta(valueHtml, delta, isBest) {
        return `<span class="${isBest ? 'text-success' : ''}">${valueHtml}</span>${delta ? ` <span class="text-secondary">${delta}</span>` : ''}`;
    }

    static relationStatusHtml(entry, relation) {
        const t = NearDuplicateView.t;
        if (entry.kind === 'self') {
            if (relation.parent) {
                return `<span class="text-primary font-bold">${escapeHtml(t('pending_child_of', { id: relation.parent }))}</span>`;
            }
            if (relation.children.length) {
                const ids = relation.children.map(id => `#${id}`).join(', ');
                return `<span class="text-primary font-bold">${escapeHtml(t('pending_parent_of', { ids }))}</span>`;
            }
            return '';
        }
        if (entry.kind === 'existing') {
            if (entry.parent_id) {
                return `<span class="text-secondary">${escapeHtml(t('existing_child_of', { id: entry.parent_id }))}</span>`;
            }
            if (entry.children_count > 0) {
                const key = entry.children_count === 1 ? 'existing_parent_of_one' : 'existing_parent_of';
                return `<span class="text-secondary">${escapeHtml(t(key, { count: entry.children_count }))}</span>`;
            }
        }
        return '';
    }

    static renderActions(entry, relation) {
        const t = NearDuplicateView.t;
        const btn = 'btn flex-1 px-2 py-1.5 whitespace-nowrap';
        const remove = window.i18n.t('common.remove');
        if (entry.kind === 'self') {
            return `<div class="flex flex-wrap gap-1"><button type="button" class="btn-danger flex-1 px-2 py-1.5" data-nd-remove="${escapeHtml(entry.item_id)}">${escapeHtml(remove)}</button></div>`;
        }
        if (entry.kind === 'queue') {
            return `<div class="flex flex-wrap gap-1">
                <button type="button" class="${btn}" data-nd-select="${escapeHtml(entry.item_id)}">${escapeHtml(t('show'))}</button>
                <button type="button" class="btn-danger flex-1 px-2 py-1.5" data-nd-remove="${escapeHtml(entry.item_id)}">${escapeHtml(remove)}</button>
            </div>`;
        }

        const mediaId = Number(entry.media_id);
        const toggle = (kind, pressed, label, extraClass = '') => `
            <button type="button" class="${pressed ? 'btn-primary' : 'btn'} px-1.5 py-1.5 whitespace-nowrap ${extraClass}"
                data-nd-relate="${kind}" data-nd-key="${escapeHtml(entry.key)}" aria-pressed="${pressed ? 'true' : 'false'}">
                ${escapeHtml(label)}
            </button>`;

        let relationButtons;
        if (entry.parent_id) {
            const isSibling = relation.parent === Number(entry.parent_id);
            relationButtons = toggle(
                'sibling', isSibling, t('upload_as_sibling'), 'col-span-full'
            );
        } else if (entry.children_count > 0) {
            const isChild = relation.parent === mediaId;
            relationButtons = toggle(
                'child', isChild, t('upload_as_child'), 'col-span-full'
            );
        } else {
            const isChild = relation.parent === mediaId;
            const isParent = relation.children.includes(mediaId);
            relationButtons = `
                ${toggle('child', isChild, t('upload_as_child'))}
                ${toggle('parent', isParent, t('upload_as_parent'))}`;
        }

        return `<div class="grid grid-cols-2 gap-1">
            <a class="${btn}" href="${escapeHtml(entry.page_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(t('open_post'))}</a>
            <button type="button" class="${btn}" data-nd-update="${escapeHtml(entry.key)}">${escapeHtml(window.i18n.t('media.actions.update_post'))}</button>
            ${relationButtons}
        </div>`;
    }

    static renderThumb(entry, extraClass = '') {
        const t = NearDuplicateView.t;
        const clickable = entry.kind !== 'self';
        return `
            <button type="button" class="nd-thumb-btn relative bg border block p-0 ${extraClass}"
                ${clickable ? `data-nd-compare="${escapeHtml(entry.key)}" title="${escapeHtml(t('compare'))}"` : 'disabled'}
                aria-label="${escapeHtml(clickable ? t('compare') : entry.filename)}">
                <img class="nd-thumb" src="${escapeHtml(entry.thumbUrl)}" alt="" onerror="this.style.visibility='hidden'">
                ${clickable ? `<span class="absolute top-1 right-1 surface border p-0.5 flex">${window.Icons.search({ size: 12 })}</span>` : ''}
            </button>`;
    }

    static renderMatrix(structure) {
        const t = NearDuplicateView.t;
        const entries = structure.all;
        const self = structure.self;
        const bestPixels = NearDuplicateView.bestKeys(entries, NearDuplicateView.pixels);
        const bestSize = NearDuplicateView.bestKeys(entries, e => e.file_size || 0);
        const hasDuration = entries.some(e => e.duration && e.duration > 0);

        const cell = (entry, html, cls = '') =>
            `<td class="${entry.kind === 'self' ? 'surface ' : ''}${cls}">${html}</td>`;
        const row = (label, fn) =>
            `<tr><th class="nd-label surface text-secondary" scope="row">${escapeHtml(label)}</th>${entries.map(fn).join('')}</tr>`;

        const groupCells = [
            `<th class="nd-label surface"></th>`,
            `<th class="surface text-secondary"><span class="nd-group-label">${escapeHtml(t('this_upload'))}</span></th>`
        ];
        if (structure.existing.length) {
            groupCells.push(`<th class="surface text-secondary" colspan="${structure.existing.length}"><span class="nd-group-label">${escapeHtml(t('group_existing', { count: structure.existing.length }))}</span></th>`);
        }
        if (structure.queue.length) {
            groupCells.push(`<th class="surface text-secondary" colspan="${structure.queue.length}"><span class="nd-group-label">${escapeHtml(t('group_queue', { count: structure.queue.length }))}</span></th>`);
        }

        const rows = [];
        rows.push(row(window.i18n.t('common.preview'), entry => cell(entry, NearDuplicateView.renderThumb(entry, 'w-full'))));
        rows.push(row(window.i18n.t('media.info.filename'), entry => cell(entry,
            `<span class="nd-name font-mono" title="${escapeHtml(entry.filename)}">${escapeHtml(entry.filename)}</span>`)));
        rows.push(row(t('match'), entry => cell(entry, NearDuplicateView.renderSimilarity(entry))));
        rows.push(row(window.i18n.t('media.info.type'), entry => cell(entry, NearDuplicateView.typeLabel(entry))));
        rows.push(row(window.i18n.t('media.info.dimensions'), entry => {
            const px = NearDuplicateView.pixels(entry);
            if (!px) return cell(entry, '-');
            const delta = entry.kind === 'self' ? null : NearDuplicateView.percentDelta(px, NearDuplicateView.pixels(self));
            return cell(entry, NearDuplicateView.valueWithDelta(`${entry.width}×${entry.height}`, delta, bestPixels.has(entry.key)));
        }));
        rows.push(row(window.i18n.t('media.info.size'), entry => {
            const delta = entry.kind === 'self' ? null : NearDuplicateView.percentDelta(entry.file_size, self.file_size);
            return cell(entry, NearDuplicateView.valueWithDelta(escapeHtml(formatFileSize(entry.file_size, { fallback: '-' })), delta, bestSize.has(entry.key)));
        }));
        if (hasDuration) {
            rows.push(row(window.i18n.t('media.info.duration'), entry =>
                cell(entry, escapeHtml(NearDuplicateView.formatDuration(entry.duration)))));
        }
        if (structure.existing.length > 0) {
            rows.push(row(t('relations_label'), entry =>
                `<td class="${entry.kind === 'self' ? 'surface ' : ''}" data-nd-relation-cell="${escapeHtml(entry.key)}">${NearDuplicateView.relationStatusHtml(entry, structure.relation) || '<span class="text-secondary">-</span>'}</td>`));
        }
        rows.push(row(window.i18n.t('common.actions'), entry =>
            cell(entry, NearDuplicateView.renderActions(entry, structure.relation))));

        const cols = [`<col class="nd-label">`, ...entries.map(() => '<col>')];
        return `
            <div class="nd-scroll">
                <table class="nd-table text-xs">
                    <colgroup>${cols.join('')}</colgroup>
                    <thead><tr>${groupCells.join('')}</tr></thead>
                    <tbody>${rows.join('')}</tbody>
                </table>
            </div>`;
    }

    static renderCards(structure) {
        const t = NearDuplicateView.t;
        const entries = structure.all;
        const self = structure.self;
        const bestPixels = NearDuplicateView.bestKeys(entries, NearDuplicateView.pixels);
        const bestSize = NearDuplicateView.bestKeys(entries, e => e.file_size || 0);

        const kv = (label, valueHtml) => `
            <div class="min-w-0">
                <div class="text-secondary text-[10px] uppercase tracking-wide">${escapeHtml(label)}</div>
                <div class="truncate">${valueHtml}</div>
            </div>`;

        const renderCard = (entry) => {
            const px = NearDuplicateView.pixels(entry);
            const pxDelta = entry.kind === 'self' || !px ? null : NearDuplicateView.percentDelta(px, NearDuplicateView.pixels(self));
            const sizeDelta = entry.kind === 'self' ? null : NearDuplicateView.percentDelta(entry.file_size, self.file_size);
            const stats = [
                kv(window.i18n.t('media.info.type'), NearDuplicateView.typeLabel(entry)),
                kv(window.i18n.t('media.info.dimensions'), px
                    ? NearDuplicateView.valueWithDelta(`${entry.width}×${entry.height}`, pxDelta, bestPixels.has(entry.key)) : '-'),
                kv(window.i18n.t('media.info.size'),
                    NearDuplicateView.valueWithDelta(escapeHtml(formatFileSize(entry.file_size, { fallback: '-' })), sizeDelta, bestSize.has(entry.key))),
            ];
            if (entry.duration) {
                stats.push(kv(window.i18n.t('media.info.duration'), escapeHtml(NearDuplicateView.formatDuration(entry.duration))));
            }
            const relationHtml = NearDuplicateView.relationStatusHtml(entry, structure.relation);
            if (entry.kind === 'self' || relationHtml) {
                stats.push(`
                    <div class="min-w-0" data-nd-relation-card="${escapeHtml(entry.key)}" style="${relationHtml ? '' : 'display:none;'}">
                        <div class="text-secondary text-[10px] uppercase tracking-wide">${escapeHtml(t('relations_label'))}</div>
                        <div class="truncate" data-nd-relation-card-value>${relationHtml}</div>
                    </div>`);
            }

            const actions = entry.kind === 'self' ? '' :
                `<div class="px-2 pb-2">${NearDuplicateView.renderActions(entry, structure.relation)}</div>`;

            return `
                <section class="nd-card ${entry.kind === 'self' ? 'surface' : 'bg'} border">
                    <div class="nd-card-main p-2">
                        ${NearDuplicateView.renderThumb(entry, 'nd-card-thumb')}
                        <div class="min-w-0 flex flex-col justify-center gap-1">
                            <span class="nd-card-name font-mono" title="${escapeHtml(entry.filename)}">${escapeHtml(entry.filename)}</span>
                            ${entry.kind === 'self' ? '' : NearDuplicateView.renderSimilarity(entry)}
                        </div>
                    </div>
                    <div class="nd-card-stats px-2 pb-2">${stats.join('')}</div>
                    ${actions}
                </section>`;
        };

        const group = (label, list) => list.length ? `
            <h4 class="text-secondary text-[10px] uppercase tracking-wide font-bold mt-1">${escapeHtml(label)}</h4>${list.map(renderCard).join('')}` : '';

        return `
            <div class="nd-cards">
                <h4 class="text-secondary text-[10px] uppercase tracking-wide font-bold">${escapeHtml(t('this_upload'))}</h4>
                ${renderCard(self)}
                ${group(t('group_existing', { count: structure.existing.length }), structure.existing)}
                ${group(t('group_queue', { count: structure.queue.length }), structure.queue)}
            </div>`;
    }

    /* '' if none. */
    static renderPanel(item, session, expanded = true) {
        const matches = session.getNearDuplicates(item.item_id);
        const total = matches ? (matches.existing || []).length + (matches.queue || []).length : 0;
        if (!total) return '';

        const structure = NearDuplicateView.buildEntries(item, matches, session);
        return `
            <div class="nd-panel bg border mb-3" id="editor-near-duplicates" data-expanded="${expanded ? 'true' : 'false'}">
                <button type="button" id="editor-near-duplicates-toggle"
                    class="w-full flex items-center gap-2 p-2 text-xs font-bold text-left cursor-pointer hover:surface transition-colors"
                    aria-expanded="${expanded ? 'true' : 'false'}">
                    <span class="flex-1 min-w-0 truncate">${escapeHtml(NearDuplicateView.t('panel_title', { count: total }))}</span>
                    <span class="nd-chevron">${window.Icons.chevronDown({ size: 14 })}</span>
                </button>
                <div class="nd-panel-body p-2 border-t">
                    ${NearDuplicateView.renderMatrix(structure)}
                    ${NearDuplicateView.renderCards(structure)}
                </div>
            </div>`;
    }

    static bindPanel(container, item, session, handlers = {}) {
        const panel = container.querySelector('#editor-near-duplicates');
        if (!panel) return;

        const toggle = panel.querySelector('#editor-near-duplicates-toggle');
        toggle?.addEventListener('click', () => {
            const expanded = panel.dataset.expanded !== 'true';
            panel.dataset.expanded = expanded ? 'true' : 'false';
            toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            NearDuplicateView._panelExpanded = expanded;
        });

        const table = panel.querySelector('.nd-table');
        const labelCell = table?.querySelector('th.nd-label');
        if (table && labelCell) {
            const syncLabelWidth = () => {
                const width = labelCell.getBoundingClientRect().width;
                if (width > 0) table.style.setProperty('--nd-label-w', `${width}px`);
            };
            syncLabelWidth();
            if (typeof ResizeObserver !== 'undefined') {
                new ResizeObserver(syncLabelWidth).observe(labelCell);
            }
        }

        const structure = NearDuplicateView.buildEntries(item, session.getNearDuplicates(item.item_id), session);
        const byKey = new Map(structure.all.map(e => [e.key, e]));

        panel.querySelectorAll('[data-nd-compare]').forEach(btn => {
            btn.addEventListener('click', () => {
                const other = byKey.get(btn.dataset.ndCompare);
                if (other && other.kind !== 'self') {
                    NearDuplicateView.openCompare(structure.self, other, structure);
                }
            });
        });
        panel.querySelectorAll('[data-nd-select]').forEach(btn => {
            btn.addEventListener('click', () => handlers.onSelect?.(btn.dataset.ndSelect));
        });
        panel.querySelectorAll('[data-nd-remove]').forEach(btn => {
            btn.addEventListener('click', () => handlers.onRemove?.(btn.dataset.ndRemove));
        });
        panel.querySelectorAll('[data-nd-relate]').forEach(btn => {
            btn.addEventListener('click', () => {
                const target = byKey.get(btn.dataset.ndKey);
                if (target) handlers.onRelate?.(target, btn.dataset.ndRelate);
            });
        });
        panel.querySelectorAll('[data-nd-update]').forEach(btn => {
            btn.addEventListener('click', () => {
                const target = byKey.get(btn.dataset.ndUpdate);
                if (target) handlers.onUpdatePost?.(target);
            });
        });
    }

    static updateRelations(container, item, session) {
        const panel = container.querySelector('#editor-near-duplicates');
        const matches = session.getNearDuplicates(item.item_id);
        if (!panel || !matches) return false;

        const structure = NearDuplicateView.buildEntries(item, matches, session);
        const byKey = new Map(structure.all.map(e => [e.key, e]));
        const relation = structure.relation;

        panel.querySelectorAll('[data-nd-relate]').forEach(btn => {
            const entry = byKey.get(btn.dataset.ndKey);
            if (!entry) return;
            const kind = btn.dataset.ndRelate;
            let pressed = false;
            if (kind === 'sibling') {
                pressed = relation.parent === Number(entry.parent_id);
            } else if (kind === 'child') {
                pressed = relation.parent === Number(entry.media_id);
            } else if (kind === 'parent') {
                pressed = relation.children.includes(Number(entry.media_id));
            }
            btn.classList.toggle('btn-primary', pressed);
            btn.classList.toggle('btn', !pressed);
            btn.setAttribute('aria-pressed', pressed ? 'true' : 'false');
        });

        panel.querySelectorAll('[data-nd-relation-cell]').forEach(td => {
            const entry = byKey.get(td.dataset.ndRelationCell);
            if (!entry) return;
            td.innerHTML = NearDuplicateView.relationStatusHtml(entry, relation) || '<span class="text-secondary">-</span>';
        });

        panel.querySelectorAll('[data-nd-relation-card]').forEach(cardStat => {
            const entry = byKey.get(cardStat.dataset.ndRelationCard);
            if (!entry) return;
            const html = NearDuplicateView.relationStatusHtml(entry, relation);
            const valueEl = cardStat.querySelector('[data-nd-relation-card-value]');
            if (valueEl) valueEl.innerHTML = html;
            cardStat.style.display = html ? '' : 'none';
        });

        return true;
    }

    static renderMedia(entry, { controls = false, extraClass = '' } = {}) {
        if (entry.file_type === 'video') {
            return `<video class="${extraClass}" src="${escapeHtml(entry.fileUrl)}" ${controls ? 'controls' : ''} muted loop autoplay playsinline></video>`;
        }
        return `<img class="${extraClass}" src="${escapeHtml(entry.fileUrl)}" alt="${escapeHtml(entry.filename)}">`;
    }

    /* The better one of the pair is green. */
    static renderPairStats(entry, other) {
        const px = NearDuplicateView.pixels(entry);
        const otherPx = NearDuplicateView.pixels(other);
        const betterRes = px && otherPx && px > otherPx;
        const betterSize = entry.file_size && other.file_size && entry.file_size > other.file_size;

        const parts = [
            px ? `<span class="${betterRes ? 'text-success' : ''}">${entry.width}×${entry.height}</span>` : null,
            escapeHtml(NearDuplicateView.formatLabel(entry.mime_type, entry.filename)),
            entry.file_size ? `<span class="${betterSize ? 'text-success' : ''}">${escapeHtml(formatFileSize(entry.file_size))}</span>` : null,
            entry.duration ? escapeHtml(NearDuplicateView.formatDuration(entry.duration)) : null,
        ].filter(Boolean);
        return `<div class="text-xs text-secondary">${parts.join(' · ')}</div>`;
    }

    /* Aspect ratio of the larger of the two media. */
    static referenceAspect(a, b) {
        const larger = NearDuplicateView.pixels(a) >= NearDuplicateView.pixels(b) ? a : b;
        const fallback = larger === a ? b : a;
        const pick = (larger.width && larger.height) ? larger : fallback;
        return pick.width && pick.height ? (pick.width / pick.height) : 1;
    }

    static openCompare(selfEntry, otherEntry, structure = null) {
        NearDuplicateView.closeCompare();
        const t = NearDuplicateView.t;

        const others = structure ? [...structure.existing, ...structure.queue] : [otherEntry];
        let current = otherEntry;
        let mode = 'side';
        let blinkShowsOther = true;

        const overlay = document.createElement('div');
        overlay.id = 'nd-compare-modal';
        overlay.className = 'fixed inset-0 flex items-center justify-center z-50';
        overlay.style.background = 'rgba(0, 0, 0, 0.5)';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', t('compare'));
        document.body.appendChild(overlay);
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';

        const sourceLabel = (entry) => entry.kind === 'existing' ? t('in_library') : t('in_queue');

        const renderBody = () => {
            const ar = NearDuplicateView.referenceAspect(selfEntry, current);
            const style = `--nd-ar: ${ar};`;
            if (mode === 'side') {
                const pane = (entry, other, label) => `
                    <figure class="nd-pane min-w-0">
                        <figcaption class="text-xs mb-1 min-w-0">
                            <div class="font-bold">${escapeHtml(label)}</div>
                            <div class="nd-name font-mono text-secondary" title="${escapeHtml(entry.filename)}">${escapeHtml(entry.filename)}</div>
                        </figcaption>
                        <div class="nd-stage bg border" style="${style}">${NearDuplicateView.renderMedia(entry, { controls: true })}</div>
                        <div class="mt-1">${NearDuplicateView.renderPairStats(entry, other)}</div>
                    </figure>`;
                return `<div class="nd-compare-grid">
                    ${pane(selfEntry, current, t('this_upload'))}
                    ${pane(current, selfEntry, sourceLabel(current))}
                </div>`;
            }
            const shown = blinkShowsOther ? current : selfEntry;
            const other = blinkShowsOther ? selfEntry : current;
            return `
                <div class="nd-blink">
                    <div class="text-xs mb-1 min-w-0">
                        <div class="font-bold" id="nd-blink-label">${escapeHtml(blinkShowsOther ? sourceLabel(current) : t('this_upload'))}</div>
                        <div class="nd-name font-mono text-secondary" id="nd-blink-name" title="${escapeHtml(shown.filename)}">${escapeHtml(shown.filename)}</div>
                    </div>
                    <div class="nd-stage nd-blink-stage bg border" id="nd-blink-stage" style="${style}" tabindex="0" role="button"
                        aria-label="${escapeHtml(t('blink_hint'))}" title="${escapeHtml(t('blink_hint'))}">
                        ${NearDuplicateView.renderMedia(selfEntry, { extraClass: blinkShowsOther ? 'nd-hidden' : '' })}
                        ${NearDuplicateView.renderMedia(current, { extraClass: blinkShowsOther ? '' : 'nd-hidden' })}
                    </div>
                    <div class="mt-1" id="nd-blink-stats">${NearDuplicateView.renderPairStats(shown, other)}</div>
                    <p class="text-xs text-secondary mt-2 mb-0">${escapeHtml(t('blink_hint'))}</p>
                </div>`;
        };

        const render = () => {
            const index = others.findIndex(o => o.key === current.key);
            const modeBtn = (id, label, active) => `
                <button type="button" id="${id}" class="flex-1 sm:flex-none min-h-12 sm:min-h-0 px-3 sm:px-5 py-3 sm:py-2 ${active ? 'btn-primary' : 'btn'} text-sm font-medium cursor-pointer"
                    aria-pressed="${active ? 'true' : 'false'}">${escapeHtml(label)}</button>`;

            overlay.innerHTML = `
                <div class="surface p-2 sm:p-6 border shadow-2xl w-full max-w-5xl mx-2 sm:mx-4 max-h-[90vh] flex flex-col">
                    <div class="flex items-center justify-between gap-3 mb-3 flex-shrink-0">
                        <h2 class="text-base sm:text-lg font-bold truncate">${escapeHtml(t('compare'))}</h2>
                        <div class="text-xs shrink-0 min-w-0 truncate">
                            <span class="font-bold">${Number(current.similarity).toFixed(1)}%</span>
                            <span class="text-secondary">· ${escapeHtml(t(`confidence_${current.confidence || 'similar'}`))}</span>
                        </div>
                    </div>
                    <div id="nd-compare-body" class="flex-1 min-h-0 overflow-auto">${renderBody()}</div>
                    <div class="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 mt-4 flex-shrink-0">
                        <div class="flex items-center gap-2 ${others.length > 1 ? '' : 'invisible'}">
                            <button type="button" id="nd-prev" class="btn px-3 py-2" aria-label="${escapeHtml(window.i18n.t('common.previous'))}" ${index <= 0 ? 'disabled' : ''}>
                                ${window.Icons.chevronLeft({ size: 14 })}</button>
                            <span class="text-xs text-secondary">${index + 1} / ${others.length}</span>
                            <button type="button" id="nd-next" class="btn px-3 py-2" aria-label="${escapeHtml(window.i18n.t('common.next'))}" ${index >= others.length - 1 ? 'disabled' : ''}>
                                ${window.Icons.chevronRight({ size: 14 })}</button>
                        </div>
                        <div class="flex gap-2">
                            ${modeBtn('nd-mode-side', t('mode_side'), mode === 'side')}
                            ${modeBtn('nd-mode-blink', t('mode_blink'), mode === 'blink')}
                            <button type="button" id="nd-close" class="flex-1 sm:flex-none min-h-12 sm:min-h-0 px-3 sm:px-5 py-3 sm:py-2 btn text-sm font-medium cursor-pointer">
                                ${escapeHtml(window.i18n.t('common.close'))}</button>
                        </div>
                    </div>
                </div>`;

            const q = (sel) => overlay.querySelector(sel);
            q('#nd-close').addEventListener('click', NearDuplicateView.closeCompare);
            q('#nd-mode-side').addEventListener('click', () => { mode = 'side'; render(); });
            q('#nd-mode-blink').addEventListener('click', () => { mode = 'blink'; blinkShowsOther = true; render(); });
            q('#nd-prev')?.addEventListener('click', () => { current = others[index - 1]; render(); });
            q('#nd-next')?.addEventListener('click', () => { current = others[index + 1]; render(); });

            const stage = q('#nd-blink-stage');
            if (stage) {
                const flip = () => {
                    blinkShowsOther = !blinkShowsOther;
                    const shown = blinkShowsOther ? current : selfEntry;
                    const other = blinkShowsOther ? selfEntry : current;
                    stage.querySelectorAll('img, video').forEach((el, i) => {
                        el.classList.toggle('nd-hidden', (i === 1) !== blinkShowsOther);
                    });
                    q('#nd-blink-label').textContent = blinkShowsOther ? sourceLabel(current) : t('this_upload');
                    const name = q('#nd-blink-name');
                    name.textContent = shown.filename;
                    name.title = shown.filename;
                    q('#nd-blink-stats').innerHTML = NearDuplicateView.renderPairStats(shown, other);
                };
                stage.addEventListener('click', flip);
                stage.addEventListener('keydown', (e) => {
                    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); flip(); }
                });
            }
        };

        overlay.addEventListener('mousedown', (e) => {
            if (e.target === overlay) NearDuplicateView.closeCompare();
        });
        NearDuplicateView._onKeydown = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                NearDuplicateView.closeCompare();
            }
        };
        document.addEventListener('keydown', NearDuplicateView._onKeydown, true);
        NearDuplicateView._overlay = overlay;
        NearDuplicateView._previousOverflow = previousOverflow;
        render();
        overlay.querySelector('#nd-close')?.focus();
    }

    static closeCompare() {
        if (NearDuplicateView._overlay) {
            NearDuplicateView._overlay.remove();
            NearDuplicateView._overlay = null;
            document.body.style.overflow = NearDuplicateView._previousOverflow || '';
        }
        if (NearDuplicateView._onKeydown) {
            document.removeEventListener('keydown', NearDuplicateView._onKeydown, true);
            NearDuplicateView._onKeydown = null;
        }
    }
}

window.NearDuplicateView = NearDuplicateView;
