"""Fail-closed Stage3 source/model preflight; zero downloads and zero inference.

Public GitHub contains immutable *upstream commit candidates* only, not private
source rows or model weights. The verified local private roster is independently
stored in restricted Drive. File-level provenance, binary checksums and a
compatible exact runtime lock are mandatory BEFORE an owner-authorized run.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from .stage3_runtime_guard import audit_runtime_versions, audit_transformers_security


class Stage3PreflightError(ValueError):
    pass


HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXACT_UPSTREAM = {
    "pubmedbert": (
        "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract",
        "d673b8835373c6fa116d6d8006b33d48734e305d",
    ),
    "specter2_base": (
        "allenai/specter2_base",
        "3447645e1def9117997203454fa4495937bfbd83",
    ),
    "specter2_proximity": (
        "allenai/specter2",
        "2081559630a80fc5851d8f798a05ba81e9468089",
    ),
}
FROZEN_ARCHIVE_SHA = "a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127"
PRIVATE_COHORT_SHA = "c080449e4a3450e6ff2e396c0463d05960d8b1cd101f42c7f99ccf3ab202e234"


def sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_static_preflight_config(config: dict) -> None:
    """Check owner-backed cohort and full HF refs; never silently use 'main'."""
    if config.get("schema") != "pro-adherence-stage3-model-preflight/v1":
        raise Stage3PreflightError("invalid Stage3 preflight schema")
    if config.get("status") != "PLANNING_ONLY_NO_INFERENCE":
        raise Stage3PreflightError("Stage3 must remain planning-only")
    if config.get("publication_authorized") is not False:
        raise Stage3PreflightError("private data cannot be published")
    cohort = config.get("owner_approved_analytical_population", {})
    if (cohort.get("frozen_stage2_sha256") != FROZEN_ARCHIVE_SHA
        or cohort.get("private_manifest_sha256") != PRIVATE_COHORT_SHA
        or cohort.get("canonical_count") != 57293
        or cohort.get("eligible_count") != 57204
        or cohort.get("source_counts") != {
            "book_only_excluded": 86, "confirmed_retraction_excluded": 3,
            "peer_review_unknown_flagged": 19,
            "wos_nr_cr_flagged": 413,
        }):
        raise Stage3PreflightError("Stage3 frozen cohort identity does not match owner policy")
    upstream = config.get("upstream_revisions")
    if not isinstance(upstream, dict) or set(upstream) != set(EXACT_UPSTREAM):
        raise Stage3PreflightError("missing/extra Stage3 upstream model identity")
    for key, (repo, revision) in EXACT_UPSTREAM.items():
        item = upstream[key]
        if (item.get("repository") != repo
            or item.get("revision") != revision
            or not HEX40.fullmatch(str(item.get("revision", "")))
            or item.get("source") != f"https://huggingface.co/{repo}/commit/{revision}"):
            raise Stage3PreflightError(f"unverified upstream revision: {key}")
        files = item.get("required_files")
        if not isinstance(files, list) or not files or len(files) != len(set(files)):
            raise Stage3PreflightError(f"invalid required file inventory: {key}")
        for file in files:
            if (not isinstance(file, str) or file in {"", ".", ".."}
                or Path(file).name != file or "/" in file or "\\" in file):
                raise Stage3PreflightError(f"unsafe model filename: {key}")
    pending = config.get("pending_before_compute", {})
    if not isinstance(pending, dict) or not pending or any(v is not True for v in pending.values()):
        raise Stage3PreflightError("must explicitly declare pending compute checks")


def audit_stage3_preflight(
    config: dict, *, private_cohort_path: Path | None = None,
    model_cache_dirs: dict[str, Path] | None = None,
    authoritative_file_hashes: dict[str, dict[str, str]] | None = None,
    exact_runtime_lock: dict | None = None,
    exact_runtime_lock_path: Path | None = None,
    graph_snapshot: dict | None = None,
    graph_artifact_paths: dict[str, Path] | None = None,
    compute_authorized: bool = False,
) -> dict:
    """Report blocking conditions without loading model weights or touching web.

    An authoritative digest must come from provider metadata/validated release
    evidence and is separately compared against every cached file's ACTUAL bytes.
    Supplying a cache path without provider SHA evidence never certifies weights.
    """
    verify_static_preflight_config(config)
    blocks: dict[str, list[str]] = {
        "pubmedbert": [], "specter2": [], "node2vec": [],
    }
    if private_cohort_path is None:
        for key in blocks:
            blocks[key].append("PRIVATE_COHORT_FILE_NOT_SUPPLIED")
    else:
        if sha256_path(Path(private_cohort_path)) != PRIVATE_COHORT_SHA:
            raise Stage3PreflightError("private cohort bytes SHA256 mismatch")

    revisions = config["upstream_revisions"]
    for lens, components in {
        "pubmedbert": ("pubmedbert",),
        "specter2": ("specter2_base", "specter2_proximity"),
    }.items():
        for component in components:
            dirname = (model_cache_dirs or {}).get(component)
            expected = (authoritative_file_hashes or {}).get(component)
            if dirname is None or expected is None:
                blocks[lens].append(f"ARTIFACT_BYTES_OR_PROVENANCE_NOT_VERIFIED:{component}")
                continue
            required = revisions[component]["required_files"]
            if set(expected) != set(required):
                raise Stage3PreflightError(f"provider digest inventory incomplete: {component}")
            for file in required:
                trusted = expected[file]
                if not HEX64.fullmatch(str(trusted)):
                    raise Stage3PreflightError(f"invalid provider digest: {component}/{file}")
                cached = Path(dirname) / file
                if not cached.is_file():
                    blocks[lens].append(f"REQUIRED_MODEL_FILE_NOT_PRESENT:{component}/{file}")
                    continue
                if sha256_path(cached) != trusted:
                    raise Stage3PreflightError(f"model file checksum mismatch: {component}/{file}")

    runtime = exact_runtime_lock or {}
    runtime_path = Path(exact_runtime_lock_path) if exact_runtime_lock_path else None
    runtime_hash = str(runtime.get("lockfile_sha256", ""))
    runtime_bytes_match = (
        runtime_path is not None and runtime_path.is_file()
        and HEX64.fullmatch(runtime_hash) is not None
        and sha256_path(runtime_path) == runtime_hash
    )
    for lens, packages in {
        "pubmedbert": ("python", "torch", "transformers", "tokenizers"),
        "specter2": ("python", "torch", "transformers", "tokenizers", "adapters"),
        "node2vec": ("python", "node2vec_backend"),
    }.items():
        if (not HEX64.fullmatch(runtime_hash)
            or any(not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+(?:[.+a-zA-Z0-9-]*)",
                                      str(runtime.get(pkg, ""))) for pkg in packages)):
            blocks[lens].append("EXACT_COMPATIBLE_RUNTIME_NOT_VERIFIED")
        if not runtime_bytes_match:
            blocks[lens].append("RUNTIME_LOCK_BYTES_NOT_VERIFIED")
    if isinstance(runtime.get("transformers"), str) and isinstance(runtime.get("adapters"), str):
        try:
            guard = audit_runtime_versions(
                transformers=runtime["transformers"], adapters=runtime["adapters"])
        except ValueError as exc:
            raise Stage3PreflightError("invalid exact runtime version") from exc
        blocks["specter2"].extend(guard["blockers"])
    if isinstance(runtime.get("transformers"), str):
        try:
            blocks["pubmedbert"].extend(audit_transformers_security(runtime["transformers"]))
        except ValueError as exc:
            raise Stage3PreflightError("invalid transformers security version") from exc

    if graph_snapshot is None:
        blocks["node2vec"].append("CITATION_GRAPH_SNAPSHOT_NOT_VERIFIED")
    else:
        for field in ("source_directed_graph_sha256", "training_undirected_graph_sha256",
                      "sorted_node_mapping_sha256"):
            if not HEX64.fullmatch(str(graph_snapshot.get(field, ""))):
                raise Stage3PreflightError(f"node2vec graph missing identity: {field}")
        if (graph_snapshot.get("eligible_node_count") != 57204
            or graph_snapshot.get("training_orientation") != "undirected"
            or graph_snapshot.get("source_orientation") != "directed"
            or graph_snapshot.get("weights") != "binary_unit"):
            raise Stage3PreflightError("node2vec owner-approved graph policy mismatch")
        # A 64-character label proves no bytes. Compare the actual three files.
        for field in ("source_directed_graph_sha256", "training_undirected_graph_sha256",
                      "sorted_node_mapping_sha256"):
            f = (graph_artifact_paths or {}).get(field)
            if f is None or not Path(f).is_file():
                blocks["node2vec"].append(f"GRAPH_ARTIFACT_BYTES_NOT_VERIFIED:{field}")
            elif sha256_path(Path(f)) != graph_snapshot[field]:
                raise Stage3PreflightError(f"node2vec graph artifact SHA256 mismatch: {field}")

    if not compute_authorized:
        for key in blocks:
            blocks[key].append("OWNER_COMPUTE_GATE_NOT_GRANTED")
    return {
        "schema": "pro-adherence-stage3-model-preflight-result/v1",
        "preflight_only": True,
        "publication_authorized": False,
        "owner_compute_authorized": bool(compute_authorized),
        "upstream_commit_refs_match_approved_config": True,
        "upstream_commit_refs_verified": False,  # no provider readback in offline CLI
        "private_cohort_sha256": PRIVATE_COHORT_SHA,
        "lenses": {
            lens: {
                "ready_for_owner_authorized_compute": len(blockers) == 0,
                "blockers": sorted(set(blockers)),
            } for lens, blockers in blocks.items()
        },
    }


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf8") as handle:
        config = json.load(handle)
    verify_static_preflight_config(config)
    return config

def main() -> None:
    """Print planning-only blocked status. Does not read private data by default."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path,
        default=Path("configs/stage3/model_preflight_pins.json"),
    )
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    report = audit_stage3_preflight(load_config(args.config))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_ready and not all(
        state["ready_for_owner_authorized_compute"]
        for state in report["lenses"].values()
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
