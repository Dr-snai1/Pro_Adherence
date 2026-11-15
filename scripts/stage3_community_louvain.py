#!/usr/bin/env python3
"""Stage3 private exploratory Louvain on frozen citation projections.

PUBLIC source-free code. Input corpora and all article assignments remain PRIVATE.
No Leiden is claimed. This run compares *community detection procedures*, not
scientifically verified topics or author communities. Frozen directed citation
edges are read only to check lineage of the already accepted binary projection.

Primary graphs:
 * direct_undirected_binary: frozen node2vec training *graph* (not embedding);
   each observed eligible directed exact-DOI edge counted once per unordered pair.
 * co_citation_weighted: frozen 18-part PAC1 asset; original integer weights.
No threshold/pruning, no self-loops. Structural isolates are null, not topics.
"""
from __future__ import annotations
import argparse
import base64
from collections import Counter
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import sys
import time
import zipfile

import networkx as nx
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

N = 57204
GRAPH_SHA = '33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c'
CO_SHA = '6fb952d2c3f5e3e955cec517902b777b45ae185c2d48ef312ac22f8f280c3fec'
CO_BYTES = 5147675
EXPECTED_DIRECT = 328298
EXPECTED_CO = (2055149, 2891776)
RUNS = [(0.75, 20261031), (1.0, 20261031), (1.25, 20261031), (1.0, 20261032)]


def digest(path):
    with Path(path).open('rb') as h:
        return hashlib.file_digest(h, 'sha256').hexdigest()


def jsonl_gz(z, member):
    with z.open(member) as f, gzip.GzipFile(fileobj=f) as gz:
        for raw in gz:
            if raw.strip():
                yield json.loads(raw)


def direct_edges(path):
    if digest(path) != GRAPH_SHA:
        raise ValueError('Frozen graph SHA mismatch')
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None, 'Frozen graph ZIP CRC'
        m = json.loads(z.read('node2vec_graph_manifest.private.json'))
        assert m['eligible_count'] == N and m['node2vec_training_edge_count'] == EXPECTED_DIRECT
        a2i, ids = {}, [None] * N
        for row in jsonl_gz(z, 'node2vec_node_mapping.private.jsonl.gz'):
            art, i = row['article_id'], row['node_index']
            if type(i) is not int or not 0 <= i < N or ids[i] is not None or art in a2i:
                raise ValueError('Corrupted frozen mapping')
            ids[i] = art
            a2i[art] = i
        if len(a2i) != N or any(x is None for x in ids):
            raise ValueError('Incomplete canonical eligible roster')
        pairs = set()
        for row in jsonl_gz(z, 'node2vec_training_edges.private.jsonl.gz'):
            a = a2i[row['source_article_id']]
            b = a2i[row['target_article_id']]
            if a == b or row['weight'] != 1:
                raise ValueError('Frozen training graph not binary nonloop')
            x, y = sorted((a, b))
            if (x, y) in pairs:
                raise ValueError('Repeated undirected pair')
            pairs.add((x, y))
        if len(pairs) != EXPECTED_DIRECT:
            raise ValueError('Frozen projection edge census mismatch')
        observed = set()
        directed_total = eligible = selfloop = excluded = 0
        for row in jsonl_gz(z, 'directed_edges.private.jsonl.gz'):
            directed_total += 1
            a = a2i.get(row['source_article_id'])
            b = a2i.get(row['target_article_id'])
            if a is None or b is None:
                excluded += 1
            elif a == b:
                selfloop += 1
            else:
                eligible += 1
                observed.add(tuple(sorted((a, b))))
        if (directed_total, eligible, excluded, selfloop) != (328383,328307,47,29):
            raise ValueError('Directed original edge counts did not replay')
        if pairs != observed:
            raise ValueError('Binary graph not exactly the projection of original directed links')
        return ids, sorted((a, b, 1) for a, b in pairs), {
            'original_directed': directed_total,
            'eligible_directed': eligible,
            'excluded_endpoints': excluded,
            'eligible_selfloops': selfloop,
            'projection_edges': len(pairs),
            'input_graph_sha256': GRAPH_SHA,
            'projection_crosscheck_original_directed': 'PASS_EXACT_PAIR_SET',
        }


