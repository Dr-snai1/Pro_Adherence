#!/usr/bin/env python3
"""Path-parameterized launcher for byte-frozen TASK-0003 V05 offline wrapper.

Never changes the accepted scientific code or frozen inputs. No network is used
by the accepted wrapper's offline build. Requires exact CPython 3.13.16 and
an isolated checkout at the accepted historical commit.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import runpy
import sys

PINNED_WRAPPER_SHA256 = "cb72548120bcecd8b653c98264d75ddd0c0775f841a19f479d75768f5040fced"
PINNED_MANIFEST_SHA256 = "fab7cb43ba8d9c034386550ad1bc0f2040d77f0462b98dc153fe49391d41f963"
PINNED_SQLITE_SHA256 = "de31e44523e3857eaa328fb832b6bd6d9d58712e0623785cbfe0e68d1890dde6"
WRAPPER_NAME = "TASK0003_V05_CANONICAL_OFFLINE_FINAL_v3.py"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for piece in iter(lambda: f.read(1024 * 1024), b""):
            h.update(piece)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, type=Path, help="Drive-mounted frozen V05 source evidence package")
    p.add_argument("--work", required=True, type=Path, help="new isolated disposable compute workspace")
    p.add_argument("--checkout", required=True, type=Path, help="historical exact Git checkout ae2dd813...")
    p.add_argument("--deps", required=True, type=Path, help="installed pinned build dependencies")
    p.add_argument("--wrapper", type=Path, default=Path(__file__).with_name(WRAPPER_NAME))
    p.add_argument("--preflight-only", action="store_true", help="check executable identity and paths, no run or writes")
    args = p.parse_args(argv)
    if sys.version_info[:3] != (3, 13, 16):
        p.error("Exact CPython 3.13.16 is required; no scientific run was started")
    wrapper = args.wrapper.resolve(strict=True)
    if sha256(wrapper) != PINNED_WRAPPER_SHA256:
        p.error("Frozen V05 wrapper bytes do not match the accepted SHA256")
    source = args.source.resolve(strict=True)
    checkout = args.checkout.resolve(strict=True)
    deps = args.deps.resolve(strict=True)
    work = args.work.resolve()
    if not source.is_dir() or not checkout.is_dir() or not deps.is_dir():
        p.error("Source, pinned checkout and pinned deps must be directories")
    if not (checkout / "src" / "pro_adherence" / "pubmed_evidence.py").is_file():
        p.error("Pinned checkout module not found")
    if work == source or source in work.parents or work in source.parents:
        p.error("Disposable work must be separate from immutable Drive source")
    if args.preflight_only:
        print("V05_PORTABLE_PREFLIGHT_PATHS_PASS wrapper_sha256=" + PINNED_WRAPPER_SHA256)
        print("SCIENTIFIC_REPRODUCTION_NOT_RUN")
        return 0
    if work.exists() and any(work.iterdir()):
        p.error("Work directory must be absent or empty for a clean-path reproduction")
    work.mkdir(parents=True, exist_ok=True)
    # Prevent original __main__ execution before overriding Windows-only paths.
    namespace = runpy.run_path(str(wrapper), run_name="_v05_frozen_module")
    fn = namespace["run_pipeline"]
    fn.__globals__.update(CHECKOUT=checkout, SOURCE=source, WORK=work, DEPS=deps)
    result = fn()
    if result != 0:
        raise RuntimeError("Frozen pipeline failed; original data retained")
    snaps = list((work / "corpus-v3").glob("*/corpus_manifest.json"))
    if len(snaps) != 1 or sha256(snaps[0]) != PINNED_MANIFEST_SHA256:
        raise RuntimeError("Clean-path canonical manifest differs from accepted baseline")
    import json
    report = json.loads(snaps[0].read_bytes())
    if report.get("sqlite_sha256") != PINNED_SQLITE_SHA256:
        raise RuntimeError("Clean-path SQLite SHA differs from accepted baseline")
    print("V05_CLEAN_PATH_MANIFEST_SQLITE_SHA_PASS")
    print("V05_753_FILE_QA_COMPARISON_STILL_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
