#!/usr/bin/env python3
"""Stage 3 private direct-citation diagnostics; PUBLIC CODE, NO CORPUS.

Input is the frozen original *directed* Stage3 exact-DOI citation graph. One
unique eligible non-self source->target is one directed edge; observation_count
and raw source evidence are separately audited but NEVER used as extra edges.
Node-level citation ranks are corpus-internal observations, NOT general impact.
The analysis is a diagnostic, not acceptance of a new scientific lens.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import zipfile

FROZEN_GRAPH_SHA = '33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c'
FROZEN_STAGE2_SHA = 'a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127'
EXPECTED = {'directed_all': 328383, 'excluded_edges': 47,
            'self_edges': 29, 'directed_eligible': 328307,
            'evidence_all': 406811, 'evidence_excluded': 50, 'evidence_self': 32}
GRAPH_MEMBERS = ('node2vec_node_mapping.private.jsonl.gz',
                 'directed_edges.private.jsonl.gz',
                 'directed_citation_evidence.private.jsonl.gz')


def sha256_file(path):
    with Path(path).open('rb') as src:
        return hashlib.file_digest(src, 'sha256').hexdigest()


def member_sha256(z, name):
    digest = hashlib.sha256()
    with z.open(name) as src:
        for data in iter(lambda: src.read(1 << 20), b''):
            digest.update(data)
    return digest.hexdigest()


def rows(z, name):
    with z.open(name) as src, gzip.GzipFile(fileobj=src) as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def ingest_graph(path, *, verify_frozen=True):
    if verify_frozen and sha256_file(path) != FROZEN_GRAPH_SHA:
        raise ValueError('Frozen directed graph SHA256 mismatch')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP CRC mismatch')
        m = json.loads(z.read('node2vec_graph_manifest.private.json'))
        for name in GRAPH_MEMBERS:
            if member_sha256(z, name) != m['outputs'][name]['sha256']:
                raise ValueError('Member SHA256 mismatch: ' + name)
        n = m['eligible_count']
        idx = {}
        ids = [None] * n
        for row in rows(z, GRAPH_MEMBERS[0]):
            i, art = row['node_index'], row['article_id']
            if type(i) is not int or not (0 <= i < n) or ids[i] is not None or art in idx:
                raise ValueError('Invalid, repeated or out-of-range mapping')
            ids[i] = art
            idx[art] = i
        if len(idx) != n or any(v is None for v in ids):
            raise ValueError('Incomplete eligible node map')
        adj = [[] for _ in ids]
        rev = [[] for _ in ids]
        expected_obs = {}
        counts = Counter()
        for row in rows(z, GRAPH_MEMBERS[1]):
            counts['directed_all'] += 1
            s_id, t_id = row['source_article_id'], row['target_article_id']
            if row['weight'] != 1 or type(row['observation_count']) is not int or row['observation_count'] < 1:
                raise ValueError('Graph edge semantics changed')
            key = (s_id, t_id)
            if key in expected_obs:
                raise ValueError('Duplicate directed edge')
            expected_obs[key] = row['observation_count']
            s, t = idx.get(s_id), idx.get(t_id)
            if s is None or t is None:
                counts['excluded_edges'] += 1
            elif s == t:
                counts['self_edges'] += 1
            else:
                adj[s].append(t)
                rev[t].append(s)
                counts['directed_eligible'] += 1
        edge_observations = Counter()
        source_stats = defaultdict(Counter)
        source_masks = {}
        source_per_pair = defaultdict(set)
        for row in rows(z, GRAPH_MEMBERS[2]):
            counts['evidence_all'] += 1
            key = (row['source_article_id'], row['target_article_id'])
            if key not in expected_obs:
                raise ValueError('Evidence for missing graph edge')
            source = row['source_record_id'].split(':', 1)[0]
            if source not in ('pubmed', 'woscc'):
                raise ValueError('Unexpected exact-DOI source evidence: ' + source)
            edge_observations[key] += 1
            source_stats[source]['evidence_all'] += 1
            s, t = idx.get(key[0]), idx.get(key[1])
            if s is None or t is None:
                counts['evidence_excluded'] += 1
                source_stats[source]['evidence_excluded'] += 1
            elif s == t:
                counts['evidence_self'] += 1
                source_stats[source]['evidence_self'] += 1
            else:
                source_stats[source]['evidence_eligible'] += 1
                source_per_pair[(s, t)].add(source)
                source_masks[(s, t)] = source_masks.get((s, t), 0) | (1 if source == 'pubmed' else 2)
        if len(edge_observations) != len(expected_obs) or edge_observations != expected_obs:
            raise ValueError('Original edge observation_count did not replay from full evidence')
        for key in EXPECTED:
            if verify_frozen and counts[key] != EXPECTED[key]:
                raise ValueError(f'Frozen {key} changed: {counts[key]} != {EXPECTED[key]}')
        if verify_frozen and n != 57204:
            raise ValueError('Unexpected frozen cohort')
        if sum(map(len, adj)) != counts['directed_eligible'] or sum(map(len, rev)) != counts['directed_eligible']:
            raise AssertionError('Adjacency degree census mismatch')
        for a in adj:
            a.sort()
        for a in rev:
            a.sort()
        for (s, t), names in source_per_pair.items():
            for source in names:
                source_stats[source]['unique_eligible_edges'] += 1
        source_stats = {source: dict(sorted(stats.items())) for source, stats in sorted(source_stats.items())}
        by_mask = Counter(source_masks.values())
        if sum(by_mask.values()) != counts['directed_eligible']:
            raise AssertionError('An eligible edge has no source evidence')
        return ids, adj, rev, {
            'counts': dict(sorted(counts.items())),
            'source_evidence': source_stats,
            'eligible_edge_source_sets': {'pubmed_only': by_mask[1], 'woscc_only': by_mask[2],
                                          'both_sources': by_mask[3]},
            'graph_member_sha256': {name: m['outputs'][name]['sha256'] for name in GRAPH_MEMBERS},
        }


def weak_components(adj, rev):
    n = len(adj)
    parent = list(range(n))
    size = [1] * n

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for s, targets in enumerate(adj):
        for t in targets:
            a, b = find(s), find(t)
            if a != b:
                if size[a] < size[b]:
                    a, b = b, a
                parent[b] = a
                size[a] += size[b]
    comps = defaultdict(list)
    for i in range(n):
        comps[find(i)].append(i)
    return canonical_components(list(comps.values()), n)


def strong_components(adj, rev):
    """Iterative Kosaraju; no recursion depth or non-stdlib graph dependencies."""
    n = len(adj)
    marked = bytearray(n)
    finish = []
    for root in range(n):
        if marked[root]:
            continue
        marked[root] = 1
        stack = [(root, 0)]
        while stack:
            u, next_idx = stack[-1]
            if next_idx < len(adj[u]):
                v = adj[u][next_idx]
                stack[-1] = (u, next_idx + 1)
                if not marked[v]:
                    marked[v] = 1
                    stack.append((v, 0))
            else:
                finish.append(u)
                stack.pop()
    marked = bytearray(n)
    comps = []
    for root in reversed(finish):
        if marked[root]:
            continue
        marked[root] = 1
        comp, stack = [], [root]
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in rev[u]:
                if not marked[v]:
                    marked[v] = 1
                    stack.append(v)
        comps.append(comp)
    return canonical_components(comps, n)


def canonical_components(comps, n):
    comps.sort(key=lambda comp: (-len(comp), min(comp)))
    membership = [-1] * n
    sizes = []
    for ci, comp in enumerate(comps):
        sizes.append(len(comp))
        for u in comp:
            if membership[u] != -1:
                raise ValueError('Overlapping components')
            membership[u] = ci
    if sum(sizes) != n or -1 in membership:
        raise ValueError('Component partition not a census')
    return membership, sizes


def pagerank(adj, damping=0.85, tolerance=1e-12, max_iterations=300):
    """Corpus-internal uniform-teleport PageRank, dangling mass redistributed."""
    n = len(adj)
    if n == 0 or not (0 < damping < 1):
        raise ValueError('Invalid PageRank input')
    old = [1.0 / n] * n
    nonzero = [(i, len(a)) for i, a in enumerate(adj) if a]
    dangling = [i for i, a in enumerate(adj) if not a]
    trace = []
    for iteration in range(1, max_iterations + 1):
        base = (1.0 - damping + damping * math.fsum(old[i] for i in dangling)) / n
        new = [base] * n
        for i, deg in nonzero:
            contribution = damping * old[i] / deg
            for j in adj[i]:
                new[j] += contribution
        residual = math.fsum(abs(new[i] - old[i]) for i in range(n))
        trace.append(residual)
        old = new
        if residual < tolerance:
            return old, {'damping': damping, 'tolerance_l1': tolerance,
                         'iterations': iteration, 'last_l1_residual': residual,
                         'mass_sum': math.fsum(old), 'converged': True}
    raise ValueError(f'PageRank failed convergence in {max_iterations} iterations; residual {trace[-1]}')


def percentile(values, pct):
    s = sorted(values)
    return s[min(len(s) - 1, int(math.ceil(pct * len(s))) - 1)]


def summarize_nodes(ids, adj, rev, lineage):
    n = len(ids)
    w_index, w_sizes = weak_components(adj, rev)
    s_index, s_sizes = strong_components(adj, rev)
    prs, pr_info = pagerank(adj)
    indeg = list(map(len, rev))
    outdeg = list(map(len, adj))
    isolated = sum(a == 0 and b == 0 for a, b in zip(indeg, outdeg))
    reciprocal = sum(1 for i, a in enumerate(adj) for j in a if i < j and i in adj[j])
    cyclic_node_count = sum(s for s in s_sizes if s > 1)
    internal_scc_edges = sum(1 for i, a in enumerate(adj) for j in a if s_index[i] == s_index[j] and s_sizes[s_index[i]] > 1)
    if sum(indeg) != sum(outdeg):
        raise ValueError('Directed handshake mismatch')
    def rank(degrees=None, pr=False, limit=100):
        keys = sorted(range(n), key=(lambda i: (-prs[i], ids[i])) if pr else
                      (lambda i: (-degrees[i], ids[i])))[:limit]
        return [{'rank': r, 'node_index': i, 'article_id': ids[i],
                 'in_degree': indeg[i], 'out_degree': outdeg[i],
                 'pagerank': prs[i], 'weak_component': w_index[i]}
                for r, i in enumerate(keys, 1)]
    summary = {
        'semantics': 'source article -> target article; one unique exact-DOI directed eligible nonself pair; source-observations are NOT repeated edges',
        'scope': 'Stage3 57204 eligible articles; within-corpus observed references ONLY; rankings are diagnostic, not global citation impact',
        'eligible_nodes': n, 'unique_directed_edges': sum(indeg),
        'in_degree_sum': sum(indeg), 'out_degree_sum': sum(outdeg),
        'nonzero_in_degree_nodes': sum(v > 0 for v in indeg),
        'nonzero_out_degree_nodes': sum(v > 0 for v in outdeg),
        'both_in_and_out': sum(a > 0 and b > 0 for a, b in zip(indeg, outdeg)),
        'either_in_or_out': n - isolated,
        'isolated_nodes': isolated,
        'reciprocal_unique_pairs': reciprocal,
        'edge_density_directed_no_loops': sum(indeg) / (n * (n - 1)),
        'in_degree': {'max': max(indeg), 'quantiles': {str(p): percentile(indeg, p/100) for p in (50, 90, 95, 99)},
                      'degree_ge_10': sum(x >= 10 for x in indeg),
                      'degree_ge_100': sum(x >= 100 for x in indeg)},
        'out_degree': {'max': max(outdeg), 'quantiles': {str(p): percentile(outdeg, p/100) for p in (50, 90, 95, 99)},
                       'degree_ge_10': sum(x >= 10 for x in outdeg),
                       'degree_ge_100': sum(x >= 100 for x in outdeg)},
        'weak_components': {'total': len(w_sizes), 'largest': w_sizes[0], 'singletons': sum(x == 1 for x in w_sizes),
                            'largest_sizes_top20': w_sizes[:20]},
        'strong_components': {'total': len(s_sizes), 'largest': s_sizes[0], 'singletons': sum(x == 1 for x in s_sizes),
                              'nontrivial': sum(x > 1 for x in s_sizes), 'cyclic_nodes': cyclic_node_count,
                              'internal_edges_in_nontrivial_scc': internal_scc_edges,
                              'largest_sizes_top20': s_sizes[:20]},
        'pagerank': pr_info,
        'source_lineage': lineage,
        'caveats': [
            'Exact-DOI eligible in-corpus citations only; absent edge is NOT zero real-world citations.',
            'APA reference lists not exposed in source corpus; PubMed/WoS evidence cannot be treated as equivalent coverage.',
            'No authors, schools, scientific topics or clinical conclusions inferred from these degree or rank scores.',
            'PageRank uses explicitly specified 0.85 teleport parameter only as descriptive sensitivity baseline; not scientific acceptance.',
            'Observed source evidence multiplicity is separated from unique directed citation edges.'
        ],
    }
    ranks = {'by_indegree_top100': rank(indeg), 'by_outdegree_top100': rank(outdeg),
             'by_pagerank_top100': rank(pr=True)}
    metrics = ({'article_id': ids[i], 'node_index': i, 'in_degree': indeg[i],
                'out_degree': outdeg[i], 'pagerank': prs[i],
                'weak_component': w_index[i], 'weak_component_size': w_sizes[w_index[i]],
                'strong_component': s_index[i], 'strong_component_size': s_sizes[s_index[i]]}
               for i in range(n))
    return summary, ranks, metrics


def save_json(path, data):
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, sort_keys=True, ensure_ascii=False, indent=2)
        f.write('\n')
    return {'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}


def save_node_gzip(path, metrics):
    count = in_total = out_total = 0
    with path.open('xb') as out, gzip.GzipFile(filename='', mode='wb', fileobj=out, compresslevel=6, mtime=0) as zipped:
        for row in metrics:
            zipped.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode())
            count += 1
            in_total += row['in_degree']
            out_total += row['out_degree']
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        # This replay independently reads entire compressed output incl. gzip CRC.
        replay_count = 0
        for line in f:
            x = json.loads(line)
            if x['node_index'] != replay_count:
                raise AssertionError('Noncontiguous saved node metrics')
            replay_count += 1
    if replay_count != count or in_total != out_total:
        raise AssertionError('Node gzip replay or degree conservation failed')
    return {'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha256_file(path),
            'rows': count, 'in_degree_sum': in_total, 'out_degree_sum': out_total}


def enrich_rankings_from_frozen_stage2(rankings, stage2_path):
    if sha256_file(stage2_path) != FROZEN_STAGE2_SHA:
        raise ValueError('Optional frozen Stage2 input SHA256 mismatch')
    interested = {r['article_id'] for name in rankings for r in rankings[name]}
    found = {}
    with zipfile.ZipFile(stage2_path) as z:
        if z.testzip() is not None:
            raise ValueError('Stage2 ZIP CRC mismatch')
        for row in rows(z, 'canonical_articles.jsonl.gz'):
            aid = row['canonical_article_id']
            if aid in interested:
                found[aid] = {'doi': row.get('doi'), 'pmid': row.get('pmid'),
                              'source_ids': row.get('source_ids')}
    if len(found) != len(interested):
        raise ValueError('Ranked eligible node missing from frozen canonical roster')
    for entries in rankings.values():
        for entry in entries:
            entry['canonical_frozen_identifiers'] = found[entry['article_id']]
    return {'stage2_zip_sha256': FROZEN_STAGE2_SHA, 'ranked_articles_enriched': len(found),
            'stage2_canonical_member': 'canonical_articles.jsonl.gz'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph-zip', required=True, type=Path)
    p.add_argument('--stage2-zip', type=Path, help='Optional frozen Stage2 metadata ONLY for top100 DOI/PMID enrichment')
    p.add_argument('--private-output-dir', required=True, type=Path)
    p.add_argument('--explicit-private-research-run', action='store_true')
    args = p.parse_args(argv)
    if not args.explicit_private_research_run:
        p.error('Private restricted research execution must be explicit')
    if args.private_output_dir.exists() and any(args.private_output_dir.iterdir()):
        p.error('Output directory must be empty; never overwrite an existing research result')
    ids, adj, rev, lineage = ingest_graph(args.graph_zip)
    summary, rankings, metrics = summarize_nodes(ids, adj, rev, lineage)
    if args.stage2_zip:
        summary['ranking_identifier_enrichment'] = enrich_rankings_from_frozen_stage2(rankings, args.stage2_zip)
    args.private_output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(args.private_output_dir, 0o700)
    files = {}
    files['nodes'] = save_node_gzip(args.private_output_dir / 'direct_citation_nodes.private.jsonl.gz', metrics)
    files['rankings'] = save_json(args.private_output_dir / 'direct_citation_rankings.private.json', rankings)
    files['summary'] = save_json(args.private_output_dir / 'direct_citation_summary.private.json', summary)
    manifest = {
        'schema': 'pro-adherence-stage3-direct-citation-diagnostic/v1',
        'status': 'LOCAL_RESEARCH_RESULT_REQUIRES_RESTRICTED_DRIVE_REMOTE_READBACK',
        'frozen_graph_drive_id': '1NysRCVbYlEAbW2FPXfdanKueaGjvYPsm',
        'input_graph_sha256': FROZEN_GRAPH_SHA,
        'input_stage2_sha256': FROZEN_STAGE2_SHA if args.stage2_zip else None,
        'analysis': 'full eligible original directed exact-DOI citation graph, diagnostic only',
        'pagerank': summary['pagerank'], 'counts': lineage['counts'],
        'files': files, 'private': True, 'publication_authorized': False,
        'stage_gate_authorized': False, 'scientific_validation_claimed': False,
        'runtime': {'python': platform.python_version()}, 'code_sha256': sha256_file(Path(__file__)),
    }
    files['manifest'] = save_json(args.private_output_dir / 'direct_citation_manifest.private.json', manifest)
    print(json.dumps({'status': manifest['status'], 'summary': summary,
                      'files': files}, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
