#!/usr/bin/env python3
"""Owner-authorized FULL frozen 57,204-paper SPECTER2 local CPU inference.

Only approved frozen private input ZIP, verified public base/proximity weights,
Transformers 5.22.2 safe candidate (not unsupported upstream Adapters).
Streaming atomic, resume-safe 1,000-row shards; never sends private records to CI.

Stage3 scientific contract: exact title+[SEP]+abstract, max512 truncate,
first-token 768d raw float32 + L2 norm float64 + unit float32, source lineage,
per-record tokens lost. User authorized full free local CPU on 2026-11-13.
"""
from __future__ import annotations
if not __debug__:
    raise SystemExit('Optimized Python -O prohibited: frozen source assertions required')
import argparse
import contextlib
from collections import Counter
import gzip
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import platform
import resource
import signal
import sys
import time
import zipfile

import numpy as np
import torch
from transformers import BertTokenizerFast
from pro_adherence.stage3_specter2_proximity_compat import CandidateBertOutputAdapter, pinned_weights_only
from stage3_specter2_public_end_to_end import load_pinned_base, verify_public_files

APPROVED_FULL_ARCHIVE_SHA='cc60cefdaa62a60712425b0f1ea1719338ec4250ec8bcaf1fd465329c677395e'
APPROVED_FULL_MEMBER_SHA='1611f07e18ccf999493938e552d1a73ad049db931a11399fc01f0ca7b07dc053'
APPROVED_BUNDLE_LOCK_SHA='1ee689fd2f10449745f23fb2fa63985d44d55f293ba05dd37a701b3bbb15574a'
APPROVED_BASE_SHA='801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc'
APPROVED_ADAPTER_SHA='5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'
COHORT, DIM, MAX_TOKENS, SHARD_ROWS = 57204, 768, 512, 1000
APPROVED_SOURCE_IDS={'pubmed','woscc','apa_psycinfo'}
STOP_REQUESTED=False

def stop_on_signal(signum,frame):
    global STOP_REQUESTED
    STOP_REQUESTED=True

def sha_file(path:Path)->str:
    h=sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def sha_data(data:bytes)->str:return sha256(data).hexdigest()

def json_bytes(data)->bytes:return (json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')

def peak_mib()->float:return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2)

def cgroup():
    base=Path('/sys/fs/cgroup');p=base/'memory.max'
    if p.exists() and p.read_text().strip()!='max':
        limit=int(p.read_text());usage=int((base/'memory.current').read_text());return limit,usage
    return None,None

def health():
    limit,used=cgroup()
    if limit is not None and limit-used<384*1024**2:
        raise RuntimeError('RAM HEADROOM STOP: fewer than 384MiB left in cgroup')
    if STOP_REQUESTED:raise KeyboardInterrupt('graceful signal stop at shard boundary')

def verify_bundle(bundle:Path,evidence:Path):
    from importlib.metadata import version
    if platform.machine().lower()!='x86_64' or sys.version_info[:2]!=(3,13):
        raise RuntimeError('requires pinned CPython3.13 Linux x86-64 runtime')
    if torch.__version__!='2.10.0+cpu':raise RuntimeError('torch CPU version mismatch')
    if sha_file(bundle/'lock.json')!=APPROVED_BUNDLE_LOCK_SHA:
        raise RuntimeError('frozen wheel closure SHA mismatch')
    lock=json.loads((bundle/'lock.json').read_text())
    if set(lock)!= {'scope','python','architecture','wheels'} or len(lock['wheels'])!=31:
        raise RuntimeError('frozen wheel closure inventory mismatch')
    for name,meta in lock['wheels'].items():
        p=bundle/'wheels'/meta['filename']
        if not p.is_file() or p.is_symlink() or p.stat().st_size!=meta['bytes'] or sha_file(p)!=meta['sha256'] or version(name)!=meta['version']:
            raise RuntimeError('frozen local wheel/version mismatch: '+name)
    from importlib.metadata import version
    for name,v in [('transformers','5.22.2'),('tokenizers','0.23.3'),('numpy','2.5.4'),('safetensors','0.8.0')]:
        if version(name)!=v:raise RuntimeError('critical inference dependency changed: '+name)
    e=json.loads(evidence.read_text())
    verify_public_files(bundle/'base',bundle/'adapter'/'pytorch_adapter.bin',e)
    if sha_file(bundle/'base'/'pytorch_model.bin')!=APPROVED_BASE_SHA or sha_file(bundle/'adapter'/'pytorch_adapter.bin')!=APPROVED_ADAPTER_SHA:
        raise RuntimeError('frozen public base or proximity SHA changed')
    return {'python':sys.version.split()[0],'torch':torch.__version__, 'transformers':version('transformers'),
            'numpy':version('numpy'),'wheel_hash_count':31,'wheel_closure_sha256':APPROVED_BUNDLE_LOCK_SHA,
            'torch_provider_wheel_byte_sha_verified':False,
            'torch_version_import_checked_and_P1_numerically_validated':True}

