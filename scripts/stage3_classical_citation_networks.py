#!/usr/bin/env python3
"""Private Stage 3 classical citation projections; source data are NEVER published.

Approved scientific scope: primary eligible canonical article roster and the ORIGINAL
directed exact-DOI article-to-article graph, not the undirected node2vec projection.

Creates two unpruned, exactly weighted undirected pair networks:
  co_citation: two cited papers have the same citing paper;
  bibliographic_coupling: two citing papers share a cited paper.

The edges are encoded as [packed_uint32_pair_key, integer_weight] JSONL, gzip,
with node_index -> private article ID mapping remaining in the frozen source ZIP.
No author/term fields are inferred from citations.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import zipfile

import numpy as np

FROZEN_GRAPH_SHA256 = "33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c"
N_ELIGIBLE = 57_204
N_DIRECTED_ALL = 328_383
N_ELIGIBLE_DIRECTED = 328_307
N_EXCLUDED_ENDPOINT = 47
N_ELIGIBLE_LOOPS = 29
EXPECTED = {
    "co_citation": {"incidences": 2_891_776, "unique_pairs": 2_055_149},
    "bibliographic_coupling": {"incidences": 18_490_159, "unique_pairs": 15_871_086},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as member:
        with gzip.GzipFile(fileobj=member, mode="rb") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def load_directed_eligible(archive: zipfile.ZipFile):
    mapping = {}
    ids = [None] * N_ELIGIBLE
    for row in read_rows(archive, "node2vec_node_mapping.private.jsonl.gz"):
        article_id, index = row["article_id"], row["node_index"]
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("Invalid node index")
        if not 0 <= index < N_ELIGIBLE or ids[index] is not None:
            raise ValueError("Missing/duplicate node index")
        if article_id in mapping:
            raise ValueError("Duplicate article ID")
        mapping[article_id] = index
        ids[index] = article_id
    if len(mapping) != N_ELIGIBLE or any(x is None for x in ids):
        raise ValueError("Incorrect frozen eligible roster")

    outgoing = [[] for _ in range(N_ELIGIBLE)]
    incoming = [[] for _ in range(N_ELIGIBLE)]
    count_all = excluded = loops = accepted = 0
    seen = set()
    for row in read_rows(archive, "directed_edges.private.jsonl.gz"):
        count_all += 1
        src = mapping.get(row["source_article_id"])
        dst = mapping.get(row["target_article_id"])
        if src is None or dst is None:
            excluded += 1
            continue
        if src == dst:
            loops += 1
            continue
        key = src * N_ELIGIBLE + dst
        if key in seen:
            raise ValueError("Duplicate directed source-target pair")
        seen.add(key)
        outgoing[src].append(dst)
        incoming[dst].append(src)
        accepted += 1
    if (count_all, excluded, loops, accepted) != (
        N_DIRECTED_ALL, N_EXCLUDED_ENDPOINT, N_ELIGIBLE_LOOPS, N_ELIGIBLE_DIRECTED
    ):
        raise ValueError("Frozen directed graph counts changed")

    if sum(len(a) for a in outgoing) != accepted:
        raise AssertionError("Out-degree sum")
    if sum(len(a) for a in incoming) != accepted:
        raise AssertionError("In-degree sum")
    return outgoing, incoming, {
        "nodes": len(mapping), "all_directed_edges": count_all,
        "out_of_cohort_edges": excluded, "eligible_self_loops": loops,
        "eligible_nonloop_directed_edges": accepted,
        "isolated_nodes": sum(not a and not b for a, b in zip(outgoing, incoming)),
    }


def pair_projection(neighborhoods: list[list[int]], n_nodes: int):
    """Exact sorted unordered pair keys and integer shared-neighbor counts.

    Keys use a*n_nodes+b for a<b; all event pairs are retained including weight=1.
    """
    if n_nodes * n_nodes > (1 << 32):
        raise ValueError("Pair keys exceed uint32 capacity")
    total = 0
    for group in neighborhoods:
        if len(group) != len(set(group)):
            raise ValueError("Repeated neighbor in an exact directed projection")
        n = len(group)
        total += n * (n - 1) // 2
    pairs = np.empty(total, dtype=np.uint32)
    pos = 0
    for group in neighborhoods:
        values = sorted(group)
        for i, a in enumerate(values):
            for b in values[i + 1:]:
                pairs[pos] = a * n_nodes + b
                pos += 1
    if pos != total:
        raise AssertionError("Pair enumeration discrepancy")
    if not total:
        return np.empty(0, dtype=np.uint32), np.empty(0, dtype=np.uint32), total
    pairs.sort()
    # np.unique sorts; the inverse is not needed and is intentionally omitted.
    unique, frequencies = np.unique(pairs, return_counts=True)
    if int(frequencies.sum()) != total:
        raise AssertionError("Weighted edge count does not sum to incidences")
    if int(unique.max()) >= n_nodes * n_nodes:
        raise AssertionError("Packed pair overflow")
    return unique.astype(np.uint32, copy=False), frequencies.astype(np.uint32), total


def emit_pairs(path: Path, keys: np.ndarray, weights: np.ndarray) -> dict:
    if path.exists():
        raise FileExistsError(path)
    with path.open("xb") as binary:
        with gzip.GzipFile(filename="", fileobj=binary, mode="wb", mtime=0, compresslevel=6) as out:
            for offset in range(0, len(keys), 2048):
                chunk = "".join(
                    f"[{int(key)},{int(weight)}]\n"
                    for key, weight in zip(keys[offset: offset + 2048], weights[offset: offset + 2048])
                )
                out.write(chunk.encode("ascii"))
    # A separate read forces the gzip integrity trailer to be checked.
    line_count = weight_sum = 0
    with gzip.open(path, "rt", encoding="ascii") as source:
        previous_key = -1
        for line in source:
            key, weight = json.loads(line)
            if key <= previous_key or weight < 1:
                raise AssertionError("Noncanonical ordered pair output")
            previous_key = key
            weight_sum += weight
            line_count += 1
    if line_count != len(keys) or weight_sum != int(weights.sum()):
        raise AssertionError("Persistent pair-list replay mismatch")
    return {
        "name": path.name, "rows": line_count, "incidences": weight_sum,
        "sha256": sha256(path), "size_bytes": path.stat().st_size,
        "encoding": "gzip/jsonl; rows [packed_uint32_key,shared_neighbor_count]",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-graph", type=Path, required=True)
    parser.add_argument("--restricted-output-dir", type=Path, required=True)
    parser.add_argument("--explicit-private-research-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.explicit_private_research_run:
        parser.error("Must explicitly acknowledge the private research run")
    if np.__version__ != "2.3.5":
        parser.error("Expected pinned numpy 2.3.5; do not silently change runtime")
    graph = args.frozen_graph
    if sha256(graph) != FROZEN_GRAPH_SHA256:
        parser.error("Frozen graph SHA256 mismatch")
    target = args.restricted_output_dir
    if target.exists() and any(target.iterdir()):
        parser.error("Output directory is nonempty; no overwrites")
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target, 0o700)

    with zipfile.ZipFile(graph) as archive:
        if archive.testzip() is not None:
            parser.error("Graph ZIP CRC failed")
        source_manifest = json.load(archive.open("node2vec_graph_manifest.private.json"))
        if source_manifest.get("node2vec_training_edge_count") != 328_298:
            parser.error("Frozen graph manifest disagrees with accepted record")
        outgoing, incoming, directed = load_directed_eligible(archive)

    if directed["isolated_nodes"] != 13_596:
        parser.error("Unexpected isolate count")
    results = {}
    # Swap incoming/outgoing to switch from co-citation to bibliographic coupling.
    for label, neighborhoods in (
        ("co_citation", outgoing),
        ("bibliographic_coupling", incoming),
    ):
        keys, weights, incidences = pair_projection(neighborhoods, N_ELIGIBLE)
        expected = EXPECTED[label]
        if incidences != expected["incidences"] or len(keys) != expected["unique_pairs"]:
            parser.error(f"{label}: exact reference aggregate mismatch")
        path = target / f"{label}.pairs.private.jsonl.gz"
        artifact = emit_pairs(path, keys, weights)
        histogram = collections.Counter(int(w) if int(w) < 6 else "6_plus" for w in weights)
        artifact.update({
            "max_weight": int(weights.max()) if len(weights) else 0,
            "weights_histogram": {str(k): v for k, v in histogram.items()},
            "pair_key_formula": "min(article_index_1,article_index_2)*57204+max(article_index_1,article_index_2)",
            "no_threshold": True,
        })
        results[label] = artifact
        del keys, weights

    manifest = {
        "schema": "pro-adherence-stage3-classical-directed-citation-projections/v1",
        "status": "LOCAL_DERIVED_ARTIFACTS_REQUIRE_RESTRICTED_DRIVE_UPLOAD_AND_INDEPENDENT_QA",
        "input_graph_sha256": FROZEN_GRAPH_SHA256,
        "authoritative_input_graph_drive_id": "1NysRCVbYlEAbW2FPXfdanKueaGjvYPsm",
        "article_index_mapping": "frozen node2vec_node_mapping.private.jsonl.gz",
        "source_orientation": "directed",
        "source_observations": "exact DOI within canonical corpus, incomplete external reference coverage",
        "eligible_population_only": True,
        "directed": directed,
        "outputs": results,
        "scientific_validation_claimed": False,
        "private_data_publication_authorized": False,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "code_sha256": sha256(Path(__file__)),
    }
    manifest_path = target / "STAGE3_PRIVATE_CLASSICAL_CITATION_MANIFEST.json"
    with manifest_path.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, sort_keys=True, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps({
        "result": "LOCAL_CLASSICAL_PAIR_NETWORKS_COMPLETE_PENDING_DRIVE_READBACK",
        "eligible_nodes": N_ELIGIBLE,
        "co_citation_pairs": results["co_citation"]["rows"],
        "coupling_pairs": results["bibliographic_coupling"]["rows"],
        "manifest_sha256": sha256(manifest_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
