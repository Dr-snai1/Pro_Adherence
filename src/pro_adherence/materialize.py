"""Deterministic Stage 0 public serving materialization.

The materializer consumes only an explicitly promoted release plus its exact
corpus/lineage/quality evidence and an exact source mapping for selected public
artifacts. It has no production database or backend dependency.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

from . import validate as v


def _safe_public_path(raw: str) -> tuple[str | None, list[str]]:
    errors = v.validate_public_paths([raw], allow_serving_placeholder=False)
    normalized, path_error = v.normalize_repo_path(raw)
    if path_error:
        errors.append(f"materialization: invalid public_path {raw!r}: {path_error}")
        return None, errors
    if not normalized:
        errors.append("materialization: public_path must not be empty")
        return None, errors
    if normalized in {"release-manifest.json", "_materialization.json"}:
        errors.append(f"materialization: reserved public_path {normalized}")
    return normalized, errors


def _tree_snapshot(root: Path) -> tuple[str, list[dict]]:
    entries: list[dict] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        entries.append({"path": rel, "sha256": v.sha256_bytes(data), "size": len(data)})
    return v.sha256_bytes(v.canonical_json(entries)), entries


def validate_materialization_inputs(
    release: dict,
    *,
    catalog: v.EvidenceCatalog,
    corpora: Mapping[str, dict],
    lineage_artifact_ids: set[str],
    artifact_sources: Mapping[str, Path],
) -> list[str]:
    errors = v.validate_release_manifest(
        release,
        artifacts=catalog.artifacts,
        corpus_manifests=corpora,
        promotion_events=catalog.promotion_events,
        quality_reports=catalog.quality_reports,
        run_outputs=catalog.run_outputs,
        lineage_artifact_ids=lineage_artifact_ids,
    )
    if release.get("status") != "promoted":
        errors.append("materialization: release status must be promoted")

    selected = release.get("artifacts", [])
    selected_ids = [item.get("artifact_id") for item in selected]
    if len(selected_ids) != len(set(selected_ids)):
        errors.append("materialization: duplicate selected artifact_id")
    supplied_ids = set(artifact_sources)
    if supplied_ids != set(selected_ids):
        missing = sorted(set(selected_ids) - supplied_ids)
        extra = sorted(supplied_ids - set(selected_ids))
        if missing:
            errors.append(f"materialization: missing selected payload sources {missing}")
        if extra:
            errors.append(f"materialization: extra/unselected payload sources {extra}")

    public_paths: list[str] = []
    for item in selected:
        artifact_id = item.get("artifact_id")
        public_path, path_errors = _safe_public_path(item.get("public_path", ""))
        errors.extend(path_errors)
        if public_path:
            public_paths.append(public_path)
        artifact = catalog.artifacts.get(artifact_id)
        if artifact is not None:
            uri, uri_error = v.normalize_repo_path(str(artifact.get("uri", "")))
            if uri_error:
                errors.append(f"materialization: artifact {artifact_id} unsafe uri: {uri_error}")
            elif uri and any(
                uri.startswith(prefix)
                for prefix in ("data/raw/", "data/research/", "data/restricted/", "research/", "restricted/")
            ):
                errors.append(
                    f"materialization: artifact {artifact_id} reads forbidden raw/research source {uri}"
                )
        source = artifact_sources.get(artifact_id)
        if source is None:
            continue
        source = Path(source)
        if not source.is_file() or source.is_symlink():
            errors.append(f"materialization: payload source is not a regular file {source}")
            continue
        actual = v.sha256_bytes(source.read_bytes())
        if actual != item.get("content_hash"):
            errors.append(
                f"materialization: selected artifact {artifact_id} payload hash mismatch "
                f"expected {item.get('content_hash')} got {actual}"
            )

    if len(public_paths) != len(set(public_paths)):
        errors.append("materialization: duplicate public_path")
    return errors


def materialize_release(
    release: dict,
    *,
    catalog: v.EvidenceCatalog,
    corpora: Mapping[str, dict],
    lineage_artifact_ids: set[str],
    artifact_sources: Mapping[str, Path],
    output_dir: Path,
) -> dict:
    output_dir = Path(output_dir)
    errors = validate_materialization_inputs(
        release,
        catalog=catalog,
        corpora=corpora,
        lineage_artifact_ids=lineage_artifact_ids,
        artifact_sources=artifact_sources,
    )
    if errors:
        raise v.ValidationFailure("\n".join(errors))
    if output_dir.exists():
        raise v.ValidationFailure(f"materialization: output already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stage0-materialize-", dir=output_dir.parent))
    try:
        (stage / "release-manifest.json").write_bytes(v.canonical_json(release) + b"\n")
        for item in sorted(release["artifacts"], key=lambda x: x["public_path"]):
            public_path, path_errors = _safe_public_path(item["public_path"])
            if path_errors or public_path is None:
                raise v.ValidationFailure("\n".join(path_errors))
            target = stage / public_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(artifact_sources[item["artifact_id"]]).read_bytes())

        payload_tree_hash, files = _tree_snapshot(stage)
        metadata = {
            "materialization_schema": "stage0-materialization/v1",
            "release_id": release["release_id"],
            "release_manifest_hash": release["manifest_hash"],
            "payload_tree_hash": payload_tree_hash,
            "files": files,
        }
        (stage / "_materialization.json").write_bytes(v.canonical_json(metadata) + b"\n")
        bundle_tree_hash, bundle_files = _tree_snapshot(stage)
        os.replace(stage, output_dir)
        return {
            "release_id": release["release_id"],
            "payload_tree_hash": payload_tree_hash,
            "bundle_tree_hash": bundle_tree_hash,
            "files": bundle_files,
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--artifact-source must be ARTIFACT_ID=PATH")
    artifact_id, path = value.split("=", 1)
    if not artifact_id or not path:
        raise argparse.ArgumentTypeError("--artifact-source must be ARTIFACT_ID=PATH")
    return artifact_id, Path(path)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Materialize one validated Stage 0 promoted release")
    p.add_argument("--release", required=True)
    p.add_argument("--corpus", action="append", default=[], required=True)
    p.add_argument("--lineage", action="append", default=[], required=True)
    p.add_argument("--evidence", action="append", default=[])
    p.add_argument("--artifact-source", action="append", default=[], type=_parse_source, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = v.SchemaContext.from_repo(v.ROOT)
    evidence_paths = list(args.lineage) + list(args.evidence)
    catalog, evidence_errors, lineage_ids = v._load_evidence(
        evidence_paths, ctx, lineage_paths=set(args.lineage)
    )
    corpora, corpus_errors = v._load_corpora(args.corpus, ctx, v.ROOT, artifacts=catalog.artifacts)
    if evidence_errors or corpus_errors:
        errors = evidence_errors + corpus_errors
        if args.json:
            print(json.dumps({"status": "FAIL", "failures": errors}, sort_keys=True))
        else:
            print("FAIL materialize")
            for error in errors:
                print(f"- {error}")
        return 1
    sources = dict(args.artifact_source)
    try:
        result = materialize_release(
            v.load_json(Path(args.release)),
            catalog=catalog,
            corpora=corpora,
            lineage_artifact_ids=lineage_ids,
            artifact_sources=sources,
            output_dir=Path(args.output),
        )
    except Exception as exc:
        if args.json:
            print(json.dumps({"status": "FAIL", "failures": [str(exc)]}, sort_keys=True))
        else:
            print("FAIL materialize")
            print(f"- {exc}")
        return 1
    if args.json:
        print(json.dumps({"status": "PASS", "result": result}, sort_keys=True))
    else:
        print("PASS materialize")
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
