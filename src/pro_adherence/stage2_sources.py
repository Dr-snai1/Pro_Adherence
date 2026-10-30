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
    declared_refs = _single(tags, "NR")
    if declared_refs is None or not declared_refs.isdecimal():
        raise SourceFormatError("MISSING_OR_INVALID_WOS_NR")
    exported_refs = len(_values(tags, "CR"))
    declared_count = int(declared_refs)
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
        "cited_references_declared": declared_count,
        "cited_references_exported": exported_refs,
        "cited_references_count_anomaly": declared_count != exported_refs,
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
            if last_tag == "CR":
                # WoS encodes each cited reference as a separate indented CR line,
                # whereas other indented fields continue their preceding value.
                tags[last_tag].append(line.strip())
            else:
                tags[last_tag][-1] += " " + line.strip()
        elif line.strip():
            raise SourceFormatError("UNKNOWN_EXPORT_LINE")
    if tags is not None or not finished:
        raise SourceFormatError("EXPORT_NOT_COMPLETE")
    if not result:
        raise SourceFormatError("NO_RECORDS")
    return {"schema": "stage2-wos-tagged-export/v1", "source_id": _SOURCE,
            "raw_export_sha256": digest, "records": result,
            "record_count": len(result),
            "nr_anomaly_count": sum(r["cited_references_count_anomaly"] for r in result),
            "access_class": "restricted-license",
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
    families_by_component = [{r["record_family"]} if r.get("record_family") else set() for r in kept]
    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i
    # Indexed candidate buckets replace the O(N^2) all-pairs walk.
    # A key with contradictory identifiers must not merge an arbitrary subset
    # based on input ordering; veto the whole bucket deterministically.
    index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, r in enumerate(kept):
        if r.get("doi"):
            index[("doi", r["doi"])].append(i)
        if r.get("pmid"):
            index[("pmid", str(r["pmid"]))].append(i)
    blocked: set[tuple[str, str]] = set()
    decisions: list[dict[str, Any]] = []
    source_members = [{r["source_id"]} for r in kept]
    for (kind, value), indices in sorted(index.items()):
        if len(indices) < 2:
            continue
        key_dois = {kept[i]["doi"] for i in indices if kept[i].get("doi")}
        key_pmids = {str(kept[i]["pmid"]) for i in indices if kept[i].get("pmid")}
        source_ids = [kept[i]["source_id"] for i in indices]
        families = {kept[i].get("record_family") for i in indices if kept[i].get("record_family")}
        if len(key_dois) > 1 or len(key_pmids) > 1 or len(set(source_ids)) < len(source_ids) or len(families) > 1:
            decisions.append({"key_kind": kind, "key_value": value,
                              "action": "ambiguous_key",
                              "source_record_ids": sorted(keys[i] for i in indices)})
            for a in indices:
                for b in indices:
                    if a < b:
                        blocked.add(tuple(sorted((keys[a], keys[b]))))
            continue
        for i in indices[1:]:
            a, b = root(indices[0]), root(i)
            if a == b:
                continue
            if (not _compatible(dois[a], dois[b]) or
                    not _compatible(pmids[a], pmids[b]) or
                    not _compatible(families_by_component[a], families_by_component[b]) or
                    source_members[a] & source_members[b]):
                blocked.add(tuple(sorted((keys[indices[0]], keys[i]))))
                decisions.append({"key_kind": kind, "key_value": value,
                                  "action": "blocked_component_conflict",
                                  "source_record_ids": sorted((keys[indices[0]], keys[i]))})
                continue
            parent[b] = a
            members[a] |= members[b]
            dois[a] |= dois[b]
            pmids[a] |= pmids[b]
            families_by_component[a] |= families_by_component[b]
            source_members[a] |= source_members[b]
            decisions.append({"key_kind": kind, "key_value": value,
                              "action": "merge_exact_identifier",
                              "source_record_ids": sorted((keys[indices[0]], keys[i]))})
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, r in enumerate(kept):
        groups[root(i)].append(r)
    # Exact identifiers can be contradictory across disconnected components.
    # An ambiguous DOI/PMID must neither give two articles the same canonical ID
    # nor silently resolve a citation to whichever component was iterated last.
    components = sorted(groups.values(), key=lambda xs: min(x["source_record_id"] for x in xs))
    doi_owners: dict[str, int] = defaultdict(int)
    pmid_owners: dict[str, int] = defaultdict(int)
    for group in components:
        for d in {x["doi"] for x in group if x.get("doi")}:
            doi_owners[d] += 1
        for p in {str(x["pmid"]) for x in group if x.get("pmid")}:
            pmid_owners[p] += 1
    articles: list[dict[str, Any]] = []
    # Preserve every DOI owner, including intentionally unresolved conflicts.
    # A DOI that labels multiple canonical groups is an ambiguous citation,
    # never an ordinary unresolved reference and never an arbitrary target.
    doi_to_articles: dict[str, list[str]] = defaultdict(list)
    for group in components:
        source_ids = sorted(x["source_record_id"] for x in group)
        doi_set = {x["doi"] for x in group if x.get("doi")}
        pmid_set = {str(x["pmid"]) for x in group if x.get("pmid")}
        unique_dois = sorted(d for d in doi_set if doi_owners[d] == 1)
        unique_pmids = sorted(p for p in pmid_set if pmid_owners[p] == 1)
        token = ("doi:" + unique_dois[0] if unique_dois else
                 "pmid:" + unique_pmids[0] if unique_pmids else
                 "source:" + source_ids[0])
        article_id = "article:" + sha256(token.encode("utf-8"))[:24]
        article = {"canonical_article_id": article_id, "source_record_ids": source_ids,
                   "source_ids": sorted({x["source_id"] for x in group}),
                   "doi": min(doi_set) if doi_set else None,
                   "pmid": min(pmid_set) if pmid_set else None,
                   "ambiguous_doi": bool(doi_set and not unique_dois),
                   "identity_method": "exact_doi_or_pmid" if len(group) > 1 else "source_only"}
        articles.append(article)
        for d in sorted(doi_set):
            doi_to_articles[d].append(article_id)
    links: list[dict[str, Any]] = []
    unresolved = ambiguous = 0
    for r in kept:
        for number, raw in enumerate(r.get("cited_references_raw") or [], 1):
            found = _DOI.search(raw)
            doi = normalize_doi(found.group() if found else None)
            candidates = doi_to_articles.get(doi, []) if doi else []
            target = candidates[0] if len(candidates) == 1 else None
            status = ("exact_doi" if len(candidates) == 1 else
                      "ambiguous_doi" if len(candidates) > 1 else "unresolved")
            unresolved += status == "unresolved"
            ambiguous += status == "ambiguous_doi"
            links.append({"citing_source_record_id": r["source_record_id"],
                          "raw_reference_ordinal": number, "cited_article_id": target,
                          "external_target_doi": doi if not target else None,
                          "resolution_method": status,
                          "raw_evidence_pointer": {"export_sha256": r.get("raw_export_sha256"),
                                                  "record_ordinal": r.get("raw_record_ordinal"),
                                                  "reference_ordinal": number}})
    return {"schema": "stage2-source-view/v1", "omitted_sources": sorted(omitted),
            "source_counts": {s: sum(r["source_id"] == s for r in kept)
                              for s in sorted({r["source_id"] for r in kept})},
            "source_record_count": len(kept), "canonical_article_count": len(articles),
            "articles": articles, "citation_links": links,
            "unresolved_citation_count": unresolved,
            "ambiguous_citation_count": ambiguous,
            "blocked_identity_pairs": sorted(list(blocked)),
            "identity_decisions": decisions,
            "public_promotion": False}



def resolution_version_delta(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Explicit merge/split aliases between two pinned resolution versions.

    Comparison is scoped to source records in BOTH versions. For the first
    three-source candidate, no predecessor exists: do not invent splits.
    """
    old = {sid: art["canonical_article_id"]
           for art in previous["articles"] for sid in art["source_record_ids"]}
    new = {sid: art["canonical_article_id"]
           for art in current["articles"] for sid in art["source_record_ids"]}
    shared = sorted(set(old) & set(new))
    successors: dict[str, set[str]] = defaultdict(set)
    predecessors: dict[str, set[str]] = defaultdict(set)
    for sid in shared:
        successors[old[sid]].add(new[sid])
        predecessors[new[sid]].add(old[sid])
    return {
        "schema": "stage2-identity-version-delta/v1",
        "shared_source_record_count": len(shared),
        "splits": sorted(({"previous_id": old_id, "successor_ids": sorted(targets)}
                          for old_id, targets in successors.items() if len(targets) > 1),
                         key=lambda x: x["previous_id"]),
        "merges": sorted(({"current_id": new_id, "predecessor_ids": sorted(origins)}
                          for new_id, origins in predecessors.items() if len(origins) > 1),
                         key=lambda x: x["current_id"]),
    }


def leave_one_source_out(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Deterministically recompute all source partitions without hand edits."""
    return {source: reconcile_sources(records, {source})
            for source in sorted({r["source_id"] for r in records})}


def canonical_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
