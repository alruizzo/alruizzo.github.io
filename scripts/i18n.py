"""Translations for the Spanish and German versions of the site.

English is the source and the default (served at the site root). Each further language has one
file, i18n/<lang>.yml, holding everything that is not a page: site configuration overrides,
variables, interface strings for the listing templates, theme names, month names and the
translated fields of every data record. Pages are translated as <page>.<lang>.qmd next to the
English <page>.qmd.

Translations must be complete: a record or field that has no translation fails the build instead
of silently showing English. Publication titles, author names, journal names, talk titles and
dataset titles are not translated (they are cited as published).
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "i18n"
DEFAULT_LANG = "en"
LANGS = ("en", "es", "de")          # order of the language switcher

# Data fields that carry prose and must be translated, per data file. `period` is converted by
# rule (see translate_period), not by the overlay.
TRANSLATABLE = {
    "career": ("title", "org", "place", "detail", "short"),
    "recognition": ("title", "org", "summary", "detail"),
    "news": ("title", "summary"),
    "talks": ("org", "place", "detail"),
    "outputs": ("kind", "description"),
    "funders": ("name", "logo_alt", "logo_caption"),
    "profiles": ("name", "handle"),
    "publications": ("summary", "note"),
}
PERIOD_FILES = ("career", "recognition", "talks")
# Keys every language file must provide.
REQUIRED_KEYS = {"lang", "label", "name", "locale", "config", "vars", "period", "months", "month_year", "themes",
                 "types", "ui", "link_labels", "cards", "data"}
# Interface strings every language must translate (used by build_site.py and the templates).
REQUIRED_UI = {"skip_link", "to_light", "to_dark", "footer_profiles", "language", "authors", "open_access",
               "in_spanish", "doi_for", "preprint", "preprint_of", "data_code", "data_code_for", "cite", "joint",
               "to", "project_record", "grant", "funded_by", "related", "funding", "news_categories", "new_tab"}

PERIOD_RE = re.compile(r"^(\d{4})(?: to (\d{4}|present))?$")


class TranslationError(ValueError):
    """A translation file is incomplete or inconsistent with the English source."""


def load(lang: str) -> dict:
    """The language file, validated for its top-level keys."""
    if lang == DEFAULT_LANG:
        raise TranslationError("English is the source language and has no translation file")
    path = I18N / f"{lang}.yml"
    if not path.is_file():
        raise TranslationError(f"{path.relative_to(ROOT)} not found")
    tr = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = REQUIRED_KEYS - tr.keys()
    unknown = tr.keys() - REQUIRED_KEYS
    if missing or unknown:
        raise TranslationError(f"{path.name}: missing keys {sorted(missing)}, unknown keys {sorted(unknown)}")
    if tr["lang"] != lang:
        raise TranslationError(f"{path.name}: lang is {tr['lang']!r}, expected {lang!r}")
    if len(tr["months"]) != 12:
        raise TranslationError(f"{path.name}: months must list 12 names")
    if set(tr["ui"]) != REQUIRED_UI:
        raise TranslationError(f"{path.name}: ui is missing {sorted(REQUIRED_UI - set(tr['ui']))}, "
                               f"has unknown {sorted(set(tr['ui']) - REQUIRED_UI)}")
    if set(tr["cards"]) != {"name", "index_eyebrow"}:
        raise TranslationError(f"{path.name}: cards needs exactly name and index_eyebrow")
    return tr


def translate_period(period: str, tr: dict) -> str:
    """'2019 to 2022' -> '2019 a 2022'; '2022 to present' -> '2022 a la actualidad'; '2007' stays."""
    m = PERIOD_RE.match(str(period))
    if not m:
        raise TranslationError(f"period {period!r} has no translation rule (expected 'YYYY', 'YYYY to YYYY' or 'YYYY to present')")
    start, end = m.groups()
    if end is None:
        return start
    return f"{start} {tr['period']['to']} {tr['period']['present'] if end == 'present' else end}"


def translate_records(name: str, records: list[dict], tr: dict) -> list[dict]:
    """English records with their prose fields replaced from the overlay; fails on any gap."""
    overlay = (tr["data"] or {}).get(name)
    fields = TRANSLATABLE[name]
    needed = {r["id"]: [f for f in fields if r.get(f)] for r in records if any(r.get(f) for f in fields)}
    if needed and overlay is None:
        raise TranslationError(f"{tr['lang']}.yml: data.{name} is missing")
    overlay = overlay or {}
    problems = []
    for rid in sorted(overlay.keys() - {r["id"] for r in records}):
        problems.append(f"data.{name}.{rid}: no such record in data/{name}.yml")
    out = []
    for rec in records:
        new = copy.deepcopy(rec)
        tr_rec = overlay.get(rec["id"], {}) or {}
        for f in sorted(tr_rec.keys() - set(fields)):
            problems.append(f"data.{name}.{rec['id']}.{f}: not a translatable field of {name}")
        for f in needed.get(rec["id"], []):
            if not str(tr_rec.get(f, "")).strip():
                problems.append(f"data.{name}.{rec['id']}.{f}: translation missing")
            else:
                new[f] = tr_rec[f]
        for f in tr_rec.keys() & set(fields):
            if not rec.get(f):
                problems.append(f"data.{name}.{rec['id']}.{f}: English record has no {f} to translate")
        if name in PERIOD_FILES and rec.get("period"):
            try:
                new["period"] = translate_period(rec["period"], tr)
            except TranslationError as exc:
                problems.append(f"data/{name}.yml ({rec['id']}): {exc}")
        if name in ("talks", "recognition"):
            for link in new.get("links") or []:
                label = tr["link_labels"].get(link["label"])
                if not label:
                    problems.append(f"link_labels: no translation for talk link label {link['label']!r}")
                else:
                    link["label"] = label
        if name == "publications":
            new["categories"] = [theme_name(c, tr) for c in rec.get("categories", [])]
            # Titles stay as published; mark English ones so screen readers switch voice.
            new.setdefault("language", "en")
        out.append(new)
    if problems:
        raise TranslationError(f"{tr['lang']}.yml is incomplete:\n  " + "\n  ".join(problems))
    return out


# English theme names, keyed by slug. Mirrors prerender.THEMES (imported there from here).
THEMES_EN = {
    "attention": "Visual attention",
    "networks": "Brain networks",
    "decline": "Cognitive decline and dementia",
    "lifestyle": "Lifestyle and interventions",
    "clinical": "Clinical neuroscience",
    "data": "Data science",
}
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]


def themes(lang: str) -> dict:
    """Theme slug -> display name in `lang`."""
    if lang == DEFAULT_LANG:
        return dict(THEMES_EN)
    tr = load(lang)
    if set(tr["themes"]) != set(THEMES_EN):
        raise TranslationError(f"{lang}.yml: themes must cover exactly {sorted(THEMES_EN)}")
    return dict(tr["themes"])


def months(lang: str) -> list[str]:
    return list(MONTHS_EN) if lang == DEFAULT_LANG else list(load(lang)["months"])


def month_year(lang: str, month: int, year: str) -> str:
    """'September 2026', 'septiembre de 2026', 'September 2026' (German)."""
    pattern = "{month} {year}" if lang == DEFAULT_LANG else load(lang)["month_year"]
    if "{month}" not in pattern or "{year}" not in pattern:
        raise TranslationError(f"{lang}.yml: month_year must contain {{month}} and {{year}}")
    return pattern.format(month=months(lang)[month - 1], year=year)


def theme_name(english_name: str, tr: dict) -> str:
    slug = next((k for k, v in THEMES_EN.items() if v == english_name), None)
    if slug is None:
        raise TranslationError(f"category {english_name!r} is not a theme")
    return tr["themes"][slug]


def page_languages(page: str) -> list[str]:
    """Languages in which <page>.qmd exists."""
    return [lang for lang in LANGS if (ROOT / (f"{page}.qmd" if lang == DEFAULT_LANG else f"{page}.{lang}.qmd")).is_file()]
