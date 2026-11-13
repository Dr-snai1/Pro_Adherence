#!/usr/bin/env python3
"""Audit a *local* original APA PsycINFO / EBSCO RIS export, without edits.

Scientific records remain private (restricted Drive). This script operates
offline, emits only aggregates/digests and checks source IDs; no deduplication,
no network, no full-text synthesis, no invented cited references.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ENTRY = re.compile(r"^([A-Z0-9]{2})  - ?(.*)$")
CITED_REFERENCE_KEYS = ("CR", "C1", "RX", "RN", "RP")


class RisAuditError(ValueError):
    pass


def parse_ris(raw: bytes) -> list[dict[str, list[str]]]:
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise RisAuditError("RIS_ENCODING_NOT_UTF8") from exc
    rows: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] | None = None
    last_key: str | None = None
    for number, line in enumerate(lines, 1):
        found = ENTRY.match(line)
        if found:
            key, value = found.groups()
            if key == "TY":
                if current is not None:
                    raise RisAuditError(f"MISSING_ER_BEFORE_RECORD_{len(rows)+1}")
                current = {"TY": [value]}
                last_key = "TY"
                continue
            if current is None:
                raise RisAuditError(f"ORPHAN_RIS_TAG_LINE_{number}")
            current.setdefault(key, []).append(value)
            last_key = key
            if key == "ER":
                rows.append(current)
                current = None
                last_key = None
            continue
        if not line.strip():
            continue
        if current is None or last_key is None:
            raise RisAuditError(f"ORPHAN_NON_TAG_LINE_{number}")
        # EBSCO abstracts sometimes have genuine RIS line continuations.
        current[last_key][-1] += "\n" + line
    if current is not None:
        raise RisAuditError("UNTERMINATED_LAST_RECORD")
    if not rows:
        raise RisAuditError("NO_RIS_RECORDS")
    return rows


def audit(raw: bytes, *, expected: int | None = None,
          expected_database: str = "APA PsycInfo") -> dict:
    rows = parse_ris(raw)
    if expected is not None and expected != len(rows):
        raise RisAuditError(f"RECORD_COUNT_MISMATCH expected={expected} actual={len(rows)}")
    ids: list[str] = []
    for i, r in enumerate(rows, 1):
        if r.get("DB") != [expected_database]:
            raise RisAuditError(f"WRONG_SOURCE_DATABASE record={i}")
        if len(r.get("AN", [])) != 1 or not r["AN"][0]:
            raise RisAuditError(f"MISSING_OR_DUPLICATE_AN record={i}")
        ids.append(r["AN"][0])
    dupes = [key for key, ct in Counter(ids).items() if ct > 1]
    if dupes:
        raise RisAuditError(f"DUPLICATE_APA_SOURCE_IDS count={len(dupes)}")
    types = Counter(r.get("TY", [""])[0] for r in rows)
    languages = Counter(v for r in rows for v in r.get("LA", ["(missing)"]))
    publication_types = Counter(v for r in rows for v in r.get("N1", []))
    doi_values = [r["DO"][0].strip().lower() for r in rows
                  if r.get("DO") and r["DO"][0].strip()]
    return {
        "schema": "stage2-apa-ris-audit/v1",
        "source": expected_database,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "records": len(rows),
        "unique_accession_numbers": len(ids),
        "first_an": ids[0],
        "last_an": ids[-1],
        "ty_counts": dict(sorted(types.items())),
        "language_counts": dict(sorted(languages.items())),
        "n1_type_counts": dict(sorted(publication_types.items())),
        "with_article_n1": sum("Journal Article" in r.get("N1", []) for r in rows),
        "with_abstract": sum(bool(r.get("AB")) for r in rows),
        "with_doi": len(doi_values),
        "distinct_normalized_dois": len(set(doi_values)),
        "with_title": sum(bool(r.get("TI")) for r in rows),
        "with_author": sum(bool(r.get("AU")) for r in rows),
        "with_date": sum(bool(r.get("Y1")) for r in rows),
        "with_keywords": sum(bool(r.get("KW")) for r in rows),
        "with_journal": sum(bool(r.get("JO")) for r in rows),
        "with_reference_tags": sum(any(k in r for k in CITED_REFERENCE_KEYS)
                                   for r in rows),
        "with_same_an_and_id": sum(r.get("ID") == r.get("AN") for r in rows),
        "no_cited_references_claim": "no_cited_references_exposed_in_RIS"
            if not any(any(k in r for k in CITED_REFERENCE_KEYS) for r in rows)
            else "some_reference_tags_present_audit_before_use",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ris_file", type=Path)
    p.add_argument("--expected", type=int)
    p.add_argument("--out", type=Path, help="New audit-only JSON, without bibliographic text")
    args = p.parse_args(argv)
    report = audit(args.ris_file.read_bytes(), expected=args.expected)
    s = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        if args.out.exists():
            raise FileExistsError("AUDIT_OUTPUT_ALREADY_EXISTS")
        args.out.write_text(s, encoding="utf-8")
    print("APA_RIS_AUDIT_PASS records=", report["records"],
          "unique_AN=", report["unique_accession_numbers"],
          "source=", report["source"],
          "with_DOI=", report["with_doi"],
          "with_AB=", report["with_abstract"],
          "with_reference_tags=", report["with_reference_tags"],
          "SHA256=", report["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
