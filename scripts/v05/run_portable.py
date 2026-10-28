#!/usr/bin/env python3
"""One-command read-only Drive package restore and exact V05 offline rebuild.

Reuses the byte-frozen accepted scientific wrapper, source, and 250 archived XML
batches. Writes ONLY to a new disposable workspace. Never calls PubMed, changes
accepted evidence, or promotes private data. No fixed local drive path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sqlite3
import subprocess
import sys

RUN = "r-d841c4b5c419f4f12eafee793f4c4fc0"
ARCHIVE_SHA = "5506a463a5bc9e5e38c6faa0e832e6a5e71568775fe2611fbe64e583cdda4da7"
UID_SHA = "bbb34a0b69872c235d897d844b0338be4aa06adf167e090ae73e0d7e3ddcfe2b"
MANIFEST_SHA = "fab7cb43ba8d9c034386550ad1bc0f2040d77f0462b98dc153fe49391d41f963"
SQLITE_SHA = "de31e44523e3857eaa328fb832b6bd6d9d58712e0623785cbfe0e68d1890dde6"
WRAPPER_SHA = "cb72548120bcecd8b653c98264d75ddd0c0775f841a19f479d75768f5040fced"
OLD_COMMIT = "ae2dd8131fb7840ccb6f0ac9332dcf31ee4776ea"
OLD_BLOB = "994879fcc9ee6e1b526f4c51fff296dcdf8ecd79"
WRAPPER = "TASK0003_V05_CANONICAL_OFFLINE_FINAL_v3.py"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as inp:
        for chunk in iter(lambda: inp.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def accepted_paths(root: Path) -> tuple[Path, Path, Path]:
    src = root / "research-backup" / "pubmed" / "TASK-0003" / "v05-proven-dp" / RUN
    archived = root / "stage1-v05-private" / RUN
    baseline = archived / "corpus-v3" / MANIFEST_SHA
    if not src.is_dir() or not archived.is_dir() or not baseline.is_dir():
        raise ValueError("V05_EXTRACTED_LAYOUT_MISSING")
    return src, archived, baseline


def verify_archive_snapshot(root: Path) -> dict:
    src, archived, canonical = accepted_paths(root)
    uid = src / "pmids" / "SELECTED" / "union.txt"
    if sha256(uid) != UID_SHA:
        raise ValueError("V05_UID_MISMATCH")
    for name, extension in (("raw", ".xml"), ("source_meta", ".json")):
        d = archived / name
        if not d.is_dir() or sorted(p.name for p in d.iterdir()) != [f"{i:06}{extension}" for i in range(1, 251)]:
            raise ValueError("V05_ARCHIVED_250_BATCHES_MISSING_" + name)
    manifest_path = canonical / "corpus_manifest.json"
    if sha256(manifest_path) != MANIFEST_SHA:
        raise ValueError("V05_MANIFEST_MISMATCH")
    m = json.loads(manifest_path.read_bytes())
    if m.get("input_records") != 49998 or m.get("canonical_records") != 49998 or m.get("book_records") != 86:
        raise ValueError("V05_ACCEPTED_COUNTS_MISMATCH")
    if m.get("sqlite_sha256") != SQLITE_SHA or len(m.get("partitions", [])) != 250:
        raise ValueError("V05_CANONICAL_IDENTITY_MISMATCH")
    total = 0
    for part in m["partitions"]:
        folder = canonical / "partitions" / f"{part['batch']:06}"
        for name, digest in part["parquet_sha256"].items():
            if sha256(folder / name) != digest:
                raise ValueError("V05_PARQUET_SHA_MISMATCH")
            total += 1
    if total != 750 or sha256(canonical / "working.sqlite") != SQLITE_SHA:
        raise ValueError("V05_753_FILE_SHA_MISMATCH")
    if (canonical / "manifest.sha256").read_text(encoding="utf-8").strip().lower() != MANIFEST_SHA:
        raise ValueError("V05_MANIFEST_SIDECAR_MISMATCH")
    with sqlite3.connect((canonical / "working.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        if db.execute("pragma integrity_check").fetchone() != ("ok",):
            raise ValueError("V05_SQLITE_INTEGRITY_MISMATCH")
        if db.execute("select count(*) from articles").fetchone() != (49998,):
            raise ValueError("V05_SQLITE_ROWS_MISMATCH")
        if db.execute("select count(*) from resolution_issues").fetchone() != (147,):
            raise ValueError("V05_SQLITE_ISSUES_MISMATCH")
    print("V05_CLOUD_ARCHIVE_RESTORE_READBACK_PASS source_pmids=49998 raw_batches=250 canonical_files=753 sqlite_rows=49998", flush=True)
    return m


def verify_parts(parts_dir: Path, work: Path) -> Path:
    meta = json.loads((parts_dir / "V05_full_private.7z.parts.manifest.json").read_text(encoding="utf-8"))
    if meta.get("archive_sha256") != ARCHIVE_SHA or meta.get("archive_size_bytes") != 210340898 or len(meta.get("parts", [])) != 3:
        raise ValueError("V05_DRIVE_PARTS_MANIFEST_MISMATCH")
    target = work / "V05_full_private.7z"
    digest = hashlib.sha256()
    total = 0
    with target.open("xb") as out:
        for index, part in enumerate(meta["parts"], 1):
            expected = f"V05_full_private.7z.part{index:03}"
            if part.get("filename") != expected:
                raise ValueError("V05_PART_ORDER_MISMATCH")
            path = parts_dir / expected
            if sha256(path) != part["sha256"] or path.stat().st_size != part["size_bytes"]:
                raise ValueError("V05_PART_CONTENT_MISMATCH")
            with path.open("rb") as inp:
                for piece in iter(lambda: inp.read(4 * 1024 * 1024), b""):
                    digest.update(piece)
                    total += len(piece)
                    out.write(piece)
    if digest.hexdigest() != ARCHIVE_SHA or total != 210340898:
        raise ValueError("V05_FULL_ARCHIVE_SHA_MISMATCH")
    print("V05_DRIVE_THREE_PART_SHA_PASS", flush=True)
    return target


def extract_verified_archive(archive: Path, output: Path, extractor: str) -> None:
    output.mkdir()
    command = [extractor, "x", "-y", "-p", str(archive.resolve()), "-o" + str(output.resolve())]
    p = subprocess.run(command, input=b"\n", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       check=False, timeout=3600)
    if p.returncode != 0:
        raise RuntimeError("V05_OFFLINE_ARCHIVE_EXTRACT_FAILED (tool exit=" + str(p.returncode) + ")")


def verify_old_code(checkout: Path) -> None:
    r = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                       text=True, capture_output=True, check=True)
    if r.stdout.strip().lower() != OLD_COMMIT:
        raise ValueError("V05_ACCEPTED_OLD_GIT_COMMIT_MISMATCH")
    module = checkout / "src" / "pro_adherence" / "pubmed_evidence.py"
    b = module.read_bytes()
    blob_sha = hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()
    if blob_sha != OLD_BLOB:
        raise ValueError("V05_ACCEPTED_OLD_GIT_BLOB_MISMATCH")


def build_exact(root: Path, work: Path, checkout: Path, deps: Path, wrapper: Path) -> None:
    if sys.version_info[:3] != (3, 13, 16):
        raise RuntimeError("V05_EXACT_PYTHON_3_13_16_REQUIRED")
    if sha256(wrapper) != WRAPPER_SHA:
        raise ValueError("V05_BYTE_PINNED_WRAPPER_MISMATCH")
    verify_old_code(checkout)
    sys.path.insert(0, str(deps))
    import pyarrow as pa
    import numpy as np
    if (pa.__version__, np.__version__) != ("26.0.0", "2.3.5"):
        raise RuntimeError("V05_EXACT_PYARROW_NUMPY_DEPENDENCIES_REQUIRED")
    src, archived, baseline = accepted_paths(root)
    runwork = work / "clean-build"
    runwork.mkdir()
    for d, ext in (("raw", ".xml"), ("source_meta", ".json")):
        newdir = runwork / d
        newdir.mkdir()
        for index in range(1, 251):
            filename = f"{index:06}{ext}"
            shutil.copyfile(archived / d / filename, newdir / filename)
    fn = runpy.run_path(str(wrapper), run_name="_frozen_v05_module")["run_pipeline"]
    fn.__globals__.update(CHECKOUT=checkout, SOURCE=src, WORK=runwork, DEPS=deps)
    if fn() != 0:
        raise RuntimeError("V05_OFFLINE_REBUILD_RETURNED_FAILURE")
    result = runwork / "corpus-v3" / MANIFEST_SHA
    expected = {p.relative_to(baseline) for p in baseline.rglob("*") if p.is_file()}
    actual = {p.relative_to(result) for p in result.rglob("*") if p.is_file()}
    if expected != actual or len(expected) != 753:
        raise ValueError("V05_REBUILD_FILE_SET_MISMATCH")
    for rel in sorted(expected):
        if sha256(baseline / rel) != sha256(result / rel):
            raise ValueError("V05_REBUILD_SHA_MISMATCH: " + str(rel))
    verify_archive_snapshot(work / "restored") if (work / "restored").is_dir() else verify_archive_snapshot(root)
    print("V05_CLEAN_PATH_DETERMINISTIC_REBUILD_PASS files=753/753 network_calls=0", flush=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--parts-dir", type=Path, help="mounted Drive folder with three verified archive chunks and JSON manifest")
    source.add_argument("--extracted-root", type=Path, help="previously restored Drive archive root (verify independently)")
    p.add_argument("--work", type=Path, help="new disposable workspace for archive restore and clean rebuild")
    p.add_argument("--checkout", type=Path, help="historical Git checkout on exact ae2dd813 commit")
    p.add_argument("--deps", type=Path, help="pinned Python dependencies pyarrow=26.0.0 numpy=2.3.5")
    p.add_argument("--wrapper", type=Path, default=Path(__file__).with_name(WRAPPER))
    p.add_argument("--extractor", default="7z", help="available 7-Zip CLI or absolute path (7z/7zz/7zr)")
    p.add_argument("--verify-only", action="store_true", help="restore and verify 753 baseline files, no scientific rebuild")
    a = p.parse_args(argv)
    if a.parts_dir:
        if not a.work:
            p.error("--work is mandatory with --parts-dir")
        work = a.work.resolve()
        if work.exists() and any(work.iterdir()):
            p.error("--work must be new/empty")
        work.mkdir(parents=True, exist_ok=True)
        archive = verify_parts(a.parts_dir.resolve(strict=True), work)
        root = work / "restored"
        extract_verified_archive(archive, root, a.extractor)
    else:
        root = a.extracted_root.resolve(strict=True)
        work = a.work.resolve() if a.work else None
    verify_archive_snapshot(root)
    if a.verify_only:
        print("V05_REPRODUCTION_NOT_RUN (verify-only)")
        return 0
    if not work or not a.checkout or not a.deps:
        p.error("--work --checkout --deps required for deterministic clean rebuild")
    if a.extracted_root:
        if work.exists() and any(work.iterdir()):
            p.error("--work must be new/empty for --extracted-root")
        work.mkdir(parents=True, exist_ok=True)
    build_exact(root, work, a.checkout.resolve(strict=True), a.deps.resolve(strict=True), a.wrapper.resolve(strict=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())