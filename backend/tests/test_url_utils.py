"""Unit tests for URL normalization and dedup logic - the heart of the crawler."""
from app.utils.url_utils import is_same_site, normalize_url


def test_strips_query_string():
    assert normalize_url("https://example.com/products?id=1") == "https://example.com/products"


def test_strips_fragment():
    assert normalize_url("https://example.com/about#team") == "https://example.com/about"


def test_dedup_query_variants_collapse_to_same_path():
    a = normalize_url("https://example.com/products?id=1")
    b = normalize_url("https://example.com/products?id=2")
    c = normalize_url("https://example.com/products")
    assert a == b == c == "https://example.com/products"


def test_trailing_slash_normalized():
    assert normalize_url("https://example.com/about/") == normalize_url("https://example.com/about")


def test_root_path_trailing_slash_preserved_as_root():
    assert normalize_url("https://example.com/") == "https://example.com/"
    assert normalize_url("https://example.com") == "https://example.com/"


def test_hostname_lowercased_path_preserved():
    assert normalize_url("https://EXAMPLE.com/AboutUs") == "https://example.com/AboutUs"


def test_resolves_relative_url_against_base():
    assert normalize_url("/contact", base_url="https://example.com/somewhere") == "https://example.com/contact"


def test_default_ports_stripped():
    assert normalize_url("https://example.com:443/about") == "https://example.com/about"
    assert normalize_url("http://example.com:80/about") == "http://example.com/about"


def test_non_default_port_preserved():
    assert normalize_url("https://example.com:8443/about") == "https://example.com:8443/about"


def test_mailto_and_tel_rejected():
    assert normalize_url("mailto:someone@example.com") is None
    assert normalize_url("tel:+15551234567") is None


def test_javascript_and_anchor_only_rejected():
    assert normalize_url("javascript:void(0)") is None
    assert normalize_url("#section-2") is None


def test_non_page_file_extensions_rejected():
    assert normalize_url("https://example.com/brochure.pdf") is None
    assert normalize_url("https://example.com/logo.PNG") is None
    assert normalize_url("https://example.com/app.js") is None
    assert normalize_url("https://example.com/styles.css") is None


def test_non_http_scheme_rejected():
    assert normalize_url("ftp://example.com/file") is None


def test_is_same_site_matches_exact_and_subdomains():
    assert is_same_site("example.com", "example.com")
    assert is_same_site("www.example.com", "example.com")
    assert is_same_site("example.com", "www.example.com")
    assert not is_same_site("evil.com", "example.com")
    assert not is_same_site("notexample.com", "example.com")
