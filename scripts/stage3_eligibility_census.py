"""Offline, restricted Stage2 -> Stage3 canonical cohort census (NO model inference).

Usage:
  python scripts/stage3_eligibility_census.py \
      --archive /secure/Stage2_frozen.zip \
      --private-output-dir /secure/stage3_census

The script never contacts the network and never writes raw titles, abstracts or
citations. It still handles restricted article IDs/lineage: output is PRIVATE,
never commit or publish the generated files. Requires the exact frozen ZIP hash.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import zipfile

from pro_adherence.stage3_contracts import (
    FROZEN_STAGE2_ZIP_SHA256,
    Stage3ContractError,
    normalize_stage3_source_flags,
    plan_stage3_canonical_eligibility,
)

EXPECTED_FILES = {
    "canonical_articles.jsonl.gz",
    "source_records.jsonl.gz",
    "identity_decisions.jsonl.gz",
    "citation_links.jsonl.gz",
    "author_observations.jsonl.gz",
    "affiliation_observations.jsonl.gz",
    "loo_pubmed.json", "loo_woscc.json", "loo_apa_psycinfo.json", "manifest.json",
}
POLICY_ID = "stage3-journal-primary-canonical/v1-2026-11-10"


def _sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _read_jsonl(z: zipfile.ZipFile, name: str):
    with z.open(name) as packed, gzip.GzipFile(fileobj=packed) as plain:
        for line in plain:
            if line.strip():
                yield json.loads(line)


def calculate(archive_path: Path) -> dict:
    """Compute all canonical statuses with strict source lineage; in memory only."""
    actual_sha = _sha256_file(archive_path)
    if actual_sha != FROZEN_STAGE2_ZIP_SHA256:
        raise Stage3ContractError("frozen Stage2 archive SHA256 mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        if set(archive.namelist()) != EXPECTED_FILES:
            raise Stage3ContractError("Stage2 ZIP member inventory mismatch")
        if archive.testzip() is not None:
            raise Stage3ContractError("Stage2 ZIP CRC mismatch")
        metadata = json.load(archive.open("manifest.json"))
        if (metadata.get("schema") != "pro-adherence-stage2-three-source-private/v1"
            or metadata.get("publication_authorized") is not False
            or metadata.get("canonical_articles") != 57293
            or metadata.get("source_records") != 87511):
            raise Stage3ContractError("Stage2 embedded manifest mismatch")
        raw_sources = [
            {
                "source_record_id": row.get("source_record_id"),
                "source_id": row.get("source_id"),
                "record_family": row.get("record_family"),
                "raw_export_sha256": row.get("raw_export_sha256"),
                "raw_record_ordinal": row.get("raw_record_ordinal"),
                **{key: row[key] for key in
                   ("retracted_article", "peer_review_unknown",
                    "cited_references_count_anomaly") if key in row},
            }
            for row in _read_jsonl(archive, "source_records.jsonl.gz")
        ]
        canonical = list(_read_jsonl(archive, "canonical_articles.jsonl.gz"))
    if len(raw_sources) != 87511 or len(canonical) != 57293:
        raise Stage3ContractError("Stage2 input record counts mismatch")
    normalized = normalize_stage3_source_flags(raw_sources)
    result = plan_stage3_canonical_eligibility(canonical, normalized)
    source_counts = dict(Counter(item["source_id"] for item in normalized))
    if source_counts != metadata.get("source_counts"):
        raise Stage3ContractError("Stage2 frozen source counts mismatch")
    flags = result["source_flag_counts"]
    if (flags.get("is_retracted", 0) != metadata.get("apa_retraction_flags")
        or flags.get("wos_nr_cr_mismatch", 0) !=
        metadata.get("wos_nr_cr_anomaly_flags")
        or flags.get("peer_review_unknown", 0) != 19):
        raise Stage3ContractError("Stage2 source flag census mismatch")

    # Independent method: Stage2's pre-existing article_only_eligible is
    # journal-family membership; new rule removes observed retracted articles.
    stage2_preexisting = {a["canonical_article_id"]: a.get("article_only_eligible")
                          for a in canonical}
    if any(type(v) is not bool for v in stage2_preexisting.values()):
        raise Stage3ContractError("Stage2 article-only eligibility missing")
    deviations = []
    for row in result["rows"]:
        old = stage2_preexisting[row["article_id"]]
        expected = old and not row["is_retracted"]
        if expected != row["primary_eligible"]:
            deviations.append(row["article_id"])
    if deviations:
        raise Stage3ContractError(
            f"Stage2 independent eligibility comparison mismatches: {len(deviations)}")

    result["input_archive_sha256"] = actual_sha
    result["source_manifest_schema"] = metadata["schema"]
    result["policy_id"] = POLICY_ID
    result["independent_stage2_article_only_eligible_count"] = sum(stage2_preexisting.values())
    result["independent_eligible_minus_retraction_count"] = (
        result["independent_stage2_article_only_eligible_count"]
        - sum(a["is_retracted"] and stage2_preexisting[a["article_id"]]
              for a in result["rows"])
    )
    result["source_record_counts_by_database"] = source_counts
    # The accepted restricted artifact preserves Stage2's frozen row order.
    # The planning function sorts by ID internally; retain original read order
    # so this exact ZIP produces the same deterministic compressed bytes.
    result["source_canonical_order"] = [
        a["canonical_article_id"] for a in canonical
    ]
    return result


def write_private_artifacts(result: dict, output_dir: Path) -> dict:
    """Write compressed PRIVATE roster, with deterministic gzip bytes and SHA.

    Full roster order equals frozen canonical JSONL order. A synthetic unit test
    without source_canonical_order falls back to caller's supplied row order.
    """
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    manifest_path = output_dir / "article_eligibility_stage3_private.jsonl.gz"
    temp_path = output_dir / "article_eligibility_stage3_private.jsonl.gz.tmp"
    indexed = {row["article_id"]: row for row in result["rows"]}
    if len(indexed) != result["article_count"]:
        raise Stage3ContractError("private derived manifest ID coverage mismatch")
    order = result.get("source_canonical_order") or [
        row["article_id"] for row in result["rows"]
    ]
    if len(order) != len(indexed) or len(set(order)) != len(indexed) or set(order) != set(indexed):
        raise Stage3ContractError("frozen canonical row order mismatch")
    fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=6,
                           mtime=0) as output:
            for article_id in order:
                row = dict(indexed[article_id], policy_id=POLICY_ID)
                output.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    os.replace(temp_path, manifest_path)
    os.chmod(manifest_path, 0o600)
    manifest_hash = _sha256_file(manifest_path)

    flags = result.get("source_flag_counts", {})
    source_positive = {
        key: flags.get(key, 0) for key in
        ("is_retracted", "peer_review_unknown", "wos_nr_cr_mismatch")
    }
    source_not_exposed = {
        key + "_not_exposed": flags.get(key + "_not_exposed", 0)
        for key in ("is_retracted", "peer_review_unknown", "wos_nr_cr_mismatch")
    }
    canonical_flags = result.get("canonical_flag_counts", {})
    summary = {
        "schema": "pro-adherence-stage3-private-cohort-census/v1",
        "access_class": "restricted",
        "publication_authorized": False,
        "policy_id": POLICY_ID,
        "frozen_archive_sha256": result.get("input_archive_sha256"),
        "frozen_source_record_count": result.get("source_record_count"),
        "frozen_canonical_group_count": result["article_count"],
        "stage2_article_only_eligible_count":
            result.get("independent_stage2_article_only_eligible_count"),
        "primary_eligible_count": result["primary_eligible_count"],
        "eligibility_status_counts": result["eligibility_status_counts"],
        "canonical_flag_counts": {
            "is_retracted": canonical_flags.get("retracted", 0),
            "mixed_book_journal": canonical_flags.get("mixed_book_journal", 0),
            "peer_review_unknown": canonical_flags.get("peer_review_unknown", 0),
            "wos_nr_cr_mismatch": canonical_flags.get("wos_nr_cr_mismatch", 0),
        },
        "source_flag_counts": source_positive,
        "source_not_exposed_counts": source_not_exposed,
        "source_counts_by_database":
            result.get("source_record_counts_by_database", {}),
        "source_membership_coverage": result.get("source_record_count"),
        "independent_stage2_comparison_mismatches": 0,
        "derived_manifest_file": manifest_path.name,
        "derived_manifest_sha256": manifest_hash,
        "derived_manifest_size_bytes": manifest_path.stat().st_size,
        "derived_manifest_row_count": result["article_count"],
        "source_flag_exposure_note": (
            "APA retraction/peer-review, WoS NR-CR; other sources "
            "not exposed != false; no evidence to exclude unflagged retractions"
        ),
    }
    summary_path = output_dir / "eligibility_summary_stage3_private.json"
    fd = os.open(output_dir / "eligibility_summary_stage3_private.json.tmp",
                 os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(summary, output, ensure_ascii=False, sort_keys=True, indent=2)
        output.write("\n")
    os.replace(output_dir / "eligibility_summary_stage3_private.json.tmp", summary_path)
    os.chmod(summary_path, 0o600)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--private-output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = calculate(args.archive)
    summary = write_private_artifacts(result, args.private_output_dir)
    # No identifiers, licensed content, source records or citation rows to stdout.
    print(json.dumps({
        "status": "PRIVATE_CENSUS_PASS",
        "canonical": summary["frozen_canonical_group_count"],
        "primary_eligible": summary["primary_eligible_count"],
        "status_counts": summary["eligibility_status_counts"],
        "source_flag_counts": {
            k: v for k, v in summary["source_flag_counts"].items()
            if not k.endswith("_not_exposed")
        },
        "archive_sha256": summary["frozen_archive_sha256"],
        "derived_manifest_sha256": summary["derived_manifest_sha256"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
