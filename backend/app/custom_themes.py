import io
import json
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import tinycss2

from .config import APP_VERSION, settings
from .utils.logger import logger
from .translations import translation_helper

_t = lambda key, **kw: translation_helper.get(f"admin.settings.custom_themes.errors.{key}", **kw)

MAX_CSS_BYTES = 50 * 1024  # 50 KB
CUSTOM_THEMES_JSON = settings.DATA_DIR / "custom_themes.json"
CUSTOM_THEMES_DIR = settings.DATA_DIR / "custom_themes"

# Potentially harmful
_BLOCKED_PATTERNS = [
    re.compile(r"expression\s*\(", re.IGNORECASE),          # IE expression()
    re.compile(r"javascript\s*:", re.IGNORECASE),            # JS URI scheme
    re.compile(r"-moz-binding\s*:", re.IGNORECASE),          # Firefox binding
    re.compile(r"<\s*/?\s*script", re.IGNORECASE),           # script tag injection
    re.compile(r"<\s*/?\s*style", re.IGNORECASE),            # style tag escape
]

def sanitize_css(raw_css: str) -> str:
    """Parse and sanitize user-supplied CSS using tinycss2."""
    if not isinstance(raw_css, str):
        raise ValueError("CSS must be a string")

    # Strip null bytes and non-printable control chars, but keep newlines and tabs
    raw_css = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw_css)

    if len(raw_css.encode("utf-8")) > MAX_CSS_BYTES:
        raise ValueError(_t("css_too_large", limit=MAX_CSS_BYTES // 1024))

    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(raw_css):
            raise ValueError(_t("disallowed_construct"))

    rules = tinycss2.parse_stylesheet(raw_css, skip_comments=True, skip_whitespace=False)

    output_parts: list[str] = []

    for rule in rules:
        if rule.type == "error":
            # Skip parse errors silently
            continue

        if rule.type == "at-rule":
            rule_name = (rule.at_keyword or "").lower()

            if rule_name == "import":
                # Re-check the prelude for blocked patterns
                import_prelude = tinycss2.serialize(rule.prelude)
                _check_value_string(import_prelude)
                output_parts.append(tinycss2.serialize([rule]))
                continue

            # Allow other at-rules (@keyframes, @font-face, @media, etc.)
            if rule.content is not None:
                sanitized_content = _sanitize_declaration_list(rule.content)
                # Re-serialize the at-rule with sanitized content
                prelude_str = tinycss2.serialize(rule.prelude)
                _check_value_string(prelude_str)
                output_parts.append(
                    f"@{rule.at_keyword} {prelude_str} {{{tinycss2.serialize(sanitized_content)}}}"
                )
            else:
                prelude_str = tinycss2.serialize(rule.prelude)
                _check_value_string(prelude_str)
                output_parts.append(f"@{rule.at_keyword} {prelude_str};")
            continue

        if rule.type == "qualified-rule":
            prelude_str = tinycss2.serialize(rule.prelude)
            _check_value_string(prelude_str)
            sanitized_content = _sanitize_declaration_list(rule.content)
            output_parts.append(
                f"{prelude_str} {{{tinycss2.serialize(sanitized_content)}}}"
            )
            continue

        # Keep whitespace, drop comments
        if rule.type == "whitespace":
            output_parts.append(rule.value)

    return "\n".join(output_parts)

def _sanitize_declaration_list(tokens: list) -> list:
    """
    Walk a declaration list (inside a rule block) and validate each
    declaration's value for blocked constructs.
    Returns the filtered token list.
    """
    declarations = tinycss2.parse_declaration_list(tokens, skip_comments=True)
    safe_tokens: list = []

    for decl in declarations:
        if decl.type == "error":
            continue
        if decl.type == "declaration":
            value_str = tinycss2.serialize(decl.value)
            _check_value_string(value_str)
            # Rebuild declaration tokens
            safe_tokens.append(decl)
        elif decl.type == "at-rule":
            # e.g. @apply inside a block -- allow but sanitize
            prelude_str = tinycss2.serialize(decl.prelude)
            _check_value_string(prelude_str)
            safe_tokens.append(decl)
        # whitespace nodes
        elif decl.type == "whitespace":
            safe_tokens.append(decl)

    return safe_tokens

def _check_value_string(value: str) -> None:
    """Raise ValueError if the value string matches any blocked pattern."""
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(value):
            raise ValueError(_t("disallowed_construct"))

def _extract_css_var(css: str, var_name: str) -> Optional[str]:
    """
    Extract the value of a CSS custom property. Returns the first match or None.
    """
    pattern = re.compile(
        rf"{re.escape(var_name)}\s*:\s*([^;}}]+)", re.IGNORECASE
    )
    m = pattern.search(css)
    if m:
        return m.group(1).strip()
    return None

def _slugify(name: str) -> str:
    """Convert a theme name to a safe filesystem/registry ID."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s_-]+", "_", name).strip("_")
    return name or "custom"

def _unique_id(base: str, existing_ids: set[str]) -> str:
    """Append a counter suffix until the ID is unique."""
    candidate = f"custom_{base}"
    if candidate not in existing_ids:
        return candidate
    for i in range(2, 10000):
        candidate = f"custom_{base}_{i}"
        if candidate not in existing_ids:
            return candidate
    raise RuntimeError("Could not generate a unique theme ID")

def _resolve_backup_theme_id(requested_id: str) -> str:
    """
    Validate and return a built-in (non-custom) theme ID to use as the fallback for a custom theme.
    If the requested ID is not a registered built-in, falls back to 'default_dark'.
    """
    from .themes import theme_registry
    theme = theme_registry.get_theme(requested_id)
    if theme is not None and not theme.is_custom:
        return requested_id
    return "default_dark"

class CustomThemeManager:
    """
    Manages user-created themes stored on disk.

    All mutating operations update custom_themes.json and the CSS file atomically-ish.
    """

    @property
    def custom_themes_dir(self) -> Path:
        p = settings.DATA_DIR / "custom_themes"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def custom_themes_json(self) -> Path:
        return settings.DATA_DIR / "custom_themes.json"

    def __init__(self) -> None:
        self.custom_themes_dir.mkdir(parents=True, exist_ok=True)
        self._meta: dict[str, dict] = self._load_meta()

    def _load_meta(self) -> dict[str, dict]:
        if self.custom_themes_json.exists():
            try:
                with self.custom_themes_json.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                logger.warning(f"Could not read custom_themes.json: {e}")
        return {}

    def _save_meta(self) -> None:
        with self.custom_themes_json.open("w", encoding="utf-8") as f:
            json.dump(self._meta, f, indent=2)

    def load_from_disk(self) -> None:
        """Register all saved custom themes into the global ThemeRegistry."""
        from .themes import theme_registry, Theme

        for theme_id, meta in list(self._meta.items()):
            css_path = self.custom_themes_dir / f"{theme_id}.css"
            if not css_path.exists():
                logger.warning(
                    f"Custom theme CSS missing for {theme_id!r}, skipping"
                )
                continue

            theme = Theme(
                id=theme_id,
                name=meta["name"],
                css_path=f"/data/themes/{theme_id}.css",
                is_dark=meta.get("is_dark", True),
                primary_color=meta.get("primary_color", "#3b82f6"),
                background_color=meta.get("background_color", "#0f172a"),
                is_custom=True,
            )
            theme_registry.register_theme(theme)

        logger.info(f"Loaded {len(self._meta)} custom theme(s)")

    def create_theme(
        self, name: str, is_dark: bool, css_content: str,
        backup_theme_id: str = "default_dark",
    ) -> dict:
        """
        Sanitize CSS, persist to disk, and register in ThemeRegistry.
        Returns the new theme metadata dict.
        Raises ValueError on validation failure.
        """
        name = name.strip()
        if not name:
            raise ValueError(_t("name_required"))
        if len(name) > 80:
            raise ValueError(_t("name_too_long"))

        clean_css = sanitize_css(css_content)
        if not clean_css.strip():
            raise ValueError(_t("no_valid_css"))

        theme_id = _unique_id(_slugify(name), set(self._meta.keys()))

        primary_color = _extract_css_var(clean_css, "--primary-color") or "#3b82f6"
        background_color = _extract_css_var(clean_css, "--background") or "#0f172a"

        primary_color = primary_color[:32]
        background_color = background_color[:32]

        backup_theme_id = _resolve_backup_theme_id(backup_theme_id)

        css_file = self.custom_themes_dir / f"{theme_id}.css"
        css_file.write_text(clean_css, encoding="utf-8")

        meta = {
            "name": name,
            "is_dark": is_dark,
            "primary_color": primary_color,
            "background_color": background_color,
            "backup_theme_id": backup_theme_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._meta[theme_id] = meta
        self._save_meta()

        from .themes import theme_registry, Theme

        theme_registry.register_theme(
            Theme(
                id=theme_id,
                name=name,
                css_path=f"/data/themes/{theme_id}.css",
                is_dark=is_dark,
                primary_color=primary_color,
                background_color=background_color,
                is_custom=True,
            )
        )

        return {"id": theme_id, **meta}

    def update_theme(
        self,
        theme_id: str,
        *,
        name: Optional[str] = None,
        is_dark: Optional[bool] = None,
        css_content: Optional[str] = None,
        backup_theme_id: Optional[str] = None,
    ) -> dict:
        """
        Update one or more fields of an existing custom theme.
        Returns the updated metadata dict.
        Raises KeyError if not found, ValueError on validation failure.
        """
        if theme_id not in self._meta:
            raise KeyError(f"Custom theme {theme_id!r} not found")

        meta = self._meta[theme_id]

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError(_t("name_required"))
            if len(name) > 80:
                raise ValueError(_t("name_too_long"))
            meta["name"] = name

        if is_dark is not None:
            meta["is_dark"] = is_dark

        if backup_theme_id is not None:
            meta["backup_theme_id"] = _resolve_backup_theme_id(backup_theme_id)

        if css_content is not None:
            clean_css = sanitize_css(css_content)
            if not clean_css.strip():
                raise ValueError(_t("no_valid_css"))
            css_file = self.custom_themes_dir / f"{theme_id}.css"
            css_file.write_text(clean_css, encoding="utf-8")
            meta["primary_color"] = (
                _extract_css_var(clean_css, "--primary-color") or meta.get("primary_color", "#3b82f6")
            )[:32]
            meta["background_color"] = (
                _extract_css_var(clean_css, "--background") or meta.get("background_color", "#0f172a")
            )[:32]

        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_meta()

        from .themes import theme_registry, Theme

        theme_registry.register_theme(
            Theme(
                id=theme_id,
                name=meta["name"],
                css_path=f"/data/themes/{theme_id}.css",
                is_dark=meta["is_dark"],
                primary_color=meta.get("primary_color", "#3b82f6"),
                background_color=meta.get("background_color", "#0f172a"),
                is_custom=True,
            )
        )

        return {"id": theme_id, **meta}

    def delete_theme(self, theme_id: str) -> None:
        """
        Remove a custom theme from disk and the registry.
        Raises KeyError if not found.
        Does NOT check whether the theme is currently active, callers are responsible for that guard.
        """
        if theme_id not in self._meta:
            raise KeyError(f"Custom theme {theme_id!r} not found")

        css_file = self.custom_themes_dir / f"{theme_id}.css"
        try:
            css_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Could not delete CSS file for {theme_id}: {e}")

        del self._meta[theme_id]
        self._save_meta()

        from .themes import theme_registry
        theme_registry.unregister_theme(theme_id)

    def get_css(self, theme_id: str) -> str:
        """Return raw CSS content for a custom theme. Raises KeyError if not found."""
        if theme_id not in self._meta:
            raise KeyError(f"Custom theme {theme_id!r} not found")
        css_file = self.custom_themes_dir / f"{theme_id}.css"
        if not css_file.exists():
            raise FileNotFoundError(f"CSS file for {theme_id!r} is missing")
        return css_file.read_text(encoding="utf-8")

    def get_all(self) -> list[dict]:
        """Return list of all custom theme metadata dicts (with id included)."""
        return [{"id": tid, **meta} for tid, meta in self._meta.items()]

    def export_bundle(self, theme_id: str) -> bytes:
        """
        Create a .blombooru-theme ZIP bundle containing:
        - theme.css (sanitized CSS)
        - theme.json (metadata: name, is_dark, exported_at, app_version)

        Returns the bundle bytes.
        """
        meta = self._meta.get(theme_id)
        if meta is None:
            raise KeyError(f"Custom theme {theme_id!r} not found")

        css_content = self.get_css(theme_id)

        manifest = {
            "name": meta["name"],
            "is_dark": meta["is_dark"],
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "app_version": APP_VERSION,
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("theme.css", css_content.encode("utf-8"))
            zf.writestr("theme.json", json.dumps(manifest, indent=2).encode("utf-8"))
        return buf.getvalue()

    def import_bundle(
        self,
        data: bytes,
        *,
        name_override: Optional[str] = None,
        is_dark_override: Optional[bool] = None,
    ) -> dict:
        """
        Import a .blombooru-theme bundle or a raw .css file.

        For bundles: reads name/is_dark from theme.json (overrides take precedence).
        For raw CSS:  name_override and is_dark_override are required.

        Returns the created theme metadata dict.
        """
        # Detect ZIP vs raw CSS
        if data[:2] == b"PK":
            # ZIP bundle
            try:
                buf = io.BytesIO(data)
                with zipfile.ZipFile(buf, "r") as zf:
                    names = zf.namelist()
                    if "theme.css" not in names:
                        raise ValueError(_t("bundle_missing_css"))

                    css_bytes = zf.read("theme.css")
                    if len(css_bytes) > MAX_CSS_BYTES:
                        raise ValueError(_t("bundle_css_too_large", limit=MAX_CSS_BYTES // 1024))
                    css_content = css_bytes.decode("utf-8", errors="replace")

                    meta_from_bundle: dict = {}
                    if "theme.json" in names:
                        try:
                            meta_from_bundle = json.loads(
                                zf.read("theme.json").decode("utf-8")
                            )
                        except Exception:
                            pass  # Ignore malformed metadata; user overrides will apply

            except zipfile.BadZipFile as exc:
                raise ValueError(_t("invalid_bundle", detail=str(exc))) from exc

            name = name_override or meta_from_bundle.get("name") or "Imported Theme"
            is_dark = is_dark_override if is_dark_override is not None else meta_from_bundle.get("is_dark", True)

        else:
            # Raw CSS
            if len(data) > MAX_CSS_BYTES:
                raise ValueError(_t("css_too_large", limit=MAX_CSS_BYTES // 1024))
            css_content = data.decode("utf-8", errors="replace")
            name = name_override or "Imported Theme"
            is_dark = is_dark_override if is_dark_override is not None else True

        return self.create_theme(name, is_dark, css_content)

custom_theme_manager = CustomThemeManager()

def get_backup_theme_for(custom_theme_id: str):
    """
    Return the built-in Theme that should be used in the admin panel
    (or any other fallback context) when `custom_theme_id` is the active theme.

    Resolution order:
    1. The backup_theme_id stored in the custom theme's metadata (if valid)
    2. 'default_dark'
    """
    from .themes import theme_registry

    meta = custom_theme_manager._meta.get(custom_theme_id, {})
    backup_id = meta.get("backup_theme_id", "default_dark")
    theme = theme_registry.get_theme(backup_id)
    if theme is None or theme.is_custom:
        theme = theme_registry.get_theme("default_dark")
    return theme
