#!/usr/bin/env python3
"""Pre-render step: validate data/*.yml, then regenerate the BibTeX export.

Run automatically by `quarto render` (project.pre-render). Exits non-zero, which aborts the
render, when a record is malformed, an identifier repeats, a cross-reference is dangling, or
an unknown field appears. Prints the realised counts so every build logs what it contains.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BIB_OUT = ROOT / "files" / "ruiz-rizzo-publications.bib"

THEMES = {
    "attention": "Visual attention",
    "networks": "Brain networks",
    "decline": "Cognitive decline and dementia",
    "lifestyle": "Lifestyle and interventions",
    "clinical": "Clinical neuroscience",
    "data": "Data science",
}
PUB_TYPES = {"article", "chapter", "preprint", "abstract", "thesis", "scicomm"}
PUB_FIELDS = {
    "required": {"id", "type", "title", "year", "date"},
    "optional": {"authors", "venue", "volume", "issue", "pages", "doi", "url", "open_access", "language",
                 "categories", "theme", "featured", "selected", "note", "summary", "preprint", "data", "source",
                 "equal_contribution"},
}
OUTPUT_FIELDS = {"required": {"id", "title", "kind", "year", "repository", "doi", "url"},
                 "optional": {"related", "license", "description"}}
CAREER_FIELDS = {"required": {"id", "kind", "period", "title", "org"}, "optional": {"place", "detail", "highlight", "short"}}
RECOG_FIELDS = {"required": {"id", "kind", "period", "title"},
                "optional": {"org", "highlight", "source", "funders", "programme", "grant", "grant_url", "fellowship", "summary",
                             "amount_eur", "detail"}}
FUNDER_FIELDS = {"required": {"id", "name"}, "optional": {"logo", "logo_alt", "logo_source", "url", "logo_status", "logo_kind", "in_strip", "logo_caption"}}
EU_STATEMENTS = {"Funded by the European Union", "Co-funded by the European Union"}
SOURCES = {"repo", "orcid", "cv", "about+orcid"}
RECOG_SOURCES = {"orcid", "cv", "orcid+cv", "cv+cordis", "about+orcid+cordis"}
GENERATED = DATA / "generated"
FEATURED_MAX = 4
HIGHLIGHTS_PER_COLUMN = 2   # homepage credentials strip: education, positions, recognition

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ME_RE = re.compile(r"^Ruiz(?:[- ]Rizzo)?\s+A")
# House style: no em dashes in prose we write (summaries, notes). Publication titles stay verbatim.
EM_DASH = "\u2014"

errors: list[str] = []
warnings: list[str] = []


def load(name: str) -> list[dict]:
    path = DATA / name
    try:
        records = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{name}: file missing")
        return []
    except yaml.YAMLError as exc:
        errors.append(f"{name}: invalid YAML ({exc})")
        return []
    if records is None:
        return []  # empty collection is valid
    if not isinstance(records, list):
        errors.append(f"{name}: top level must be a list of records")
        return []
    return records


def check_fields(name: str, records: list[dict], spec: dict) -> None:
    seen: dict[str, int] = {}
    allowed = spec["required"] | spec["optional"]
    for i, rec in enumerate(records):
        where = f"{name}[{i}] ({rec.get('id', '?')})"
        if not isinstance(rec, dict):
            errors.append(f"{where}: record must be a mapping")
            continue
        for f in sorted(spec["required"] - rec.keys()):
            errors.append(f"{where}: missing required field '{f}'")
        for f in sorted(rec.keys() - allowed):
            errors.append(f"{where}: unknown field '{f}' (typo?)")
        rid = rec.get("id")
        if rid is not None:
            if not isinstance(rid, str) or not ID_RE.match(rid):
                errors.append(f"{where}: id must be lowercase-hyphenated")
            elif rid in seen:
                errors.append(f"{where}: duplicate id (also record {seen[rid]})")
            else:
                seen[rid] = i


def check_publications(pubs: list[dict]) -> None:
    check_fields("publications.yml", pubs, PUB_FIELDS)
    for rec in pubs:
        where = f"publications.yml ({rec.get('id', '?')})"
        typ = rec.get("type")
        if typ not in PUB_TYPES:
            errors.append(f"{where}: type '{typ}' not in {sorted(PUB_TYPES)}")
        date = str(rec.get("date", ""))
        if not DATE_RE.match(date):
            errors.append(f"{where}: date must be YYYY-MM-DD")
        elif rec.get("year") != int(date[:4]):
            errors.append(f"{where}: year {rec.get('year')} does not match date {date}")
        doi = rec.get("doi")
        if doi is not None and (not DOI_RE.match(str(doi)) or str(doi) != str(doi).lower()):
            errors.append(f"{where}: DOI '{doi}' must be a bare, lowercase 10.xxxx/... identifier")
        if rec.get("preprint") is not None and not DOI_RE.match(str(rec["preprint"])):
            errors.append(f"{where}: preprint must be a bare DOI")
        if not doi and not rec.get("url") and typ not in {"thesis"}:
            warnings.append(f"{where}: no DOI or URL, entry renders without a link")
        url = rec.get("url")
        if url is not None and not str(url).startswith("https://"):
            errors.append(f"{where}: url must be https")
        for d in rec.get("data") or []:
            if not str(d).startswith("https://"):
                errors.append(f"{where}: data link '{d}' must be https")
        cats = rec.get("categories") or []
        bad = [c for c in cats if c not in THEMES.values()]
        if bad:
            errors.append(f"{where}: unknown categories {bad}; allowed: {list(THEMES.values())}")
        theme = rec.get("theme")
        if cats and theme != next((k for k, v in THEMES.items() if v == cats[0]), None):
            errors.append(f"{where}: theme '{theme}' must be the slug of the first category '{cats[0]}'")
        if theme and not cats:
            errors.append(f"{where}: theme set without categories")
        authors = rec.get("authors")
        if authors is not None:
            if not isinstance(authors, list) or not all(isinstance(a, str) and a.strip() for a in authors):
                errors.append(f"{where}: authors must be a list of non-empty strings")
            elif not any(ME_RE.match(a) for a in authors):
                errors.append(f"{where}: author list does not include Ruiz-Rizzo")
        else:
            warnings.append(f"{where}: author list not recorded (renders without authors)")
        if rec.get("featured"):
            if not rec.get("summary") or not doi:
                errors.append(f"{where}: featured items need a summary and a DOI")
        for prose in ("summary", "note"):
            if EM_DASH in str(rec.get(prose, "")):
                errors.append(f"{where}: em dash in '{prose}' (house style)")
        if rec.get("source") not in SOURCES:
            errors.append(f"{where}: source must be one of {sorted(SOURCES)}")
    n_feat = sum(bool(r.get("featured")) for r in pubs)
    if not 1 <= n_feat <= FEATURED_MAX:
        errors.append(f"publications.yml: {n_feat} featured items; the homepage grid expects 1 to {FEATURED_MAX}")
    dois = Counter(r["doi"] for r in pubs if r.get("doi"))
    for d, n in dois.items():
        if n > 1:
            errors.append(f"publications.yml: DOI {d} appears {n} times")
    for rec in pubs:
        where = f"publications.yml ({rec.get('id')})"
        if rec.get("equal_contribution") not in (None, "first", "last"):
            errors.append(f"{where}: equal_contribution must be 'first' or 'last'")
        if (rec.get("featured") or rec.get("selected")) and not is_lead(rec):
            errors.append(f"{where}: featured or selected, but Ruiz-Rizzo is {author_role(rec)}; "
                          "only papers she leads (first or last author) are highlighted")


# ---------------- Author position: only papers she leads are highlighted ----------------
# Highlights (homepage features, news, the research page's selected lists, findings and method
# evidence links) show only papers where she is first or last author. equal_contribution records
# a documented shared first or shared senior authorship (from the CV's asterisks), which counts.
HIGHLIGHT_PAGES = ("index.qmd", "research.qmd", "expertise.qmd", "about.qmd", "contact.qmd", "news.qmd")


def author_role(rec: dict) -> str:
    authors = rec.get("authors") or []
    idx = [i for i, a in enumerate(authors) if ME_RE.match(a)]
    if not idx:
        return "not listed"
    if idx[0] == 0:
        return "first author"
    if idx[0] == len(authors) - 1:
        return "last author"
    shared = rec.get("equal_contribution")
    if shared:
        return f"shared {shared} author"
    return f"a middle author ({idx[0] + 1} of {len(authors)})"


def is_lead(rec: dict) -> bool:
    return author_role(rec) in ("first author", "last author", "shared first author", "shared last author")


def check_highlight_links(pubs: list[dict]) -> None:
    """DOI links in curated pages (findings, method evidence, prose) must point to papers she leads.
    The publications page lists everything and is exempt."""
    by_doi = {r["doi"].lower(): r for r in pubs if r.get("doi")}
    for page in HIGHLIGHT_PAGES:
        path = ROOT / page
        if not path.is_file():
            continue
        for doi in re.findall(r"doi\.org/(10\.[^\s)\"<>\]]+)", path.read_text(encoding="utf-8")):
            rec = by_doi.get(doi.lower())
            if rec is not None and not is_lead(rec):
                errors.append(f"{page}: links {rec['id']}, where Ruiz-Rizzo is {author_role(rec)}; "
                              "highlight only papers she leads")


def write_publications_with_roles(pubs: list[dict]) -> None:
    """Listings cannot compute fields, so write a copy with `lead` for the research page's lists."""
    out = [{**r, "lead": is_lead(r)} for r in pubs]
    GENERATED.mkdir(exist_ok=True)
    text = ("# Generated by scripts/prerender.py from publications.yml (adds `lead`). Do not edit.\n"
            + yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=110))
    target = GENERATED / "publications.yml"
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.write_text(text, encoding="utf-8")


