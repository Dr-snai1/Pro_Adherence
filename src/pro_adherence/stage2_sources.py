"""Stage 2: conservative, offline Web of Science tagged-text import and source views.

No website automation, credentials, network access or public data promotion.
WoS exports remain private; this module only produces in-memory metadata views.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
from typing import Any

_SOURCE = "woscc"
_TAG = re.compile(r"^([A-Z][A-Z0-9])(?: (.*))?$")
_DOI = re.compile(r"10\.\d{4,9}/[^\s;,\]]+", re.IGNORECASE)
_PMID = re.compile(r"^[1-9][0-9]*$")


class SourceFormatError(ValueError):
    """Reject ambiguous or incomplete exports rather than inventing records."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    s = value.strip()
    s = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", s, flags=re.I)
    s = s.strip().rstrip(".,;")
    return s.casefold() if _DOI.fullmatch(s) else None


def _values(tags: dict[str, list[str]], tag: str) -> list[str]:
    return [s.strip() for s in tags.get(tag, []) if s.strip()]


def _single(tags: dict[str, list[str]], tag: str) -> str | None:
    vals = _values(tags, tag)
    return " ".join(vals) if vals else None


def _convert(tags: dict[str, list[str]], ordinal: int, digest: str) -> dict[str, Any]:
    uid = _single(tags, "UT")
    if not uid or not uid.upper().startswith("WOS:"):
        raise SourceFormatError("WOS_UT_REQUIRED")
    pmid = _single(tags, "PM")
    if pmid and not _PMID.fullmatch(pmid):
        raise SourceFormatError("INVALID_PMID")
    doi_raw = _single(tags, "DI")
    doi = normalize_doi(doi_raw)
    if doi_raw and not doi:
        raise SourceFormatError("INVALID_DOI")
    return {
        "source_id": _SOURCE,
        "source_native_id": uid,
        "source_record_id": f"{_SOURCE}:{uid}",
        "raw_export_sha256": digest,
        "raw_record_ordinal": ordinal,
        "title": _single(tags, "TI"),
        "abstract": _single(tags, "AB"),
        "year": _single(tags, "PY"),
        "language": _single(tags, "LA"),
        "document_type": _single(tags, "DT"),
        "venue": _single(tags, "SO"),
        "doi": doi,
        "pmid": pmid,
        "authors_raw": _values(tags, "AU"),
        "addresses_raw": _values(tags, "C1"),
        "affiliations_raw": _values(tags, "C3"),
        "keywords_raw": _values(tags, "DE") + _values(tags, "ID"),
        "cited_references_raw": _values(tags, "CR"),
        "access_class": "restricted-license",
        "publication_authorized": False,
    }


def parse_wos_tagged_export(payload: bytes) -> dict[str, Any]:
    """Parse downloaded WoS Core Collection 'Plain text' files, no live queries.

    Retain whole-file SHA and record ordinal as immutable provenance pointers.
    Field contents are not licensed for publication by successful parsing.
    """
    if not payload:
        raise SourceFormatError("EMPTY_EXPORT")
    try:
        lines = payload.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise SourceFormatError("UTF8_EXPORT_REQUIRED") from exc
    if not lines or not lines[0].startswith("FN "):
        raise SourceFormatError("WOS_FN_HEADER_REQUIRED")
    digest = sha256(payload)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    tags: dict[str, list[str]] | None = None
    last_tag: str | None = None
    finished = False
    for line in lines[1:]:
        if finished:
            if line.strip():
                raise SourceFormatError("TRAILING_DATA")
            continue
        if line == "EF":
            if tags is not None:
                raise SourceFormatError("UNTERMINATED_RECORD")
            finished = True
            continue
        if line == "ER":
            if tags is None:
                raise SourceFormatError("ER_WITHOUT_RECORD")
            rec = _convert(tags, len(result) + 1, digest)
            if rec["source_native_id"] in seen:
                raise SourceFormatError("DUPLICATE_WOS_UID")
            seen.add(rec["source_native_id"])
            result.append(rec)
            tags = None
            last_tag = None
            continue
        match = _TAG.match(line)
        if match:
            tag, value = match.groups()
            if tag in {"FN", "VR"}:
                if tags is not None:
                    raise SourceFormatError("HEADER_IN_RECORD")
                continue
            if tags is None:
                if tag != "PT":
                    raise SourceFormatError("RECORD_MUST_START_PT")
                tags = {}
            if tag == "PT" and tags:
                raise SourceFormatError("NESTED_RECORD")
            tags.setdefault(tag, []).append(value or "")
            last_tag = tag
        elif line.startswith("   ") and tags is not None and last_tag:
            tags[last_tag][-1] += " " + line.strip()
        elif line.strip():
            raise SourceFormatError("UNKNOWN_EXPORT_LINE")
    if tags is not None or not finished:
        raise SourceFormatError("EXPORT_NOT_COMPLETE")
    if not result:
        raise SourceFormatError("NO_RECORDS")
    return {"schema": "stage2-wos-tagged-export/v1", "source_id": _SOURCE,
            "raw_export_sha256": digest, "records": result,
            "record_count": len(result), "access_class": "restricted-license",
            "publication_authorized": False}


