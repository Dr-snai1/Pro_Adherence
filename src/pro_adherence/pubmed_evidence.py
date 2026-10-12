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


# Central canonical semantic-role POSIX paths. Query ID remains a separate segment.
def query_path(qid):
    return f"queries/{safe_id(qid)}.txt"


def union_path(qid):
    return f"pmids/{safe_id(qid)}/union.txt"


def _natural_index(index, *, minimum=0):
    if type(index) is not int or index < minimum:
        raise ValueError("invalid artifact index/attempt")
    return index


def leaf_path(qid, index):
    return f"pmids/{safe_id(qid)}/leaves/{_natural_index(index):05d}.txt"


def sample_path(qid):
    return f"samples/{safe_id(qid)}/pmids.txt"


def esearch_raw_path(qid, sequence, kind):
    if kind not in ("count", "ids"):
        raise ValueError("invalid ESearch artifact kind")
    return f"raw/{safe_id(qid)}/esearch/{_natural_index(sequence, minimum=1):05d}-{kind}.json"


def efetch_raw_path(qid, attempt):
    return f"raw/{safe_id(qid)}/efetch/{_natural_index(attempt, minimum=1):05d}.xml"


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


def checked_sample(raw, chosen):
    """Recheck immutable raw XML; no failed attempt is silently accepted."""
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        raise ValueError("malformed PubMed EFetch XML") from None
    if root.tag != "PubmedArticleSet":
        raise ValueError("unexpected PubMed EFetch XML")
    found = [element.text for element in root.findall("./PubmedArticle/MedlineCitation/PMID")]
    try:
        valid = numeric_pmids(found) == chosen and len(found) == len(chosen)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("EFetch PMID identity mismatch")


def selected_pmids(spec, qid, union):
    rule = spec.get("sample_policy", {}).get(qid)
    if rule is None:
        return []
    return numeric_pmids(sorted(union, key=lambda pmid: sha((rule["sha256_prefix"] + pmid).encode()))[:rule["size"]])


