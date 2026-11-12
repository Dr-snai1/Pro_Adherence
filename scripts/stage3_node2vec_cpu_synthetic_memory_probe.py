"""Synthetic full-vocabulary CPU memory pressure probe; <=1% token budget.

No private graph, no scientific embeddings and no real-data training.
The real full run is never triggered by this script.
"""
from __future__ import annotations

if not __debug__:
    raise SystemExit("Python assertions (-O forbidden) for node2vec gate")

import argparse
import json
import os
from pathlib import Path
import resource
import time

import numpy as np

import stage3_node2vec_cpu_smoke as approved

FULL_NONISOLATE_VOCAB = 43608
MAX_WALKS = 4360
TOKENS_PER_WALK = 40
MAX_TOKENS = 174400


class SyntheticFullVocabularyCorpus:
    """Re-iterable deterministic synthetic tokens, not citation walks."""
    def __iter__(self):
        for walk_index in range(MAX_WALKS):
            yield [str((walk_index * TOKENS_PER_WALK + i) % FULL_NONISOLATE_VOCAB)
                   for i in range(TOKENS_PER_WALK)]


def run_probe() -> dict:
    assert FULL_NONISOLATE_VOCAB == approved.N_NODES - approved.N_ISOLATES
    assert MAX_WALKS * TOKENS_PER_WALK == MAX_TOKENS
    assert approved.MAX_START_NODES * approved.WALKS_PER_NODE == MAX_WALKS
    assert approved.NEGATIVE == 5 and approved.SAMPLE == 0.001
    assert approved.SG == 1 and approved.HS == 0
    started = time.monotonic()
    model = approved.train(SyntheticFullVocabularyCorpus(), approved.SEED)
    elapsed = time.monotonic() - started
    assert len(model.wv) == FULL_NONISOLATE_VOCAB
    assert model.wv.vectors.shape == (FULL_NONISOLATE_VOCAB, approved.DIM)
    assert np.isfinite(model.wv.vectors).all()
    return {
        "schema": "pro-adherence-node2vec-synthetic-vocab-memory-probe/v1",
        "status": "SYNTHETIC_ONE_PERCENT_TOKENS_NOT_PRIVATE_GRAPH_NOT_FULL_TRAINING",
        "scope": {
            "vocabulary": FULL_NONISOLATE_VOCAB,
            "synthetic_walks": MAX_WALKS,
            "synthetic_tokens": MAX_TOKENS,
            "private_graph_loaded": False,
            "private_article_ids_or_vectors_saved": False,
        },
        "backend": {
            "dimensions": approved.DIM,
            "sg": approved.SG,
            "hs": approved.HS,
            "negative": model.negative,
            "sample": model.sample,
            "seed": approved.SEED,
            "workers": approved.WORKERS,
        },
        "measurements": {
            "fit_seconds": round(elapsed, 3),
            "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "python": os.sys.version.split()[0],
            "gensim": __import__("gensim").__version__,
            "numpy": np.__version__,
        },
        "gates": {
            "full_scale_memory_measured": False,
            "full_scale_duration_measured": False,
            "full_training_authorized": False,
            "production_vectors_generated": False,
            "publication_authorized": False,
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        raise SystemExit("refuse overwrite of preflight report")
    report = run_probe()
    args.out.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("SYNTHETIC_FULL_VOCAB_MEMORY_PROBE_PASS_NOT_FULL_TRAINING")


if __name__ == "__main__":
    main()
