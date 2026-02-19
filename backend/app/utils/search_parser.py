import re
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, not_, desc, asc, func, exists, cast, Date, Float, case, text, literal
from sqlalchemy.orm import Session, Query, aliased
from ..models import Media, Tag, RatingEnum, blombooru_media_tags, Album, blombooru_album_media, TagCategoryEnum

TOKEN_PATTERN = re.compile(r'(-?)(?:([a-zA-Z0-9_]+):)?("[^"]*"|[^\s"]+)')

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
        parts = value.split('..')
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
    
    # List: 1,2,3
    if ',' in value:
        return {'op': 'in', 'value': [converter(v) for v in value.split(',') if v]}
    
    # Exact match
    return {'op': 'eq', 'value': converter(value)}

def parse_date_range(value: str) -> Dict[str, Any]:
    """Parse date values (YYYY-MM-DD)."""
    def to_date(s):
        return datetime.strptime(s, "%Y-%m-%d").date()
    
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
    
    def parse_time_unit(s):
        units = {
            's': 'seconds', 'sec': 'seconds',
            'mi': 'minutes', 'min': 'minutes',
            'h': 'hours',
            'd': 'days',
            'w': 'weeks',
            'mo': 'months', # approx 30 days
            'y': 'years'    # approx 365 days
        }
        
        # Split number and alpha
        m = re.match(r'^(\d+)([a-z]+)$', s, re.IGNORECASE)
        if not m:
            return timedelta(days=0)
        
        num = int(m.group(1))
        unit_str = m.group(2).lower()
        
        # Approximate matching for units
        for k in units:
            if unit_str.startswith(k):
                target_unit = units[k]
                if unit_str == k: # exact match
                    break
        
        # Handling month/year approx
        if unit_str.startswith('mo'): delta = timedelta(days=num * 30)
        elif unit_str.startswith('y'): delta = timedelta(days=num * 365)
        elif unit_str.startswith('w'): delta = timedelta(weeks=num)
        elif unit_str.startswith('d'): delta = timedelta(days=num)
        elif unit_str.startswith('h'): delta = timedelta(hours=num)
        elif unit_str.startswith('mi'): delta = timedelta(minutes=num)
        elif unit_str.startswith('s'): delta = timedelta(seconds=num)
        else: delta = timedelta(days=0)
        
        return delta
    
    criteria = parse_range(value, converter=lambda x: x) # keep as string
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
    def parse_size(s, multiplier):
        try:
            return int(float(s) * multiplier)
        except ValueError:
            return 0

    val_lower = value.lower()
    
    # Check for units to determine range
    multiplier = 1
    unit_found = False
    
    if val_lower.endswith('kb'):
        multiplier = 1024
        val_lower = val_lower[:-2]
        unit_found = True
    elif val_lower.endswith('k'):
        multiplier = 1024
        val_lower = val_lower[:-1]
        unit_found = True
    elif val_lower.endswith('mb'):
        multiplier = 1024 * 1024
        val_lower = val_lower[:-2]
        unit_found = True
    elif val_lower.endswith('m'):
        multiplier = 1024 * 1024
        val_lower = val_lower[:-1]
        unit_found = True
    elif val_lower.endswith('gb'):
        multiplier = 1024 * 1024 * 1024
        val_lower = val_lower[:-2]
        unit_found = True
    elif val_lower.endswith('g'):
        multiplier = 1024 * 1024 * 1024
        val_lower = val_lower[:-1]
        unit_found = True
    elif val_lower.endswith('b'):
        val_lower = val_lower[:-1]
        
    if unit_found and '..' not in value and not any(op in value for op in ['>', '<', ',']):
        # If a specific unit was given without an operator, assume fuzzy range [val, val+1_unit)
        try:
            base_val = float(val_lower)
            start_bytes = int(base_val * multiplier)
            # Use 1 of the unit as the range width
            end_bytes = start_bytes + multiplier
            
            return {'op': 'between', 'value': (start_bytes, end_bytes - 1)}
        except ValueError:
            pass

    # Fallback if no unit inference needed
    def simple_parse_size(s):
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
            s = s[:-1]
            
        try:
            return int(float(s) * mul)
        except ValueError:
            return 0
            
    return parse_range(value, converter=simple_parse_size)

