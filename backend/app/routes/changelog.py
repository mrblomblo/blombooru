import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from wenmode import Wenmode
from wenmode.presets import github

from ..auth import require_admin_mode
from ..config import APP_VERSION, settings
from ..utils.logger import logger

router = APIRouter(prefix="/api/changelog", tags=["changelog"])

CHANGELOG_PATH = settings.BASE_DIR / "CHANGELOG.md"
wen = Wenmode(github())

class ChangelogResponse(BaseModel):
    needs_modal: bool
    current_version: Optional[str] = None
    html: Optional[str] = None

@router.get("", response_model=ChangelogResponse)
async def get_changelog(current_user: dict = Depends(require_admin_mode)):
    """Get changelog content and check if the What's Changed modal should be shown."""
    if not CHANGELOG_PATH.exists() or not CHANGELOG_PATH.is_file():
        return ChangelogResponse(needs_modal=False)

    try:
        content = CHANGELOG_PATH.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.error(f"Failed to read CHANGELOG.md: {e}")
        return ChangelogResponse(needs_modal=False)

    if not content:
        return ChangelogResponse(needs_modal=False)

    last_seen = settings.LAST_SEEN_VERSION

    # On a fresh installation where last_seen_version has never been recorded,
    # silently record the current version so first install skips the modal.
    if last_seen is None:
        try:
            settings.save_settings({"last_seen_version": APP_VERSION})
        except Exception as e:
            logger.error(f"Failed to save initial last_seen_version: {e}")
        return ChangelogResponse(needs_modal=False)

    if last_seen == APP_VERSION:
        return ChangelogResponse(needs_modal=False)

    def linkify_version_headings(text: str) -> str:
        def replace_heading(m):
            hashes = m.group(1)
            ver_raw = m.group(2).strip()
            tag = ver_raw if ver_raw.startswith("v") else f"v{ver_raw}"
            url = f"https://github.com/mrblomblo/blombooru/releases/tag/{tag}"
            return f"{hashes}[{ver_raw}]({url})"

        return re.sub(r'^(#{1,6}\s+)(v?\d+[\w\.\-]*)$', replace_heading, text, flags=re.MULTILINE)

    linked_content = linkify_version_headings(content)
    sections = [s.strip() for s in re.split(r'(?m)^(?=##\s+)', linked_content) if s.strip()] or [linked_content]

    try:
        rendered_sections = []
        for s in sections:
            rendered = wen.render(s)
            rendered = re.sub(
                r'<a\s+(?!.*?target=)(href="[^"]+")',
                r'<a target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" \1',
                rendered
            )
            rendered_sections.append(f'<div class="changelog-version bg p-3 md:p-4 border">{rendered}</div>')
        html = "\n".join(rendered_sections)
    except Exception as e:
        logger.error(f"Error rendering CHANGELOG.md: {e}")
        html = "\n".join(
            f'<div class="changelog-version bg p-3 md:p-4 border"><pre>{s}</pre></div>'
            for s in sections
        )

    return ChangelogResponse(
        needs_modal=True,
        current_version=APP_VERSION,
        html=html
    )

@router.post("/acknowledge")
async def acknowledge_changelog(current_user: dict = Depends(require_admin_mode)):
    """Acknowledge that the changelog for the current version has been seen."""
    settings.save_settings({"last_seen_version": APP_VERSION})
    return {"ok": True}
