"""Metadata-only Stage3 Hugging Face revision inventory.

Queries ONLY model metadata JSON for the exact approved revisions.
Never calls /resolve/, downloads weights/tokenizers, imports transformers,
loads pickle, or claims that provider LFS OIDs are locally checked bytes.
Offline fixture validation is available and is what CI exercises.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .stage3_preflight import load_config, Stage3PreflightError

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
COMPONENTS = ("pubmedbert", "specter2_base", "specter2_proximity")
REQUIRED_LFS = {"pytorch_model.bin", "pytorch_adapter.bin"}
MAX_METADATA_BYTES = 2 * 1024 * 1024


def audit_component(spec: dict, provider_response: dict) -> dict:
    """Check identity and inventory; provider metadata is NOT a bytes readback."""
    repo, revision = spec["repository"], spec["revision"]
    if provider_response.get("sha") != revision or not SHA40.fullmatch(revision):
        raise Stage3PreflightError("HF metadata immutable revision mismatch")
    sibling_list = provider_response.get("siblings")
    if not isinstance(sibling_list, list):
        raise Stage3PreflightError("HF metadata has no file inventory")
    siblings = {}
    for item in sibling_list:
        if not isinstance(item, dict):
            raise Stage3PreflightError("invalid HF metadata sibling")
        name = item.get("rfilename")
        if not isinstance(name, str) or not name or name in siblings:
            raise Stage3PreflightError("duplicate/bad HF metadata file identity")
        siblings[name] = item
    if not set(spec["required_files"]).issubset(set(siblings)):
        raise Stage3PreflightError("HF metadata missing approved required file")
    rows = {}
    for name in spec["required_files"]:
        meta = siblings[name]
        lfs = meta.get("lfs")
        lfs_digest = lfs.get("sha256") if isinstance(lfs, dict) else None
        if lfs_digest is not None and not SHA64.fullmatch(str(lfs_digest)):
            raise Stage3PreflightError("HF metadata malformed LFS sha256")
        if name in REQUIRED_LFS and lfs_digest is None:
            raise Stage3PreflightError("HF metadata missing model weight LFS sha256")
        size = meta.get("size")
        if size is not None and (type(size) is not int or size < 0):
            raise Stage3PreflightError("invalid HF file size")
        rows[name] = {
            "provider_lfs_sha256_claim": lfs_digest,
            "provider_file_size_claim": size,
            "local_content_sha256_verified": False,
        }
    return {
        "repository": repo, "pinned_revision": revision,
        "hf_revision_matches_approved": True,
        "required_files_present": True,
        "required_files": rows,
        "provider_metadata_only": True,
        "weights_or_tokenizers_downloaded": False,
        "ready_for_compute": False,
    }


def audit_metadata_snapshot(config: dict, snapshots: dict) -> dict:
    if not isinstance(snapshots, dict) or set(snapshots) != set(COMPONENTS):
        raise Stage3PreflightError("HF snapshot must contain all three components")
    result = {
        key: audit_component(config["upstream_revisions"][key], snapshots[key])
        for key in COMPONENTS
    }
    return {
        "schema": "pro-adherence-stage3-hf-metadata-audit/v1",
        "status": "PROVIDER_METADATA_ONLY_BYTE_READBACK_PENDING",
        "model_bytes_readback_verified": False,
        "model_load_executed": False,
        "components": result,
    }


def metadata_url(repo: str, revision: str) -> str:
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
            or not SHA40.fullmatch(revision)):
        raise Stage3PreflightError("unsafe HF repository/revision")
    return ("https://huggingface.co/api/models/" + quote(repo, safe="/")
            + "/revision/" + revision + "?blobs=true")


def fetch_metadata_only(repo: str, revision: str) -> dict:
    """Opt-in public GET, exact model metadata endpoint only, bounded JSON."""
    url = metadata_url(repo, revision)
    request = Request(url, headers={"Accept": "application/json",
                                    "User-Agent": "ProAdherenceStage3-MetadataPreflight/1.0"})
    with urlopen(request, timeout=15) as response:
        target = urlsplit(response.geturl())
        if target.scheme != "https" or target.hostname != "huggingface.co":
            raise Stage3PreflightError("HF metadata redirect crossed trusted host")
        if response.headers.get_content_type() != "application/json":
            raise Stage3PreflightError("HF metadata response is not JSON")
        raw = response.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise Stage3PreflightError("HF metadata exceeded size limit")
        return json.loads(raw.decode("utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, default=Path(
        "configs/stage3/model_preflight_pins.json"))
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--offline-snapshot", type=Path,
                   help="JSON with exact provider metadata for the 3 pinned repos")
    g.add_argument("--online-metadata-only", action="store_true",
                   help="explicit opt-in: HTTPS metadata requests; NO binary downloads")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    config = load_config(args.config)
    if args.offline_snapshot:
        snapshots = json.loads(args.offline_snapshot.read_text(encoding="utf-8"))
    else:
        snapshots = {
            key: fetch_metadata_only(spec["repository"], spec["revision"])
            for key, spec in config["upstream_revisions"].items()
        }
    result = audit_metadata_snapshot(config, snapshots)
    if args.output.exists():
        raise Stage3PreflightError("never overwrite provenance snapshot")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": result["status"], "components": len(result["components"]),
                      "weight_files_downloaded": False}, sort_keys=True))


if __name__ == "__main__":
    main()
