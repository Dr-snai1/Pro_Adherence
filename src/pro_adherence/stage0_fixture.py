"""Frozen Stage 0 promoted-release acceptance fixture builder."""
from __future__ import annotations

import copy
from pathlib import Path

from . import validate as v

FIXTURE_SPEC = "tests/fixtures/stage0_materialization/fixture_spec.json"


def _public_access() -> dict:
    return {
        "access_class": "public",
        "license_class": "fixture",
        "license_status": "confirmed",
        "license_evidence_ref": "stage0-materialization-fixture",
        "publication_permissions": {
            "metadata": "allow",
            "raw_text": "deny",
            "derived": "allow",
        },
    }


def build_fixture(root: Path = v.ROOT, payload: bytes | None = None) -> dict:
    spec = v.load_json(root / FIXTURE_SPEC)
    payload_path = root / spec["payload_path"]
    default_payload = payload is None
    payload = payload_path.read_bytes() if default_payload else payload
    payload_hash = v.sha256_bytes(payload)
    if default_payload and payload_hash != spec["payload_sha256"]:
        raise v.ValidationFailure("stage0 fixture payload hash mismatch")

    lineage = v.load_json(root / "contracts/manifests/minimal_lineage.example.json")
    artifact = lineage["artifacts"][-1]
    artifact["content_hash"] = payload_hash
    artifact["access_license"] = _public_access()

    corpus = v.load_json(root / "contracts/manifests/empty_corpus.manifest.json")
    corpus["corpus_release_id"] = lineage["corpus_release_ids"][0]
    corpus["manifest_hash"] = v.recompute_manifest_hash(corpus)

    ids = spec["ids"]
    report = {
        "record_type": "quality_report",
        "quality_report_id": ids["quality_report"],
        "subject_artifact_id": artifact["artifact_id"],
        "status": "pass",
        "checks": [{
            "check_id": "stage0_materialization_fixture",
            "status": "pass",
            "message": None,
            "evidence_ref": "tests/fixtures/stage0_materialization/fixture_spec.json",
        }],
        "created_at": "2026-10-08T20:00:00Z",
    }
    event = {
        "record_type": "promotion_event",
        "promotion_event_id": ids["promotion_event"],
        "artifact_ids": [artifact["artifact_id"]],
        "quality_report_ids": [report["quality_report_id"]],
        "decision": "promoted",
        "target_release_id": ids["release"],
        "created_at": "2026-10-08T20:01:00Z",
    }
    release = {
        "manifest_version": "1.0.0",
        "release_id": ids["release"],
        "status": "promoted",
        "corpus_release_id": corpus["corpus_release_id"],
        "artifacts": [{
            "artifact_id": artifact["artifact_id"],
            "artifact_type": artifact["artifact_type"],
            "content_hash": artifact["content_hash"],
            "schema_version": artifact["schema_version"],
            "role": "stage0_public_fixture",
            "public_path": spec["public_path"],
            "publication_permission_basis": "derived",
            "access_license": copy.deepcopy(artifact["access_license"]),
        }],
        "promotion_event_ids": [event["promotion_event_id"]],
        "manifest_hash": "",
        "created_at": "2026-10-08T20:01:00Z",
        "superseded_by": None,
    }
    release["manifest_hash"] = v.recompute_manifest_hash(release)
    return {
        "spec": spec, "payload": payload, "lineage": lineage, "corpus": corpus,
        "report": report, "event": event, "release": release,
        "artifact_id": artifact["artifact_id"],
    }


def write_fixture_input_bundle(destination: Path, root: Path = v.ROOT) -> dict:
    destination = Path(destination)
    if destination.exists():
        raise v.ValidationFailure(f"fixture destination already exists: {destination}")
    destination.mkdir(parents=True)
    fixture = build_fixture(root)
    json_files = {
        "lineage.json": fixture["lineage"],
        "corpus.json": fixture["corpus"],
        "quality-report.json": fixture["report"],
        "promotion-event.json": fixture["event"],
        "release.json": fixture["release"],
    }
    for name, value in json_files.items():
        (destination / name).write_bytes(v.canonical_json(value) + b"\n")
    (destination / "public-artifact.json").write_bytes(fixture["payload"])
    manifest = {
        "backup_fixture_schema": "stage0-backup-fixture/v1",
        "source_commit_scope": "candidate-commit",
        "files": [],
    }
    for path in sorted(p for p in destination.iterdir() if p.is_file()):
        data = path.read_bytes()
        manifest["files"].append({"path": path.name, "sha256": v.sha256_bytes(data), "size": len(data)})
    manifest["snapshot_hash"] = v.sha256_bytes(v.canonical_json(manifest["files"]))
    (destination / "backup-manifest.json").write_bytes(v.canonical_json(manifest) + b"\n")
    return fixture


def verify_restored_input_bundle(destination: Path) -> dict:
    destination = Path(destination)
    manifest = v.load_json(destination / "backup-manifest.json")
    actual = []
    for item in manifest.get("files", []):
        path = destination / item["path"]
        if not path.is_file():
            raise v.ValidationFailure(f"restore fixture missing {item['path']}")
        data = path.read_bytes()
        actual.append({"path": item["path"], "sha256": v.sha256_bytes(data), "size": len(data)})
        if actual[-1] != item:
            raise v.ValidationFailure(f"restore fixture mismatch {item['path']}")
    if v.sha256_bytes(v.canonical_json(actual)) != manifest.get("snapshot_hash"):
        raise v.ValidationFailure("restore fixture snapshot hash mismatch")
    return manifest