def frozen_rows(input_zip:Path):
    if sha_file(input_zip)!=APPROVED_FULL_ARCHIVE_SHA:raise RuntimeError('full frozen input ZIP SHA mismatch')
    with zipfile.ZipFile(input_zip) as z:
        if z.testzip() is not None:raise RuntimeError('frozen input CRC mismatch')
        if set(z.namelist()) != {'full_pubmedbert_inputs.private.jsonl.gz','full_inputs_manifest.private.json'}:
            raise RuntimeError('frozen full ZIP files mismatch')
        if sha_data(z.read('full_pubmedbert_inputs.private.jsonl.gz'))!=APPROVED_FULL_MEMBER_SHA:
            raise RuntimeError('full frozen gzip member SHA mismatch')
        with gzip.open(z.open('full_pubmedbert_inputs.private.jsonl.gz'),'rt',encoding='utf-8') as f:
            rows=[json.loads(s) for s in f]
    if len(rows)!=COHORT or len({r['article_id'] for r in rows})!=COHORT:
        raise RuntimeError('frozen full canonical cohort count/uniqueness mismatch')
    states=Counter();sources=Counter()
    for r in rows:
        state=r.get('text_state')
        if state not in ('title_abstract','title_only') or not isinstance(r.get('title'),str) or not r['title'].strip():
            raise RuntimeError('frozen cohort text state or title invalid')
        if state=='title_only' and r.get('abstract') not in (None,''):
            raise RuntimeError('title-only row unexpectedly includes abstract')
        if state=='title_abstract' and (not isinstance(r.get('abstract'),str) or not r['abstract'].strip()):
            raise RuntimeError('title+abstract row missing abstract')
        if r.get('source_id') not in APPROVED_SOURCE_IDS or not r.get('source_record_id') or not r.get('raw_export_sha256'):
            raise RuntimeError('source identity missing')
        states[state]+=1;sources[r['source_id']]+=1
    if dict(states)!={'title_abstract':49398,'title_only':7806}:
        raise RuntimeError('unexpected scientific full-cohort eligible text breakdown')
    return rows,dict(states),dict(sources)

def compute_lengths(tok, rows):
    texts=[r['title']+tok.sep_token+(r.get('abstract') or '') for r in rows]
    # The exact WordPiece tokenizer is frozen; no fragmentation or title loss prevention.
    untruncated=tok(texts,add_special_tokens=True,truncation=False)['input_ids']
    stat=[]
    for text,ids in zip(texts,untruncated):
        total=len(ids);used=min(total,MAX_TOKENS)
        stat.append({'untruncated_tokens':total,'encoded_tokens':used,'tokens_lost':total-used,
                     'text_sha256':sha_data(text.encode('utf-8'))})
    return texts,stat

def numeric(raw:np.ndarray):
    if raw.dtype!=np.float32 or raw.ndim!=2 or raw.shape[1]!=DIM or not np.isfinite(raw).all():
        raise RuntimeError('nonfinite or invalid first-token vectors')
    norm=np.linalg.norm(raw.astype(np.float64),axis=1)
    if not np.isfinite(norm).all() or (norm<=0).any():raise RuntimeError('nonfinite L2 norms')
    unit=(raw.astype(np.float64)/norm[:,None]).astype(np.float32)
    if not np.allclose(np.linalg.norm(unit.astype(np.float64),axis=1),1,rtol=0,atol=1e-5):
        raise RuntimeError('unit vector norm error')
    if not np.allclose(unit.astype(np.float64)*norm[:,None],raw.astype(np.float64),atol=3e-6,rtol=3e-6):
        raise RuntimeError('vector reconstruction error')
    return norm,unit

