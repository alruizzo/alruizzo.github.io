#!/usr/bin/env python3
"""Generate the link-preview image (Open Graph / Twitter card) for every page.

Run after changing a page's title or description:  python3 scripts/make_social_cards.py
Requires Pillow (requirements-dev.txt) and the macOS system fonts named below; the build itself
does not need either. Output: assets/social/<page>.png (1200 x 630 PNG, the size Open Graph and
Twitter/X large cards expect) and assets/social/cards.json, a manifest of the text each card was
drawn from. scripts/prerender.py compares that manifest with the pages and fails the build when a
card is stale, so previews always match the current page content.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "social"
W, H = 1200, 630
MARGIN_X, MARGIN_Y = 80, 72          # keeps text inside the 2:1 crop some apps apply

# Colors: hero ground and text tones of the site (styles/light.scss).
HERO, WHITE, TEXT2, TEXT3 = "#16132B", "#FFFFFF", "#DDDDDD", "#B2B2B2"
ACCENT = "#F29D6D"                    # batlow[192], the hero accent
NODES = ["#C09036", "#F29D6D", "#FDB4B6", "#FCC0D8"]   # batlow[160..240]

SERIF = "/System/Library/Fonts/Supplemental/Iowan Old Style.ttc"   # index 0 Roman, 1 Bold
SANS = "/System/Library/Fonts/SFNS.ttf"

# Pages that get a card. The eyebrow above the title is her name, except on the homepage, whose
# title already is her name. The card title is the page title (or `share-card-title` in the page's
# front matter); the tagline is `share-card-tagline` or else the page description.
NAME = "Dr. Adriana L. Ruiz-Rizzo"
PAGES = {
    "index": "Cognitive and clinical neuroscience",
    "research": NAME, "publications": NAME, "expertise": NAME, "about": NAME,
    "contact": NAME, "news": NAME, "legal": NAME, "privacy": NAME, "404": NAME,
}
PORTRAIT_PAGES = {"index", "about"}
SITE_LABEL = "alruizzo.github.io"


def page_file(page: str, lang: str = "en") -> Path:
    """The page source in `lang`: <page>.<lang>.qmd, or <page>.qmd for English. Inside a language
    build (scripts/build_site.py) the translation has already been renamed to <page>.qmd."""
    translated = ROOT / f"{page}.{lang}.qmd"
    return translated if lang != "en" and translated.is_file() else ROOT / f"{page}.qmd"


def front_matter(page: str, lang: str = "en") -> dict:
    text = page_file(page, lang).read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def eyebrow(page: str, lang: str) -> str:
    if lang == "en":
        return PAGES[page]
    import i18n
    cards = i18n.load(lang)["cards"]
    return cards["name"] if PAGES[page] == NAME else cards["index_eyebrow"]


def card_text(page: str, lang: str = "en") -> dict:
    """The text a card is drawn from; also what prerender.py checks for staleness."""
    fm = front_matter(page, lang)
    title = fm.get("share-card-title") or fm.get("title") or fm.get("pagetitle")
    return {"eyebrow": eyebrow(page, lang), "title": str(title),
            "tagline": str(fm.get("share-card-tagline") or fm.get("description", ""))}


def font(path: str, size: int, index: int = 0, variation: bytes | None = None):
    from PIL import ImageFont
    f = ImageFont.truetype(path, size, index=index)
    if variation:
        f.set_variation_by_name(variation)
    return f


def wrap(draw, text, f, width, max_lines):
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if draw.textlength(trial, font=f) <= width:
            line = trial
        else:
            lines.append(line)
            line = w
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while draw.textlength(lines[-1] + "…", font=f) > width:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] = lines[-1].rstrip(",;:") + "…"
    return lines


def motif(draw, x0, x1, seed):
    """Decorative network, the same visual language as the hero (does not depict data)."""
    rnd = random.Random(seed)
    pts = [(rnd.uniform(x0, x1), rnd.uniform(16, H - 16)) for _ in range(34)]
    for a in pts:
        for j in sorted(range(len(pts)), key=lambda k: math.dist(a, pts[k]))[1:3]:
            draw.line([a, pts[j]], fill=(255, 255, 255, 30), width=1)
    for k, (x, y) in enumerate(pts):
        r = 5 if k % 7 == 0 else 2.5
        col = NODES[k % len(NODES)] if k % 3 == 0 else TEXT2
        rgba = tuple(int(col[i:i + 2], 16) for i in (1, 3, 5)) + ((210,) if k % 3 == 0 else (120,))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=rgba)


def draw_card(page: str, text: dict, portrait):
    from PIL import Image, ImageDraw, ImageOps
    img = Image.new("RGB", (W, H), HERO)
    d = ImageDraw.Draw(img, "RGBA")
    with_portrait = page in PORTRAIT_PAGES
    # The motif stays clear of the text column.
    motif(d, 640 if with_portrait else 960, W - 10, seed=sum(map(ord, page)))
    text_w = (820 if with_portrait else 900) - MARGIN_X

    eyebrow = font(SANS, 22, variation=b"Semibold")
    d.text((MARGIN_X, MARGIN_Y), text["eyebrow"].upper(), font=eyebrow, fill=ACCENT)

    # Title: largest size (76 to 52 px) that fits in two lines.
    for size in range(76, 50, -4):
        tf = font(SERIF, size, index=1)
        lines = wrap(d, text["title"], tf, text_w - (220 if with_portrait else 0), 3)
        if len(lines) <= 2 and not lines[-1].endswith("…"):
            break
    y = MARGIN_Y + 58
    line_h = int(size * 1.12)
    d.rectangle([MARGIN_X - 26, y + 10, MARGIN_X - 21, y + line_h * len(lines) - 6], fill=ACCENT)   # accent rule
    for ln in lines:
        d.text((MARGIN_X, y), ln, font=tf, fill=WHITE)
        y += line_h

    body = font(SANS, 29, variation=b"Regular")
    y += 22
    for ln in wrap(d, text["tagline"], body, text_w - (220 if with_portrait else 0), 3):
        d.text((MARGIN_X, y), ln, font=body, fill=TEXT2)
        y += 41

    # Footer: monogram square and address.
    fy = H - MARGIN_Y - 30
    d.rounded_rectangle([MARGIN_X, fy, MARGIN_X + 40, fy + 40], radius=9, fill="#6D5480")
    d.text((MARGIN_X + 20, fy + 21), "AR", font=font(SERIF, 19, index=1), fill=WHITE, anchor="mm")
    small = font(SANS, 22, variation=b"Regular")
    d.text((MARGIN_X + 56, fy + 20), SITE_LABEL, font=small, fill=TEXT3, anchor="lm")

    if with_portrait:
        # Square crop, never a stretch: the portrait is a 3:2 landscape photograph. The horizontal
        # centering matches the site's object-position (43%), which keeps her face centered.
        p = ImageOps.fit(portrait, (256, 256), Image.LANCZOS, centering=(0.43, 0.5))
        mask = Image.new("L", p.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, 255, 255], radius=26, fill=255)
        img.paste(p, (W - MARGIN_X - 256, (H - 256) // 2 - 10), mask)
    return img


def main() -> int:
    """Usage: make_social_cards.py [--lang en|es|de|all]  (default: en)."""
    from PIL import Image
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import i18n
    arg = sys.argv[sys.argv.index("--lang") + 1] if "--lang" in sys.argv else "en"
    langs = list(i18n.LANGS) if arg == "all" else [arg]
    if any(lang not in i18n.LANGS for lang in langs):
        raise SystemExit(f"--lang must be one of {i18n.LANGS} or all")
    portrait = Image.open(ROOT / "assets" / "img" / "portrait.jpg").convert("RGB")
    for lang in langs:
        out = OUT if lang == "en" else OUT / lang
        out.mkdir(parents=True, exist_ok=True)
        manifest = {}
        for page in PAGES:
            text = card_text(page, lang)
            path = out / f"{page}.png"
            draw_card(page, text, portrait).save(path, optimize=True)
            manifest[page] = text
            print(f"  {path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB  {text['title']!r}")
        (out / "cards.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
