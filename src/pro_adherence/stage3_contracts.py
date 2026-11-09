"""Stage 3 planning-only, synthetic-testable contracts (NO model or graph training).

This module never downloads scientific records, loads transformer weights, trains
node2vec, or publishes private data. All scientific choices are supplied explicitly.
The frozen 57,293-group Stage 2 release remains authoritative on private Drive.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import math
import re


class Stage3ContractError(ValueError):
    """Refuse an implicit scientific parameter, invented link or lost provenance."""


SHA256 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_REFERENCE_STATUS = {"exact_doi", "ambiguous_doi", "unresolved"}
FROZEN_STAGE2_ZIP_SHA256 = (
    "a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127"
)


def _unique_index(rows: list[dict], key: str, label: str) -> dict:
    result = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise Stage3ContractError(f"{label}: missing {key}")
        if value in result:
            raise Stage3ContractError(f"{label}: duplicate {key}={value}")
        result[value] = row
    return result


def _exact_coverage(label: str, mapping: dict, ids: set[str]) -> None:
    if set(mapping) != ids:
        raise Stage3ContractError(
            f"{label}: missing={len(ids - set(mapping))} extra={len(set(mapping) - ids)}"
        )


def freeze_snapshot_contract(snapshot: dict) -> dict:
    """Preflight the *accepted* private Stage2 identity; no input bytes are read."""
    expected = {
        "archive_sha256": FROZEN_STAGE2_ZIP_SHA256,
        "source_record_count": 87511,
        "canonical_article_count": 57293,
    }
    for key, val in expected.items():
        if snapshot.get(key) != val:
            raise Stage3ContractError(f"Stage2 snapshot mismatch: {key}")
    if snapshot.get("access_class") != "restricted":
        raise Stage3ContractError("Stage2 is restricted, not a public corpus")
    return dict(expected, access_class="restricted")


def validate_model_readiness(lens: str, specification: dict) -> None:
    """Fail closed until owner scientific choices and immutable weights are pinned.

    A technically valid specification is not an authorization to run inference.
    The calling code must separately check the Stage gate / owner permission.
    """
    if lens not in {"pubmedbert", "specter2", "node2vec"}:
        raise Stage3ContractError("unknown Stage3 lens")
    if specification.get("scientific_parameters_status") != "owner_approved":
        raise Stage3ContractError("scientific parameters not owner-approved")
    if not SHA256.fullmatch(str(specification.get("config_sha256", ""))):
        raise Stage3ContractError("missing immutable scientific config SHA")
    if lens == "pubmedbert":
        # Owner decision (2026-11-09): MetSyn reproducibility is NOT a scientific
        # requirement for Pro_Adherence. Pooling/segmentation and other choices
        # are methodological variables; they must be recorded and approved
        # independently, not inherited as unexamined defaults from MetSyn.
        for name in (
            "methodology_decision_ref", "model_ref_id", "model_identity_hash",
            "tokenizer_identity", "title_abstract_format", "pooling",
            "normalization", "max_length", "overflow_policy",
        ):
            if specification.get(name) is None or specification.get(name) == "":
                raise Stage3ContractError(f"unresolved PubMedBERT methodology: {name}")
        if not SHA256.fullmatch(str(specification["model_identity_hash"])):
            raise Stage3ContractError("unverified PubMedBERT model identity")
        # Owner's 2026-11-09 decisions; do not broaden the scientific scope.
        chosen = {
            "pretraining_corpus": "pubmed_abstracts",
            "embedding_dimension": 768,
            "layer_selection": "last_hidden",
            "title_abstract_format": "title_sep_abstract",
            "max_length": 512,
            "overflow_policy": "fragmented",
            "fine_tuning": False,
        }
        for name, approved_value in chosen.items():
            if name not in specification or specification[name] != approved_value:
                raise Stage3ContractError(f"PubMedBERT owner decision mismatch: {name}")
        if specification["pooling"] not in ("cls_last_hidden", "masked_mean_last_hidden"):
            raise Stage3ContractError("PubMedBERT pooling must be CLS or masked mean")
        # Both choices are authorised as distinct variants, NOT an arbitrary
        # concatenation or a forced choice between them.
        # Multi-fragment article aggregation is a further scientific variable,
        # not specified by choosing a 512-token fragment size.
        if specification.get("fragment_aggregation") in (None, ""):
            raise Stage3ContractError("PubMedBERT multi-fragment aggregation is still undecided")
        if specification.get("special_tokens_policy") in (None, ""):
            raise Stage3ContractError("PubMedBERT special-token pooling policy is undecided")
    elif lens == "specter2":
        for name in ("base_model_ref", "base_model_identity_hash",
                     "adapter_ref", "adapter_identity_hash",
                     "model_identity_hash", "tokenizer_identity",
                     "input_format", "max_length"):
            if specification.get(name) in (None, ""):
                raise Stage3ContractError(f"unresolved SPECTER2 {name}")
        for name in ("base_model_identity_hash", "adapter_identity_hash", "model_identity_hash"):
            if not SHA256.fullmatch(str(specification[name])):
                raise Stage3ContractError(f"invalid SPECTER2 {name}")
    else:
        for name in ("graph_snapshot_sha256", "model_ref_id", "model_identity_hash",
                     "walk_length", "walks_per_node", "window",
                     "dimension", "p", "q", "seed", "isolate_policy"):
            if specification.get(name) is None:
                raise Stage3ContractError(f"unresolved node2vec {name}")
        if not SHA256.fullmatch(str(specification["graph_snapshot_sha256"])):
            raise Stage3ContractError("node2vec graph not pinned")
        if not SHA256.fullmatch(str(specification["model_identity_hash"])):
            raise Stage3ContractError("node2vec model identity not pinned")


def plan_text_inputs(
    canonical_articles: list[dict],
    source_records: list[dict],
    source_choice: dict[str, str],
    eligibility: dict[str, bool],
    *,
    permitted_missing_states: set[str],
) -> list[dict]:
    """Require explicit *per-article* scientific choices: never auto-pick a text.

    The returned rows may contain licensed titles/abstracts: private storage only.
    Text hash represents the selected raw fields, not the not-yet-pinned
    PubMedBERT/SPECTER2 tokenizer concatenation.
    """
    articles = _unique_index(canonical_articles, "canonical_article_id", "canonical")
    sources = _unique_index(source_records, "source_record_id", "source")
    ids = set(articles)
    _exact_coverage("eligibility", eligibility, ids)
    _exact_coverage("source choices", source_choice, ids)
    if permitted_missing_states not in (
        {"both"}, {"both", "title_only"}, {"both", "title_only", "abstract_only"},
    ):
        raise Stage3ContractError("missing-text policy is not explicitly allowed")
    out = []
    for article_id in sorted(ids):
        article = articles[article_id]
        selected = source_choice[article_id]
        if not isinstance(eligibility[article_id], bool):
            raise Stage3ContractError("eligibility must be an explicit boolean")
        if selected not in article.get("source_record_ids", []):
            raise Stage3ContractError(f"source choice not in canonical group {article_id}")
        raw = sources.get(selected)
        if raw is None:
            raise Stage3ContractError(f"missing chosen source record {selected}")
        title = raw.get("title") or ""
        abstract = raw.get("abstract") or ""
        if not isinstance(title, str) or not isinstance(abstract, str):
            raise Stage3ContractError("invalid source title/abstract")
        state = ("both" if title.strip() and abstract.strip() else
                 "title_only" if title.strip() else
                 "abstract_only" if abstract.strip() else "missing_both")
        eligible = eligibility[article_id]
        status = ("excluded_by_policy" if not eligible else
                  "ready" if state in permitted_missing_states else
                  "missing_input")
        payload = json.dumps([title, abstract], ensure_ascii=False, separators=(",", ":")).encode("utf8")
        out.append({
            "article_id": article_id,
            "source_record_id": selected,
            "source_record_ids": sorted(article["source_record_ids"]),
            "text_fields_sha256": sha256(payload).hexdigest(),
            "title": title, "abstract": abstract,
            "text_state": state, "embedding_input_status": status,
            "access_class": "restricted",
        })
    return out


def plan_citation_graph(
    canonical_articles: list[dict],
    source_records: list[dict],
    citation_links: list[dict],
    eligibility: dict[str, bool],
    *,
    graph_policy: dict,
) -> dict:
    """Create an observed candidate graph with complete source evidence pointers.

    No training. Exact DOI links only; APA missing references and ambiguous DOIs
    are not turned into artificial edges. No scientific graph policy is defaulted.
    """
    articles = _unique_index(canonical_articles, "canonical_article_id", "canonical")
    sources = _unique_index(source_records, "source_record_id", "source")
    ids = set(articles)
    _exact_coverage("eligibility", eligibility, ids)
    if any(not isinstance(x, bool) for x in eligibility.values()):
        raise Stage3ContractError("eligibility must be boolean")
    if set(graph_policy) != {"orientation", "duplicate_policy", "self_loop_policy"}:
        raise Stage3ContractError("explicit graph policy required, without hidden defaults")
    if graph_policy["orientation"] not in {"directed", "undirected"}:
        raise Stage3ContractError("graph orientation not approved")
    if graph_policy["duplicate_policy"] not in {"binary", "observation_count"}:
        raise Stage3ContractError("graph duplication policy not approved")
    if graph_policy["self_loop_policy"] not in {"retain", "exclude"}:
        raise Stage3ContractError("self-loop policy not approved")
    source_to_article: dict[str, str] = {}
    for article_id, article in articles.items():
        for sid in article.get("source_record_ids", []):
            if sid in source_to_article or sid not in sources:
                raise Stage3ContractError("duplicate/missing source member")
            source_to_article[sid] = article_id
    if set(source_to_article) != set(sources):
        raise Stage3ContractError("source mapping incomplete")
    status_counts = Counter()
    excluded_edges = Counter()
    edges = Counter()
    evidence_by_edge: dict[tuple[str, str], list[dict]] = {}
    seen_refs: set[tuple[str, int]] = set()
    for link in citation_links:
        status = link.get("resolution_method")
        if status not in ALLOWED_REFERENCE_STATUS:
            raise Stage3ContractError("unknown citation-resolution status")
        status_counts[status] += 1
        source_id = link.get("citing_source_record_id")
        if source_id not in source_to_article:
            raise Stage3ContractError("citing record has no canonical article")
        source = sources[source_id]
        ordinal = link.get("raw_reference_ordinal")
        pointer = link.get("raw_evidence_pointer")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
            raise Stage3ContractError("invalid raw reference ordinal")
        if (not isinstance(pointer, dict)
            or pointer.get("export_sha256") != source.get("raw_export_sha256")
            or not SHA256.fullmatch(str(pointer.get("export_sha256", "")))
            or pointer.get("record_ordinal") != source.get("raw_record_ordinal")
            or pointer.get("reference_ordinal") != ordinal):
            raise Stage3ContractError("citation source provenance does not match original record")
        references = source.get("cited_references_raw")
        if not isinstance(references, list) or ordinal > len(references):
            raise Stage3ContractError("citation is not observed in source reference list")
        if source.get("reference_coverage") == "not_exposed":
            raise Stage3ContractError("fabricated reference from not_exposed source")
        key = (source_id, ordinal)
        if key in seen_refs:
            raise Stage3ContractError("duplicate source reference identity")
        seen_refs.add(key)
        target = link.get("cited_article_id")
        if status != "exact_doi":
            if target is not None:
                raise Stage3ContractError("unresolved/ambiguous citation has invented target")
            continue
        if target is None or target not in articles:
            raise Stage3ContractError("exact DOI target not present in frozen article roster")
        source_article = source_to_article[source_id]
        if not eligibility[source_article] or not eligibility[target]:
            excluded_edges["excluded_policy"] += 1
            continue
        if source_article == target and graph_policy["self_loop_policy"] == "exclude":
            excluded_edges["self_loop_policy"] += 1
            continue
        pair = (source_article, target)
        if graph_policy["orientation"] == "undirected":
            pair = tuple(sorted(pair))
        edges[pair] += 1
        evidence_by_edge.setdefault(pair, []).append({
            "source_record_id": source_id,
            "raw_reference_ordinal": ordinal,
            "export_sha256": pointer["export_sha256"],
            "record_ordinal": pointer["record_ordinal"],
        })
    rows = [
        {"source_article_id": left, "target_article_id": right,
         "observation_count": count,
         "weight": count if graph_policy["duplicate_policy"] == "observation_count" else 1,
         "evidence_pointers": sorted(evidence_by_edge[(left, right)],
             key=lambda p: (p["source_record_id"], p["raw_reference_ordinal"]))}
        for (left, right), count in sorted(edges.items())
    ]
    adjacent: set[str] = set()
    for left, right in edges:
        adjacent.update((left, right))
    node_rows = []
    for article_id, article in sorted(articles.items()):
        coverage = sorted({
            sources[sid].get("reference_coverage", "unknown")
            for sid in article["source_record_ids"]
        })
        observed = article_id in adjacent
        outgoing_observed = any(s in ("exposed", "incomplete") for s in coverage)
        node_rows.append({
            "article_id": article_id,
            "eligible": eligibility[article_id],
            "reference_coverage": coverage,
            "has_observed_resolved_edge": observed,
            "isolate_reason": (None if observed else
                "excluded_by_policy" if not eligibility[article_id] else
                "missing_reference_coverage" if not outgoing_observed else
                "no_resolved_observed_edge"),
        })
    return {
        "article_count": len(ids),
        "eligible_article_count": sum(eligibility.values()),
        "citation_status_counts": dict(sorted(status_counts.items())),
        "excluded_edge_observations": dict(sorted(excluded_edges.items())),
        "graph_policy": dict(graph_policy),
        "nodes": node_rows,
        "edges": rows,
        "edge_count": len(rows),
        "edge_observation_count": sum(edges.values()),
        "access_class": "restricted",
    }


def validate_vector_rows(
    canonical_article_ids: list[str], vector_rows: list[dict], *,
    dimension: int, model_identity_hash: str
) -> dict:
    """Ensure missing inputs are explicit, never replaced by fabricated zeros."""
    if not isinstance(dimension, int) or dimension < 1:
        raise Stage3ContractError("invalid embedding dimension")
    if not SHA256.fullmatch(model_identity_hash):
        raise Stage3ContractError("model identity missing")
    if len(set(canonical_article_ids)) != len(canonical_article_ids):
        raise Stage3ContractError("duplicate canonical roster")
    rows = _unique_index(vector_rows, "article_id", "vectors")
    _exact_coverage("vector roster including missing statuses", rows, set(canonical_article_ids))
    counts = Counter()
    for row in vector_rows:
        state = row.get("status")
        if state not in {"present", "missing_input", "missing_structural", "excluded_by_policy"}:
            raise Stage3ContractError("unknown vector status")
        counts[state] += 1
        if row.get("model_identity_hash") != model_identity_hash:
            raise Stage3ContractError("model identity drift")
        vector = row.get("vector")
        if state != "present":
            if vector is not None:
                raise Stage3ContractError("missing vector must be null, not a fake value")
            continue
        if not isinstance(vector, (list, tuple)) or len(vector) != dimension:
            raise Stage3ContractError("embedding has wrong dimension")
        if any(not isinstance(value, (int, float)) or isinstance(value, bool)
               or not math.isfinite(value) for value in vector):
            raise Stage3ContractError("embedding contains invalid/nonfinite values")
    return {"article_count": len(rows), "dimension": dimension,
            "status_counts": dict(sorted(counts.items())),
            "model_identity_hash": model_identity_hash}
