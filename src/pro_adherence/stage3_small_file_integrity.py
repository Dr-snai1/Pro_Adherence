"""Audit only small text/tokenizer files from exact, owner-approved HF revisions.

No .bin, no torch, no model loading. Provider Git blob SHA-1 (where present)
is checked against bytes, along with provider size and local SHA-256.
Designed for explicit, one-shot metadata+small-asset evidence only.
"""
from __future__ import annotations

from hashlib import sha1, sha256
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .stage3_hf_provenance import fetch_metadata_only, audit_component
from .stage3_preflight import Stage3PreflightError, load_config

SMALL_FILE_LIMIT = 1024 * 1024
MODEL_BINARIES = frozenset(("pytorch_model.bin", "pytorch_adapter.bin"))
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def small_file_url(repository: str, revision: str, filename: str) -> str:
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or not HEX40.fullmatch(revision)
        or not isinstance(filename, str) or not filename
        or filename in MODEL_BINARIES or not re.fullmatch(r"[A-Za-z0-9_.-]+", filename)):
        raise Stage3PreflightError("unapproved path or model binary requested")
    return (f"https://huggingface.co/{repository}/resolve/"
            f"{revision}/{quote(filename, safe='')}")


def git_blob_id(raw: bytes) -> str:
    return sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def audit_small_bytes(raw: bytes, sibling: dict, filename: str) -> dict:
    if filename in MODEL_BINARIES or not isinstance(raw, bytes):
        raise Stage3PreflightError("model binary or non-bytes supplied")
    size = sibling.get("size")
    if type(size) is not int or not 0 <= size <= SMALL_FILE_LIMIT:
        raise Stage3PreflightError("invalid or large provider file size")
    if len(raw) != size:
        raise Stage3PreflightError("provider small-file byte length mismatch")
    blob = sibling.get("blobId")
    local_blob = git_blob_id(raw)
    if blob is not None:
        if not HEX40.fullmatch(str(blob)) or blob != local_blob:
            raise Stage3PreflightError("provider Git blob identity mismatch")
    return {
        "filename": filename,
        "size_bytes": len(raw),
        "local_sha256": sha256(raw).hexdigest(),
        "local_git_blob_id": local_blob,
        "provider_blob_id": blob,
        "provider_git_blob_identity_verified": bool(blob),
        "local_bytes_readback_verified": True,
        "model_weights_downloaded": False,
    }


def fetch_small_bytes(url: str) -> bytes:
    req = Request(url, headers={"Accept": "application/octet-stream",
                               "User-Agent": "ProAdherenceStage3-SmallFiles/1.0"})
    with urlopen(req, timeout=20) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname != "huggingface.co":
            raise Stage3PreflightError("small-file redirect crossed approved HF host")
        announced = response.headers.get("Content-Length")
        if announced and int(announced) > SMALL_FILE_LIMIT:
            raise Stage3PreflightError("small-file HTTP response too large")
        raw = response.read(SMALL_FILE_LIMIT + 1)
        if len(raw) > SMALL_FILE_LIMIT:
            raise Stage3PreflightError("small-file download limit exceeded")
        return raw


def verify_pinned_small_files(config: dict, output_dir: Path) -> dict:
    if output_dir.exists():
        raise Stage3PreflightError("refuse to overwrite model small-file audit directory")
    output_dir.mkdir(mode=0o700, parents=True)
    components = {}
    for key, spec in config["upstream_revisions"].items():
        metadata = fetch_metadata_only(spec["repository"], spec["revision"])
        audit_component(spec, metadata)
        by_name = {f["rfilename"]: f for f in metadata["siblings"]}
        folder = output_dir / key
        folder.mkdir(mode=0o700)
        results = {}
        for filename in spec["required_files"]:
            if filename in MODEL_BINARIES:
                continue
            sibling = by_name[filename]
            size = sibling.get("size")
            if type(size) is not int or not 0 <= size <= SMALL_FILE_LIMIT:
                raise Stage3PreflightError("required file too large or size unknown")
            raw = fetch_small_bytes(small_file_url(spec["repository"], spec["revision"], filename))
            digest = audit_small_bytes(raw, sibling, filename)
            dest = folder / filename
            with dest.open("xb") as f:
                f.write(raw)
            if sha256(dest.read_bytes()).hexdigest() != digest["local_sha256"]:
                raise Stage3PreflightError("small-file disk SHA256 readback mismatch")
            results[filename] = digest
        components[key] = {
            "repository": spec["repository"], "revision": spec["revision"],
            "files": results,
        }
    manifest = {
        "schema": "pro-adherence-stage3-pinned-small-files/v1",
        "publication_authorized": False, "weights_downloaded": False,
        "model_inference_executed": False, "ready_for_training": False,
        "all_local_byte_readbacks_pass": True,
        "all_provider_git_blobs_verified": all(
            f["provider_git_blob_identity_verified"]
            for c in components.values() for f in c["files"].values()
        ),
        "components": components,
    }
    path = output_dir / "small_file_integrity.json"
    with path.open("x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    if json.loads(path.read_text(encoding="utf-8")) != manifest:
        raise Stage3PreflightError("small-file audit manifest readback mismatch")
    return manifest


def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path,
                   default=Path("configs/stage3/model_preflight_pins.json"))
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--online-small-files", action="store_true")
    args = p.parse_args()
    if not args.online_small_files:
        p.error("explicit --online-small-files gate required")
    report = verify_pinned_small_files(load_config(args.config), args.output_dir)
    print(json.dumps({
        "status": "SMALL_FILES_BYTE_READBACK_PASS"
        if report["all_provider_git_blobs_verified"]
        else "SMALL_FILE_BYTES_READ_GIT_BLOB_EVIDENCE_PENDING",
        "files": sum(len(c["files"]) for c in report["components"].values()),
        "provider_git_blob_ids_verified": report["all_provider_git_blobs_verified"],
        "large_weights_downloaded": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
