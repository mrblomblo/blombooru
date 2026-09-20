import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import (Float, and_, case, cast, exists, false, func,
                        literal, not_, or_)
from sqlalchemy.orm import Query, Session, aliased

from ..enums import FileTypeEnum
from ..models import (Album, Media, RatingEnum, Tag, TagCategoryEnum,
                      blombooru_media_tags)

TOKEN_PATTERN = re.compile(r'(-?)(?:([a-zA-Z0-9_]+):)?("[^"]*"|[^\s"]+)')

COMBINABLE_KEYS: Set[str] = {
    'rating', 'tagcount', 'gentags', 'arttags', 'chartags', 'copytags', 'metatags',
    'id', 'width', 'height', 'duration', 'filesize', 'date', 'age', 'filetype',
    'source', 'md5', 'album', 'pool', 'album_tree', 'pool_tree', 'parent', 'child'
}

SINGULAR_KEYS: Set[str] = {'order', 'sort'}
ALL_KNOWN_KEYS: Set[str] = COMBINABLE_KEYS | SINGULAR_KEYS

def _strip_size_unit(s: str) -> Tuple[str, int]:
    """Strip filesize unit suffix and return (numeric_string, multiplier)."""
    s = s.lower()
    mul = 1
    if s.endswith('kb'):
        mul = 1024
        s = s[:-2]
    elif s.endswith('k'):
        mul = 1024
        s = s[:-1]
    elif s.endswith('mb'):
        mul = 1024 * 1024
        s = s[:-2]
    elif s.endswith('m'):
        mul = 1024 * 1024
        s = s[:-1]
    elif s.endswith('gb'):
        mul = 1024 * 1024 * 1024
        s = s[:-2]
    elif s.endswith('g'):
        mul = 1024 * 1024 * 1024
        s = s[:-1]
    elif s.endswith('b'):
        mul = 1
        s = s[:-1]
    return s, mul

def _parse_size_bytes(s: str) -> int:
    """Parse a filesize string with unit into bytes."""
    s_stripped, mul = _strip_size_unit(s)
    try:
        return int(float(s_stripped) * mul)
    except ValueError:
        return 0

def _parse_numeric_value(s: str) -> Optional[Union[int, float]]:
    """Attempt to parse integer or float value."""
    try:
        if '.' in s:
            return float(s)
        return int(s)
    except ValueError:
        return None

def parse_time_unit(s: str) -> timedelta:
    """Parse relative time string like '24h', '1w', '30d' into timedelta."""
    units = {
        's': 'seconds', 'sec': 'seconds',
        'mi': 'minutes', 'min': 'minutes',
        'h': 'hours',
        'd': 'days',
        'w': 'weeks',
        'mo': 'months',
        'y': 'years'
    }

    m = re.match(r'^(\d+)([a-z]+)$', s, re.IGNORECASE)
    if not m:
        return timedelta(days=0)

    num = int(m.group(1))
    unit_str = m.group(2).lower()

    for k in units:
        if unit_str.startswith(k):
            if unit_str == k:
                break

    if unit_str.startswith('mo'):
        return timedelta(days=num * 30)
    elif unit_str.startswith('y'):
        return timedelta(days=num * 365)
    elif unit_str.startswith('w'):
        return timedelta(weeks=num)
    elif unit_str.startswith('d'):
        return timedelta(days=num)
    elif unit_str.startswith('h'):
        return timedelta(hours=num)
    elif unit_str.startswith('mi') or unit_str.startswith('min') or unit_str == 'm':
        return timedelta(minutes=num)
    elif unit_str.startswith('s'):
        return timedelta(seconds=num)
    return timedelta(days=0)

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
    if key_lower in (None, 'date', 'uploaded_at', 'created_at', 'time'):
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
    if key_lower == 'age':
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
                val_str = ','.join(f'"{v}"' if ' ' in v else v for v in folded)
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

