"""Scoped NCBI/PubMed retrieval and internal-only durable evidence, contract v1.

Only Python stdlib. Raw responses precede parsing; this module never writes to serving.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib import parse, request, error
from xml.etree import ElementTree

ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
SCHEMA = "pubmed-evidence/v1"
PARTITION_POLICY = "pubdate-bisect/v1"
MAX_PACKAGE = 50 * 1024 * 1024
MAX_REPOSITORY = 1024 * 1024 * 1024
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
PMID_RE = re.compile(r"[1-9][0-9]*\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def safe_id(value):
    if not isinstance(value, str) or not ID_RE.fullmatch(value) or value in (".", ".."):
        raise ValueError("unsafe identifier")
    return value


def strict_path(base, name):
    root = Path(base).resolve()
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("unsafe or symlink path")
    return path


def read_spec(path, *, mode, code_commit, runtime):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"schema", "task_id", "query_artifact", "queries", "operation", "partition_policy", "date_start", "date_end", "ncbi_config_refs"}
    if not isinstance(value, dict) or not required.issubset(value) or set(value) - required - {"sample_policy"} or value["schema"] != "pubmed-run-spec/v1":
        raise ValueError("run spec schema/keys mismatch")
    safe_id(value["task_id"])
    safe_id(value["query_artifact"])
    if value["operation"] != "esearch-pmids" or value["partition_policy"] != PARTITION_POLICY:
        raise ValueError("unsupported operation or policy")
    if not isinstance(value["queries"], dict) or not value["queries"]:
        raise ValueError("queries required")
    for key, term in value["queries"].items():
        safe_id(key)
        if not isinstance(term, str) or not term.strip() or len(term) > 100000:
            raise ValueError("invalid query")
    a, b = dt.date.fromisoformat(value["date_start"]), dt.date.fromisoformat(value["date_end"])
    if a > b or a.year < 1800 or b.year > 2100:
        raise ValueError("unsafe date range")
    if value["ncbi_config_refs"] != ["NCBI_TOOL", "NCBI_EMAIL", "NCBI_API_KEY(optional)"]:
        raise ValueError("invalid non-secret config refs")
    policy = value.get("sample_policy", {})
    if not isinstance(policy, dict) or set(policy) - set(value["queries"]):
        raise ValueError("sample policy must reference declared queries")
    for qid, rule in policy.items():
        if not isinstance(rule, dict) or set(rule) != {"size", "sha256_prefix"}:
            raise ValueError("invalid sample rule")
        if not isinstance(rule["size"], int) or not 1 <= rule["size"] <= 100:
            raise ValueError("unsafe sample size")
        if not isinstance(rule["sha256_prefix"], str) or not rule["sha256_prefix"] or len(rule["sha256_prefix"]) > 256:
            raise ValueError("invalid sample prefix")
    if mode == "smoke" and policy:
        raise ValueError("smoke must not retrieve scientific samples")
    if mode not in ("smoke", "full"):
        raise ValueError("unsupported mode")
    if mode == "smoke" and (len(value["queries"]) != 1 or any(len(q) > 200 for q in value["queries"].values())):
        raise ValueError("smoke must use a small neutral query")
    if mode == "full" and value["query_artifact"].startswith("infra-smoke"):
        raise ValueError("smoke-only input cannot be used as scientific run")
    if not re.fullmatch(r"[a-f0-9]{40}", code_commit):
        raise ValueError("code commit must be pinned SHA")
    identity = {"spec": value, "mode": mode, "code_commit": code_commit, "runtime": runtime, "attempt": "1"}
    return value, "r-" + sha(canonical(identity))[:32]


def numeric_pmids(ids):
    if not isinstance(ids, list) or any(not isinstance(x, str) or not PMID_RE.fullmatch(x) for x in ids):
        raise ValueError("invalid PMID")
    return sorted(set(ids), key=int)


class Client:
    def __init__(self, tool, email, api_key="", opener=None, sleep=time.sleep, clock=time.monotonic):
        if not tool or " " in tool or not email or "@" not in email or " " in email:
            raise ValueError("NCBI_TOOL/NCBI_EMAIL required")
        self.tool, self.email, self._key = tool, email, api_key
        self.opener, self.sleep, self.clock = opener or request.urlopen, sleep, clock
        self.last_request = None

    def efetch(self, pmids):
        if not pmids or len(pmids) > 100 or numeric_pmids(pmids) != pmids:
            raise ValueError("EFetch requires <=100 canonical PMIDs")
        return self._post(EFETCH_ENDPOINT, {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}, len(pmids))

    def esearch(self, term, retmax):
        # Always POST: protects long-query correctness and avoids leaking API keys in URLs.
        return self._post(ENDPOINT, {"db":"pubmed", "term":term, "retmode":"json", "retmax":str(retmax)}, retmax)

    def _post(self, endpoint, parameters, retmax):
        form = {**parameters, "tool": self.tool, "email": self.email}
        if self._key:
            form["api_key"] = self._key
        data = parse.urlencode(form).encode("utf-8")
        for attempt in range(5):
            if not self._key and self.last_request is not None:
                self.sleep(max(0, 0.36 - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            req = request.Request(endpoint, data=data, method="POST",
                                  headers={"User-Agent": self.tool, "Content-Type": "application/x-www-form-urlencoded"})
            try:
                with self.opener(req, timeout=35) as response:
                    raw = response.read()
                return raw, {"endpoint": endpoint, "method": "POST", "utc": utc_now(), "retmax": retmax}
            except error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                    raise RuntimeError(f"NCBI HTTP failure: {exc.code}") from None
            except (error.URLError, TimeoutError, OSError):
                if attempt == 4:
                    raise RuntimeError("NCBI transient request failure") from None
            self.sleep(min(8, 2 ** attempt))
        raise AssertionError("unreachable")


def parse_result(raw):
    parsed = json.loads(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("esearchresult"), dict):
        raise ValueError("invalid NCBI response")
    obj = parsed["esearchresult"]
    if "error" in obj or obj.get("errorlist", {}).get("phrasesnotfound"):
        # Search errors are scientifically material; raw was already stored.
        raise ValueError("NCBI search error; inspect saved raw evidence")
    count = int(obj["count"])
    if count < 0 or count > 1000000000:
        raise ValueError("invalid NCBI count")
    ids = obj.get("idlist", [])
    numeric_pmids(ids)
    return {"count": count, "ids": ids, "querytranslation": obj.get("querytranslation"),
            "warninglist": obj.get("warninglist"), "errorlist": obj.get("errorlist")}


def date_query(base, start, end):
    return f'({base}) AND ("{start:%Y/%m/%d}"[dp] : "{end:%Y/%m/%d}"[dp])'


def plan_spans(start, end):
    """Unambiguous, nonoverlapping inclusive bisection with deterministic bounds."""
    middle = start + dt.timedelta(days=(end - start).days // 2)
    return (start, middle), (middle + dt.timedelta(days=1), end)


def write_raw(directory, relative, raw):
    path = strict_path(directory, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("raw evidence is immutable")
    path.write_bytes(raw)


def collect_sample(spec, root, qid, union, client, calls):
    """Finish an optional deterministic sample, including after a partial EFetch failure."""
    rule = spec.get("sample_policy", {}).get(qid)
    if rule is None:
        return
    chosen = numeric_pmids(sorted(union, key=lambda pmid: sha((rule["sha256_prefix"] + pmid).encode()))[:rule["size"]])
    rel = f"raw/{qid}-sample.xml"
    sample_path = f"samples/{qid}.pmids.txt"
    if not chosen:
        # A zero-result branch has no PubMed citation to fetch or classify.
        if not strict_path(root, sample_path).exists():
            write_raw(root, sample_path, b"")
        return
    if strict_path(root, rel).exists():
        raw = strict_path(root, rel).read_bytes()  # manifest verified before resume
    else:
        raw, meta = client.efetch(chosen)
        write_raw(root, rel, raw)
        calls.append({"query_id": qid, "query_sha256": sha(canonical(chosen)), "file": rel, **meta})
    try:
        xroot = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        raise ValueError("malformed PubMed EFetch XML") from None
    if xroot.tag != "PubmedArticleSet":
        raise ValueError("unexpected PubMed EFetch XML")
    found = [el.text for el in xroot.findall("./PubmedArticle/MedlineCitation/PMID")]
    if numeric_pmids(found) != chosen or len(found) != len(chosen):
        raise ValueError("EFetch PMID identity mismatch")
    sample_bytes = ("\n".join(chosen) + "\n").encode()
    if strict_path(root, sample_path).exists():
        if strict_path(root, sample_path).read_bytes() != sample_bytes:
            raise ValueError("checkpoint sample changed")
    else:
        write_raw(root, sample_path, sample_bytes)


def collect(spec, run_id, root, client, *, timestamp=None, resume=False):
    """Save raw bytes before parsing; a verified incomplete package may resume.

    Rerun partition counts on resume, reuse only hash-verified completed UID leaves,
    fail closed if the saved partition plan differs from the current plan.
    """
    task = safe_id(spec["task_id"])
    if not re.fullmatch(r"r-[0-9a-f]{32}", run_id):
        raise ValueError("invalid run identity")
    root = Path(root)
    previous = None
    if resume:
        if not root.exists():
            raise FileNotFoundError("no incomplete checkpoint")
        verify(root, require_final=False)
        previous = json.loads((root / "manifest.json").read_bytes())
        if (previous["status"] != "incomplete" or previous["task_id"] != task
                or previous["run_id"] != run_id or previous["query_artifact"] != spec["query_artifact"]
                or previous["code_commit"] != os.environ.get("PUBMED_CODE_COMMIT")
                or previous["runtime"] != os.environ.get("PUBMED_RUNTIME")
                or previous["query_hashes"] != {k: sha(v.encode("utf-8")) for k,v in sorted(spec["queries"].items())}):
            raise ValueError("checkpoint execution identity mismatch")
        (root / "manifest.json").unlink()
    else:
        if root.exists():
            raise FileExistsError("new evidence package cannot overwrite existing state")
        root.mkdir(parents=True)
    for name in ("queries", "partitions", "pmids", "raw", "metadata", "samples"):
        (root / name).mkdir(exist_ok=True)
    now = previous["created_utc"] if previous else (timestamp or utc_now())
    partitions = list(previous["partitions"]) if previous else []
    results = dict(previous["reconciliation"]) if previous else {}
    calls = list(previous["requests"]) if previous else []
    prior_leaves = {(leaf["query_id"], leaf["exact_query"]): leaf for leaf in partitions}
    used_leaves = set()
    try:
        for qid, term in sorted(spec["queries"].items()):
            if not (root / f"queries/{qid}.txt").exists():
                write_raw(root, f"queries/{qid}.txt", term.encode("utf-8"))
            if (root / f"queries/{qid}.txt").read_bytes() != term.encode("utf-8"):
                raise ValueError("checkpoint query bytes mismatch")
            if qid in results:
                used_leaves.update(k for k in prior_leaves if k[0] == qid)
                union = strict_path(root, results[qid]["pmid_file"]).read_text().splitlines()
                collect_sample(spec, root, qid, union, client, calls)
                continue
            counter = max((int(Path(c["file"]).stem.split("-")[-2]) for c in calls if c["query_id"] == qid), default=0)
            leaves = [leaf for leaf in partitions if leaf["query_id"] == qid]

            def lookup(query, *, retmax, kind):
                nonlocal counter
                counter += 1
                rel = f"raw/{qid}-{counter:05d}-{kind}.json"
                raw, meta = client.esearch(query, retmax)
                write_raw(root, rel, raw)
                calls.append({"query_id": qid, "query_sha256": sha(query.encode()), "file": rel, **meta})
                return parse_result(raw)

            base = lookup(term, retmax=0, kind="count")
            a, b = dt.date.fromisoformat(spec["date_start"]), dt.date.fromisoformat(spec["date_end"])
            frontier = [(None, None)] if base["count"] < 10000 else [(a, b)]
            while frontier:
                first, last = frontier.pop(0)
                q = term if first is None else date_query(term, first, last)
                count = base["count"] if first is None else lookup(q, retmax=0, kind="count")["count"]
                if count >= 10000:
                    if first is None or first == last:
                        raise ValueError("unsplittable >=10000 PubMed partition")
                    frontier[:0] = list(plan_spans(first, last))
                    continue
                key = (qid, q)
                if key in prior_leaves:
                    leaf = prior_leaves[key]
                    if leaf["count"] != count:
                        raise ValueError("checkpoint partition count changed")
                    used_leaves.add(key)
                else:
                    retrieved = lookup(q, retmax=count, kind="ids")
                    if retrieved["count"] != count or len(retrieved["ids"]) != count:
                        raise ValueError("ESearch retrieval count mismatch")
                    ids = numeric_pmids(retrieved["ids"])
                    if len(ids) != count:
                        raise ValueError("duplicate UIDs within a partition")
                    leaf_id = f"{qid}-{len(leaves):05d}"
                    payload = ("\n".join(ids) + ("\n" if ids else "")).encode()
                    write_raw(root, f"pmids/{leaf_id}.txt", payload)
                    leaf = {"id": leaf_id, "query_id": qid, "exact_query": q,
                            "date_start": first.isoformat() if first else None,
                            "date_end": last.isoformat() if last else None,
                            "count": count, "pmid_file": f"pmids/{leaf_id}.txt",
                            "pmid_sha256": sha(payload), "querytranslation": retrieved["querytranslation"],
                            "warninglist": retrieved["warninglist"], "errorlist": retrieved["errorlist"]}
                    leaves.append(leaf)
                    partitions.append(leaf)  # partial partition captured even on later failure
                used_leaves.add(key)
            if set(k for k in prior_leaves if k[0] == qid) - used_leaves:
                raise ValueError("checkpoint partition plan diverged")
            union = numeric_pmids([p for leaf in leaves for p in (root / leaf["pmid_file"]).read_text().splitlines()])
            duplicate_count = sum(x["count"] for x in leaves) - len(union)
            if len(union) != base["count"] or duplicate_count != 0:
                raise ValueError("partition union / source count mismatch")
            output = ("\n".join(union) + ("\n" if union else "")).encode()
            write_raw(root, f"pmids/{qid}.txt", output)
            results[qid] = {"source_count": base["count"], "unique_count": len(union),
                            "duplicates": duplicate_count, "union_sha256": sha(output),
                            "pmid_file": f"pmids/{qid}.txt", "query_sha256": sha(term.encode()),
                            "querytranslation": base["querytranslation"], "warninglist": base["warninglist"],
                            "errorlist": base["errorlist"]}
            collect_sample(spec, root, qid, union, client, calls)
        write_summaries(root, partitions, results, calls)
    except Exception:
        write_summaries(root, partitions, results, calls)
        write_manifest(root, spec, run_id, now, results, "incomplete", partitions, calls)
        raise
    write_manifest(root, spec, run_id, now, results, "final", partitions, calls)
    return verify(root)


def write_summaries(root, partitions, results, calls):
    """Checkpoint metadata is versioned by Git; raw responses are immutable."""
    for rel, value in (("partitions/plan.json", partitions), ("reconciliation.json", results),
                       ("metadata/requests.json", calls)):
        strict_path(root, rel).write_bytes(canonical(value))


def write_manifest(root, spec, run_id, created, reconciliation, status, partitions, calls):
    root = Path(root)
    if (root / "manifest.json").exists():
        raise FileExistsError("manifest is immutable")
    files = {p.relative_to(root).as_posix(): {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
             for p in root.rglob("*") if p.is_file() and p.name != "manifest.json"}
    runtime = os.environ.get("PUBMED_RUNTIME", "python-stdlib")
    commit = os.environ.get("PUBMED_CODE_COMMIT", "0" * 40)
    manifest = {"schema": SCHEMA, "task_id": spec["task_id"], "run_id": run_id,
                "status": status, "code_commit": commit, "runtime": runtime,
                "query_artifact": spec["query_artifact"], "sample_policy": spec.get("sample_policy", {}),
                "query_hashes": {k: sha(v.encode("utf-8")) for k, v in sorted(spec["queries"].items())},
                "created_utc": created, "finalized_utc": created if status == "final" else None,
                "ncbi": {"endpoint": ENDPOINT, "method": "POST", "tool": os.environ.get("NCBI_TOOL", "test-tool"),
                         "email": os.environ.get("NCBI_EMAIL", "test@example.org")},
                "partition_policy": PARTITION_POLICY, "date_start": spec["date_start"],
                "date_end": spec["date_end"], "partitions": partitions,
                "requests": calls, "reconciliation": reconciliation,
                "files": dict(sorted(files.items()))}
    manifest["package_root_sha256"] = sha(canonical(manifest))
    (root / "manifest.json").write_bytes(canonical(manifest) + b"\n")


def verify(root, *, require_final=True):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_bytes())
    if (manifest.get("schema") != SCHEMA or manifest.get("status") not in ("final", "incomplete")
            or (require_final and manifest.get("status") != "final")):
        raise ValueError("schema/status mismatch")
    if manifest.get("partition_policy") != PARTITION_POLICY:
        raise ValueError("partition policy mismatch")
    task, run = safe_id(manifest["task_id"]), safe_id(manifest["run_id"])
    expected = set(manifest["files"]) | {"manifest.json"}
    allowed = ("queries/", "raw/", "pmids/", "partitions/", "samples/", "metadata/")
    if any(name != "reconciliation.json" and not name.startswith(allowed) for name in manifest["files"]):
        raise ValueError("forbidden evidence data class/path")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("symlink is forbidden")
    if actual != expected:
        raise ValueError("missing/extra evidence files")
    for name, details in manifest["files"].items():
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError("path traversal")
        p = strict_path(root, name)
        b = p.read_bytes()
        if len(b) != details["bytes"] or sha(b) != details["sha256"]:
            raise ValueError("file content/hash mismatch")
    reported_hash = manifest.pop("package_root_sha256")
    if not SHA_RE.fullmatch(reported_hash) or sha(canonical(manifest)) != reported_hash:
        raise ValueError("package root hash mismatch")
    manifest["package_root_sha256"] = reported_hash
    for qid, qsha in manifest["query_hashes"].items():
        safe_id(qid)
        if sha(strict_path(root, f"queries/{qid}.txt").read_bytes()) != qsha:
            raise ValueError("query hash mismatch")
    for call in manifest["requests"]:
        if call["file"] not in manifest["files"] or call["endpoint"] not in (ENDPOINT, EFETCH_ENDPOINT):
            raise ValueError("invalid raw request provenance")
    rec = manifest["reconciliation"]
    leaves = manifest["partitions"]
    if json.loads((root / "metadata/requests.json").read_bytes()) != manifest["requests"]:
        raise ValueError("raw request metadata drift")
    approved = {"reconciliation.json", "partitions/plan.json", "metadata/requests.json"}
    approved.update(f"queries/{qid}.txt" for qid in manifest["query_hashes"])
    approved.update(leaf["pmid_file"] for leaf in leaves)
    approved.update(summary["pmid_file"] for summary in rec.values())
    approved.update(call["file"] for call in manifest["requests"])
    for qid in manifest.get("sample_policy", {}):
        sample_file = f"samples/{qid}.pmids.txt"
        if sample_file in manifest["files"]:
            approved.add(sample_file)
    if set(manifest["files"]) != approved:
        raise ValueError("unexpected evidence file or missing file provenance")
    if True:
        if json.loads((root / "reconciliation.json").read_bytes()) != rec:
            raise ValueError("reconciliation drift")
        if json.loads((root / "partitions/plan.json").read_bytes()) != leaves:
            raise ValueError("partition plan drift")
        for leaf in leaves:
            if leaf["count"] >= 10000:
                raise ValueError("unsafe large partition")
            part_file = strict_path(root, leaf["pmid_file"])
            vals = part_file.read_text().splitlines()
            if vals != numeric_pmids(vals) or len(vals) != leaf["count"] or sha(part_file.read_bytes()) != leaf["pmid_sha256"]:
                raise ValueError("checkpoint partition integrity failure")
        for qid, summary in rec.items():
            safe_id(qid)
            file = strict_path(root, summary["pmid_file"])
            ids = file.read_text().splitlines()
            if ids != numeric_pmids(ids):
                raise ValueError("PMIDs are not canonical")
            if len(ids) != summary["unique_count"] or sha(file.read_bytes()) != summary["union_sha256"]:
                raise ValueError("PMID union integrity failure")
            leafset = []
            for leaf in leaves:
                if leaf["query_id"] == qid:
                    if leaf["count"] >= 10000:
                        raise ValueError("unsafe large partition")
                    values = strict_path(root, leaf["pmid_file"]).read_text().splitlines()
                    if values != numeric_pmids(values) or len(values) != leaf["count"]:
                        raise ValueError("partition count/hash mismatch")
                    if sha(strict_path(root, leaf["pmid_file"]).read_bytes()) != leaf["pmid_sha256"]:
                        raise ValueError("partition file hash mismatch")
                    leafset.extend(values)
            if numeric_pmids(leafset) != ids or len(leafset) - len(ids) != summary["duplicates"]:
                raise ValueError("partition union mismatch")
            if summary["unique_count"] != summary["source_count"] or summary["duplicates"]:
                raise ValueError("NCBI count reconciliation failed")
    if manifest["status"] == "final":
        if set(rec) != set(manifest["query_hashes"]):
            raise ValueError("final package missing a logical query")
        for qid, summary in rec.items():
            qleaves = [leaf for leaf in leaves if leaf["query_id"] == qid]
            if not qleaves or any(leaf["query_id"] not in rec for leaf in leaves):
                raise ValueError("final plan has missing or alien leaf")
            exact = strict_path(root, f"queries/{qid}.txt").read_text()
            if summary["source_count"] < 10000:
                if len(qleaves) != 1 or qleaves[0]["date_start"] is not None or qleaves[0]["exact_query"] != exact:
                    raise ValueError("uncut partition plan mismatch")
            else:
                first = dt.date.fromisoformat(manifest["date_start"])
                last = dt.date.fromisoformat(manifest["date_end"])
                bounds = sorted(qleaves, key=lambda leaf: leaf["date_start"] or "")
                current = first
                for leaf in bounds:
                    a = dt.date.fromisoformat(leaf["date_start"])
                    b = dt.date.fromisoformat(leaf["date_end"])
                    if a != current or b < a or leaf["exact_query"] != date_query(exact, a, b):
                        raise ValueError("partition boundary/query mismatch")
                    current = b + dt.timedelta(days=1)
                if current != last + dt.timedelta(days=1):
                    raise ValueError("partition plan date coverage mismatch")
    for qid, rule in manifest.get("sample_policy", {}).items():
        safe_id(qid)
        if qid not in manifest["query_hashes"]:
            raise ValueError("sample policy references unknown query")
        if qid not in rec:
            if manifest["status"] == "incomplete":
                continue
            raise ValueError("final sample has no query result")
        ids = strict_path(root, rec[qid]["pmid_file"]).read_text().splitlines()
        selected = numeric_pmids(sorted(ids, key=lambda pmid: sha((rule["sha256_prefix"] + pmid).encode()))[:rule["size"]])
        sample_path = strict_path(root, f"samples/{qid}.pmids.txt")
        xml_path = strict_path(root, f"raw/{qid}-sample.xml")
        # A checkpoint can contain a reconciled PMID set before EFetch succeeds.
        # Any extant sample/XML is still included in the manifest's SHA inventory.
        if manifest["status"] == "incomplete" and not sample_path.exists() and not xml_path.exists():
            continue
        if not sample_path.exists():
            if manifest["status"] != "incomplete":
                raise ValueError("final sample selection is missing")
        elif sample_path.read_text().splitlines() != selected:
            raise ValueError("sample selection drift")
        if not selected:
            if xml_path.exists() or not sample_path.exists():
                raise ValueError("empty sample must not fetch XML")
            continue
        if not xml_path.exists():
            raise ValueError("sample XML missing")
        try:
            xroot = ElementTree.fromstring(xml_path.read_bytes())
        except ElementTree.ParseError:
            raise ValueError("malformed sample XML") from None
        if xroot.tag != "PubmedArticleSet":
            raise ValueError("sample XML root drift")
        found = [el.text for el in xroot.findall("./PubmedArticle/MedlineCitation/PMID")]
        if numeric_pmids(found) != selected or len(found) != len(selected):
            raise ValueError("sample XML UID mismatch")
    size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    if size > MAX_PACKAGE:
        raise ValueError("package exceeds 50 MiB")
    return {"task_id": task, "run_id": run, "root_hash": reported_hash, "bytes": size,
            "status": manifest["status"], "counts": {k:v["unique_count"] for k,v in manifest["reconciliation"].items()}}


def _run(*args, cwd=None, env=None):
    return subprocess.check_output(args, cwd=cwd, env=env, stderr=subprocess.DEVNULL, text=True).strip()


def evidence_path(task, run):
    return f"pubmed/{safe_id(task)}/{safe_id(run)}"


def validate_repository(repository):
    if repository != "Dr-snai1/Pro_Adherence-research-evidence":
        raise ValueError("unapproved evidence repository")
    return "git@github.com:" + repository + ".git"


def git_write(package, repository, *, workdir=None):
    check = verify(package, require_final=False)
    if check["status"] not in ("final", "incomplete"):
        raise ValueError("unsupported package status")
    url = validate_repository(repository)
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        git = Path(tmp) / "evidence"
        _run("git", "clone", "--quiet", url, str(git))
        rel = evidence_path(check["task_id"], check["run_id"])
        dst = strict_path(git, rel)
        if dst.exists():
            previous = verify(dst, require_final=False)
            if previous["status"] != "incomplete" or previous["task_id"] != check["task_id"] or previous["run_id"] != check["run_id"]:
                raise FileExistsError("cannot overwrite existing final or different evidence")
            old_files = {p.relative_to(dst).as_posix():sha(p.read_bytes()) for p in dst.rglob("*") if p.is_file()}
            new_files = {p.relative_to(package).as_posix():sha(p.read_bytes()) for p in Path(package).rglob("*") if p.is_file()}
            if set(old_files) - set(new_files):
                raise ValueError("checkpoint removed existing evidence")
            mutable = {"manifest.json", "partitions/plan.json", "reconciliation.json", "metadata/requests.json"}
            if any(old_files[name] != new_files[name] for name in old_files if name not in mutable):
                raise ValueError("checkpoint rewrote immutable raw evidence")
        existing_size = sum(p.stat().st_size for p in git.rglob("*") if p.is_file())
        if existing_size + check["bytes"] >= MAX_REPOSITORY:
            raise ValueError("evidence repository exceeds 1 GiB boundary")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(package, dst, dirs_exist_ok=True)
        verify(dst, require_final=False)
        _run("git", "-C", str(git), "add", "--", rel)
        _run("git", "-C", str(git), "-c", "user.name=Pro Adherence Evidence",
             "-c", "user.email=research-evidence@users.noreply.github.com",
             "commit", "-m", f"Evidence {check['task_id']} {check['run_id']}")
        commit = _run("git", "-C", str(git), "rev-parse", "HEAD")
        _run("git", "-C", str(git), "push", "origin", "HEAD:main")
        return commit, rel, check


def clone_readback(repository, commit, task, run, *, target=None):
    validate_repository(repository)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("exact evidence commit required")
    work = Path(target) if target else Path(tempfile.mkdtemp(prefix="pubmed-readback-"))
    if work.exists() and any(work.iterdir()):
        raise FileExistsError("readback directory must be empty")
    work.mkdir(parents=True, exist_ok=True)
    _run("git", "clone", "--quiet", "--no-checkout", validate_repository(repository), str(work))
    _run("git", "-C", str(work), "checkout", "--quiet", "--detach", commit)
    if _run("git", "-C", str(work), "rev-parse", "HEAD") != commit:
        raise ValueError("readback did not checkout requested commit")
    rel = evidence_path(task, run)
    return verify(strict_path(work, rel)), strict_path(work, rel)


def prepare_resume(repository, task, run, target):
    """Get a hash-verified incomplete checkpoint from durable private Git history."""
    validate_repository(repository)
    target = Path(target)
    if target.exists():
        raise FileExistsError("checkpoint destination must not exist")
    with tempfile.TemporaryDirectory() as tmp:
        git = Path(tmp) / "evidence"
        _run("git", "clone", "--quiet", validate_repository(repository), str(git))
        rel = evidence_path(task, run)
        source = strict_path(git, rel)
        proof = verify(source, require_final=False)
        if proof["status"] != "incomplete":
            raise ValueError("only incomplete packages can resume")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        if verify(target, require_final=False) != proof:
            raise ValueError("copied checkpoint hash mismatch")
        return proof


def backup(repository, commit, task, run, dest):
    target = strict_path(Path(dest), evidence_path(task, run))
    if target.exists():
        raise FileExistsError("backup must never overwrite an existing snapshot")
    with tempfile.TemporaryDirectory() as tmp:
        info, source = clone_readback(repository, commit, task, run, target=Path(tmp)/"readback")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        check = verify(target)
        if check != info:
            raise ValueError("local backup verification mismatch")
    record = {"schema": "pubmed-local-backup/v1", "evidence_commit": commit,
              "package_path": evidence_path(task, run), "verified_at_utc": utc_now(), **check}
    path = target.parent / (run + ".backup-verification.json")
    path.write_bytes(canonical(record) + b"\n")
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description="PubMed project-internal evidence runner (not scientific verdict)")
    subs = p.add_subparsers(dest="action", required=True)
    col = subs.add_parser("collect")
    for flag in ("spec", "out", "mode", "code-commit", "runtime"):
        col.add_argument("--"+flag, required=True)
    col.add_argument("--resume", action="store_true")
    ver = subs.add_parser("verify"); ver.add_argument("path"); ver.add_argument("--allow-incomplete",action="store_true")
    res = subs.add_parser("prepare-resume")
    for flag in ("repository", "task-id", "run-id", "target"):
        res.add_argument("--"+flag, required=True)
    wr = subs.add_parser("write"); wr.add_argument("path"); wr.add_argument("--repository", required=True)
    read = subs.add_parser("readback")
    back = subs.add_parser("backup")
    for sub in (read, back):
        for flag in ("repository", "commit", "task-id", "run-id"):
            sub.add_argument("--"+flag, required=True)
    back.add_argument("--target", required=True)
    args = p.parse_args(argv)
    try:
        if args.action == "collect":
            spec, run = read_spec(args.spec, mode=args.mode, code_commit=args.code_commit, runtime=args.runtime)
            os.environ["PUBMED_CODE_COMMIT"] = args.code_commit
            os.environ["PUBMED_RUNTIME"] = args.runtime
            info = collect(spec, run, Path(args.out) / evidence_path(spec["task_id"], run),
                           Client(os.environ["NCBI_TOOL"], os.environ["NCBI_EMAIL"], os.environ.get("NCBI_API_KEY", "")),
                           resume=args.resume)
        elif args.action == "verify":
            info = verify(args.path,require_final=not args.allow_incomplete)
        elif args.action == "prepare-resume":
            info = prepare_resume(args.repository,args.task_id,args.run_id,args.target)
        elif args.action == "write":
            commit, rel, info = git_write(args.path, args.repository)
            info.update({"evidence_commit": commit, "evidence_path": rel})
        elif args.action == "readback":
            info, _ = clone_readback(args.repository, args.commit, args.task_id, args.run_id)
        elif args.action == "backup":
            info = backup(args.repository, args.commit, args.task_id, args.run_id, args.target)
        print(json.dumps(info, sort_keys=True))
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError, subprocess.CalledProcessError, KeyError) as exc:
        # Never emit request contents, NCBI key, SSH key or subprocess stderr.
        print(f"pubmed-evidence: failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
