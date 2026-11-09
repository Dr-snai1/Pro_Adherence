"""Stage3 synthetic contracts: no private corpus, no models, no external calls."""
from __future__ import annotations

from copy import deepcopy
import unittest

from pro_adherence.stage3_contracts import (
    FROZEN_STAGE2_ZIP_SHA256,
    Stage3ContractError,
    freeze_snapshot_contract,
    plan_citation_graph,
    plan_text_inputs,
    validate_model_readiness,
    validate_vector_rows,
)

HASH = "a" * 64

ARTICLES = [
    {"canonical_article_id": "article:A", "source_record_ids": ["pubmed:101"]},
    {"canonical_article_id": "article:B", "source_record_ids": ["apa_psycinfo:AN-202"]},
    {"canonical_article_id": "article:C", "source_record_ids": ["woscc:WOS:303"]},
]
SOURCES = [
    {"source_record_id": "pubmed:101", "title": "Medication adherence",
     "abstract": "Synthetic adherence study", "record_family": "journal"},
    {"source_record_id": "apa_psycinfo:AN-202", "title": "Pill taking", "abstract": None,
     "record_family": "journal", "reference_coverage": "not_exposed"},
    {"source_record_id": "woscc:WOS:303", "title": None, "abstract": None,
     "record_family": "journal", "reference_coverage": "incomplete"},
]
ELIGIBILITY = {"article:A": True, "article:B": True, "article:C": True}
CHOICES = {"article:A": "pubmed:101", "article:B": "apa_psycinfo:AN-202",
           "article:C": "woscc:WOS:303"}
POLICY = {"orientation": "directed", "duplicate_policy": "binary",
          "self_loop_policy": "exclude"}
REFERENCES = [
    {"citing_source_record_id": "woscc:WOS:303", "cited_article_id": "article:A",
     "resolution_method": "exact_doi"},
    {"citing_source_record_id": "woscc:WOS:303", "cited_article_id": "article:A",
     "resolution_method": "exact_doi"},
    {"citing_source_record_id": "woscc:WOS:303", "cited_article_id": None,
     "resolution_method": "ambiguous_doi", "external_target_doi": "10.1234/shared"},
    {"citing_source_record_id": "woscc:WOS:303", "cited_article_id": None,
     "resolution_method": "unresolved"},
]


