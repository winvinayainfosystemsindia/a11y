"""
Async site crawler: given a base URL, discovers every unique page (by
normalized path) reachable within max_depth / max_pages, respecting
robots.txt by default. Pure crawling logic - no DB access happens here;
the controller/repository layer persists whatever this returns.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.utils.url_utils import get_hostname, is_same_site, normalize_url

logger = logging.getLogger(__name__)

USER_AGENT = "A11yAuditBot/1.0 (+accessibility audit crawler; respects robots.txt)"


@dataclass
class PageResult:
    url: str
    title: str | None
    status_code: int | None


class RobotsChecker:
    """Fetches and caches robots.txt for a single host, best-effort."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, enabled: bool = True):
        self._client = client
        self._enabled = enabled
        self._parser: RobotFileParser | None = None
        parts = urlsplit(base_url)
        self._robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"

    async def load(self) -> None:
        if not self._enabled:
            return
        try:
            resp = await self._client.get(self._robots_url, timeout=settings.CRAWLER_REQUEST_TIMEOUT_SECONDS)
            if resp.status_code >= 400:
                self._parser = None
                return
            parser = RobotFileParser()
            parser.parse(resp.text.splitlines())
            self._parser = parser
        except (httpx.HTTPError, Exception):  # noqa: BLE001 - robots.txt is best-effort
            self._parser = None

    def can_fetch(self, url: str) -> bool:
        if not self._enabled or self._parser is None:
            return True
        try:
            return self._parser.can_fetch(USER_AGENT, url)
        except Exception:  # noqa: BLE001
            return True


def extract_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()[:512]
    return None


def extract_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [a.get("href") for a in soup.find_all("a", href=True) if a.get("href")]


MAX_SITEMAP_DOCUMENTS = 25


def _parse_sitemap_document(xml_text: str) -> tuple[list[str], list[str]]:
    """
    A sitemap document is either a <sitemapindex> (its <sitemap><loc> entries
    point to more sitemap documents, e.g. sitemap-stocks.xml) or a <urlset>
    (its <url><loc> entries are actual pages). Returns
    (child_sitemap_urls, page_urls) - only one list is populated for a
    well-formed document.
    """
    soup = BeautifulSoup(xml_text, "xml")

    child_sitemaps = [
        loc.text.strip()
        for tag in soup.find_all("sitemap")
        if (loc := tag.find("loc")) and loc.text.strip()
    ]
    page_urls = [
        loc.text.strip()
        for tag in soup.find_all("url")
        if (loc := tag.find("loc")) and loc.text.strip()
    ]
    return child_sitemaps, page_urls


async def fetch_sitemap_urls(client: httpx.AsyncClient, base_url: str, max_pages: int) -> list[str]:
    """
    Best-effort read of /sitemap.xml at the site root, following sitemap
    index files down to their real <urlset> page listings. Bounded by
    max_pages (page URLs collected) and MAX_SITEMAP_DOCUMENTS (sitemap
    files fetched) so a site with a huge sitemap tree doesn't stall the
    crawl - stops as soon as either limit is reached.
    """
    parts = urlsplit(base_url)
    root_sitemap_url = f"{parts.scheme}://{parts.netloc}/sitemap.xml"

    collected: list[str] = []
    visited_documents: set[str] = set()
    queue: list[str] = [root_sitemap_url]

    while queue and len(collected) < max_pages and len(visited_documents) < MAX_SITEMAP_DOCUMENTS:
        sitemap_url = queue.pop(0)
        if sitemap_url in visited_documents:
            continue
        visited_documents.add(sitemap_url)

        try:
            resp = await client.get(sitemap_url, timeout=settings.CRAWLER_REQUEST_TIMEOUT_SECONDS)
            if resp.status_code >= 400:
                continue
            child_sitemaps, page_urls = _parse_sitemap_document(resp.text)
        except (httpx.HTTPError, Exception):  # noqa: BLE001 - sitemap is optional
            continue

        collected.extend(page_urls)
        queue.extend(child_sitemaps)

    return collected[:max_pages]


