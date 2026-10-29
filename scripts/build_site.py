#!/usr/bin/env python3
"""Build the whole site in English (default, at the root), Spanish (/es/) and German (/de/).

Usage:  python3 scripts/build_site.py            # all languages (what CI runs)
        python3 scripts/build_site.py --lang es  # English plus one translation

Quarto has no built-in multilingual websites, so each translation is rendered as its own Quarto
project in a copy of this one (.i18n-build/<lang>/): the copy gets the translated pages
(<page>.<lang>.qmd renamed to <page>.qmd), the translated data and variables (scripts/i18n.py),
a localized _quarto.yml and the interface strings for the listing templates. The same pre-render
validation and post-render checks run in every language. The outputs are then merged into _site/
and every page gets a language switcher (navbar and footer), hreflang alternates and one sitemap.
A final pass checks the internal links of the combined site, including the switcher's.

Before rendering anything, every translation is checked for completeness; a page or data field
without a translation stops the build (no silent English fallback).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from html import escape
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i18n  # noqa: E402

ROOT = i18n.ROOT
SITE = ROOT / "_site"
WORK = ROOT / ".i18n-build"
DATA_FILES = tuple(i18n.TRANSLATABLE)
COPY_IGNORE = shutil.ignore_patterns("_site", ".git", ".quarto", ".i18n-build", "__pycache__", "*.local.md",
                                     "generated", ".DS_Store")
LANG_NAMES = {"en": "English", "es": "Español", "de": "Deutsch"}
SWITCH_LABEL = {"en": "Language"}


def english_pages() -> list[str]:
    return sorted(p.stem for p in ROOT.glob("*.qmd") if "." not in p.stem)


def check_translations(langs: list[str]) -> dict[str, dict]:
    """Load every language file and prove the translations are complete before any rendering."""
    problems, loaded = [], {}
    pages = english_pages()
    for lang in langs:
        try:
            tr = i18n.load(lang)
        except i18n.TranslationError as exc:
            problems.append(str(exc))
            continue
        loaded[lang] = tr
        for page in pages:
            if not (ROOT / f"{page}.{lang}.qmd").is_file():
                problems.append(f"{page}.{lang}.qmd missing (translation of {page}.qmd)")
        for orphan in sorted(ROOT.glob(f"*.{lang}.qmd")):
            if orphan.name.split(".")[0] not in pages:
                problems.append(f"{orphan.name} has no English page {orphan.name.split('.')[0]}.qmd")
        for name in DATA_FILES:
            try:
                i18n.translate_records(name, yaml.safe_load((ROOT / "data" / f"{name}.yml").read_text(encoding="utf-8")) or [], tr)
            except i18n.TranslationError as exc:
                problems.append(str(exc))
    if problems:
        raise SystemExit("build_site: translations incomplete:\n  " + "\n  ".join(problems))
    return loaded


def set_path(cfg: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    node = cfg
    for k in keys[:-1]:
        if k not in node or not isinstance(node[k], dict):
            raise SystemExit(f"build_site: config override {dotted}: {k} is not a mapping in _quarto.yml")
        node = node[k]
    if keys[-1] not in node:
        raise SystemExit(f"build_site: config override {dotted} targets a key that _quarto.yml does not have")
    node[keys[-1]] = value


def deep_merge(base: dict, over: dict, where: str = "") -> dict:
    for k, v in over.items():
        if k not in base:
            raise SystemExit(f"build_site: vars override {where}{k} is not in _variables.yml")
        base[k] = deep_merge(base[k], v, f"{where}{k}.") if isinstance(v, dict) else v
    return base


def replace_once(text: str, old: str, new: str, where: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"build_site: expected exactly one {old!r} in {where}")
    return text.replace(old, new)


def localize_config(work: Path, lang: str, tr: dict, profiles: list[dict]) -> None:
    cfg = yaml.safe_load((ROOT / "_quarto.yml").read_text(encoding="utf-8"))
    site_url = str(cfg["website"]["site-url"]).rstrip("/")
    cfg["lang"] = lang
    cfg["website"]["site-url"] = f"{site_url}/{lang}"
    cfg["website"]["open-graph"]["locale"] = tr["locale"]
    cfg["image"] = f"assets/social/{lang}/index.png"
    cfg["project"]["render"] = ["*.qmd"]
    for dotted, value in tr["config"].items():
        set_path(cfg, dotted, value)
    # Footer icon row from the translated profiles, built by the same function prerender checks.
    os.environ["RR_LANG"] = lang
    import prerender
    prerender.LANG = lang
    cfg["website"]["page-footer"]["center"] = prerender.footer_html(profiles) + "\n"
    html = cfg["format"]["html"]
    html["include-before-body"][0]["text"] = replace_once(
        html["include-before-body"][0]["text"], ">Skip to main content<", f">{escape(tr['ui']['skip_link'])}<", "include-before-body")
    after = html["include-after-body"][0]["text"]
    after = replace_once(after, '"Switch to light mode"', f'"{tr["ui"]["to_light"]}"', "include-after-body")
    after = replace_once(after, '"Switch to dark mode"', f'"{tr["ui"]["to_dark"]}"', "include-after-body")
    html["include-after-body"][0]["text"] = after
    (work / "_quarto.yml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")


def template_strings(tr: dict) -> dict:
    return {**tr["ui"], "themes": tr["themes"], "types": tr["types"]}


def localize_page(path: Path, strings: dict) -> None:
    """Pass the interface strings to every listing template on the page."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return
    _, fm_text, body = text.split("---", 2)
    fm = yaml.safe_load(fm_text) or {}
    listings = fm.get("listing")
    if not listings:
        return
    for lst in listings if isinstance(listings, list) else [listings]:
        lst["template-params"] = {**(lst.get("template-params") or {}), "t": strings}
    path.write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=1000) + "---" + body,
                    encoding="utf-8")