def check_outputs(outputs: list[dict], pubs: list[dict]) -> None:
    check_fields("outputs.yml", outputs, OUTPUT_FIELDS)
    by_id = {p.get("id"): p for p in pubs}
    output_urls = set()
    for rec in outputs:
        where = f"outputs.yml ({rec.get('id', '?')})"
        output_urls.add(rec.get("url"))
        if not DOI_RE.match(str(rec.get("doi", ""))):
            errors.append(f"{where}: doi must be a bare DOI")
        rel = rec.get("related")
        if rel is not None:
            if rel not in by_id:
                errors.append(f"{where}: related '{rel}' is not a publication id")
            elif rec.get("url") not in (by_id[rel].get("data") or []):
                errors.append(f"{where}: publication '{rel}' does not list {rec.get('url')} under data")
    for p in pubs:
        for d in p.get("data") or []:
            if d not in output_urls:
                errors.append(f"publications.yml ({p.get('id')}): data link {d} has no record in outputs.yml")


def check_simple(name: str, records: list[dict], spec: dict, kinds: set[str]) -> None:
    check_fields(name, records, spec)
    for rec in records:
        if rec.get("kind") not in kinds:
            errors.append(f"{name} ({rec.get('id')}): kind must be one of {sorted(kinds)}")
        for k, v in rec.items():
            if isinstance(v, str) and EM_DASH in v:
                errors.append(f"{name} ({rec.get('id')}): em dash in '{k}' (house style)")


