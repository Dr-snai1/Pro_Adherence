#!/usr/bin/env python3
"""Resumable Web of Science Core Collection UI-only export helper.

This prototype uses the normal site's Export -> Plain text file dialog in a
human-authenticated browser. It does not use private APIs, steal cookies, evade
rate limits, or make an unapproved search query. It halts on any uncertainty.

IMPORTANT: the site's real UI has not been tested in this environment. Run a
single batch first; operator must verify the local export and permitted terms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import re
import sys
import time
from pathlib import Path

HEADER = b"FN Clarivate Analytics Web of Science"
UT_RE = re.compile(r"^UT (WOS:[^\s]+)$", re.MULTILINE)
NR_RE = re.compile(r"^NR (\d+)$", re.MULTILINE)
SAFE_HOST = re.compile(r"^https://(www\.)?webofscience\.com/", re.I)


class ExportError(RuntimeError):
    pass


def ranges(total: int, batch_size: int = 500, start_from: int = 1):
    if not (1 <= total <= 1_000_000 and 1 <= batch_size <= 500 and 1 <= start_from <= total):
        raise ValueError("Invalid total/batch-size/start-from")
    if (start_from - 1) % batch_size:
        raise ValueError("start-from must align with batch boundaries")
    return [(a, min(total, a + batch_size - 1)) for a in range(start_from, total + 1, batch_size)]


def audit_export(raw: bytes, expected_count: int) -> dict:
    if not raw.startswith(HEADER) and not raw.startswith(b"\xef\xbb\xbf" + HEADER):
        raise ExportError("Not a WoS tagged text export")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExportError("WoS export is not UTF-8") from exc
    lines = text.splitlines()
    if not lines or lines[-1] != "EF":
        raise ExportError("WoS export must terminate with EF")
    counts = {"records": 0, "refs": 0}
    ids = []
    reference_count_anomalies = []
    in_record = False
    refs_in_record = 0
    declared = None
    last_tag = None
    current_uid = None
    for line in lines[2:]:
        if line.startswith("PT "):
            if in_record:
                raise ExportError("Nested record")
            in_record = True
            counts["records"] += 1
            refs_in_record = 0
            declared = None
            current_uid = None
            last_tag = "PT"
        elif line == "ER":
            if not in_record or declared is None or current_uid is None:
                raise ExportError("Incomplete record; UT or NR missing")
            if declared != refs_in_record:
                # Real WoS export can report NR greater than actual CR lines.
                # This MUST remain an explicit, per-record integrity anomaly.
                # Do not invent missing cited references or discard 500 valid UTs.
                reference_count_anomalies.append({
                    "record_ordinal": counts["records"], "uid": current_uid,
                    "nr_declared": declared, "cr_exported": refs_in_record,
                    "shortfall": declared - refs_in_record,
                })
            in_record = False
            last_tag = None
        elif line == "EF":
            if in_record:
                raise ExportError("Incomplete last record")
        elif in_record:
            if line.startswith("NR "):
                declared = int(line[3:])
            if line.startswith("CR "):
                last_tag = "CR"
                refs_in_record += 1
                counts["refs"] += 1
            elif line.startswith("   ") and last_tag == "CR":
                refs_in_record += 1
                counts["refs"] += 1
            elif not line.startswith("   "):
                if len(line) >= 3 and line[2] == " ":
                    last_tag = line[:2]
            if line.startswith("UT "):
                current_uid = line[3:].strip()
                ids.append(current_uid)
    if counts["records"] != expected_count:
        raise ExportError(f"Expected {expected_count} records, found {counts['records']}")
    if len(ids) != expected_count or len(set(ids)) != expected_count:
        raise ExportError("Missing or duplicate WoS UT identifiers")
    if not all(i.startswith("WOS:") for i in ids):
        raise ExportError("Malformed source-native UT identifier")
    return {"records": counts["records"], "cited_references": counts["refs"],
            "nr_anomaly_count": len(reference_count_anomalies),
            "nr_anomalies": reference_count_anomalies,
            "first_uid": ids[0], "last_uid": ids[-1], "uids": ids,
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def visible(locator):
    return locator.count() > 0 and locator.first.is_visible()


def locate_export_panel(page):
    """Find the real WoS export panel without assuming ARIA dialog or CSS class.

    Screenshot from the owner shows the distinctive heading, two radio
    choices, Record Content, and a final Export button. Some WoS builds
    render this as an ordinary DIV, and menu selection is asynchronous.
    Identify the *smallest visible ancestor* that contains these controls.
    """
    title = page.get_by_text(re.compile(r"^Export Records to Plain Text File$", re.I))
    try:
        title.first.wait_for(state="visible", timeout=15000)
    except Exception as exc:
        raise ExportError("WoS export heading did not appear after Plain text file selection") from exc

    dialog = page.get_by_role("dialog").filter(
        has_text=re.compile(r"Export Records to Plain Text File", re.I))
    if visible(dialog) and dialog.first.locator('input[type="radio"]').count() >= 2:
        return dialog.first

    for i in range(min(title.count(), 3)):
        heading = title.nth(i)
        if not heading.is_visible():
            continue
        for depth in range(1, 10):
            container = heading.locator(f"xpath=ancestor::*[{depth}]")
            if container.count() != 1 or not container.is_visible():
                continue
            if (container.locator('input[type="radio"]').count() >= 2
                    and container.get_by_role(
                        "button", name=re.compile(r"^Export$", re.I)).count() >= 1
                    and container.get_by_text("Record Content:", exact=False).count() >= 1):
                return container
    raise ExportError(
        "WoS export heading is visible, but its two range radios, Record Content "
        "and final Export button are not in one visible panel. Stop before download.")


def resolve_cookie_consent(page, *, input_fn=input, output_fn=print):
    """Resolve real OneTrust cookie UI *before* clicking WoS Export.

    The owner's live Playwright trace identified
    #onetrust-consent-sdk .onetrust-pc-dark-filter intercepting Export.
    We only use visible consent controls, prefer explicitly Reject All
    optional cookies (privacy preserving), and never remove the overlay
    using JS/CSS or use force=True. If no rejection choice is available,
    the owner makes the choice on the visible banner.
    """
    sdk = page.locator("#onetrust-consent-sdk")
    if sdk.count() == 0:
        return
    overlay = sdk.locator(".onetrust-pc-dark-filter")
    banner = sdk.locator("#onetrust-banner-sdk")
    preferences = sdk.locator("#onetrust-pc-sdk")

    def blocked():
        return visible(overlay) or visible(banner) or visible(preferences)

    if not blocked():
        return

    # OneTrust supports this ID for reject-optional cookies on many sites.
    # Other versions expose a reject button in the visible preference dialog.
    reject = sdk.locator("#onetrust-reject-all-handler, "
                         ".ot-pc-refuse-all-handler, #onetrust-pc-reject-all-handler")
    if not visible(reject):
        reject = sdk.get_by_role(
            "button",
            name=re.compile(r"^(Reject All|Reject Optional|"
                            r"Отклонить все|Отказаться от всех|Alles ablehnen)$",
                            re.I))
    if visible(reject):
        output_fn("ONETRUST: rejecting optional cookies through the normal UI.")
        reject.first.click(timeout=15000)
        try:
            for layer in (overlay, banner, preferences):
                if visible(layer):
                    layer.first.wait_for(state="hidden", timeout=15000)
        except Exception:
            # Some consent dialogs remain after pressing Reject All and
            # require a further Save; let the owner decide on site controls.
            pass

    while blocked():
        output_fn("COOKIE_CHOICE_REQUIRED: OneTrust is covering the WoS Export button.")
        output_fn("In automated Chrome, choose Reject All or your preferred")
        output_fn("cookie option in the visible OneTrust dialog. Do not click")
        output_fn("through the dark overlay or enter account passwords here.")
        answer = input_fn("After cookie dialog closes press Enter; Q to stop: ").strip().lower()
        if answer in {"q", "quit", "stop", "выход"}:
            raise ExportError("Stopped: OneTrust cookie choice still pending")
    output_fn("ONETRUST_CLEARED: Export is no longer covered by cookie consent.")


def open_modal(page):
    """Open the site's ordinary Export > Plain text file menu, then wait."""
    resolve_cookie_consent(page)
    option = page.get_by_text("Plain text file", exact=True)
    if not visible(option):
        button = page.get_by_role("button", name=re.compile(r"^Export$", re.I))
        if not visible(button):
            raise ExportError("Results-page Export button not found")
        button.first.click(timeout=15000)
        option = page.get_by_text("Plain text file", exact=True)
        try:
            option.first.wait_for(state="visible", timeout=15000)
        except Exception as exc:
            raise ExportError("Plain text file option did not open") from exc
    option.first.click(timeout=15000)
    return locate_export_panel(page)

