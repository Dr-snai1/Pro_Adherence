#!/usr/bin/env python3
"""Web of Science 501..N batches -> private Google Drive UI, with C: fail-safe.

First 1-500 is already archived in the project Drive; never re-download it.
Use normal authenticated Chrome UI for *both* WoS export and Drive upload.
No private API, no tokens, no scraping, no hidden browser auth.
All transient downloads are kept on C: until an independent Drive verification.
Not tested against the owner's live HTML; stop on unexpected UI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
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
QUERY_MARKER = "TS=("
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
        "drive_receipt_status": "UI_ONLY_RECEIPTS_PENDING_INDEPENDENT_READBACK",
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
    if QUERY_MARKER not in txt:
        raise ExportError("TS full query not visible; stop (do not use six-term pilot)")


def verify_drive_folder(page) -> None:
    if not re.match(
        r"^https://drive\\.google\\.com/drive/(?:u/\\d+/)?folders/"
        + re.escape(DRIVE_FOLDER_ID) + r"(?:[/?#]|$)", page.url, re.I
    ):
        raise ExportError("Google Drive browser page is not the approved private folder")
    body = page.locator("body").inner_text(timeout=20000)
    if "Request access" in body or "Запросить доступ" in body:
        raise ExportError("Wrong Google account; no access to target folder")


def drive_upload(page, source: Path, *, timeout_sec=240) -> dict:
    """Upload through Google Drive's native New->File upload chooser.

    The source remains on C: even after a positive UI receipt; independent
    byte-readback via project connector is a separate gate before cleanup.
    """
    name = source.name
    verify_drive_folder(page)
    # Do not overwrite or guess identity when the same named file already shows.
    exact = page.get_by_text(name, exact=True)
    if visible(exact):
        raise ExportError(f"Drive folder already shows {name}; verify before resuming")
    # Visible menu ensures the upload is user-authorized UI operation.
    new_button = page.get_by_role("button", name=re.compile(r"^(New|Создать)$", re.I))
    if not visible(new_button):
        raise ExportError("Google Drive New button not found; no files uploaded")
    new_button.first.click(timeout=20000)
    item = page.get_by_role("menuitem", name=re.compile(r"^(File upload|Загрузить файлы|Загрузка файлов)$", re.I))
    if not visible(item):
        item = page.get_by_text(re.compile(r"^(File upload|Загрузить файлы|Загрузка файлов)$", re.I))
    if not visible(item):
        raise ExportError("Google Drive File upload menu item not visible")
    with page.expect_file_chooser(timeout=20000) as chooser:
        item.first.click(timeout=20000)
    chooser.value.set_files(str(source))
    # Both completion receipt and locally preserved bytes are required.
    complete = re.compile(r"(upload complete|uploaded|загруз(?:ка завершена|ено|ен)|загружен)", re.I)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            body = page.locator("body").inner_text(timeout=10000)
            if complete.search(body) and name in body:
                # May be a generic toast; never infer remote byte-identity here.
                return {"filename": name, "ui_upload_receipt": True,
                        "remote_bytes_verified": False,
                        "sha256": sha(source), "size_bytes": source.stat().st_size}
        except Exception:
            pass
        time.sleep(3)
    raise ExportError(f"Drive did not confirm completed upload of {name}; "
                      "keep C: file and do not continue automatically")


def make_repro_package(paths: list[Path], outpath: Path) -> None:
    with ZipFile(outpath, "w", compression=ZIP_DEFLATED) as archive:
        for p in paths:
            if not p.exists():
                raise ExportError(f"Required reproducibility script missing: {p.name}")
            archive.write(p, arcname=p.name)


def run(output: Path, *, max_batches=0, delay_seconds=12.0):
    if delay_seconds < 8:
        raise ExportError("Must keep at least 8s between normal UI exports")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExportError("Python Playwright not installed") from exc
    output.mkdir(parents=True, exist_ok=True)
    batch_dir = output / "exports"
    batch_dir.mkdir(exist_ok=True)
    manifest_path = output / "WOS_STAGE2_20261029_MANIFEST.json"
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
            wos.goto("https://www.webofscience.com/wos/woscc/basic-search",
                     wait_until="domcontentloaded", timeout=90000)
            drive = context.new_page()
            drive.goto("https://drive.google.com/drive/folders/" + DRIVE_FOLDER_ID,
                       wait_until="domcontentloaded", timeout=90000)
            print("Sign into WoS and Google Drive in the opened Chrome windows.")
            print("In WoS, open full 180-term query results with 30,635 English Articles.")
            input("When BOTH pages are ready, press Enter in console: ")
            preflight_wos(wos)
            verify_drive_folder(drive)
            state["source_query_url"] = wos.url
            persist_state(manifest_path, state)
            for start, end in ranges(EXPECTED_TOTAL, start_from=501):
                fname = f"{NAME_PREFIX}{start:06d}-{end:06d}.txt"
                done = next((x for x in state["new_batches"]
                             if x["range_start"] == start and x["range_end"] == end), None)
                if done:
                    if not done["drive_ui_receipt"]:
                        raise ExportError("Batch without Drive receipt; resolve before resume")
                    print(f"SKIP already archived via UI: {fname}")
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
                receipt = drive_upload(drive, dest)
                row = {
                    "range_start": start, "range_end": end, "filename": fname,
                    "records": audit["records"], "sha256": audit["sha256"],
                    "size_bytes": audit["size_bytes"],
                    "first_uid": audit["first_uid"], "last_uid": audit["last_uid"],
                    "uids": audit["uids"], "cited_references": audit["cited_references"],
                    "nr_anomalies": audit["nr_anomalies"],
                    "drive_ui_receipt": receipt["ui_upload_receipt"],
                    "drive_file_id": None, "cloud_sha256_confirmed": False,
                }
                state["new_batches"].append(row)
                persist_state(manifest_path, state)
                started += 1
                print(f"UPLOADED_BY_UI {start}-{end} records={audit['records']} "
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
                       Path(__file__).with_name("start_wos_export_windows.ps1")]
            package = output / "WOS_STAGE2_20261029_REPRO_SCRIPTS.zip"
            make_repro_package(scripts, package)
            # Last: archive exact scripts and manifest used to create all outputs.
            drive_upload(drive, package)
            state["script_bundle_filename"] = package.name
            state["script_bundle_sha256"] = sha(package)
            persist_state(manifest_path, state)
            drive_upload(drive, manifest_path)
            print("UPLOADS_UI_COMPLETE: 61 new batches + manifest + reproducibility scripts.")
            print("DO NOT DELETE C: folder until independent Drive SHA256 verification.")
        finally:
            context.close()


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