def check_recognition(recognition: list[dict], funders: list[dict]) -> None:
    check_fields("funders.yml", funders, FUNDER_FIELDS)
    by_id = {f.get("id"): f for f in funders}
    for f in funders:
        where = f"funders.yml ({f.get('id')})"
        if f.get("logo"):
            if not (ROOT / f["logo"]).is_file():
                errors.append(f"{where}: logo file {f['logo']} not found")
            for need in ("logo_alt", "logo_source"):
                if not f.get(need):
                    errors.append(f"{where}: a logo needs '{need}'")
        if f.get("logo_kind") not in (None, "eu-emblem"):
            errors.append(f"{where}: logo_kind must be 'eu-emblem' or absent")
        if f.get("logo_kind") == "eu-emblem" and f.get("logo_alt") not in EU_STATEMENTS:
            errors.append(f"{where}: EU emblem alt text must be its funding statement, one of {sorted(EU_STATEMENTS)}")
        if f.get("logo_caption") and not f.get("logo"):
            errors.append(f"{where}: logo_caption needs a logo")
        if f.get("logo_caption") and f.get("logo_kind") == "eu-emblem":
            errors.append(f"{where}: the EU emblem must not be combined with other text (it carries its own statement)")
        if f.get("logo_status") not in (None, "pending"):
            errors.append(f"{where}: logo_status must be 'pending' or absent")
    for rec in recognition:
        where = f"recognition.yml ({rec.get('id')})"
        for fid in rec.get("funders") or []:
            if fid not in by_id:
                errors.append(f"{where}: funder '{fid}' is not defined in funders.yml")
        ids = rec.get("funders") or []
        eu = [i for i, fid in enumerate(ids) if (by_id.get(fid) or {}).get("logo_kind") == "eu-emblem"]
        if eu and eu != [0]:
            errors.append(f"{where}: the EU emblem must be listed once and first among funders (EU emblem rules)")
        if rec.get("fellowship") and not (rec.get("summary") and rec.get("funders")):
            errors.append(f"{where}: fellowship entries need a summary and funders")
        if rec.get("source") not in RECOG_SOURCES:
            errors.append(f"{where}: source must be one of {sorted(RECOG_SOURCES)}")
        amount = rec.get("amount_eur")
        if amount is not None and (rec.get("kind") != "funding" or type(amount) is not int or amount <= 0):
            errors.append(f"{where}: amount_eur must be a positive whole number of euros, on funding records only")
    pending = [f["name"] for f in funders if f.get("logo_status") == "pending"]
    if pending:
        warnings.append(f"funders.yml: logos pending for {', '.join(pending)} (rendered as wordmarks)")