def _compatible(left: set[str], right: set[str]) -> bool:
    return len(left | right) <= 1


def reconcile_sources(records: list[dict[str, Any]], omit_sources: set[str] | None = None) -> dict[str, Any]:
    """Exact DOI/PMID only; conflicted identifiers never force an auto-merge.

    This is a provisional identity graph, not scientific article eligibility.
    Missing citations are missing *observations*, not proof of uncitedness.
    """
    omitted = omit_sources or set()
    kept = sorted((r for r in records if r["source_id"] not in omitted),
                  key=lambda r: r["source_record_id"])
    keys = [r["source_record_id"] for r in kept]
    if len(set(keys)) != len(keys):
        raise SourceFormatError("DUPLICATE_SOURCE_RECORD_ID")
    parent = list(range(len(kept)))
    members = [{i} for i in range(len(kept))]
    dois = [{r["doi"]} if r.get("doi") else set() for r in kept]
    pmids = [{str(r["pmid"])} if r.get("pmid") else set() for r in kept]
    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i
    blocked: set[tuple[str, str]] = set()
    for i, r in enumerate(kept):
        for j in range(i):
            q = kept[j]
            a, b = root(i), root(j)
            if a == b:
                continue
            same = ((r.get("doi") and r["doi"] == q.get("doi")) or
                    (r.get("pmid") and str(r["pmid"]) == str(q.get("pmid"))))
            if not same:
                continue
            if (not _compatible(dois[a], dois[b]) or
                    not _compatible(pmids[a], pmids[b])):
                blocked.add(tuple(sorted((r["source_record_id"], q["source_record_id"]))))
                continue
            parent[b] = a
            members[a] |= members[b]
            dois[a] |= dois[b]
            pmids[a] |= pmids[b]
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, r in enumerate(kept):
        groups[root(i)].append(r)
    articles: list[dict[str, Any]] = []
    doi_to_article: dict[str, str] = {}
    for group in sorted(groups.values(), key=lambda xs: min(x["source_record_id"] for x in xs)):
        source_ids = sorted(x["source_record_id"] for x in group)
        doi_set = {x["doi"] for x in group if x.get("doi")}
        pmid_set = {str(x["pmid"]) for x in group if x.get("pmid")}
        token = ("doi:" + min(doi_set) if doi_set else
                 "pmid:" + min(pmid_set) if pmid_set else
                 "source:" + source_ids[0])
        article_id = "article:" + sha256(token.encode("utf-8"))[:24]
        article = {"canonical_article_id": article_id, "source_record_ids": source_ids,
                   "source_ids": sorted({x["source_id"] for x in group}),
                   "doi": min(doi_set) if doi_set else None,
                   "pmid": min(pmid_set) if pmid_set else None,
                   "identity_method": "exact_doi_or_pmid" if len(group) > 1 else "source_only"}
        articles.append(article)
        for d in doi_set:
            doi_to_article[d] = article_id
    links: list[dict[str, Any]] = []
    unresolved = 0
    for r in kept:
        for number, raw in enumerate(r.get("cited_references_raw") or [], 1):
            found = _DOI.search(raw)
            doi = normalize_doi(found.group() if found else None)
            target = doi_to_article.get(doi) if doi else None
            if not target:
                unresolved += 1
            links.append({"citing_source_record_id": r["source_record_id"],
                          "raw_reference_ordinal": number, "cited_article_id": target,
                          "external_target_doi": doi if not target else None,
                          "resolution_method": "exact_doi" if target else "unresolved",
                          "raw_evidence_pointer": {"export_sha256": r.get("raw_export_sha256"),
                                                  "record_ordinal": r.get("raw_record_ordinal"),
                                                  "reference_ordinal": number}})
    return {"schema": "stage2-source-view/v1", "omitted_sources": sorted(omitted),
            "source_counts": {s: sum(r["source_id"] == s for r in kept)
                              for s in sorted({r["source_id"] for r in kept})},
            "source_record_count": len(kept), "canonical_article_count": len(articles),
            "articles": articles, "citation_links": links,
            "unresolved_citation_count": unresolved,
            "blocked_identity_pairs": sorted(list(blocked)),
            "public_promotion": False}


def leave_one_source_out(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Deterministically recompute all source partitions without hand edits."""
    return {source: reconcile_sources(records, {source})
            for source in sorted({r["source_id"] for r in records})}


def canonical_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
