#!/usr/bin/env python3
"""Source-aware, NON-disambiguated observational co-author/co-word projections.

Research-only outputs. A matching author name is NOT a verified person identity.
WoS keywords_raw merges DE and ID upstream; this observational vocabulary must
NOT be interpreted as controlled subject indexing or an accepted co-word lens.
PubMed/APA missing keyword fields mean not-exposed, never zero occurrence.

Run only on the exact restricted immutable Stage2 archive and Stage3 graph.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from hashlib import sha256
from itertools import combinations
import gzip
import json
import os
from pathlib import Path
import sqlite3
import unicodedata
import zipfile

STAGE2_SHA = "a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127"
GRAPH_SHA = "33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c"
MEMBER_SHA = {
    "canonical_articles.jsonl.gz": "df9572a79db8063dc6b871cb0e03c6deae1fe4a4f1aaf1e06457932e048c311b",
    "source_records.jsonl.gz": "b68a3e71eff44276a42da754fd4c2eaff09c4886c3a0f356130dcb14981aafba",
    "author_observations.jsonl.gz": "68ef9997898c33a41eaf24a7f950290f0ceb199e7e922fee575f83517293d9f5",
}


def digest(path):
    h = sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


@contextmanager
def zipped_jsonl(z, member):
    with z.open(member) as f, gzip.GzipFile(fileobj=f) as reader:
        def rows():
            for raw in reader:
                if raw.strip():
                    yield json.loads(raw)
        yield rows()


def sha_member(z, member):
    h = sha256()
    with z.open(member) as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def nfc_label(raw):
    if not isinstance(raw, str):
        raise ValueError("Expected raw source string, not an inferred identity")
    return unicodedata.normalize("NFC", raw).strip()


def phrase_labels(values, *, split_semicolon):
    if not isinstance(values, list):
        raise ValueError("Expected raw source list")
    output = set()
    for entry in values:
        normalized = nfc_label(entry)
        for part in normalized.split(";") if split_semicolon else (normalized,):
            label = part.strip()
            if label:
                output.add(label)
    return sorted(output)


def node_id(source, label):
    return sha256((source + "\x00" + label).encode("utf-8")).hexdigest()


def init_db(connection):
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("CREATE TABLE labels(layer TEXT, source TEXT, node TEXT, value TEXT, "
                       "PRIMARY KEY(layer,source,node)) WITHOUT ROWID")
    connection.execute("CREATE TABLE edges(layer TEXT, source TEXT, left_node TEXT, "
                       "right_node TEXT, weight INTEGER NOT NULL, "
                       "PRIMARY KEY(layer,source,left_node,right_node)) WITHOUT ROWID")


def observe(connection, layer, source, labels):
    """One co-occurrence per pair per source article, no cross-source dedupe."""
    if len(labels) != len(set(labels)):
        raise ValueError("Duplicate normalized observation labels")
    nodes = sorted((node_id(source, label), label) for label in labels)
    for node, label in nodes:
        old = connection.execute(
            "SELECT value FROM labels WHERE layer=? AND source=? AND node=?",
            (layer, source, node),
        ).fetchone()
        if old is not None and old[0] != label:
            raise ValueError("SHA256 label collision")
        if old is None:
            connection.execute("INSERT INTO labels VALUES(?,?,?,?)",
                               (layer, source, node, label))
    for (a, _), (b, _) in combinations(nodes, 2):
        connection.execute(
            "INSERT INTO edges(layer,source,left_node,right_node,weight) VALUES(?,?,?,?,1) "
            "ON CONFLICT(layer,source,left_node,right_node) "
            "DO UPDATE SET weight=weight+1", (layer, source, a, b),
        )
    return len(nodes), len(nodes) * (len(nodes)-1) // 2


def process_source_records(connection, rows, source_to_article, eligible):
    seen = set()
    census = Counter()
    covered = Counter()
    incidences = Counter()
    source_presence = Counter()
    unknown_keywords = Counter()
    for row in rows:
        census["all_source_records"] += 1
        sid = row["source_record_id"]
        article = source_to_article.get(sid)
        if article is None:
            raise ValueError("Unmapped Stage2 source record")
        if article not in eligible:
            continue
        source = row["source_id"]
        if not source or not isinstance(source, str):
            raise ValueError("Missing source ID")
        key = (article, source)
        if key in seen:
            raise ValueError("Multiple source records from one source in canonical article")
        seen.add(key)
        census["eligible_source_records"] += 1
        source_presence[source] += 1
        authors = phrase_labels(row.get("authors_raw") or [], split_semicolon=False)
        if authors:
            covered[("authors", source)] += 1
        _, events = observe(connection, "author_names_not_persons", source, authors)
        incidences[("authors", source)] += events
        if "keywords_raw" not in row:
            unknown_keywords[source] += 1
        else:
            # WoS normalized keywords_raw is a concatenation of DE and ID;
            # no unobserved type distinction is reconstructed here.
            words = phrase_labels(row["keywords_raw"] or [], split_semicolon=True)
            if words:
                covered[("keywords", source)] += 1
            _, events = observe(connection, "raw_keyword_phrases", source, words)
            incidences[("keywords", source)] += events
    if census["all_source_records"] != 87511:
        raise ValueError("Full frozen Stage2 source census mismatch")
    return {
        "census": dict(census),
        "source_presence": dict(source_presence),
        "eligible_articles_per_source_with_content": {
            f"{kind}|{source}": n for (kind, source), n in covered.items()
        },
        "pair_incidences_source_observations": {
            f"{kind}|{source}": n for (kind, source), n in incidences.items()
        },
        "keywords_not_exposed_source_records": dict(unknown_keywords),
    }


def save_table(connection, sql, outfile):
    if outfile.exists():
        raise FileExistsError(outfile)
    count = weight_sum = 0
    with outfile.open("xb") as f:
        with gzip.GzipFile(filename="", fileobj=f, mode="wb", mtime=0, compresslevel=6) as writer:
            for row in connection.execute(sql):
                row = list(row)
                if len(row) == 5:
                    weight_sum += row[-1]
                writer.write((json.dumps(row, ensure_ascii=False, separators=(",", ":")) +
                              "\n").encode("utf-8"))
                count += 1
    return {"name": outfile.name, "rows": count, "weight_sum": weight_sum,
            "bytes": outfile.stat().st_size, "sha256": digest(outfile)}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--stage2-zip", required=True, type=Path)
    p.add_argument("--graph-zip", required=True, type=Path)
    p.add_argument("--private-output-dir", required=True, type=Path)
    p.add_argument("--explicit-private-research-run", action="store_true")
    a = p.parse_args(argv)
    if not a.explicit_private_research_run:
        p.error("Explicit private research authorization required")
    if digest(a.stage2_zip) != STAGE2_SHA or digest(a.graph_zip) != GRAPH_SHA:
        p.error("Frozen Stage2/graph SHA mismatch")
    if a.private_output_dir.exists() and any(a.private_output_dir.iterdir()):
        p.error("Do not overwrite existing results")
    a.private_output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(a.private_output_dir, 0o700)
    with zipfile.ZipFile(a.graph_zip) as graph:
        if graph.testzip() is not None:
            p.error("Graph CRC mismatch")
        with zipped_jsonl(graph, "node2vec_node_mapping.private.jsonl.gz") as rows:
            eligible = {row["article_id"] for row in rows}
    if len(eligible) != 57204:
        p.error("Eligible article count mismatch")
    with zipfile.ZipFile(a.stage2_zip) as stage2:
        if stage2.testzip() is not None:
            p.error("Stage2 CRC mismatch")
        for member, expected in MEMBER_SHA.items():
            if sha_member(stage2, member) != expected:
                p.error("Frozen Stage2 member hash mismatch: " + member)
        source_to_article = {}
        ids = set()
        with zipped_jsonl(stage2, "canonical_articles.jsonl.gz") as rows:
            for row in rows:
                article = row["canonical_article_id"]
                if article in ids:
                    raise ValueError("Duplicate canonical article")
                ids.add(article)
                for sid in row["source_record_ids"]:
                    if sid in source_to_article:
                        raise ValueError("Duplicate source record mapping")
                    source_to_article[sid] = article
        if len(ids) != 57293 or len(source_to_article) != 87511:
            p.error("Stage2 canonical/source mapping mismatch")
        if not eligible <= ids:
            p.error("Graph eligible article outside Stage2 canonical roster")
        db = a.private_output_dir / "observational.private.sqlite3"
        connection = sqlite3.connect(db)
        try:
            init_db(connection)
            with zipped_jsonl(stage2, "source_records.jsonl.gz") as rows:
                report = process_source_records(connection, rows, source_to_article, eligible)
            with zipped_jsonl(stage2, "author_observations.jsonl.gz") as rows:
                author_count = sum(1 for _ in rows)
            if author_count != 381211:
                p.error("Frozen author observation count mismatch")
            connection.commit()
            files = {}
            files["edges"] = save_table(
                connection,
                "SELECT layer,source,left_node,right_node,weight FROM edges ORDER BY 1,2,3,4",
                a.private_output_dir / "raw_observational_edges.private.jsonl.gz",
            )
            files["labels"] = save_table(
                connection,
                "SELECT layer,source,node,value FROM labels ORDER BY 1,2,3",
                a.private_output_dir / "raw_observational_labels.private.jsonl.gz",
            )
            report["unique_weighted_edges"] = {
                f"{layer}|{source}": {"pairs": n, "weight_sum": total}
                for layer, source, n, total in connection.execute(
                    "SELECT layer,source,COUNT(*),SUM(weight) FROM edges GROUP BY 1,2"
                )
            }
        finally:
            connection.close()
        # Do not keep large mutable SQLite as the accepted scientific asset.
        db.unlink()
    manifest = {
        "schema": "pro-adherence-stage3-classical-metadata-observations/v1",
        "status": "PROVISIONAL_RAW_LABEL_NETWORKS_NOT_DISAMBIGUATED_NOT_SCIENTIFICALLY_ACCEPTED",
        "stage2_zip_sha256": STAGE2_SHA, "graph_zip_sha256": GRAPH_SHA,
        "research_only": True, "publication_authorized": False,
        "input_member_sha256": MEMBER_SHA,
        "scope": "eligible canonical articles, per-source record-level co-occurrences",
        "author_node_semantics": "observed NFC-trimmed raw string within source, not a person",
        "term_node_semantics": "observed raw source keyword phrase; WoS DE+ID conflated upstream",
        "missing_keywords": "not_exposed is not interpreted as zero keywords",
        "no_cross_source_identity_union": True,
        "no_lemma_stem_stopword": True,
        "report": report, "outputs": files, "code_sha256": digest(__file__),
    }
    path = a.private_output_dir / "observational_metadata_manifest.private.json"
    with path.open("x", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps({"status": manifest["status"], "manifest_sha256": digest(path),
                      "files": files}, sort_keys=True))


if __name__ == "__main__":
    main()