def check_highlights(career: list[dict], recognition: list[dict]) -> None:
    """The credentials strip under the hero shows exactly HIGHLIGHTS_PER_COLUMN items per column."""
    columns = {"education": [r for r in career if r.get("kind") == "education" and r.get("highlight")],
               "positions": [r for r in career if r.get("kind") == "position" and r.get("highlight")],
               "recognition": [r for r in recognition if r.get("highlight")]}
    for name, items in columns.items():
        if len(items) != HIGHLIGHTS_PER_COLUMN:
            errors.append(f"credentials strip: {len(items)} highlighted {name} items "
                          f"({', '.join(str(r.get('id')) for r in items)}); expected {HIGHLIGHTS_PER_COLUMN}")


def write_resolved_recognition(recognition: list[dict], funders: list[dict]) -> None:
    """Listings cannot join two files, so write recognition records with their funders inlined."""
    by_id = {f["id"]: f for f in funders}
    resolved = []
    for rec in recognition:
        out = dict(rec)
        out["funder_list"] = [by_id[f] for f in rec.get("funders") or []]
        if rec.get("amount_eur"):
            out["amount"] = f"€{rec['amount_eur']:,}"
        resolved.append(out)
    GENERATED.mkdir(exist_ok=True)
    text = ("# Generated by scripts/prerender.py from recognition.yml and funders.yml. Do not edit.\n"
            + yaml.safe_dump(resolved, allow_unicode=True, sort_keys=False, width=110))
    target = GENERATED / "recognition.yml"
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.write_text(text, encoding="utf-8")
    funder_text = ("# Generated by scripts/prerender.py: funders that support a listed award or grant.\n"
                   + yaml.safe_dump([f for f in funders if f.get("in_strip", True)
                                     and any(f["id"] in (r.get("funders") or []) for r in recognition)],
                                    allow_unicode=True, sort_keys=False, width=110))
    target = GENERATED / "funders.yml"
    if not target.exists() or target.read_text(encoding="utf-8") != funder_text:
        target.write_text(funder_text, encoding="utf-8")


# ---------------- News and talks ----------------
NEWS_FIELDS = {"required": {"id", "date", "category", "title", "summary"}, "optional": {"url", "related"}}
NEWS_CATEGORIES = {"Publication", "Preprint", "Talk", "Press", "Media", "Event", "Funding", "Project"}
NEWS_DATE_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")
NEWS_TITLE_MAX, NEWS_SUMMARY_MAX = 80, 300
TALK_FIELDS = {"required": {"id", "period", "title", "org"}, "optional": {"place", "detail", "links"}}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def news_sort_key(date: str) -> tuple[int, int, int]:
    y, m, d = NEWS_DATE_RE.match(date).groups()
    return int(y), int(m), int(d or 0)


def check_link(where: str, url) -> None:
    """Links in news and talks: external https, or an internal page (with optional anchor) that exists."""
    if not isinstance(url, str) or not url.strip():
        errors.append(f"{where}: url must be a non-empty string")
    elif url.startswith("https://"):
        return
    elif re.match(r"^[a-z0-9-]+\.qmd(#[A-Za-z0-9_-]+)?$", url):
        if not (ROOT / url.split("#")[0]).is_file():
            errors.append(f"{where}: internal link {url} points to a missing page")
    else:
        errors.append(f"{where}: url must be https:// or an internal page.qmd#anchor, got {url!r}")