def np_bytes(a):
    b=io.BytesIO();np.save(b,a,allow_pickle=False);return b.getvalue()

def stable_zip(z,name,raw):
    info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
    info.external_attr=0o600<<16
    z.writestr(info,raw)

def create_shard(path,ix,start,rows,stats,raw,runtime,elapsed_s,mem_mib):
    norms,unit=numeric(raw)
    buf=io.BytesIO()
    with gzip.GzipFile(filename='',fileobj=buf,mode='wb',mtime=0,compresslevel=6) as g:
        for offset,(r,s) in enumerate(zip(rows,stats)):
            obj={'canonical_article_id':r['article_id'],'vector_row_global':start+offset,
                'vector_row_in_shard':offset,'source_id':r['source_id'],'source_record_id':r['source_record_id'],
                'raw_export_sha256':r['raw_export_sha256'],'raw_record_ordinal':r['raw_record_ordinal'],
                'text_state':r['text_state'],'title_only':r['text_state']=='title_only',
                'text_sha256':s['text_sha256'],'untruncated_tokens':s['untruncated_tokens'],
                'encoded_tokens':s['encoded_tokens'],'tokens_lost':s['tokens_lost'],
                'status':'ready','peer_review_unknown':r['peer_review_unknown'],
                'wos_nr_cr_mismatch':r['wos_nr_cr_mismatch']}
            g.write(json_bytes(obj))
    data={'raw.float32.npy':np_bytes(raw), 'raw_l2_norm.float64.npy':np_bytes(norms),
          'unit.float32.npy':np_bytes(unit), 'status.private.jsonl.gz':buf.getvalue()}
    metrics={'status':'COMPLETE_SHARD_LOCAL','shard':ix,'start':start,'rows':len(rows),
             'lost_tokens':sum(s['tokens_lost'] for s in stats),
             'truncated_rows':sum(s['tokens_lost']>0 for s in stats),
             'title_only_rows':sum(r['text_state']=='title_only' for r in rows),
             'source_counts':dict(Counter(r['source_id'] for r in rows)),
             'min_l2':float(norms.min()),'max_l2':float(norms.max()),
             'max_unit_l2_deviation':float(np.abs(np.linalg.norm(unit.astype(np.float64),axis=1)-1).max()),
             'elapsed_inference_s':round(elapsed_s,3),'process_peak_rss_mib':mem_mib,
             'approved_full_input_zip_sha256':APPROVED_FULL_ARCHIVE_SHA,
             'base_sha256':APPROVED_BASE_SHA,'adapter_sha256':APPROVED_ADAPTER_SHA,
             'runtime':runtime,'full_57204_cohort_complete':False,'publication_authorized':False,
             'stage3_closed':False}
    data['report.private.json']=json_bytes(metrics)
    manifest={'schema':'pro-adherence-stage3-specter2-full-shard-private/v1',
              'shard_index':ix,'global_start':start,'count':len(rows),'dimension':DIM,
              'cohort':COHORT,'input_zip_sha256':APPROVED_FULL_ARCHIVE_SHA,
              'base_weight_sha256':APPROVED_BASE_SHA,'adapter_weight_sha256':APPROVED_ADAPTER_SHA,
              'runtime_wheel_sha256':APPROVED_BUNDLE_LOCK_SHA,
              'files':{name:{'sha256':sha_data(b),'bytes':len(b)} for name,b in data.items()},
              'full_cohort_executed':False,'stage3_closed':False,'publication_authorized':False}
    data['manifest.private.json']=json_bytes(manifest)
    tmp=path.with_suffix('.incomplete')
    if tmp.exists():tmp.unlink()
    with zipfile.ZipFile(tmp,'w') as z:
        for name,b in data.items():stable_zip(z,name,b)
    with zipfile.ZipFile(tmp) as z:
        if z.testzip() is not None:raise RuntimeError('result ZIP CRC failure')
        for name,meta in manifest['files'].items():
            b=z.read(name)
            if len(b)!=meta['bytes'] or sha_data(b)!=meta['sha256']:
                raise RuntimeError('result ZIP internal SHA failure: '+name)
    tmp.replace(path);os.chmod(path,0o600)
    return metrics,sha_file(path)