def parse_search_query(query_string: str) -> Dict[str, Any]:
    """
    Parses a Danbooru-style search query string into a structured dictionary.
    """
    if not query_string:
        return {'tags': {'include': [], 'exclude': [], 'wildcards': []}, 'meta': {}}

    result = {
        'tags': {
            'include': [],
            'exclude': [],
            'wildcards': []  # list of (type, pattern) where type is 'include' or 'exclude'
        },
        'meta': {}  # specific fields like id, width, etc.
    }

    matches = TOKEN_PATTERN.findall(query_string)

    for negate, key, value in matches:
        value = value.strip('"')
        is_negated = bool(negate)

        if key and key.lower() not in ALL_KNOWN_KEYS:
            # Unknown qualifier
            value = f"{key}:{value}"
            key = ''

        if key:
            key = key.lower()
            if key not in result['meta']:
                result['meta'][key] = []
            result['meta'][key].append({'value': value, 'negated': is_negated})
        else:
            if '*' in value or '?' in value:
                if is_negated:
                    result['tags']['wildcards'].append(('exclude', value))
                else:
                    result['tags']['wildcards'].append(('include', value))
            else:
                if is_negated:
                    result['tags']['exclude'].append(value)
                else:
                    result['tags']['include'].append(value)

    return result

def parse_range(value: str, converter=int) -> Dict[str, Any]:
    """
    Parses a range string like '100..200', '>=100', '100', '1,2,3'.
    Returns a dict with 'op' and 'value' (one or two values).
    """
    if '..' in value:
        parts = value.split('..', 1)
        if len(parts) == 2:
            v1 = parts[0]
            v2 = parts[1]
            if v1 == '':
                return {'op': 'le', 'value': converter(v2)}
            if v2 == '':
                return {'op': 'ge', 'value': converter(v1)}
            return {'op': 'between', 'value': (converter(v1), converter(v2))}

    if value.startswith('>='):
        return {'op': 'ge', 'value': converter(value[2:])}
    elif value.startswith('<='):
        return {'op': 'le', 'value': converter(value[2:])}
    elif value.startswith('>'):
        return {'op': 'gt', 'value': converter(value[1:])}
    elif value.startswith('<'):
        return {'op': 'lt', 'value': converter(value[1:])}
    elif value.startswith('!='):
        return {'op': 'ne', 'value': converter(value[2:])}
    
    # List: 1,2,3
    if ',' in value:
        return {'op': 'in', 'value': [converter(v) for v in value.split(',') if v]}
    
    # Exact match
    return {'op': 'eq', 'value': converter(value)}

def parse_date_range(value: str) -> Dict[str, Any]:
    """Parse date values (YYYY-MM-DD)."""
    def to_date(s):
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    
    try:
        return parse_range(value, converter=to_date)
    except ValueError:
        # Fallback for invalid dates
        return {'op': 'eq', 'value': None}

def parse_age(value: str) -> Dict[str, Any]:
    """
    Parses age string to date range relative to now.
    age:2weeks..1year -> between 1 year ago and 2 weeks ago.
    'age' is reverse of 'date'. Older age means smaller date (earlier time).
    age: < 1w (less than 1 week old) -> date > (now - 1w)
    """
    now = datetime.now()
    criteria = parse_range(value, converter=lambda x: x)
    op = criteria['op']
    val = criteria['value']
    
    if op == 'between':
        t1 = parse_time_unit(val[0])
        t2 = parse_time_unit(val[1])
        # age: 2w..1y means between 2w and 1y old.
        # date: (now - 1y) .. (now - 2w)
        d1 = now - t1
        d2 = now - t2
        # d1 is "2 weeks ago", d2 is "1 year ago". d1 > d2.
        # So range is between d2 and d1.
        if d1 < d2: d1, d2 = d2, d1
        return {'op': 'between', 'value': (d2, d1)} 
    
    t = parse_time_unit(val) if isinstance(val, str) else timedelta(0)
    d = now - t
    
    # age < 1w => less than 1 week old => uploaded_at > (now - 1w)
    if op == 'lt': return {'op': 'gt', 'value': d}
    if op == 'gt': return {'op': 'lt', 'value': d}
    if op == 'le': return {'op': 'ge', 'value': d}
    if op == 'ge': return {'op': 'le', 'value': d}
    if op == 'eq': 
        return {'op': 'between', 'value': (d - timedelta(hours=12), d + timedelta(hours=12))}

    return {'op': 'eq', 'value': d}