def check_news(news: list[dict], pubs: list[dict]) -> None:
    check_fields("news.yml", news, NEWS_FIELDS)
    by_id = {p.get("id"): p for p in pubs}
    dated = []
    for rec in news:
        where = f"news.yml ({rec.get('id')})"
        date = rec.get("date")
        m = NEWS_DATE_RE.match(date) if isinstance(date, str) else None
        if not m or not 1 <= int(m.group(2)) <= 12 or (m.group(3) and not 1 <= int(m.group(3)) <= 31):
            errors.append(f"{where}: date must be a quoted YYYY-MM-DD or YYYY-MM, got {date!r}")
        else:
            dated.append(date)
        if rec.get("category") not in NEWS_CATEGORIES:
            errors.append(f"{where}: category must be one of {sorted(NEWS_CATEGORIES)}")
        title, summary = str(rec.get("title", "")), str(rec.get("summary", ""))
        if len(title) > NEWS_TITLE_MAX:
            errors.append(f"{where}: title is {len(title)} characters; keep it to {NEWS_TITLE_MAX}")
        if len(summary) > NEWS_SUMMARY_MAX:
            errors.append(f"{where}: summary is {len(summary)} characters; keep it to {NEWS_SUMMARY_MAX}")
        if len(re.findall(r"[.!?](?:\s|$)", summary)) > 2:
            errors.append(f"{where}: summary has more than two sentences")
        for k in ("title", "summary"):
            if EM_DASH in str(rec.get(k, "")):
                errors.append(f"{where}: em dash in '{k}' (house style)")
        if "url" in rec:
            check_link(where, rec["url"])
        if "related" in rec:
            pub = by_id.get(rec["related"])
            if pub is None:
                errors.append(f"{where}: related publication '{rec['related']}' not in publications.yml")
            elif pub.get("doi") and rec.get("url") != f"https://doi.org/{pub['doi']}":
                errors.append(f"{where}: url must be the related publication's DOI link https://doi.org/{pub['doi']}")
            elif not is_lead(pub):
                errors.append(f"{where}: related publication {pub['id']} is one where Ruiz-Rizzo is "
                              f"{author_role(pub)}; news highlights only papers she leads")
    keys = [news_sort_key(d) for d in dated]
    if len(dated) == len(news) and keys != sorted(keys, reverse=True):
        errors.append("news.yml: items must be ordered newest first")


def check_talks(talks: list[dict]) -> None:
    check_fields("talks.yml", talks, TALK_FIELDS)
    for rec in talks:
        where = f"talks.yml ({rec.get('id')})"
        for k, v in rec.items():
            if isinstance(v, str) and EM_DASH in v:
                errors.append(f"{where}: em dash in '{k}' (house style)")
        links = rec.get("links")
        if links is None:
            continue
        if not isinstance(links, list) or not links:
            errors.append(f"{where}: links must be a non-empty list of {{label, url}}")
            continue
        for link in links:
            if not isinstance(link, dict) or set(link) != {"label", "url"} or not str(link.get("label", "")).strip():
                errors.append(f"{where}: each link needs exactly a label and a url")
            else:
                check_link(where, link["url"])


def write_news(news: list[dict]) -> None:
    """Add display dates ("September 2026") and machine dates for <time datetime>."""
    out = []
    for rec in news:
        y, m, _ = NEWS_DATE_RE.match(rec["date"]).groups()
        out.append({**rec, "when": f"{MONTHS[int(m) - 1]} {y}", "datetime": rec["date"]})
    GENERATED.mkdir(exist_ok=True)
    text = ("# Generated by scripts/prerender.py from news.yml. Do not edit.\n"
            + yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=110))
    target = GENERATED / "news.yml"
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.write_text(text, encoding="utf-8")


# ---------------- CV: Adriana's own PDF, published unchanged ----------------
def file_sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_cv(site_vars: dict) -> None:
    cv = site_vars.get("cv") or {}
    path = ROOT / str(cv.get("file", ""))
    if not cv.get("file") or not path.is_file():
        errors.append(f"_variables.yml: cv.file {cv.get('file')!r} not found")
    elif not cv.get("sha256"):
        errors.append("_variables.yml: cv.sha256 missing (it pins the supplied PDF)")
    elif file_sha256(path) != cv["sha256"]:
        errors.append(f"{cv['file']}: content differs from the supplied CV (sha256 mismatch); "
                      "publish the owner's PDF unchanged, then update cv.sha256 only for a new version")


# ---------------- Co-authors ----------------
COAUTHOR_MIN_JOINT = 3          # joint peer-reviewed works needed to be listed
COAUTHOR_CURRENT_SINCE = 2023   # last joint work in or after this year counts as current
COAUTHOR_TYPES = {"article", "chapter", "preprint"}


def coauthor_key(name: str) -> str:
    """Family name without accents, hyphens or spaces, plus first initial."""
    import unicodedata
    family, initials = name.rsplit(" ", 1)
    folded = unicodedata.normalize("NFKD", family).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", folded) + " " + initials[0].lower()


def display_name(name: str) -> str:
    """'Müller HJ' -> 'H. J. Müller'."""
    family, initials = name.rsplit(" ", 1)
    return " ".join(c + "." for c in initials) + " " + family


