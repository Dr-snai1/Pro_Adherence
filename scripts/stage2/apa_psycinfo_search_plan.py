#!/usr/bin/env python3
"""Offline APA PsycINFO / EBSCOhost lexical search candidate from frozen PubMed.

No network, credentials, licensed data, implicit source eligibility decisions,
live hit counts, or empirical equivalence claims. The six frozen blocks are
extracted by the already-tested WoS source translator, not reinvented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from wos_search_plan import SearchPlanError, lexical_groups

SOURCE = "configs/pubmed/medication-adherence-SELECTED.v1.json"
NAMES = (
    "rare_terms",
    "general_adherence",
    "persistence",
    "medication_classes",
    "measurement_proxies",
    "abbreviations",
)
COUNTS = (2, 54, 15, 69, 36, 4)


def field_query(terms: list[str], field: str) -> str:
    """EBSCOhost format: TI ("foo bar" OR other), not WoS TI=(...)."""
    if field not in {"TI", "AB", "KW"}:
        raise ValueError("UNSUPPORTED_EBSCO_FIELD")
    if not terms or any(not t or any(c in t for c in '"\r\n') for t in terms):
        raise SearchPlanError("INVALID_FROZEN_TERM")
    pieces = [f'"{t}"' if " " in t else t for t in terms]
    return f"{field} (" + " OR ".join(pieces) + ")"


def combine_fields(terms: list[str], fields: tuple[str, ...]) -> str:
    if not fields or len(set(fields)) != len(fields):
        raise SearchPlanError("BAD_FIELD_SET")
    return "(" + " OR ".join(field_query(terms, f) for f in fields) + ")"


def make_plan(payload: bytes) -> dict:
    obj = json.loads(payload.decode("utf-8"))
    if obj.get("query_artifact") != "medication-adherence-pubmed-selected":
        raise SearchPlanError("NOT_FROZEN_SELECTED_SOURCE")
    original = obj["queries"]["SELECTED"]
    groups = lexical_groups(original)
    assert tuple(map(len, groups)) == COUNTS
    terms = [t for group in groups for t in group]
    assert len(terms) == len(set(terms)) == 180
    primary = ("TI", "AB")
    extended = ("TI", "AB", "KW")
    return {
        "schema": "stage2-apa-psycinfo-ebsco-query-candidate/v1",
        "source_config_sha256": hashlib.sha256(payload).hexdigest(),
        "source_query_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "source_term_counts": list(COUNTS),
        "terms": 180,
        "primary_fields": list(primary),
        "sensitivity_fields": list(extended),
        "blocks": [
            {"name": NAMES[i], "term_count": len(group),
             "primary_query": combine_fields(group, primary),
             "keyword_sensitivity_query": combine_fields(group, extended)}
            for i, group in enumerate(groups)
        ],
        "primary_single_query": combine_fields(terms, primary),
        "keyword_sensitivity_single_query": combine_fields(terms, extended),
        "filters_not_automatically_applied": {
            "database": "APA PsycINFO ONLY (not PsycARTICLES or PsycTests)",
            "language": "English",
            "publication_type": "Journal Article / equivalent ONLY IF UI validates",
        },
        "status": "SOURCE_DERIVED_CANDIDATE_NOT_RUN_IN_LICENSED_EBSCO",
        "methodological_cautions": [
            "PubMed MeSH noexp has no automatic APA Thesaurus counterpart.",
            "PubMed tiab proximity ~0/~1 is NOT equivalent to quoted EBSCO phrase.",
            "EBSCO KW is a separate sensitivity search, never silently in primary.",
            "EBSCO UI language/publication type and DB selection need live audit.",
            "Search History result counts and exact query/expanded query/filters "
            "must be downloaded for the live run.",
            "Article-only eligibility is a scientific contract, not guaranteed "
            "by EBSCO publication type facets.",
            "Full CR reference lists are NOT guaranteed in EBSCO RIS export.",
            "Institution-enabled bulk exports and personal MyEBSCO are not presumed.",
        ],
    }


def write_plan(plan: dict, out: Path) -> list[Path]:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("NO_OVERWRITE_OF_EXISTING_OUTPUT")
    out.mkdir(parents=True, exist_ok=True)
    created = []
    for i, block in enumerate(plan["blocks"], 1):
        for kind in ("primary_query", "keyword_sensitivity_query"):
            path = out / f"apa_{i:02d}_{block['name']}_{kind}.txt"
            path.write_text(block[kind] + "\n", encoding="utf-8")
            created.append(path)
    for name, key in (
        ("apa_PRIMARY_all_180_TI_AB_CANDIDATE.txt", "primary_single_query"),
        ("apa_SENSITIVITY_all_180_TI_AB_KW.txt", "keyword_sensitivity_single_query"),
    ):
        path = out / name
        path.write_text(plan[key] + "\n", encoding="utf-8")
        created.append(path)
    p = out / "apa_candidate_manifest.json"
    p.write_text(json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    created.append(p)
    return created


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=Path(SOURCE))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--print", choices=("primary", "keyword_sensitivity", "rare"))
    args = ap.parse_args(argv)
    plan = make_plan(args.source.read_bytes())
    if args.print:
        print({"primary": plan["primary_single_query"],
               "keyword_sensitivity": plan["keyword_sensitivity_single_query"],
               "rare": plan["blocks"][0]["primary_query"]}[args.print])
    if args.out:
        files = write_plan(plan, args.out)
        print(f"APA_CANDIDATE_READY terms=180 groups=6 files={len(files)} "
              f"config_sha256={plan['source_config_sha256']}")
    if not args.print and not args.out:
        print("APA PsycINFO EBSCOhost candidate: six source blocks / 180 terms; "
              "TI+AB primary; KW sensitivity only; no live source validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
