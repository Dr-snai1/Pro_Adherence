"""Prepare ONE 1,000-article Stage3 pilot from accepted private frozen inputs.

NO model loading, inference, training, network or cost. Restricted input/output.
Do not commit or publish generated article-level outputs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import zipfile

ARCHIVE_SHA = 'a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127'
COHORT_SHA = 'c080449e4a3450e6ff2e396c0463d05960d8b1cd101f42c7f99ccf3ab202e234'
EDGE_SHA = 'd744feb52524b675bf04a06abef5cb15ff36b6af4397450cb30d553477ab348f'
SOURCE_PRIORITY = ('pubmed', 'woscc', 'apa_psycinfo')
COUNT_ELIGIBLE = 57204
PILOT_COUNT = 1000
SEED = 'stage3-p1-fixed-20261031'


def digest(path: Path) -> str:
    h = sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def gzrows(file):
    with gzip.GzipFile(fileobj=file, mode='rb') as g:
        for line in g:
            if line.strip():
                yield json.loads(line)


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def choose_source(records: list[dict]) -> dict:
    """Whole record, complete before title-only, then PubMed > WoS > APA.

    If an abstract exists without any complete title+abstract record, it is
    unresolved. Never combine fields from different source records.
    """
    if not records:
        return {'text_state': 'missing_input', 'record': None}
    ordered = sorted(records, key=lambda r: (SOURCE_PRIORITY.index(r['source_id']),
                                              r['source_record_id']))
    complete = [r for r in ordered if text(r.get('title')) and text(r.get('abstract'))]
    if complete:
        return {'text_state': 'title_abstract', 'record': complete[0]}
    if any(text(r.get('abstract')) for r in ordered):
        return {'text_state': 'requires_source_resolution', 'record': None}
    titled = [r for r in ordered if text(r.get('title'))]
    if titled:
        return {'text_state': 'title_only', 'record': titled[0]}
    return {'text_state': 'missing_input', 'record': None}


def year_bucket(value):
    if not isinstance(value, str):
        return 'year_unknown'
    m = re.search(r'(?<!\d)(18\d\d|19\d\d|20\d\d)(?!\d)', value)
    if not m:
        return 'year_unknown'
    yr = int(m.group(1))
    if yr < 2000:
        return 'year_pre2000'
    if yr < 2010:
        return 'year_2000s'
    if yr < 2020:
        return 'year_2010s'
    return 'year_2020plus'


def degree_bucket(n):
    return 'degree_zero' if n == 0 else 'degree_1_4' if n <= 4 else 'degree_5_19' if n < 20 else 'degree_20plus'


def strata(row):
    out = [row['text_state'], row['year_bucket'], row['degree_bucket'],
           'source_' + (row['source_id'] or 'none')]
    if row['peer_review_unknown']:
        out.append('flag_peer_review_unknown')
    if row['wos_nr_cr_mismatch']:
        out.append('flag_wos_nr_cr_mismatch')
    # Approximate candidate by character length only; NOT tokenizer evidence.
    if row['long_abstract_candidate']:
        out.append('long_abstract_candidate')
    return out


def rank(article_id: str) -> str:
    return sha256((SEED + ':' + article_id).encode('utf-8')).hexdigest()


def sample(candidates: list[dict], n=PILOT_COUNT, per_stratum=20):
    if len(candidates) < n or len({r['article_id'] for r in candidates}) != len(candidates):
        raise ValueError('not enough distinct canonical article IDs')
    buckets = defaultdict(list)
    for r in candidates:
        for label in strata(r):
            buckets[label].append(r)
    chosen = {}
    # Coverage for rare edge cases. This is a technical pilot, not a population sample.
    for label in sorted(buckets):
        for r in sorted(buckets[label], key=lambda r: (rank(r['article_id']), r['article_id']))[:per_stratum]:
            if len(chosen) >= n:
                break
            chosen[r['article_id']] = r
    for r in sorted(candidates, key=lambda r: (rank(r['article_id']), r['article_id'])):
        if len(chosen) >= n:
            break
        chosen[r['article_id']] = r
    assert len(chosen) == n
    return [chosen[k] for k in sorted(chosen)]


def prepare(archive: Path, cohort: Path, graph_edges: Path, out: Path,
            *, verify_inputs=True):
    if out.exists():
        raise ValueError('refuse to overwrite existing private pilot directory')
    if verify_inputs:
        for path, expected in ((archive, ARCHIVE_SHA), (cohort, COHORT_SHA), (graph_edges, EDGE_SHA)):
            if digest(path) != expected:
                raise ValueError('approved frozen private input SHA mismatch: ' + path.name)
    eligible = {}
    with cohort.open('rb') as f:
        for a in gzrows(f):
            if a['primary_eligible']:
                if a['article_id'] in eligible:
                    raise ValueError('duplicate eligible canonical ID')
                eligible[a['article_id']] = {
                    'source_record_ids': set(a['source_record_ids']),
                    'peer_review_unknown': bool(a['peer_review_unknown']),
                    'wos_nr_cr_mismatch': bool(a['wos_nr_cr_mismatch']),
                }
    if verify_inputs and len(eligible) != COUNT_ELIGIBLE:
        raise ValueError('accepted Stage3 eligibility count mismatch')
    degree = Counter()
    with graph_edges.open('rb') as f:
        for edge in gzrows(f):
            a, b = edge['source_article_id'], edge['target_article_id']
            if a not in eligible or b not in eligible or a >= b or edge['weight'] != 1:
                raise ValueError('training graph policy/endpoint mismatch')
            degree[a] += 1
            degree[b] += 1
    if verify_inputs and sum(degree.values()) != 328298 * 2:
        raise ValueError('approved node2vec edge count mismatch')
    member_map = {}
    for a, info in eligible.items():
        for source_id in info['source_record_ids']:
            if source_id in member_map:
                raise ValueError('nonunique source to canonical relation')
            member_map[source_id] = a
    sources = defaultdict(list)
    with zipfile.ZipFile(archive) as z:
        if verify_inputs:
            m = json.load(z.open('manifest.json'))
            if m['publication_authorized'] is not False or m['source_records'] != 87511:
                raise ValueError('frozen ZIP embedded manifest policy mismatch')
        with z.open('source_records.jsonl.gz') as raw:
            for r in gzrows(raw):
                aid = member_map.get(r['source_record_id'])
                if aid is not None:
                    sources[aid].append({
                        'source_record_id': r['source_record_id'],
                        'source_id': r['source_id'],
                        'raw_export_sha256': r['raw_export_sha256'],
                        'raw_record_ordinal': r.get('raw_record_ordinal'),
                        'title': text(r.get('title')),
                        'abstract': text(r.get('abstract')),
                        'year': r.get('year'),
                    })
    candidates = []
    for article_id, info in eligible.items():
        observed = sources.get(article_id, [])
        if set(r['source_record_id'] for r in observed) != info['source_record_ids']:
            raise ValueError('source provenance incomplete for eligible article')
        selection = choose_source(observed)
        selected = selection['record']
        state = selection['text_state']
        abstract = selected['abstract'] if selected and state == 'title_abstract' else None
        title = selected['title'] if selected else None
        candidates.append({
            'article_id': article_id,
            'source_record_id': selected['source_record_id'] if selected else None,
            'source_id': selected['source_id'] if selected else None,
            'raw_export_sha256': selected['raw_export_sha256'] if selected else None,
            'raw_record_ordinal': selected['raw_record_ordinal'] if selected else None,
            'text_state': state,
            'title': title,
            'abstract': abstract,
            'year_raw': selected['year'] if selected else None,
            'year_bucket': year_bucket(selected['year'] if selected else None),
            'citation_degree': degree[article_id],
            'degree_bucket': degree_bucket(degree[article_id]),
            'peer_review_unknown': info['peer_review_unknown'],
            'wos_nr_cr_mismatch': info['wos_nr_cr_mismatch'],
            'long_abstract_candidate': bool(abstract and len(abstract) >= 2500),
            # Token counts, fragmenting and truncation must use exact model tokenizers later.
            'token_length_measured': False,
        })
    selected = sample(candidates)
    out.mkdir(mode=0o700, parents=True)
    os.chmod(out, 0o700)
    name = 'pilot_1000_inputs.private.jsonl.gz'
    with (out/name).open('xb') as f:
        with gzip.GzipFile(filename='', fileobj=f, mode='wb', mtime=0, compresslevel=6) as gz:
            for item in selected:
                gz.write((json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode('utf-8'))
    def census(seq):
        return {
            'text_state': dict(sorted(Counter(r['text_state'] for r in seq).items())),
            'chosen_source': dict(sorted(Counter(r['source_id'] or 'none' for r in seq).items())),
            'degree_bucket': dict(sorted(Counter(r['degree_bucket'] for r in seq).items())),
            'year_bucket': dict(sorted(Counter(r['year_bucket'] for r in seq).items())),
            'peer_review_unknown': sum(r['peer_review_unknown'] for r in seq),
            'wos_nr_cr_mismatch': sum(r['wos_nr_cr_mismatch'] for r in seq),
            'long_abstract_candidate': sum(r['long_abstract_candidate'] for r in seq),
        }
    manifest = {
        'schema': 'pro-adherence-stage3-p1-private-inputs/v1',
        'status': 'INPUTS_PREPARED_NO_MODEL_RUN',
        'owner_approved_population': len(eligible),
        'pilot_selected': len(selected),
        'sampling': {'method': 'seeded hash with up to 20 per diagnostic stratum, fill by seeded hash; technical not representative',
                     'seed': SEED},
        'source_priority': list(SOURCE_PRIORITY),
        'complete_text_first': True,
        'no_cross_source_title_abstract_merge': True,
        'tokenization_not_run': True,
        'full_eligible_diagnostics': census(candidates),
        'pilot_diagnostics': census(selected),
        'approved_private_sources': {'stage2_archive_sha256': ARCHIVE_SHA,
                                    'stage3_eligibility_sha256': COHORT_SHA,
                                    'node2vec_training_edges_sha256': EDGE_SHA},
        'outputs': {name: {'sha256': digest(out/name), 'bytes': (out/name).stat().st_size, 'rows': len(selected)}},
        'weights_downloaded': False,
        'model_inference_executed': False,
        'node2vec_training_executed': False,
        'pilot_compute_authorized': False,
        'publication_authorized': False,
    }
    dest = out/'pilot_1000_manifest.private.json'
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)+'\n',encoding='utf-8')
    os.chmod(dest, 0o600)
    return {'manifest': manifest, 'manifest_sha256': digest(dest)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--training-edges', type=Path, required=True)
    p.add_argument('--private-output-dir', type=Path, required=True)
    p.add_argument('--prepare-private-inputs', action='store_true')
    args=p.parse_args()
    if not args.prepare_private_inputs:
        p.error('explicit --prepare-private-inputs required')
    result=prepare(args.archive,args.cohort,args.training_edges,args.private_output_dir)
    m=result['manifest']
    print(json.dumps({'status': m['status'], 'pilot_selected': m['pilot_selected'],
                      'diagnostics':m['pilot_diagnostics'],
                      'manifest_sha256':result['manifest_sha256'],
                      'pilot_input_sha256':m['outputs']['pilot_1000_inputs.private.jsonl.gz']['sha256'],
                      'no_inference':True},sort_keys=True))

if __name__=='__main__':
    main()
