function canonicalizeQuery(queryString) {
    if (!queryString || !queryString.trim()) return '';

    const tokenRegex = /(-?)(?:([a-zA-Z0-9_]+):)?("[^"]*"|[^\s"]+)/g;
    const singularKeys = new Set(['order', 'sort']);
    const knownQualifiers = new Set([
        'rating', 'tagcount', 'gentags', 'arttags', 'chartags', 'copytags', 'metatags',
        'id', 'width', 'height', 'duration', 'filesize', 'file_size', 'size',
        'date', 'age', 'filetype', 'source', 'md5',
        'album', 'pool', 'album_tree', 'pool_tree', 'parent', 'child',
        'order', 'sort', 'uploaded_at', 'time', 'created_at',
        'custom_date', 'custom_age', 'filename', 'name'
    ]);

    const orderedKeys = [];
    const qualifierValues = new Map();
    const singularValues = new Map();
    const seenTags = new Set();

    let match;
    while ((match = tokenRegex.exec(queryString)) !== null) {
        const isNegated = Boolean(match[1]);
        let key = match[2] ? match[2].toLowerCase() : null;
        let value = match[3] || '';
        if (value.startsWith('"') && value.endsWith('"')) {
            value = value.slice(1, -1);
        }

        if (key && !knownQualifiers.has(key)) {
            // Unknown qualifier
            value = `${key}:${value}`;
            key = null;
        }

        if (key) {
            if (singularKeys.has(key)) {
                if (!orderedKeys.some(e => e.type === 'singular' && e.key === key)) {
                    orderedKeys.push({ type: 'singular', key: key });
                }
                singularValues.set(key, value);
            } else {
                const mapKey = `${isNegated ? '-' : ''}${key}`;
                if (!orderedKeys.some(e => e.type === 'meta' && e.mapKey === mapKey)) {
                    orderedKeys.push({ type: 'meta', mapKey: mapKey, isNegated: isNegated, key: key });
                }
                if (!qualifierValues.has(mapKey)) {
                    qualifierValues.set(mapKey, []);
                }
                qualifierValues.get(mapKey).push(value);
            }
        } else {
            const isWildcard = value.includes('*') || value.includes('?');
            const tokenType = isWildcard ? 'wildcard' : 'tag';
            const tagKey = `${tokenType}:${isNegated ? '-' : ''}${value}`;
            if (!seenTags.has(tagKey)) {
                seenTags.add(tagKey);
                orderedKeys.push({
                    type: tokenType,
                    isNegated: isNegated,
                    value: value
                });
            }
        }
    }

    function parseBytes(num, unit) {
        const mulMap = {
            'b': 1, 'k': 1024, 'kb': 1024,
            'm': 1024 * 1024, 'mb': 1024 * 1024,
            'g': 1024 * 1024 * 1024, 'gb': 1024 * 1024 * 1024
        };
        const u = unit.toLowerCase();
        const mul = mulMap[u] || 1;
        return parseFloat(num) * mul;
    }

    function parseAgeSec(num, unit) {
        const u = unit.toLowerCase();
        const n = parseInt(num, 10);
        if (u.startsWith('mo')) return n * 30 * 86400;
        if (u.startsWith('y')) return n * 365 * 86400;
        if (u.startsWith('w')) return n * 7 * 86400;
        if (u.startsWith('d')) return n * 86400;
        if (u.startsWith('h')) return n * 3600;
        if (u.startsWith('mi') || u.startsWith('min')) return n * 60;
        if (u.startsWith('s')) return n;
        return n * 86400;
    }

    function parseDateOrdinal(dateStr) {
        const parts = dateStr.split('-');
        if (parts.length !== 3) return null;
        const year = parseInt(parts[0], 10);
        const month = parseInt(parts[1], 10) - 1;
        const day = parseInt(parts[2], 10);
        const d = new Date(Date.UTC(year, month, day));
        return isNaN(d.getTime()) ? null : Math.floor(d.getTime() / 86400000);
    }

    function parseConditionItem(raw, key = null) {
        const clean = raw.trim().replace(/^"|"$/g, '');
        if (!clean) return null;

        const keyLower = key ? key.toLowerCase() : null;

        // 1. Date
        if (!keyLower || ['date', 'uploaded_at', 'created_at', 'time', 'custom_date'].includes(keyLower)) {
            const dateMatch = clean.match(/^(>=|<=|>|<|!=)?(\d{4}-\d{2}-\d{2})$/);
            if (dateMatch) {
                const op = dateMatch[1] || '==';
                const val = parseDateOrdinal(dateMatch[2]);
                if (val !== null) {
                    const opType = { '==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne' }[op];
                    return { domain: 'date', type: opType, val: val, raw: clean };
                }
            }
            const dateRangeMatch = clean.match(/^(\d{4}-\d{2}-\d{2})?\.\.(\d{4}-\d{2}-\d{2})?$/);
            if (dateRangeMatch && (dateRangeMatch[1] || dateRangeMatch[2])) {
                const v1 = dateRangeMatch[1] ? parseDateOrdinal(dateRangeMatch[1]) : null;
                const v2 = dateRangeMatch[2] ? parseDateOrdinal(dateRangeMatch[2]) : null;
                return { domain: 'date', type: 'range', v1: v1, v2: v2, raw: clean };
            }
        }

        // 2. Age
        if (keyLower && ['age', 'custom_age'].includes(keyLower)) {
            const ageMatch = clean.match(/^(>=|<=|>|<|!=)?(\d+)\s*([a-zA-Z]+)?$/);
            if (ageMatch) {
                const op = ageMatch[1] || '==';
                const val = parseAgeSec(ageMatch[2], ageMatch[3] || 'd');
                if (val > 0) {
                    const opType = { '==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne' }[op];
                    return { domain: 'age', type: opType, val: val, raw: clean };
                }
            }
            const ageRangeMatch = clean.match(/^(\d+[a-zA-Z]+)?\.\.(\d+[a-zA-Z]+)?$/);
            if (ageRangeMatch && (ageRangeMatch[1] || ageRangeMatch[2])) {
                const parseA = (s) => {
                    if (!s) return null;
                    const m = s.match(/^(\d+)\s*([a-zA-Z]+)$/);
                    return m ? parseAgeSec(m[1], m[2]) : null;
                };
                return { domain: 'age', type: 'range', v1: parseA(ageRangeMatch[1]), v2: parseA(ageRangeMatch[2]), raw: clean };
            }
        }

        // 3. Filesize
        if (keyLower && ['filesize', 'file_size', 'size'].includes(keyLower)) {
            const sizeMatch = clean.match(/^(>=|<=|>|<|!=)?(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?$/);
            if (sizeMatch) {
                const op = sizeMatch[1] || '==';
                const unit = (sizeMatch[3] || 'b').toLowerCase();
                const val = parseBytes(sizeMatch[2], unit);
                const opType = { '==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne' }[op];
                return { domain: 'size', type: opType, val: val, raw: clean };
            }
            const sizeRangeMatch = clean.match(/^(\d+(?:\.\d+)?[a-zA-Z]+)?\.\.(\d+(?:\.\d+)?[a-zA-Z]+)?$/);
            if (sizeRangeMatch && (sizeRangeMatch[1] || sizeRangeMatch[2])) {
                const parseS = (s) => {
                    if (!s) return null;
                    const m = s.match(/^(\d+(?:\.\d+)?)\s*([a-zA-Z]+)$/);
                    return m ? parseBytes(m[1], m[2]) : null;
                };
                return { domain: 'size', type: 'range', v1: parseS(sizeRangeMatch[1]), v2: parseS(sizeRangeMatch[2]), raw: clean };
            }
        }

        // 4. Numeric
        const numericKeys = new Set(['id', 'width', 'height', 'duration', 'tagcount', 'gentags', 'arttags', 'chartags', 'copytags', 'metatags', 'parent', 'child', 'mpixels', 'resolution']);
        if (keyLower && numericKeys.has(keyLower)) {
            const numMatch = clean.match(/^(>=|<=|>|<|!=)?(\d+(?:\.\d+)?)$/);
            if (numMatch) {
                const op = numMatch[1] || '==';
                const val = parseFloat(numMatch[2]);
                const opType = { '==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne' }[op];
                return { domain: 'number', type: opType, val: val, raw: clean };
            }
            const numRangeMatch = clean.match(/^(\d+(?:\.\d+)?)?\.\.(\d+(?:\.\d+)?)?$/);
            if (numRangeMatch && (numRangeMatch[1] || numRangeMatch[2])) {
                const v1 = numRangeMatch[1] ? parseFloat(numRangeMatch[1]) : null;
                const v2 = numRangeMatch[2] ? parseFloat(numRangeMatch[2]) : null;
                return { domain: 'number', type: 'range', v1: v1, v2: v2, raw: clean };
            }
        }

        // 5. Fallback if key is None or other
        const sizeMatch = clean.match(/^(>=|<=|>|<|!=)?(\d+(?:\.\d+)?)\s*(kb|mb|gb|k|b)$/i);
        if (sizeMatch) {
            const op = sizeMatch[1] || '==';
            const unit = sizeMatch[3].toLowerCase();
            const val = parseBytes(sizeMatch[2], unit);
            const opType = { '==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne' }[op];
            return { domain: 'size', type: opType, val: val, raw: clean };
        }

        const ageMatch = clean.match(/^(>=|<=|>|<|!=)?(\d+)\s*(mo|mi|min|sec|s|h|d|w|y)$/i);
        if (ageMatch) {
            const op = ageMatch[1] || '==';
            const val = parseAgeSec(ageMatch[2], ageMatch[3]);
            if (val > 0) {
                const opType = { '==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne' }[op];
                return { domain: 'age', type: opType, val: val, raw: clean };
            }
        }

        const numMatch = clean.match(/^(>=|<=|>|<|!=)?(\d+(?:\.\d+)?)$/);
        if (numMatch) {
            const op = numMatch[1] || '==';
            const val = parseFloat(numMatch[2]);
            const opType = { '==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne' }[op];
            return { domain: 'number', type: opType, val: val, raw: clean };
        }
        const numRangeMatch = clean.match(/^(\d+(?:\.\d+)?)?\.\.(\d+(?:\.\d+)?)?$/);
        if (numRangeMatch && (numRangeMatch[1] || numRangeMatch[2])) {
            const v1 = numRangeMatch[1] ? parseFloat(numRangeMatch[1]) : null;
            const v2 = numRangeMatch[2] ? parseFloat(numRangeMatch[2]) : null;
            return { domain: 'number', type: 'range', v1: v1, v2: v2, raw: clean };
        }

        return null;
    }

    function isSubsumed(c1, c2) {
        if (c1.domain !== c2.domain) return false;
        const t1 = c1.type;
        const t2 = c2.type;

        if (t1 === 'eq') {
            const x = c1.val;
            if (t2 === 'ge') return x >= c2.val;
            if (t2 === 'gt') return x > c2.val;
            if (t2 === 'le') return x <= c2.val;
            if (t2 === 'lt') return x < c2.val;
            if (t2 === 'eq') return x === c2.val;
            if (t2 === 'range') {
                const v1 = c2.v1 !== null ? c2.v1 : -Infinity;
                const v2 = c2.v2 !== null ? c2.v2 : Infinity;
                return v1 <= x && x <= v2;
            }
        }
        if (t1 === 'le') {
            const x = c1.val;
            if (t2 === 'le') return x <= c2.val;
            if (t2 === 'lt') return x < c2.val;
        }
        if (t1 === 'lt') {
            const x = c1.val;
            if (t2 === 'le') return x <= c2.val;
            if (t2 === 'lt') return x <= c2.val;
        }
        if (t1 === 'ge') {
            const x = c1.val;
            if (t2 === 'ge') return x >= c2.val;
            if (t2 === 'gt') return x > c2.val;
        }
        if (t1 === 'gt') {
            const x = c1.val;
            if (t2 === 'ge') return x >= c2.val;
            if (t2 === 'gt') return x >= c2.val;
        }
        if (t1 === 'range') {
            const a1 = c1.v1 !== null ? c1.v1 : -Infinity;
            const b1 = c1.v2 !== null ? c1.v2 : Infinity;
            if (t2 === 'ge') return a1 >= c2.val;
            if (t2 === 'gt') return a1 > c2.val;
            if (t2 === 'le') return b1 <= c2.val;
            if (t2 === 'lt') return b1 < c2.val;
            if (t2 === 'range') {
                const a2 = c2.v1 !== null ? c2.v1 : -Infinity;
                const b2 = c2.v2 !== null ? c2.v2 : Infinity;
                return a2 <= a1 && b1 <= b2;
            }
        }
        return false;
    }

    function foldConditionItems(items, key = null) {
        const rawList = [];
        for (const item of items) {
            if (!item) continue;
            const parts = item.split(',').map(p => p.trim().replace(/^"|"$/g, '')).filter(Boolean);
            for (const p of parts) {
                if (p && !rawList.includes(p)) {
                    rawList.push(p);
                }
            }
        }

        if (rawList.length <= 1) return rawList;

        const parsedConditions = [];
        const otherItems = [];

        for (const raw of rawList) {
            const parsed = parseConditionItem(raw, key);
            if (parsed) {
                parsedConditions.push(parsed);
            } else {
                otherItems.push(raw);
            }
        }

        if (parsedConditions.length === 0) return otherItems;

        // 1. Boundary folding: eq(x) + gt(x) -> ge(x), eq(x) + lt(x) -> le(x)
        const foldedConditions = [];
        const handledIndices = new Set();

        for (let i = 0; i < parsedConditions.length; i++) {
            if (handledIndices.has(i)) continue;
            const c1 = parsedConditions[i];

            if (c1.type === 'eq') {
                let gtMatch = null;
                let ltMatch = null;
                for (let j = 0; j < parsedConditions.length; j++) {
                    if (j !== i && !handledIndices.has(j) && parsedConditions[j].domain === c1.domain && parsedConditions[j].val === c1.val) {
                        if (parsedConditions[j].type === 'gt') { gtMatch = j; break; }
                        else if (parsedConditions[j].type === 'lt') { ltMatch = j; break; }
                    }
                }
                if (gtMatch !== null) {
                    const c2 = parsedConditions[gtMatch];
                    const rawOp = c1.domain === 'number' ? `>=${c1.raw}` : `>=${c2.raw.replace(/^>/, '')}`;
                    foldedConditions.push({ domain: c1.domain, type: 'ge', val: c1.val, raw: rawOp });
                    handledIndices.add(i);
                    handledIndices.add(gtMatch);
                    continue;
                }
                if (ltMatch !== null) {
                    const c2 = parsedConditions[ltMatch];
                    const rawOp = c1.domain === 'number' ? `<=${c1.raw}` : `<=${c2.raw.replace(/^</, '')}`;
                    foldedConditions.push({ domain: c1.domain, type: 'le', val: c1.val, raw: rawOp });
                    handledIndices.add(i);
                    handledIndices.add(ltMatch);
                    continue;
                }
            } else if (c1.type === 'gt') {
                let eqMatch = null;
                for (let j = 0; j < parsedConditions.length; j++) {
                    if (j !== i && !handledIndices.has(j) && parsedConditions[j].domain === c1.domain && parsedConditions[j].val === c1.val && parsedConditions[j].type === 'eq') {
                        eqMatch = j;
                        break;
                    }
                }
                if (eqMatch !== null) {
                    const c2 = parsedConditions[eqMatch];
                    const rawOp = c1.domain === 'number' ? `>=${c2.raw}` : `>=${c1.raw.replace(/^>/, '')}`;
                    foldedConditions.push({ domain: c1.domain, type: 'ge', val: c1.val, raw: rawOp });
                    handledIndices.add(i);
                    handledIndices.add(eqMatch);
                    continue;
                }
            } else if (c1.type === 'lt') {
                let eqMatch = null;
                for (let j = 0; j < parsedConditions.length; j++) {
                    if (j !== i && !handledIndices.has(j) && parsedConditions[j].domain === c1.domain && parsedConditions[j].val === c1.val && parsedConditions[j].type === 'eq') {
                        eqMatch = j;
                        break;
                    }
                }
                if (eqMatch !== null) {
                    const c2 = parsedConditions[eqMatch];
                    const rawOp = c1.domain === 'number' ? `<=${c2.raw}` : `<=${c1.raw.replace(/^</, '')}`;
                    foldedConditions.push({ domain: c1.domain, type: 'le', val: c1.val, raw: rawOp });
                    handledIndices.add(i);
                    handledIndices.add(eqMatch);
                    continue;
                }
            }

            foldedConditions.push(c1);
            handledIndices.add(i);
        }

        // 2. Subsumption filter
        const survivingConditions = [];
        for (let i = 0; i < foldedConditions.length; i++) {
            let swallowed = false;
            for (let j = 0; j < foldedConditions.length; j++) {
                if (i !== j && isSubsumed(foldedConditions[i], foldedConditions[j])) {
                    swallowed = true;
                    break;
                }
            }
            if (!swallowed) {
                survivingConditions.push(foldedConditions[i]);
            }
        }

        // 3. Order output
        const eqItems = [];
        const opItems = [];
        const seen = new Set();

        for (const c of survivingConditions) {
            if (seen.has(c.raw)) continue;
            seen.add(c.raw);
            if (c.type === 'eq') {
                eqItems.push(c.raw);
            } else {
                opItems.push(c.raw);
            }
        }

        const result = eqItems.concat(opItems);
        for (const other of otherItems) {
            if (!seen.has(other)) {
                seen.add(other);
                result.push(other);
            }
        }
        return result;
    }

    const formattedTokens = [];
    for (const entry of orderedKeys) {
        if (entry.type === 'meta') {
            const mapKey = entry.mapKey;
            const rawKey = entry.key;
            const values = qualifierValues.get(mapKey) || [];
            const folded = foldConditionItems(values, rawKey);
            if (folded.length > 0) {
                const joined = folded.join(',');
                const valStr = joined.includes(' ') ? `"${joined}"` : joined;
                formattedTokens.push(`${mapKey}:${valStr}`);
            }
        } else if (entry.type === 'singular') {
            const key = entry.key;
            const val = singularValues.get(key) || '';
            if (val) {
                const valFormatted = val.includes(' ') ? `"${val}"` : val;
                formattedTokens.push(`${key}:${valFormatted}`);
            }
        } else if (entry.type === 'tag' || entry.type === 'wildcard') {
            const prefix = entry.isNegated ? '-' : '';
            const tagVal = entry.value;
            const formatted = tagVal.includes(' ') ? `"${tagVal}"` : tagVal;
            formattedTokens.push(`${prefix}${formatted}`);
        }
    }

    return formattedTokens.join(' ');
}

window.canonicalizeQuery = canonicalizeQuery;
