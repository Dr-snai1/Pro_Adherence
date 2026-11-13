"""Strictly bounded <=1% private graph streaming preflight; never full node2vec.

This invokes the accepted frozen graph parser/1% start selector/Word2Vec
implementation. Uses re-iterable walks rather than materialized walk lists.
Outputs aggregate diagnostics only; no article IDs, model, graph rows or vectors.
"""
from __future__ import annotations

if not __debug__:
    raise SystemExit("Python assertions (-O forbidden) for private graph verification")

import argparse
import json
import os
from pathlib import Path
import resource
import time

import numpy as np
import gensim

import stage3_node2vec_cpu_smoke as bounded


def run_bounded_stream_probe(graph: Path) -> dict:
    assert bounded.MAX_START_NODES == 436
    assert bounded.WALKS_PER_NODE == 10 and bounded.WALK_LENGTH == 40
    assert bounded.N_NODES == 57204 and bounded.N_EDGES == 328298
    assert bounded.N_ISOLATES == 13596
    start = time.monotonic()
    degrees, offsets, adj = bounded.secure_load(graph)
    graph_load_seconds = time.monotonic() - start
    assert np.count_nonzero(degrees > 0) == 43608
    starts, strata = bounded.choose_starts(degrees)
    assert len(starts) == bounded.MAX_START_NODES

    # Re-opening creates the identical sequence for Gensim vocab/train passes.
    stream = bounded.RepeatableWalkCorpus(starts, offsets, adj, bounded.SEED)
    start = time.monotonic()
    sha1 = bounded.walk_digest(stream)
    sha2 = bounded.walk_digest(stream)
    assert sha1 == sha2
    assert sum(1 for _ in stream) == 4360
    stream_replay_seconds = time.monotonic() - start

    start = time.monotonic()
    model = bounded.train(stream, bounded.SEED)  # strictly 4,360 walks, never 436,080
    bounded_fit_seconds = time.monotonic() - start
    digest = bounded.vectors_digest(model)
    assert len(model.wv) <= bounded.N_NODES - bounded.N_ISOLATES
    assert model.wv.vector_size == bounded.DIM
    assert np.isfinite(model.wv.vectors).all()
    assert model.sg == bounded.SG and model.hs == bounded.HS
    assert model.negative == bounded.NEGATIVE and model.sample == bounded.SAMPLE
    return {
        "schema": "pro-adherence-stage3-node2vec-bounded-stream-readiness/v1",
        "status": "BOUNDED_STREAM_TECHNICAL_PROBE_NOT_PRODUCTION",
        "graph_zip_sha256": bounded.GRAPH_SHA,
        "scope": {
            "real_graph_nodes": bounded.N_NODES,
            "full_graph_unique_undirected_edges": bounded.N_EDGES,
            "nonisolated_nodes": 43608,
            "isolates": bounded.N_ISOLATES,
            "degree_strata_populations": strata,
            "pilot_starts": 436,
            "pilot_walks": 4360,
            "pilot_tokens": 174400,
            "nominal_full_walks_not_generated": 436080,
            "pilot_vocab": len(model.wv),
            "private_article_ids_or_vectors_saved": False
        },
        "fixed_backend": {
            "dimension": bounded.DIM, "p": 1, "q": 1,
            "walk_length": bounded.WALK_LENGTH,
            "walks_per_node": bounded.WALKS_PER_NODE,
            "context_window": bounded.WINDOW,
            "epochs": bounded.EPOCHS,
            "seed": bounded.SEED, "workers": bounded.WORKERS,
            "sg": model.sg, "hs": model.hs,
            "negative": model.negative, "sample": model.sample
        },
        "replay": {
            "same_seed_walk_sha256_pass": sha1 == sha2,
            "walk_sha256": sha1,
            "diagnostic_pilot_vector_sha256": digest
        },
        "resource": {
            "python": os.sys.version.split()[0],
            "gensim": gensim.__version__,
            "numpy": np.__version__,
            "graph_load_seconds": round(graph_load_seconds, 3),
            "three_stream_pass_seconds": round(stream_replay_seconds, 3),
            "bounded_fit_seconds": round(bounded_fit_seconds, 3),
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        },
        "gates": {
            "full_scale_time_measured": False,
            "full_scale_ram_measured": False,
            "owner_full_training_permission": False,
            "production_embeddings_generated": False,
            "publication_authorized": False
        }
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        raise SystemExit("refuse overwrite of preflight report")
    report = run_bounded_stream_probe(args.graph)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("BOUNDED_STREAM_PROBE_PASS_NOT_FULL_TRAINING")


if __name__ == "__main__":
    main()
