import html
import re
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from wenmode import Wenmode
from wenmode.presets import github

from ..config import settings
from ..utils.logger import logger

router = APIRouter(prefix="/api/acknowledgements", tags=["acknowledgements"])

ACKNOWLEDGEMENTS_PATH = settings.BASE_DIR / "ACKNOWLEDGEMENTS.md"
wen = Wenmode(github())

_EXTERNAL_LINK_RE = re.compile(r'<a\s+(?!.*?target=)(href="https?://[^"]+")')

_cached_html: Optional[str] = None
_cached_mtime: Optional[float] = None

class AcknowledgementsResponse(BaseModel):
    html: Optional[str] = None

def _open_links_in_new_tab(rendered_html: str) -> str:
    return _EXTERNAL_LINK_RE.sub(
        r'<a target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" \1',
        rendered_html,
    )

def _render_preamble(preamble_text: str) -> str:
    try:
        rendered = _open_links_in_new_tab(wen.render(preamble_text))
    except Exception as e:
        logger.error(f"Error rendering acknowledgements preamble: {e}")
        rendered = f"<pre>{html.escape(preamble_text)}</pre>"
    return f'<div class="acknowledgement-preamble bg p-3 md:p-4 border mb-4 text-sm">{rendered}</div>'

def _render_package_card(pkg: dict) -> str:
    name = str(pkg.get("name", "")).strip()
    version = str(pkg.get("version", "")).strip()
    license_name = str(pkg.get("license", "")).strip()
    author = str(pkg.get("author", "")).strip()
    license_text = str(pkg.get("license_text", "")).strip()

    header = f"### {name} `{version}`" if version else f"### {name}"
    meta_lines = []
    if license_name:
        meta_lines.append(f"- **License**: {license_name}")
    if author:
        meta_lines.append(f"- **Author**: {author}")

    meta_md = "\n".join(meta_lines)
    full_md = f"{header}\n\n{meta_md}\n\n**License Text:**\n\n```\n{license_text}\n```"

    try:
        rendered = _open_links_in_new_tab(wen.render(full_md))
    except Exception as e:
        logger.error(f"Error rendering dependency card for {name}: {e}")
        rendered = f"<h3>{html.escape(name)}</h3><pre>{html.escape(license_text)}</pre>"

    pkg_key = html.escape(name.lower())
    return f'<div class="acknowledgement-card bg p-3 md:p-4 border space-y-2" data-pkg-name="{pkg_key}">{rendered}</div>'

def _parse_acknowledgements_md(content: str):
    parts = re.split(r"\n+---\n+(?=Name: )", content)
    if not parts:
        return "", []

    preamble_text = parts[0].strip()
    packages = []
    for entry_text in parts[1:]:
        entry_parts = re.split(r"\nLicense Text:\s*\n===\s*\n*", entry_text.strip(), maxsplit=1)
        meta_part = entry_parts[0]
        lic_text = entry_parts[1].strip() if len(entry_parts) > 1 else ""
        meta = {}
        for line in meta_part.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        packages.append({
            "name": meta.get("name", ""),
            "version": meta.get("version", ""),
            "license": meta.get("license", ""),
            "author": meta.get("author", ""),
            "license_text": lic_text,
        })
    return preamble_text, packages

def _render_acknowledgements() -> Optional[str]:
    global _cached_html, _cached_mtime

    if not ACKNOWLEDGEMENTS_PATH.exists() or not ACKNOWLEDGEMENTS_PATH.is_file():
        return None

    try:
        current_mtime = ACKNOWLEDGEMENTS_PATH.stat().st_mtime
        if _cached_html is not None and _cached_mtime == current_mtime:
            return _cached_html

        content = ACKNOWLEDGEMENTS_PATH.read_text(encoding="utf-8")
        preamble_text, packages = _parse_acknowledgements_md(content)
    except Exception as e:
        logger.error(f"Failed to read ACKNOWLEDGEMENTS.md: {e}")
        return None

    if not preamble_text and not packages:
        return None

    rendered_sections = []
    if preamble_text:
        rendered_sections.append(_render_preamble(preamble_text))

    for pkg in packages:
        try:
            rendered_sections.append(_render_package_card(pkg))
        except Exception as e:
            logger.error(f"Error rendering dependency card for {pkg.get('name')}: {e}")

    _cached_html = "\n".join(rendered_sections)
    _cached_mtime = current_mtime
    return _cached_html

@router.get("", response_model=AcknowledgementsResponse)
async def get_acknowledgements():
    """Get acknowledgements content rendered as HTML."""
    return AcknowledgementsResponse(html=_render_acknowledgements())