def read_uleb(buffer, p):
    value, shift = 0, 0
    for _ in range(8):
        if p >= len(buffer):
            raise ValueError('Truncated PAC1 record')
        x = buffer[p]
        p += 1
        value |= (x & 127) << shift
        if not x & 128:
            return value, p
        shift += 7
    raise ValueError('Oversized PAC1 unsigned integer')


def decode_pac1(blob):
    if len(blob) < 16 or blob[:4] != b'PAC1':
        raise ValueError('PAC1 header missing')
    n, expected_pairs, expected_incidences = struct.unpack_from('<III', blob, 4)
    if n != N:
        raise ValueError('PAC1 frozen cohort mismatch')
    p, last_key = 16, -1
    weights, pairs = 0, []
    while p < len(blob):
        delta, p = read_uleb(blob, p)
        w, p = read_uleb(blob, p)
        last_key += delta
        a, b = divmod(last_key, N)
        if delta < 1 or not 0 <= a < b < N or w < 1:
            raise ValueError('Invalid/noncanonical PAC1 pair')
        pairs.append((a, b, w))
        weights += w
    if (len(pairs), weights) != (expected_pairs, expected_incidences):
        raise ValueError('PAC1 pair/weight census mismatch')
    return pairs, weights


def cocitation_edges(folder):
    import glob
    files = sorted(Path(folder).glob('STAGE3_PRIVATE_PAC1_COCITATION_part*of018.b64.txt'))
    if len(files) != 18:
        raise ValueError('Missing PAC1 co-citation transport parts')
    blob_parts = []
    for i, file in enumerate(files, 1):
        if f'part{i:03d}of018' not in file.name:
            raise ValueError('PAC1 transport order mismatch')
        raw = file.read_bytes().removeprefix(b'\xef\xbb\xbf').strip()
        blob_parts.append(base64.b64decode(raw, validate=True))
    blob = b''.join(blob_parts)
    if len(blob) != CO_BYTES or hashlib.sha256(blob).hexdigest() != CO_SHA:
        raise ValueError('Frozen complete co-citation PAC1 SHA256 mismatch')
    pairs, weight_sum = decode_pac1(blob)
    if (len(pairs), weight_sum) != EXPECTED_CO:
        raise ValueError('Frozen accepted co-citation totals mismatch')
    return pairs, {'input_pac1_sha256': CO_SHA,
                   'pac1_bytes': CO_BYTES, 'transport_parts':len(files),
                   'unique_weighted_pairs':len(pairs), 'weighted_incidences':weight_sum}


def make_graph(edges, n=N):
    graph=nx.Graph()
    graph.add_weighted_edges_from(edges)
    if graph.number_of_edges()!=len(edges):
        raise ValueError('Collapsed input graph edges')
    if graph.number_of_nodes()>n:
        raise ValueError('More graph nodes than eligible roster')
    return graph


def canonical_membership(communities, active, n=N):
    # Cluster ordering is deterministic; membership IDs are run-local.
    clusters = sorted((sorted(c) for c in communities),key=lambda c:(-len(c),c[0]))
    membership = [-1]*n
    for c, members in enumerate(clusters):
        for node in members:
            if not 0 <= node < n or membership[node] >= 0:
                raise ValueError('Overlapping/out of range community assignment')
            membership[node]=c
    if {i for i,x in enumerate(membership) if x>=0}!=set(active):
        raise ValueError('Community membership does not exactly cover active nodes')
    return membership, [len(c) for c in clusters]


def independent_modularity(edges, membership, resolution, n=N):
    strength=[0]*n
    inside=Counter()
    total_weight=0
    for a,b,w in edges:
        strength[a]+=w; strength[b]+=w; total_weight+=w
        if membership[a]>=0 and membership[a]==membership[b]:
            inside[membership[a]]+=w
    community_strength=Counter()
    for i,w in enumerate(strength):
        if membership[i]>=0:
            community_strength[membership[i]]+=w
    q=sum(inside[c]/total_weight-resolution*(community_strength[c]/(2*total_weight))**2
          for c in community_strength)
    return q, total_weight, sum(inside.values())


