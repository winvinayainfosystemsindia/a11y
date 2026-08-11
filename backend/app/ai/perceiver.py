"""
PERCEIVE stage: fetch the selected page's live HTML, computed structure
(landmarks, headings, images, forms, contrast samples) via Playwright, take
a full-page screenshot, and pull relevant memory (retriever.py) before
planning starts. Read-only against the live page - no DB writes happen
here; agent.py persists the resulting PageSnapshot.
"""
from __future__ import annotations

import logging

from playwright.async_api import Page
from sqlalchemy.orm import Session

from app.ai.memory import retriever
from app.ai.schemas import ContrastSample, FormFieldInfo, HeadingInfo, ImageInfo, PageSnapshot
from app.ai.tools import screenshot_tool

logger = logging.getLogger(__name__)

_SNAPSHOT_JS = """() => {
    const landmarks = Array.from(document.querySelectorAll(
        'header, nav, main, footer, aside, [role="banner"], [role="navigation"], [role="main"], ' +
        '[role="contentinfo"], [role="complementary"], [role="search"], [role="form"]'
    )).map(el => (el.getAttribute('role') || el.tagName.toLowerCase()));

    const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6')).slice(0, 60).map(el => ({
        level: parseInt(el.tagName.substring(1), 10),
        text: (el.innerText || '').trim().slice(0, 120),
    }));

    const images = Array.from(document.querySelectorAll('img')).slice(0, 100).map(el => ({
        src: el.getAttribute('src') || '',
        alt: el.hasAttribute('alt') ? el.getAttribute('alt') : null,
        has_alt_attribute: el.hasAttribute('alt'),
    }));

    const forms = Array.from(document.querySelectorAll('form')).slice(0, 10).map(form =>
        Array.from(form.querySelectorAll('input, select, textarea')).map(field => {
            const id = field.getAttribute('id');
            const label = id ? document.querySelector('label[for="' + id + '"]') : field.closest('label');
            return {
                tag: field.tagName.toLowerCase(),
                input_type: field.getAttribute('type'),
                has_label: !!label || field.hasAttribute('aria-label') || field.hasAttribute('aria-labelledby'),
                label_text: label ? (label.innerText || '').trim().slice(0, 120) : (field.getAttribute('aria-label') || null),
                placeholder: field.getAttribute('placeholder'),
            };
        })
    );

    const interactiveSelector = 'a[href], button, input, select, textarea, [tabindex], [role="button"], [role="link"]';

    return {
        landmarks,
        headings,
        images,
        forms,
        links_count: document.querySelectorAll('a[href]').length,
        interactive_elements_count: document.querySelectorAll(interactiveSelector).length,
        has_skip_link: Array.from(document.querySelectorAll('a[href^="#"]')).some(a => /skip/i.test(a.innerText || '')),
        lang_attribute: document.documentElement.getAttribute('lang'),
        title: document.title,
    };
}"""

