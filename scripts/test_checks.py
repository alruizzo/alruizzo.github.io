#!/usr/bin/env python3
"""Tests for the build checks. Run: python3 -m unittest discover -s scripts -p 'test_*.py'

The validators guard the content data, so they get fault-injection tests: start from the real,
valid data, inject one known defect, and assert the validator names it. A validator that stops
catching a defect fails here instead of silently letting a bad page ship.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_site  # noqa: E402
import prerender  # noqa: E402


def run_checks(pubs, outputs, career, recognition, funders=None) -> list[str]:
    funders = prerender.load("funders.yml") if funders is None else funders
    prerender.errors.clear()
    prerender.warnings.clear()
    prerender.check_publications(pubs)
    prerender.check_outputs(outputs, pubs)
    prerender.check_simple("career.yml", career, prerender.CAREER_FIELDS, {"position", "education", "teaching"})
    prerender.check_simple("recognition.yml", recognition, prerender.RECOG_FIELDS, {"award", "funding"})
    prerender.check_recognition(recognition, funders)
    return list(prerender.errors)


class DataValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pubs = prerender.load("publications.yml")
        cls.outputs = prerender.load("outputs.yml")
        cls.career = prerender.load("career.yml")
        cls.recognition = prerender.load("recognition.yml")

    def fresh(self):
        return (copy.deepcopy(self.pubs), copy.deepcopy(self.outputs),
                copy.deepcopy(self.career), copy.deepcopy(self.recognition))

    def assertCaught(self, errors, needle):
        self.assertTrue(any(needle in e for e in errors), f"expected an error containing {needle!r}, got {errors}")

    def test_real_data_is_valid(self):
        self.assertEqual(run_checks(*self.fresh()), [])

    def test_realised_inventory(self):
        types = [p["type"] for p in self.pubs]
        # Every record must be one of the rendered sections; nothing silently dropped.
        self.assertEqual(len(types), sum(types.count(t) for t in prerender.PUB_TYPES))
        self.assertTrue(1 <= sum(bool(p.get("featured")) for p in self.pubs) <= prerender.FEATURED_MAX)
        # Every theme used in the filter has at least one publication, so no filter button is empty.
        used = {c for p in self.pubs for c in p.get("categories", [])}
        self.assertEqual(used, set(prerender.THEMES.values()))

    def test_duplicate_id(self):
        pubs, *rest = self.fresh()
        pubs[1]["id"] = pubs[0]["id"]
        self.assertCaught(run_checks(pubs, *rest), "duplicate id")

    def test_unknown_field(self):
        pubs, *rest = self.fresh()
        pubs[0]["jounral"] = "typo"
        self.assertCaught(run_checks(pubs, *rest), "unknown field 'jounral'")

    def test_unknown_category(self):
        pubs, *rest = self.fresh()
        pubs[0]["categories"] = ["Neuroscience"]
        self.assertCaught(run_checks(pubs, *rest), "unknown categories")

    def test_theme_must_match_first_category(self):
        pubs, *rest = self.fresh()
        pubs[0]["theme"] = "data"
        self.assertCaught(run_checks(pubs, *rest), "must be the slug of the first category")

    def test_year_date_mismatch(self):
        pubs, *rest = self.fresh()
        pubs[0]["year"] = pubs[0]["year"] - 1
        self.assertCaught(run_checks(pubs, *rest), "does not match date")

    def test_uppercase_doi(self):
        pubs, *rest = self.fresh()
        pubs[0]["doi"] = pubs[0]["doi"].upper()
        self.assertCaught(run_checks(pubs, *rest), "lowercase")

    def test_duplicate_doi(self):
        pubs, *rest = self.fresh()
        with_doi = [p for p in pubs if p.get("doi")]
        with_doi[1]["doi"] = with_doi[0]["doi"]
        self.assertCaught(run_checks(pubs, *rest), "appears 2 times")

    def test_author_list_without_her(self):
        pubs, *rest = self.fresh()
        pubs[0]["authors"] = ["Someone A", "Else B"]
        self.assertCaught(run_checks(pubs, *rest), "does not include Ruiz-Rizzo")

    def test_featured_needs_summary(self):
        pubs, *rest = self.fresh()
        feat = next(p for p in pubs if p.get("featured"))
        del feat["summary"]
        self.assertCaught(run_checks(pubs, *rest), "featured items need a summary")

    def test_too_many_featured(self):
        pubs, *rest = self.fresh()
        for p in pubs:
            if p.get("doi") and p["type"] == "article":
                p["featured"], p["summary"] = True, "x"
        self.assertCaught(run_checks(pubs, *rest), "featured items; the homepage grid expects")

    def test_em_dash_in_prose(self):
        pubs, *rest = self.fresh()
        pubs[0]["note"] = "a \u2014 b"
        self.assertCaught(run_checks(pubs, *rest), "em dash")

    def test_data_link_without_output_record(self):
        pubs, *rest = self.fresh()
        pubs[0]["data"] = ["https://osf.io/zzzzz/"]
        self.assertCaught(run_checks(pubs, *rest), "has no record in outputs.yml")

    def test_output_related_to_missing_publication(self):
        pubs, outputs, career, recognition = self.fresh()
        outputs[1]["related"] = "no-such-paper"
        self.assertCaught(run_checks(pubs, outputs, career, recognition), "is not a publication id")

    def test_output_relation_must_be_two_way(self):
        pubs, outputs, career, recognition = self.fresh()
        rel = next(o for o in outputs if o.get("related"))
        target = next(p for p in pubs if p["id"] == rel["related"])
        target["data"] = []
        errors = run_checks(pubs, outputs, career, recognition)
        self.assertCaught(errors, "does not list")

    def test_bad_career_kind(self):
        pubs, outputs, career, recognition = self.fresh()
        career[0]["kind"] = "job"
        self.assertCaught(run_checks(pubs, outputs, career, recognition), "kind must be one of")


    def test_unknown_funder(self):
        pubs, outputs, career, recognition = self.fresh()
        recognition[0]["funders"] = ["nsf"]
        self.assertCaught(run_checks(pubs, outputs, career, recognition), "is not defined in funders.yml")

    def test_fellowship_needs_summary(self):
        pubs, outputs, career, recognition = self.fresh()
        fellow = next(r for r in recognition if r.get("fellowship"))
        del fellow["summary"]
        self.assertCaught(run_checks(pubs, outputs, career, recognition), "fellowship entries need a summary")

    def test_missing_logo_file_and_source(self):
        funders = copy.deepcopy(prerender.load("funders.yml"))
        funders[0]["logo"] = "assets/logos/does-not-exist.svg"
        del funders[0]["logo_source"]
        errors = run_checks(*self.fresh(), funders=funders)
        self.assertCaught(errors, "not found")
        self.assertCaught(errors, "a logo needs 'logo_source'")

    def test_eu_emblem_must_come_first(self):
        pubs, outputs, career, recognition = self.fresh()
        lmu = next(r for r in recognition if r["id"] == "lmu-research-fellows")
        lmu["funders"] = ["lmu", "eu-cofunded", "bmbf"]
        self.assertCaught(run_checks(pubs, outputs, career, recognition), "EU emblem must be listed once and first")

    def test_eu_emblem_alt_is_funding_statement(self):
        funders = copy.deepcopy(prerender.load("funders.yml"))
        next(f for f in funders if f["id"] == "eu")["logo_alt"] = "EU flag"
        self.assertCaught(run_checks(*self.fresh(), funders=funders), "alt text must be its funding statement")

    def test_featured_fellowships_present(self):
        recognition = prerender.load("recognition.yml")
        self.assertEqual(sorted(r["id"] for r in recognition if r.get("fellowship")), ["lmu-research-fellows", "msca-phd"])


    def test_amount_must_be_whole_euros_on_funding(self):
        pubs, outputs, career, recognition = self.fresh()
        next(r for r in recognition if r["id"] == "izkf-ams")["amount_eur"] = "150k"
        next(r for r in recognition if r["kind"] == "award")["amount_eur"] = 1000
        errors = run_checks(pubs, outputs, career, recognition)
        self.assertEqual(sum("amount_eur must be" in e for e in errors), 2, errors)


class NewsTalksAndCV(unittest.TestCase):
    """News and talks are hand-written; these checks keep them dated, ordered, short and linked."""

    @classmethod
    def setUpClass(cls):
        cls.pubs = prerender.load("publications.yml")
        cls.news = prerender.load("news.yml")
        cls.talks = prerender.load("talks.yml")

    def errors(self, news=None, talks=None):
        prerender.errors.clear()
        prerender.check_news(copy.deepcopy(self.news) if news is None else news, self.pubs)
        prerender.check_talks(copy.deepcopy(self.talks) if talks is None else talks)
        return list(prerender.errors)

    def assertCaught(self, errors, needle):
        self.assertTrue(any(needle in e for e in errors), f"expected an error containing {needle!r}, got {errors}")

    def test_real_news_and_talks_are_valid(self):
        self.assertEqual(self.errors(), [])
        self.assertGreaterEqual(len(self.news), 3, "the homepage shows three news items")

    def test_out_of_order_news(self):
        news = copy.deepcopy(self.news)
        news[0], news[1] = news[1], news[0]
        self.assertCaught(self.errors(news=news), "newest first")

    def test_month_only_dates_sort_and_display(self):
        self.assertGreater(prerender.news_sort_key("2023-04"), prerender.news_sort_key("2023-03-31"))
        news = copy.deepcopy(self.news)
        news[0]["date"] = "2026-13-01"
        news[1]["date"] = "2026/05/21"
        errors = self.errors(news=news)
        self.assertEqual(sum("date must be" in e for e in errors), 2, errors)

    def test_unknown_category_long_text_and_three_sentences(self):
        news = copy.deepcopy(self.news)
        news[0]["category"] = "Blog"
        news[1]["title"] = "x" * 81
        news[2]["summary"] = "One. Two. Three."
        errors = self.errors(news=news)
        for needle in ("category must be one of", "title is 81 characters", "more than two sentences"):
            self.assertCaught(errors, needle)

    def test_related_publication_and_doi_link(self):
        news = copy.deepcopy(self.news)
        pub_items = [n for n in news if n.get("related")]
        pub_items[0]["related"] = "no-such-paper"
        pub_items[1]["url"] = "https://example.org/paper"
        errors = self.errors(news=news)
        self.assertCaught(errors, "not in publications.yml")
        self.assertCaught(errors, "must be the related publication's DOI link")

    def test_links_must_be_https_or_existing_pages(self):
        news, talks = copy.deepcopy(self.news), copy.deepcopy(self.talks)
        news[-1]["url"] = "missing.qmd#x"
        talks[1]["links"][0]["url"] = "http://insecure.example.org"
        talks[2]["links"] = [{"label": "", "url": "https://example.org"}]
        errors = self.errors(news=news, talks=talks)
        self.assertCaught(errors, "points to a missing page")
        self.assertCaught(errors, "must be https://")
        self.assertCaught(errors, "needs exactly a label and a url")

    def test_cv_is_the_supplied_pdf(self):
        site_vars = prerender.yaml.safe_load((prerender.ROOT / "_variables.yml").read_text(encoding="utf-8"))
        prerender.errors.clear()
        prerender.check_cv(site_vars)
        self.assertEqual(prerender.errors, [])
        tampered = copy.deepcopy(site_vars)
        tampered["cv"]["sha256"] = "0" * 64
        prerender.check_cv(tampered)
        self.assertCaught(prerender.errors, "differs from the supplied CV")


class CoauthorAggregation(unittest.TestCase):
    def pub(self, pid, year, authors, typ="article"):
        return {"id": pid, "type": typ, "year": year, "authors": authors}

    def test_variants_merge_and_threshold_holds(self):
        pubs = [self.pub("a", 2019, ["Ruiz-Rizzo AL", "Napiórkowski N", "Lopera F"]),
                self.pub("b", 2020, ["Napiorkowski N", "Ruiz-Rizzo AL", "Lopera Restrepo F"]),
                self.pub("c", 2024, ["Ruiz Rizzo AL", "Napiórkowski N", "Once O", "Lopera F"])]
        got = {c["as_published"]: c for c in prerender.compute_coauthors(pubs, {"Lopera Restrepo F": "Lopera F"})}
        self.assertEqual(set(got), {"Napiórkowski N", "Lopera F"})        # accent variant and alias joined
        self.assertEqual(got["Lopera F"]["joint"], 3)
        self.assertNotIn("Once O", got)                                       # below threshold
        self.assertFalse(any(k.startswith("Ruiz") for k in got))              # never lists herself

    def test_status_and_types(self):
        pubs = [self.pub(str(i), y, ["Ruiz-Rizzo AL", "Old O"]) for i, y in enumerate((2010, 2011, 2012))]
        pubs += [self.pub(f"n{i}", 2023, ["Ruiz-Rizzo AL", "New N"]) for i in range(3)]
        pubs += [self.pub(f"x{i}", 2025, ["Ruiz-Rizzo AL", "Abstract A"], typ="abstract") for i in range(3)]
        got = {c["as_published"]: c["status"] for c in prerender.compute_coauthors(pubs, {})}
        self.assertEqual(got, {"Old O": "previous", "New N": "current"})      # abstracts do not count

    def test_real_data_counts_each_paper_once_per_person(self):
        pubs = prerender.load("publications.yml")
        for c in prerender.compute_coauthors(pubs, {"Lopera Restrepo F": "Lopera F"}):
            n_papers = sum(1 for p in pubs if p["type"] in prerender.COAUTHOR_TYPES
                           and any(prerender.coauthor_key(a) == prerender.coauthor_key(c["as_published"])
                                   or a == "Lopera Restrepo F" and c["as_published"] == "Lopera F"
                                   for a in p.get("authors") or []))
            self.assertEqual(c["joint"], n_papers, c["name"])


class SharePreviews(unittest.TestCase):
    URL = check_site.SITE_URL + "/research.html"

    def page(self, extra="", drop=()):
        tags = {
            "description": '<meta name="description" content="D">',
            "og:title": '<meta property="og:title" content="T">',
            "og:description": '<meta property="og:description" content="D">',
            "og:image": f'<meta property="og:image" content="{check_site.SITE_URL}/assets/social/research.png">',
            "og:image:alt": '<meta property="og:image:alt" content="A">',
            "og:image:type": '<meta property="og:image:type" content="image/png">',
            "og:image:width": '<meta property="og:image:width" content="1200">',
            "og:image:height": '<meta property="og:image:height" content="630">',
            "og:type": '<meta property="og:type" content="website">',
            "og:site_name": '<meta property="og:site_name" content="S">',
            "og:locale": '<meta property="og:locale" content="en_US">',
            "og:url": f'<meta property="og:url" content="{self.URL}">',
            "canonical": f'<link rel="canonical" href="{self.URL}">',
            "twitter:card": '<meta name="twitter:card" content="summary_large_image">',
            "twitter:title": '<meta name="twitter:title" content="T">',
            "twitter:description": '<meta name="twitter:description" content="D">',
            "twitter:image": f'<meta name="twitter:image" content="{check_site.SITE_URL}/assets/social/research.png">',
            "twitter:image:alt": '<meta name="twitter:image:alt" content="A">',
        }
        p = check_site.Page()
        p.feed("<head>" + "".join(v for k, v in tags.items() if k not in drop) + extra + "</head>")
        return p

    def errs(self, page, noindex=False):
        # The image-exists check needs a rendered site; ignore it in these unit tests.
        return [e for e in check_site.check_share_meta(page, self.URL, noindex) if "does not exist" not in e]

    def test_complete_page_passes(self):
        self.assertEqual(self.errs(self.page()), [])

    def test_missing_og_url_and_canonical(self):
        errs = self.errs(self.page(drop=("og:url", "canonical")))
        self.assertTrue(any("og:url" in e for e in errs) and any("canonical" in e for e in errs), errs)

    def test_duplicate_tag(self):
        errs = self.errs(self.page(extra='<meta property="og:title" content="Other">'))
        self.assertTrue(any("og:title: expected exactly one" in e for e in errs), errs)

    def test_twitter_must_match_og(self):
        p = self.page(drop=("twitter:title",), extra='<meta name="twitter:title" content="Different">')
        self.assertTrue(any("og:title and twitter:title differ" in e for e in self.errs(p)))

    def test_relative_image_rejected(self):
        p = self.page(drop=("og:image", "twitter:image"),
                      extra='<meta property="og:image" content="assets/social/research.png"><meta name="twitter:image" content="assets/social/research.png">')
        self.assertTrue(any("absolute URL" in e for e in self.errs(p)))

    def test_noindex_page_rules(self):
        errs = self.errs(self.page(), noindex=True)
        self.assertTrue(any("robots" in e for e in errs) and any("must not declare a canonical" in e for e in errs), errs)

    def test_png_size_reads_header(self):
        self.assertEqual(prerender.png_size(prerender.ROOT / "assets" / "social" / "index.png"), prerender.CARD_SIZE)

    def test_real_cards_are_current(self):
        prerender.errors.clear()
        prerender.check_share_cards()
        self.assertEqual(prerender.errors, [])

    def test_stale_card_detected(self):
        import make_social_cards
        original = make_social_cards.card_text
        make_social_cards.card_text = lambda page: dict(original(page), title="Renamed page")
        try:
            prerender.errors.clear()
            prerender.check_share_cards()
            self.assertTrue(any("preview card is stale" in e for e in prerender.errors), prerender.errors)
        finally:
            make_social_cards.card_text = original
            prerender.errors.clear()


class ProfilesFooter(unittest.TestCase):
    def setUp(self):
        self.profiles = copy.deepcopy(prerender.load("profiles.yml"))
        prerender.errors.clear()

    def tearDown(self):
        prerender.errors.clear()

    def test_real_profiles_and_footer_in_sync(self):
        prerender.check_profiles(self.profiles)
        self.assertEqual(prerender.errors, [])

    def test_footer_out_of_sync_detected(self):
        self.profiles[0]["name"] = "Mail"
        prerender.check_profiles(self.profiles)
        self.assertTrue(any("out of sync" in e for e in prerender.errors), prerender.errors)

    def test_url_must_match_variables(self):
        next(p for p in self.profiles if p["id"] == "github")["url"] = "https://github.com/someone-else"
        prerender.check_profiles(self.profiles)
        self.assertTrue(any("differs from _variables.yml" in e for e in prerender.errors), prerender.errors)

    def test_missing_icon_detected(self):
        self.profiles[1]["icon"] = "bluesky"
        prerender.check_profiles(self.profiles)
        self.assertTrue(any("icon file assets/icons/bluesky.svg not found" in e for e in prerender.errors))
        self.assertTrue(any("no .rr-icon-bluesky rule" in e for e in prerender.errors))

    def test_footer_names_stay_visible_and_icons_hidden_from_readers(self):
        html = prerender.footer_html(self.profiles)
        self.assertEqual(html.count('aria-hidden="true"'), len(self.profiles))
        self.assertEqual(html.count('class="rr-social-name"'), len(self.profiles))


class HeroMotif(unittest.TestCase):
    def test_generated_motif_is_current_and_decorative(self):
        import tempfile
        import make_motif
        path = prerender.ROOT / "_hero-motif.md"
        committed = path.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            make_motif.OUT = Path(tmp) / "_hero-motif.md"
            make_motif.main()
            regenerated = make_motif.OUT.read_text(encoding="utf-8")
        self.assertEqual(committed, regenerated, "run python3 scripts/make_motif.py")
        self.assertIn('aria-hidden="true" focusable="false"', committed)
        self.assertEqual(committed.count('class="rr-signal"'), make_motif.N_SIGNALS)


class BibTeXExport(unittest.TestCase):
    def test_one_entry_per_record_with_unique_keys(self):
        pubs = prerender.load("publications.yml")
        entries = [prerender.to_bibtex(p) for p in pubs]
        keys = [e.split("{", 1)[1].split(",", 1)[0] for e in entries]
        self.assertEqual(len(keys), len(pubs))
        self.assertEqual(len(set(keys)), len(keys))

    def test_entry_types_and_escaping(self):
        rec = {"id": "x-2020-y", "type": "chapter", "title": "A & B", "year": 2020, "venue": "In: Methods",
               "authors": ["Ruiz-Rizzo AL"], "pages": "1-2"}
        bib = prerender.to_bibtex(rec)
        self.assertTrue(bib.startswith("@incollection{x-2020-y,"))
        self.assertIn(r"A \& B", bib)
        self.assertIn("booktitle = {Methods}", bib)
        self.assertIn("pages = {1--2}", bib)
        self.assertIn("author = {Ruiz-Rizzo, A. L.}", bib)


class SiteCheckHelpers(unittest.TestCase):
    def test_count_in_listing_stays_inside_its_container(self):
        html = ('<main><div id="listing-a"><article class="rr-pub x"></article><article class="rr-pub"></article></div>'
                '<div id="listing-b"><article class="rr-pub"></article></div></main>')
        self.assertEqual(check_site.count_in_listing(html, "listing-a", "rr-pub"), 2)
        self.assertEqual(check_site.count_in_listing(html, "listing-b", "rr-pub"), 1)
        self.assertEqual(check_site.count_in_listing(html, "listing-missing", "rr-pub"), -1)

    def test_class_match_is_exact_token(self):
        html = '<div id="listing-a"><div class="rr-pubs"></div><div class="rr-pub"></div></div></main>'
        self.assertEqual(check_site.count_in_listing(html, "listing-a", "rr-pub"), 1)


if __name__ == "__main__":
    unittest.main()