def run_louvain(graph,edges,gamma,seed, n=N):
    t=time.monotonic()
    communities=nx.community.louvain_communities(graph,weight='weight',resolution=gamma,seed=seed,threshold=1e-7)
    membership,sizes=canonical_membership(communities,graph.nodes(),n)
    q=nx.community.modularity(graph,communities,weight='weight',resolution=gamma)
    independent,weight_sum,internal=independent_modularity(edges,membership,gamma,n)
    if abs(q-independent)>1e-9:
        raise AssertionError(f'Independent modularity mismatch {q} vs {independent}')
    if sum(sizes)!=graph.number_of_nodes():
        raise AssertionError('Community census discrepancy')
    return membership,{
        'method':'networkx_louvain', 'resolution':gamma, 'seed':seed, 'community_count':len(sizes),
        'active_nodes':graph.number_of_nodes(), 'structural_missing_nodes':n-graph.number_of_nodes(),
        'largest_20':sizes[:20], 'singletons':sum(s==1 for s in sizes),
        'modularity':q, 'independent_modularity':independent,
        'weight_sum':weight_sum, 'internal_weight':internal,
        'internal_weight_fraction':internal/weight_sum, 'runtime_seconds':round(time.monotonic()-t,3),
        'status':'TECHNICAL_DIAGNOSTIC_ONLY',
    }


def sensitivity(memberships,active,runs=RUNS):
    indices=sorted(active)
    labels=[[row[i] for i in indices] for row in memberships]
    pairs=[]
    for i in range(len(labels)):
        for j in range(i+1,len(labels)):
            pairs.append({'left':i,'right':j, 'resolution_left':runs[i][0], 'resolution_right':runs[j][0],
                          'seed_left':runs[i][1], 'seed_right':runs[j][1],
                          'adjusted_rand':float(adjusted_rand_score(labels[i],labels[j])),
                          'normalized_mutual_information':float(normalized_mutual_info_score(labels[i],labels[j]))})
    return pairs


def save_json(path,obj):
    if path.exists():raise FileExistsError(path)
    with path.open('x',encoding='utf-8') as f:
        json.dump(obj,f,sort_keys=True,ensure_ascii=False,indent=2)
        f.write('\n')
    return {'name':path.name,'sha256':digest(path),'bytes':path.stat().st_size}


