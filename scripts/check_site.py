#!/usr/bin/env python3
"""Post-render step: check the rendered site in _site/.

Fails (non-zero exit, which fails `quarto render`) on:
  * internal links or fragments that do not resolve,
  * images without an alt attribute, or local images that do not exist,
  * listings whose rendered item count differs from the data that should feed them
    (asserts the realised pages, not the template's intent).
External links are not checked here; see .github/workflows/external-links.yml (warning only).
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "_site"
SITE_URL = "https://alruizzo.github.io"
BASE_PATH = urlsplit(SITE_URL).path.rstrip("/") + "/"  # "/" for a site served from the root
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.canonical: list[str] = []
        self.ids: set[str] = set()
        self.links: list[tuple[str, str]] = []  # (attr, value)
        self.imgs: list[dict] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (a.get("property") or a.get("name")):
            self.meta.setdefault(a.get("property") or a.get("name"), []).append(a.get("content") or "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical.append(a.get("href") or "")
        if a.get("id"):
            self.ids.add(a["id"])
        if "name" in a and tag == "a":
            self.ids.add(a["name"])
        for attr in ("href", "src"):
            if a.get(attr) and tag in {"a", "link", "script", "img", "source", "iframe"}:
                self.links.append((attr, a[attr]))
        if tag == "img":
            self.imgs.append(a)


def count_in_listing(html: str, listing: str, cls: str) -> int:
    """Count elements carrying class `cls` inside the listing container `listing`.

    The window runs from the container's id to the next listing container or the end of <main>;
    listings are siblings in these pages, never nested.
    """
    start = html.find(f'id="{listing}"')
    if start < 0:
        return -1
    ends = [i for i in (html.find('id="listing-', start + 1), html.find("</main>", start)) if i > 0]
    window = html[start:min(ends) if ends else len(html)]
    return sum(cls in c.split() for c in re.findall(r'class="([^"]*)"', window))


def check_share_meta(page: "Page", expected_url: str, noindex: bool) -> list[str]:
    """Link-preview tags a page needs so messengers, social platforms and mail clients show a
    correct card: one value each, consistent between Open Graph and Twitter/X, absolute URLs."""
    errs = []
    one = lambda k: page.meta.get(k, [None])[0] if len(page.meta.get(k, [])) == 1 else None
    for key in ("og:title", "og:description", "og:image", "og:image:alt", "og:image:type", "og:type",
                "og:site_name", "og:locale", "twitter:card", "twitter:title", "twitter:description",
                "twitter:image", "twitter:image:alt", "description"):
        n = len(page.meta.get(key, []))
        if n != 1 or not (page.meta[key][0] or "").strip():
            errs.append(f"{key}: expected exactly one non-empty value, found {n}")
    if one("og:image:width") != "1200" or one("og:image:height") != "630":
        errs.append("og:image dimensions must be declared as 1200x630")
    if one("twitter:card") != "summary_large_image":
        errs.append("twitter:card must be summary_large_image")
    for a, b in (("og:title", "twitter:title"), ("og:description", "twitter:description"),
                 ("og:image", "twitter:image"), ("og:description", "description")):
        if one(a) and one(b) and one(a) != one(b):
            errs.append(f"{a} and {b} differ")
    img = one("og:image") or ""
    if not img.startswith(SITE_URL + "/"):
        errs.append(f"og:image must be an absolute URL on the site, got {img!r}")
    elif not (SITE / unquote(img[len(SITE_URL) + 1:])).is_file():
        errs.append(f"og:image {img} does not exist in _site")
    if noindex:
        if page.meta.get("robots") != ["noindex"]:
            errs.append("noindex page needs <meta name=robots content=noindex>")
        if page.canonical or "og:url" in page.meta:
            errs.append("noindex page must not declare a canonical URL")
    else:
        if page.meta.get("og:url") != [expected_url]:
            errs.append(f"og:url should be {expected_url}, found {page.meta.get('og:url')}")
        if page.canonical != [expected_url]:
            errs.append(f"canonical link should be {expected_url}, found {page.canonical}")
    return errs


def parse(path: Path) -> Page:
    p = Page()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    return p


def main() -> int:
    if not SITE.is_dir():
        print("check_site: _site/ not found; run quarto render first.", file=sys.stderr)
        return 1
    pages = {p: parse(p) for p in SITE.rglob("*.html")}
    errors: list[str] = []

    for path, page in pages.items():
        rel = path.relative_to(SITE)
        for attr, raw in page.links:
            if raw.startswith(SKIP_SCHEMES):
                continue
            if raw.startswith(SITE_URL):
                raw = raw[len(SITE_URL):] or "/"
            parts = urlsplit(raw)
            if parts.scheme or parts.netloc:
                continue  # external
            if parts.path.startswith("/"):
                # Root-relative links (Quarto uses them on 404.html) resolve against the site's base path.
                local = parts.path[len(BASE_PATH):] if parts.path.startswith(BASE_PATH) else parts.path
                target = (SITE / unquote(local.lstrip("/"))).resolve()
            elif parts.path:
                target = (path.parent / unquote(parts.path)).resolve()
            else:
                target = path
            if (parts.path or "").endswith("/") or (target.exists() and target.is_dir()):
                target = target / "index.html"
            if not target.exists():
                errors.append(f"{rel}: broken internal {attr} -> {raw}")
                continue
            frag = unquote(parts.fragment)
            # Listing filter hashes (#category=...) are state, not anchors.
            if frag and "=" not in frag and target.suffix == ".html":
                tpage = pages.get(target) or parse(target)
                if frag not in tpage.ids:
                    errors.append(f"{rel}: missing anchor #{frag} in {target.relative_to(SITE)}")
        # The privacy statement promises no third-party requests: fail on any external resource load.
        for attr, raw in page.links:
            if attr == "src" or raw.endswith((".css", ".js")):
                host = urlsplit(raw).netloc
                if host and not raw.startswith(SITE_URL):
                    errors.append(f"{rel}: loads a third-party resource {raw}")
        for img in page.imgs:
            if "alt" not in img:
                errors.append(f"{rel}: <img src={img.get('src')!r}> has no alt attribute")

    # Link-preview metadata of every page.
    for path, page in pages.items():
        rel = path.relative_to(SITE).as_posix()
        if path.parent != SITE:
            continue
        expected = SITE_URL + "/" + ("" if rel == "index.html" else rel)
        for e in check_share_meta(page, expected, noindex=(rel == "404.html")):
            errors.append(f"{rel}: share metadata: {e}")
    print(f"  share metadata: checked {sum(1 for p in pages if p.parent == SITE)} pages")

    # Realised listing counts versus the data that feeds them.
    pubs = yaml.safe_load((ROOT / "data" / "publications.yml").read_text(encoding="utf-8")) or []
    outputs = yaml.safe_load((ROOT / "data" / "outputs.yml").read_text(encoding="utf-8")) or []
    recognition = yaml.safe_load((ROOT / "data" / "recognition.yml").read_text(encoding="utf-8")) or []
    coauthors = yaml.safe_load((ROOT / "data" / "generated" / "coauthors.yml").read_text(encoding="utf-8")) or []
    profiles = yaml.safe_load((ROOT / "data" / "profiles.yml").read_text(encoding="utf-8")) or []
    news = yaml.safe_load((ROOT / "data" / "news.yml").read_text(encoding="utf-8")) or []
    talks = yaml.safe_load((ROOT / "data" / "talks.yml").read_text(encoding="utf-8")) or []
    home_news = re.search(r"id: news\n(?:\s{4}.*\n)*?\s{4}max-items: (\d+)", (ROOT / "index.qmd").read_text(encoding="utf-8"))
    if not home_news:
        errors.append("index.qmd: the news listing must set max-items")

    # Every page's footer carries one icon link per profile, in data order, each with its visible name.
    want = [(p["url"], p["name"], p["icon"]) for p in profiles]
    for path in pages:
        html = path.read_text(encoding="utf-8")
        nav = re.search(r'<nav class="rr-social".*?</nav>', html, re.S)
        got = re.findall(r'<a class="rr-social-link" href="([^"]+)"><span class="rr-icon rr-icon-([a-z]+)" '
                         r'aria-hidden="true"></span><span class="rr-social-name">([^<]+)</span></a>', nav.group(0)) if nav else []
        if [(unquote(u).replace("&amp;", "&"), n, i) for u, i, n in got] != want:
            errors.append(f"{path.relative_to(SITE)}: footer icon row does not match data/profiles.yml")
    expected = {
        ("publications.html", "listing-articles", "rr-pub"): sum(p["type"] in {"article", "chapter", "preprint"} for p in pubs),
        ("publications.html", "listing-abstracts", "rr-pub"): sum(p["type"] == "abstract" for p in pubs),
        ("publications.html", "listing-theses", "rr-pub"): sum(p["type"] == "thesis" for p in pubs),
        ("publications.html", "listing-scicomm", "rr-pub"): sum(p["type"] == "scicomm" for p in pubs),
        ("index.html", "listing-featured", "rr-feature"): sum(bool(p.get("featured")) for p in pubs),
        ("expertise.html", "listing-outputs", "rr-card"): len(outputs),
        ("index.html", "listing-fellowships", "rr-fellowship"): sum(bool(r.get("fellowship")) for r in recognition),
        ("contact.html", "listing-coauthors-current", "rr-coauthor"): sum(c["status"] == "current" for c in coauthors),
        ("contact.html", "listing-profiles", "rr-icon"): len(profiles),
        ("index.html", "listing-hero-profiles", "rr-pill-link"): sum(bool(p.get("hero")) for p in profiles),
        ("contact.html", "listing-coauthors-previous", "rr-coauthor"): sum(c["status"] == "previous" for c in coauthors),
        ("index.html", "listing-news", "rr-news-item"): min(len(news), int(home_news.group(1)) if home_news else 0),
        ("news.html", "listing-news-all", "rr-news-item"): len(news),
        ("about.html", "listing-talks", "rr-timeline-item"): len(talks),
    }
    for (fname, listing, cls), n in expected.items():
        path = SITE / fname
        if not path.exists():
            errors.append(f"{fname}: page missing")
            continue
        got = count_in_listing(path.read_text(encoding="utf-8"), listing, cls)
        if got != n:
            errors.append(f"{fname}#{listing}: rendered {got} .{cls} items, data has {n}")
        else:
            print(f"  {fname}#{listing}: {got} items (matches data)")

    # The inline theme filter must offer exactly the themes defined for the data.
    import base64
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prerender import THEMES
    pub_html = (SITE / "publications.html").read_text(encoding="utf-8")
    offered = {unquote(base64.b64decode(v).decode()) for v in re.findall(r'class="category rr-filter-btn[^"]*" data-category="([^"]*)"', pub_html)}
    if offered != set(THEMES.values()) | {""}:
        errors.append(f"publications.html: theme filter offers {sorted(offered)}, data themes are {sorted(THEMES.values())}")

    # The published CV is the owner's PDF byte for byte (pinned by cv.sha256 in _variables.yml).
    import hashlib
    cv = (yaml.safe_load((ROOT / "_variables.yml").read_text(encoding="utf-8")) or {}).get("cv") or {}
    built = SITE / str(cv.get("file", ""))
    if not built.is_file():
        errors.append(f"{cv.get('file')}: CV missing from _site")
    elif hashlib.sha256(built.read_bytes()).hexdigest() != cv.get("sha256"):
        errors.append(f"{cv.get('file')}: CV in _site differs from the pinned CV (sha256)")
    else:
        print(f"  {cv['file']}: matches the pinned CV (sha256 {cv['sha256'][:12]}...)")

    if errors:
        for e in errors:
            print("  ERROR:", e, file=sys.stderr)
        print(f"check_site: {len(errors)} problem(s).", file=sys.stderr)
        return 1
    print(f"check_site: {len(pages)} pages, internal links, anchors and alt text OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