def parse_filesize(value: str) -> Dict[str, Any]:
    """Parse filesize string like 200kb, 1.5M."""
    val_stripped, multiplier = _strip_size_unit(value)
    unit_found = multiplier > 1
        
    if unit_found and '..' not in value and not any(op in value for op in ['>', '<', '!=', ',']):
        # If a specific unit was given without an operator, assume fuzzy range [val, val+1_unit)
        try:
            base_val = float(val_stripped)
            start_bytes = int(base_val * multiplier)
            end_bytes = start_bytes + multiplier
            
            return {'op': 'between', 'value': (start_bytes, end_bytes - 1)}
        except ValueError:
            pass

    return parse_range(value, converter=_parse_size_bytes)

def wildcard_to_regex(pattern: str) -> str:
    """Convert wildcard pattern to PostgreSQL regex pattern"""
    pattern = pattern.replace('\\', '\\\\')
    
    special_chars = ['.', '^', '$', '+', '(', ')', '[', ']', '{', '}', '|']
    for char in special_chars:
        pattern = pattern.replace(char, '\\' + char)
    
    pattern = pattern.replace('*', '.*')
    pattern = pattern.replace('?', '.?')
    pattern = '^' + pattern + '$'
    return pattern

def build_range_condition(column, value_str: str, converter=int):
    """
    Builds a SQLAlchemy boolean expression supporting comma-separated multi-value expressions,
    e.g. '13,16,<8,>91', '10..20,>=50', etc.
    """
    parts = [p.strip() for p in value_str.split(',') if p.strip()]
    if not parts:
        return None

    conditions = []
    exact_values = []

    for part in parts:
        try:
            if '..' in part:
                p_split = part.split('..', 1)
                v1 = p_split[0]
                v2 = p_split[1]
                if v1 == '':
                    conditions.append(column <= converter(v2))
                elif v2 == '':
                    conditions.append(column >= converter(v1))
                else:
                    conditions.append(column.between(converter(v1), converter(v2)))
            elif part.startswith('>='):
                conditions.append(column >= converter(part[2:]))
            elif part.startswith('<='):
                conditions.append(column <= converter(part[2:]))
            elif part.startswith('>'):
                conditions.append(column > converter(part[1:]))
            elif part.startswith('<'):
                conditions.append(column < converter(part[1:]))
            elif part.startswith('!='):
                conditions.append(column != converter(part[2:]))
            else:
                exact_values.append(converter(part))
        except (ValueError, TypeError):
            continue

    if exact_values:
        if len(exact_values) == 1:
            conditions.append(column == exact_values[0])
        else:
            conditions.append(column.in_(exact_values))

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return or_(*conditions)

def build_filesize_condition(column, value_str: str):
    """Builds a SQLAlchemy boolean expression for filesize multi-expressions."""
    parts = [p.strip() for p in value_str.split(',') if p.strip()]
    if not parts:
        return None

    conditions = []
    for part in parts:
        try:
            val_stripped, multiplier = _strip_size_unit(part)
            unit_found = multiplier > 1

            if unit_found and '..' not in part and not any(op in part for op in ['>', '<', '!=']):
                base_val = float(val_stripped)
                start_bytes = int(base_val * multiplier)
                end_bytes = start_bytes + multiplier
                conditions.append(column.between(start_bytes, end_bytes - 1))
            else:
                cond = build_range_condition(column, part, converter=_parse_size_bytes)
                if cond is not None:
                    conditions.append(cond)
        except (ValueError, TypeError):
            continue

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return or_(*conditions)

