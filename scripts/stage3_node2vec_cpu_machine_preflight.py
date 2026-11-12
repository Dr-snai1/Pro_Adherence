"""Read-only CPU machine and frozen-graph identity preflight for Stage 3.

No walk generation, Gensim training, embeddings, cloud spending or publication.
The output explicitly CANNOT authorize a full node2vec run.
"""
from __future__ import annotations

if not __debug__:
    raise SystemExit("Python assertions (-O forbidden) for node2vec preflight")

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import zipfile

GRAPH_SHA256 = "33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c"
REQUIRED = {
    "gensim": "4.4.0",
    "numpy": "2.3.5",
    "scipy": "1.17.0",
    "smart_open": "7.6.1",
    "wrapt": "2.2.1",
}
NONISOLATED, ISOLATED = 43608, 13596
EDGES = 328298
WALKS_PER_NODE, WALK_LENGTH = 10, 40
DIM = 128


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_graph_archive(path: Path) -> dict:
    if not path.is_file() or sha256_file(path) != GRAPH_SHA256:
        raise ValueError("frozen graph ZIP missing or SHA256 mismatch")
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise ValueError("frozen graph CRC failed")
        manifest = json.loads(z.read("node2vec_graph_manifest.private.json"))
        outputs = manifest["outputs"]
        expected = {
            "node2vec_node_mapping.private.jsonl.gz",
            "node2vec_training_edges.private.jsonl.gz",
            "directed_edges.private.jsonl.gz",
            "directed_citation_evidence.private.jsonl.gz",
        }
        if set(outputs) != expected:
            raise ValueError("frozen graph manifest member set changed")
        for name, entry in outputs.items():
            data = z.read(name)
            if len(data) != entry["size_bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("frozen graph member digest or length mismatch")
    return {
        "sha256": GRAPH_SHA256,
        "zip_crc_and_four_member_sha256": "PASS",
        "bytes": path.stat().st_size,
    }


def cgroup_memory() -> dict:
    base = Path("/sys/fs/cgroup")
    if (base / "memory.max").exists():
        raw_limit = (base / "memory.max").read_text(encoding="ascii").strip()
        raw_current = (base / "memory.current").read_text(encoding="ascii").strip()
        if raw_limit != "max":
            limit = int(raw_limit)
            used = int(raw_current)
            return {
                "source": "cgroup_v2", "limit_bytes": limit,
                "current_bytes": used, "available_to_cgroup_bytes": max(0, limit - used),
            }
    # No cgroup cap, OS physical memory is a bound, not free capacity.
    try:
        physical = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        physical = None
    return {"source": "physical_or_unknown", "limit_bytes": physical,
            "current_bytes": None, "available_to_cgroup_bytes": None}


def preflight(graph: Path, workspace: Path) -> dict:
    if sys.version_info[:2] != (3, 13) or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise RuntimeError("verified wheel ABI requires CPython 3.13 x86-64")
    observed = {name: metadata.version(name) for name in REQUIRED}
    if observed != REQUIRED:
        raise RuntimeError(f"CPU backend installed version mismatch: {observed}")
    from gensim.models import Word2Vec
    import gensim
    import numpy as np
    import scipy

    model = Word2Vec(
        vector_size=DIM, window=10, negative=5, sample=0.001,
        sg=1, hs=0, min_count=1, workers=1, seed=20261031,
    )
    model_estimate = model.estimate_memory(vocab_size=NONISOLATED)
    if model.sg != 1 or model.hs != 0 or model.negative != 5 or model.sample != 0.001:
        raise RuntimeError("owner-approved backend settings mismatch")

    disk = shutil.disk_usage(workspace)
    memory = cgroup_memory()
    return {
        "schema": "pro-adherence-stage3-node2vec-machine-readiness/v1",
        "status": "READ_ONLY_PREFLIGHT_FULL_TRAINING_NOT_AUTHORIZED",
        "graph": verify_graph_archive(graph),
        "runtime": {
            "python": sys.version.split()[0], "platform": platform.system(),
            "architecture": platform.machine(), "packages": observed,
            "package_imports_pass": bool(gensim and np and scipy),
            "installed_wheel_bytes_reverified_here": False,
            "fresh_ci_hashed_wheel_install": "PASS (separate GitHub Actions run 43292747039)",
            "gensim_shrink_windows_default": model.shrink_windows,
            "gensim_ns_exponent_default": model.ns_exponent,
            "gensim_alpha_default": model.alpha,
            "gensim_min_alpha_default": model.min_alpha,
        },
        "resource": {
            "memory": memory,
            "disk_free_bytes": disk.free,
            "total_expected_walks_NOT_generated": NONISOLATED * WALKS_PER_NODE,
            "nominal_total_tokens_NOT_generated": NONISOLATED * WALKS_PER_NODE * WALK_LENGTH,
            "packed_uint32_walk_token_lower_bound_bytes": NONISOLATED * WALKS_PER_NODE * WALK_LENGTH * 4,
            "model_gensim_estimate_bytes_NOT_peak_RSS": model_estimate,
            "raw_and_unit_float32_vector_lower_bound_bytes": NONISOLATED * DIM * 4 * 2,
            "full_run_RSS_measured": False,
            "full_run_duration_measured": False,
            "streaming_will_avoid_full_python_walk_list": True,
        },
        "gates": {
            "owner_full_training_authorized": False,
            "full_runtime_identity_verified_on_target": False,
            "peak_RSS_safety_guaranteed": False,
            "production_embeddings_generated": False,
            "publication_authorized": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refuse overwrite")
    result = preflight(args.graph, args.workspace)
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("READ_ONLY_NODE2VEC_MACHINE_PREFLIGHT_PASS_NOT_FULL_TRAINING")


if __name__ == "__main__":
    main()