def collect_sample(spec, root, qid, union, client, calls):
    """Append-only EFetch attempts: rejected bytes remain evidence on retry."""
    if qid not in spec.get("sample_policy", {}):
        return
    chosen = selected_pmids(spec, qid, union)
    sample_rel = sample_path(qid)
    if not chosen:
        if not strict_path(root, sample_rel).exists():
            write_raw(root, sample_rel, b"")
        return
    old = [call for call in calls if call["query_id"] == qid and call["endpoint"] == EFETCH_ENDPOINT]
    if old and old[-1]["outcome"] == "accepted":
        raw = strict_path(root, old[-1]["file"]).read_bytes()
        checked_sample(raw, chosen)
    else:
        attempt = len(old) + 1
        rel = efetch_raw_path(qid, attempt)
        raw, meta = client.efetch(chosen)
        write_raw(root, rel, raw)
        record = {"query_id": qid, "query_sha256": sha(canonical(chosen)),
                  "file": rel, "attempt": attempt, **meta}
        calls.append(record)
        try:
            checked_sample(raw, chosen)
        except ValueError as exc:
            record["outcome"] = "rejected"
            record["failure_reason"] = str(exc)
            raise
        record["outcome"] = "accepted"
    data = ("\n".join(chosen) + "\n").encode()
    if strict_path(root, sample_rel).exists():
        if strict_path(root, sample_rel).read_bytes() != data:
            raise ValueError("checkpoint sample changed")
    else:
        write_raw(root, sample_rel, data)

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
    states = dict(previous["query_states"]) if previous else {qid: "not_started" for qid in spec["queries"]}
    # Materialize *all* exact query identities before the first network request.
    for qid, term in sorted(spec["queries"].items()):
        rel = query_path(qid)
        if not strict_path(root, rel).exists():
            write_raw(root, rel, term.encode("utf-8"))
        if strict_path(root, rel).read_bytes() != term.encode("utf-8"):
            raise ValueError("checkpoint query bytes mismatch")
    active = None
    stage = None
    try:
        for qid, term in sorted(spec["queries"].items()):
            active = qid
            stage = "sample" if qid in results else "search"
            states[qid] = "in_progress"
            if qid in results:
                used_leaves.update(k for k in prior_leaves if k[0] == qid)
                union = strict_path(root, results[qid]["pmid_file"]).read_text().splitlines()
                collect_sample(spec, root, qid, union, client, calls)
                states[qid] = "completed"
                continue
            counter = sum(c["query_id"] == qid and c["endpoint"] == ENDPOINT for c in calls)
            leaves = [leaf for leaf in partitions if leaf["query_id"] == qid]

            def lookup(query, *, retmax, kind):
                nonlocal counter
                counter += 1
                rel = esearch_raw_path(qid, counter, kind)
                raw, meta = client.esearch(query, retmax)
                write_raw(root, rel, raw)
                call = {"query_id": qid, "query_sha256": sha(query.encode()),
                        "exact_query": query, "file": rel, **meta}
                calls.append(call)
                try:
                    parsed = parse_result(raw)
                except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    call["outcome"] = "rejected"
                    call["failure_reason"] = type(exc).__name__
                    raise
                call["outcome"] = "accepted"
                call["result_count"] = parsed["count"]
                call["result_ids_sha256"] = sha(canonical(parsed["ids"]))
                return parsed

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
                    write_raw(root, leaf_path(qid, len(leaves)), payload)
                    leaf = {"id": leaf_id, "query_id": qid, "exact_query": q,
                            "date_start": first.isoformat() if first else None,
                            "date_end": last.isoformat() if last else None,
                            "count": count, "pmid_file": leaf_path(qid, len(leaves)),
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
            write_raw(root, union_path(qid), output)
            results[qid] = {"source_count": base["count"], "unique_count": len(union),
                            "duplicates": duplicate_count, "union_sha256": sha(output),
                            "pmid_file": union_path(qid), "query_sha256": sha(term.encode()),
                            "querytranslation": base["querytranslation"], "warninglist": base["warninglist"],
                            "errorlist": base["errorlist"]}
            stage = "sample"
            collect_sample(spec, root, qid, union, client, calls)
            states[qid] = "completed"
        write_summaries(root, partitions, results, calls)
    except Exception as exc:
        if active is None:
            raise
        states[active] = "failed_checkpointable"
        failure = {"query_id": active, "stage": stage,
                   "exception": type(exc).__name__}
        write_summaries(root, partitions, results, calls)
        write_manifest(root, spec, run_id, now, results, "incomplete", partitions, calls,
                       states, failure)
        raise
    write_manifest(root, spec, run_id, now, results, "final", partitions, calls,
                   states, None)
    return verify(root)


def write_summaries(root, partitions, results, calls):
    """Checkpoint metadata is versioned by Git; raw responses are immutable."""
    for rel, value in (("partitions/plan.json", partitions), ("reconciliation.json", results),
                       ("metadata/requests.json", calls)):
        strict_path(root, rel).write_bytes(canonical(value))


def write_manifest(root, spec, run_id, created, reconciliation, status, partitions, calls,
                   query_states, failure):
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
                "query_states": query_states, "failure": failure,
                "files": dict(sorted(files.items()))}
    manifest["package_root_sha256"] = sha(canonical(manifest))
    (root / "manifest.json").write_bytes(canonical(manifest) + b"\n")


def valid_query_span(term, exact, start, end):
    if exact == term:
        return True
    match = re.fullmatch(
        r'\(' + re.escape(term) + r'\) AND \("(\d{4}/\d{2}/\d{2})"\[dp\] : "(\d{4}/\d{2}/\d{2})"\[dp\]\)',
        exact, flags=re.DOTALL)
    if not match:
        return False
    try:
        a = dt.datetime.strptime(match.group(1), "%Y/%m/%d").date()
        b = dt.datetime.strptime(match.group(2), "%Y/%m/%d").date()
        return (dt.date.fromisoformat(start) <= a <= b <= dt.date.fromisoformat(end)
                and date_query(term, a, b) == exact)
    except ValueError:
        return False


