"""Offline synthetic integration checks: no private source material in Git."""
from pathlib import Path
import tempfile
import unittest

from pro_adherence.stage2_integrate import (
    parse_apa_ris, parse_pubmed_batch, save_private_candidate,
)
from pro_adherence.stage2_sources import reconcile_sources, canonical_json, SourceFormatError


PUBMED = b"""<PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID>1234</PMID>
<Article><ArticleTitle>Adherence study</ArticleTitle>
<AuthorList><Author><LastName>Lee</LastName><ForeName>A</ForeName>
<AffiliationInfo><Affiliation>University A</Affiliation></AffiliationInfo>
</Author></AuthorList></Article></MedlineCitation><PubmedData><ArticleIdList>
<ArticleId IdType="doi">10.1234/a</ArticleId>
</ArticleIdList></PubmedData></PubmedArticle>
<PubmedBookArticle><BookDocument><PMID>4321</PMID><BookTitle>Book title</BookTitle>
</BookDocument><PubmedBookData><ArticleIdList>
<ArticleId IdType="doi">10.5678/book</ArticleId></ArticleIdList></PubmedBookData>
</PubmedBookArticle></PubmedArticleSet>"""

RIS = b"""TY  - JOUR
DB  - APA PsycInfo
AN  - 2026-11111-001
DO  - 10.1234/a
TI  - Adherence study
AU  - Lee, A
N1  - Journal Article
N1  - Retracted Article
ER  -
"""


class ThreeSourceIntegrationTests(unittest.TestCase):
    def test_pubmed_preserves_book_family_and_exact_source(self):
        r = parse_pubmed_batch(PUBMED, "000001.xml")
        self.assertEqual([x["source_native_id"] for x in r], ["1234", "4321"])
        self.assertEqual(r[0]["doi"], "10.1234/a")
        self.assertEqual(r[0]["affiliations_raw"], ["University A"])
        self.assertTrue(r[0]["scientific_article_only_eligible"])
        self.assertFalse(r[1]["scientific_article_only_eligible"])
        self.assertEqual(r[1]["exclusion_reason"], "book_family_not_journal_article")

    def test_apa_preserves_retraction_and_nonobserved_references(self):
        x = parse_apa_ris(RIS)[0]
        self.assertTrue(x["retracted_article"])
        self.assertEqual(x["reference_coverage"], "not_exposed")
        self.assertEqual(x["cited_references_raw"], [])
        with self.assertRaises(SourceFormatError):
            parse_apa_ris(RIS.replace(b"ER  -", b"CR  - possible reference\nER  -"))

    def test_cross_source_exact_merges_are_deterministic_and_conservative(self):
        pm = parse_pubmed_batch(PUBMED, "000001.xml")
        ap = parse_apa_ris(RIS)
        wo = {
            "source_id": "woscc", "source_native_id": "WOS:1",
            "source_record_id": "woscc:WOS:1", "doi": "10.1234/a", "pmid": "1234",
            "title": "Adherence study", "record_family": "journal",
            "cited_references_raw": ["Citation doi 10.5678/book"],
        }
        rows = pm + ap + [wo]
        r = reconcile_sources(rows)
        self.assertEqual(r["source_record_count"], 4)
        self.assertEqual(r["canonical_article_count"], 2)
        self.assertEqual(len(r["citation_links"]), 1)
        self.assertEqual(r["citation_links"][0]["resolution_method"], "exact_doi")
        self.assertEqual(canonical_json(r), canonical_json(reconcile_sources(list(reversed(rows)))))
        book_clone = dict(wo, source_native_id="WOS:2",
                          source_record_id="woscc:WOS:2", doi="10.5678/book", pmid=None)
        other = reconcile_sources(pm + [book_clone])
        self.assertEqual(other["canonical_article_count"], 3)
        self.assertTrue(other["blocked_identity_pairs"])

    def test_staging_rejects_omitted_source_and_is_non_destructive(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SourceFormatError):
                save_private_candidate(parse_pubmed_batch(PUBMED, "000001.xml"), Path(tmp)/"candidate")


if __name__ == "__main__":
    unittest.main()
