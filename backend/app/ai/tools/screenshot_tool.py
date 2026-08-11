"""
Captures visual evidence per finding. Screenshots are written under
settings.AI_SCREENSHOT_DIR (served by app.main's /static mount) and every
capture function returns the *public URL*, never a filesystem path, so
callers can drop the result straight into StepResult.evidence.
"""
from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import Page

from app.config import settings

logger = logging.getLogger(__name__)


def _run_dir(run_id: int) -> Path:
    directory = Path(settings.AI_SCREENSHOT_DIR) / str(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _public_url(local_path: Path) -> str:
    posix = local_path.as_posix()
    prefix = "static/"
    if posix.startswith(prefix):
        posix = posix[len(prefix) :]
    return f"/static/{posix}"


async def capture_full_page(page: Page, run_id: int, name: str = "full_page") -> str | None:
    path = _run_dir(run_id) / f"{name}.png"
    try:
        await page.screenshot(path=str(path), full_page=True, timeout=15000)
    except Exception:
        logger.warning("Full-page screenshot failed for run %s", run_id, exc_info=True)
        return None
    return _public_url(path)


async def capture_element(page: Page, run_id: int, selector: str, name: str) -> str | None:
    locator = page.locator(selector).first
    try:
        await locator.wait_for(state="attached", timeout=3000)
    except Exception:
        return None

    path = _run_dir(run_id) / f"{name}.png"
    try:
        await locator.screenshot(path=str(path), timeout=8000)
    except Exception:
        logger.info("Element screenshot failed for selector %r in run %s", selector, run_id)
        return None
    return _public_url(path)