def save_membership(path,ids,assignments):
    if path.exists():raise FileExistsError(path)
    with path.open('xb') as f, gzip.GzipFile(fileobj=f,filename='',mode='wb',mtime=0,compresslevel=6) as out:
        for i,art in enumerate(ids):
            # Every eligible article gets one row. Isolates are missing_structural/null.
            record={'article_id':art,'node_index':i,'communities':[
                (v[i] if v[i]>=0 else None) for v in assignments]}
            out.write((json.dumps(record,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
    # Full independent serialized replay + gzip checksum.
    rows=0
    with gzip.open(path,'rt',encoding='utf-8') as src:
        for line in src:
            row=json.loads(line)
            if row['node_index']!=rows or row['article_id']!=ids[rows]:
                raise AssertionError('Output readback node mapping mismatch')
            if row['communities']!=[(v[rows] if v[rows]>=0 else None) for v in assignments]:
                raise AssertionError('Output readback membership mismatch')
            rows+=1
    if rows!=len(ids): raise AssertionError('Output readback census mismatch')
    return {'name':path.name,'sha256':digest(path),'bytes':path.stat().st_size,'rows':rows}


def analyze(name,ids,edges,lineage,target):
    graph=make_graph(edges)
    covered=graph.number_of_nodes()
    count=graph.number_of_edges()
    print(f'{name}: graph active={covered}, edges={count}, weight={sum(w for _,_,w in edges)}',flush=True)
    assignments=[]; reports=[]
    for gamma,seed in RUNS:
        assignment,report=run_louvain(graph,edges,gamma,seed)
        assignments.append(assignment);reports.append(report)
        print(f'{name}: resolution={gamma} seed={seed} communities={report["community_count"]} modularity={report["modularity"]:.6f} time={report["runtime_seconds"]}s',flush=True)
    pairs=sensitivity(assignments,graph.nodes())
    output=target/f'{name}.assignments.private.jsonl.gz'
    membership=save_membership(output,ids,assignments)
    summary={'graph':name,'version':'diagnostic-v1','method':'Louvain (networkx); NOT Leiden',
             'source':lineage,'eligible_roster_count':N,
             'unique_pairs':count,'active_nodes':covered,'structural_missing_nodes':N-covered,
             'runs':reports,'stability':pairs,
             'input_policy':'complete frozen graph, no edge threshold/pruning; retain raw weights; undirected projection stated explicitly',
             'interpretive_limits':[
                 'Communities are algorithm and resolution dependent, not independently validated subject taxonomy.',
                 'Citation observation coverage incomplete; missing APA references are not observed zero.',
                 'No identity-disambiguated co-authorship or normalized co-word claims.',
                 'Structural isolates are null across all runs, not singleton discovered topics.',
                 'Resolutions and seeds are exploratory sensitivity choices, not accepted scientific hyperparameters.',
                 'Louvain was run; Leiden was NOT executed because a supported Leiden runtime was unavailable.'
             ]}
    summary_file=save_json(target/f'{name}.summary.private.json',summary)
    return {'assignments':membership,'summary':summary_file},summary


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--frozen-graph',type=Path,required=True)
    parser.add_argument('--co-pac1-parts-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--explicit-private-research-run',action='store_true')
    args=parser.parse_args(argv)
    if not args.explicit_private_research_run:parser.error('Explicit restricted-only run required')
    if args.output_dir.exists() and any(args.output_dir.iterdir()):parser.error('Output folder not empty')
    args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(args.output_dir,0o700)
    started=time.time()
    ids,edges,lineage=direct_edges(args.frozen_graph)
    outputs,infos={},{}
    outputs['direct_binary'],infos['direct_binary']=analyze('direct_binary',ids,edges,lineage,args.output_dir)
    del edges
    co,co_lineage=cocitation_edges(args.co_pac1_parts_dir)
    outputs['co_citation_weighted'],infos['co_citation_weighted']=analyze('co_citation_weighted',ids,co,co_lineage,args.output_dir)
    del co
    manifest={'schema':'pro-adherence-stage3-community-louvain-exploratory/v1',
              'status':'PRIVATE_LOCAL_TECHNICAL_NEEDS_REMOTE_DRIVE_READBACK',
              'no_leiden_executed':True,'frozen_graph_sha256':GRAPH_SHA,
              'frozen_cocitation_pac1_sha256':CO_SHA,'eligible_articles':N,
              'method':'NetworkX Louvain exact input weights and full observed pairs',
              'specifications':{'runs':[{'resolution':v,'seed':s} for v,s in RUNS],
                                'weights':'direct binary vs co-citation retained integer frequencies',
                                'pruning':'none','isolates':'null not clusters'},
              'versions':{'python':platform.python_version(),'networkx':nx.__version__,
                          'sklearn':__import__('sklearn').__version__},
              'code_sha256':digest(Path(__file__)),'outputs':outputs,
              'numerical_self_check':['exact input hashes and pair counts',
                   'full membership replay/gzip CRC','independent modularity formula vs NetworkX'],
              'scientific_acceptance_claimed':False,'release_authorized':False,
              'stage_gate_authorized':False,
              'duration_seconds':round(time.time()-started,1)}
    out=save_json(args.output_dir/'louvain_manifest.private.json',manifest)
    print('COMPLETE',json.dumps({'manifest':out,'runs':sum(len(v['runs']) for v in infos.values())},sort_keys=True),flush=True)

if __name__=='__main__':main()
