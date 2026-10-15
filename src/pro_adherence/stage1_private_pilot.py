"""Private-only offline pilot of three frozen TASK-0003 EFetch XML samples.

Strictly sample-only: NOT a full corpus, scientific Check B, or promoted release.
No NCBI requests, workflow dispatch, secret access, or Git writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from . import pubmed_evidence as evidence
from . import stage1_ingest as ingest

BRANCHES = ("V01_D_only", "V01_E_only", "PDC_incremental_only")


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _declared(package: Path, manifest: dict, rel: str) -> bytes:
    entry = manifest["files"].get(rel)
    if not isinstance(entry, dict) or not isinstance(entry.get("bytes"), int):
        raise ValueError("undeclared evidence input")
    target = package / rel
    if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(package.resolve()):
        raise ValueError("unsafe evidence file path")
    content = target.read_bytes()
    if len(content) != entry["bytes"] or _sha(content) != entry["sha256"]:
        raise ValueError("evidence input bytes/hash mismatch")
    return content


def _source_meta(manifest: dict, calls: list, qid: str, exact_query: str, evidence_commit: str) -> dict:
    if manifest["query_hashes"].get(qid) != _sha(exact_query.encode("utf-8")):
        raise ValueError("frozen query hash mismatch")
    rel = f"raw/{qid}/efetch/00001.xml"
    accepted = [call for call in calls if call.get("query_id") == qid
                and call.get("file") == rel and call.get("outcome") == "accepted"
                and str(call.get("endpoint", "")).endswith("/efetch.fcgi")]
    if len(accepted) != 1:
        raise ValueError("missing or ambiguous accepted EFetch provenance")
    return {"source_id": "pubmed", "retrieval_time": accepted[0]["utc"],
            "query_definition": exact_query,
            "source_cursor": f"frozen-efetch-sample:{evidence_commit}:{manifest['run_id']}:{qid}",
            "license_class": "pubmed-metadata-license-unverified",
            "access_class": "project-internal"}


def run(package: Path, workspace: Path, *, evidence_commit: str, expected_package_root: str) -> dict:
    package, workspace = Path(package).resolve(), Path(workspace).resolve()
    if len(evidence_commit) != 40 or any(c not in "0123456789abcdef" for c in evidence_commit):
        raise ValueError("invalid exact private evidence commit")
    if len(expected_package_root) != 64 or any(c not in "0123456789abcdef" for c in expected_package_root):
        raise ValueError("invalid exact evidence package root")
    repo_root = Path(ingest.__file__).resolve().parents[2]
    if (workspace.is_relative_to(package) or package.is_relative_to(workspace)
            or workspace.is_relative_to(repo_root)):
        raise ValueError("research workspace must be independent from evidence and public repository")
    # Full native evidence verification BEFORE any workspace writes: checks
    # inventory, root hash, accepted original response semantics and PMID samples.
    evidence.verify(package, require_final=True)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("task_id") != "TASK-0003" or manifest.get("status") != "final"
            or manifest.get("package_root_sha256") != expected_package_root):
        raise ValueError("wrong/unaccepted immutable primary evidence package")
    calls = json.loads(_declared(package, manifest, "metadata/requests.json"))
    entries, all_pmids = [], []
    for qid in BRANCHES:
        xml_rel = f"raw/{qid}/efetch/00001.xml"
        sample_rel = f"samples/{qid}/pmids.txt"
        query_rel = f"queries/{qid}.txt"
        raw_xml = _declared(package, manifest, xml_rel)
        selected = [x for x in _declared(package, manifest, sample_rel).decode("ascii").splitlines() if x]
        query = _declared(package, manifest, query_rel).decode("utf-8").rstrip("\n")
        expected_size = manifest["sample_policy"][qid]["size"]
        if len(selected) != expected_size or len(set(selected)) != len(selected):
            raise ValueError("frozen sample count or uniqueness mismatch")
        meta = _source_meta(manifest, calls, qid, query, evidence_commit)
        ingest._validate_meta(meta)
        articles, _, _, positions = ingest._parse(
            raw_xml, ingest._id("raw/" + _sha(raw_xml)), "pubmed", meta["retrieval_time"])
        if positions != len(selected) or {a["pmid"] for a in articles} != set(selected):
            raise ValueError("PubMed sample XML and frozen sample IDs do not match")
        all_pmids.extend(row["pmid"] for row in articles)
        entries.append((qid, xml_rel, sample_rel, query_rel, meta, positions, _sha(raw_xml)))
    # All input checks passed. Build outputs only inside an independent private workspace.
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    meta_dir = workspace / "_source_metadata"
    meta_dir.mkdir(exist_ok=True, mode=0o700)
    reports = []
    for qid, xml_rel, sample_rel, query_rel, meta, positions, raw_hash in entries:
        meta_file = meta_dir / (qid + ".json")
        meta_bytes = _canonical(meta) + b"\n"
        if meta_file.is_symlink():
            raise ValueError("private metadata symlink forbidden")
        if meta_file.exists():
            if meta_file.read_bytes() != meta_bytes:
                raise ValueError("private source metadata drift")
        else:
            with meta_file.open("xb") as handle:
                handle.write(meta_bytes)
        dest = ingest.build(package / xml_rel, meta_file, workspace / qid)
        snapshot = json.loads((dest / "corpus_manifest.json").read_text(encoding="utf-8"))
        if snapshot["article_count"] != positions or snapshot["status"] != "draft":
            raise ValueError("diagnostic snapshot reconciliation failed")
        reports.append({"branch": qid, "count": positions, "raw_sha256": raw_hash,
                        "snapshot_id": dest.name, "snapshot_manifest_hash": snapshot["manifest_hash"],
                        "sample_source": sample_rel, "xml_source": xml_rel, "query_source": query_rel})
    report = {"scope": "FROZEN_SAMPLE_ONLY_NOT_FULL_CORPUS", "status": "diagnostic-not-promoted",
              "evidence_commit": evidence_commit, "evidence_package_root_sha256": expected_package_root,
              "run_id": manifest["run_id"], "positions": sum(x["count"] for x in reports),
              "unique_pmids_across_samples": len(set(all_pmids)),
              "overlap_positions": len(all_pmids) - len(set(all_pmids)), "branches": reports}
    target = workspace / "diagnostic_pilot_report.json"
    contents = _canonical(report) + b"\n"
    if target.exists():
        if target.is_symlink() or target.read_bytes() != contents:
            raise ValueError("pilot report drift; refusing overwrite")
    else:
        with target.open("xb") as fp:
            fp.write(contents)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline verified TASK-0003 sample materialization")
    parser.add_argument("--private-package", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence-commit", required=True)
    parser.add_argument("--expected-package-root", required=True)
    args = parser.parse_args(argv)
    out = run(args.private_package, args.workspace, evidence_commit=args.evidence_commit,
              expected_package_root=args.expected_package_root)
    print(json.dumps({"status": out["status"], "positions": out["positions"],
                      "unique_pmids_across_samples": out["unique_pmids_across_samples"],
                      "overlap_positions": out["overlap_positions"], "public_promotion": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
