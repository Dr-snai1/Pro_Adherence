#!/usr/bin/env python3
"""Canonical Stage 0 deterministic build/materialization/restore E2E."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from pro_adherence import materialize as m
from pro_adherence import stage0_fixture as f
from pro_adherence import validate as v


def load_inputs(root: Path):
    ctx = v.SchemaContext.from_repo(ROOT)
    lineage = v.load_json(root / "lineage.json")
    corpus = v.load_json(root / "corpus.json")
    report = v.load_json(root / "quality-report.json")
    event = v.load_json(root / "promotion-event.json")
    release = v.load_json(root / "release.json")

    errors = []
    errors.extend(v.validate_contracts(ROOT, ctx))
    errors.extend(v.validate_lineage(lineage, ctx))
    catalog = v.catalog_from_bundle(lineage, errors)
    for record in (report, event):
        errors.extend(v._schema_errors(ctx, "provenance.schema.json", record, record["record_type"]))
        if record.get("record_type") == "quality_report":
            errors.extend(v.validate_quality_report(record))
        v.add_evidence_record(catalog, record, errors)
    errors.extend(v.validate_corpus_manifest(corpus, root=ROOT, ctx=ctx, artifacts=catalog.artifacts))
    errors.extend(v.validate_release_manifest(
        release, ctx=ctx, artifacts=catalog.artifacts,
        corpus_manifests={corpus["corpus_release_id"]: corpus},
        promotion_events=catalog.promotion_events,
        quality_reports=catalog.quality_reports,
        run_outputs=catalog.run_outputs,
        lineage_artifact_ids={lineage["root_output_artifact_id"]},
    ))
    if errors:
        raise v.ValidationFailure("\n".join(errors))
    return lineage, corpus, release, catalog


def build(input_dir: Path, output_dir: Path) -> dict:
    lineage, corpus, release, catalog = load_inputs(input_dir)
    artifact_id = lineage["root_output_artifact_id"]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    command = [
        sys.executable, "-m", "pro_adherence.materialize",
        "--release", str(input_dir / "release.json"),
        "--corpus", str(input_dir / "corpus.json"),
        "--lineage", str(input_dir / "lineage.json"),
        "--evidence", str(input_dir / "quality-report.json"),
        "--evidence", str(input_dir / "promotion-event.json"),
        "--artifact-source", f"{artifact_id}={input_dir / 'public-artifact.json'}",
        "--output", str(output_dir),
        "--json",
    ]
    p = subprocess.run(
        command, cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if p.returncode:
        raise v.ValidationFailure(
            "bare materializer CLI failed: " + p.stdout + p.stderr
        )
    payload = json.loads(p.stdout)
    if payload.get("status") != "PASS":
        raise v.ValidationFailure("bare materializer CLI did not report PASS")
    return payload["result"]


def main() -> int:
    boundary_errors = v.validate_repository_boundary(ROOT)
    if boundary_errors:
        raise v.ValidationFailure("\n".join(boundary_errors))
    with tempfile.TemporaryDirectory(prefix="pro-adherence-stage0-e2e-") as td:
        work = Path(td)
        source = work / "source"
        fixture = f.write_fixture_input_bundle(source, ROOT)
        f.verify_restored_input_bundle(source)

        out1 = work / "serving-1"
        first = build(source, out1)
        expected = fixture["spec"].get("expected_bundle_tree_hash")
        print("E2E_BUNDLE_TREE_HASH=" + first["bundle_tree_hash"])
        if expected and first["bundle_tree_hash"] != expected:
            raise v.ValidationFailure(
                f"materialized bundle hash mismatch expected {expected} got {first['bundle_tree_hash']}"
            )

        shutil.rmtree(out1)
        out2 = work / "serving-2"
        second = build(source, out2)
        if first["bundle_tree_hash"] != second["bundle_tree_hash"]:
            raise v.ValidationFailure("delete/rebuild bundle hash mismatch")
        if first["payload_tree_hash"] != second["payload_tree_hash"]:
            raise v.ValidationFailure("delete/rebuild payload tree hash mismatch")

        backup = work / "backup"
        shutil.copytree(source, backup)
        shutil.rmtree(source)
        restored = work / "restored"
        shutil.copytree(backup, restored)
        f.verify_restored_input_bundle(restored)
        out3 = work / "serving-restored"
        third = build(restored, out3)
        if first["bundle_tree_hash"] != third["bundle_tree_hash"]:
            raise v.ValidationFailure("restore/rebuild bundle hash mismatch")

        independent_hash, _ = m._tree_snapshot(out3)
        if independent_hash != third["bundle_tree_hash"]:
            raise v.ValidationFailure("independent output tree hash reconciliation failed")

        print(json.dumps({
            "status": "PASS",
            "bundle_tree_hash": first["bundle_tree_hash"],
            "payload_tree_hash": first["payload_tree_hash"],
            "backup_snapshot_hash": v.load_json(restored / "backup-manifest.json")["snapshot_hash"],
            "rebuild_equal": True,
            "restore_equal": True,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
