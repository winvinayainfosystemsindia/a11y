"""
Shared Playwright page lifecycle for one audit run. PERCEIVE and EXECUTE
share a single browser page (opened once by agent.py) so deterministic tool
checks (axe, contrast, keyboard nav, screenshots) all run against the exact
same rendered DOM the plan was built from - not a second, possibly
different, page load.
"""
from __future__ import annotations

import contextlib
from typing import AsyncIterator

from playwright.async_api import Page, async_playwright

from app.config import settings

USER_AGENT = "A11yAuditBot/1.0 (+accessibility AI audit agent; respects robots.txt)"


@contextlib.asynccontextmanager
async def open_page(url: str) -> AsyncIterator[Page]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport={"width": 1366, "height": 900},
                user_agent=USER_AGENT,
            )
            page = await context.new_page()
            await page.goto(url, wait_until="load", timeout=settings.AI_PAGE_LOAD_TIMEOUT_MS)
            yield page
        finally:
            await browser.close()
