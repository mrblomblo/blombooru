import re
from datetime import datetime, timedelta
from typing import (
    Any,
    Dict,
    Optional,
    Set,
    Tuple,
    Union,
)

TOKEN_PATTERN = re.compile(r'(-?)(?:([a-zA-Z0-9_]+):)?("[^"]*"|[^\s"]+)')

COMBINABLE_KEYS: Set[str] = {
    'rating', 'tagcount', 'gentags', 'arttags', 'chartags', 'copytags', 'metatags',
    'id', 'width', 'height', 'duration', 'filesize', 'date', 'age', 'filetype',
    'source', 'md5', 'album', 'pool', 'album_tree', 'pool_tree', 'parent', 'child',
    'custom_date', 'custom_age', 'filename', 'name', 'similar_to', 'similar_to_strict'
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