def build_date_condition(column, value_str: str):
    """Builds a SQLAlchemy boolean expression for date multi-expressions."""
    def to_date(s):
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()

    return build_range_condition(func.date(column), value_str, converter=to_date)

def build_age_condition(column, value_str: str):
    """Builds a SQLAlchemy boolean expression for age multi-expressions."""
    parts = [p.strip() for p in value_str.split(',') if p.strip()]
    if not parts:
        return None

    now = datetime.now()
    conditions = []

    for part in parts:
        try:
            if '..' in part:
                p_split = part.split('..', 1)
                t1 = parse_time_unit(p_split[0]) if p_split[0] else timedelta(0)
                t2 = parse_time_unit(p_split[1]) if p_split[1] else timedelta(0)
                d1 = now - t1
                d2 = now - t2
                if d1 < d2:
                    d1, d2 = d2, d1
                conditions.append(column.between(d2, d1))
            elif part.startswith('>='):
                d = now - parse_time_unit(part[2:])
                conditions.append(column <= d)
            elif part.startswith('<='):
                d = now - parse_time_unit(part[2:])
                conditions.append(column >= d)
            elif part.startswith('>'):
                d = now - parse_time_unit(part[1:])
                conditions.append(column < d)
            elif part.startswith('<'):
                d = now - parse_time_unit(part[1:])
                conditions.append(column > d)
            else:
                d = now - parse_time_unit(part)
                conditions.append(column.between(d - timedelta(hours=12), d + timedelta(hours=12)))
        except (ValueError, TypeError):
            continue

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return or_(*conditions)

