"""
End-to-end test of the crawler against a mocked site (via respx, no real
network calls) - verifies query-string dedup, same-domain restriction, and
non-page-link skipping all work together.
"""
import httpx
import pytest
import respx

from app.services.crawler_service import crawl_site, fetch_sitemap_urls

HOME_HTML = """
<html><head><title>Home</title></head>
<body>
  <a href="/products?id=1">Product 1</a>
  <a href="/products?id=2">Product 2</a>
  <a href="/about/">About</a>
  <a href="https://external.com/page">External</a>
  <a href="mailto:hello@example.com">Email us</a>
  <a href="/brochure.pdf">Brochure</a>
</body></html>
"""

ABOUT_HTML = """
<html><head><title>About Us</title></head>
<body><a href="/">Home</a></body></html>
"""

PRODUCTS_HTML = """
<html><head><title>Products</title></head>
<body></body></html>
"""


@pytest.mark.asyncio
@respx.mock
async def test_crawl_dedups_query_string_variants_and_skips_external_links():
    html_headers = {"content-type": "text/html; charset=utf-8"}
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text=HOME_HTML, headers=html_headers))
    respx.get("https://example.com/products").mock(
        return_value=httpx.Response(200, text=PRODUCTS_HTML, headers=html_headers)
    )
    respx.get("https://example.com/about").mock(
        return_value=httpx.Response(200, text=ABOUT_HTML, headers=html_headers)
    )

    pages = await crawl_site("https://example.com", max_depth=2, max_pages=50, respect_robots=True)
    urls = {p.url for p in pages}

    assert urls == {
        "https://example.com/",
        "https://example.com/products",
        "https://example.com/about",
    }
    assert "https://external.com/page" not in urls

    products_page = next(p for p in pages if p.url == "https://example.com/products")
    assert products_page.title == "Products"
    assert products_page.status_code == 200


SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://example.com/sitemap-a.xml</loc></sitemap>
<sitemap><loc>https://example.com/sitemap-b.xml</loc></sitemap>
</sitemapindex>
"""

SITEMAP_A_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://example.com/stocks/aaa</loc></url>
<url><loc>https://example.com/stocks/bbb</loc></url>
</urlset>
"""

SITEMAP_B_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://example.com/stocks/ccc?ref=sitemap</loc></url>
</urlset>
"""


@pytest.mark.asyncio
@respx.mock
async def test_fetch_sitemap_urls_recurses_into_sitemap_index():
    respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, text=SITEMAP_INDEX_XML, headers={"content-type": "application/xml"})
    )
    respx.get("https://example.com/sitemap-a.xml").mock(
        return_value=httpx.Response(200, text=SITEMAP_A_XML, headers={"content-type": "application/xml"})
    )
    respx.get("https://example.com/sitemap-b.xml").mock(
        return_value=httpx.Response(200, text=SITEMAP_B_XML, headers={"content-type": "application/xml"})
    )

    async with httpx.AsyncClient() as client:
        urls = await fetch_sitemap_urls(client, "https://example.com", max_pages=50)

    assert set(urls) == {
        "https://example.com/stocks/aaa",
        "https://example.com/stocks/bbb",
        "https://example.com/stocks/ccc?ref=sitemap",
    }


@pytest.mark.asyncio
@respx.mock
async def test_crawl_seeds_pages_from_sitemap_index_for_spa_sites():
    """
    Mirrors a client-rendered SPA whose homepage HTML has no real <a href>
    links (nav is injected by JS) but whose sitemap index -> child sitemaps
    list real pages - the crawler must still discover those pages.
    """
    html_headers = {"content-type": "text/html; charset=utf-8"}
    xml_headers = {"content-type": "application/xml"}

    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, text=SITEMAP_INDEX_XML, headers=xml_headers)
    )
    respx.get("https://example.com/sitemap-a.xml").mock(
        return_value=httpx.Response(200, text=SITEMAP_A_XML, headers=xml_headers)
    )
    respx.get("https://example.com/sitemap-b.xml").mock(
        return_value=httpx.Response(200, text=SITEMAP_B_XML, headers=xml_headers)
    )
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html><head><title>Home</title></head><body></body></html>", headers=html_headers)
    )
    respx.get("https://example.com/stocks/aaa").mock(
        return_value=httpx.Response(200, text="<html><head><title>AAA</title></head><body></body></html>", headers=html_headers)
    )
    respx.get("https://example.com/stocks/bbb").mock(
        return_value=httpx.Response(200, text="<html><head><title>BBB</title></head><body></body></html>", headers=html_headers)
    )
    respx.get("https://example.com/stocks/ccc").mock(
        return_value=httpx.Response(200, text="<html><head><title>CCC</title></head><body></body></html>", headers=html_headers)
    )

    pages = await crawl_site("https://example.com", max_depth=2, max_pages=50, respect_robots=True)
    urls = {p.url for p in pages}

    assert urls == {
        "https://example.com/",
        "https://example.com/stocks/aaa",
        "https://example.com/stocks/bbb",
        "https://example.com/stocks/ccc",
    }