def select_record_content(page, modal):
    """Fail closed unless Full Record and Cited References visibly selected."""
    expected = "Full Record and Cited References"
    select = modal.locator("select")
    for n in range(select.count()):
        opts = select.nth(n).locator("option")
        labels = [opts.nth(j).inner_text().strip() for j in range(opts.count())]
        if expected in labels:
            select.nth(n).select_option(label=expected)
            return
    if visible(modal.get_by_text(expected, exact=True)):
        return  # Already shown as selected custom dropdown label.
    combo = modal.get_by_role("combobox")
    if visible(combo):
        combo.last.click()
        item = page.get_by_text(expected, exact=True)
        if visible(item):
            item.last.click()
            return
    raise ExportError("Full Record and Cited References selection cannot be verified")


def fill_range(modal, start: int, end: int):
    """Screenshot-verified WoS export UI: All records on page vs Records from.

    Select the range *radio*, not just its text. Never export page-only by
    accident when requesting record indices outside the current page.
    """
    radios = modal.locator("input[type=radio]")
    named_radio = modal.get_by_role("radio", name=re.compile(r"Records from", re.I))
    if visible(named_radio):
        named_radio.first.check()
    elif radios.count() == 2:
        radios.nth(1).check()
    else:
        raise ExportError("Cannot identify 'Records from' radio; stop before export")
    if radios.count() == 2 and not radios.nth(1).is_checked():
        raise ExportError("'Records from' radio not selected")
    # Input fields that can hold numeric ranges (radio inputs excluded).
    numeric = modal.locator('input[type="number"], input[inputmode="numeric"]')
    if numeric.count() < 2:
        numeric = modal.locator("input:not([type=radio]):not([type=checkbox]):not([type=hidden])")
    if numeric.count() != 2:
        raise ExportError(f"Expected 2 record-range input fields, found {numeric.count()}")
    # Playwright fill triggers native input/change events expected by React.
    numeric.nth(0).fill(str(start))
    numeric.nth(1).fill(str(end))
    if numeric.nth(0).input_value() != str(start) or numeric.nth(1).input_value() != str(end):
        raise ExportError("Range entry failed")
    if (not numeric.nth(0).is_enabled()) or (not numeric.nth(1).is_enabled()):
        raise ExportError("WoS range inputs disabled; range radio selection failed")
    if (end - start + 1) > 500:
        raise ExportError("WoS Full Record and Cited References export max is 500")


