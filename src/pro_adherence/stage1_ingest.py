"""Offline, one-source Stage 1 PubMed XML to immutable research-only canonical snapshot.

No NCBI requests, no web-serving publication, no private evidence embedded in source.
Stage 0 IDs and corpus manifest schemas are reused unchanged. Input metadata is pinned.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

ADAPTER_VERSION = "pubmed-xml-stage1/0.1.0"
RESOLVER_VERSION = "pmid-hard-v0.1.0"
SCHEMA_VERSION = "pubmed-stage1-v0.1.0"
UUID_SEED = b"pro-adherence/stage1/deterministic-id/v1/"
REQUIRED_META = {"source_id", "retrieval_time", "query_definition", "source_cursor", "license_class", "access_class"}
CANON_COLUMNS = ["canonical_article_id", "pmid", "doi", "title_display", "title_match", "abstract_text", "publication_date", "document_type", "language", "access_license", "record_status", "created_in_resolution_version"]
SOURCE_COLUMNS = ["source_record_id", "source_id", "raw_artifact_id", "source_native_id", "original_metadata_payload_pointer", "parsed_fields", "retrieval_timestamp"]
EXTERNAL_COLUMNS = ["canonical_article_id", "namespace", "value_normalized", "source_record_id", "confidence", "valid_from"]


def _json_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _id(label):
    """Stable opaque UUIDv7-format ID, not a chronological sequence or a DOI/PMID encoding.

    The first 48 bits use a fixed v1 ID epoch; the remaining 74 random bits are
    SHA-256-derived. The algorithm is frozen here for reproducible rebuilds.
    """
    digest = hashlib.sha256(UUID_SEED + label.encode("utf-8")).digest()
    bs = bytearray(bytes.fromhex("0199dd431800") + digest[:10])
    bs[6] = (bs[6] & 0x0F) | 0x70
    bs[8] = (bs[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(bs)))


def _content(element):
    return "".join(element.itertext()).strip() if element is not None else None


def _doi(text):
    if text is None:
        return None
    value = text.strip().lower()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.I)
    if not value.startswith("10.") or "/" not in value or any(x.isspace() for x in value):
        raise ValueError("unsafe or malformed DOI in raw input")
    return value


def _pub_date(article):
    pub = article.find("./Journal/JournalIssue/PubDate")
    if pub is None:
        return None, None
    year = pub.findtext("Year")
    if not year:
        return None, None
    if not re.fullmatch(r"\d{4}", year) or not 1800 <= int(year) <= 2100:
        raise ValueError("invalid publication year")
    value, precision = year, "year"
    month, day = pub.findtext("Month"), pub.findtext("Day")
    if month:
        if month.isdigit():
            m = int(month)
        else:
            short = month[:3].lower()
            months = "jan feb mar apr may jun jul aug sep oct nov dec".split()
            m = months.index(short) + 1 if short in months else 0
        if m not in range(1, 13):
            raise ValueError("unrecognized publication month")
        value, precision = f"{year}-{m:02d}", "month"
        if day:
            import datetime
            datetime.date(int(year), m, int(day))
            value, precision = f"{value}-{int(day):02d}", "day"
    elif day:
        raise ValueError("publication day without month")
    return value, precision


def _parse(raw_bytes, raw_id, source_id, retrieval_time):
    """Validate source record identity and preserve original metadata pointers."""
    # NLM EFetch emits an external PUBLIC DTD. Accept its exact identity,
    # then remove the declaration from parser input only (no DTD fetch).
    # The archived raw XML bytes and source hash are never modified.
    if re.search(rb"<!ENTITY\b", raw_bytes, re.IGNORECASE):
        raise ValueError("DTD/entity declarations forbidden in raw XML")
    declaration = re.search(rb"<!DOCTYPE\b[^>]*>", raw_bytes, re.IGNORECASE)
    parse_bytes = raw_bytes
    if declaration:
        expected = re.fullmatch(
            rb'<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January (20[0-9]{2})//EN" "https://dtd\.nlm\.nih\.gov/ncbi/pubmed/out/pubmed_([0-9]{2})0101\.dtd">',
            declaration.group(0),
        )
        if expected is None or expected.group(1)[2:] != expected.group(2):
            raise ValueError("untrusted PubMed DTD declaration")
        parse_bytes = raw_bytes[:declaration.start()] + raw_bytes[declaration.end():]
    if re.search(rb"<!DOCTYPE\b", parse_bytes, re.IGNORECASE):
        raise ValueError("multiple or untrusted DTD declarations")
    raw_pointer = f"raw/{_sha(raw_bytes)}.xml"
    root = ET.fromstring(parse_bytes)
    if root.tag != "PubmedArticleSet":
        raise ValueError("expected PubmedArticleSet root")
    articles, sources, ext, seen, dois = [], [], [], {}, {}
    for index, entry in enumerate(root):
        if entry.tag != "PubmedArticle":
            raise ValueError("unexpected raw PubMed XML child")
        medline = entry.find("MedlineCitation")
        if medline is None:
            raise ValueError("missing MedlineCitation")
        pmid = medline.findtext("PMID")
        if not pmid or not re.fullmatch(r"[1-9][0-9]*", pmid):
            raise ValueError("PMID must be nonzero decimal")
        art = medline.find("Article")
        if art is None:
            raise ValueError("missing Article")
        title = _content(art.find("ArticleTitle"))
        if not title:
            raise ValueError("no title: fail closed rather than invent a record")
        abstract_el = art.find("Abstract")
        abstract_source = "Article/Abstract" if abstract_el is not None else None
        abstract_type = None
        if abstract_el is None:
            # A legacy citation may contain an English OtherAbstract only.
            # Foreign-language or ambiguous alternatives are not substituted.
            alternatives = [x for x in medline.findall("OtherAbstract")
                            if x.get("Language", "").lower() in ("eng", "en")]
            if len(alternatives) > 1:
                raise ValueError("ambiguous English OtherAbstract sources")
            if alternatives:
                abstract_el = alternatives[0]
                abstract_source = "MedlineCitation/OtherAbstract"
                abstract_type = abstract_el.get("Type")
        abstract_parts = ([_content(node) for node in abstract_el.findall("AbstractText")]
                          if abstract_el is not None else [])
        abstract = "\n".join(part for part in abstract_parts if part) or None
        doi_texts = []
        for v in entry.findall("./PubmedData/ArticleIdList/ArticleId[@IdType='doi']"):
            if _content(v):
                doi_texts.append(_content(v))
        for v in art.findall("./ELocationID[@EIdType='doi']"):
            if _content(v):
                doi_texts.append(_content(v))
        normalized_dois = {_doi(d) for d in doi_texts}
        if len(normalized_dois) > 1:
            raise ValueError("conflicting DOI assertions within one source record")
        doi = next(iter(normalized_dois)) if normalized_dois else None
        pub_date, precision = _pub_date(art)
        doc_type = _content(art.find("./PublicationTypeList/PublicationType"))
        language = _content(art.find("Language"))
        record = {"canonical_article_id": _id("article/pmid/"+pmid), "pmid": pmid,
                  "doi": doi, "title_display": title, "title_match": " ".join(title.casefold().split()),
                  "abstract_text": abstract,
                  "publication_date": {"value": pub_date, "precision": precision} if pub_date else None,
                  "document_type": doc_type, "language": language, "access_license": None,
                  "record_status": "active", "created_in_resolution_version": RESOLVER_VERSION}
        cmp = {k: v for k, v in record.items() if k != "access_license"}
        if pmid in seen:
            previous, n = seen[pmid]
            if previous != cmp:
                raise ValueError("same PMID has conflicting content: no silent merge")
            sources[n]["parsed_fields"]["duplicate_occurrences"] += 1
            continue
        if doi:
            if doi in dois and dois[doi] != pmid:
                raise ValueError("DOI shared by distinct PMIDs: needs independent resolver decision")
            dois[doi] = pmid
        source_id_value = _id("source/"+source_id+"/"+raw_id+"/"+pmid)
        source = {"source_record_id": source_id_value, "source_id": source_id,
                  "raw_artifact_id": raw_id, "source_native_id": pmid,
                  "original_metadata_payload_pointer": f"{raw_pointer}#PubmedArticle={index}",
                  "retrieval_timestamp": retrieval_time,
                  "parsed_fields": {"title_original": title, "doi_original": doi_texts[0] if doi_texts else None,
                                    "duplicate_occurrences": 1, "abstract_source": abstract_source,
                                    "other_abstract_type": abstract_type}}
        seen[pmid] = (cmp, len(sources))
        articles.append(record)
        sources.append(source)
        for namespace, value in (("pmid", pmid), ("doi", doi)):
            if value:
                ext.append({"canonical_article_id": record["canonical_article_id"],
                            "namespace": namespace, "value_normalized": value,
                            "source_record_id": source_id_value, "confidence": 1.0,
                            "valid_from": RESOLVER_VERSION})
    if not articles:
        raise ValueError("empty PubMed input not accepted as a canonical research snapshot")
    articles.sort(key=lambda r: int(r["pmid"]))
    sources.sort(key=lambda r: int(r["source_native_id"]))
    ext.sort(key=lambda r: (r["canonical_article_id"], r["namespace"], r["value_normalized"]))
    return articles, sources, ext, len(root)


def _validate_meta(meta):
    if not isinstance(meta, dict) or set(meta) != REQUIRED_META:
        raise ValueError("input metadata keys not pinned")
    if meta["source_id"] != "pubmed":
        raise ValueError("Stage 1 adapter is PubMed-only")
    from datetime import datetime
    try:
        timestamp = datetime.fromisoformat(meta["retrieval_time"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
            raise ValueError()
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("retrieval_time must be an explicit UTC ISO-8601 timestamp") from exc
    if meta["access_class"] not in ("project-internal", "restricted-license"):
        raise ValueError("Stage 1 raw cannot be public or secret input")
    for k in ("query_definition", "source_cursor", "license_class"):
        if not isinstance(meta[k], str) or not meta[k].strip():
            raise ValueError("missing required source metadata: "+k)
    if not isinstance(meta["retrieval_time"], str) or not meta["retrieval_time"].endswith("Z"):
        raise ValueError("retrieval_time must use canonical Z suffix")


def _arrow_tables(articles, sources, external, access, license_name, destination):
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Stage 1 requires pinned pyarrow==26.0.0 (requirements-stage1.lock)") from exc
    for record in articles:
        record["access_license"] = {"access_class": access, "license_class": license_name,
                                    "license_status": "unknown", "publication_permissions": {
                                        "metadata": "deny", "raw_text": "deny", "derived": "deny"}}
    for filename, records, names in (("articles.parquet", articles, CANON_COLUMNS),
                                     ("source_records.parquet", sources, SOURCE_COLUMNS),
                                     ("external_ids.parquet", external, EXTERNAL_COLUMNS)):
        columns = {name: [record.get(name) for record in records] for name in names}
        pq.write_table(pa.table(columns), destination / filename, compression="NONE",
                       use_dictionary=False, write_statistics=False, version="2.6")
        if pq.read_table(destination / filename).num_rows != len(records):
            raise ValueError("Parquet roundtrip count mismatch")


def _sqlite(articles, sources, external, dest):
    con = sqlite3.connect(dest / "working.sqlite")
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("CREATE TABLE articles(canonical_article_id TEXT PRIMARY KEY, pmid TEXT NOT NULL UNIQUE, doi TEXT UNIQUE, title_display TEXT NOT NULL, abstract_text TEXT)")
        con.execute("CREATE TABLE source_records(source_record_id TEXT PRIMARY KEY, canonical_article_id TEXT NOT NULL REFERENCES articles(canonical_article_id), pmid TEXT UNIQUE NOT NULL, raw_artifact_id TEXT NOT NULL)")
        con.execute("CREATE TABLE external_ids(canonical_article_id TEXT NOT NULL REFERENCES articles(canonical_article_id), namespace TEXT NOT NULL, value_normalized TEXT NOT NULL, PRIMARY KEY(namespace,value_normalized))")
        by_pmid = {r["pmid"]: r for r in articles}
        con.executemany("INSERT INTO articles VALUES (?,?,?,?,?)", [(r["canonical_article_id"], r["pmid"], r["doi"], r["title_display"], r["abstract_text"]) for r in articles])
        con.executemany("INSERT INTO source_records VALUES (?,?,?,?)", [(r["source_record_id"], by_pmid[r["source_native_id"]]["canonical_article_id"], r["source_native_id"], r["raw_artifact_id"]) for r in sources])
        con.executemany("INSERT INTO external_ids VALUES (?,?,?)", [(r["canonical_article_id"], r["namespace"], r["value_normalized"]) for r in external])
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("invalid reference in working SQLite")
        con.commit()
    finally:
        con.close()


def build(raw_xml: Path, metadata_json: Path, workspace: Path):
    """Build research-only snapshot atomically; never replace an existing snapshot."""
    raw_xml, metadata_json, workspace = Path(raw_xml), Path(metadata_json), Path(workspace)
    if workspace.is_symlink():
        raise ValueError("workspace must not be a symlink")
    repo_root = Path(__file__).resolve().parents[2]
    if workspace.resolve().is_relative_to(repo_root.resolve()):
        raise ValueError("research workspace must be outside public Git repository")
    meta = json.loads(metadata_json.read_text(encoding="utf-8"))
    _validate_meta(meta)
    raw = raw_xml.read_bytes()
    raw_hash = _sha(raw)
    raw_id = _id("raw/"+raw_hash)
    articles, sources, ext, raw_positions = _parse(raw, raw_id, meta["source_id"], meta["retrieval_time"])
    import pyarrow
    if pyarrow.__version__ != "26.0.0":
        raise RuntimeError("unlocked pyarrow version")
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    if workspace.is_symlink():
        raise ValueError("workspace must not be a symlink")
    raw_dir = workspace / "raw"
    raw_dir.mkdir(exist_ok=True, mode=0o700)
    if raw_dir.is_symlink():
        raise ValueError("raw directory must not be a symlink")
    raw_dest = raw_dir / f"{raw_hash}.xml"
    if raw_dest.is_symlink():
        raise ValueError("raw path must not be a symlink")
    if raw_dest.exists():
        if _sha(raw_dest.read_bytes()) != raw_hash:
            raise ValueError("immutable raw content hash drift")
    else:
        with raw_dest.open("xb") as fp:
            fp.write(raw)
    metadata_hash = _sha(_json_bytes(meta))
    snapshot_id = _id("snapshot/"+raw_hash+"/"+metadata_hash+"/"+ADAPTER_VERSION+"/"+RESOLVER_VERSION)
    snapshot_base = workspace / "snapshots"
    snapshot_base.mkdir(exist_ok=True, mode=0o700)
    if snapshot_base.is_symlink():
        raise ValueError("snapshot directory must not be a symlink")
    target = snapshot_base / snapshot_id
    if target.is_symlink():
        raise ValueError("snapshot path must not be a symlink")
    if target.exists():
        if not target.is_dir():
            raise ValueError("existing snapshot not a directory")
        verify_snapshot(target, raw_dest, raw_hash, meta, snapshot_id)
        return target
    staging = Path(tempfile.mkdtemp(prefix=".stage1-", dir=snapshot_base))
    try:
        _arrow_tables(articles, sources, ext, meta["access_class"], meta["license_class"], staging)
        _sqlite(articles, sources, ext, staging)
        generated = {}
        for filename in ("articles.parquet", "source_records.parquet", "external_ids.parquet", "working.sqlite"):
            generated[filename] = _sha((staging / filename).read_bytes())
        source_info = {**meta, "adapter_version": ADAPTER_VERSION,
                       "raw_artifact_id": raw_id, "raw_artifact_uri": f"raw/{raw_hash}.xml",
                       "raw_byte_hash": raw_hash, "raw_bytes": len(raw),
                       "metadata_hash": metadata_hash,
                       "completeness_flags": {"raw_xml_parsed": True, "article_ids_present": True,
                                              "title_present": True, "abstracts_complete": all(r["abstract_text"] is not None for r in articles)},
                       "license_status": "unknown", "publication_permissions": {"metadata": "deny", "raw_text": "deny", "derived": "deny"}}
        (staging / "source_provenance.json").write_bytes(_json_bytes(source_info)+b"\n")
        policy = {"mode": "include_all_valid_pubmed_source_records", "version": "v0.1.0"}
        exclude = {"mode": "fail_closed_conflicting_pmid_or_doi", "version": "v0.1.0"}
        manifest = {"manifest_version": "1.0.0", "corpus_release_id": snapshot_id,
                    "status": "draft", "canonical_schema_version": SCHEMA_VERSION,
                    "entity_resolution_version": RESOLVER_VERSION,
                    "inclusion_policy": {"uri": "policy:stage1/include-v0.1.0", "content_hash": _sha(_json_bytes(policy))},
                    "exclusion_policy": {"uri": "policy:stage1/exclude-v0.1.0", "content_hash": _sha(_json_bytes(exclude))},
                    "input_artifacts": [{"artifact_id": raw_id, "content_hash": raw_hash}],
                    "canonical_article_ids": sorted(r["canonical_article_id"] for r in articles),
                    "article_count": len(articles), "created_at": meta["retrieval_time"]}
        manifest["manifest_hash"] = _sha(_json_bytes(manifest))
        (staging / "corpus_manifest.json").write_bytes(_json_bytes(manifest)+b"\n")
        quality = {"scope": "stage1-pubmed-one-source", "sample_source": "offline XML, no network",
                   "raw_positions": raw_positions, "unique_pmids": len(articles),
                   "duplicate_pmid_positions": raw_positions-len(articles),
                   "missing_titles": sum(not r["title_display"] for r in articles),
                   "missing_abstracts": sum(r["abstract_text"] is None for r in articles),
                   "distinct_dois": len(set(r["doi"] for r in articles if r["doi"])),
                   "unresolved_identifier_conflicts": 0,
                   "license_access": "project-internal or restricted; NO public promotion",
                   "checks": {"source_schema": "pass", "strict_pmid": "pass",
                              "doi_collision": "pass", "parquet_roundtrip": "pass",
                              "sqlite_fk": "pass", "immutable_raw": "pass"},
                   "status": "diagnostic-only"}
        (staging / "qa_report.json").write_bytes(_json_bytes(quality)+b"\n")
        generated.update({name: _sha((staging / name).read_bytes()) for name in ("source_provenance.json", "corpus_manifest.json", "qa_report.json")})
        (staging / "checksums.json").write_bytes(_json_bytes(generated)+b"\n")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    verify_snapshot(target, raw_dest, raw_hash, meta, snapshot_id)
    return target


def verify_snapshot(target, raw_dest, raw_hash, meta, snapshot_id):
    if target.is_symlink() or raw_dest.is_symlink():
        raise ValueError("immutable paths cannot be symlinks")
    if _sha(raw_dest.read_bytes()) != raw_hash:
        raise ValueError("raw input changed after archive")
    checks = json.loads((target / "checksums.json").read_text(encoding="utf-8"))
    expected = {"articles.parquet", "source_records.parquet", "external_ids.parquet", "working.sqlite",
                "source_provenance.json", "corpus_manifest.json", "qa_report.json"}
    if set(checks) != expected or {f.name for f in target.iterdir()} != expected | {"checksums.json"}:
        raise ValueError("snapshot inventory drift")
    for name, expected_hash in checks.items():
        file = target / name
        if file.is_symlink() or _sha(file.read_bytes()) != expected_hash:
            raise ValueError("snapshot artifact mutated: "+name)
    provenance = json.loads((target / "source_provenance.json").read_text(encoding="utf-8"))
    if provenance["raw_byte_hash"] != raw_hash or provenance["metadata_hash"] != _sha(_json_bytes(meta)):
        raise ValueError("source lineage mismatch")
    manifest = json.loads((target / "corpus_manifest.json").read_text(encoding="utf-8"))
    if manifest["corpus_release_id"] != snapshot_id or manifest["status"] != "draft":
        raise ValueError("unexpected release/serving state")
    stored_hash = manifest.pop("manifest_hash")
    if _sha(_json_bytes(manifest)) != stored_hash:
        raise ValueError("manifest hash mismatch")
    report = json.loads((target / "qa_report.json").read_text(encoding="utf-8"))
    if report["unique_pmids"] != manifest["article_count"] or len(set(manifest["canonical_article_ids"])) != manifest["article_count"]:
        raise ValueError("canonical snapshot count mismatch")
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline research-only Stage 1 PubMed XML ingestion")
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args(argv)
    output = build(args.raw, args.metadata, args.workspace)
    print(json.dumps({"snapshot_path": str(output), "verified": True, "public_promotion": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