def validate_existing(path,index,start,rows):
    if not path.exists():return None
    if path.is_symlink():raise RuntimeError('unsafe previous shard symlink')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise RuntimeError('previous shard CRC mismatch')
        m=json.loads(z.read('manifest.private.json'));report=json.loads(z.read('report.private.json'))
        if m['shard_index']!=index or m['global_start']!=start or m['count']!=len(rows) or m['cohort']!=COHORT or m['dimension']!=DIM:
            raise RuntimeError('previous shard manifest changed')
        if m['input_zip_sha256']!=APPROVED_FULL_ARCHIVE_SHA or m['base_weight_sha256']!=APPROVED_BASE_SHA or m['adapter_weight_sha256']!=APPROVED_ADAPTER_SHA or m['runtime_wheel_sha256']!=APPROVED_BUNDLE_LOCK_SHA:
            raise RuntimeError('previous shard public/frozen identity changed')
        for name,x in m['files'].items():
            b=z.read(name)
            if len(b)!=x['bytes'] or sha_data(b)!=x['sha256']:raise RuntimeError('previous shard file SHA mismatch')
        with gzip.open(io.BytesIO(z.read('status.private.jsonl.gz')),'rt') as f:
            roster=[json.loads(s) for s in f]
        if len(roster)!=len(rows) or any(x['canonical_article_id']!=r['article_id'] or x['vector_row_global']!=start+i or x['status']!='ready' for i,(x,r) in enumerate(zip(roster,rows))):
            raise RuntimeError('previous shard row identity mismatch')
    return {'file':path.name,'sha256':sha_file(path),'size_bytes':path.stat().st_size,'report':report}

