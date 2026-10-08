"""Executable Stage 0 repository validator.

The validator is intentionally local/static: it reads repository contracts and
fixtures, resolves JSON Schema references from the repository only, and needs no
production database or backend.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "contracts" / "schemas"
FORMAT_CHECKER = FormatChecker()

PROVENANCE_COLLECTIONS = {
    "artifact": ("artifacts", "artifact_id"),
    "run": ("runs", "run_id"),
    "code_ref": ("code_refs", "code_ref_id"),
    "config_ref": ("config_refs", "config_ref_id"),
    "model_ref": ("model_refs", "model_ref_id"),
    "environment_ref": ("environment_refs", "environment_ref_id"),
    "source_fetch": ("source_fetches", "source_fetch_id"),
    "quality_report": ("quality_reports", "quality_report_id"),
    "promotion_event": ("promotion_events", "promotion_event_id"),
}
FORBIDDEN_PREFIXES = (
    "data/raw/",
    "data/normalized/",
    "data/canonical/",
    "data/derived/",
    "research/",
    "restricted/",
)


class ValidationFailure(ValueError):
    pass


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def recompute_manifest_hash(manifest: Mapping) -> str:
    payload = dict(manifest)
    payload.pop("manifest_hash", None)
    return sha256_bytes(canonical_json(payload))


@dataclass
class SchemaContext:
    schemas: dict[str, dict]
    paths: dict[str, Path]

    @classmethod
    def from_repo(cls, root: Path = ROOT) -> "SchemaContext":
        schemas = {}
        paths = {}
        for path in sorted((root / "contracts" / "schemas").glob("*.schema.json")):
            schema = load_json(path)
            Draft202012Validator.check_schema(schema)
            schema_id = schema.get("$id")
            if not schema_id:
                raise ValidationFailure(f"schema without $id: {path}")
            if schema_id in schemas:
                raise ValidationFailure(f"duplicate schema $id: {schema_id}")
            schemas[schema_id] = schema
            paths[schema_id] = path
        return cls(schemas=schemas, paths=paths)

    def validator(self, schema_name: str) -> Draft202012Validator:
        schema = self.schemas[schema_name]
        resolver = RefResolver.from_schema(schema, store=self.schemas)
        return Draft202012Validator(
            schema, resolver=resolver, format_checker=FORMAT_CHECKER
        )


def _schema_errors(ctx: SchemaContext, schema_name: str, value, label: str) -> list[str]:
    errors = []
    for err in sorted(ctx.validator(schema_name).iter_errors(value), key=lambda e: list(e.path)):
        loc = ".".join(str(x) for x in err.path) or "<root>"
        errors.append(f"{label}: schema error at {loc}: {err.message}")
    return errors


def _index(records: Iterable[dict], key: str, label: str, errors: list[str]) -> dict:
    out = {}
    for record in records:
        value = record.get(key)
        if value in out:
            errors.append(f"{label}: duplicate {key} {value}")
        else:
            out[value] = record
    return out


@dataclass
class EvidenceCatalog:
    artifacts: dict = field(default_factory=dict)
    runs: dict = field(default_factory=dict)
    code_refs: dict = field(default_factory=dict)
    config_refs: dict = field(default_factory=dict)
    model_refs: dict = field(default_factory=dict)
    environment_refs: dict = field(default_factory=dict)
    source_fetches: dict = field(default_factory=dict)
    quality_reports: dict = field(default_factory=dict)
    promotion_events: dict = field(default_factory=dict)
    run_inputs: list[dict] = field(default_factory=list)
    run_outputs: list[dict] = field(default_factory=list)
    corpus_release_ids: set[str] = field(default_factory=set)


def catalog_from_bundle(bundle: dict, errors: list[str] | None = None) -> EvidenceCatalog:
    errors = errors if errors is not None else []
    catalog = EvidenceCatalog()
    for record_type, (collection, key) in PROVENANCE_COLLECTIONS.items():
        records = bundle.get(collection, [])
        setattr(catalog, collection, _index(records, key, collection, errors))
    catalog.run_inputs = list(bundle.get("run_inputs", []))
    catalog.run_outputs = list(bundle.get("run_outputs", []))
    catalog.corpus_release_ids = set(bundle.get("corpus_release_ids", []))
    return catalog


def add_evidence_record(catalog: EvidenceCatalog, record: dict, errors: list[str]) -> None:
    record_type = record.get("record_type")
    if record_type == "lineage_bundle":
        other = catalog_from_bundle(record, errors)
        for attr in (
            "artifacts", "runs", "code_refs", "config_refs", "model_refs",
            "environment_refs", "source_fetches", "quality_reports", "promotion_events"
        ):
            target = getattr(catalog, attr)
            for key, value in getattr(other, attr).items():
                if key in target:
                    errors.append(f"{attr}: duplicate identifier {key}")
                else:
                    target[key] = value
        catalog.run_inputs.extend(other.run_inputs)
        catalog.run_outputs.extend(other.run_outputs)
        catalog.corpus_release_ids.update(other.corpus_release_ids)
        return
    spec = PROVENANCE_COLLECTIONS.get(record_type)
    if spec:
        collection, key = spec
        target = getattr(catalog, collection)
        value = record.get(key)
        if value in target:
            errors.append(f"{collection}: duplicate {key} {value}")
        else:
            target[value] = record
        return
    if record_type == "run_input":
        catalog.run_inputs.append(record)
    elif record_type == "run_output":
        catalog.run_outputs.append(record)
    else:
        errors.append(f"unsupported evidence record_type: {record_type!r}")


def validate_lineage(bundle: dict, ctx: SchemaContext | None = None) -> list[str]:
    ctx = ctx or SchemaContext.from_repo()
    errors = _schema_errors(ctx, "provenance.schema.json", bundle, "lineage")
    catalog = catalog_from_bundle(bundle, errors)

    for report in catalog.quality_reports.values():
        errors.extend(validate_quality_report(report))

    if bundle.get("root_output_artifact_id") not in catalog.artifacts:
        errors.append("lineage: root output artifact does not exist")

    for binding_name, bindings in (("run_input", catalog.run_inputs), ("run_output", catalog.run_outputs)):
        for binding in bindings:
            if binding.get("run_id") not in catalog.runs:
                errors.append(f"{binding_name}: missing run {binding.get('run_id')}")
            if binding.get("artifact_id") not in catalog.artifacts:
                errors.append(f"{binding_name}: missing artifact {binding.get('artifact_id')}")

    for run in catalog.runs.values():
        for field_name, index in (
            ("code_ref_id", catalog.code_refs),
            ("config_ref_id", catalog.config_refs),
            ("environment_ref_id", catalog.environment_refs),
        ):
            if run.get(field_name) not in index:
                errors.append(f"run {run.get('run_id')}: missing {field_name} {run.get(field_name)}")
        model_ref_id = run.get("model_ref_id")
        if model_ref_id is not None and model_ref_id not in catalog.model_refs:
            errors.append(f"run {run.get('run_id')}: missing model_ref_id {model_ref_id}")
        corpus_id = run.get("corpus_release_id")
        if corpus_id is not None and corpus_id not in catalog.corpus_release_ids:
            errors.append(f"run {run.get('run_id')}: undeclared corpus_release_id {corpus_id}")

    for artifact in catalog.artifacts.values():
        fetch_id = artifact.get("source_fetch_id")
        if fetch_id is not None and fetch_id not in catalog.source_fetches:
            errors.append(f"artifact {artifact.get('artifact_id')}: missing source_fetch_id {fetch_id}")
        corpus_id = artifact.get("corpus_release_id")
        if corpus_id is not None and corpus_id not in catalog.corpus_release_ids:
            errors.append(f"artifact {artifact.get('artifact_id')}: undeclared corpus_release_id {corpus_id}")

    for fetch in catalog.source_fetches.values():
        raw_id = fetch.get("raw_artifact_id")
        raw = catalog.artifacts.get(raw_id)
        if raw is None:
            errors.append(f"source_fetch {fetch.get('source_fetch_id')}: missing raw artifact {raw_id}")
        elif raw.get("content_hash") != fetch.get("byte_hash"):
            errors.append(f"source_fetch {fetch.get('source_fetch_id')}: raw artifact hash mismatch")

    producers: dict[str, list[str]] = {}
    for output in catalog.run_outputs:
        producers.setdefault(output.get("artifact_id"), []).append(output.get("run_id"))
    for artifact_id, run_ids in producers.items():
        artifact = catalog.artifacts.get(artifact_id)
        if artifact and artifact.get("immutable") is True and len(set(run_ids)) > 1:
            errors.append(
                f"artifact {artifact_id}: duplicate producing runs {sorted(set(run_ids))}"
            )

    if not errors:
        try:
            result = reconstruct_lineage(bundle, bundle["root_output_artifact_id"])
            if not result["direct_input_artifact_ids"]:
                errors.append("lineage reconstruction: root producing run has no input artifacts")
            if not result["source_fetch_ids"]:
                errors.append("lineage reconstruction: root lineage has no relevant source fetch")
            if not result["corpus_release_ids"]:
                errors.append("lineage reconstruction: root lineage has no relevant corpus release")
        except ValidationFailure as exc:
            errors.append(f"lineage reconstruction: {exc}")
    return errors


def reconstruct_lineage(bundle: dict, output_artifact_id: str) -> dict:
    catalog = catalog_from_bundle(bundle)
    if output_artifact_id not in catalog.artifacts:
        raise ValidationFailure(f"unknown output artifact {output_artifact_id}")

    producer_map: dict[str, list[str]] = {}
    inputs_by_run: dict[str, list[str]] = {}
    consumers_by_artifact: dict[str, list[str]] = {}
    outputs_by_run: dict[str, list[str]] = {}
    for item in catalog.run_outputs:
        producer_map.setdefault(item["artifact_id"], []).append(item["run_id"])
        outputs_by_run.setdefault(item["run_id"], []).append(item["artifact_id"])
    for item in catalog.run_inputs:
        inputs_by_run.setdefault(item["run_id"], []).append(item["artifact_id"])
        consumers_by_artifact.setdefault(item["artifact_id"], []).append(item["run_id"])

    root_producers = sorted(set(producer_map.get(output_artifact_id, [])))
    if len(root_producers) != 1:
        raise ValidationFailure(
            f"output {output_artifact_id} must have exactly one producer, found {root_producers}"
        )
    root_run_id = root_producers[0]

    ancestors: set[str] = set()
    descendants: set[str] = set()
    source_fetch_ids: set[str] = set()
    code_ref_ids: set[str] = set()
    config_ref_ids: set[str] = set()
    model_ref_ids: set[str] = set()
    environment_ref_ids: set[str] = set()
    corpus_release_ids: set[str] = set()
    visited_up: set[str] = set()
    visited_down: set[str] = set()

    def visit_up(artifact_id: str, root: bool = False) -> None:
        if artifact_id in visited_up:
            return
        visited_up.add(artifact_id)
        artifact = catalog.artifacts.get(artifact_id)
        if artifact is None:
            raise ValidationFailure(f"missing artifact {artifact_id}")
        if not root:
            ancestors.add(artifact_id)
        corpus_id = artifact.get("corpus_release_id")
        if corpus_id is not None:
            corpus_release_ids.add(corpus_id)
        fetch_id = artifact.get("source_fetch_id")
        if fetch_id is not None:
            fetch = catalog.source_fetches.get(fetch_id)
            if fetch is None:
                raise ValidationFailure(f"missing source fetch {fetch_id}")
            source_fetch_ids.add(fetch_id)
            raw_id = fetch.get("raw_artifact_id")
            if raw_id is not None and raw_id != artifact_id:
                visit_up(raw_id)
        producers = sorted(set(producer_map.get(artifact_id, [])))
        if len(producers) > 1:
            raise ValidationFailure(f"duplicate producer for artifact {artifact_id}")
        if not producers:
            return
        run = catalog.runs.get(producers[0])
        if run is None:
            raise ValidationFailure(f"missing producing run {producers[0]}")
        for field_name, index, sink in (
            ("code_ref_id", catalog.code_refs, code_ref_ids),
            ("config_ref_id", catalog.config_refs, config_ref_ids),
            ("environment_ref_id", catalog.environment_refs, environment_ref_ids),
        ):
            ref = run.get(field_name)
            if ref not in index:
                raise ValidationFailure(f"missing {field_name} {ref}")
            sink.add(ref)
        model_ref = run.get("model_ref_id")
        if model_ref is not None:
            if model_ref not in catalog.model_refs:
                raise ValidationFailure(f"missing model_ref_id {model_ref}")
            model_ref_ids.add(model_ref)
        corpus_id = run.get("corpus_release_id")
        if corpus_id is not None:
            if corpus_id not in catalog.corpus_release_ids:
                raise ValidationFailure(f"undeclared corpus release {corpus_id}")
            corpus_release_ids.add(corpus_id)
        for input_id in sorted(inputs_by_run.get(run["run_id"], [])):
            visit_up(input_id)

    def visit_down(artifact_id: str) -> None:
        if artifact_id in visited_down:
            return
        visited_down.add(artifact_id)
        for run_id in sorted(set(consumers_by_artifact.get(artifact_id, []))):
            if run_id not in catalog.runs:
                raise ValidationFailure(f"missing consuming run {run_id}")
            for child_id in sorted(set(outputs_by_run.get(run_id, []))):
                if child_id != output_artifact_id:
                    descendants.add(child_id)
                visit_down(child_id)

    visit_up(output_artifact_id, root=True)
    visit_down(output_artifact_id)

    direct_inputs = sorted(set(inputs_by_run.get(root_run_id, [])))
    direct_children = sorted(
        {
            child
            for run_id in consumers_by_artifact.get(output_artifact_id, [])
            for child in outputs_by_run.get(run_id, [])
        }
    )
    return {
        "root_output_artifact_id": output_artifact_id,
        "root_producing_run_id": root_run_id,
        "direct_input_artifact_ids": direct_inputs,
        "ancestor_artifact_ids": sorted(ancestors),
        "descendant_artifact_ids": sorted(descendants),
        "direct_child_artifact_ids": direct_children,
        "source_fetch_ids": sorted(source_fetch_ids),
        "corpus_release_ids": sorted(corpus_release_ids),
        "code_ref_ids": sorted(code_ref_ids),
        "config_ref_ids": sorted(config_ref_ids),
        "model_ref_ids": sorted(model_ref_ids),
        "environment_ref_ids": sorted(environment_ref_ids),
    }


def _safe_repo_path(root: Path, uri: str) -> Path | None:
    if not isinstance(uri, str) or not uri or Path(uri).is_absolute():
        return None
    path = (root / uri).resolve()
    root_resolved = root.resolve()
    if path != root_resolved and root_resolved not in path.parents:
        return None
    return path


def validate_corpus_manifest(
    manifest: dict,
    *,
    root: Path = ROOT,
    ctx: SchemaContext | None = None,
    artifacts: Mapping[str, dict] | None = None,
) -> list[str]:
    ctx = ctx or SchemaContext.from_repo(root)
    errors = _schema_errors(ctx, "corpus-release.schema.json", manifest, "corpus manifest")

    article_ids = manifest.get("canonical_article_ids", [])
    if manifest.get("article_count") != len(article_ids):
        errors.append("corpus manifest: article_count does not equal canonical_article_ids length")
    if len(article_ids) != len(set(article_ids)):
        errors.append("corpus manifest: duplicate canonical_article_ids")

    inputs = manifest.get("input_artifacts", [])
    if inputs and artifacts is None:
        errors.append("corpus manifest: artifact catalog required for declared input_artifacts")
    if artifacts is not None:
        for item in inputs:
            artifact = artifacts.get(item.get("artifact_id"))
            if artifact is None:
                errors.append(f"corpus manifest: missing input artifact {item.get('artifact_id')}")
            elif artifact.get("content_hash") != item.get("content_hash"):
                errors.append(f"corpus manifest: input artifact hash mismatch {item.get('artifact_id')}")

    for key in ("inclusion_policy", "exclusion_policy"):
        policy = manifest.get(key, {})
        path = _safe_repo_path(root, policy.get("uri"))
        if path is None or not path.is_file():
            errors.append(f"corpus manifest: missing/read-protected {key} {policy.get('uri')}")
            continue
        actual = sha256_bytes(path.read_bytes())
        if actual != policy.get("content_hash"):
            errors.append(f"corpus manifest: {key} hash mismatch")

    expected = recompute_manifest_hash(manifest)
    if manifest.get("manifest_hash") != expected:
        errors.append(
            f"corpus manifest: manifest_hash mismatch expected {expected} got {manifest.get('manifest_hash')}"
        )
    return errors


def _publication_allowed(access: dict, basis: str) -> bool:
    return (
        access.get("access_class") == "public"
        and access.get("publication_permissions", {}).get(basis) == "allow"
    )


def effective_quality_report_status(report: Mapping) -> str | None:
    """Return fail > warn > pass aggregate from checks, or None if not computable."""
    statuses = [check.get("status") for check in report.get("checks", [])]
    if not statuses or any(status not in {"pass", "warn", "fail"} for status in statuses):
        return None
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def validate_quality_report(report: Mapping) -> list[str]:
    """Validate executable report-level status consistency."""
    report_id = report.get("quality_report_id")
    effective = effective_quality_report_status(report)
    if effective is None:
        return [f"quality_report {report_id}: unable to compute effective status from checks"]
    declared = report.get("status")
    if declared != effective:
        return [
            f"quality_report {report_id}: declared status {declared!r} "
            f"does not match effective status {effective!r}"
        ]
    return []


def quality_report_applicable_artifacts(
    report: Mapping,
    event_artifact_ids: Iterable[str],
    run_outputs: Sequence[dict],
) -> set[str]:
    """Return only explicitly covered event artifacts; run scope is direct-output only."""
    event_ids = set(event_artifact_ids)
    subject_artifact_id = report.get("subject_artifact_id")
    if subject_artifact_id is not None:
        return {subject_artifact_id} & event_ids
    subject_run_id = report.get("subject_run_id")
    if subject_run_id is None:
        return set()
    direct_outputs = {
        item.get("artifact_id")
        for item in run_outputs
        if item.get("run_id") == subject_run_id
    }
    return direct_outputs & event_ids


def validate_promotion_event_quality(
    event: Mapping,
    *,
    quality_reports: Mapping[str, dict],
    run_outputs: Sequence[dict],
) -> tuple[list[str], bool]:
    """Validate exact evidence semantics; bool means the event qualifies as promotion."""
    errors: list[str] = []
    event_id = event.get("promotion_event_id")
    decision = event.get("decision")
    artifact_ids = set(event.get("artifact_ids", []))
    covered: set[str] = set()

    for report_id in event.get("quality_report_ids", []):
        report = quality_reports.get(report_id)
        if report is None:
            errors.append(f"promotion_event {event_id}: missing quality_report {report_id}")
            continue

        report_errors = validate_quality_report(report)
        errors.extend(report_errors)
        applicable = quality_report_applicable_artifacts(report, artifact_ids, run_outputs)
        if not applicable:
            errors.append(
                f"promotion_event {event_id}: quality_report {report_id} "
                "has no applicable artifacts in this event"
            )

        if decision == "promoted":
            if report.get("status") != "pass":
                errors.append(
                    f"promotion_event {event_id}: quality_report {report_id} "
                    f"status {report.get('status')!r} is not qualifying PASS evidence"
                )
            if not report_errors and report.get("status") == "pass":
                covered.update(applicable)

    if decision == "promoted":
        for artifact_id in sorted(artifact_ids - covered):
            errors.append(
                f"promotion_event {event_id}: artifact {artifact_id} "
                "lacks qualifying PASS quality coverage"
            )
        return errors, not errors
    return errors, False


def validate_release_manifest(
    manifest: dict,
    *,
    ctx: SchemaContext | None = None,
    artifacts: Mapping[str, dict] | None = None,
    corpus_manifests: Mapping[str, dict] | None = None,
    promotion_events: Mapping[str, dict] | None = None,
    quality_reports: Mapping[str, dict] | None = None,
    run_outputs: Sequence[dict] | None = None,
    lineage_artifact_ids: set[str] | None = None,
) -> list[str]:
    ctx = ctx or SchemaContext.from_repo()
    errors = _schema_errors(ctx, "release-manifest.schema.json", manifest, "release manifest")
    artifacts = artifacts or {}
    corpus_manifests = corpus_manifests or {}
    promotion_events = promotion_events or {}
    quality_reports = quality_reports or {}
    run_outputs = list(run_outputs or [])
    lineage_artifact_ids = set(lineage_artifact_ids or set())

    expected = recompute_manifest_hash(manifest)
    if manifest.get("manifest_hash") != expected:
        errors.append(
            f"release manifest: manifest_hash mismatch expected {expected} got {manifest.get('manifest_hash')}"
        )

    corpus_id = manifest.get("corpus_release_id")
    if corpus_id is not None and corpus_id not in corpus_manifests:
        errors.append(f"release manifest: unresolved corpus_release_id {corpus_id}")

    release_artifact_ids = []
    for item in manifest.get("artifacts", []):
        artifact_id = item.get("artifact_id")
        release_artifact_ids.append(artifact_id)
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            errors.append(f"release manifest: missing artifact {artifact_id}")
            continue
        for field_name in ("artifact_id", "content_hash", "schema_version"):
            if item.get(field_name) != artifact.get(field_name):
                errors.append(f"release manifest: artifact {artifact_id} {field_name} mismatch")
        if "artifact_type" in item and "artifact_type" in artifact:
            if item.get("artifact_type") != artifact.get("artifact_type"):
                errors.append(f"release manifest: artifact {artifact_id} artifact_type mismatch")
        if item.get("access_license") != artifact.get("access_license"):
            errors.append(f"release manifest: artifact {artifact_id} access_license mismatch")
        basis = item.get("publication_permission_basis")
        if not _publication_allowed(artifact.get("access_license", {}), basis):
            errors.append(f"release manifest: artifact {artifact_id} is not publishable for {basis}")
        artifact_corpus = artifact.get("corpus_release_id")
        if artifact_corpus is not None and artifact_corpus != corpus_id:
            errors.append(
                f"release manifest: artifact {artifact_id} corpus mismatch {artifact_corpus} != {corpus_id}"
            )

    if manifest.get("status") == "promoted":
        event_ids = manifest.get("promotion_event_ids", [])
        covered: set[str] = set()
        for event_id in event_ids:
            event = promotion_events.get(event_id)
            if event is None:
                errors.append(f"release manifest: missing promotion_event {event_id}")
                continue

            event_qualifies = True
            if event.get("decision") != "promoted":
                errors.append(f"release manifest: promotion_event {event_id} decision is not promoted")
                event_qualifies = False
            if event.get("target_release_id") != manifest.get("release_id"):
                errors.append(f"release manifest: promotion_event {event_id} wrong target_release_id")
                event_qualifies = False

            quality_errors, quality_qualifies = validate_promotion_event_quality(
                event, quality_reports=quality_reports, run_outputs=run_outputs
            )
            errors.extend(f"release manifest: {error}" for error in quality_errors)
            if not quality_qualifies:
                event_qualifies = False
            if event_qualifies:
                covered.update(event.get("artifact_ids", []))

        for artifact_id in release_artifact_ids:
            if artifact_id not in covered:
                errors.append(f"release manifest: artifact {artifact_id} lacks promotion coverage")
        producer_counts: dict[str, set[str]] = {}
        for item in run_outputs:
            producer_counts.setdefault(item.get("artifact_id"), set()).add(item.get("run_id"))
        for artifact_id in release_artifact_ids:
            if len(producer_counts.get(artifact_id, set())) != 1:
                errors.append(
                    f"release manifest: promoted artifact {artifact_id} lacks unique producing-run lineage"
                )
            if artifact_id not in lineage_artifact_ids:
                errors.append(
                    f"release manifest: promoted artifact {artifact_id} lacks validated complete lineage"
                )
    return errors


def _policy_files(root: Path) -> list[Path]:
    files = list((root / "contracts" / "policies").glob("*.json"))
    files.extend((root / "contracts" / "manifests" / "policies").glob("*.json"))
    return sorted(files)


def validate_contracts(root: Path = ROOT, ctx: SchemaContext | None = None) -> list[str]:
    errors: list[str] = []
    try:
        ctx = ctx or SchemaContext.from_repo(root)
    except Exception as exc:
        return [f"schemas: {exc}"]

    mappings = [
        (root / "contracts/manifests/empty_corpus.manifest.json", "corpus-release.schema.json"),
        (root / "contracts/manifests/empty_release.manifest.json", "release-manifest.schema.json"),
        (root / "contracts/manifests/minimal_lineage.example.json", "provenance.schema.json"),
        (root / "contracts/examples/model_compute_asset.example.json", "provenance.schema.json"),
        (root / "contracts/examples/nonmodel_compute_asset.example.json", "provenance.schema.json"),
        (root / "contracts/examples/identity_resolution_history.example.json", "entities.schema.json"),
    ]
    for path, schema_name in mappings:
        try:
            value = load_json(path)
        except Exception as exc:
            errors.append(f"{path.relative_to(root)}: unreadable JSON: {exc}")
            continue
        errors.extend(_schema_errors(ctx, schema_name, value, str(path.relative_to(root))))

    if "policy.schema.json" not in ctx.schemas:
        errors.append("contracts: policy.schema.json missing")
    else:
        for path in _policy_files(root):
            try:
                value = load_json(path)
            except Exception as exc:
                errors.append(f"{path.relative_to(root)}: unreadable JSON: {exc}")
                continue
            errors.extend(
                _schema_errors(ctx, "policy.schema.json", value, str(path.relative_to(root)))
            )
    return errors


def validate_public_paths(paths: Iterable[str]) -> list[str]:
    errors = []
    for raw in paths:
        path = raw.replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        path = path.lstrip("/")
        if any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            errors.append(f"repository boundary: forbidden tracked path {raw}")
            continue
        name = Path(path).name
        lower = name.lower()
        if lower == ".env" or (lower.startswith(".env.") and lower != ".env.example"):
            errors.append(f"repository boundary: forbidden secret path {raw}")
        elif lower.startswith("secrets.") or lower.endswith((".pem", ".key", ".p12", ".pfx")):
            errors.append(f"repository boundary: forbidden secret path {raw}")
    return errors


def tracked_paths(root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def validate_repository_boundary(root: Path = ROOT) -> list[str]:
    try:
        return validate_public_paths(tracked_paths(root))
    except Exception as exc:
        return [f"repository boundary: unable to inspect git index: {exc}"]


def aggregate_stage0(root: Path = ROOT) -> list[str]:
    ctx = SchemaContext.from_repo(root)
    errors = []
    errors.extend(validate_contracts(root, ctx))

    lineage = load_json(root / "contracts/manifests/minimal_lineage.example.json")
    lineage_errors = validate_lineage(lineage, ctx)
    errors.extend(lineage_errors)
    catalog = catalog_from_bundle(lineage)

    corpus = load_json(root / "contracts/manifests/empty_corpus.manifest.json")
    errors.extend(validate_corpus_manifest(corpus, root=root, ctx=ctx, artifacts=catalog.artifacts))

    release = load_json(root / "contracts/manifests/empty_release.manifest.json")
    errors.extend(
        validate_release_manifest(
            release,
            ctx=ctx,
            artifacts={},
            corpus_manifests={},
            promotion_events={},
            quality_reports={},
            run_outputs=[],
        )
    )

    # Aggregate Stage 0 also exercises the promoted-release quality predicate
    # with a deterministic committed smoke fixture rather than only a draft release.
    smoke_ids = load_json(root / "tests/fixtures/promotion_quality_cases.json")
    promoted_lineage = copy.deepcopy(lineage)
    promoted_artifact = promoted_lineage["artifacts"][-1]
    promoted_artifact["access_license"] = {
        "access_class": "public",
        "license_class": "fixture",
        "license_status": "confirmed",
        "license_evidence_ref": "fixture",
        "publication_permissions": {
            "metadata": "allow",
            "raw_text": "deny",
            "derived": "allow",
        },
    }
    promoted_catalog = catalog_from_bundle(promoted_lineage)

    promoted_corpus = copy.deepcopy(corpus)
    promoted_corpus["corpus_release_id"] = promoted_lineage["corpus_release_ids"][0]
    promoted_corpus["manifest_hash"] = recompute_manifest_hash(promoted_corpus)

    report_id = smoke_ids["reports"]["artifact_pass"]
    event_id = smoke_ids["events"]["primary"]
    release_id = smoke_ids["release"]
    report = {
        "record_type": "quality_report",
        "quality_report_id": report_id,
        "subject_artifact_id": promoted_artifact["artifact_id"],
        "status": "pass",
        "checks": [{"check_id": "stage0_smoke", "status": "pass"}],
        "created_at": "2026-10-08T00:19:00Z",
    }
    event = {
        "record_type": "promotion_event",
        "promotion_event_id": event_id,
        "artifact_ids": [promoted_artifact["artifact_id"]],
        "quality_report_ids": [report_id],
        "decision": "promoted",
        "target_release_id": release_id,
        "created_at": "2026-10-08T00:20:00Z",
    }
    promoted_release = {
        "manifest_version": "1.0.0",
        "release_id": release_id,
        "status": "promoted",
        "corpus_release_id": promoted_lineage["corpus_release_ids"][0],
        "artifacts": [{
            "artifact_id": promoted_artifact["artifact_id"],
            "artifact_type": promoted_artifact["artifact_type"],
            "content_hash": promoted_artifact["content_hash"],
            "schema_version": promoted_artifact["schema_version"],
            "role": "stage0_smoke",
            "public_path": "data/stage0-smoke.json",
            "publication_permission_basis": "derived",
            "access_license": copy.deepcopy(promoted_artifact["access_license"]),
        }],
        "promotion_event_ids": [event_id],
        "manifest_hash": "",
        "created_at": "2026-10-08T00:20:00Z",
        "superseded_by": None,
    }
    promoted_release["manifest_hash"] = recompute_manifest_hash(promoted_release)
    errors.extend(
        validate_release_manifest(
            promoted_release,
            ctx=ctx,
            artifacts=promoted_catalog.artifacts,
            corpus_manifests={
                promoted_corpus["corpus_release_id"]: promoted_corpus
            },
            promotion_events={event_id: event},
            quality_reports={report_id: report},
            run_outputs=promoted_catalog.run_outputs,
            lineage_artifact_ids={promoted_artifact["artifact_id"]},
        )
    )

    errors.extend(validate_repository_boundary(root))
    return errors


def _load_evidence(
    paths: Sequence[str],
    ctx: SchemaContext,
    *,
    lineage_paths: set[str] | None = None,
) -> tuple[EvidenceCatalog, list[str], set[str]]:
    errors: list[str] = []
    catalog = EvidenceCatalog()
    lineage_paths = set(lineage_paths or set())
    validated_lineage_artifact_ids: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path)
        record = load_json(path)
        if raw_path in lineage_paths:
            if record.get("record_type") != "lineage_bundle":
                errors.append(f"{path}: --lineage input must be a lineage_bundle")
            else:
                lineage_errors = validate_lineage(record, ctx)
                errors.extend(f"{path}: {error}" for error in lineage_errors)
                if not lineage_errors:
                    validated_lineage_artifact_ids.add(record["root_output_artifact_id"])
        else:
            errors.extend(_schema_errors(ctx, "provenance.schema.json", record, str(path)))
            if record.get("record_type") == "quality_report":
                errors.extend(validate_quality_report(record))
        add_evidence_record(catalog, record, errors)
    return catalog, errors, validated_lineage_artifact_ids


def _load_corpora(
    paths: Sequence[str],
    ctx: SchemaContext,
    root: Path,
    artifacts: Mapping[str, dict] | None = None,
) -> tuple[dict, list[str]]:
    corpora = {}
    errors = []
    for raw_path in paths:
        path = Path(raw_path)
        value = load_json(path)
        errors.extend(validate_corpus_manifest(value, root=root, ctx=ctx, artifacts=artifacts))
        corpus_id = value.get("corpus_release_id")
        if corpus_id in corpora:
            errors.append(f"corpus catalog: duplicate corpus_release_id {corpus_id}")
        corpora[corpus_id] = value
    return corpora, errors


def _emit(command: str, errors: list[str], payload=None, json_mode: bool = False) -> int:
    if json_mode:
        print(json.dumps(
            {"command": command, "status": "PASS" if not errors else "FAIL",
             "failures": errors, "result": payload},
            ensure_ascii=False, sort_keys=True, indent=2,
        ))
    elif errors:
        print(f"FAIL {command}")
        for error in errors:
            print(f"- {error}")
    else:
        print(f"PASS {command}")
        if payload is not None:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pro_Adherence Stage 0 validator")
    parser.add_argument("--json", action="store_true", help="emit JSON result")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("contracts")
    p_corpus = sub.add_parser("corpus")
    p_corpus.add_argument("manifest")
    p_corpus.add_argument("--catalog", help="lineage bundle supplying artifact catalog")
    p_release = sub.add_parser("release")
    p_release.add_argument("manifest")
    p_release.add_argument("--lineage", action="append", default=[])
    p_release.add_argument("--corpus", action="append", default=[])
    p_release.add_argument("--evidence", action="append", default=[])
    p_lineage = sub.add_parser("lineage")
    p_lineage.add_argument("bundle")
    p_lineage.add_argument("--output-id")
    sub.add_parser("boundary")
    sub.add_parser("stage0")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = ROOT
    try:
        ctx = SchemaContext.from_repo(root)
        if args.command == "contracts":
            return _emit("contracts", validate_contracts(root, ctx), json_mode=args.json)
        if args.command == "corpus":
            manifest = load_json(Path(args.manifest))
            artifacts = None
            if args.catalog:
                bundle = load_json(Path(args.catalog))
                line_errors = validate_lineage(bundle, ctx)
                if line_errors:
                    return _emit("corpus", line_errors, json_mode=args.json)
                artifacts = catalog_from_bundle(bundle).artifacts
            return _emit(
                "corpus",
                validate_corpus_manifest(manifest, root=root, ctx=ctx, artifacts=artifacts),
                json_mode=args.json,
            )
        if args.command == "lineage":
            bundle = load_json(Path(args.bundle))
            errors = validate_lineage(bundle, ctx)
            payload = None
            if not errors:
                payload = reconstruct_lineage(
                    bundle, args.output_id or bundle["root_output_artifact_id"]
                )
            return _emit("lineage", errors, payload=payload, json_mode=args.json)
        if args.command == "release":
            manifest = load_json(Path(args.manifest))
            evidence_paths = list(args.lineage) + list(args.evidence)
            catalog, evidence_errors, lineage_artifact_ids = _load_evidence(
                evidence_paths, ctx, lineage_paths=set(args.lineage)
            )
            corpora, corpus_errors = _load_corpora(
                args.corpus, ctx, root, artifacts=catalog.artifacts
            )
            errors = evidence_errors + corpus_errors
            errors.extend(
                validate_release_manifest(
                    manifest,
                    ctx=ctx,
                    artifacts=catalog.artifacts,
                    corpus_manifests=corpora,
                    promotion_events=catalog.promotion_events,
                    quality_reports=catalog.quality_reports,
                    run_outputs=catalog.run_outputs,
                    lineage_artifact_ids=lineage_artifact_ids,
                )
            )
            return _emit("release", errors, json_mode=args.json)
        if args.command == "boundary":
            return _emit("boundary", validate_repository_boundary(root), json_mode=args.json)
        if args.command == "stage0":
            return _emit("stage0", aggregate_stage0(root), json_mode=args.json)
    except Exception as exc:
        return _emit(args.command, [f"validator exception: {exc}"], json_mode=args.json)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
