#!/usr/bin/env python3
"""Independent private audit of full classical citation pair-list outputs.

The writer is separate: scripts/stage3_classical_citation_networks.py.
This verifier independently streams retained directed evidence, verifies exact
compressed bytes / gzip CRC, all pair ordering and expected weight histograms,
and recomputes sampled pair weights directly from source graph neighborhoods.

No private source strings, IDs, DOI, or vectors appear in a success report.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import zipfile


N = 57204
GRAPH_SHA256 = "33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c"
EXPECTED = {
    "co_citation": {
        "rows": 2055149, "sum": 2891776, "max": 333,
        "hist": {"1":1671708,"2":233200,"3":70498,"4":30563,"5":16254,"6_plus":32926},
    },
    "bibliographic_coupling": {
        "rows":15871086, "sum":18490159, "max":163,
        "hist":{"1":13919745,"2":1518424,"3":297582,"4":83566,"5":29236,"6_plus":22533},
    },
}


def digest(path):
    d = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1<<20), b""):
            d.update(block)
    return d.hexdigest()


def jsonl_member(z, member):
    with z.open(member) as f, gzip.GzipFile(fileobj=f,mode="rb") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def load_graph(z):
    eligible={}
    for row in jsonl_member(z,"node2vec_node_mapping.private.jsonl.gz"):
        ind=row["node_index"];aid=row["article_id"]
        if type(ind) is not int or ind<0 or ind>=N or ind in eligible.values():
            raise ValueError("Bad node mapping index")
        if aid in eligible:
            raise ValueError("Duplicate article mapping")
        eligible[aid]=ind
    if len(eligible)!=N:
        raise ValueError("Incorrect eligible mapping length")
    outgoing=[set() for _ in range(N)]
    incoming=[set() for _ in range(N)]
    seen=set()
    raw=noneligible=loops=0
    for edge in jsonl_member(z,"directed_edges.private.jsonl.gz"):
        raw+=1
        a=eligible.get(edge["source_article_id"])
        b=eligible.get(edge["target_article_id"])
        if a is None or b is None:
            noneligible+=1;continue
        if a==b:
            loops+=1;continue
        key=(a,b)
        if key in seen:
            raise ValueError("Duplicated directed evidence edge")
        seen.add(key)
        outgoing[a].add(b)
        incoming[b].add(a)
    if (raw,noneligible,loops,len(seen))!=(328383,47,29,328307):
        raise ValueError("Frozen directed graph counts changed")
    return outgoing,incoming


def expected_support(label, a, b, outgoing, incoming):
    if label=="co_citation":
        return len(incoming[a].intersection(incoming[b]))
    if label=="bibliographic_coupling":
        return len(outgoing[a].intersection(outgoing[b]))
    raise ValueError(label)


def stream_verify(path,label,outgoing,incoming):
    exp=EXPECTED[label]
    n=weighted=maximum=previous=0
    previous=-1
    hist=Counter()
    # Full stream is validated; samples follow fixed row indices, not RNG.
    checks=set((0,1,2,exp["rows"]//2,exp["rows"]-1))
    checks.update(range(100000,exp["rows"],100000))
    sampled=0
    with gzip.open(path,"rt",encoding="ascii") as f:
        for line in f:
            row=json.loads(line)
            if not isinstance(row,list) or len(row)!=2:
                raise ValueError("Bad pair row")
            key,weight=row
            if type(key) is not int or type(weight) is not int or weight<1:
                raise ValueError("Noninteger or nonpositive pair value")
            if key<=previous:
                raise ValueError("Out-of-order / duplicate pair key")
            a,b=divmod(key,N)
            if not 0<=a<b<N:
                raise ValueError("Out-of-range or noncanonical pair key")
            previous=key
            weighted+=weight
            maximum=max(maximum,weight)
            hist[str(weight) if weight<6 else "6_plus"]+=1
            if n in checks:
                if expected_support(label,a,b,outgoing,incoming)!=weight:
                    raise ValueError("Independent source-vs-pair weight mismatch")
                sampled+=1
            n+=1
    if (n,weighted,maximum)!=(exp["rows"],exp["sum"],exp["max"]):
        raise ValueError("Pair output totals mismatch")
    if dict(hist)!=exp["hist"]:
        raise ValueError("Weight histogram mismatch")
    neighborhoods=outgoing if label=="co_citation" else incoming
    incidence=sum(len(adj)*(len(adj)-1)//2 for adj in neighborhoods)
    if weighted!=incidence:
        raise ValueError("Independent combinatorial incidence mismatch")
    return {"rows":n,"weight_sum":weighted,"max_weight":maximum,
            "sampled_exact_source_checks":sampled, "histogram":dict(hist),
            "file_sha256":digest(path),"file_bytes":Path(path).stat().st_size}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--frozen-graph",type=Path,required=True)
    p.add_argument("--private-pair-dir",type=Path,required=True)
    p.add_argument("--private-report",type=Path,required=True)
    a=p.parse_args(argv)
    if a.private_report.exists():
        p.error("Independent report would overwrite")
    if digest(a.frozen_graph)!=GRAPH_SHA256:
        p.error("Original graph SHA changed")
    with zipfile.ZipFile(a.frozen_graph) as z:
        if z.testzip() is not None:
            p.error("Original graph ZIP CRC failed")
        outgoing,incoming=load_graph(z)
    results={}
    for label in EXPECTED:
        path=a.private_pair_dir / f"{label}.pairs.private.jsonl.gz"
        if not path.is_file():
            p.error("Missing private pair-list: "+label)
        results[label]=stream_verify(path,label,outgoing,incoming)
    report={"schema":"pro-adherence-stage3-classical-citation-independent-audit/v1",
            "status":"TECHNICAL_CITATION_PROJECTIONS_PASS_PRIVATE_DRIVE_READBACK_REQUIRED",
            "original_graph_sha256":GRAPH_SHA256,"eligible_nodes":N,
            "restricted_report":True,"no_private_node_ids":True,
            "independent_audit":results,
            "scientific_external_validation_claimed":False}
    with a.private_report.open("x",encoding="utf-8") as f:
        json.dump(report,f,sort_keys=True,ensure_ascii=False,indent=2)
        f.write("\n")
    print(json.dumps({"result":report["status"],
                      "co_citation_pairs":results["co_citation"]["rows"],
                      "coupling_pairs":results["bibliographic_coupling"]["rows"]}))


if __name__=="__main__":
    main()