def run(args):
    if not args.owner_full_scope:raise RuntimeError('explicit owner full-57,204 SPECTER2 CPU authorization flag required')
    if os.environ.get('HF_HUB_OFFLINE')!='1' or os.environ.get('TRANSFORMERS_OFFLINE')!='1':
        raise RuntimeError('frozen model inference must be OFFLINE')
    if 'adapters' in sys.modules:raise RuntimeError('unsupported old official Adapters runtime forbidden')
    health()
    runtime=verify_bundle(args.bundle,args.evidence)
    rows,states,sources=frozen_rows(args.input_zip)
    args.out_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(args.out_dir,0o700)
    final=args.out_dir/'FULL_57204_MANIFEST.private.json'
    if final.exists():raise RuntimeError('complete run manifest already exists; no overwrite')
    torch.set_num_threads(args.threads);torch.manual_seed(20261113)
    base,load_info=load_pinned_base(args.bundle/'base')
    actual=pinned_weights_only(args.bundle/'adapter'/'pytorch_adapter.bin')
    orig=[layer.output for layer in base.encoder.layer]
    if len(orig)!=12:raise RuntimeError('approved 12 BERT FFN layers mismatch')
    for i,layer in enumerate(base.encoder.layer):layer.output=CandidateBertOutputAdapter(orig[i],actual,i).eval()
    base.requires_grad_(False);base.eval();del actual
    tokenizer=BertTokenizerFast.from_pretrained(str(args.bundle/'base'),local_files_only=True)
    t0=time.monotonic();shard_reports=[];reused=0
    print(json.dumps({'event':'FULL_SPECTER2_BEGIN','articles':COHORT,'sources':sources,'text_state':states,
                      'batch':args.batch,'threads':args.threads,'shard':SHARD_ROWS,'rss_mib':peak_mib(),
                      'runtime':runtime},sort_keys=True),flush=True)
    for ix,start in enumerate(range(0,COHORT,SHARD_ROWS)):
        health()
        batchrows=rows[start:min(start+SHARD_ROWS,COHORT)]
        name=f'STAGE3_20261113_SPECTER2_FULL_SHARD_{ix:03d}.zip'
        dest=args.out_dir/name
        prev=validate_existing(dest,ix,start,batchrows)
        if prev is not None:
            shard_reports.append(prev);reused+=1
            print(json.dumps({'event':'SHARD_RESUME_VERIFIED','shard':ix,'rows':len(batchrows),'progress':start+len(batchrows)}),flush=True)
            continue
        texts,stats=compute_lengths(tokenizer,batchrows)
        raw=np.empty((len(batchrows),DIM),dtype=np.float32)
        # Sort by number of clipped WordPiece tokens only, preserving each canonical
        # row's final position. Avoid padding all small papers to 512 tokens.
        ordered=sorted(range(len(batchrows)),key=lambda i:(stats[i]['encoded_tokens'],i))
        began=time.monotonic()
        with torch.inference_mode():
            for k in range(0,len(ordered),args.batch):
                chosen=ordered[k:k+args.batch]
                encoded=tokenizer([texts[j] for j in chosen],return_tensors='pt',padding=True,
                    truncation=True,max_length=MAX_TOKENS,return_token_type_ids=False)
                output=base(**encoded).last_hidden_state[:,0,:].detach().cpu().to(torch.float32).numpy()
                if output.shape!=(len(chosen),DIM) or not np.isfinite(output).all():
                    raise RuntimeError(f'nonfinite/incomplete output in shard {ix}')
                raw[chosen]=output
                if k%max(args.batch*32,256)==0:health()
        elapsed=time.monotonic()-began
        report,digest=create_shard(dest,ix,start,batchrows,stats,raw,runtime,elapsed,peak_mib())
        del raw,stats,texts
        shard_reports.append({'file':name,'sha256':digest,'size_bytes':dest.stat().st_size,'report':report})
        print(json.dumps({'event':'SHARD_COMPLETE','shard':ix,'rows':report['rows'],
             'completed':start+len(batchrows),'total':COHORT,'seconds':round(elapsed,1),
             'process_peak_rss_mib':peak_mib(),'tokens_lost':report['lost_tokens'],
             'truncated_rows':report['truncated_rows'],'sha256':digest},sort_keys=True),flush=True)
        if STOP_REQUESTED:raise KeyboardInterrupt('graceful stop after atomic shard')
    if sum(x['report']['rows'] for x in shard_reports)!=COHORT or len(shard_reports)!=58:
        raise RuntimeError('full 57,204 coverage was not reached')
    manifest={'schema':'pro-adherence-stage3-specter2-full-private-run/v1',
              'status':'FULL_57204_LOCAL_COMPUTE_COMPLETE_AWAITING_INDEPENDENT_REMOTE_AUDIT',
              'authorized_owner_scope':'free local CPU full SPECTER2 57,204, 2026-11-13',
              'article_count':COHORT,'dimension':DIM,'source_counts':sources,'text_state_counts':states,
              'public_model_base_sha256':APPROVED_BASE_SHA,'public_proximity_adapter_sha256':APPROVED_ADAPTER_SHA,
              'scientific_contract':'title+[SEP]+abstract; BERT first-token768; no fragmentation; 512-token truncate; raw/norm/unit cosine',
              'private_source_zip_sha256':APPROVED_FULL_ARCHIVE_SHA,'private_gzip_member_sha256':APPROVED_FULL_MEMBER_SHA,
              'runtime':runtime,'model_base_loading':load_info,
              'shard_files':[{k:v for k,v in item.items() if k in ('file','sha256','size_bytes')} for item in shard_reports],
              'total_truncated_rows':sum(x['report']['truncated_rows'] for x in shard_reports),
              'total_lost_tokens':sum(x['report']['lost_tokens'] for x in shard_reports),
              'title_only_rows':sum(x['report']['title_only_rows'] for x in shard_reports),
              'elapsed_process_seconds':round(time.monotonic()-t0,2),'peak_rss_mib':peak_mib(),
              'independent_full_audit_passed':False,'remote_drive_upload_complete':False,
              'stage3_closed':False,'publication_authorized':False,'pr_merge_authorized':False}
    with final.open('xb') as f:f.write(json_bytes(manifest))
    os.chmod(final,0o600)
    print(json.dumps({'event':'FULL_LOCAL_57204_COMPLETE','shards':len(shard_reports),
        'article_count':COHORT,'manifest_sha256':sha_file(final),'lost_tokens':manifest['total_lost_tokens'],
        'truncated_articles':manifest['total_truncated_rows'],'rss_mib':peak_mib()},sort_keys=True),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--input-zip',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--batch',type=int,default=8,choices=(2,4,8,16))
    p.add_argument('--threads',type=int,default=4,choices=(2,4))
    p.add_argument('--owner-full-scope',action='store_true')
    args=p.parse_args()
    signal.signal(signal.SIGTERM,stop_on_signal)
    signal.signal(signal.SIGINT,stop_on_signal)
    try:run(args)
    except KeyboardInterrupt:
        print(json.dumps({'event':'FULL_RUN_STOPPED_AFTER_CHECKPOINT','note':'Resume rechecks all existing shards; no claim of completeness'}),flush=True)
        sys.exit(130)