def verify(root, *, require_final=True):
    """One integrity gate for final and declared incomplete states; reparse source raw."""
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_bytes())
    expected_keys = {"schema", "task_id", "run_id", "status", "code_commit",
                     "runtime", "query_artifact", "sample_policy", "query_hashes",
                     "created_utc", "finalized_utc", "ncbi", "partition_policy",
                     "date_start", "date_end", "partitions", "requests",
                     "reconciliation", "files", "package_root_sha256",
                     "query_states", "failure"}
    if set(manifest) != expected_keys or manifest["schema"] != SCHEMA:
        raise ValueError("manifest schema mismatch")
    if manifest["status"] not in ("final", "incomplete") or (require_final and manifest["status"] != "final"):
        raise ValueError("schema/status mismatch")
    if (manifest["partition_policy"] != PARTITION_POLICY
            or not re.fullmatch(r"[0-9a-f]{40}", manifest["code_commit"])
            or not isinstance(manifest["runtime"], str) or not manifest["runtime"]
            or not isinstance(manifest["query_artifact"], str)):
        raise ValueError("execution identity mismatch")
    safe_id(manifest["query_artifact"])
    task, run = safe_id(manifest["task_id"]), safe_id(manifest["run_id"])
    if not re.fullmatch(r"r-[a-f0-9]{32}", run):
        raise ValueError("run identity mismatch")
    try:
        if dt.date.fromisoformat(manifest["date_start"]) > dt.date.fromisoformat(manifest["date_end"]):
            raise ValueError("date bounds invalid")
        dt.datetime.fromisoformat(manifest["created_utc"].replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("manifest dates invalid") from None
    if manifest["status"] == "final" and manifest["finalized_utc"] != manifest["created_utc"]:
        raise ValueError("final timestamp mismatch")
    if manifest["status"] == "incomplete" and manifest["finalized_utc"] is not None:
        raise ValueError("incomplete final timestamp mismatch")
    if (manifest["ncbi"]["endpoint"] != ENDPOINT or manifest["ncbi"]["method"] != "POST"
            or not manifest["ncbi"].get("tool") or not manifest["ncbi"].get("email")):
        raise ValueError("NCBI provenance mismatch")
    queries = manifest["query_hashes"]
    states = manifest["query_states"]
    if not isinstance(queries, dict) or not queries or set(states) != set(queries):
        raise ValueError("query identity/state mismatch")
    if any(not SHA_RE.fullmatch(h) for h in queries.values()):
        raise ValueError("query hash format mismatch")
    if not isinstance(manifest["sample_policy"], dict) or not set(manifest["sample_policy"]).issubset(queries):
        raise ValueError("invalid sample policy")
    for rule in manifest["sample_policy"].values():
        if (not isinstance(rule, dict) or set(rule) != {"size", "sha256_prefix"}
                or type(rule["size"]) is not int or not 1 <= rule["size"] <= 100
                or not isinstance(rule["sha256_prefix"], str) or not rule["sha256_prefix"]):
            raise ValueError("invalid sample rule")
    failure = manifest["failure"]
    order = sorted(queries)
    if manifest["status"] == "final":
        if failure is not None or any(states[q] != "completed" for q in order):
            raise ValueError("final state inconsistency")
    else:
        if (not isinstance(failure, dict) or set(failure) != {"query_id", "stage", "exception"}
                or failure["query_id"] not in queries
                or failure["stage"] not in ("search", "sample")
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", failure["exception"])):
            raise ValueError("checkpoint failure metadata inconsistency")
        active = order.index(failure["query_id"])
        required_states = {q: ("completed" if i < active else
                               "failed_checkpointable" if i == active else "not_started")
                           for i, q in enumerate(order)}
        if states != required_states:
            raise ValueError("checkpoint query state inconsistency")
        failed_qid = failure["query_id"]
        if ((failure["stage"] == "sample" and
             (failed_qid not in manifest["reconciliation"] or
              failed_qid not in manifest["sample_policy"]))
                or (failure["stage"] == "search" and
                    failed_qid in manifest["reconciliation"])):
            raise ValueError("checkpoint stage/artifact inconsistency")
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
        if name.startswith("/") or ".." in Path(name).parts or name.endswith("/"):
            raise ValueError("path traversal")
        b = strict_path(root, name).read_bytes()
        if set(details) != {"sha256", "bytes"} or len(b) != details["bytes"] or sha(b) != details["sha256"]:
            raise ValueError("file content/hash mismatch")
    reported_hash = manifest.pop("package_root_sha256")
    if not SHA_RE.fullmatch(reported_hash) or sha(canonical(manifest)) != reported_hash:
        raise ValueError("package root hash mismatch")
    manifest["package_root_sha256"] = reported_hash
    exact_queries = {}
    for qid, qsha in queries.items():
        safe_id(qid)
        raw_query = strict_path(root, query_path(qid)).read_bytes()
        if sha(raw_query) != qsha:
            raise ValueError("query hash mismatch")
        exact_queries[qid] = raw_query.decode("utf-8")
        if not exact_queries[qid].strip():
            raise ValueError("empty query")

    rec, leaves, calls = manifest["reconciliation"], manifest["partitions"], manifest["requests"]
    if json.loads((root / "metadata/requests.json").read_bytes()) != calls:
        raise ValueError("request metadata drift")
    if (json.loads((root / "reconciliation.json").read_bytes()) != rec
            or json.loads((root / "partitions/plan.json").read_bytes()) != leaves):
        raise ValueError("derived metadata drift")
    # Inventory is independently reconstructed from canonical semantic identities.
    # Detect cross-query and cross-role aliases even if hashes and manifest are rehashed.
    semantic_paths = ["reconciliation.json", "partitions/plan.json", "metadata/requests.json"]
    semantic_paths.extend(query_path(qid) for qid in queries)
    leaf_seq = {}
    for leaf in leaves:
        qid = leaf["query_id"]
        if qid not in queries:
            raise ValueError("alien partition query")
        index = leaf_seq.get(qid, 0)
        if leaf["id"] != f"{qid}-{index:05d}" or leaf["pmid_file"] != leaf_path(qid, index):
            raise ValueError("noncanonical partition role/path/index")
        semantic_paths.append(leaf_path(qid, index))
        leaf_seq[qid] = index + 1
    if not set(rec).issubset(queries):
        raise ValueError("alien reconciled query")
    for qid, summary in rec.items():
        if summary["pmid_file"] != union_path(qid):
            raise ValueError("noncanonical union role/path")
        semantic_paths.append(union_path(qid))
    search_attempts, fetch_attempts = {}, {}
    for call in calls:
        qid = call["query_id"]
        if qid not in queries:
            raise ValueError("alien request query")
        if call["endpoint"] == ENDPOINT:
            seq = search_attempts.get(qid, 0) + 1
            match = re.fullmatch(r"raw/" + re.escape(qid) + r"/esearch/([0-9]{5,})-(count|ids)\.json", call["file"])
            if not match or int(match.group(1)) != seq:
                raise ValueError("noncanonical ESearch role/path/index")
            expected_rel = esearch_raw_path(qid, seq, match.group(2))
            search_attempts[qid] = seq
        elif call["endpoint"] == EFETCH_ENDPOINT:
            seq = fetch_attempts.get(qid, 0) + 1
            expected_rel = efetch_raw_path(qid, seq)
            fetch_attempts[qid] = seq
        else:
            raise ValueError("unapproved source endpoint")
        if call["file"] != expected_rel:
            raise ValueError("noncanonical request role/path")
        semantic_paths.append(expected_rel)
    for qid in manifest["sample_policy"]:
        if qid not in queries:
            raise ValueError("unknown sample query")
        rel = sample_path(qid)
        if rel in manifest["files"]:
            semantic_paths.append(rel)
    if len(semantic_paths) != len(set(semantic_paths)):
        raise ValueError("physical evidence pathname aliases two semantic roles")
    if set(manifest["files"]) != set(semantic_paths):
        raise ValueError("unexpected evidence file or missing file provenance")
    if not set(rec).issubset(queries):
        raise ValueError("alien reconciled query")
    if any(states[q] == "not_started" and (q in rec or any(x["query_id"] == q for x in leaves+calls))
           for q in queries):
        raise ValueError("not-started query has artifacts")
    if any(states[q] == "completed" and q not in rec for q in queries):
        raise ValueError("completed query has missing reconciliation")
    if manifest["status"] == "final" and set(rec) != set(queries):
        raise ValueError("final missing queries")
    # Every persisted response has a provenance record and a semantic outcome.
    raw_responses = {}
    ids_by_q = {}
    base_counts = {}
    sample_by_q = {}
    search_seq = {}
    for call in calls:
        qid = call["query_id"]
        if qid not in queries or states[qid] == "not_started":
            raise ValueError("request query state mismatch")
        rel = call["file"]
        if rel not in manifest["files"] or call.get("method") != "POST" or not call.get("utc"):
            raise ValueError("invalid raw request provenance")
        if rel in raw_responses:
            raise ValueError("duplicate raw request provenance")
        if call["endpoint"] == ENDPOINT:
            match = re.fullmatch(r"raw/" + re.escape(qid) + r"/esearch/(\d{5,})-(count|ids)\.json", rel)
            if not match or call["retmax"] < 0:
                raise ValueError("ESearch path/limit provenance mismatch")
            seq = int(match.group(1))
            if seq != search_seq.get(qid, 0) + 1 or rel != esearch_raw_path(qid, seq, match.group(2)):
                raise ValueError("ESearch request ordering mismatch")
            search_seq[qid] = seq
            kind = match.group(2)
            query = call.get("exact_query")
            if (not isinstance(query, str)
                    or not valid_query_span(exact_queries[qid], query, manifest["date_start"], manifest["date_end"])
                    or call["query_sha256"] != sha(query.encode())
                    or (kind == "count" and call["retmax"] != 0)
                    or (kind == "ids" and not 0 <= call["retmax"] < 10000)):
                raise ValueError("ESearch exact query provenance mismatch")
            try:
                parsed = parse_result(strict_path(root, rel).read_bytes())
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                if call.get("outcome") != "rejected" or call.get("failure_reason") not in ("ValueError", "KeyError", "TypeError", "JSONDecodeError"):
                    raise ValueError("unrecorded invalid ESearch response")
                raw_responses[rel] = (call, None)
                continue
            if (call.get("outcome") != "accepted" or call.get("result_count") != parsed["count"]
                    or call.get("result_ids_sha256") != sha(canonical(parsed["ids"]))):
                raise ValueError("raw ESearch source/metadata mismatch")
            if kind == "count" and parsed["ids"]:
                raise ValueError("count-only ESearch supplied UIDs")
            if kind == "ids":
                if parsed["count"] != call["retmax"] or len(parsed["ids"]) != call["retmax"]:
                    # This can be a legitimate failed checkpoint, but not a completed query.
                    if manifest["status"] == "final" or states[qid] != "failed_checkpointable":
                        raise ValueError("unreconciled ESearch UID response")
                ids_by_q.setdefault((qid, query), []).append((rel, parsed))
            elif query == exact_queries[qid]:
                base_counts.setdefault(qid, []).append(parsed)
            raw_responses[rel] = (call, parsed)
        elif call["endpoint"] == EFETCH_ENDPOINT:
            sample_by_q.setdefault(qid, []).append(call)
            n = len(sample_by_q[qid])
            expected_rel = efetch_raw_path(qid, n)
            if (call.get("attempt") != n or rel != expected_rel
                    or qid not in manifest["sample_policy"] or qid not in rec):
                raise ValueError("sample attempt provenance mismatch")
            ids = strict_path(root, rec[qid]["pmid_file"]).read_text().splitlines()
            chosen = selected_pmids({"sample_policy": manifest["sample_policy"]}, qid, ids)
            if not chosen or call["query_sha256"] != sha(canonical(chosen)) or call["retmax"] != len(chosen):
                raise ValueError("sample selection provenance mismatch")
            try:
                checked_sample(strict_path(root, rel).read_bytes(), chosen)
            except ValueError as exc:
                if call.get("outcome") != "rejected" or call.get("failure_reason") != str(exc):
                    raise ValueError("sample attempt failure metadata mismatch")
            else:
                if call.get("outcome") != "accepted" or "failure_reason" in call:
                    raise ValueError("sample attempt success metadata mismatch")
            raw_responses[rel] = (call, None)
        else:
            raise ValueError("unapproved source endpoint")
    if any(call["endpoint"] == EFETCH_ENDPOINT and call["outcome"] == "accepted"
           and any(next_call["endpoint"] == EFETCH_ENDPOINT and next_call["query_id"] == call["query_id"]
                   for next_call in calls[calls.index(call)+1:]) for call in calls):
        raise ValueError("successful sample attempt cannot be retried")

    # Source/raw-to-derived reconciliation, independent of manifest file hashes.
    leaf_files = set()
    for leaf in leaves:
        qid = leaf["query_id"]
        if qid not in queries or states[qid] == "not_started" or leaf["count"] >= 10000:
            raise ValueError("unsafe partition query/state/count")
        if (leaf["pmid_file"] not in semantic_paths
                or not leaf["id"].startswith(qid + "-")
                or leaf["pmid_file"] in leaf_files
                or not valid_query_span(exact_queries[qid], leaf["exact_query"],
                                        manifest["date_start"], manifest["date_end"])):
            raise ValueError("partition path/query mismatch")
        leaf_files.add(leaf["pmid_file"])
        part = strict_path(root, leaf["pmid_file"])
        vals = part.read_text().splitlines()
        if vals != numeric_pmids(vals) or len(vals) != leaf["count"] or sha(part.read_bytes()) != leaf["pmid_sha256"]:
            raise ValueError("checkpoint partition integrity failure")
        linked = ids_by_q.get((qid, leaf["exact_query"]), [])
        if len(linked) != 1 or numeric_pmids(linked[0][1]["ids"]) != vals or linked[0][1]["count"] != leaf["count"]:
            raise ValueError("raw ESearch ID/derived leaf mismatch")
        counts = [item[1] for item in raw_responses.values()
                  if item[0]["endpoint"] == ENDPOINT and item[0]["file"].endswith("-count.json")
                  and item[0]["query_id"] == qid and item[0]["exact_query"] == leaf["exact_query"]
                  and item[1] is not None]
        if not counts or counts[-1]["count"] != leaf["count"]:
            raise ValueError("raw ESearch count/derived leaf mismatch")
    for (qid, query), raw_ids in ids_by_q.items():
        if len(raw_ids) != 1:
            raise ValueError("multiple raw ID responses for same partition")
        if not any(leaf["query_id"] == qid and leaf["exact_query"] == query for leaf in leaves):
            if states[qid] != "failed_checkpointable":
                raise ValueError("orphan accepted ESearch IDs")
    for qid, summary in rec.items():
        if summary["query_sha256"] != queries[qid] or summary["pmid_file"] != union_path(qid):
            raise ValueError("reconciliation identity mismatch")
        if not base_counts.get(qid) or base_counts[qid][-1]["count"] != summary["source_count"]:
            raise ValueError("raw ESearch count/reconciliation mismatch")
        base = base_counts[qid][-1]
        if any(summary.get(k) != base[k] for k in ("querytranslation", "warninglist", "errorlist")):
            raise ValueError("source ESearch metadata drift")
        part_ids = [pid for leaf in leaves if leaf["query_id"] == qid
                    for pid in strict_path(root, leaf["pmid_file"]).read_text().splitlines()]
        ids = strict_path(root, summary["pmid_file"]).read_text().splitlines()
        if ids != numeric_pmids(ids) or numeric_pmids(part_ids) != ids:
            raise ValueError("partition union mismatch")
        if (len(ids) != summary["unique_count"] or len(part_ids) - len(ids) != summary["duplicates"]
                or summary["duplicates"] or summary["source_count"] != summary["unique_count"]
                or sha(strict_path(root, summary["pmid_file"]).read_bytes()) != summary["union_sha256"]):
            raise ValueError("NCBI count reconciliation failed")
        qleaves = [leaf for leaf in leaves if leaf["query_id"] == qid]
        if not qleaves:
            raise ValueError("reconciled query has no leaves")
        if summary["source_count"] < 10000:
            if len(qleaves) != 1 or qleaves[0]["exact_query"] != exact_queries[qid] or qleaves[0]["date_start"] is not None:
                raise ValueError("uncut partition plan mismatch")
        else:
            bounds = sorted(qleaves, key=lambda x: x["date_start"] or "")
            current = dt.date.fromisoformat(manifest["date_start"])
            for leaf in bounds:
                a = dt.date.fromisoformat(leaf["date_start"])
                b = dt.date.fromisoformat(leaf["date_end"])
                if a != current or b < a or leaf["exact_query"] != date_query(exact_queries[qid], a, b):
                    raise ValueError("partition boundary/query mismatch")
                current = b + dt.timedelta(days=1)
            if current != dt.date.fromisoformat(manifest["date_end"]) + dt.timedelta(days=1):
                raise ValueError("partition plan date coverage mismatch")

    # Final requires successful last EFetch (or the explicit zero-result policy).
    for qid, rule in manifest["sample_policy"].items():
        if qid not in rec:
            if manifest["status"] == "final":
                raise ValueError("final sample query missing")
            continue
        ids = strict_path(root, rec[qid]["pmid_file"]).read_text().splitlines()
        chosen = selected_pmids({"sample_policy": manifest["sample_policy"]}, qid, ids)
        sample_file = strict_path(root, sample_path(qid))
        attempts = sample_by_q.get(qid, [])
        accepted = bool(attempts and attempts[-1]["outcome"] == "accepted")
        if not chosen:
            if not sample_file.exists() or sample_file.read_bytes() != b"" or attempts:
                raise ValueError("zero-result sample policy mismatch")
            continue
        if sample_file.exists() and sample_file.read_text().splitlines() != chosen:
            raise ValueError("sample selection drift")
        if sample_file.exists() and not accepted:
            raise ValueError("sample file lacks successful raw evidence")
        if manifest["status"] == "final" or states[qid] == "completed":
            if not sample_file.exists() or not accepted:
                raise ValueError("completed sample missing successful attempt")
    size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    if size > MAX_PACKAGE:
        raise ValueError("package exceeds 50 MiB")
    return {"task_id": task, "run_id": run, "root_hash": reported_hash, "bytes": size,
            "status": manifest["status"], "counts": {k: v["unique_count"] for k, v in rec.items()}}

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
