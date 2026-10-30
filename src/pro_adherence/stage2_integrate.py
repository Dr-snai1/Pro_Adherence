"""Offline one-shot Stage 2 integration. Restricted research data never enter Git.

The accepted V05 7z package must be restored with the pinned 7-Zip procedure.
This module consumes only the already-extracted 250 raw PubMed XML batches,
the original WoS tagged TXT + ZIP and the original APA PsycINFO RIS.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET
import gzip
import json
import re
import zipfile

from pro_adherence.stage2_sources import (
    SourceFormatError, canonical_json, normalize_doi, parse_wos_tagged_export,
    reconcile_sources,
)

WOS_TXT_SHA = "3247ec52dabe2ab3a156df6b57bfdd38b4e0496861458e70d0de0f5fe59ce020"
WOS_ZIP_SHA = "513e5837858801f72bc4063ca03cb482223b4b07a569276e1a1796cc1286d6bf"
APA_SHA = "dfc9d2902459f068b5492e79d73ab57694a04647a56c2a2d7abd95e59c19a462"
RIS_TAG = re.compile(r"^([A-Z0-9]{2})  - ?(.*)$")


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _first(fields: dict, key: str) -> str | None:
    v = fields.get(key) or []
    return v[0].strip() or None if v else None


def parse_apa_ris(raw: bytes) -> list[dict]:
    records, item, last = [], None, None
    raw_hash = digest(raw)
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise SourceFormatError("APA_ENCODING_INVALID") from exc
    for number, line in enumerate(lines, 1):
        match = RIS_TAG.match(line)
        if match:
            tag, value = match.groups()
            if tag == "TY":
                if item is not None:
                    raise SourceFormatError("APA_UNTERMINATED_RECORD")
                item = {"TY": [value]}
            else:
                if item is None:
                    raise SourceFormatError("APA_ORPHAN_TAG")
                item.setdefault(tag, []).append(value)
                if tag == "ER":
                    if item.get("DB") != ["APA PsycInfo"] or len(item.get("AN", [])) != 1:
                        raise SourceFormatError("APA_DATABASE_OR_AN_MISMATCH")
                    an = _first(item, "AN")
                    if not an:
                        raise SourceFormatError("APA_AN_MISSING")
                    doi_raw = _first(item, "DO")
                    doi = normalize_doi(doi_raw)
                    if doi_raw and not doi:
                        raise SourceFormatError("APA_INVALID_DOI")
                    tags = item.get("N1", [])
                    if any(k in item for k in ("CR", "C1", "RX", "RN", "RP")):
                        raise SourceFormatError("APA_REFERENCE_COVERAGE_CHANGED")
                    records.append({
                        "source_id": "apa_psycinfo", "source_native_id": an,
                        "source_record_id": "apa_psycinfo:" + an,
                        "pmid": None, "doi": doi, "title": _first(item, "TI"),
                        "abstract": _first(item, "AB"), "year": _first(item, "Y1"),
                        "venue": _first(item, "JO"), "authors_raw": item.get("AU", []),
                        "affiliations_raw": [], "cited_references_raw": [],
                        "reference_coverage": "not_exposed",
                        "retracted_article": "Retracted Article" in tags,
                        "peer_review_unknown": "Peer-Reviewed Status-Unknown" in tags,
                        "record_family": "journal", "scientific_article_only_eligible": True,
                        "raw_export_sha256": raw_hash, "raw_record_ordinal": len(records) + 1,
                        "access_class": "restricted-license", "publication_authorized": False,
                    })
                    item, last = None, None
                    continue
            last = tag
        elif line.strip():
            if item is None or last is None:
                raise SourceFormatError(f"APA_INVALID_CONTINUATION_{number}")
            item[last][-1] += "\n" + line
    if item is not None or not records:
        raise SourceFormatError("APA_INCOMPLETE_RIS")
    if len({r["source_native_id"] for r in records}) != len(records):
        raise SourceFormatError("APA_DUPLICATE_AN")
    return records


def parse_pubmed_batch(raw: bytes, filename: str) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise SourceFormatError("V05_INVALID_XML") from exc
    if root.tag != "PubmedArticleSet":
        raise SourceFormatError("V05_INVALID_ROOT")
    result = []
    raw_hash = digest(raw)
    for node in root:
        if node.tag not in ("PubmedArticle", "PubmedBookArticle"):
            raise SourceFormatError("V05_UNEXPECTED_FAMILY")
        family = "book" if node.tag == "PubmedBookArticle" else "journal"
        base = node.find("MedlineCitation") if family == "journal" else node.find("BookDocument")
        if base is None:
            raise SourceFormatError("V05_MISSING_SOURCE_BASE")
        pmid = base.findtext("PMID")
        if not pmid or not pmid.isdecimal():
            raise SourceFormatError("V05_MISSING_PMID")
        dois = {
            normalize_doi(x.text) for x in node.findall(".//ArticleIdList/ArticleId")
            if x.attrib.get("IdType") == "doi"
        } - {None}
        if len(dois) > 1:
            raise SourceFormatError("V05_MULTIPLE_DOI")
        title = base.find(".//ArticleTitle")
        if title is None:
            title = base.find(".//BookTitle")
        authors = base.findall(".//AuthorList/Author")
        references = []
        for ref in node.findall(".//ReferenceList/Reference"):
            cite = ref.findtext("Citation") or ""
            ref_dois = [x.text for x in ref.findall(".//ArticleId")
                        if x.attrib.get("IdType") == "doi" and x.text]
            references.append(cite + (" DOI " + ref_dois[0] if ref_dois else ""))
        result.append({
            "source_id": "pubmed", "source_native_id": pmid,
            "source_record_id": "pubmed:" + pmid, "pmid": pmid,
            "doi": next(iter(dois), None),
            "title": "".join(title.itertext()) if title is not None else None,
            "abstract": "\n".join("".join(a.itertext()) for a in base.findall(".//Abstract/AbstractText")) or None,
            "year": base.findtext(".//PubDate/Year"),
            "venue": base.findtext(".//Journal/Title"),
            "authors_raw": [
                " ".join(filter(None, [a.findtext("LastName"), a.findtext("ForeName")]))
                for a in authors
            ],
            "affiliations_raw": [
                x.text or "" for a in authors
                for x in a.findall(".//AffiliationInfo/Affiliation")
            ],
            "cited_references_raw": references,
            "reference_coverage": "exposed" if references else "unknown",
            "record_family": family, "scientific_article_only_eligible": family == "journal",
            "exclusion_reason": "book_family_not_journal_article" if family == "book" else None,
            "raw_export_sha256": raw_hash, "raw_filename": filename,
            "raw_record_ordinal": len(result) + 1,
            "access_class": "restricted", "publication_authorized": False,
        })
    return result


def load_sources(pubmed_dir: Path, wos_first: Path, wos_zip: Path, apa_ris: Path) -> list[dict]:
    files = sorted(pubmed_dir.glob("*.xml"))
    if [f.name for f in files] != [f"{i:06}.xml" for i in range(1, 251)]:
        raise SourceFormatError("V05_ACCEPTED_250_BATCHES_REQUIRED")
    records = []
    for file in files:
        records.extend(parse_pubmed_batch(file.read_bytes(), file.name))
    if (len(records), len({r["pmid"] for r in records})) != (49998, 49998):
        raise SourceFormatError("V05_ACCEPTED_PMID_COUNT_MISMATCH")
    if Counter(r["record_family"] for r in records) != Counter({"journal": 49912, "book": 86}):
        raise SourceFormatError("V05_ACCEPTED_FAMILY_MISMATCH")

    text = wos_first.read_bytes()
    zipped = wos_zip.read_bytes()
    apa = apa_ris.read_bytes()
    if (digest(text), digest(zipped), digest(apa)) != (WOS_TXT_SHA, WOS_ZIP_SHA, APA_SHA):
        raise SourceFormatError("FROZEN_SOURCE_SHA_MISMATCH")
    with zipfile.ZipFile(wos_zip) as z:
        names = sorted(n for n in z.namelist() if n.startswith("WOS_CORE_") and n.endswith(".txt"))
        if len(names) != 61 or z.testzip() is not None:
            raise SourceFormatError("WOS_ZIP_INTEGRITY_MISMATCH")
        inputs = [(wos_first.name, text)] + [(n, z.read(n)) for n in names]
    for name, payload in inputs:
        chunk = parse_wos_tagged_export(payload)["records"]
        for r in chunk:
            r["raw_filename"] = name
            r["record_family"] = "journal"
            r["scientific_article_only_eligible"] = True
            r["reference_coverage"] = "incomplete" if r["cited_references_count_anomaly"] else "exposed"
        records.extend(chunk)
    wos = [r for r in records if r["source_id"] == "woscc"]
    if (len(wos), len({r["source_native_id"] for r in wos}),
        sum(r["cited_references_count_anomaly"] for r in wos)) != (30635, 30635, 413):
        raise SourceFormatError("WOS_ACCEPTED_CENSUS_MISMATCH")
    apa_records = parse_apa_ris(apa)
    if len(apa_records) != 6878 or sum(r["retracted_article"] for r in apa_records) != 3:
        raise SourceFormatError("APA_ACCEPTED_CENSUS_MISMATCH")
    records.extend(apa_records)
    if len(records) != 87511:
        raise SourceFormatError("THREE_SOURCE_TOTAL_MISMATCH")
    return records


def save_private_candidate(records: list[dict], directory: Path) -> dict:
    """Only one three-source candidate; never creates a two-source canonical release."""
    if set(r["source_id"] for r in records) != {"pubmed", "woscc", "apa_psycinfo"}:
        raise SourceFormatError("THREE_SOURCES_REQUIRED")
    if directory.exists() and any(directory.iterdir()):
        raise SourceFormatError("OUTPUT_NOT_EMPTY")
    directory.mkdir(parents=True, exist_ok=True)
    views = {"three_source": reconcile_sources(records)}
    for source in ("pubmed", "woscc", "apa_psycinfo"):
        views["loo_" + source] = reconcile_sources(records, {source})
    artifacts = {}
    for name, view in views.items():
        if name == "three_source":
            view["source_records"] = records
            view["reference_coverage"] = dict(sorted(Counter(
                f'{r["source_id"]}:{r.get("reference_coverage", "unknown")}' for r in records
            ).items()))
            view["retracted_apa_source_ids"] = sorted(
                r["source_record_id"] for r in records if r.get("retracted_article"))
            view["author_observations"] = [
                {"source_record_id": r["source_record_id"], "ordinal": i, "original": val}
                for r in records for i, val in enumerate(r.get("authors_raw") or [], 1)
            ]
            view["affiliation_observations"] = [
                {"source_record_id": r["source_record_id"], "ordinal": i, "original": val}
                for r in records for i, val in enumerate(
                    r.get("affiliations_raw") or r.get("addresses_raw") or [], 1)
            ]
        payload = canonical_json(view)
        dest = directory / (name + ".json.gz")
        with dest.open("xb") as stream:
            with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressor:
                compressor.write(payload)
        artifacts[name] = {"file": dest.name, "sha256": digest(dest.read_bytes()),
                           "uncompressed_sha256": digest(payload), "bytes": dest.stat().st_size,
                           "source_count": view["source_record_count"],
                           "canonical_count": view["canonical_article_count"]}
    manifest = {
        "schema": "pro-adherence-stage2-private-candidate/v1",
        "acceptance": "PROVISIONAL_NO_STAGE_GATE",
        "source_counts": views["three_source"]["source_counts"],
        "source_record_count": 87511, "book_family_retained": 86,
        "wos_nr_cr_discrepancy_records": 413, "apa_retraction_flags": 3,
        "apa_reference_lists": "not_exposed_not_zero_citations",
        "artifacts": artifacts, "public_promotion": False,
    }
    (directory / "manifest.json").write_bytes(canonical_json(manifest))
    return manifest
