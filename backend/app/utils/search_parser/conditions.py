from datetime import datetime, timedelta
from sqlalchemy import func, or_
from .tokens import _parse_size_bytes, _strip_size_unit, parse_time_unit

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

def build_filename_condition(column, value_str: str):
    """Builds a SQLAlchemy boolean expression for filename matching with wildcards and multi-values."""
    parts = [p.strip() for p in value_str.split(',') if p.strip()]
    if not parts:
        return None

    conditions = []
    for part in parts:
        has_wildcard = '*' in part or '?' in part
        escaped = part.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        if has_wildcard:
            pattern = escaped.replace('*', '%').replace('?', '_')
            conditions.append(column.ilike(pattern, escape='\\'))
        else:
            if '.' not in part:
                conditions.append(or_(
                    column.ilike(escaped, escape='\\'),
                    column.ilike(f"{escaped}.%", escape='\\')
                ))
            else:
                conditions.append(column.ilike(escaped, escape='\\'))

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return or_(*conditions)
