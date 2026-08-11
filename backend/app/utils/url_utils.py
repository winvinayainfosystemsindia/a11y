"""
URL normalization and dedup helpers used by the crawler.

The crawler must treat these as the SAME page:
    https://Example.com/products?id=1
    https://example.com/products?id=2#reviews
    https://example.com/products/
    https://example.com/products
-> all normalize to: https://example.com/products
"""
from __future__ import annotations

from urllib.parse import urljoin, urlsplit, urlunsplit

# File extensions that are never "pages" for accessibility auditing purposes.
NON_PAGE_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".css", ".js", ".mjs",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".ogg",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".eot",
    ".xml", ".json",
}

NON_PAGE_SCHEMES = {"mailto", "tel", "javascript", "data", "ftp", "sms", "whatsapp"}


def normalize_url(url: str, base_url: str | None = None) -> str | None:
    """
    Resolve `url` against `base_url` (if relative) and normalize it into a
    canonical page identifier:
      - strip query string and fragment
      - lowercase the scheme + hostname (path casing is preserved)
      - drop default ports (80 for http, 443 for https)
      - collapse trailing slash (except for the root path "/")

    Returns None if the URL cannot be treated as a normal http(s) page
    (e.g. mailto:, javascript:, anchor-only links, or non-page file types).
    """
    if url is None:
        return None

    raw = url.strip()
    if not raw or raw.startswith("#"):
        return None

    resolved = urljoin(base_url, raw) if base_url else raw

    try:
        parts = urlsplit(resolved)
    except ValueError:
        return None

    scheme = (parts.scheme or "").lower()
    if scheme in NON_PAGE_SCHEMES:
        return None
    if scheme not in ("http", "https"):
        return None

    if not parts.hostname:
        return None

    host = parts.hostname.lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parts.path or "/"
    if _has_non_page_extension(path):
        return None

    # Collapse repeated slashes and normalize trailing slash (root "/" stays as-is).
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    if not path:
        path = "/"

    # Drop query string and fragment entirely - they are not part of page identity.
    normalized = urlunsplit((scheme, netloc, path, "", ""))
    return normalized


def _has_non_page_extension(path: str) -> bool:
    lowered = path.lower()
    for ext in NON_PAGE_EXTENSIONS:
        if lowered.endswith(ext):
            return True
    return False


def get_hostname(url: str) -> str | None:
    try:
        hostname = urlsplit(url).hostname
    except ValueError:
        return None
    return hostname.lower() if hostname else None


def is_same_site(candidate_host: str, base_host: str) -> bool:
    """
    True if `candidate_host` is the same host as `base_host`, or a subdomain
    of it (or vice versa), so the crawler stays within the same site instead
    of following links to unrelated external domains.
    """
    if not candidate_host or not base_host:
        return False
    candidate_host = candidate_host.lower()
    base_host = base_host.lower()
    if candidate_host == base_host:
        return True
    return candidate_host.endswith("." + base_host) or base_host.endswith("." + candidate_host)


def is_crawlable_page(url: str, base_host: str) -> bool:
    """Convenience check combining hostname + non-page-extension filtering."""
    host = get_hostname(url)
    if not host:
        return False
    return is_same_site(host, base_host)