def compute_coauthors(pubs: list[dict], aliases: dict) -> list[dict]:
    groups: dict[str, dict] = {}
    for p in pubs:
        if p.get("type") not in COAUTHOR_TYPES:
            continue
        seen_here = set()
        for raw in p.get("authors") or []:
            if ME_RE.match(raw):
                continue
            name = aliases.get(raw, raw)
            k = coauthor_key(name)
            if k in seen_here:
                continue
            seen_here.add(k)
            g = groups.setdefault(k, {"forms": Counter(), "years": [], "ids": []})
            g["forms"][name] += 1
            g["years"].append(p["year"])
            g["ids"].append(p["id"])
    out = []
    for k, g in groups.items():
        if len(g["years"]) < COAUTHOR_MIN_JOINT:
            continue
        # Most complete published form (more initials), then most frequent.
        form = max(g["forms"], key=lambda f: (len(f.rsplit(" ", 1)[1]), g["forms"][f]))
        last = max(g["years"])
        out.append({"id": re.sub(r"[^a-z0-9]+", "-", k).strip("-"), "name": display_name(form), "as_published": form,
                    "joint": len(g["years"]), "first_year": min(g["years"]), "last_year": last,
                    "status": "current" if last >= COAUTHOR_CURRENT_SINCE else "previous"})
    out.sort(key=lambda c: (-c["joint"], c["name"].split(" ")[-1]))
    return out


def write_coauthors(pubs: list[dict]) -> list[dict]:
    path = DATA / "coauthor-aliases.yml"
    aliases = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    aliases = aliases or {}
    known = {a for p in pubs for a in p.get("authors") or []}
    for src, dst in aliases.items():
        if src not in known:
            errors.append(f"coauthor-aliases.yml: '{src}' does not appear in any author list")
    coauthors = compute_coauthors(pubs, aliases)
    GENERATED.mkdir(exist_ok=True)
    text = (f"# Generated by scripts/prerender.py: co-authors with >= {COAUTHOR_MIN_JOINT} joint peer-reviewed works.\n"
            + yaml.safe_dump(coauthors, allow_unicode=True, sort_keys=False, width=110))
    target = GENERATED / "coauthors.yml"
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.write_text(text, encoding="utf-8")
    return coauthors


# ---------------- Link previews (share cards) ----------------
SHARE_DESC_MAX = 160      # longer descriptions are cut off in most link previews
SHARE_TITLE_MAX = 70
CARD_SIZE = (1200, 630)   # Open Graph / Twitter large card
CARD_MAX_BYTES = 300_000  # some messengers drop larger preview images


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def check_share_cards() -> None:
    """Every page has its own, current preview card and share-ready title and description."""
    import json
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from make_social_cards import PAGES, card_text   # Pillow is only needed to draw, not here

    pages = {p.stem for p in ROOT.glob("*.qmd")}
    for missing in sorted(pages - PAGES.keys()):
        errors.append(f"{missing}.qmd: no preview card; add it to PAGES in scripts/make_social_cards.py")
    manifest_path = ROOT / "assets" / "social" / "cards.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for page in sorted(pages & PAGES.keys()):
        where = f"{page}.qmd"
        fm = yaml.safe_load((ROOT / where).read_text(encoding="utf-8").split("---", 2)[1]) or {}
        card = ROOT / "assets" / "social" / f"{page}.png"
        if fm.get("image") != f"assets/social/{page}.png":
            errors.append(f"{where}: image must be assets/social/{page}.png (its preview card)")
        if not fm.get("image-alt"):
            errors.append(f"{where}: image-alt (preview card alt text) missing")
        desc = str(fm.get("description", ""))
        if not 50 <= len(desc) <= SHARE_DESC_MAX:
            errors.append(f"{where}: description is {len(desc)} characters; previews need 50 to {SHARE_DESC_MAX}")
        title = str(((fm.get("open-graph") or {}).get("title")) or fm.get("title") or fm.get("pagetitle") or "")
        if not title or len(title) > SHARE_TITLE_MAX:
            errors.append(f"{where}: share title missing or longer than {SHARE_TITLE_MAX} characters")
        if not card.is_file():
            errors.append(f"{where}: preview card {card.relative_to(ROOT)} missing; run scripts/make_social_cards.py")
            continue
        try:
            size = png_size(card)
        except ValueError:
            errors.append(f"{where}: preview card is not a PNG")
            continue
        if size != CARD_SIZE:
            errors.append(f"{where}: preview card is {size[0]}x{size[1]}, expected {CARD_SIZE[0]}x{CARD_SIZE[1]}")
        if card.stat().st_size > CARD_MAX_BYTES:
            errors.append(f"{where}: preview card is {card.stat().st_size // 1024} KB, keep it under {CARD_MAX_BYTES // 1000} KB")
        if manifest.get(page) != card_text(page):
            errors.append(f"{where}: preview card is stale (title or description changed); run python3 scripts/make_social_cards.py")


