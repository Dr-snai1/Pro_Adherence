#!/usr/bin/env python3
"""Web of Science 501..N authorized export -> ONE private-Drive deliverable ZIP.

Owner's first 1–500 WoS TXT already exists on private Google Drive; never repeat it.
Google blocks sign-in from software-controlled Chrome, so this script NEVER opens
Google sign-in or Drive inside Playwright. For WoS only, use authorized browser UI.
It stores complete source batches + manifest + exact scripts in one ZIP on the
owner-approved C: workspace. Upload ONE ZIP with user's normal signed-in Chrome
to the already-approved private Google Drive folder, then independently verify
Drive bytes via connected ChatGPT Drive before cleaning C:. NO automatic cleanup.
No sign-in bypass, auth token access, API license assumption or private Git data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import webbrowser
import sys
import time
from zipfile import ZipFile, ZIP_DEFLATED

from wos_ui_export import (
    ExportError, audit_export, fill_range, open_modal,
    ranges, select_record_content, visible, SAFE_HOST,
)

DRIVE_FOLDER_ID = "1h9Y-wjhpl3gc1wog0VP_qPaCxBWoeVyV"
FIRST_SOURCE_ID = "1_s3NXcNniPGS21L9BtzUWvZCeiddRMTP"
FIRST_SOURCE_SHA = "3247ec52dabe2ab3a156df6b57bfdd38b4e0496861458e70d0de0f5fe59ce020"
EXPECTED_TOTAL = 30635
NAME_PREFIX = "WOS_CORE_20261029_FULL180_ARTICLE_ENGLISH_"


def safe_c_workspace() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise ExportError("LOCALAPPDATA unavailable; do not pick an arbitrary directory")
    loc = Path(root).resolve()
    if loc.drive.upper() != "C:":
        raise ExportError(f"Expected owner-authorized C: temporary directory, got {loc.drive}")
    return loc / "Pro_Adherence" / "WoS_Stage2_Temp"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_default() -> dict:
    return {
        "schema": "stage2-wos-drive-archive/v1",
        "expected_results": EXPECTED_TOTAL,
        "search_query": "180-term TS candidate, Article+English",
        "folder_id": DRIVE_FOLDER_ID,
        "first_batch_existing": {
            "range_start": 1, "range_end": 500,
            "drive_file_id": FIRST_SOURCE_ID,
            "sha256": FIRST_SOURCE_SHA,
            "verified_in_chat": True,
        },
        "source_query_url": None,
        "new_batches": [],
        "delivery_status": "LOCAL_ARCHIVE_PENDING_OWNER_DRIVE_UPLOAD",
        "all_files_public": False,
        "cleanup_allowed": False,
    }


def read_state(path: Path) -> dict:
    if not path.exists():
        return manifest_default()
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema") != "stage2-wos-drive-archive/v1"
            or data.get("expected_results") != EXPECTED_TOTAL
            or data.get("folder_id") != DRIVE_FOLDER_ID):
        raise ExportError("Manifest belongs to different search/folder: stop")
    return data


def persist_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".pending")
    tmp.write_text(json.dumps(state, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def preflight_wos(page) -> None:
    if not SAFE_HOST.match(page.url) or "/wos/woscc/" not in page.url:
        raise ExportError("WoS page is not Web of Science Core Collection")
    txt = page.locator("body").inner_text()
    m = re.search(r"([\d,]+) results? from Web of Science", txt, re.I)
    if not m or int(m.group(1).replace(",", "")) != EXPECTED_TOTAL:
        raise ExportError("Expected 30,635 filtered results; wrong page or changed search")
    if not re.search(r"Document Types:\s*Article\b", txt, re.I):
        raise ExportError("Required Article refinement is missing")
    if not re.search(r"Languages:\s*English\b", txt, re.I):
        raise ExportError("Required English refinement is missing")



def make_repro_package(paths: list[Path], outpath: Path) -> None:
    with ZipFile(outpath, "w", compression=ZIP_DEFLATED) as archive:
        for p in paths:
            if not p.exists():
                raise ExportError(f"Required reproducibility script missing: {p.name}")
            archive.write(p, arcname=p.name)


def build_full_archive(batch_dir: Path, archive_path: Path,
                       *, expected_file_count: int = 63) -> dict:
    """Package *exact* source files + manifest + code. Do not delete originals.

    Verification reads each archived member back and compares SHA256 to the
    source file. The resulting ZIP is one upload in the user's normal Chrome.
    """
    input_files = sorted(p for p in batch_dir.iterdir()
                         if p.is_file() and p.suffix in {".txt", ".json", ".zip"})
    if len(input_files) != expected_file_count:
        raise ExportError(f"Expected {expected_file_count} upload artifacts, got {len(input_files)}")
    if len(set(p.name for p in input_files)) != len(input_files):
        raise ExportError("Duplicate package member names")
    pending_zip = archive_path.with_suffix(".pending")
    if pending_zip.exists():
        pending_zip.unlink()
    try:
        with ZipFile(pending_zip, "w", compression=ZIP_DEFLATED,
                     compresslevel=6, allowZip64=True) as zf:
            for p in input_files:
                zf.write(p, arcname=p.name)
        with ZipFile(pending_zip, "r") as zf:
            if sorted(zf.namelist()) != sorted(p.name for p in input_files):
                raise ExportError("Final ZIP inventory does not match source inventory")
            for p in input_files:
                h = hashlib.sha256(zf.read(p.name)).hexdigest()
                if h != sha(p):
                    raise ExportError(f"ZIP byte validation failed for {p.name}")
        pending_zip.replace(archive_path)
        return {"archive_name": archive_path.name, "sha256": sha(archive_path),
                "bytes": archive_path.stat().st_size,
                "member_count": len(input_files)}
    finally:
        if pending_zip.exists():
            pending_zip.unlink()


def run(output: Path, *, max_batches=0, delay_seconds=12.0):
    if delay_seconds < 8:
        raise ExportError("Must keep at least 8s between normal UI exports")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExportError("Python Playwright not installed") from exc
    output.mkdir(parents=True, exist_ok=True)
    batch_dir = output / "DELIVER_TO_PRIVATE_GOOGLE_DRIVE"
    batch_dir.mkdir(exist_ok=True)
    manifest_path = batch_dir / "WOS_STAGE2_20261029_MANIFEST.json"
    state = read_state(manifest_path)
    seen = set()
    for row in state["new_batches"]:
        p = batch_dir / row["filename"]
        if not p.exists() or sha(p) != row["sha256"]:
            raise ExportError("Existing batch missing/changed: do not resume blindly")
        audit = audit_export(p.read_bytes(), row["range_end"] - row["range_start"] + 1)
        if seen.intersection(audit["uids"]):
            raise ExportError("Duplicate WoS identifiers across previous batches")
        seen.update(audit["uids"])
    started = 0
    profile_dir = output / "browser_profile"
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir), channel="chrome",
            headless=False, accept_downloads=True)
        try:
            wos = context.pages[0] if context.pages else context.new_page()
            # Institutional authentication via Brunel University Library,
            # not the direct Clarivate personal-account sign-in form.
            wos.goto("https://libguides.brunel.ac.uk/az/databases?a=w",
                     wait_until="domcontentloaded", timeout=90000)
            print("IN THIS automated Chrome: Brunel Library A-Z databases page.")
            print("Type 'Web of Science' in Database Title / Keyword, click Search,")
            print("then Web of Science. Use Brunel Sign In if university login is requested.")
            print("DO NOT enter personal credentials into a direct Clarivate sign-in")
            print("and do NOT sign into Google inside this automated Chrome.")
            print("Once WoS opens, use the full 180-term result page (30,635; Article+English).")
            print("Press Enter ONLY when you see the actual WoS results (not a sign-in page).")
            input("WoS results ready? Press Enter (or Ctrl+C to stop): ")
            # The user may have opened the results in another tab while signing
            # in: never insist on the original blank tab.
            pages = [page for page in context.pages
                     if SAFE_HOST.match(page.url) and "/wos/woscc/" in page.url]
            if not pages:
                raise ExportError("No WoS Core Collection tab open. No exports started.")
            errors = []
            for candidate in pages:
                try:
                    preflight_wos(candidate)
                    wos = candidate
                    break
                except Exception as exc:
                    errors.append(str(exc))
            else:
                raise ExportError(
                    "No tab has the 30,635 English Article results. "
                    + " ; ".join(errors[:3]) + ". No exports started.")
            state["source_query_url"] = wos.url
            persist_state(manifest_path, state)
            for start, end in ranges(EXPECTED_TOTAL, start_from=501):
                fname = f"{NAME_PREFIX}{start:06d}-{end:06d}.txt"
                done = next((x for x in state["new_batches"]
                             if x["range_start"] == start and x["range_end"] == end), None)
                if done:
                    print(f"SKIP existing C: validated batch: {fname}")
                    continue
                if max_batches and started >= max_batches:
                    break
                dest = batch_dir / fname
                if dest.exists():
                    audit = audit_export(dest.read_bytes(), end - start + 1)
                else:
                    modal = open_modal(wos)
                    fill_range(modal, start, end)
                    select_record_content(wos, modal)
                    btn = modal.get_by_role("button", name=re.compile(r"^Export$", re.I))
                    if not visible(btn):
                        raise ExportError("Export button in WoS dialog not found")
                    try:
                        with wos.expect_download(timeout=180000) as item:
                            btn.first.click(timeout=20000)
                        download = item.value
                        if not download.suggested_filename.lower().endswith(".txt"):
                            raise ExportError("WoS exported non-TXT payload")
                        pending = dest.with_suffix(".pending")
                        download.save_as(str(pending))
                        audit = audit_export(pending.read_bytes(), end - start + 1)
                        pending.replace(dest)
                    except Exception:
                        raise ExportError(f"WoS download {start}-{end} failed; no Drive upload")
                if seen.intersection(audit["uids"]):
                    raise ExportError(f"WoS UT overlap in {start}-{end}; stop")
                seen.update(audit["uids"])
                row = {
                    "range_start": start, "range_end": end, "filename": fname,
                    "records": audit["records"], "sha256": audit["sha256"],
                    "size_bytes": audit["size_bytes"],
                    "first_uid": audit["first_uid"], "last_uid": audit["last_uid"],
                    "uids": audit["uids"], "cited_references": audit["cited_references"],
                    "nr_anomalies": audit["nr_anomalies"],
                    "drive_file_id": None, "cloud_sha256_confirmed": False,
                }
                state["new_batches"].append(row)
                persist_state(manifest_path, state)
                started += 1
                print(f"VALIDATED_C_SOURCE {start}-{end} records={audit['records']} "
                      f"SHA256={audit['sha256']} NR_flags={audit['nr_anomaly_count']}")
                time.sleep(delay_seconds)
            if max_batches and started >= max_batches:
                print("LIMITED_SESSION_PAUSED: source files and manifest retained on C:")
                return
            if len(state["new_batches"]) != 61:
                raise ExportError("Not all 61 remaining batches present; do not mark complete")
            if sum(r["records"] for r in state["new_batches"]) != 30135:
                raise ExportError("Source record total mismatch")
            scripts = [Path(__file__).resolve(),
                       Path(__file__).with_name("wos_ui_export.py"),
                       Path(__file__).with_name("wos_search_plan.py"),
                       Path(__file__).with_name("medication-adherence-SELECTED.v1.json"),
                       Path(__file__).with_name("start_wos_export_windows.ps1")]
            package = batch_dir / "WOS_STAGE2_20261029_REPRO_SCRIPTS.zip"
            make_repro_package(scripts, package)
            state["script_bundle_filename"] = package.name
            state["script_bundle_sha256"] = sha(package)
            state["delivery_status"] = "LOCAL_ARCHIVE_PENDING_OWNER_DRIVE_UPLOAD"
            state["cleanup_allowed"] = False
            persist_state(manifest_path, state)
            archive_path = output / "WOS_STAGE2_ALL_REMAINING_501-30635.zip"
            result = build_full_archive(batch_dir, archive_path)
            print(f"ARCHIVE_READY_ON_C: {archive_path}")
            print(f"ARCHIVE_SHA256: {result['sha256']}; bytes={result['bytes']}")
            print("Open the private Drive folder in your NORMAL signed-in Chrome.")
            print("Upload ONE ZIP file using Google Drive: New -> File upload.")
            print("Remote archive hash/contents will be checked independently before cleanup.")
            webbrowser.open("https://drive.google.com/drive/folders/" + DRIVE_FOLDER_ID)
        finally:
            context.close()
            # Chromium auth profile is disposable runtime/cache, not research
            # evidence. Never retain signed-in session cookies on the C: disk.
            shutil.rmtree(profile_dir, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-batches", type=int, default=0)
    parser.add_argument("--delay-seconds", type=float, default=12)
    parser.add_argument("--plan", action="store_true", help="No downloads, browser or writes")
    args = parser.parse_args(argv)
    if args.plan:
        jobs = ranges(EXPECTED_TOTAL, start_from=501)
        print(f"Remaining batches: {len(jobs)}, first {jobs[0]}, last {jobs[-1]}")
        return 0
    out = safe_c_workspace()
    if args.output is not None and args.output.resolve() != out.resolve():
        print("Custom output path forbidden; C: staging only per owner approval", file=sys.stderr)
        return 2
    try:
        run(out, max_batches=args.max_batches, delay_seconds=args.delay_seconds)
    except (ExportError, OSError, ValueError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        print("Files already downloaded/verified are preserved on C: for recovery.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
