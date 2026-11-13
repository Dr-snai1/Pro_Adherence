"""Private-only independent read-only QA for immutable Stage 3 shard block 009-013.

No model import or private row-level output. Can audit a subset as shards finish.
"""
from __future__ import annotations
import argparse, hashlib, gzip, io, json, zipfile
from pathlib import Path
from collections import Counter
import numpy as np
ROOT=Path('/mnt/data')
EXPECTED_INPUT='cc60cefdaa62a60712425b0f1ea1719338ec4250ec8bcaf1fd465329c677395e'
EXPECTED_MEMBER='1611f07e18ccf999493938e552d1a73ad049db931a11399fc01f0ca7b07dc053'
EXPECTED_BASE='801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc'
EXPECTED_ADAPTER='5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'
EXPECTED_RUNTIME='1ee689fd2f10449745f23fb2fa63985d44d55f293ba05dd37a701b3bbb15574a'
SOURCE_ZIP=ROOT/'STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_INPUTS.zip'
SHARDS=ROOT/'stage3_specter2_full_private'

def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def bytes_sha(b):return hashlib.sha256(b).hexdigest()

def source_rows():
    assert sha(SOURCE_ZIP)==EXPECTED_INPUT
    with zipfile.ZipFile(SOURCE_ZIP) as z:
        assert z.testzip() is None
        blob=z.read('full_pubmedbert_inputs.private.jsonl.gz')
        assert bytes_sha(blob)==EXPECTED_MEMBER
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as f:rows=[json.loads(l) for l in f]
    assert len(rows)==57204 and len({r['article_id'] for r in rows})==57204
    return rows

def audit_index(i, rows):
    f=SHARDS/f'STAGE3_20261113_SPECTER2_FULL_SHARD_{i:03d}.zip'
    assert f.is_file() and not f.is_symlink()
    digest=sha(f)
    with zipfile.ZipFile(f) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('manifest.private.json'))
        report=json.loads(z.read('report.private.json'))
        assert manifest['shard_index']==i and manifest['global_start']==1000*i and manifest['count']==1000
        assert manifest['cohort']==57204 and manifest['dimension']==768
        assert manifest['input_zip_sha256']==EXPECTED_INPUT
        assert manifest['base_weight_sha256']==EXPECTED_BASE and manifest['adapter_weight_sha256']==EXPECTED_ADAPTER
        assert manifest['runtime_wheel_sha256']==EXPECTED_RUNTIME
        assert report['rows']==1000 and report['approved_full_input_zip_sha256']==EXPECTED_INPUT
        for name,r in manifest['files'].items():
            b=z.read(name)
            assert bytes_sha(b)==r['sha256'] and len(b)==r['bytes'],name
        raw=np.load(io.BytesIO(z.read('raw.float32.npy')),allow_pickle=False)
        norm=np.load(io.BytesIO(z.read('raw_l2_norm.float64.npy')),allow_pickle=False)
        unit=np.load(io.BytesIO(z.read('unit.float32.npy')),allow_pickle=False)
        assert raw.shape==(1000,768) and raw.dtype==np.float32
        assert norm.shape==(1000,) and norm.dtype==np.float64
        assert unit.shape==(1000,768) and unit.dtype==np.float32
        assert np.isfinite(raw).all() and np.isfinite(norm).all() and np.isfinite(unit).all()
        assert (norm>0).all()
        assert np.allclose(np.linalg.norm(raw.astype('float64'),axis=1),norm,rtol=1e-5,atol=1e-6)
        assert np.allclose(np.linalg.norm(unit.astype('float64'),axis=1),1,rtol=0,atol=1e-5)
        assert np.allclose(unit.astype('float64')*norm[:,None],raw.astype('float64'),rtol=3e-6,atol=3e-6)
        with gzip.GzipFile(fileobj=io.BytesIO(z.read('status.private.jsonl.gz'))) as g:
            status=[json.loads(s) for s in g]
        assert len(status)==1000
        sources=Counter();trunc=0;lost=0;title_only=0
        for j,(record,src) in enumerate(zip(status,rows[1000*i:1000*(i+1)])):
            assert record['canonical_article_id']==src['article_id']
            assert record['vector_row_global']==1000*i+j and record['vector_row_in_shard']==j
            assert record['source_id']==src['source_id'] and record['source_record_id']==src['source_record_id']
            assert record['raw_export_sha256']==src['raw_export_sha256']
            assert record['raw_record_ordinal']==src['raw_record_ordinal']
            assert record['text_state']==src['text_state']
            assert record['title_only']==(src['text_state']=='title_only')
            assert record['text_sha256']==bytes_sha((src['title']+'[SEP]'+(src.get('abstract') or '')).encode('utf-8'))
            assert record['status']=='ready'
            assert record['encoded_tokens']==min(record['untruncated_tokens'],512)
            assert record['tokens_lost']==max(0,record['untruncated_tokens']-512)
            assert record['untruncated_tokens']>=2
            sources[record['source_id']]+=1
            trunc+=record['tokens_lost']>0
            lost+=record['tokens_lost']
            title_only+=record['title_only']
        assert report['truncated_rows']==trunc and report['lost_tokens']==lost
        assert report['title_only_rows']==title_only and report['source_counts']==dict(sources)
        assert report['full_57204_cohort_complete'] is False and report['publication_authorized'] is False
        return {'index':i,'count':1000,'size_bytes':f.stat().st_size,'sha256':digest,'truncated_rows':trunc,
                'tokens_lost':lost,'title_only_rows':title_only,
                'max_unit_l2_deviation':float(np.abs(np.linalg.norm(unit.astype('float64'),axis=1)-1).max()),
                'independent_source_text_numeric_SHA_CRC_PASS':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=9);p.add_argument('--stop',type=int,default=13)
    args=p.parse_args()
    assert 9<=args.start<=args.stop<=13
    rows=source_rows()
    results=[audit_index(i,rows) for i in range(args.start,args.stop+1)]
    print(json.dumps({'status':'PRIVATE_PARTIAL_STAGE3_INDEPENDENT_PASS','start':args.start,'stop':args.stop,
                     'verified_rows':sum(x['count'] for x in results),'shards':results},sort_keys=True))
