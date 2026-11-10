"""Stage3 synthetic contracts: no private corpus, no models, no external calls."""
from __future__ import annotations

from copy import deepcopy
import unittest

from pro_adherence.stage3_contracts import (
    FROZEN_STAGE2_ZIP_SHA256,
    Stage3ContractError,
    freeze_snapshot_contract,
    plan_citation_graph,
    plan_approved_node2vec_graph,
    plan_stage3_canonical_eligibility,
    normalize_stage3_source_flags,
    preserve_node2vec_article_vector,
    plan_text_inputs,
    choose_pubmedbert_source_priority,
    plan_pubmedbert_text_inputs,
    plan_specter2_text_inputs,
    summarize_specter2_truncation,
    preserve_specter2_article_vector,
    validate_model_readiness,
    validate_vector_rows,
    aggregate_weighted_fragments,
    summarize_long_abstract_coverage,
    pack_sentence_token_groups,
    mean_pooling_content_mask,
    summarize_pubmedbert_text_coverage,
    preserve_raw_and_l2_article_vector,
)

HASH = "a" * 64

ARTICLES = [
    {"canonical_article_id": "article:A", "source_record_ids": ["pubmed:101"]},
    {"canonical_article_id": "article:B", "source_record_ids": ["apa_psycinfo:AN-202"]},
    {"canonical_article_id": "article:C", "source_record_ids": ["woscc:WOS:303"]},
]
SOURCES = [
    {"source_record_id": "pubmed:101", "title": "Medication adherence",
     "abstract": "Synthetic adherence study", "record_family": "journal",
     "raw_export_sha256": "b" * 64, "raw_record_ordinal": 1,
     "cited_references_raw": [], "reference_coverage": "unknown"},
    {"source_record_id": "apa_psycinfo:AN-202", "title": "Pill taking", "abstract": None,
     "record_family": "journal", "reference_coverage": "not_exposed",
     "raw_export_sha256": "c" * 64, "raw_record_ordinal": 2,
     "cited_references_raw": []},
    {"source_record_id": "woscc:WOS:303", "title": None, "abstract": None,
     "record_family": "journal", "reference_coverage": "incomplete",
     "raw_export_sha256": "d" * 64, "raw_record_ordinal": 3,
     "cited_references_raw": ["synthetic ref 1", "synthetic ref 2",
                              "synthetic ref 3", "synthetic ref 4"]},
]
ELIGIBILITY = {"article:A": True, "article:B": True, "article:C": True}
CHOICES = {"article:A": "pubmed:101", "article:B": "apa_psycinfo:AN-202",
           "article:C": "woscc:WOS:303"}
POLICY = {"orientation": "directed", "duplicate_policy": "binary",
          "self_loop_policy": "exclude"}

def observed_reference(ordinal, method, target):
    return {
        "citing_source_record_id": "woscc:WOS:303",
        "cited_article_id": target,
        "resolution_method": method,
        "raw_reference_ordinal": ordinal,
        "raw_evidence_pointer": {
            "export_sha256": "d" * 64,
            "record_ordinal": 3,
            "reference_ordinal": ordinal,
        },
    }

REFERENCES = [
    observed_reference(1, "exact_doi", "article:A"),
    observed_reference(2, "exact_doi", "article:A"),
    observed_reference(3, "ambiguous_doi", None),
    observed_reference(4, "unresolved", None),
]
REFERENCES[2]["external_target_doi"] = "10.1234/shared"