_CONTRAST_SAMPLE_JS = """() => {
        function getEffectiveBackgroundColor(el) {
            function parseRGBA(str) {
                const m = /rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/.exec(str || '');
                if (!m) return null;
                return { r: parseFloat(m[1]), g: parseFloat(m[2]), b: parseFloat(m[3]), a: m[4] === undefined ? 1 : parseFloat(m[4]) };
            }
            let acc = { r: 0, g: 0, b: 0, a: 0 };
            let node = el;
            while (node && acc.a < 1) {
                const bg = parseRGBA(getComputedStyle(node).backgroundColor);
                if (bg && bg.a > 0) {
                    const outA = acc.a + bg.a * (1 - acc.a);
                    if (outA > 0) {
                        acc = {
                            r: (acc.r * acc.a + bg.r * bg.a * (1 - acc.a)) / outA,
                            g: (acc.g * acc.a + bg.g * bg.a * (1 - acc.a)) / outA,
                            b: (acc.b * acc.a + bg.b * bg.a * (1 - acc.a)) / outA,
                            a: outA,
                        };
                    }
                }
                node = node.parentElement;
            }
            const r = Math.round(acc.r * acc.a + 255 * (1 - acc.a));
            const g = Math.round(acc.g * acc.a + 255 * (1 - acc.a));
            const b = Math.round(acc.b * acc.a + 255 * (1 - acc.a));
            return 'rgb(' + r + ', ' + g + ', ' + b + ')';
        }
        function cssPath(el) {
            // A short, usable (if not perfectly unique) locator: id if
            // present, else a tag+nth-of-type chain up to 3 levels - far
            // more useful to a developer than a bare tag name like "span".
            if (el.id) return '#' + el.id;
            const parts = [];
            let node = el;
            for (let depth = 0; node && node.nodeType === 1 && depth < 3; depth++) {
                let part = node.tagName.toLowerCase();
                if (node.parentElement) {
                    const siblings = Array.from(node.parentElement.children).filter(c => c.tagName === node.tagName);
                    if (siblings.length > 1) {
                        part += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
                    }
                }
                parts.unshift(part);
                if (node.id) { parts[0] = '#' + node.id; break; }
                node = node.parentElement;
            }
            return parts.join(' > ');
        }
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, null);
    const samples = [];
    const seen = new Set();
    let node = walker.currentNode;
    while (node && samples.length < 40) {
        const text = (node.innerText || '').trim();
        if (text && node.children.length === 0) {
            const style = getComputedStyle(node);
            const effectiveBg = getEffectiveBackgroundColor(node);
            const key = style.color + '|' + effectiveBg;
            if (!seen.has(key)) {
                seen.add(key);
                samples.push({
                    selector: cssPath(node),
                    text_preview: text.slice(0, 60),
                    foreground: style.color,
                    background: effectiveBg,
                    font_size_px: parseFloat(style.fontSize) || 16,
                    font_weight: parseInt(style.fontWeight, 10) || 400,
                    html: (node.outerHTML || '').slice(0, 200),
                });
            }
        }
        node = walker.nextNode();
    }
    return samples;
}"""


def _page_type_signature(structure: dict) -> str:
    """A short, stable descriptor of this page's structural "type" - the key
    ai_memory is keyed by. Based on structure, not the URL, so similar pages
    across a site (and across sites) share learned patterns."""
    features: list[str] = []
    if structure["forms"]:
        has_password = any(
            field.get("input_type") == "password" for form in structure["forms"] for field in form
        )
        features.append("login_form" if has_password else "form")
    if any("nav" in landmark for landmark in structure["landmarks"]):
        features.append("nav")
    if len(structure["images"]) >= 6:
        features.append("media_heavy")
    if structure["interactive_elements_count"] >= 25:
        features.append("interactive_heavy")
    if not features:
        features.append("generic")
    return "|".join(sorted(set(features)))


def _describe_page_type(structure: dict, signature: str) -> str:
    return (
        f"page type {signature}: {len(structure['forms'])} form(s), {len(structure['images'])} image(s), "
        f"{structure['interactive_elements_count']} interactive element(s), "
        f"landmarks: {', '.join(structure['landmarks']) or 'none'}"
    )


async def perceive(
    db: Session,
    page: Page,
    *,
    url: str,
    final_url: str,
    status_code: int | None,
    page_id: int,
    run_id: int,
) -> PageSnapshot:
    structure = await page.evaluate(_SNAPSHOT_JS)
    try:
        contrast_raw = await page.evaluate(_CONTRAST_SAMPLE_JS)
    except Exception:
        logger.warning("Contrast sampling failed for %s", url, exc_info=True)
        contrast_raw = []

    html = await page.content()
    signature = _page_type_signature(structure)
    screenshot_path = await screenshot_tool.capture_full_page(page, run_id)

    memory = retriever.build_memory_context(
        db,
        page_id=page_id,
        page_type_signature=signature,
        page_type_description=_describe_page_type(structure, signature),
        current_run_id=run_id,
    )

    return PageSnapshot(
        url=url,
        final_url=final_url,
        title=structure.get("title"),
        page_type_signature=signature,
        status_code=status_code,
        landmarks=structure.get("landmarks", []),
        headings=[HeadingInfo(**h) for h in structure.get("headings", [])],
        images=[ImageInfo(**i) for i in structure.get("images", [])],
        forms=[[FormFieldInfo(**f) for f in form] for form in structure.get("forms", [])],
        links_count=structure.get("links_count", 0),
        interactive_elements_count=structure.get("interactive_elements_count", 0),
        has_skip_link=structure.get("has_skip_link", False),
        lang_attribute=structure.get("lang_attribute"),
        contrast_samples=[ContrastSample(**c) for c in contrast_raw],
        html_excerpt=html[:20000],
        screenshot_path=screenshot_path,
        memory_context=memory,
    )