# ---------------- Profiles: contact list and footer icon row ----------------
PROFILE_FIELDS = {"required": {"id", "name", "url", "icon", "handle"}, "optional": {"hero"}}
# Markers sit at the key indentation (4 spaces): deeper, they would be literal text inside a YAML block.
FOOTER_BEGIN = "    # BEGIN profiles footer: generated from data/profiles.yml by `python3 scripts/prerender.py --write-footer`"
FOOTER_END = "    # END profiles footer"


def footer_html(profiles: list[dict]) -> str:
    """The footer's icon row: one link per profile, icon above its name (names stay visible)."""
    from html import escape
    links = "\n".join(
        f'<a class="rr-social-link" href="{escape(p["url"])}"><span class="rr-icon rr-icon-{escape(p["icon"])}" '
        f'aria-hidden="true"></span><span class="rr-social-name">{escape(p["name"])}</span></a>'
        for p in profiles)
    return f'<nav class="rr-social" aria-label="Contact and profiles">\n{links}\n</nav>'


def footer_block(profiles: list[dict]) -> str:
    body = "\n".join("        " + line for line in footer_html(profiles).splitlines())
    return f"{FOOTER_BEGIN}\n    center: |\n{body}\n{FOOTER_END}"


def check_profiles(profiles: list[dict]) -> None:
    check_fields("profiles.yml", profiles, PROFILE_FIELDS)
    site_vars = yaml.safe_load((ROOT / "_variables.yml").read_text(encoding="utf-8")) or {}
    links = dict(site_vars.get("links") or {}, email="mailto:" + str(site_vars.get("email", "")))
    scss = (ROOT / "styles" / "site.scss").read_text(encoding="utf-8")
    for p in profiles:
        where = f"profiles.yml ({p.get('id')})"
        if p.get("id") in links and links[p["id"]] != p.get("url"):
            errors.append(f"{where}: url {p.get('url')} differs from _variables.yml ({links[p['id']]})")
        if not (ROOT / "assets" / "icons" / f"{p.get('icon')}.svg").is_file():
            errors.append(f"{where}: icon file assets/icons/{p.get('icon')}.svg not found")
        if f".rr-icon-{p.get('icon')} " not in scss and f".rr-icon-{p.get('icon')}{{" not in scss:
            errors.append(f"{where}: no .rr-icon-{p.get('icon')} rule in styles/site.scss")
        if not str(p.get("url", "")).startswith(("https://", "mailto:")):
            errors.append(f"{where}: url must be https or mailto")
    quarto_yml = (ROOT / "_quarto.yml").read_text(encoding="utf-8")
    start, end = quarto_yml.find(FOOTER_BEGIN), quarto_yml.find(FOOTER_END)
    if start < 0 or end < 0:
        errors.append("_quarto.yml: profiles footer markers missing; run python3 scripts/prerender.py --write-footer")
    elif quarto_yml[start:end + len(FOOTER_END)] != footer_block(profiles):
        errors.append("_quarto.yml: footer icon row is out of sync with data/profiles.yml; "
                      "run python3 scripts/prerender.py --write-footer")


def write_footer(profiles: list[dict]) -> None:
    path = ROOT / "_quarto.yml"
    text = path.read_text(encoding="utf-8")
    start, end = text.find(FOOTER_BEGIN), text.find(FOOTER_END)
    if start < 0 or end < 0:
        raise SystemExit("_quarto.yml: add the profiles footer markers under page-footer first")
    path.write_text(text[:start] + footer_block(profiles) + text[end + len(FOOTER_END):], encoding="utf-8")
    print("prerender: footer icon row rewritten from data/profiles.yml")


# ---------------- BibTeX export ----------------

def bib_escape(s: str) -> str:
    return re.sub(r"([&%$#_])", r"\\\1", str(s))


def bib_author(a: str) -> str:
    parts = a.split(" ")
    if len(parts) < 2:
        return a
    ini = parts.pop()
    return f"{' '.join(parts)}, {' '.join(c + '.' for c in ini)}"