class Stage3PlanningContractTests(unittest.TestCase):
    def test_owner_approved_canonical_publication_eligibility(self):
        articles = [
            {"canonical_article_id": "a", "source_record_ids": ["pubmed:book", "woscc:journal"]},
            {"canonical_article_id": "b", "source_record_ids": ["pubmed:book_only"]},
            {"canonical_article_id": "c", "source_record_ids": ["apa_psycinfo:retracted"]},
            {"canonical_article_id": "d", "source_record_ids": ["apa_psycinfo:unknown_peer"]},
            {"canonical_article_id": "e", "source_record_ids": ["woscc:nrcr"]},
            {"canonical_article_id": "f", "source_record_ids": ["woscc:unknown_family"]},
            {"canonical_article_id": "g", "source_record_ids": ["woscc:ordinary"]},
        ]
        sources = [
            {"source_record_id": "pubmed:book", "record_family": "book"},
            {"source_record_id": "woscc:journal", "record_family": "journal"},
            {"source_record_id": "pubmed:book_only", "record_family": "book"},
            {"source_record_id": "apa_psycinfo:retracted", "record_family": "journal",
             "is_retracted": True},
            {"source_record_id": "apa_psycinfo:unknown_peer", "record_family": "journal",
             "peer_review_unknown": True},
            {"source_record_id": "woscc:nrcr", "record_family": "journal",
             "wos_nr_cr_mismatch": True},
            {"source_record_id": "woscc:unknown_family", "record_family": "unknown"},
            {"source_record_id": "woscc:ordinary", "record_family": "journal"},
        ]
        sources = [
            {**{"is_retracted": False, "peer_review_unknown": False,
                "wos_nr_cr_mismatch": False}, **row} for row in sources
        ]
        output = plan_stage3_canonical_eligibility(articles, sources)
        statuses = {row["article_id"]: row["eligibility_status"] for row in output["rows"]}
        self.assertEqual(statuses, {
            "a": "eligible_journal", "b": "excluded_book_only",
            "c": "excluded_retracted", "d": "eligible_journal",
            "e": "eligible_journal", "f": "requires_family_resolution",
            "g": "eligible_journal",
        })
        self.assertEqual(output["primary_eligible_count"], 4)
        self.assertEqual(output["article_count"], 7)
        self.assertEqual(output["source_record_count"], 8)
        self.assertEqual(output["canonical_flag_counts"]["mixed_book_journal"], 1)
        self.assertEqual(output["canonical_flag_counts"]["retracted"], 1)
        self.assertEqual(output["canonical_flag_counts"]["peer_review_unknown"], 1)
        self.assertEqual(output["canonical_flag_counts"]["wos_nr_cr_mismatch"], 1)
        self.assertEqual(output["source_flag_counts"]["is_retracted"], 1)
        self.assertTrue(output["eligibility_by_article_id"]["a"])
        self.assertFalse(output["eligibility_by_article_id"]["b"])
        self.assertEqual(
            output, plan_stage3_canonical_eligibility(
                list(reversed(articles)), list(reversed(sources))))
        with self.assertRaisesRegex(Stage3ContractError, "tri-state source flag required"):
            bad = deepcopy(sources)
            del bad[0]["is_retracted"]
            plan_stage3_canonical_eligibility(articles, bad)
        with self.assertRaisesRegex(Stage3ContractError, "record_family required"):
            bad = deepcopy(sources)
            bad[0]["record_family"] = None
            plan_stage3_canonical_eligibility(articles, bad)
        with self.assertRaisesRegex(Stage3ContractError, "source member coverage"):
            plan_stage3_canonical_eligibility(
                articles,
                sources + [{
                    "source_record_id": "woscc:unassigned",
                    "record_family": "journal", "is_retracted": False,
                    "peer_review_unknown": False, "wos_nr_cr_mismatch": False,
                }])
        with self.assertRaisesRegex(Stage3ContractError, "duplicate canonical source assignment"):
            bad = deepcopy(articles)
            bad[1]["source_record_ids"].append("pubmed:book")
            plan_stage3_canonical_eligibility(bad, sources)

    def test_real_stage2_flag_schema_missing_is_not_exposed(self):
        h = "a" * 64
        raw = [
            {
                "source_id": "pubmed", "source_record_id": "pubmed:1",
                "record_family": "book", "raw_export_sha256": h,
                "raw_record_ordinal": 1,
            },
            {
                "source_id": "woscc", "source_record_id": "woscc:2",
                "record_family": "journal", "raw_export_sha256": h,
                "raw_record_ordinal": 2, "cited_references_count_anomaly": True,
            },
            {
                "source_id": "apa_psycinfo", "source_record_id": "apa_psycinfo:3",
                "record_family": "journal", "raw_export_sha256": h,
                "raw_record_ordinal": 3, "retracted_article": False,
                "peer_review_unknown": True,
            },
        ]
        normalized = normalize_stage3_source_flags(raw)
        self.assertIsNone(normalized[0]["is_retracted"])
        self.assertIsNone(normalized[0]["peer_review_unknown"])
        self.assertIsNone(normalized[1]["is_retracted"])
        self.assertTrue(normalized[1]["wos_nr_cr_mismatch"])
        self.assertIsNone(normalized[2]["wos_nr_cr_mismatch"])
        self.assertFalse(normalized[2]["is_retracted"])
        article = [
            {"canonical_article_id": "pubmed_only", "source_record_ids": ["pubmed:1"]},
            {"canonical_article_id": "wos_only", "source_record_ids": ["woscc:2"]},
            {"canonical_article_id": "apa_only", "source_record_ids": ["apa_psycinfo:3"]},
        ]
        census = plan_stage3_canonical_eligibility(article, normalized)
        self.assertEqual(census["primary_eligible_count"], 2)
        self.assertEqual(census["source_flag_counts"]["is_retracted_not_exposed"], 2)
        self.assertEqual(census["source_flag_counts"]["peer_review_unknown_not_exposed"], 2)
        self.assertEqual(census["source_flag_counts"]["wos_nr_cr_mismatch_not_exposed"], 2)
        self.assertEqual(census["source_flag_counts"]["peer_review_unknown"], 1)
        self.assertEqual(census["source_flag_counts"]["wos_nr_cr_mismatch"], 1)
        self.assertEqual(census["rows"][0]["source_evidence"][0]["raw_export_sha256"], h)
        bad = deepcopy(raw)
        del bad[2]["retracted_article"]
        with self.assertRaisesRegex(Stage3ContractError, "missing declared Stage2"):
            normalize_stage3_source_flags(bad)
        bad = deepcopy(raw)
        bad[1]["cited_references_count_anomaly"] = "unknown"
        with self.assertRaisesRegex(Stage3ContractError, "invalid Stage2 flag"):
            normalize_stage3_source_flags(bad)
        bad = deepcopy(raw)
        bad[0]["raw_record_ordinal"] = None
        with self.assertRaisesRegex(Stage3ContractError, "raw record ordinal"):
            normalize_stage3_source_flags(bad)
        # Unexpected but explicitly exposed positive retraction must propagate.
        positive = deepcopy(raw)
        positive[1]["retracted_article"] = True
        normalized_positive = normalize_stage3_source_flags(positive)
        self.assertTrue(normalized_positive[1]["is_retracted"])

    def test_private_census_manifest_writer_is_deterministic_and_restricted(self):
        from hashlib import sha256
        import importlib.util
        import json
        import gzip
        import os
        from pathlib import Path
        import tempfile
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "stage3_eligibility_census.py"
        spec = importlib.util.spec_from_file_location("stage3_census_script", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rows = [
            {"article_id": "article:1", "primary_eligible": True,
             "eligibility_status": "eligible_journal"},
            {"article_id": "article:2", "primary_eligible": False,
             "eligibility_status": "excluded_retracted"},
        ]
        census = {
            "rows": rows, "article_count": 2,
            "primary_eligible_count": 1,
            "eligibility_by_article_id": {
                "article:1": True, "article:2": False,
            },
            "eligibility_status_counts": {
                "eligible_journal": 1, "excluded_retracted": 1,
            },
            "source_flag_counts": {"is_retracted": 1},
            "input_archive_sha256": HASH,
            "policy_id": mod.POLICY_ID,
        }
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "restricted"
            out = mod.write_private_artifacts(census, private)
            file = private / out["derived_manifest_file"]
            self.assertEqual(out["derived_manifest_row_count"], 2)
            self.assertEqual(sha256(file.read_bytes()).hexdigest(),
                             out["derived_manifest_sha256"])
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(private.stat().st_mode & 0o777, 0o700)
            self.assertFalse(out["publication_authorized"])
            self.assertEqual(out["access_class"], "restricted")
            self.assertEqual(
                json.loads((private / "eligibility_summary.json").read_text())["derived_manifest_sha256"],
                out["derived_manifest_sha256"])
            with gzip.open(file, "rt", encoding="utf8") as stream:
                actual_rows = [json.loads(line) for line in stream]
            self.assertEqual(len(actual_rows), 2)
            self.assertEqual(actual_rows[0]["article_id"], "article:1")
            self.assertEqual(actual_rows[1]["article_id"], "article:2")
            self.assertEqual(actual_rows[0]["policy_id"], mod.POLICY_ID)
            self.assertEqual(file.read_bytes()[4:8], b"\x00\x00\x00\x00")  # gzip mtime=0
            again = mod.write_private_artifacts(census, private)
            self.assertEqual(again["derived_manifest_sha256"], out["derived_manifest_sha256"])

    def test_excluded_publications_remain_in_original_directed_citation_graph(self):
        eligible = {"article:A": False, "article:B": True, "article:C": True}
        graph = plan_approved_node2vec_graph(
            ARTICLES, SOURCES, REFERENCES, eligible)
        original = graph["directed_citation_graph"]
        training = graph["node2vec_training_graph"]
        self.assertEqual(original["edge_observation_count"], 2)
        self.assertEqual(original["edge_count"], 1)
        self.assertEqual(training["edge_observation_count"], 0)
        self.assertEqual(training["edge_count"], 0)
        self.assertEqual(training["excluded_edge_observations"]["excluded_policy"], 2)
        self.assertTrue(original["edges"][0]["source_article_id"] == "article:C")
        self.assertTrue(original["edges"][0]["target_article_id"] == "article:A")

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
        self.assertEqual([r["title_only_vector"] for r in x],
                         [False, True, False])
        self.assertEqual(x[1]["abstract_available_source_record_ids"], [])
        coverage = summarize_pubmedbert_text_coverage(x, canonical_total=3)
        self.assertEqual(coverage["title_only_count"], 1)
        self.assertAlmostEqual(coverage["title_only_pct_canonical"], 33.3333, places=3)
        self.assertEqual(coverage["title_only_pct_ready"], 50.0)
        self.assertEqual(coverage["status_counts"]["missing_input"], 1)
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

    def test_alt_source_abstract_prevents_unjustified_title_only(self):
        sources = SOURCES + [{
            "source_record_id": "woscc:WOS:202",
            "title": "Pill taking", "abstract": "Alternate synthetic abstract"
        }]
        articles = deepcopy(ARTICLES)
        articles[1]["source_record_ids"].append("woscc:WOS:202")
        rows = plan_text_inputs(articles, sources, CHOICES, ELIGIBILITY,
                                permitted_missing_states={"both", "title_only"})
        self.assertEqual(rows[1]["embedding_input_status"],
                         "requires_source_resolution")
        self.assertFalse(rows[1]["title_only_vector"])
        self.assertEqual(rows[1]["abstract_available_source_record_ids"],
                         ["woscc:WOS:202"])
        report = summarize_pubmedbert_text_coverage(rows, canonical_total=3)
        self.assertEqual(report["title_only_count"], 0)
        self.assertEqual(report["status_counts"]["requires_source_resolution"], 1)
        chosen_alt = {**CHOICES, "article:B": "woscc:WOS:202"}
        ready = plan_text_inputs(articles, sources, chosen_alt, ELIGIBILITY,
                                 permitted_missing_states={"both", "title_only"})
        self.assertEqual(ready[1]["embedding_input_status"], "ready")
        self.assertEqual(ready[1]["text_state"], "both")
        self.assertFalse(ready[1]["title_only_vector"])
        altered = deepcopy(ready)
        altered[1]["title_only_vector"] = True
        with self.assertRaisesRegex(Stage3ContractError, "incorrect title-only"):
            summarize_pubmedbert_text_coverage(altered, canonical_total=3)
        with self.assertRaisesRegex(Stage3ContractError, "full canonical roster"):
            summarize_pubmedbert_text_coverage(ready[:2], canonical_total=3)

    def test_pubmed_wos_apa_priority_and_complete_abstract_fallback(self):
        articles = [
            {"canonical_article_id": "x", "source_record_ids": [
                "apa_psycinfo:3", "woscc:2", "pubmed:1"]},
            {"canonical_article_id": "y", "source_record_ids": [
                "apa_psycinfo:4", "pubmed:5", "woscc:6"]},
            {"canonical_article_id": "z", "source_record_ids": [
                "apa_psycinfo:7", "woscc:8", "pubmed:9"]},
        ]
        sources = [
            {"source_record_id": "pubmed:1", "title": "PubMed full",
             "abstract": "Full abstract"},
            {"source_record_id": "woscc:2", "title": "WoS full",
             "abstract": "Full abstract"},
            {"source_record_id": "apa_psycinfo:3", "title": "APA full",
             "abstract": "Full abstract"},
            {"source_record_id": "apa_psycinfo:4", "title": "APA full",
             "abstract": "Full abstract"},
            {"source_record_id": "pubmed:5", "title": "PubMed title",
             "abstract": ""},
            {"source_record_id": "woscc:6", "title": "WoS full",
             "abstract": "Full abstract"},
            {"source_record_id": "apa_psycinfo:7", "title": "APA title",
             "abstract": ""},
            {"source_record_id": "woscc:8", "title": "WoS title",
             "abstract": ""},
            {"source_record_id": "pubmed:9", "title": "PubMed title",
             "abstract": ""},
        ]
        choices = choose_pubmedbert_source_priority(articles, sources)
        self.assertEqual(choices, {"x": "pubmed:1", "y": "woscc:6",
                                   "z": "pubmed:9"})
        self.assertEqual(choices, choose_pubmedbert_source_priority(
            list(reversed(articles)), list(reversed(sources))))
        planned = plan_pubmedbert_text_inputs(
            articles, sources, {x: True for x in choices})
        self.assertEqual([x["text_state"] for x in planned],
                         ["both", "both", "title_only"])
        self.assertEqual([x["title_only_vector"] for x in planned],
                         [False, False, True])
        # If only an abstract survives in a different source, do not
        # fabricate a merged title + abstract from two databases.
        sources[6]["title"] = ""
        sources[6]["abstract"] = "APA abstract"
        choices = choose_pubmedbert_source_priority(articles, sources)
        self.assertEqual(choices["z"], "pubmed:9")
        planned = plan_text_inputs(articles, sources, choices,
                                   {x: True for x in choices},
                                   permitted_missing_states={"both", "title_only"})
        self.assertEqual(planned[2]["embedding_input_status"],
                         "requires_source_resolution")
        with self.assertRaisesRegex(Stage3ContractError, "unsupported"):
            choose_pubmedbert_source_priority(
                [{"canonical_article_id": "q",
                  "source_record_ids": ["other:q"]}],
                [{"source_record_id": "other:q", "title": "Title",
                  "abstract": "Abstract"}])

    def test_raw_vector_norm_and_unit_vector_retained_without_overwriting(self):
        import math
        raw = [3.0, 4.0, 0.0]
        result = preserve_raw_and_l2_article_vector(raw, dimension=3)
        self.assertEqual(result["raw_article_vector"], raw)
        self.assertEqual(raw, [3.0, 4.0, 0.0])
        self.assertEqual(result["raw_l2_norm"], 5.0)
        self.assertEqual(result["unit_article_vector"], [0.6, 0.8, 0.0])
        self.assertAlmostEqual(math.hypot(*result["unit_article_vector"]), 1.0)
        self.assertEqual(result["similarity_metric"], "cosine")
        for bad in ([0.0, 0.0, 0.0], [float("nan"), 1.0, 0.0],
                    [3.0, 4.0], [float("inf"), 0.0, 0.0]):
            with self.subTest(raw=bad):
                with self.assertRaises(Stage3ContractError):
                    preserve_raw_and_l2_article_vector(bad, dimension=3)
        with self.assertRaises(Stage3ContractError):
            preserve_raw_and_l2_article_vector([True, 2.0, 3.0], dimension=3)

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
        self.assertEqual(len(result["edges"][0]["evidence_pointers"]), 2)
        self.assertEqual(result["nodes"][1]["isolate_reason"], "missing_reference_coverage")
        self.assertIsNone(result["nodes"][0]["isolate_reason"])
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

    def test_citation_graph_requires_raw_byte_provenance_and_source_observation(self):
        bad = deepcopy(REFERENCES)
        bad[0]["raw_evidence_pointer"]["export_sha256"] = "0" * 64
        with self.assertRaisesRegex(Stage3ContractError, "provenance"):
            plan_citation_graph(ARTICLES, SOURCES, bad, ELIGIBILITY, graph_policy=POLICY)
        bad = deepcopy(REFERENCES)
        bad[1]["raw_reference_ordinal"] = 1
        with self.assertRaises(Stage3ContractError):
            plan_citation_graph(ARTICLES, SOURCES, bad, ELIGIBILITY, graph_policy=POLICY)
        no_export = deepcopy(SOURCES)
        no_export[2]["reference_coverage"] = "not_exposed"
        with self.assertRaisesRegex(Stage3ContractError, "fabricated reference"):
            plan_citation_graph(ARTICLES, no_export, REFERENCES, ELIGIBILITY,
                                graph_policy=POLICY)

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
        with self.assertRaisesRegex(Stage3ContractError, "methodology_decision_ref"):
            validate_model_readiness("pubmedbert", {
                "scientific_parameters_status": "owner_approved", "config_sha256": HASH})
        # Synthetic demonstration only: no MetSyn execution files are required.
        # The owner must still approve actual settings before real computation.
        pubmedbert = {
            "scientific_parameters_status": "owner_approved",
            "config_sha256": HASH, "methodology_decision_ref": "synthetic-choice",
            "model_ref_id": "synthetic-biomedbert",
            "model_identity_hash": HASH, "tokenizer_identity": "synthetic-tokenizer",
            "title_abstract_format": "title_sep_abstract",
            "pooling": "masked_mean_last_hidden",
            "normalization": "l2_after_article_aggregation",
            "similarity_metric": "cosine", "raw_vector_retention": True,
            "max_length": 512, "overflow_policy": "fragmented",
            "pretraining_corpus": "pubmed_abstracts",
            "embedding_dimension": 768, "layer_selection": "last_hidden",
            "fine_tuning": False,
            "fragment_aggregation": "content_token_weighted_mean",
            "special_tokens_policy": "exclude_all_special_and_padding",
        }
        for variant in ("cls_last_hidden", "masked_mean_last_hidden"):
            with self.subTest(pooling=variant):
                self.assertIsNone(validate_model_readiness(
                    "pubmedbert", {**pubmedbert, "pooling": variant}))
        for field, bad in (
            ("pooling", "max_pooling"),
            ("pretraining_corpus", "pubmed_abstracts_plus_fulltext"),
            ("embedding_dimension", 1024),
            ("layer_selection", "middle"),
            ("title_abstract_format", "plain_concat"),
            ("max_length", 256),
            ("overflow_policy", "truncate"),
            ("fine_tuning", True),
            ("normalization", "l2_before_fragment_aggregation"),
            ("similarity_metric", "euclidean"),
            ("raw_vector_retention", False),
        ):
            with self.subTest(field=field):
                with self.assertRaises(Stage3ContractError):
                    validate_model_readiness("pubmedbert", {**pubmedbert, field: bad})
        with self.assertRaisesRegex(Stage3ContractError, "fragment"):
            validate_model_readiness("pubmedbert", {
                **pubmedbert, "fragment_aggregation": None})
        with self.assertRaisesRegex(Stage3ContractError, "token-weighted"):
            validate_model_readiness("pubmedbert", {
                **pubmedbert, "fragment_aggregation": "equal_mean"})
        with self.assertRaisesRegex(Stage3ContractError, "all special"):
            validate_model_readiness("pubmedbert", {
                **pubmedbert, "special_tokens_policy": None})
        with self.assertRaisesRegex(Stage3ContractError, "all special"):
            validate_model_readiness("pubmedbert", {
                **pubmedbert, "special_tokens_policy": "include_cls_sep"})
        # SPECTER2 now fails earlier on the missing immutable base revision.
        with self.assertRaisesRegex(Stage3ContractError, "base_model_revision"):
            validate_model_readiness("specter2", {
                "scientific_parameters_status": "owner_approved",
                "config_sha256": HASH,
                "base_model_ref": "official-pinned-ref",
                "base_model_identity_hash": HASH,
            })
        with self.assertRaisesRegex(Stage3ContractError, "graph_snapshot_sha256"):
            validate_model_readiness("node2vec", {
                "scientific_parameters_status": "owner_approved", "config_sha256": HASH})

    def test_owner_approved_specter2_proximity_configuration(self):
        revision = "b" * 40
        spec = {
            "scientific_parameters_status": "owner_approved",
            "config_sha256": HASH,
            "base_model_ref": "allenai/specter2_base",
            "base_model_revision": revision,
            "base_model_identity_hash": HASH,
            "adapter_ref": "allenai/specter2",
            "adapter_revision": revision,
            "adapter_identity_hash": HASH,
            "model_identity_hash": HASH,
            "tokenizer_identity": "synthetic-pinned-tokenizer",
            "tokenizer_revision": revision,
            "adapter_task": "proximity",
            "input_format": "title_sep_abstract",
            "max_length": 512,
            "embedding_dimension": 768,
            "output_pooling": "last_hidden_first_token",
            "overflow_policy": "truncate_512_report_token_loss",
            "text_source_policy": "pubmed_wos_apa_complete_first",
            "title_only_policy": "only_if_no_abstract_in_any_source",
            "normalization": "l2_after_final_article_vector",
            "similarity_metric": "cosine",
            "raw_vector_retention": True,
            "token_loss_report": True,
            "fine_tuning": False,
        }
        validate_model_readiness("specter2", spec)
        for key, value in (
            ("base_model_ref", "allenai/specter2"),
            ("adapter_ref", "allenai/specter2_classification"),
            ("adapter_task", "classification"),
            ("input_format", "title_abstract_plain"),
            ("max_length", 256),
            ("embedding_dimension", 512),
            ("output_pooling", "masked_mean"),
            ("overflow_policy", "fragmented"),
            ("text_source_policy", "wos_first"),
            ("title_only_policy", "never"),
            ("normalization", "none"),
            ("similarity_metric", "euclidean"),
            ("raw_vector_retention", False),
            ("token_loss_report", False),
            ("fine_tuning", True),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaisesRegex(Stage3ContractError, f"mismatch: {key}"):
                    validate_model_readiness("specter2", {**spec, key: value})
        for key in ("base_model_revision", "adapter_revision", "tokenizer_revision"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(Stage3ContractError, "immutable HF revision"):
                    validate_model_readiness("specter2", {**spec, key: "main"})
        for key in ("base_model_identity_hash", "adapter_identity_hash", "model_identity_hash"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(Stage3ContractError, f"invalid SPECTER2 {key}"):
                    validate_model_readiness("specter2", {**spec, key: "not-a-sha"})
        missing = dict(spec)
        del missing["token_loss_report"]
        with self.assertRaisesRegex(Stage3ContractError, "unresolved SPECTER2 token_loss_report"):
            validate_model_readiness("specter2", missing)

    def test_specter2_text_source_and_title_only_policy(self):
        rows = plan_specter2_text_inputs(ARTICLES, SOURCES, ELIGIBILITY)
        self.assertEqual([row["text_state"] for row in rows],
                         ["both", "title_only", "missing_both"])
        self.assertEqual([row["embedding_input_status"] for row in rows],
                         ["ready", "ready", "missing_input"])
        self.assertEqual(rows[1]["source_record_id"], "apa_psycinfo:AN-202")
        self.assertTrue(rows[1]["title_only_vector"])
        self.assertEqual(rows[0]["access_class"], "restricted")
        self.assertEqual(
            rows, plan_specter2_text_inputs(
                list(reversed(ARTICLES)), list(reversed(SOURCES)), ELIGIBILITY))
        sources = deepcopy(SOURCES)
        articles = deepcopy(ARTICLES)
        sources.append({
            "source_record_id": "pubmed:999", "title": "",
            "abstract": "Abstract-only in a different database",
        })
        articles[1]["source_record_ids"].append("pubmed:999")
        conflict = plan_specter2_text_inputs(articles, sources, ELIGIBILITY)
        self.assertEqual(conflict[1]["embedding_input_status"],
                         "requires_source_resolution")
        self.assertFalse(conflict[1]["title_only_vector"])

    def test_specter2_truncation_boundary_and_reporting(self):
        input_rows = plan_specter2_text_inputs(ARTICLES, SOURCES, ELIGIBILITY)
        for row, full in zip(input_rows, (512, 513, None)):
            if full is None:
                continue
            row["full_input_token_count"] = full
            row["encoded_token_count"] = min(512, full)
            row["truncated_token_count"] = max(0, full - 512)
        report = summarize_specter2_truncation(input_rows, canonical_total=3)
        self.assertEqual(report["ready_article_count"], 2)
        self.assertEqual(report["title_only_ready_count"], 1)
        self.assertEqual(report["truncated_article_count"], 1)
        self.assertEqual(report["total_truncated_tokens"], 1)
        self.assertEqual(report["truncated_pct_canonical"], 33.3333)
        self.assertEqual(report["truncated_pct_ready"], 50.0)
        for key, value in (
            ("encoded_token_count", 511),
            ("truncated_token_count", 0),
            ("full_input_token_count", 0),
            ("encoded_token_count", 513),
        ):
            changed = deepcopy(input_rows)
            changed[1][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(Stage3ContractError):
                    summarize_specter2_truncation(changed, canonical_total=3)
        with self.assertRaisesRegex(Stage3ContractError, "full canonical roster"):
            summarize_specter2_truncation(input_rows[:2], canonical_total=3)
        changed = deepcopy(input_rows)
        changed[2]["full_input_token_count"] = 4
        with self.assertRaisesRegex(Stage3ContractError, "non-ready row"):
            summarize_specter2_truncation(changed, canonical_total=3)

    def test_specter2_retains_raw_vector_and_unit_copy(self):
        raw = [0.0] * 768
        raw[0], raw[1] = 3.0, 4.0
        got = preserve_specter2_article_vector(raw)
        self.assertEqual(got["raw_article_vector"], raw)
        self.assertEqual(got["raw_l2_norm"], 5.0)
        self.assertEqual(got["unit_article_vector"][:2], [0.6, 0.8])
        self.assertEqual(got["normalization"], "l2_after_final_article_vector")
        self.assertEqual(got["similarity_metric"], "cosine")
        self.assertEqual(raw[:2], [3.0, 4.0])
        with self.assertRaises(Stage3ContractError):
            preserve_specter2_article_vector([0.0] * 768)
        with self.assertRaises(Stage3ContractError):
            preserve_specter2_article_vector([3.0, 4.0])

    def test_node2vec_approved_p_and_q_are_both_one(self):
        spec = {
            "scientific_parameters_status": "owner_approved",
            "config_sha256": HASH,
            "graph_snapshot_sha256": HASH,
            "model_ref_id": "synthetic-node2vec",
            "model_identity_hash": HASH,
            "walk_length": 40,
            "walks_per_node": 10,
            "window": 10,
            "dimension": 128,
            "p": 1,
            "q": 1,
            "seed": 20261031,
            "isolate_policy": "missing_structural",
            "epochs": 1,
            "graph_orientation": "undirected",
            "source_graph_orientation": "directed",
            "edge_weight_policy": "binary_unique_unordered_pair",
            "self_loop_policy": "exclude",
            "normalization": "l2_after_training",
            "similarity_metric": "cosine",
            "raw_vector_retention": True,
        }
        validate_model_readiness("node2vec", spec)
        for key, value in (
            ("p", 0.5), ("p", 2), ("q", 0.5), ("q", 2),
            ("p", float("nan")), ("q", float("inf")),
            ("p", True), ("q", "1"),
        ):
            with self.subTest(parameter=key, value=value):
                with self.assertRaisesRegex(Stage3ContractError, "requires p=1 and q=1"):
                    validate_model_readiness("node2vec", {**spec, key: value})
        for value in (64, 256, 128.0, True, "128"):
            with self.subTest(dimension=value):
                with self.assertRaisesRegex(Stage3ContractError, "requires dimension=128"):
                    validate_model_readiness("node2vec", {**spec, "dimension": value})
        for key, value in (
            ("walk_length", 80), ("walk_length", "40"),
            ("walks_per_node", 5), ("window", 5), ("epochs", 2),
            ("seed", 1), ("isolate_policy", "fake_zero"),
            ("graph_orientation", "directed"),
            ("source_graph_orientation", "undirected"),
            ("edge_weight_policy", "observation_count"),
            ("self_loop_policy", "retain"),
            ("normalization", "none"), ("similarity_metric", "dot"),
            ("raw_vector_retention", False),
        ):
            with self.subTest(parameter=key, value=value):
                with self.assertRaisesRegex(Stage3ContractError, f"mismatch: {key}"):
                    validate_model_readiness("node2vec", {**spec, key: value})
        for key in ("epochs", "graph_orientation", "raw_vector_retention"):
            with self.subTest(missing=key):
                changed = dict(spec)
                del changed[key]
                with self.assertRaisesRegex(Stage3ContractError, f"unresolved node2vec {key}"):
                    validate_model_readiness("node2vec", changed)

    def test_approved_node2vec_preserves_directed_evidence_and_unit_weights(self):
        g = plan_approved_node2vec_graph(ARTICLES, SOURCES, REFERENCES, ELIGIBILITY)
        directed = g["directed_citation_graph"]
        walks = g["node2vec_training_graph"]
        self.assertEqual(g["source_graph_orientation"], "directed")
        self.assertEqual(g["training_graph_orientation"], "undirected")
        self.assertEqual(directed["edges"][0]["source_article_id"], "article:C")
        self.assertEqual(directed["edges"][0]["target_article_id"], "article:A")
        self.assertEqual(walks["edges"][0]["source_article_id"], "article:A")
        self.assertEqual(walks["edges"][0]["target_article_id"], "article:C")
        self.assertEqual(directed["edge_observation_count"], 2)
        self.assertEqual(walks["edge_observation_count"], 2)
        self.assertEqual(walks["edges"][0]["weight"], 1)
        self.assertEqual(walks["edges"][0]["observation_count"], 2)
        self.assertEqual(g["node2vec_isolate_vector_status"], "missing_structural")
        self.assertEqual(
            plan_approved_node2vec_graph(
                list(reversed(ARTICLES)), list(reversed(SOURCES)),
                list(reversed(REFERENCES)), ELIGIBILITY),
            g)

    def test_node2vec_source_preserves_self_citations_training_excludes_them(self):
        sources = deepcopy(SOURCES)
        sources[2]["cited_references_raw"].append("synthetic self reference")
        links = deepcopy(REFERENCES)
        links.append(observed_reference(5, "exact_doi", "article:C"))
        result = plan_approved_node2vec_graph(
            ARTICLES, sources, links, ELIGIBILITY)
        directed = result["directed_citation_graph"]
        training = result["node2vec_training_graph"]
        self.assertEqual(directed["edge_observation_count"], 3)
        self.assertEqual(training["edge_observation_count"], 2)
        self.assertEqual(
            training["excluded_edge_observations"]["self_loop_policy"], 1)
        self.assertTrue(any(
            edge["source_article_id"] == edge["target_article_id"] == "article:C"
            for edge in directed["edges"]))
        self.assertTrue(all(
            edge["source_article_id"] != edge["target_article_id"]
            for edge in training["edges"]))

    def test_node2vec_vectors_retain_originals_before_l2_cosine(self):
        raw = [0.0] * 128
        raw[0], raw[1] = 3.0, 4.0
        v = preserve_node2vec_article_vector(raw)
        self.assertEqual(v["raw_article_vector"], raw)
        self.assertEqual(v["raw_l2_norm"], 5.0)
        self.assertEqual(v["unit_article_vector"][:2], [0.6, 0.8])
        self.assertEqual(v["normalization"], "l2_after_training")
        self.assertEqual(v["similarity_metric"], "cosine")
        self.assertEqual(raw[:2], [3.0, 4.0])
        with self.assertRaises(Stage3ContractError):
            preserve_node2vec_article_vector([0.0] * 128)
        with self.assertRaises(Stage3ContractError):
            preserve_node2vec_article_vector([3.0, 4.0])


    def test_weighted_fragment_both_pooling_branches_and_reject_loss(self):
        fragments = [
            {"content_start": 0, "content_end": 4, "content_token_count": 4,
             "input_token_count": 6, "vector": [10.0, 20.0]},
            {"content_start": 4, "content_end": 5, "content_token_count": 1,
             "input_token_count": 3, "vector": [0.0, 0.0]},
        ]
        self.assertEqual(
            aggregate_weighted_fragments(fragments, dimension=2), [8.0, 16.0])
        self.assertEqual(
            aggregate_weighted_fragments([
                {**fragments[0], "vector": [4.0, 2.0]},
                {**fragments[1], "vector": [9.0, 7.0]},
            ], dimension=2), [5.0, 3.0])
        with self.assertRaisesRegex(Stage3ContractError, "gap, overlap"):
            aggregate_weighted_fragments([
                fragments[0], {**fragments[1], "content_start": 3}], dimension=2)
        with self.assertRaisesRegex(Stage3ContractError, "token-count mismatch"):
            aggregate_weighted_fragments([
                fragments[0], {**fragments[1], "content_token_count": 2}], dimension=2)
        with self.assertRaisesRegex(Stage3ContractError, "model limit"):
            aggregate_weighted_fragments([
                {**fragments[0], "input_token_count": 513}], dimension=2)
        with self.assertRaisesRegex(Stage3ContractError, "invalid fragment vector"):
            aggregate_weighted_fragments([
                {**fragments[0], "vector": [float("nan"), 0.0]}], dimension=2)

    def test_full_corpus_long_abstract_denominators_and_no_silent_truncation(self):
        rows = [
            dict(article_id="a", eligible=True, has_abstract=True,
                 fragment_count=1, full_input_exceeds_512=False, abstract_tokens_exceeds_512=False,
                 forced_sentence_splits=0, full_content_covered=True),
            dict(article_id="b", eligible=True, has_abstract=True,
                 fragment_count=3, full_input_exceeds_512=True, abstract_tokens_exceeds_512=True,
                 forced_sentence_splits=1, full_content_covered=True),
            dict(article_id="c", eligible=False, has_abstract=False,
                 fragment_count=0, full_input_exceeds_512=False, abstract_tokens_exceeds_512=False,
                 forced_sentence_splits=0, full_content_covered=False),
        ]
        report = summarize_long_abstract_coverage(rows, canonical_total=3)
        self.assertEqual(report["articles_needing_fragments"], 1)
        self.assertEqual(report["abstract_itself_over_512_count"], 1)
        self.assertEqual(report["pct_abstract_itself_over_512_of_eligible_abstracts"], 50.0)
        self.assertAlmostEqual(report["pct_all_canonical"], 33.3333, places=3)
        self.assertEqual(report["pct_eligible_text"], 50.0)
        self.assertEqual(report["pct_eligible_with_abstract"], 50.0)
        title_only = [dict(x) for x in rows]
        title_only[1]["has_abstract"] = False
        title_only[1]["abstract_tokens_exceeds_512"] = False
        report_no_abstract = summarize_long_abstract_coverage(title_only, canonical_total=3)
        self.assertEqual(report_no_abstract["pct_eligible_with_abstract"], 0.0)
        self.assertEqual(report_no_abstract["pct_eligible_text"], 50.0)
        self.assertEqual(report_no_abstract["chunked_articles_with_abstract_count"], 0)
        self.assertEqual(report["fragment_count_histogram"], {"1": 1, "3": 1})
        self.assertEqual(report["forced_sentence_splits_total"], 1)
        with self.assertRaisesRegex(Stage3ContractError, "full canonical roster"):
            summarize_long_abstract_coverage(rows[:2], canonical_total=3)
        bad = [dict(x) for x in rows]
        bad[1]["full_content_covered"] = False
        with self.assertRaisesRegex(Stage3ContractError, "truncated"):
            summarize_long_abstract_coverage(bad, canonical_total=3)
        bad = [dict(x) for x in rows]
        bad[1]["fragment_count"] = 1
        with self.assertRaisesRegex(Stage3ContractError, "chunk count"):
            summarize_long_abstract_coverage(bad, canonical_total=3)

    def test_sentence_boundary_packing_no_loss_and_long_sentence_fallback(self):
        pack = pack_sentence_token_groups(
            [[1, 2], [3, 4, 5], [6, 7], [8, 9, 10, 11, 12]],
            first_content_capacity=5, subsequent_content_capacity=5)
        self.assertEqual(pack["chunks"], [[1, 2, 3, 4, 5], [6, 7], [8, 9, 10, 11, 12]])
        self.assertEqual(pack["forced_sentence_splits"], 0)
        fallback = pack_sentence_token_groups(
            [[1, 2, 3, 4, 5, 6, 7]], first_content_capacity=3,
            subsequent_content_capacity=3)
        self.assertEqual(fallback["chunks"], [[1, 2, 3], [4, 5, 6], [7]])
        self.assertEqual(fallback["forced_sentence_splits"], 1)
        with self.assertRaisesRegex(Stage3ContractError, "chunk capacity"):
            pack_sentence_token_groups([[1, 2]], first_content_capacity=0,
                                       subsequent_content_capacity=2)
        with self.assertRaisesRegex(Stage3ContractError, "sentence token groups"):
            pack_sentence_token_groups([[]], first_content_capacity=2,
                                       subsequent_content_capacity=2)

    def test_mean_mask_excludes_cls_sep_other_special_and_padding(self):
        # CLS, title token, SEP, abstract tokens, SEP, padding, other special.
        mask = mean_pooling_content_mask(
            [1, 1, 1, 1, 1, 1, 0, 1],
            [1, 0, 1, 0, 0, 1, 0, 1])
        self.assertEqual(mask, [0, 1, 0, 1, 1, 0, 0, 0])
        with self.assertRaisesRegex(Stage3ContractError, "no content"):
            mean_pooling_content_mask([1, 1, 0], [1, 1, 0])
        with self.assertRaisesRegex(Stage3ContractError, "invalid content"):
            mean_pooling_content_mask([1, 1], [1])
        with self.assertRaisesRegex(Stage3ContractError, "nonbinary"):
            mean_pooling_content_mask([1, 2], [1, 0])

if __name__ == "__main__":
    unittest.main()
