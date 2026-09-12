from typing import Any, Optional

def decode_exif_user_comment(raw: Any) -> Optional[str]:
    """Decode EXIF UserComment (tag 0x9286 / 37510)."""
    if raw is None:
        return None

    if isinstance(raw, str):
        cleaned = raw.strip()
        if cleaned.startswith("UNICODE") or cleaned.startswith("ASCII"):
            cleaned = cleaned[7:].strip()
        return cleaned if cleaned else None

    if not isinstance(raw, (bytes, bytearray)):
        return str(raw).strip() or None

    data = bytes(raw)
    if not data:
        return None

    # Standard EXIF UserComment prefix is 8 bytes
    if len(data) >= 8:
        prefix = data[:8]
        payload = data[8:]

        # UNICODE\0 encoding (UTF-16)
        if prefix.startswith(b"UNICODE\x00") or prefix.startswith(b"UNICODE"):
            # Check BOM or endianness
            if payload.startswith(b"\xff\xfe"):
                try:
                    return payload[2:].decode("utf-16-le", errors="replace").replace("\x00", "").strip()
                except Exception:
                    pass
            elif payload.startswith(b"\xfe\xff"):
                try:
                    return payload[2:].decode("utf-16-be", errors="replace").replace("\x00", "").strip()
                except Exception:
                    pass

            # Detect endianness from null byte patterns if ASCII text encoded as UTF-16
            if len(payload) >= 2 and payload[1] == 0 and payload[0] != 0:
                try:
                    return payload.decode("utf-16-le", errors="replace").replace("\x00", "").strip()
                except Exception:
                    pass
            elif len(payload) >= 2 and payload[0] == 0 and payload[1] != 0:
                try:
                    return payload.decode("utf-16-be", errors="replace").replace("\x00", "").strip()
                except Exception:
                    pass

            # Fallbacks for UNICODE payload
            for enc in ("utf-16-le", "utf-16-be", "utf-8", "latin-1"):
                try:
                    res = payload.decode(enc).replace("\x00", "").strip()
                    if res:
                        return res
                except Exception:
                    pass

        # ASCII\0\0\0 encoding
        if prefix.startswith(b"ASCII\x00\x00\x00") or prefix.startswith(b"ASCII"):
            try:
                return payload.decode("utf-8", errors="replace").replace("\x00", "").strip()
            except Exception:
                try:
                    return payload.decode("latin-1", errors="replace").replace("\x00", "").strip()
                except Exception:
                    pass

        # 8 null bytes header
        if prefix == b"\x00" * 8:
            for enc in ("utf-8", "utf-16-le", "latin-1"):
                try:
                    res = payload.decode(enc).replace("\x00", "").strip()
                    if res:
                        return res
                except Exception:
                    pass

    # Generic raw payload decode
    for enc in ("utf-8", "utf-16-le", "latin-1"):
        try:
            res = data.decode(enc).replace("\x00", "").strip()
            if res:
                return res
        except Exception:
            pass

    return None
