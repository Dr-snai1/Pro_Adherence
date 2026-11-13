#!/usr/bin/env python3
"""Independent read-only FULL 57,204 SPECTER2 shard QA (no torch/inference).

Verify canonical identity/source text, 58 shard zip member SHA and CRC,
raw/norm/unit 768D arrays and per-row lost-token accounting. No row-level output.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile
import numpy as np

EXPECTED_ARCHIVE='cc60cefdaa62a60712425b0f1ea1719338ec4250ec8bcaf1fd465329c677395e'
EXPECTED_MEMBER='1611f07e18ccf999493938e552d1a73ad049db931a11399fc01f0ca7b07dc053'
BASE_SHA='801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc'
ADAPTER_SHA='5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'
WHEEL_SHA='1ee689fd2f10449745f23fb2fa63985d44d55f293ba05dd37a701b3bbb15574a'
COHORT,DIM=57204,768

def hash_data(x:bytes)->str:return sha256(x).hexdigest()
def file_sha(p:Path):
    h=sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()

def audit(root:Path,input_zip:Path,output:Path):
    if output.exists():raise ValueError('refuse overwrite independent audit')
    if file_sha(input_zip)!=EXPECTED_ARCHIVE:raise ValueError('frozen full private input archive SHA mismatch')
    with zipfile.ZipFile(input_zip) as z:
        if z.testzip() is not None:raise ValueError('input ZIP CRC failed')
        b=z.read('full_pubmedbert_inputs.private.jsonl.gz')
        if hash_data(b)!=EXPECTED_MEMBER:raise ValueError('input member SHA mismatch')
        with gzip.GzipFile(fileobj=io.BytesIO(b)) as f:rows=[json.loads(line) for line in f]
    if len(rows)!=COHORT or len({r['article_id'] for r in rows})!=COHORT:
        raise ValueError('canonical full eligible cohort uniqueness/count mismatch')
    target=root/'FULL_57204_MANIFEST.private.json'
    if not target.is_file():raise ValueError('no complete production manifest: partial not accepted')
    overall=json.loads(target.read_text())
    if overall['article_count']!=COHORT or overall['dimension']!=DIM or len(overall['shard_files'])!=58:
        raise ValueError('full manifest coverage mismatch')
    if overall['private_source_zip_sha256']!=EXPECTED_ARCHIVE or overall['public_model_base_sha256']!=BASE_SHA or overall['public_proximity_adapter_sha256']!=ADAPTER_SHA:
        raise ValueError('model or input identity mismatch')
    seen=set();source=Counter();state=Counter();totals=Counter();n=0;last=0;verified_files=[]
    global_min_l2=float('inf');global_max_l2=0;max_unit_deviation=0.;max_reconstruction_error=0.
    for ix,entry in enumerate(overall['shard_files']):
        path=root/entry['file']
        if path.is_symlink() or not path.is_file() or file_sha(path)!=entry['sha256'] or path.stat().st_size!=entry['size_bytes']:
            raise ValueError('archive missing/size/digest mismatch shard '+str(ix))
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:raise ValueError('ZIP CRC failed '+str(ix))
            m=json.loads(z.read('manifest.private.json'))
            report=json.loads(z.read('report.private.json'))
            if m['shard_index']!=ix or m['global_start']!=last or m['input_zip_sha256']!=EXPECTED_ARCHIVE or m['base_weight_sha256']!=BASE_SHA or m['adapter_weight_sha256']!=ADAPTER_SHA or m['runtime_wheel_sha256']!=WHEEL_SHA:
                raise ValueError('shard identity mismatch '+str(ix))
            length=m['count']
            if length!=min(1000,COHORT-last) or m['dimension']!=DIM:
                raise ValueError('shard size mismatch '+str(ix))
            for filename,record in m['files'].items():
                blob=z.read(filename)
                if hash_data(blob)!=record['sha256'] or len(blob)!=record['bytes']:
                    raise ValueError('member sha mismatch '+str(ix)+' '+filename)
            raw=np.load(io.BytesIO(z.read('raw.float32.npy')),allow_pickle=False)
            norm=np.load(io.BytesIO(z.read('raw_l2_norm.float64.npy')),allow_pickle=False)
            unit=np.load(io.BytesIO(z.read('unit.float32.npy')),allow_pickle=False)
            if raw.dtype!=np.float32 or unit.dtype!=np.float32 or norm.dtype!=np.float64 or raw.shape!=(length,DIM) or unit.shape!=(length,DIM) or norm.shape!=(length,):
                raise ValueError('vector shape/dtype mismatch '+str(ix))
            if not np.isfinite(raw).all() or not np.isfinite(unit).all() or not np.isfinite(norm).all() or not np.all(norm>0):
                raise ValueError('vector finite/norm mismatch '+str(ix))
            true_norm=np.linalg.norm(raw.astype(np.float64),axis=1)
            if not np.allclose(true_norm,norm,rtol=1e-5,atol=1e-6):
                raise ValueError('norm computed from raw mismatch '+str(ix))
            deviation=float(np.abs(np.linalg.norm(unit.astype(np.float64),axis=1)-1).max())
            err=float(np.abs(unit.astype(np.float64)*norm[:,None]-raw.astype(np.float64)).max())
            if deviation>1e-5 or not np.allclose(unit.astype(np.float64)*norm[:,None],raw.astype(np.float64),atol=3e-6,rtol=3e-6):
                raise ValueError('unit vector or raw reconstruction mismatch '+str(ix))
            global_min_l2=min(global_min_l2,float(norm.min()));global_max_l2=max(global_max_l2,float(norm.max()))
            max_unit_deviation=max(max_unit_deviation,deviation);max_reconstruction_error=max(max_reconstruction_error,err)
            with gzip.GzipFile(fileobj=io.BytesIO(z.read('status.private.jsonl.gz'))) as f:
                roster=[json.loads(line) for line in f]
            if len(roster)!=length:raise ValueError('roster size mismatch '+str(ix))
            for j,(rec,r) in enumerate(zip(roster,rows[last:last+length])):
                if rec['canonical_article_id']!=r['article_id'] or rec['canonical_article_id'] in seen:
                    raise ValueError('canonical order/dup mismatch '+str(ix))
                seen.add(rec['canonical_article_id'])
                if (rec['vector_row_global']!=last+j or rec['vector_row_in_shard']!=j or rec['status']!='ready' or
                    rec['source_id']!=r['source_id'] or rec['source_record_id']!=r['source_record_id'] or
                    rec['raw_export_sha256']!=r['raw_export_sha256'] or rec['raw_record_ordinal']!=r['raw_record_ordinal'] or
                    rec['text_state']!=r['text_state'] or rec['title_only']!=(r['text_state']=='title_only') or
                    rec['text_sha256']!=hash_data((r['title']+'[SEP]'+(r.get('abstract') or '')).encode('utf-8')) or
                    rec['encoded_tokens']!=min(rec['untruncated_tokens'],512) or rec['tokens_lost']!=max(0,rec['untruncated_tokens']-512) or
                    rec['untruncated_tokens']<2 or rec['encoded_tokens']>512 or rec['tokens_lost']<0):
                    raise ValueError('frozen source row/text provenance or token-loss mismatch '+str(ix))
                source[rec['source_id']]+=1;state[rec['text_state']]+=1
                totals['truncated']+=rec['tokens_lost']>0;totals['tokens_lost']+=rec['tokens_lost'];totals['title_only']+=rec['title_only']
            if report['rows']!=length or report['truncated_rows']!=sum(x['tokens_lost']>0 for x in roster) or report['lost_tokens']!=sum(x['tokens_lost'] for x in roster) or report['title_only_rows']!=sum(x['title_only'] for x in roster):
                raise ValueError('independent shard aggregate mismatch '+str(ix))
        n+=length;last+=length;verified_files.append({'file':entry['file'],'sha256':entry['sha256'],'rows':length})
    if n!=COHORT or len(seen)!=COHORT or last!=COHORT:raise ValueError('full canonical count mismatch')
    if state!=Counter({'title_abstract':49398,'title_only':7806}) or dict(source)!=overall['source_counts']:
        raise ValueError('full stratification mismatch')
    if totals['tokens_lost']!=overall['total_lost_tokens'] or totals['truncated']!=overall['total_truncated_rows'] or totals['title_only']!=overall['title_only_rows']:
        raise ValueError('full aggregate token-loss tally mismatch')
    result={'schema':'pro-adherence-stage3-specter2-full-independent-private-audit/v1',
            'status':'FULL_57204_INDEPENDENT_LOCAL_QA_PASS_PENDING_REMOTE_READBACK',
            'manifest_sha256':file_sha(target),'frozen_input_sha256':EXPECTED_ARCHIVE,
            'model_base_sha256':BASE_SHA,'model_proximity_sha256':ADAPTER_SHA,
            'full_articles':COHORT,'shards_verified':len(verified_files),'all_ready':True,
            'vector_shape':[COHORT,DIM],'source_counts':dict(source),'text_state_counts':dict(state),
            'tokens_lost_total':totals['tokens_lost'],'truncated_articles':totals['truncated'],
            'title_only_articles':totals['title_only'],
            'global_min_raw_l2':global_min_l2,'global_max_raw_l2':global_max_l2,
            'max_unit_l2_deviation':max_unit_deviation,'max_raw_reconstruction_error':max_reconstruction_error,
            'all_shard_sha_crc_and_member_hashes_verified':True,
            'all_canonical_article_source_provenance_text_sha_verified':True,
            'torch_model_executed_by_auditor':False,'remote_drive_readback_done':False,
            'private_rows_or_vectors_published':False,'stage3_closed':False}
    output.write_bytes((json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+'\n').encode())
    print(json.dumps({'status':result['status'],'all_ready':COHORT,'shards':len(verified_files),
                      'audit_sha256':file_sha(output),'truncated':totals['truncated']},sort_keys=True),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--shards-dir',required=True,type=Path)
    p.add_argument('--input-zip',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();audit(a.shards_dir,a.input_zip,a.out)