def run_live(args):
    # Owner's explicit acquisition rule (2026-10-29): do NOT create temporary
    # research export files on a local disk, or choose device/storage paths.
    # This legacy Playwright implementation saves downloads on local storage;
    # it MUST remain disabled until a verified direct-to-private-Drive method
    # is implemented with owner-approved access and no local staging.
    raise ExportError("DISABLED_LOCAL_STAGING: direct-to-private-Google-Drive implementation required")
    if not args.authorized_export:
        raise ExportError("Need --authorized-export: only run within your subscribed export rights")
    if args.delay_seconds < 8:
        raise ExportError("Minimum delay is 8 seconds between user-interface exports")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExportError("Install playwright Python package in the selected per-user staging environment first") from exc
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    batch_dir = output / "exports"
    batch_dir.mkdir(exist_ok=True)
    report = output / "export_manifest.json"
    if report.exists():
        state = json.loads(report.read_text(encoding="utf-8"))
        if state["expected_total"] != args.total or state["batch_size"] != args.batch_size:
            raise ExportError("Manifest belongs to a different search size; use an empty output dir")
    else:
        state = {"schema": "wos-ui-export-manifest/v1", "expected_total": args.total,
                 "batch_size": args.batch_size, "query_url": "MANUAL_LOGIN_AND_QUERY_NOT_CAPTURED",
                 "files": [], "public_promotion": False}
    # Browser profile is temporary: credentials/cookies are not retained on USB.
    with tempfile.TemporaryDirectory(prefix="browser_profile_", dir=output) as profile, sync_playwright() as p:
        launch = {"user_data_dir": profile, "headless": False, "accept_downloads": True}
        if args.chrome_exe:
            launch["executable_path"] = args.chrome_exe
        else:
            launch["channel"] = "chrome"
        context = p.chromium.launch_persistent_context(**launch)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.webofscience.com/wos/woscc/basic-search", wait_until="domcontentloaded", timeout=80000)
            print("Sign in in this browser window and open the FINAL checked WoS search with English+Article filters.")
            print("Confirm query count equals --total. Do not use the six-term exploratory search for the final corpus.")
            input("When the filtered result page is visible, press Enter here to start the FIRST batch... ")
            if not SAFE_HOST.match(page.url) or "/wos/woscc/" not in page.url:
                raise ExportError("Current browser page is not WoS Core Collection")
            state["query_url"] = page.url
            page_text = page.locator("body").inner_text()
            counts = re.findall(r"([\d,]+) results? from Web of Science", page_text, re.I)
            if not counts:
                raise ExportError("WoS result count not visible; do not guess --total")
            actual_count = int(counts[0].replace(",", ""))
            if actual_count != args.total:
                raise ExportError(f"WoS page has {actual_count}, expected --total {args.total}")
            if not re.search(r"Document Types:\s*Article\b", page_text, re.I):
                raise ExportError("Document Types: Article refinement is missing")
            if not re.search(r"Languages:\s*English\b", page_text, re.I):
                raise ExportError("Languages: English refinement is missing")
            print(f"REFINED_SEARCH_PREFLIGHT_PASS count={actual_count} English=on Article=on")
            seen_uids = set()
            count_done = 0
            for start, end in ranges(args.total, args.batch_size):
                target = batch_dir / f"wos_{start:06d}_{end:06d}.txt"
                if target.exists():
                    audit = audit_export(target.read_bytes(), end - start + 1)
                    if seen_uids.intersection(audit["uids"]):
                        raise ExportError("Duplicate WoS UT across existing batches")
                    seen_uids.update(audit["uids"])
                    if not any(row["filename"] == target.name for row in state["files"]):
                        row = {k: v for k, v in audit.items() if k != "uids"}
                        row.update({"range_start": start, "range_end": end, "filename": target.name})
                        state["files"].append(row)
                        report.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    print(f"SKIP existing validated {target.name}")
                    continue
                if args.max_batches and count_done >= args.max_batches:
                    break
                print(f"Exporting {start}–{end} ({end-start+1} records)...")
                try:
                    modal = open_modal(page)
                    fill_range(modal, start, end)
                    select_record_content(page, modal)
                    button = modal.get_by_role("button", name=re.compile(r"^Export$", re.I))
                    if not visible(button):
                        raise ExportError("Export confirmation button not found in dialog")
                    with page.expect_download(timeout=180000) as handle:
                        button.first.click()
                    dl = handle.value
                    if not dl.suggested_filename.lower().endswith(".txt"):
                        raise ExportError("WoS did not create a .txt export")
                    staging = target.with_suffix(".partial")
                    dl.save_as(staging)
                    audit = audit_export(staging.read_bytes(), end - start + 1)
                    if seen_uids.intersection(audit["uids"]):
                        raise ExportError("Duplicate WoS UT across batches; abort without promotion")
                    seen_uids.update(audit["uids"])
                    staging.replace(target)
                except Exception as exc:
                    snapshot = output / f"FAILED_{start:06d}_{end:06d}.png"
                    page.screenshot(path=str(snapshot))
                    raise ExportError(f"Stopped at {start}–{end}: {exc}. Screenshot {snapshot}") from exc
                row = {k: v for k, v in audit.items() if k != "uids"}
                row.update({"range_start": start, "range_end": end, "filename": target.name})
                state["files"].append(row)
                report.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                count_done += 1
                status = "NR_DISCREPANCY_REVIEW" if row["nr_anomaly_count"] else "NR_MATCH"
                print(f"PASS_RECORDS {target.name}: {row['records']} records, {row['cited_references']} cited refs, {status}={row['nr_anomaly_count']}, SHA {row['sha256']}")
                if count_done == 1:
                    input("CHECK first downloaded file and UI; press Enter to continue or Ctrl+C to stop... ")
                time.sleep(args.delay_seconds)
            print(f"COMPLETE session: {count_done} new exported batches. Manifest: {report}")
        finally:
            context.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total", type=int, required=True, help="Exact FINAL filtered WoS result count")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--output", default=str(Path.home() / "AppData" / "Local" / "Pro_Adherence" / "WoS_staging"))
    parser.add_argument("--chrome-exe", default=None)
    parser.add_argument("--max-batches", type=int, default=1, help="Defaults to ONE for safe UI trial; use 0 for all")
    parser.add_argument("--delay-seconds", type=float, default=12)
    parser.add_argument("--authorized-export", action="store_true", help="Confirm subscription permits these exports")
    parser.add_argument("--dry-run", action="store_true", help="Print batch ranges only; no Playwright or browser")
    args = parser.parse_args(argv)
    batches = ranges(args.total, args.batch_size)
    print(f"Planned batches: {len(batches)}; first: {batches[0]}; last: {batches[-1]}")
    if args.dry_run:
        for start, end in batches:
            print(f"{start:6d} {end:6d}")
        return 0
    try:
        run_live(args)
    except ExportError as exc:
        print(f"WOS_UI_EXPORT_STOP: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())