def wildcard_to_regex(pattern: str) -> str:
    """Convert wildcard pattern to PostgreSQL regex pattern"""
    special_chars = ['.', '^', '$', '+', '(', ')', '[', ']', '{', '}', '|', '\\']
    for char in special_chars:
        pattern = pattern.replace(char, '\\' + char)
    
    pattern = pattern.replace('*', '.*')
    pattern = pattern.replace('?', '.?')
    pattern = '^' + pattern + '$'
    return pattern

def apply_range_filter(query, column, criteria):
    op = criteria['op']
    val = criteria['value']
    
    if op == 'between':
        return query.filter(column.between(val[0], val[1]))
    elif op == 'ge':
        return query.filter(column >= val)
    elif op == 'le':
        return query.filter(column <= val)
    elif op == 'gt':
        return query.filter(column > val)
    elif op == 'lt':
        return query.filter(column < val)
    elif op == 'in':
        return query.filter(column.in_(val))
    elif op == 'eq':
        return query.filter(column == val)
    return query

def apply_search_criteria(query: Query, parsed_query: Dict[str, Any], db: Session) -> Query:
    """
    Applies the parsed search criteria to a SQLAlchemy query.
    """
    tags = parsed_query['tags']

    include_names = [name.lower() for name in tags['include']]
    if include_names:
        found_tags = db.query(Tag).filter(Tag.name.in_(include_names)).all()
        # Use lowercase keys for robust lookup
        found_map = {t.name.lower(): t for t in found_tags}
        
        # If any included tag is missing, result is empty (AND logic)
        for name in include_names:
            if name not in found_map:
                from sqlalchemy import literal
                return query.filter(literal(False))
            
        # Apply filters for found tags
        for tag in found_tags:
            query = query.filter(Media.tags.contains(tag))

    exclude_names = [name.lower() for name in tags['exclude']]
    if exclude_names:
        found_excluded = db.query(Tag).filter(Tag.name.in_(exclude_names)).all()
        for tag in found_excluded:
             query = query.filter(~Media.tags.contains(tag))

    for wildcard_type, pattern in tags['wildcards']:
        regex_pattern = wildcard_to_regex(pattern)
        subquery = exists().where(
            and_(
                blombooru_media_tags.c.media_id == Media.id,
                blombooru_media_tags.c.tag_id == Tag.id,
                Tag.name.op('~*')(regex_pattern)
            )
        )
        if wildcard_type == 'include':
            query = query.filter(subquery)
        else:
            query = query.filter(~subquery)
            
    meta = parsed_query['meta']
    
    def apply_numeric_filter(query, key, column, converter=int):
        if key in meta:
            for item in meta[key]:
                try:
                    criteria = parse_range(item['value'], converter=converter)
                    if item['negated']:
                        op = criteria['op']
                        val = criteria['value']
                        cond = None
                        if op == 'between': cond = column.between(val[0], val[1])
                        elif op == 'ge': cond = column >= val
                        elif op == 'le': cond = column <= val
                        elif op == 'gt': cond = column > val
                        elif op == 'lt': cond = column < val
                        elif op == 'in': cond = column.in_(val)
                        elif op == 'eq': cond = column == val
                        
                        if cond is not None:
                            query = query.filter(not_(cond))
                    else:
                        query = apply_range_filter(query, column, criteria)
                except ValueError:
                    pass
        return query
    
    query = apply_numeric_filter(query, 'id', Media.id)
    query = apply_numeric_filter(query, 'width', Media.width)
    query = apply_numeric_filter(query, 'height', Media.height)
    query = apply_numeric_filter(query, 'duration', Media.duration, converter=float)
    
    if 'filesize' in meta:
        for item in meta['filesize']:
            criteria = parse_filesize(item['value'])
            if not item['negated']:
                query = apply_range_filter(query, Media.file_size, criteria)
            else:
                # Negate the 'eq' case if it's not a range
                if criteria['op'] == 'eq':
                    query = query.filter(Media.file_size != criteria['value'])
                else:
                    pass

    if 'date' in meta:
        for item in meta['date']:
            criteria = parse_date_range(item['value'])
            if not item['negated']:
                query = apply_range_filter(query, cast(Media.uploaded_at, Date), criteria)

    if 'age' in meta:
        for item in meta['age']:
            criteria = parse_age(item['value'])
            if not item['negated']:
               query = apply_range_filter(query, Media.uploaded_at, criteria)

    if 'rating' in meta:
        for item in meta['rating']:
            val = item['value'].lower()
            ratings = []
            
            # Expand abbreviations
            valid_map = {
                's': RatingEnum.safe, 'safe': RatingEnum.safe,
                'q': RatingEnum.questionable, 'questionable': RatingEnum.questionable,
                'e': RatingEnum.explicit, 'explicit': RatingEnum.explicit
            }
            
            # Handle list: rating:s,q
            vals = val.split(',')
            for v in vals:
                if v in valid_map:
                    ratings.append(valid_map[v])
            
            if ratings:
                if item['negated']:
                    query = query.filter(~Media.rating.in_(ratings))
                else:
                    query = query.filter(Media.rating.in_(ratings))

    if 'source' in meta:
        for item in meta['source']:
            val = item['value'].lower()
            negated = item['negated']
            
            if val == 'none':
                cond = or_(Media.source == None, Media.source == "")
            elif val == 'http':
                cond = Media.source.like('http%')
            else:
                cond = Media.source.like(f"{item['value']}%")
            
            if negated:
                query = query.filter(not_(cond))
            else:
                query = query.filter(cond)

    if 'md5' in meta:
        for item in meta['md5']:
            query = query.filter(Media.hash == item['value'].strip())

    if 'filetype' in meta:
        for item in meta['filetype']:
            ext = item['value'].lower()
            cond = Media.filename.ilike(f"%.{ext}")
            if item['negated']:
                query = query.filter(not_(cond))
            else:
                query = query.filter(cond)

    if 'pool' in meta or 'album' in meta:
        items = meta.get('pool', []) + meta.get('album', [])
        for item in items:
            val = item['value'].lower()
            negated = item['negated']
            
            if val == 'any':
                cond = Media.albums.any()
            elif val == 'none':
                cond = ~Media.albums.any()
            elif val.isdigit():
                cond = Media.albums.any(Album.id == int(val))
            else:
                name_clean = val.replace('_', ' ')
                cond = Media.albums.any(Album.name.ilike(name_clean))
            
            if negated:
                 query = query.filter(not_(cond))
            else:
                 query = query.filter(cond)

    if 'parent' in meta:
        for item in meta['parent']:
            val = item['value'].lower()
            if val == 'none':
                query = query.filter(Media.parent_id == None)
            elif val == 'any':
                query = query.filter(Media.parent_id != None)
            elif val.isdigit():
                pid = int(val)
                query = query.filter(or_(Media.parent_id == pid, Media.id == pid))

    if 'child' in meta:
        for item in meta['child']:
            val = item['value'].lower()
            if val == 'none':
                child_alias = aliased(Media)
                cond = exists().where(child_alias.parent_id == Media.id)
                query = query.filter(~cond)
            elif val == 'any':
                child_alias = aliased(Media)
                cond = exists().where(child_alias.parent_id == Media.id)
                query = query.filter(cond)

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
                criteria = parse_range(item['value'])
                op, val = criteria['op'], criteria['value']
                
                stmt = func.count(blombooru_media_tags.c.tag_id)
                where_clause = [blombooru_media_tags.c.media_id == Media.id]
                
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
                
                if op == 'between': query = query.filter(subq.between(val[0], val[1]))
                elif op == 'ge': query = query.filter(subq >= val)
                elif op == 'le': query = query.filter(subq <= val)
                elif op == 'gt': query = query.filter(subq > val)
                elif op == 'lt': query = query.filter(subq < val)
                elif op == 'eq': query = query.filter(subq == val)

    order_val = 'id_desc'
    if 'order' in meta:
        order_val = meta['order'][-1]['value']
    elif 'sort' in meta:
        order_val = meta['sort'][-1]['value']
        
    if order_val == 'id': query = query.order_by(desc(Media.id))
    elif order_val == 'id_asc': query = query.order_by(asc(Media.id))
    elif order_val == 'id_desc': query = query.order_by(desc(Media.id))
    elif order_val == 'filesize': query = query.order_by(desc(Media.file_size))
    elif order_val == 'landscape': query = query.order_by(desc(cast(Media.width, Float) / Media.height))
    elif order_val == 'portrait': query = query.order_by(desc(cast(Media.height, Float) / Media.width))
    elif order_val == 'md5': query = query.order_by(Media.hash)
    elif order_val == 'custom':
        id_list = None
        if 'id' in meta:
            for item in meta['id']:
                 if ',' in item['value']:
                     try:
                         id_list = [int(x) for x in item['value'].split(',')]
                         whens = {id_: i for i, id_ in enumerate(id_list)}
                         query = query.order_by(case(whens, value=Media.id))
                     except (ValueError, TypeError): pass
    else:
        if not query._order_by_clauses:
             query = query.order_by(desc(Media.uploaded_at))

    return query
