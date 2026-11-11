"""Read-only Stage3 pilot capacity planner from VERIFIED graph aggregates.

No model imports, inference, random walks or paid requests. Rates and prices
are optional *measured owner inputs*, NEVER guessed defaults. Computing a
resource proposal does not grant any compute or release permission.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

CORPUS = 57293
ELIGIBLE = 57204
TRAINING_ISOLATES = 13596
TRAINING_EDGES = 328298
DIRECTED_EDGES = 328383
EXACT_DOI = 406811
TRAINING_OBSERVATIONS = 406729
WALK_LENGTH = 40
WALKS_PER_NODE = 10
DIM = 128
SEED = 20261031


def _positive_rate(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be a positive finite measured value")
    from math import isfinite
    if not isfinite(value) or value <= 0:
        raise ValueError(name + " must be positive and finite")
    return float(value)


def capacity_plan(*, pubmedbert_articles_per_s: float | None = None,
                  specter2_articles_per_s: float | None = None,
                  node2vec_tokens_per_s: float | None = None,
                  pubmedbert_price_per_hour: float | None = None,
                  specter2_price_per_hour: float | None = None,
                  node2vec_price_per_hour: float | None = None) -> dict:
    """Approximate workload only; no invented performance or pricing."""
    pubmedbert_articles_per_s = _positive_rate("pubmedbert_articles_per_s",
                                                pubmedbert_articles_per_s)
    specter2_articles_per_s = _positive_rate("specter2_articles_per_s",
                                              specter2_articles_per_s)
    node2vec_tokens_per_s = _positive_rate("node2vec_tokens_per_s",
                                            node2vec_tokens_per_s)
    def checked_price(name, value):
        if value is None:
            return None
        from math import isfinite
        if type(value) not in (int, float) or not isfinite(value) or value < 0:
            raise ValueError(name + " must be a nonnegative finite price")
        return float(value)
    pubmedbert_price_per_hour = checked_price("pubmedbert_price_per_hour", pubmedbert_price_per_hour)
    specter2_price_per_hour = checked_price("specter2_price_per_hour", specter2_price_per_hour)
    node2vec_price_per_hour = checked_price("node2vec_price_per_hour", node2vec_price_per_hour)
    active = ELIGIBLE - TRAINING_ISOLATES
    tokens = active * WALKS_PER_NODE * WALK_LENGTH
    # Across all eligible articles: a generous max, not actual readiness.
    # PubMedBERT CLS and Mean share one encoder pass; 2 storage assets.
    pubmed_storage = ELIGIBLE * 768 * 4 * 2 * 2
    specter_storage = ELIGIBLE * 768 * 4 * 2
    node_storage = active * DIM * 4 * 2
    def projection(work, rate, per_hour):
        if rate is None:
            return {"hours": None, "cost": None, "status": "AWAITING_MEASURED_THROUGHPUT"}
        hours = work / rate / 3600
        return {"hours": hours,
                "cost": None if per_hour is None else hours * per_hour,
                "status": "PROJECTION_NOT_MEASURED_FULL_RUN"}
    return {
        "schema": "pro-adherence-stage3-pilot-capacity/v1",
        "status": "PLANNING_ONLY_NO_INFERENCE_NO_TRAINING",
        "corpus_canonical_count": CORPUS,
        "primary_eligible_count": ELIGIBLE,
        "graph": {
            "directed_unique_edges": DIRECTED_EDGES,
            "training_unique_edges": TRAINING_EDGES,
            "training_observations": TRAINING_OBSERVATIONS,
            "raw_exact_doi_observations": EXACT_DOI,
            "training_isolates": TRAINING_ISOLATES,
            "trainable_nonisolated_nodes": active,
            "minimum_integer_adjacency_endpoint_bytes": 2 * TRAINING_EDGES * 4,
            "node2vec_fixed_parameters": {
                "p": 1, "q": 1, "dimension": DIM, "walk_length": WALK_LENGTH,
                "walks_per_node": WALKS_PER_NODE, "window": 10,
                "epochs": 1, "seed": SEED},
            "walks_nonisolate": active * WALKS_PER_NODE,
            "nominal_nonisolate_walk_tokens": tokens,
            "minimum_uint32_walk_token_bytes": tokens * 4,
            "missing_structural_vector_status": "null",
        },
        "storage_uncompressed_float32_lower_bound_bytes": {
            "pubmedbert_cls_plus_mean_raw_and_unit_upper_coverage": pubmed_storage,
            "specter2_raw_and_unit_upper_coverage": specter_storage,
            "node2vec_raw_and_unit_nonisolated": node_storage,
            "combined_raw_and_unit": pubmed_storage + specter_storage + node_storage,
        },
        "runtime_projections": {
            "pubmedbert_single_encoder_two_poolings": projection(
                ELIGIBLE, pubmedbert_articles_per_s, pubmedbert_price_per_hour),
            "specter2_proximity": projection(ELIGIBLE, specter2_articles_per_s, specter2_price_per_hour),
            "node2vec_walk_generation_only": projection(tokens, node2vec_tokens_per_s, node2vec_price_per_hour),
        },
        "limitations": [
            "PubMedBERT real fragment counts and SPECTER2 real ready count are not measured",
            "Node2vec Word2Vec training time is not inferred from walk generation",
            "Degree skew, Python allocations, tokenizer and optimizer RAM omitted",
            "No memory peak, device benchmark, price quote or safe runtime measured",
            "Float32 sizes exclude raw L2 norms, indices, null metadata, model weights and checkpoints",
            "No extrapolation from an induced subgraph is assumed valid",
        ],
        "pilot_proposal_not_authorization": {
            "pubmedbert": "64 stratified approved articles, validate model/tokenizer/CLS+Mean/fragment policy and stopwatch",
            "specter2": "same 64 articles, proximity adapter activation, 512 truncation/loss, numeric equivalence and stopwatch only after safe runtime",
            "node2vec": "full frozen graph memory/degree preflight then strictly bounded 1% synthetic walk smoke with exact fixed parameters; no full training",
            "quality": "two checks: source/lineage reconciliation and independent numerical/byte readback",
            "owner_gate": "Approve separate finite pilot run and maximum spend only after runtime and model integrity checks",
        },
        "owner_compute_authorized": False,
        "public_release_authorized": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pubmedbert-articles-per-s", type=float)
    p.add_argument("--specter2-articles-per-s", type=float)
    p.add_argument("--node2vec-tokens-per-s", type=float)
    p.add_argument("--pubmedbert-price-per-hour", type=float)
    p.add_argument("--specter2-price-per-hour", type=float)
    p.add_argument("--node2vec-price-per-hour", type=float)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = capacity_plan(
        pubmedbert_articles_per_s=args.pubmedbert_articles_per_s,
        specter2_articles_per_s=args.specter2_articles_per_s,
        node2vec_tokens_per_s=args.node2vec_tokens_per_s,
        pubmedbert_price_per_hour=args.pubmedbert_price_per_hour,
        specter2_price_per_hour=args.specter2_price_per_hour,
        node2vec_price_per_hour=args.node2vec_price_per_hour,
    )
    content = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise ValueError("do not overwrite a previous capacity estimate")
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
