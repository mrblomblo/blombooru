import re
from datetime import datetime
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)
from .tokens import (
    ALL_KNOWN_KEYS,
    SINGULAR_KEYS,
    TOKEN_PATTERN,
    _parse_size_bytes,
    parse_time_unit,
)

def _parse_condition_item(raw: str, key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Parses a single condition item into a structured interval representation across
    domains (numbers, filesizes, dates, ages).
    Uses the qualifier key (e.g. 'age', 'filesize', 'date') if provided to disambiguate units.
    """
    raw_clean = raw.strip().strip('"')
    if not raw_clean:
        return None

    key_lower = key.lower() if key else None

    # 1. Date check (YYYY-MM-DD) if key is date or key is None
    if key_lower in (None, 'date', 'uploaded_at', 'created_at', 'time', 'custom_date'):
        date_match = re.match(r'^(>=|<=|>|<|!=)?(\d{4}-\d{2}-\d{2})$', raw_clean)
        if date_match:
            op = date_match.group(1) or '=='
            d_str = date_match.group(2)
            try:
                val = datetime.strptime(d_str, "%Y-%m-%d").toordinal()
                op_type = {'==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne'}[op]
                return {'domain': 'date', 'type': op_type, 'val': val, 'raw': raw_clean}
            except ValueError:
                pass

        date_range_match = re.match(r'^(\d{4}-\d{2}-\d{2})?\.\.(\d{4}-\d{2}-\d{2})?$', raw_clean)
        if date_range_match and (date_range_match.group(1) or date_range_match.group(2)):
            d1_str = date_range_match.group(1)
            d2_str = date_range_match.group(2)
            try:
                v1 = datetime.strptime(d1_str, "%Y-%m-%d").toordinal() if d1_str else None
                v2 = datetime.strptime(d2_str, "%Y-%m-%d").toordinal() if d2_str else None
                return {'domain': 'date', 'type': 'range', 'v1': v1, 'v2': v2, 'raw': raw_clean}
            except ValueError:
                pass

    # 2. Age check if key is age
    if key_lower in ('age', 'custom_age'):
        age_match = re.match(r'^(>=|<=|>|<|!=)?(\d+)\s*([a-zA-Z]+)?$', raw_clean)
        if age_match:
            op = age_match.group(1) or '=='
            num_str = age_match.group(2)
            unit_str = (age_match.group(3) or 'd').lower()
            delta = parse_time_unit(f"{num_str}{unit_str}")
            if delta.total_seconds() > 0:
                val_sec = int(delta.total_seconds())
                op_type = {'==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne'}[op]
                return {'domain': 'age', 'type': op_type, 'val': val_sec, 'raw': raw_clean}

        age_range_match = re.match(r'^(\d+[a-zA-Z]+)?\.\.(\d+[a-zA-Z]+)?$', raw_clean)
        if age_range_match and (age_range_match.group(1) or age_range_match.group(2)):
            a1 = age_range_match.group(1)
            a2 = age_range_match.group(2)
            v1 = int(parse_time_unit(a1).total_seconds()) if a1 else None
            v2 = int(parse_time_unit(a2).total_seconds()) if a2 else None
            return {'domain': 'age', 'type': 'range', 'v1': v1, 'v2': v2, 'raw': raw_clean}

    # 3. Filesize check if key is filesize/size
    if key_lower in ('filesize', 'file_size', 'size'):
        size_match = re.match(r'^(>=|<=|>|<|!=)?(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?$', raw_clean)
        if size_match:
            op = size_match.group(1) or '=='
            num_str = size_match.group(2)
            unit_str = (size_match.group(3) or 'b').lower()
            val_bytes = _parse_size_bytes(f"{num_str}{unit_str}")
            op_type = {'==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne'}[op]
            return {'domain': 'size', 'type': op_type, 'val': val_bytes, 'raw': raw_clean}

        size_range_match = re.match(r'^(\d+(?:\.\d+)?[a-zA-Z]+)?\.\.(\d+(?:\.\d+)?[a-zA-Z]+)?$', raw_clean)
        if size_range_match and (size_range_match.group(1) or size_range_match.group(2)):
            s1 = size_range_match.group(1)
            s2 = size_range_match.group(2)
            v1 = _parse_size_bytes(s1) if s1 else None
            v2 = _parse_size_bytes(s2) if s2 else None
            return {'domain': 'size', 'type': 'range', 'v1': v1, 'v2': v2, 'raw': raw_clean}

    # 4. Numeric check if key is known numeric
    numeric_keys = {'id', 'width', 'height', 'duration', 'tagcount', 'gentags', 'arttags', 'chartags', 'copytags', 'metatags', 'parent', 'child', 'mpixels', 'resolution'}
    if key_lower in numeric_keys:
        num_match = re.match(r'^(>=|<=|>|<|!=)?(\d+(?:\.\d+)?)$', raw_clean)
        if num_match:
            op = num_match.group(1) or '=='
            val_num = float(num_match.group(2)) if '.' in num_match.group(2) else int(num_match.group(2))
            op_type = {'==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne'}[op]
            return {'domain': 'number', 'type': op_type, 'val': val_num, 'raw': raw_clean}

        num_range_match = re.match(r'^(\d+(?:\.\d+)?)?\.\.(\d+(?:\.\d+)?)?$', raw_clean)
        if num_range_match and (num_range_match.group(1) or num_range_match.group(2)):
            p1 = num_range_match.group(1)
            p2 = num_range_match.group(2)
            v1 = (float(p1) if '.' in p1 else int(p1)) if p1 else None
            v2 = (float(p2) if '.' in p2 else int(p2)) if p2 else None
            return {'domain': 'number', 'type': 'range', 'v1': v1, 'v2': v2, 'raw': raw_clean}

    # 5. Fallback if key is None or unknown
    # Try filesize with explicit units (kb, mb, gb, etc.)
    size_match = re.match(r'^(>=|<=|>|<|!=)?(\d+(?:\.\d+)?)\s*(kb|mb|gb|k|b)$', raw_clean, re.IGNORECASE)
    if size_match:
        op = size_match.group(1) or '=='
        num_str = size_match.group(2)
        unit_str = size_match.group(3).lower()
        val_bytes = _parse_size_bytes(f"{num_str}{unit_str}")
        op_type = {'==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne'}[op]
        return {'domain': 'size', 'type': op_type, 'val': val_bytes, 'raw': raw_clean}

    # Try age with explicit units (mo, mi, min, sec, s, h, d, w, y)
    age_match = re.match(r'^(>=|<=|>|<|!=)?(\d+)\s*(mo|mi|min|sec|s|h|d|w|y)$', raw_clean, re.IGNORECASE)
    if age_match:
        op = age_match.group(1) or '=='
        num_str = age_match.group(2)
        unit_str = age_match.group(3).lower()
        delta = parse_time_unit(f"{num_str}{unit_str}")
        if delta.total_seconds() > 0:
            val_sec = int(delta.total_seconds())
            op_type = {'==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne'}[op]
            return {'domain': 'age', 'type': op_type, 'val': val_sec, 'raw': raw_clean}

    # Try numeric
    num_match = re.match(r'^(>=|<=|>|<|!=)?(\d+(?:\.\d+)?)$', raw_clean)
    if num_match:
        op = num_match.group(1) or '=='
        val_num = float(num_match.group(2)) if '.' in num_match.group(2) else int(num_match.group(2))
        op_type = {'==': 'eq', '>=': 'ge', '<=': 'le', '>': 'gt', '<': 'lt', '!=': 'ne'}[op]
        return {'domain': 'number', 'type': op_type, 'val': val_num, 'raw': raw_clean}

    num_range_match = re.match(r'^(\d+(?:\.\d+)?)?\.\.(\d+(?:\.\d+)?)?$', raw_clean)
    if num_range_match and (num_range_match.group(1) or num_range_match.group(2)):
        p1 = num_range_match.group(1)
        p2 = num_range_match.group(2)
        v1 = (float(p1) if '.' in p1 else int(p1)) if p1 else None
        v2 = (float(p2) if '.' in p2 else int(p2)) if p2 else None
        return {'domain': 'number', 'type': 'range', 'v1': v1, 'v2': v2, 'raw': raw_clean}

    return None

def _is_subsumed(c1: Dict[str, Any], c2: Dict[str, Any]) -> bool:
    """Returns True if condition c1 is fully swallowed (covered) by condition c2 in an OR list."""
    if c1['domain'] != c2['domain']:
        return False

    t1, t2 = c1['type'], c2['type']

    if t1 == 'eq':
        x = c1['val']
        if t2 == 'ge': return x >= c2['val']
        if t2 == 'gt': return x > c2['val']
        if t2 == 'le': return x <= c2['val']
        if t2 == 'lt': return x < c2['val']
        if t2 == 'eq': return x == c2['val']
        if t2 == 'range':
            v1 = c2['v1'] if c2['v1'] is not None else float('-inf')
            v2 = c2['v2'] if c2['v2'] is not None else float('inf')
            return v1 <= x <= v2

    if t1 == 'le':
        x = c1['val']
        if t2 == 'le': return x <= c2['val']
        if t2 == 'lt': return x < c2['val']

    if t1 == 'lt':
        x = c1['val']
        if t2 == 'le': return x <= c2['val']
        if t2 == 'lt': return x <= c2['val']

    if t1 == 'ge':
        x = c1['val']
        if t2 == 'ge': return x >= c2['val']
        if t2 == 'gt': return x > c2['val']

    if t1 == 'gt':
        x = c1['val']
        if t2 == 'ge': return x >= c2['val']
        if t2 == 'gt': return x >= c2['val']

    if t1 == 'range':
        a1 = c1['v1'] if c1['v1'] is not None else float('-inf')
        b1 = c1['v2'] if c1['v2'] is not None else float('inf')
        if t2 == 'ge': return a1 >= c2['val']
        if t2 == 'gt': return a1 > c2['val']
        if t2 == 'le': return b1 <= c2['val']
        if t2 == 'lt': return b1 < c2['val']
        if t2 == 'range':
            a2 = c2['v1'] if c2['v1'] is not None else float('-inf')
            b2 = c2['v2'] if c2['v2'] is not None else float('inf')
            return a2 <= a1 and b1 <= b2

    return False

def fold_condition_items(items: List[str], key: Optional[str] = None) -> List[str]:
    """
    Folds and combines raw condition items into a canonical list of values.
    Handles:
    - Splitting embedded commas and stripping quotes/spaces.
    - Deduplicating items while preserving order.
    - Smart condition folding (e.g., 4 and >4 -> >=4, 4 and <4 -> <=4, 4 and >=4 -> >=4).
    - Subsumption clearing: swallowed numbers/ranges (e.g. 5,6,<=15 -> <=15) are cleared.
    - Exact values placed first in order of appearance, followed by operator expressions.
    """
    if key and key.lower() in ('similar_to', 'similar_to_strict'):
        tokens: List[str] = []
        seen_tokens: Set[str] = set()
        for item in items:
            if not item:
                continue
            for part in re.split(r'[,\s\[\]]+', item.strip('"')):
                if not part:
                    continue
                normalized = part.lower() if re.match(r'^[0-9a-fA-F]{64}$', part) else part
                if normalized not in seen_tokens:
                    seen_tokens.add(normalized)
                    tokens.append(normalized)
        return tokens

    raw_list: List[str] = []
    for item in items:
        if not item:
            continue
        parts = [p.strip().strip('"') for p in item.split(',') if p.strip()]
        for p in parts:
            if p and p not in raw_list:
                raw_list.append(p)

    if len(raw_list) <= 1:
        return raw_list

    parsed_conditions: List[Dict[str, Any]] = []
    other_items: List[str] = []

    for raw in raw_list:
        parsed = _parse_condition_item(raw, key=key)
        if parsed is not None:
            parsed_conditions.append(parsed)
        else:
            other_items.append(raw)

    if not parsed_conditions:
        return other_items

    # 1. Boundary folding: eq(x) + gt(x) -> ge(x), eq(x) + lt(x) -> le(x)
    folded_conditions: List[Dict[str, Any]] = []
    handled_indices: Set[int] = set()

    for i, c1 in enumerate(parsed_conditions):
        if i in handled_indices:
            continue

        if c1['type'] == 'eq':
            val = c1['val']
            domain = c1['domain']
            gt_match = None
            lt_match = None
            for j, c2 in enumerate(parsed_conditions):
                if j != i and j not in handled_indices and c2['domain'] == domain and c2.get('val') == val:
                    if c2['type'] == 'gt':
                        gt_match = (j, c2)
                        break
                    elif c2['type'] == 'lt':
                        lt_match = (j, c2)
                        break

            if gt_match is not None:
                j, c2 = gt_match
                raw_op = f">={c1['raw']}" if domain == 'number' else f">={c2['raw'].lstrip('>')}"
                new_c = {'domain': domain, 'type': 'ge', 'val': val, 'raw': raw_op}
                folded_conditions.append(new_c)
                handled_indices.add(i)
                handled_indices.add(j)
                continue

            if lt_match is not None:
                j, c2 = lt_match
                raw_op = f"<={c1['raw']}" if domain == 'number' else f"<={c2['raw'].lstrip('<')}"
                new_c = {'domain': domain, 'type': 'le', 'val': val, 'raw': raw_op}
                folded_conditions.append(new_c)
                handled_indices.add(i)
                handled_indices.add(j)
                continue

        elif c1['type'] == 'gt':
            val = c1['val']
            domain = c1['domain']
            eq_match = None
            for j, c2 in enumerate(parsed_conditions):
                if j != i and j not in handled_indices and c2['domain'] == domain and c2.get('val') == val and c2['type'] == 'eq':
                    eq_match = (j, c2)
                    break
            if eq_match is not None:
                j, c2 = eq_match
                raw_op = f">={c2['raw']}" if domain == 'number' else f">={c1['raw'].lstrip('>')}"
                new_c = {'domain': domain, 'type': 'ge', 'val': val, 'raw': raw_op}
                folded_conditions.append(new_c)
                handled_indices.add(i)
                handled_indices.add(j)
                continue

        elif c1['type'] == 'lt':
            val = c1['val']
            domain = c1['domain']
            eq_match = None
            for j, c2 in enumerate(parsed_conditions):
                if j != i and j not in handled_indices and c2['domain'] == domain and c2.get('val') == val and c2['type'] == 'eq':
                    eq_match = (j, c2)
                    break
            if eq_match is not None:
                j, c2 = eq_match
                raw_op = f"<={c2['raw']}" if domain == 'number' else f"<={c1['raw'].lstrip('<')}"
                new_c = {'domain': domain, 'type': 'le', 'val': val, 'raw': raw_op}
                folded_conditions.append(new_c)
                handled_indices.add(i)
                handled_indices.add(j)
                continue

        folded_conditions.append(c1)
        handled_indices.add(i)

    # 2. Subsumption filter: remove any condition c1 that is swallowed by another condition c2
    surviving_conditions: List[Dict[str, Any]] = []
    for i, c1 in enumerate(folded_conditions):
        swallowed = False
        for j, c2 in enumerate(folded_conditions):
            if i != j and _is_subsumed(c1, c2):
                swallowed = True
                break
        if not swallowed:
            surviving_conditions.append(c1)

    # 3. Output ordering: exact values first in order of appearance, followed by operators, followed by other items
    eq_items: List[str] = []
    op_items: List[str] = []
    seen: Set[str] = set()

    for c in surviving_conditions:
        raw = c['raw']
        if raw in seen:
            continue
        seen.add(raw)
        if c['type'] == 'eq':
            eq_items.append(raw)
        else:
            op_items.append(raw)

    result = eq_items + op_items
    for other in other_items:
        if other not in seen:
            seen.add(other)
            result.append(other)

    return result

def canonicalize_query(query_string: str) -> str:
    """
    Parses and canonicalizes a Danbooru-style search query string.
    Combines repeated qualifiers, performs smart condition folding,
    clears swallowed conditions, deduplicates identical tags,
    and preserves the order of first appearance.
    """
    if not query_string or not query_string.strip():
        return ""

    matches = TOKEN_PATTERN.findall(query_string)
    if not matches:
        return ""

    ordered_keys: List[Tuple[str, bool, str]] = []
    qualifier_values: Dict[Tuple[bool, str], List[str]] = {}
    singular_values: Dict[str, str] = {}
    seen_tags: Set[Tuple[str, bool, str]] = set()

    for negate, key, value in matches:
        is_negated = bool(negate)
        value = value.strip('"')

        if key and key.lower() not in ALL_KNOWN_KEYS:
            # Unknown qualifier
            value = f"{key}:{value}"
            key = ''

        if key:
            key_lower = key.lower()
            if key_lower in SINGULAR_KEYS:
                entry_id = ('singular', False, key_lower)
                if entry_id not in ordered_keys:
                    ordered_keys.append(entry_id)
                singular_values[key_lower] = value
            else:
                entry_id = ('meta', is_negated, key_lower)
                if entry_id not in ordered_keys:
                    ordered_keys.append(entry_id)
                if (is_negated, key_lower) not in qualifier_values:
                    qualifier_values[(is_negated, key_lower)] = []
                qualifier_values[(is_negated, key_lower)].append(value)
        else:
            if '*' in value or '?' in value:
                entry_id = ('wildcard', is_negated, value)
            else:
                entry_id = ('tag', is_negated, value)

            if entry_id not in seen_tags:
                seen_tags.add(entry_id)
                ordered_keys.append(entry_id)

    formatted_tokens: List[str] = []

    for token_type, is_negated, identifier in ordered_keys:
        prefix = '-' if is_negated else ''
        if token_type == 'meta':
            values = qualifier_values.get((is_negated, identifier), [])
            folded = fold_condition_items(values, key=identifier)
            if folded:
                joined = ','.join(folded)
                val_str = f'"{joined}"' if ' ' in joined else joined
                formatted_tokens.append(f"{prefix}{identifier}:{val_str}")
        elif token_type == 'singular':
            val = singular_values.get(identifier, '')
            if val:
                val_formatted = f'"{val}"' if ' ' in val else val
                formatted_tokens.append(f"{identifier}:{val_formatted}")
        elif token_type in ('tag', 'wildcard'):
            val_formatted = f'"{identifier}"' if ' ' in identifier else identifier
            formatted_tokens.append(f"{prefix}{val_formatted}")

    return " ".join(formatted_tokens)