def apply_sort_ordering(query: Query, order_val: str, db: Session, parsed_meta: Dict[str, Any]) -> Query:
    """
    Applies comprehensive sorting with full _asc and _desc support for all fields.
    """
    order_val = order_val.strip().lower()

    ascending = False
    base_sort = order_val
    if order_val.endswith('_asc'):
        ascending = True
        base_sort = order_val[:-4]
    elif order_val.endswith('_desc'):
        ascending = False
        base_sort = order_val[:-5]
    elif order_val.startswith('random'):
        base_sort = 'random'
    else:
        # Default direction per base_sort
        if base_sort in ('filename', 'name', 'md5', 'hash', 'rating'):
            ascending = True
        else:
            ascending = False

    if base_sort in ('id',):
        return query.order_by(Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('date', 'uploaded_at', 'created_at', 'time'):
        col = Media.uploaded_at
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('filesize', 'file_size', 'size'):
        col = Media.file_size
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('width',):
        col = Media.width
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('height',):
        col = Media.height
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('mpixels', 'resolution', 'pixels', 'area'):
        expr = Media.width * Media.height
        return query.order_by(expr.asc() if ascending else expr.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('duration',):
        col = Media.duration
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('landscape', 'aspect_ratio'):
        expr = cast(Media.width, Float) / func.nullif(Media.height, 0)
        return query.order_by(expr.asc() if ascending else expr.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('portrait',):
        expr = cast(Media.height, Float) / func.nullif(Media.width, 0)
        return query.order_by(expr.asc() if ascending else expr.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('tagcount', 'tag_count', 'tags'):
        subq = (
            db.query(func.count(blombooru_media_tags.c.tag_id))
            .filter(blombooru_media_tags.c.media_id == Media.id)
            .scalar_subquery()
        )
        return query.order_by(subq.asc() if ascending else subq.desc(), Media.id.asc() if ascending else Media.id.desc())

    category_sort_map = {
        'gentags': TagCategoryEnum.general,
        'arttags': TagCategoryEnum.artist,
        'chartags': TagCategoryEnum.character,
        'copytags': TagCategoryEnum.copyright,
        'metatags': TagCategoryEnum.meta,
    }
    if base_sort in category_sort_map:
        cat = category_sort_map[base_sort]
        subq = (
            db.query(func.count(blombooru_media_tags.c.tag_id))
            .join(Tag, blombooru_media_tags.c.tag_id == Tag.id)
            .filter(blombooru_media_tags.c.media_id == Media.id)
            .filter(Tag.category == cat)
            .scalar_subquery()
        )
        return query.order_by(subq.asc() if ascending else subq.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('rating',):
        col = Media.rating
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('filename', 'name'):
        col = Media.filename
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('filetype', 'file_type'):
        col = Media.file_type
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('md5', 'hash'):
        col = Media.hash
        return query.order_by(col.asc() if ascending else col.desc(), Media.id.asc() if ascending else Media.id.desc())

    if base_sort in ('random', 'rank', 'shuffle'):
        seed = "0"
        if ':' in order_val:
            seed = order_val.split(':', 1)[1].strip()
        from sqlalchemy import String
        hash_input = func.concat(cast(Media.id, String), literal(seed))
        return query.order_by(func.md5(hash_input))

    if base_sort == 'custom':
        id_list = None
        if 'id' in parsed_meta:
            for item in parsed_meta['id']:
                if ',' in item['value']:
                    try:
                        id_list = [int(x) for x in item['value'].split(',') if x.strip().isdigit()]
                        if id_list:
                            whens = {id_: i for i, id_ in enumerate(id_list)}
                            return query.order_by(case(whens, value=Media.id))
                    except (ValueError, TypeError):
                        pass

    # Fallback to default
    col = Media.uploaded_at
    return query.order_by(col.desc(), Media.id.desc())

def build_search_criteria_conditions(parsed_query: Dict[str, Any], db: Session) -> List[Any]:
    """
    Builds a list of SQLAlchemy filter conditions for the given parsed search query.
    """
    conditions = []
    tags = parsed_query.get('tags', {})

    include_names = [name.lower() for name in tags.get('include', [])]
    if include_names:
        found_tags = db.query(Tag).filter(Tag.name.in_(include_names)).all()
        # Use lowercase keys for robust lookup
        found_map = {t.name.lower(): t for t in found_tags}
        
        # If any included tag is missing, result is empty (AND logic)
        for name in include_names:
            if name not in found_map:
                return [literal(False)]
            
        # Apply filters for found tags
        for tag in found_tags:
            conditions.append(Media.tags.any(Tag.id == tag.id))

    exclude_names = [name.lower() for name in tags.get('exclude', [])]
    if exclude_names:
        found_excluded = db.query(Tag).filter(Tag.name.in_(exclude_names)).all()
        for tag in found_excluded:
            conditions.append(~Media.tags.any(Tag.id == tag.id))

    for wildcard_type, pattern in tags.get('wildcards', []):
        regex_pattern = wildcard_to_regex(pattern)
        subquery = exists().where(
            and_(
                blombooru_media_tags.c.media_id == Media.id,
                blombooru_media_tags.c.tag_id == Tag.id,
                Tag.name.op('~*')(regex_pattern)
            )
        )
        if wildcard_type == 'include':
            conditions.append(subquery)
        else:
            conditions.append(~subquery)
            
    meta = parsed_query.get('meta', {})
    
    def get_numeric_multi_conditions(key, column, converter=int):
        conds = []
        if key in meta:
            for item in meta[key]:
                cond = build_range_condition(column, item['value'], converter=converter)
                if cond is not None:
                    conds.append(not_(cond) if item['negated'] else cond)
        return conds

    conditions.extend(get_numeric_multi_conditions('id', Media.id))
    conditions.extend(get_numeric_multi_conditions('width', Media.width))
    conditions.extend(get_numeric_multi_conditions('height', Media.height))
    conditions.extend(get_numeric_multi_conditions('duration', Media.duration, converter=float))

    if 'filesize' in meta:
        for item in meta['filesize']:
            cond = build_filesize_condition(Media.file_size, item['value'])
            if cond is not None:
                conditions.append(not_(cond) if item['negated'] else cond)

    if 'date' in meta:
        for item in meta['date']:
            cond = build_date_condition(Media.uploaded_at, item['value'])
            if cond is not None:
                conditions.append(not_(cond) if item['negated'] else cond)

    if 'age' in meta:
        for item in meta['age']:
            cond = build_age_condition(Media.uploaded_at, item['value'])
            if cond is not None:
                conditions.append(not_(cond) if item['negated'] else cond)

    if 'rating' in meta:
        for item in meta['rating']:
            valid_map = {
                's': RatingEnum.safe, 'safe': RatingEnum.safe,
                'q': RatingEnum.questionable, 'questionable': RatingEnum.questionable,
                'e': RatingEnum.explicit, 'explicit': RatingEnum.explicit
            }
            vals = [v.strip().lower() for v in item['value'].split(',') if v.strip()]
            ratings = [valid_map[v] for v in vals if v in valid_map]

            if ratings:
                if item['negated']:
                    conditions.append(~Media.rating.in_(ratings))
                else:
                    conditions.append(Media.rating.in_(ratings))

    if 'source' in meta:
        for item in meta['source']:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                if v_lower == 'none':
                    conds.append(or_(Media.source == None, Media.source == ""))
                elif v_lower == 'http':
                    conds.append(Media.source.like('http%'))
                else:
                    conds.append(or_(
                        Media.source.ilike(f"%{v}%"),
                        Media.source.ilike(f"{v}%")
                    ))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'md5' in meta:
        for item in meta['md5']:
            hashes = [h.strip() for h in item['value'].split(',') if h.strip()]
            if hashes:
                if item['negated']:
                    conditions.append(~Media.hash.in_(hashes))
                else:
                    conditions.append(Media.hash.in_(hashes))

    if 'filetype' in meta:
        for item in meta['filetype']:
            types = [t.strip().lower() for t in item['value'].split(',') if t.strip()]
            conds = []
            for t in types:
                if t in ('image', 'video'):
                    conds.append(Media.file_type == FileTypeEnum(t))
                elif t == 'gif':
                    conds.append(or_(Media.file_type == FileTypeEnum.gif, Media.filename.ilike('%.gif')))
                else:
                    conds.append(Media.filename.ilike(f"%.{t}"))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'pool' in meta or 'album' in meta:
        items = meta.get('pool', []) + meta.get('album', [])
        for item in items:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                if v_lower == 'any':
                    conds.append(Media.albums.any())
                elif v_lower == 'none':
                    conds.append(~Media.albums.any())
                elif v.isdigit():
                    conds.append(Media.albums.any(Album.id == int(v)))
                else:
                    name_clean = v.replace('_', ' ')
                    conds.append(Media.albums.any(Album.name.ilike(name_clean)))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'pool_tree' in meta or 'album_tree' in meta:
        from .album_utils import get_descendant_ids
        items = meta.get('pool_tree', []) + meta.get('album_tree', [])
        for item in items:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                if v_lower == 'any':
                    conds.append(Media.albums.any())
                elif v_lower == 'none':
                    conds.append(~Media.albums.any())
                elif v.isdigit():
                    target_id = int(v)
                    desc_map = get_descendant_ids(db, [target_id])
                    tree_ids = list(desc_map.get(target_id, {target_id}))
                    conds.append(Media.albums.any(Album.id.in_(tree_ids)))
                else:
                    name_clean = v.replace('_', ' ')
                    matching_ids = [
                        r[0] for r in db.query(Album.id).filter(Album.name.ilike(name_clean)).all()
                    ]
                    if matching_ids:
                        desc_map = get_descendant_ids(db, matching_ids)
                        all_tree_ids = set()
                        for aids in desc_map.values():
                            all_tree_ids.update(aids)
                        conds.append(Media.albums.any(Album.id.in_(list(all_tree_ids))))
                    else:
                        conds.append(false())

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'parent' in meta:
        for item in meta['parent']:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                if v_lower == 'none':
                    conds.append(Media.parent_id == None)
                elif v_lower == 'any':
                    conds.append(Media.parent_id != None)
                elif v.isdigit():
                    pid = int(v)
                    conds.append(or_(Media.parent_id == pid, Media.id == pid))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    if 'child' in meta:
        for item in meta['child']:
            vals = [v.strip() for v in item['value'].split(',') if v.strip()]
            conds = []
            for v in vals:
                v_lower = v.lower()
                child_alias = aliased(Media)
                if v_lower == 'none':
                    conds.append(~exists().where(child_alias.parent_id == Media.id))
                elif v_lower == 'any':
                    conds.append(exists().where(child_alias.parent_id == Media.id))
                elif v.isdigit():
                    cid = int(v)
                    conds.append(exists().where(and_(child_alias.parent_id == Media.id, child_alias.id == cid)))

            if conds:
                combined_cond = or_(*conds) if len(conds) > 1 else conds[0]
                if item['negated']:
                    conditions.append(not_(combined_cond))
                else:
                    conditions.append(combined_cond)

    tag_counts_map = {
        'tagcount': None,
        'gentags': TagCategoryEnum.general,
        'arttags': TagCategoryEnum.artist,
        'chartags': TagCategoryEnum.character,
        'copytags': TagCategoryEnum.copyright,
        'metatags': TagCategoryEnum.meta
    }
    
    for key, category in tag_counts_map.items():
        if key in meta:
            for item in meta[key]:
                if category is not None:
                     # Join Tag to check category
                     subq = (
                         db.query(func.count(blombooru_media_tags.c.tag_id))
                         .join(Tag, blombooru_media_tags.c.tag_id == Tag.id)
                         .filter(blombooru_media_tags.c.media_id == Media.id)
                         .filter(Tag.category == category)
                         .scalar_subquery()
                     )
                else:
                    subq = (
                        db.query(func.count(blombooru_media_tags.c.tag_id))
                        .filter(blombooru_media_tags.c.media_id == Media.id)
                        .scalar_subquery()
                    )

                cond = build_range_condition(subq, item['value'], converter=int)
                if cond is not None:
                    if item['negated']:
                        conditions.append(not_(cond))
                    else:
                        conditions.append(cond)

    return conditions

def apply_search_criteria(query: Query, parsed_query: Dict[str, Any], db: Session) -> Query:
    """
    Applies the parsed search criteria to a SQLAlchemy query.
    """
    conditions = build_search_criteria_conditions(parsed_query, db)
    for cond in conditions:
        query = query.filter(cond)

    order_val = None
    meta = parsed_query.get('meta', {})
    if 'order' in meta:
        order_val = meta['order'][-1]['value']
    elif 'sort' in meta:
        order_val = meta['sort'][-1]['value']
        
    if order_val:
        query = apply_sort_ordering(query, order_val, db, meta)

    return query

def apply_custom_filters_or(query: Query, custom_filters: Any, db: Session) -> Query:
    """
    Applies multiple custom filter query strings combined with OR logic.
    Each individual custom filter string has its internal tokens ANDed together.
    """
    if not custom_filters or not isinstance(custom_filters, (list, tuple, str, set)):
        return query

    if isinstance(custom_filters, str):
        filters_list = [custom_filters]
    else:
        filters_list = list(custom_filters)

    clean_filters = [cf.strip() for cf in filters_list if isinstance(cf, str) and cf.strip()]
    if not clean_filters:
        return query

    branch_conditions = []
    for cf in clean_filters:
        cf_parsed = parse_search_query(cf)
        conds = build_search_criteria_conditions(cf_parsed, db)
        if conds:
            if len(conds) == 1:
                branch_conditions.append(conds[0])
            else:
                branch_conditions.append(and_(*conds))
        else:
            branch_conditions.append(literal(True))

    if branch_conditions:
        if len(branch_conditions) == 1:
            query = query.filter(branch_conditions[0])
        else:
            query = query.filter(or_(*branch_conditions))

    return query