async def crawl_site(
    base_url: str,
    max_depth: int = 3,
    max_pages: int = 200,
    respect_robots: bool = True,
    concurrency: int | None = None,
) -> list[PageResult]:
    """
    Breadth-first crawl of `base_url`, restricted to the same domain/subdomain,
    deduplicated by normalized path. Returns at most `max_pages` PageResult
    entries. Runs concurrently (bounded by `concurrency`) so large sites don't
    time out.
    """
    concurrency = concurrency or settings.CRAWLER_CONCURRENCY
    timeout = settings.CRAWLER_REQUEST_TIMEOUT_SECONDS

    base_normalized = normalize_url(base_url)
    if base_normalized is None:
        raise ValueError(f"base_url is not a valid http(s) URL: {base_url!r}")
    base_host = get_hostname(base_normalized)

    results: dict[str, PageResult] = {}
    visited: set[str] = set()
    queued: set[str] = {base_normalized}
    semaphore = asyncio.Semaphore(concurrency)

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout, headers=headers, limits=limits
    ) as client:
        robots = RobotsChecker(client, base_normalized, enabled=respect_robots)
        await robots.load()

        seed_urls = [base_normalized]
        sitemap_urls = await fetch_sitemap_urls(client, base_normalized, max_pages)
        for raw in sitemap_urls:
            normalized = normalize_url(raw, base_url=base_normalized)
            if normalized and normalized not in queued and is_same_site(get_hostname(normalized) or "", base_host):
                seed_urls.append(normalized)
                queued.add(normalized)
                if len(queued) >= max_pages:
                    break

        current_wave = seed_urls
        depth = 0

        while current_wave and depth <= max_depth and len(visited) < max_pages:
            room = max_pages - len(visited)
            batch = current_wave[:room]

            async def fetch_one(url: str) -> tuple[str, PageResult, list[str]]:
                async with semaphore:
                    return await _fetch_and_parse(client, url)

            fetch_tasks = [fetch_one(url) for url in batch if url not in visited and robots.can_fetch(url)]
            for url in batch:
                visited.add(url)

            next_wave_candidates: list[str] = []
            if fetch_tasks:
                fetched = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                for outcome in fetched:
                    if isinstance(outcome, Exception):
                        logger.warning("Crawl fetch failed: %s", outcome)
                        continue
                    final_url, page_result, links = outcome
                    results[final_url] = page_result

                    if depth >= max_depth:
                        continue
                    for href in links:
                        normalized = normalize_url(href, base_url=final_url)
                        if not normalized:
                            continue
                        host = get_hostname(normalized)
                        if not host or not is_same_site(host, base_host):
                            continue
                        if normalized in visited or normalized in queued:
                            continue
                        if len(queued) >= max_pages:
                            continue
                        queued.add(normalized)
                        next_wave_candidates.append(normalized)

            current_wave = next_wave_candidates
            depth += 1

    return list(results.values())


async def _fetch_and_parse(client: httpx.AsyncClient, url: str) -> tuple[str, PageResult, list[str]]:
    """
    Fetch `url`, following redirects. Returns the *normalized final*
    destination URL (post-redirect), a PageResult, and any links found on
    the page (empty if the response wasn't HTML or the request failed).
    """
    try:
        resp = await client.get(url)
    except httpx.HTTPError as exc:
        logger.info("Request failed for %s: %s", url, exc)
        return url, PageResult(url=url, title=None, status_code=None), []

    final_url = normalize_url(str(resp.url)) or url
    content_type = resp.headers.get("content-type", "")

    title = None
    links: list[str] = []
    if "text/html" in content_type:
        try:
            title = extract_title(resp.text)
            links = extract_links(resp.text)
        except Exception as exc:  # noqa: BLE001 - malformed HTML shouldn't kill the crawl
            logger.info("Failed to parse HTML for %s: %s", final_url, exc)

    return final_url, PageResult(url=final_url, title=title, status_code=resp.status_code), links