class Stage3PlanningContractTests(unittest.TestCase):
    def test_frozen_stage2_identity_is_required(self):
        snap = {"archive_sha256": FROZEN_STAGE2_ZIP_SHA256,
                "source_record_count": 87511, "canonical_article_count": 57293,
                "access_class": "restricted"}
        self.assertEqual(freeze_snapshot_contract(snap)["canonical_article_count"], 57293)
        for bad_key, value in (("archive_sha256", HASH),
                               ("source_record_count", 87510),
                               ("access_class", "public")):
            with self.subTest(bad_key=bad_key):
                with self.assertRaises(Stage3ContractError):
                    freeze_snapshot_contract(dict(snap, **{bad_key: value}))

    def test_text_sources_are_owner_selected_and_missing_is_explicit(self):
        x = plan_text_inputs(ARTICLES, SOURCES, CHOICES, ELIGIBILITY,
                             permitted_missing_states={"both", "title_only"})
        self.assertEqual([r["embedding_input_status"] for r in x],
                         ["ready", "ready", "missing_input"])
        self.assertEqual([r["text_state"] for r in x],
                         ["both", "title_only", "missing_both"])
        self.assertEqual(x[1]["source_record_id"], "apa_psycinfo:AN-202")
        self.assertEqual(x[2]["access_class"], "restricted")
        self.assertEqual(
            [r["text_fields_sha256"] for r in x],
            [r["text_fields_sha256"] for r in
             plan_text_inputs(list(reversed(ARTICLES)), list(reversed(SOURCES)),
                              CHOICES, ELIGIBILITY,
                              permitted_missing_states={"both", "title_only"})],
        )
        with self.assertRaises(Stage3ContractError):
            plan_text_inputs(ARTICLES, SOURCES, {}, ELIGIBILITY,
                             permitted_missing_states={"both"})
        with self.assertRaises(Stage3ContractError):
            plan_text_inputs(ARTICLES, SOURCES, {**CHOICES, "article:A": "woscc:WOS:303"},
                             ELIGIBILITY, permitted_missing_states={"both"})
        with self.assertRaises(Stage3ContractError):
            plan_text_inputs(ARTICLES, SOURCES, CHOICES, ELIGIBILITY,
                             permitted_missing_states={"title_only"})

    def test_citation_graph_never_invents_ambiguous_target_or_absent_apa_links(self):
        result = plan_citation_graph(ARTICLES, SOURCES, REFERENCES, ELIGIBILITY,
                                     graph_policy=POLICY)
        self.assertEqual(result["edge_count"], 1)
        self.assertEqual(result["edge_observation_count"], 2)
        self.assertEqual(result["edges"][0]["source_article_id"], "article:C")
        self.assertEqual(result["edges"][0]["target_article_id"], "article:A")
        self.assertEqual(result["edges"][0]["weight"], 1)
        self.assertEqual(result["citation_status_counts"],
                         {"ambiguous_doi": 1, "exact_doi": 2, "unresolved": 1})
        self.assertEqual(result["article_count"], 3)
        alternate = plan_citation_graph(
            list(reversed(ARTICLES)), list(reversed(SOURCES)),
            list(reversed(REFERENCES)), ELIGIBILITY, graph_policy=POLICY)
        self.assertEqual(result, alternate)
        counted = plan_citation_graph(
            ARTICLES, SOURCES, REFERENCES, ELIGIBILITY,
            graph_policy={**POLICY, "duplicate_policy": "observation_count"})
        self.assertEqual(counted["edges"][0]["weight"], 2)

        bad = deepcopy(REFERENCES)
        bad[2]["cited_article_id"] = "article:A"
        with self.assertRaises(Stage3ContractError):
            plan_citation_graph(ARTICLES, SOURCES, bad, ELIGIBILITY, graph_policy=POLICY)
        with self.assertRaises(Stage3ContractError):
            plan_citation_graph(ARTICLES, SOURCES, REFERENCES, ELIGIBILITY,
                                 graph_policy={"orientation": "directed"})

    def test_graph_checks_exact_link_target_and_roster(self):
        bad = deepcopy(REFERENCES)
        bad[0]["cited_article_id"] = "article:D"
        with self.assertRaises(Stage3ContractError):
            plan_citation_graph(ARTICLES, SOURCES, bad, ELIGIBILITY, graph_policy=POLICY)
        bad = deepcopy(SOURCES)
        bad.append(dict(SOURCES[0]))
        with self.assertRaises(Stage3ContractError):
            plan_citation_graph(ARTICLES, bad, REFERENCES, ELIGIBILITY, graph_policy=POLICY)

    def test_vector_absence_not_zero_and_all_articles_accounted_for(self):
        rows = [
            {"article_id": "article:A", "status": "present", "vector": [1., 2., 3.],
             "model_identity_hash": HASH},
            {"article_id": "article:B", "status": "missing_input", "vector": None,
             "model_identity_hash": HASH},
            {"article_id": "article:C", "status": "missing_structural", "vector": None,
             "model_identity_hash": HASH},
        ]
        v = validate_vector_rows(["article:A", "article:B", "article:C"], rows,
                                 dimension=3, model_identity_hash=HASH)
        self.assertEqual(v["status_counts"]["missing_structural"], 1)
        changed = deepcopy(rows)
        changed[1]["vector"] = [0., 0., 0.]
        with self.assertRaises(Stage3ContractError):
            validate_vector_rows(["article:A", "article:B", "article:C"], changed,
                                 dimension=3, model_identity_hash=HASH)
        changed = deepcopy(rows)
        changed[0]["vector"] = [1., float("nan"), 3.]
        with self.assertRaises(Stage3ContractError):
            validate_vector_rows(["article:A", "article:B", "article:C"], changed,
                                 dimension=3, model_identity_hash=HASH)
        with self.assertRaises(Stage3ContractError):
            validate_vector_rows(["article:A", "article:B", "article:C"], rows[:2],
                                 dimension=3, model_identity_hash=HASH)

    def test_no_implicit_pooled_pubmedbert_or_unpinned_specter2(self):
        for lens in ("pubmedbert", "specter2", "node2vec"):
            with self.subTest(lens=lens):
                with self.assertRaisesRegex(Stage3ContractError, "not owner-approved"):
                    validate_model_readiness(lens, {"scientific_parameters_status": "pending"})
        with self.assertRaisesRegex(Stage3ContractError, "metsyn_code_sha256"):
            validate_model_readiness("pubmedbert", {
                "scientific_parameters_status": "owner_approved", "config_sha256": HASH})
        with self.assertRaisesRegex(Stage3ContractError, "adapter_ref"):
            validate_model_readiness("specter2", {
                "scientific_parameters_status": "owner_approved",
                "config_sha256": HASH,
                "base_model_ref": "official-pinned-ref",
                "base_model_identity_hash": HASH,
            })
        with self.assertRaisesRegex(Stage3ContractError, "graph_snapshot_sha256"):
            validate_model_readiness("node2vec", {
                "scientific_parameters_status": "owner_approved", "config_sha256": HASH})

if __name__ == "__main__":
    unittest.main()