def to_bibtex(rec: dict) -> str:
    typ = rec["type"]
    fields: dict[str, str] = {"title": "{" + bib_escape(rec["title"]) + "}", "year": str(rec["year"])}
    if rec.get("authors"):
        fields["author"] = " and ".join(bib_author(a) for a in rec["authors"])
    venue = rec.get("venue", "")
    if typ == "chapter":
        entry = "incollection"
        fields["booktitle"] = venue.removeprefix("In: ")
    elif typ == "thesis":
        entry = "phdthesis" if venue.lower().startswith("doctoral") else "mastersthesis"
        fields["school"] = venue
    elif typ == "preprint":
        entry = "misc"
        fields["howpublished"] = venue
        fields["note"] = "Preprint"
    else:
        entry = "article"
        fields["journal"] = venue
        if typ == "abstract":
            fields["note"] = "Conference abstract"
    for k in ("volume", "issue", "pages"):
        if rec.get(k):
            fields["number" if k == "issue" else k] = str(rec[k]).replace("-", "--") if k == "pages" else str(rec[k])
    if rec.get("doi"):
        fields["doi"] = rec["doi"]
    elif rec.get("url"):
        fields["url"] = rec["url"]
    if rec.get("language") == "es":
        fields["langid"] = "spanish"
    body = ",\n".join(f"  {k} = {{{bib_escape(v) if k in ('journal', 'booktitle', 'school', 'howpublished') else v}}}"
                      for k, v in fields.items())
    return f"@{entry}{{{rec['id']},\n{body}\n}}\n"


def write_bib(pubs: list[dict]) -> None:
    header = ("% Publications of Adriana L. Ruiz-Rizzo.\n"
              "% Generated from data/publications.yml by scripts/prerender.py. Do not edit by hand.\n\n")
    text = header + "\n".join(to_bibtex(p) for p in sorted(pubs, key=lambda r: (-r["year"], r["id"])))
    # Write only on change so `quarto preview` does not see a modified resource on every render.
    if not BIB_OUT.exists() or BIB_OUT.read_text(encoding="utf-8") != text:
        BIB_OUT.write_text(text, encoding="utf-8")
        print(f"  wrote {BIB_OUT.relative_to(ROOT)}")


def main() -> int:
    pubs = load("publications.yml")
    outputs = load("outputs.yml")
    career = load("career.yml")
    recognition = load("recognition.yml")
    funders = load("funders.yml")
    check_publications(pubs)
    check_outputs(outputs, pubs)
    check_simple("career.yml", career, CAREER_FIELDS, {"position", "education", "teaching"})
    for rec in career:
        if rec.get("highlight") and not rec.get("short"):
            errors.append(f"career.yml ({rec.get('id')}): highlight needs a short label")
    check_simple("recognition.yml", recognition, RECOG_FIELDS, {"award", "funding"})
    check_recognition(recognition, funders)
    check_highlights(career, recognition)
    coauthors = write_coauthors(pubs)
    check_share_cards()
    profiles = load("profiles.yml")
    check_profiles(profiles)
    news = load("news.yml")
    check_news(news, pubs)
    check_highlight_links(pubs)
    talks = load("talks.yml")
    check_talks(talks)
    site_vars = yaml.safe_load((ROOT / "_variables.yml").read_text(encoding="utf-8")) or {}
    check_cv(site_vars)
    if str((site_vars.get("legal") or {}).get("address", "")).startswith("TO BE ADDED"):
        warnings.append("_variables.yml: legal.address is still a placeholder; the legal notice is not complete")

    print("prerender: data summary")
    print("  publications by type:", dict(Counter(p.get("type") for p in pubs)))
    print("  publications by primary theme:", dict(Counter(p.get("theme", "none") for p in pubs)))
    print("  featured:", [p["id"] for p in pubs if p.get("featured")])
    print(f"  outputs: {len(outputs)}, career: {len(career)}, recognition: {len(recognition)}, funders: {len(funders)}")
    print(f"  news: {len(news)} {dict(Counter(n.get('category') for n in news))}, talks: {len(talks)}")
    print(f"  co-authors listed: {sum(c['status'] == 'current' for c in coauthors)} current, "
          f"{sum(c['status'] == 'previous' for c in coauthors)} previous (>= {COAUTHOR_MIN_JOINT} joint works)")
    for w in warnings:
        print("  warning:", w)
    if errors:
        for e in errors:
            print("  ERROR:", e, file=sys.stderr)
        print(f"prerender: {len(errors)} error(s); render aborted.", file=sys.stderr)
        return 1
    write_bib(pubs)
    write_resolved_recognition(recognition, funders)
    write_news(news)
    write_publications_with_roles(pubs)
    print("prerender: data valid.")
    return 0


if __name__ == "__main__":
    if "--write-footer" in sys.argv:
        write_footer(load("profiles.yml"))
        sys.exit(0)
    sys.exit(main())