def build_language(lang: str, tr: dict) -> None:
    work = WORK / lang
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(ROOT, work, ignore=COPY_IGNORE)
    # Pages: the translation replaces the English page; other translations are removed.
    for page in english_pages():
        shutil.copyfile(ROOT / f"{page}.{lang}.qmd", work / f"{page}.qmd")
    for other in work.glob("*.*.qmd"):
        other.unlink()
    # Data and variables.
    profiles = None
    for name in DATA_FILES:
        records = yaml.safe_load((ROOT / "data" / f"{name}.yml").read_text(encoding="utf-8")) or []
        translated = i18n.translate_records(name, records, tr)
        if name == "profiles":
            profiles = translated
        (work / "data" / f"{name}.yml").write_text(
            f"# {lang} translation, generated by scripts/build_site.py from data/{name}.yml and i18n/{lang}.yml.\n"
            + yaml.safe_dump(translated, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    site_vars = yaml.safe_load((ROOT / "_variables.yml").read_text(encoding="utf-8"))
    (work / "_variables.yml").write_text(yaml.safe_dump(deep_merge(site_vars, tr["vars"]), allow_unicode=True,
                                                         sort_keys=False, width=1000), encoding="utf-8")
    localize_config(work, lang, tr, profiles)
    strings = template_strings(tr)
    for page in work.glob("*.qmd"):
        localize_page(page, strings)
    print(f"build_site: rendering {lang} in {work.relative_to(ROOT)}", flush=True)
    run = subprocess.run(["quarto", "render"], cwd=work, env={**os.environ, "RR_LANG": lang})
    if run.returncode != 0:
        raise SystemExit(f"build_site: the {lang} render failed")
    target = SITE / lang
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(work / "_site", target)


# ---------------- Post-processing of the merged site ----------------

def page_rel(path: Path) -> tuple[str, str]:
    """(language, path relative to that language's root) for an HTML file in _site."""
    rel = path.relative_to(SITE).as_posix()
    head = rel.split("/", 1)[0]
    if head in i18n.LANGS and head != i18n.DEFAULT_LANG and "/" in rel:
        return head, rel.split("/", 1)[1]
    return i18n.DEFAULT_LANG, rel


def lang_href(from_lang: str, to_lang: str, rel: str) -> str:
    """Relative link from a page in `from_lang` to the same page in `to_lang`."""
    up = "" if from_lang == i18n.DEFAULT_LANG else "../"
    into = "" if to_lang == i18n.DEFAULT_LANG else f"{to_lang}/"
    target = "" if rel == "index.html" else rel
    href = f"{up}{into}{target}"
    return href or "./"


def lang_url(site_url: str, lang: str, rel: str) -> str:
    base = site_url if lang == i18n.DEFAULT_LANG else f"{site_url}/{lang}"
    return f"{base}/" + ("" if rel == "index.html" else rel)


def switcher(lang: str, rel: str, labels: dict[str, str], cls: str, available: list[str]) -> str:
    links = []
    for other in available:
        current = ' aria-current="true"' if other == lang else ""
        links.append(f'<a href="{lang_href(lang, other, rel)}" hreflang="{other}" lang="{other}" '
                     f'title="{LANG_NAMES[other]}"{current}>{other.upper()}</a>')
    return f'<nav class="rr-lang {cls}" aria-label="{escape(labels[lang])}">' + "".join(links) + "</nav>"


def postprocess(langs_built: list[str], loaded: dict[str, dict]) -> int:
    site_url = str(yaml.safe_load((ROOT / "_quarto.yml").read_text(encoding="utf-8"))["website"]["site-url"]).rstrip("/")
    labels = {**SWITCH_LABEL, **{lang: tr["ui"]["language"] for lang, tr in loaded.items()}}
    pages = {f"{p}.html" for p in english_pages()}
    available = [l for l in i18n.LANGS if l == i18n.DEFAULT_LANG or l in langs_built]
    count = 0
    for path in sorted(SITE.rglob("*.html")):
        lang, rel = page_rel(path)
        if rel not in pages:
            continue          # site_libs, search snippets and other non-page HTML
        html = path.read_text(encoding="utf-8")
        if "rr-lang" in html:
            raise SystemExit(f"build_site: {path.relative_to(SITE)} already has a language switcher")
        nav_anchor = '<ul class="navbar-nav navbar-nav-scroll ms-auto">'
        start = html.find(nav_anchor)
        end = html.find("</ul>", start)
        foot = html.find('<div class="nav-footer-right">')
        foot_end = html.find("</div>", foot)
        if min(start, end, foot, foot_end) < 0:
            raise SystemExit(f"build_site: navbar or footer anchor not found in {path.relative_to(SITE)}")
        # After the right-hand list, not inside it: "Contact" must stay its last item (styled as the
        # navbar's one call to action), and the switcher still sits inside the phone menu.
        end += len("</ul>")
        html = (html[:end] + '\n<div class="rr-lang-item">' + switcher(lang, rel, labels, "rr-lang-nav", available) + "</div>"
                + html[end:foot_end] + switcher(lang, rel, labels, "rr-lang-footer", available) + html[foot_end:])
        if rel != "404.html":
            alternates = [f'<link rel="alternate" hreflang="{o}" href="{lang_url(site_url, o, rel)}">' for o in available]
            alternates.append(f'<link rel="alternate" hreflang="x-default" href="{lang_url(site_url, i18n.DEFAULT_LANG, rel)}">')
            html = replace_once(html, "</head>", "\n".join(alternates) + "\n</head>", str(path.relative_to(SITE)))
        path.write_text(html, encoding="utf-8")
        count += 1
    # One sitemap at the root listing every language.
    root_map = SITE / "sitemap.xml"
    text = root_map.read_text(encoding="utf-8")
    extra = []
    for lang in langs_built:
        sub = SITE / lang / "sitemap.xml"
        if sub.is_file():
            extra += re.findall(r"<url>.*?</url>", sub.read_text(encoding="utf-8"), re.S)
            sub.unlink()
    root_map.write_text(replace_once(text, "</urlset>", "\n".join(extra) + "\n</urlset>", "sitemap.xml"), encoding="utf-8")
    return count


def final_check() -> None:
    """Internal links and anchors across the merged site (the switcher links between languages)."""
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_site.py"), "--links-only"], cwd=ROOT)
    if run.returncode != 0:
        raise SystemExit("build_site: link check of the merged site failed")


def main() -> int:
    langs = [l for l in i18n.LANGS if l != i18n.DEFAULT_LANG]
    if "--lang" in sys.argv:
        langs = [sys.argv[sys.argv.index("--lang") + 1]]
        if langs[0] not in i18n.LANGS or langs[0] == i18n.DEFAULT_LANG:
            raise SystemExit(f"--lang must be one of {[l for l in i18n.LANGS if l != i18n.DEFAULT_LANG]}")
    loaded = check_translations(langs)
    print("build_site: translations complete for " + ", ".join(langs), flush=True)
    run = subprocess.run(["quarto", "render"], cwd=ROOT, env={k: v for k, v in os.environ.items() if k != "RR_LANG"})
    if run.returncode != 0:
        raise SystemExit("build_site: the English render failed")
    for lang in langs:
        build_language(lang, loaded[lang])
    n = postprocess(langs, loaded)
    final_check()
    print(f"build_site: {n} pages in {1 + len(langs)} languages, switcher, hreflang and sitemap OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
