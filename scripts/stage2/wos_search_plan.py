#!/usr/bin/env python3
"""Offline, deterministic WoS query translation of the frozen PubMed SELECTED.

Produce CANDIDATE lexical WoS queries; this is not equivalence or approval.
No network, private corpus, credentials, or WoS API use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

_GROUP_COUNTS = (2, 54, 15, 69, 36, 4)
_GROUP_NAMES = (
    "rare_source_terms_without_MeSH",
    "adherence_compliance_general",
    "persistence_historical",
    "medication_class_context",
    "measurement_proxy_only",
    "measurement_abbreviations",
)
_FIELD = re.compile(r'"([^"]+)"\[tiab:~([01])\]')
_SINGLE = re.compile(r'\b(pharmacoadherence|pharmionics)\[tiab\]')
_SOURCE_DEFAULT = "configs/pubmed/medication-adherence-SELECTED.v1.json"


class SearchPlanError(ValueError):
    """Bad/mutated source cannot silently change the translated vocabulary."""


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def lexical_groups(original: str) -> list[list[str]]:
    """Extract six frozen OR blocks while *retaining* every explicit lexical term.

    PubMed-only MeSH branch is annotated as unmappable, not converted to an
    invented WoS thesaurus expression. PubMed phrase proximity ~0/~1 cannot
    be treated as identical to the WoS quoted-phrase operator.
    """
    blocks = original.split("\n  OR (")
    if len(blocks) != 6 or "Medication Adherence" not in blocks[0]:
        raise SearchPlanError("UNEXPECTED_PUBMED_GROUP_STRUCTURE")
    if not original.rstrip().endswith('AND "journal article"[pt]'):
        raise SearchPlanError("UNEXPECTED_PUBMED_FILTERS")
    out: list[list[str]] = []
    for index, block in enumerate(blocks):
        quoted = [m.group(1) for m in _FIELD.finditer(block)]
        singles = _SINGLE.findall(block) if index == 0 else []
        terms = singles + quoted
        if len(terms) != _GROUP_COUNTS[index]:
            raise SearchPlanError(f"BLOCK_{index+1}_TERM_COUNT_CHANGE")
        if len(set(terms)) != len(terms):
            raise SearchPlanError("DUPLICATE_TERMS_IN_SOURCE_BLOCK")
        out.append(terms)
    flat = [x for group in out for x in group]
    if len(flat) != 180 or len(set(flat)) != 180:
        raise SearchPlanError("FROZEN_180_LEXICAL_TERMS_CHANGED")
    if re.findall(r'\[[^\]]+\]', original).count('[mh:noexp]') != 1:
        raise SearchPlanError("UNEXPECTED_MESH_COUNT")
    return out


def to_wos(terms: list[str], field: str = "TS") -> str:
    if field not in {"TS", "TI", "AB"}:
        raise ValueError("UNSUPPORTED_FIELD")
    if not terms or any('"' in t or '\n' in t for t in terms):
        raise SearchPlanError("INVALID_LEXICAL_TERM")
    return f"{field}=(" + " OR ".join(
        f'"{t}"' if " " in t else t for t in terms
    ) + ")"


def make_plan(payload: bytes) -> dict:
    source = json.loads(payload.decode("utf-8"))
    if source.get("query_artifact") != "medication-adherence-pubmed-selected":
        raise SearchPlanError("UNEXPECTED_QUERY_ARTIFACT")
    original = source["queries"]["SELECTED"]
    groups = lexical_groups(original)
    raw_blocks = [to_wos(terms) for terms in groups]
    all_terms = [term for group in groups for term in group]
    all_query = to_wos(all_terms)
    # Nearer-field sensitivity only. Neither WoS mode is a literal PubMed
    # translation of controlled MeSH or proximity-slop instructions.
    tiab_query = "(" + to_wos(all_terms, "TI") + " OR " + to_wos(all_terms, "AB") + ")"
    return {
        "schema": "stage2-wos-query-candidate/v1",
        "source_config_sha256": digest(payload),
        "source_query_sha256": digest(original.encode("utf-8")),
        "lexical_term_count": len(all_terms),
        "source_groups": [
            {"name": _GROUP_NAMES[i], "term_count": len(terms),
             "query": raw_blocks[i]}
            for i, terms in enumerate(groups)
        ],
        "all_query": all_query,
        "title_abstract_sensitivity_query": tiab_query,
        "source_search_filters": {"language": "English", "document_type": "Article"},
        "query_status": "CANDIDATE_NOT_VALIDATED_IN_WOS_UI",
        "limitations": [
            "PubMed MeSH noexp term has no WoS controlled-vocabulary equivalent.",
            "PubMed tiab:~0/1 is NOT identical to WoS quoted phrase.",
            "WoS Topic includes Author Keywords and Keywords Plus unlike PubMed tiab.",
            "WoS Exact Search setting may change lemmatization/stemming.",
            "WoS Document Types Article is not identical to PubMed journal article pt.",
            "No method/term addition; candidate must be empirically assessed and versioned.",
        ],
    }


def write_plan(plan: dict, output: Path) -> list[Path]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Refuse to overwrite a nonempty output directory")
    output.mkdir(parents=True, exist_ok=True)
    created = []
    for i, block in enumerate(plan["source_groups"], 1):
        p = output / f"wos_{i:02d}_{block['name']}.txt"
        p.write_text(block["query"] + "\n", encoding="utf-8")
        created.append(p)
    for name, query in (("wos_all_180_terms_CANDIDATE.txt", plan["all_query"]),
                        ("wos_title_abstract_SENSITIVITY.txt",
                         plan["title_abstract_sensitivity_query"])):
        p = output / name
        p.write_text(query + "\n", encoding="utf-8")
        created.append(p)
    p = output / "wos_plan_manifest.json"
    p.write_text(json.dumps(plan, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    created.append(p)
    return created


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=Path(_SOURCE_DEFAULT))
    ap.add_argument("--out", type=Path, help="New empty output directory for private candidate files")
    ap.add_argument("--print", action="store_true", help="Print full candidate query only")
    args = ap.parse_args(argv)
    plan = make_plan(args.source.read_bytes())
    if args.print:
        print(plan["all_query"])
    if args.out:
        written = write_plan(plan, args.out)
        print("STAGE2_WOS_QUERY_CANDIDATE_CREATED",
              "groups=6 terms=180 files=", len(written),
              "source_sha256=", plan["source_config_sha256"])
    if not args.out and not args.print:
        print("Stage2 WoS query candidate: six source blocks / 180 lexical terms.")
        print("Run with --out <NEW_EMPTY_DIR> or --print; English/Article filters in WoS UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
