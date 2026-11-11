"""Private, deterministic Stage3 node2vec graph preparation; no training.

Inputs must be exact frozen Stage2 ZIP and exact restricted 57,293-row
eligibility roster. All outputs are PRIVATE and must be stored on restricted
Drive with independent SHA readback before they become project artifacts.
The command is not a compute authorization or an ML inference entrypoint.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import zipfile

from pro_adherence.stage3_contracts import (
    FROZEN_STAGE2_ZIP_SHA256,
    Stage3ContractError,
    plan_approved_node2vec_graph,
)
from pro_adherence.stage3_preflight import PRIVATE_COHORT_SHA, sha256_path

EXPECTED_COUNTS = {"source": 87511, "canonical": 57293, "eligible": 57204,
                   "citations": 2437863, "exact_doi": 406811,
                   "ambiguous_doi": 223, "unresolved": 2030829}
REQUIRED_ZIP_MEMBERS = {
    "canonical_articles.jsonl.gz", "source_records.jsonl.gz",
    "identity_decisions.jsonl.gz", "citation_links.jsonl.gz",
    "author_observations.jsonl.gz", "affiliation_observations.jsonl.gz",
    "loo_pubmed.json", "loo_woscc.json", "loo_apa_psycinfo.json",
    "manifest.json",
}


def _rows(stream):
    with gzip.GzipFile(fileobj=stream, mode="rb") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_verified_inputs(archive_path: Path, cohort_path: Path) -> tuple:
    """Fail before processing if either durable input differs in any byte."""
    if sha256_path(archive_path) != FROZEN_STAGE2_ZIP_SHA256:
        raise Stage3ContractError("frozen Stage2 ZIP SHA256 mismatch")
    if sha256_path(cohort_path) != PRIVATE_COHORT_SHA:
        raise Stage3ContractError("restricted Stage3 cohort SHA256 mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        if set(archive.namelist()) != REQUIRED_ZIP_MEMBERS:
            raise Stage3ContractError("Stage2 ZIP member inventory mismatch")
        if archive.testzip() is not None:
            raise Stage3ContractError("Stage2 ZIP CRC mismatch")
        metadata = json.load(archive.open("manifest.json"))
        if (metadata.get("schema") != "pro-adherence-stage2-three-source-private/v1"
                or metadata.get("publication_authorized") is not False
                or metadata.get("canonical_articles") != 57293
                or metadata.get("source_records") != 87511):
            raise Stage3ContractError("Stage2 embedded manifest mismatch")
        with archive.open("canonical_articles.jsonl.gz") as f:
            canonical = list(_rows(f))
        with archive.open("source_records.jsonl.gz") as f:
            sources = list(_rows(f))
        with archive.open("citation_links.jsonl.gz") as f:
            citations = list(_rows(f))
    with cohort_path.open("rb") as f:
        roster = list(_rows(f))
    if (len(canonical), len(sources), len(citations), len(roster)) != (
            57293, 87511, 2437863, 57293):
        raise Stage3ContractError("source or cohort counts mismatch")
    indexed = {}
    for row in roster:
        key = row.get("article_id")
        if not isinstance(key, str) or key in indexed or type(row.get("primary_eligible")) is not bool:
            raise Stage3ContractError("invalid/duplicate cohort row")
        indexed[key] = row["primary_eligible"]
    ids = {r["canonical_article_id"] for r in canonical}
    if len(ids) != 57293 or set(indexed) != ids or sum(indexed.values()) != 57204:
        raise Stage3ContractError("approved primary cohort mapping mismatch")
    return canonical, sources, citations, indexed


def _write_gzip_rows(path: Path, rows: list[dict]) -> dict:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as dst:
        with gzip.GzipFile(filename="", fileobj=dst, mode="wb",
                           mtime=0, compresslevel=6) as zipped:
            for row in rows:
                zipped.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    return {"name": path.name, "sha256": sha256_path(path), "rows": len(rows),
            "size_bytes": path.stat().st_size}


def materialize_private_graph(graph: dict, output_dir: Path, *,
                              expected_canonical: int = 57293,
                              expected_eligible: int = 57204,
                              expected_citations: int = 2437863,
                              expected_exact_doi: int = 406811) -> dict:
    """Write immutable, sorted private evidence and read back byte identities.

    This function works on tiny synthetic fixtures for tests. Do not use a
    synthetic run as proof that the accepted 57,204-row graph was materialized.
    """
    directed, training = (graph["directed_citation_graph"],
                          graph["node2vec_training_graph"])
    dn, tn = directed["nodes"], training["nodes"]
    status = directed["citation_status_counts"]
    if (len(dn) != expected_canonical or len(tn) != expected_canonical
            or directed["article_count"] != expected_canonical
            or training["article_count"] != expected_canonical
            or training["eligible_article_count"] != expected_eligible
            or sum(status.values()) != expected_citations
            or status.get("exact_doi", 0) != expected_exact_doi
            or directed["edge_observation_count"] != expected_exact_doi
            or training["citation_status_counts"] != status):
        raise Stage3ContractError("directed/training citation census mismatch")
    mapping = sorted((row["article_id"] for row in tn if row["eligible"]))
    if len(mapping) != expected_eligible or len(set(mapping)) != len(mapping):
        raise Stage3ContractError("eligible node mapping incomplete or duplicated")
    allowed = set(mapping)
    if (sum(r["observation_count"] for r in directed["edges"]) != expected_exact_doi
            or any(r["weight"] != 1 for r in directed["edges"])):
        raise Stage3ContractError("original directed edge evidence mismatch")
    for edge in training["edges"]:
        a, b = edge["source_article_id"], edge["target_article_id"]
        if (not a < b or a not in allowed or b not in allowed
                or edge["weight"] != 1 or edge["observation_count"] < 1):
            raise Stage3ContractError("invalid binary undirected training edge")
    excluded = training["excluded_edge_observations"]
    if (directed["edge_observation_count"] != training["edge_observation_count"]
            + excluded.get("self_loop_policy", 0)
            + excluded.get("excluded_policy", 0)):
        raise Stage3ContractError("training graph silently lost DOI evidence")
    for row in dn:
        if "article_id" not in row:
            raise Stage3ContractError("directed node identity missing")
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise Stage3ContractError("private graph destination must be empty; never overwrite")
    os.chmod(output_dir, 0o700)
    lookup = {row["article_id"]: row for row in tn}
    map_rows = [
        {"node_index": i, "article_id": article_id,
         "has_observed_resolved_edge": lookup[article_id]["has_observed_resolved_edge"],
         "isolate_reason": lookup[article_id]["isolate_reason"]}
        for i, article_id in enumerate(mapping)
    ]
    outputs = {
        "directed_nodes": _write_gzip_rows(output_dir / "citation_directed_nodes.private.jsonl.gz", dn),
        "directed_edges": _write_gzip_rows(output_dir / "citation_directed_edges.private.jsonl.gz",
                                           directed["edges"]),
        "training_edges": _write_gzip_rows(output_dir / "node2vec_training_edges.private.jsonl.gz",
                                           training["edges"]),
        "node_mapping": _write_gzip_rows(output_dir / "node2vec_sorted_nodes.private.jsonl.gz",
                                         map_rows),
    }
    for file in outputs.values():
        p = output_dir / file["name"]
        if sha256_path(p) != file["sha256"]:
            raise Stage3ContractError("private graph output readback SHA mismatch")
        with p.open("rb") as f:
            if sum(1 for _ in _rows(f)) != file["rows"]:
                raise Stage3ContractError("private graph output gzip readback mismatch")
    isolates = sum(not lookup[a]["has_observed_resolved_edge"] for a in mapping)
    manifest = {
        "schema": "pro-adherence-stage3-private-node2vec-graph/v1",
        "access_class": "restricted",
        "publication_authorized": False,
        "source_stage2_zip_sha256": FROZEN_STAGE2_ZIP_SHA256,
        "source_private_cohort_sha256": PRIVATE_COHORT_SHA,
        "full_directed_coverage_count": expected_canonical,
        "eligible_node_count": expected_eligible,
        "citation_observation_count": expected_citations,
        "citation_status_counts": status,
        "directed_exact_doi_observations": expected_exact_doi,
        "directed_edge_count": directed["edge_count"],
        "training_edge_count": training["edge_count"],
        "training_edge_observations": training["edge_observation_count"],
        "training_excluded_observations": excluded,
        "training_isolate_count": isolates,
        "isolate_vector_status": "missing_structural",
        "source_orientation": "directed",
        "training_orientation": "undirected",
        "weights": "binary_unit",
        "outputs": outputs,
        "graph_snapshot": {
            "source_directed_graph_sha256": outputs["directed_edges"]["sha256"],
            "training_undirected_graph_sha256": outputs["training_edges"]["sha256"],
            "sorted_node_mapping_sha256": outputs["node_mapping"]["sha256"],
            "eligible_node_count": expected_eligible,
            "source_orientation": "directed",
            "training_orientation": "undirected",
            "weights": "binary_unit",
        },
        "planned_node2vec": {
            "dimension": 128, "p": 1, "q": 1, "walk_length": 40,
            "walks_per_node": 10, "window": 10, "epochs": 1, "seed": 20261031,
            "potential_walk_steps": expected_eligible * 10 * 40,
            "raw_vector_float32_min_bytes": expected_eligible * 128 * 4,
            "raw_plus_unit_float32_min_bytes": expected_eligible * 128 * 4 * 2,
            "note": "bounds, not measured RAM/GPU-hours; isolates need null vectors",
        },
        "training_executed": False,
    }
    manifest_path = output_dir / "node2vec_graph_manifest.private.json"
    fd = os.open(manifest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    with manifest_path.open("r", encoding="utf-8") as f:
        if json.load(f) != manifest:
            raise Stage3ContractError("manifest readback mismatch")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--private-cohort", required=True, type=Path)
    parser.add_argument("--private-output-dir", required=True, type=Path)
    parser.add_argument("--prepare-private-graph", action="store_true",
                        help="explicitly prepare graph; no model training")
    args = parser.parse_args()
    if not args.prepare_private_graph:
        parser.error("fail-closed: pass --prepare-private-graph for the approved restricted inputs")
    canonical, sources, citations, roster = load_verified_inputs(args.archive, args.private_cohort)
    graph = plan_approved_node2vec_graph(canonical, sources, citations, roster)
    manifest = materialize_private_graph(graph, args.private_output_dir)
    # No restricted article IDs, raw references or links to private files in stdout.
    print(json.dumps({
        "status": "LOCAL_PRIVATE_GRAPH_PREPARED_NOT_DURABLY_STORED",
        "eligible": manifest["eligible_node_count"],
        "directed_exact_observations": manifest["directed_exact_doi_observations"],
        "training_edge_count": manifest["training_edge_count"],
        "training_isolates": manifest["training_isolate_count"],
        "training_executed": False,
        "note": "requires restricted Drive upload + metadata/ACL + independent hash readback",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
