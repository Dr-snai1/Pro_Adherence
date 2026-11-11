#!/usr/bin/env python3
"""Private, authorized Stage3 P1 PubMedBERT only; offline CPU inference.

Never reads network, uses exact locally verified frozen weights and tokenizer.
One-time limited 1,000 canonical article pilot; no SPECTER2 or node2vec training.
"""
from __future__ import annotations
import argparse
from collections import Counter
from hashlib import sha256
import gzip
import io
import json
import os
from pathlib import Path
import re
import resource
import shutil
import time
import zipfile

EXPECTED_INPUT_ZIP_SHA = 'da92d16cfb2ac967f812aff2c219d8e6beaadd1175fd5f5bb401b4de53c716d8'
EXPECTED_WEIGHT_SHA = 'd513412d396cecec5f67936ac871b4aaf1178dfb5193776e790fd2b28bba240c'
EXPECTED_REVISION = 'd673b8835373c6fa116d6d8006b33d48734e305d'
EXPECTED_CONFIG_SHA = '56bab767c02bc792897638feb8addc06d483d9c73769a5f554bbabea1f5507a1'
EXPECTED_TOKENIZER_SHA = '53b6f42b8b8daddbdc6d3532c324187a92b46c1602bd6e8d4ad5a413b4fc90e1'
EXPECTED_VOCAB_SHA = '7b36651908a88bc38bda41b728b2a598191e0d3b553cbacf7b1e5f026d5b5b9f'


def file_sha(path):
    h=sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def sentence_boundaries(abstract, tok, full_ids):
    # Prefer sentence boundary, but only when the token sequence matches the
    # exact tokenizer output of the complete abstract. Otherwise force token
    # boundaries with no silent content loss.
    candidates = re.split(r'(?<=[.!?])\s+',abstract)
    fragments=[tok.encode(s,add_special_tokens=False) for s in candidates if s]
    flattened=[i for block in fragments for i in block]
    if flattened!=full_ids:
        return set(),True
    cur=0;ends=set()
    for f in fragments:
        cur+=len(f); ends.add(cur)
    return ends,False


def chunk_content(content_ids, capacity, boundaries):
    """Find largest sentence boundary within token capacity, else cut at capacity."""
    end=min(len(content_ids),capacity)
    cands=[x for x in boundaries if x<=end and x>0]
    return max(cands) if cands else end


def prepare_chunks(row,tok):
    title=row['title']
    abstract=row['abstract']
    if not isinstance(title,str) or not title.strip():
        raise ValueError('pilot has no usable title: '+row['article_id'])
    state=row['text_state']
    if state not in ('title_abstract','title_only'):
        raise ValueError('pilot unready text state: '+row['article_id'])
    if state=='title_abstract' and (not isinstance(abstract,str) or not abstract.strip()):
        raise ValueError('record lost chosen abstract')
    if state=='title_only' and abstract not in (None,''):
        raise ValueError('title-only has abstract')
    title_ids=tok.encode(title,add_special_tokens=False)
    abs_ids=tok.encode(abstract,add_special_tokens=False) if abstract else []
    cls_id,sep_id=tok.cls_token_id,tok.sep_token_id
    if None in (cls_id,sep_id):
        raise ValueError('model tokenizer has no CLS/SEP ids')
    chunks=[]; forced=0; fallback=False
    if not abs_ids:
        if len(title_ids)+2>512:
            raise ValueError('title-only exceeds model budget')
        tokens=[cls_id]+title_ids+[sep_id]
        mask=[0]+[1]*len(title_ids)+[0]
        return [{'ids':tokens,'content_mask':mask,'content_tokens':len(title_ids)}],0,False,len(title_ids),0
    if len(title_ids)+3>512:
        raise ValueError('title exceeds first-chunk budget')
    boundaries,fallback=sentence_boundaries(abstract,tok,abs_ids)
    cur=0;first=True
    while cur<len(abs_ids):
        capacity=512-(len(title_ids)+3 if first else 2)
        relative={b-cur for b in boundaries if b>cur}
        take=chunk_content(abs_ids[cur:],capacity,relative)
        if take<=0 or take>capacity:
            raise ValueError('non-progressing text chunk')
        if cur+take not in boundaries and cur+take!=len(abs_ids):
            forced+=1
        part=abs_ids[cur:cur+take]
        if first:
            toks=[cls_id]+title_ids+[sep_id]+part+[sep_id]
            cm=[0]+[1]*len(title_ids)+[0]+[1]*len(part)+[0]
        else:
            toks=[cls_id]+part+[sep_id]
            cm=[0]+[1]*len(part)+[0]
        if len(toks)>512 or len(toks)!=len(cm):
            raise ValueError('truncation or mask misalignment')
        chunks.append({'ids':toks,'content_mask':cm,'content_tokens':sum(cm)})
        cur+=take;first=False
    total=sum(c['content_tokens'] for c in chunks)
    if total != len(title_ids)+len(abs_ids):
        raise ValueError('silent token loss or duplicated title')
    return chunks,forced,fallback,len(title_ids),len(abs_ids)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pilot-zip',type=Path,required=True)
    ap.add_argument('--model-dir',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--batch-size',type=int,default=4)
    ap.add_argument('--cpu-threads',type=int,default=3)
    ap.add_argument('--max-articles',type=int,default=1000)
    args=ap.parse_args()
    if args.batch_size<1 or args.batch_size>8 or args.cpu_threads<1 or args.cpu_threads>5 or not 1<=args.max_articles<=1000:
        ap.error('bounded CPU-only pilot: batch 1–8, threads 1–5, articles 1–1000')
    if args.output_dir.exists():
        ap.error('refuse to overwrite an existing artifact')
    if file_sha(args.pilot_zip)!=EXPECTED_INPUT_ZIP_SHA:
        ap.error('approved private pilot ZIP SHA mismatch')
    expected={
        'pytorch_model.bin':EXPECTED_WEIGHT_SHA,'config.json':EXPECTED_CONFIG_SHA,
        'tokenizer_config.json':EXPECTED_TOKENIZER_SHA,'vocab.txt':EXPECTED_VOCAB_SHA}
    for filename,digest in expected.items():
        p=args.model_dir/filename
        if not p.is_file() or file_sha(p)!=digest:
            ap.error('pinned model file missing/bad SHA256: '+filename)
    if os.environ.get('HF_HUB_OFFLINE')!='1' or os.environ.get('TRANSFORMERS_OFFLINE')!='1':
        ap.error('require HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1')
    import torch
    import numpy as np
    from transformers import BertModel, BertTokenizer
    torch.set_num_threads(args.cpu_threads)
    torch.set_num_interop_threads(1)
    tokenizer=BertTokenizer.from_pretrained(str(args.model_dir),local_files_only=True,do_lower_case=True)
    # BertModel strips frozen MLM prediction head; base encoder weights identical.
    model=BertModel.from_pretrained(str(args.model_dir),local_files_only=True)
    model.eval()
    if model.config.hidden_size!=768 or model.config.max_position_embeddings!=512:
        raise ValueError('frozen PubMedBERT architecture mismatch')
    with zipfile.ZipFile(args.pilot_zip) as z:
        if z.testzip() is not None:
            raise ValueError('private input ZIP CRC mismatch')
        rows=[json.loads(l) for l in gzip.decompress(z.read('pilot_1000_inputs.private.jsonl.gz')).splitlines()]
        srcmanifest=json.loads(z.read('pilot_1000_manifest.private.json'))
    if len(rows)!=1000 or len({r['article_id'] for r in rows})!=1000 or srcmanifest['pilot_selected']!=1000:
        raise ValueError('pilot input canonical coverage mismatch')
    selected=rows[:args.max_articles]
    n=len(selected)
    tasks=[];token_counts=[];lengths=[];stats=Counter();rowmeta=[]
    for i,row in enumerate(selected):
        chunks,forced,fallback,title_count,abs_count=prepare_chunks(row,tokenizer)
        if len(chunks)>1:stats['fragmented_articles']+=1
        stats['fragments']+=len(chunks)
        stats['forced_token_splits']+=forced
        stats['sentence_tokenization_fallbacks']+=int(fallback)
        stats['title_only']+=row['text_state']=='title_only'
        token_counts.append(title_count+abs_count)
        lengths.append(len(chunks))
        for ch in chunks:
            tasks.append((i,ch))
        rowmeta.append({
            'article_id':row['article_id'], 'source_record_id':row['source_record_id'],
            'text_state':row['text_state'],'title_content_tokens':title_count,
            'abstract_content_tokens':abs_count,'fragment_count':len(chunks),
            'forced_token_splits':forced,'sentence_tokenization_fallback':fallback,
            'citation_degree':row['citation_degree'], 'source_id':row['source_id'],
            'raw_export_sha256':row['raw_export_sha256'],
            'year_bucket':row['year_bucket'],
        })
    raw_cls=np.zeros((n,768),dtype=np.float32)
    raw_mean=np.zeros((n,768),dtype=np.float32)
    den=np.zeros(n,dtype=np.int64)
    t0=time.monotonic();chunks_done=0
    # Stable length buckets. At a fixed, small batch, padding is limited.
    tasks.sort(key=lambda x:(len(x[1]['ids']),x[0]))
    with torch.inference_mode():
        for off in range(0,len(tasks),args.batch_size):
            batch=tasks[off:off+args.batch_size]
            L=max(len(x[1]['ids']) for x in batch)
            input_ids=np.full((len(batch),L),tokenizer.pad_token_id,dtype=np.int64)
            attention=np.zeros((len(batch),L),dtype=np.int64)
            content=np.zeros((len(batch),L),dtype=np.float32)
            for j,(_,ch) in enumerate(batch):
                l=len(ch['ids']);input_ids[j,:l]=ch['ids'];attention[j,:l]=1
                content[j,:l]=ch['content_mask']
            hidden=model(input_ids=torch.from_numpy(input_ids),
                         attention_mask=torch.from_numpy(attention)).last_hidden_state.numpy()
            # Chunk aggregation is explicitly token-content-weighted for both CLS and mean.
            for j,(idx,ch) in enumerate(batch):
                w=int(content[j].sum())
                if w!=ch['content_tokens'] or w<=0:raise ValueError('invalid content-token weight')
                cls=hidden[j,0,:].astype(np.float64)
                mn=((hidden[j,:,:].astype(np.float64) * content[j,:,None]).sum(axis=0)/w)
                raw_cls[idx]+=np.float32(cls*w)
                raw_mean[idx]+=np.float32(mn*w)
                den[idx]+=w
            chunks_done+=len(batch)
            if off and off%120==0:
                print('PROGRESS',off,'/',len(tasks),'elapsed_sec',round(time.monotonic()-t0,1),flush=True)
    if np.any(den==0) or any(rowmeta[i]['title_content_tokens']+rowmeta[i]['abstract_content_tokens']!=den[i] for i in range(n)):
        raise ValueError('non-lossy content-token accounting failed')
    raw_cls/=den.astype(np.float32)[:,None]
    raw_mean/=den.astype(np.float32)[:,None]
    if not np.all(np.isfinite(raw_cls)) or not np.all(np.isfinite(raw_mean)):
        raise ValueError('nonfinite encoder outputs')
    norms_cls=np.linalg.norm(raw_cls.astype(np.float64),axis=1)
    norms_mean=np.linalg.norm(raw_mean.astype(np.float64),axis=1)
    if (norms_cls<=0).any() or (norms_mean<=0).any():raise ValueError('zero-vector output')
    unit_cls=(raw_cls/norms_cls[:,None]).astype(np.float32)
    unit_mean=(raw_mean/norms_mean[:,None]).astype(np.float32)
    if not np.allclose(np.linalg.norm(unit_cls,axis=1),1.0,atol=1e-5) or not np.allclose(np.linalg.norm(unit_mean,axis=1),1.0,atol=1e-5):
        raise ValueError('L2 normalization mismatch')
    dur=time.monotonic()-t0
    print('ENCODER_COMPLETED',n,'CHUNKS',chunks_done,'SEC',round(dur,1),flush=True)
    args.output_dir.mkdir(mode=0o700,parents=True)
    # Six matrices; norm is float64 to match original-norm precision.
    for name,arr in [('cls_raw.npy',raw_cls),('mean_raw.npy',raw_mean),
                     ('cls_unit.npy',unit_cls),('mean_unit.npy',unit_mean),
                     ('cls_norm.npy',norms_cls),('mean_norm.npy',norms_mean)]:
        np.save(args.output_dir/name,arr,allow_pickle=False)
    mdpath=args.output_dir/'article_status.private.jsonl.gz'
    with mdpath.open('xb') as f:
        with gzip.GzipFile(filename='',fileobj=f,mode='wb',mtime=0,compresslevel=6) as z:
            for row in rowmeta:
                z.write((json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode())
    # Evidence-only 10 nearest neighbours from 1,000, no textual/personal names in public report.
    sim=unit_mean @ unit_mean.T
    sample_indices=np.linspace(0,n-1,num=min(10,n),dtype=int)
    sample_neighbours=[]
    for i in sample_indices:
        idx=np.argsort(-sim[i]); idx=idx[idx!=i][:3]
        sample_neighbours.append({'article_id':rowmeta[i]['article_id'],
              'neighbours':[{'article_id':rowmeta[j]['article_id'],'cosine':float(sim[i,j])} for j in idx]})
    with (args.output_dir/'nearest_neighbour_examples.private.json').open('x') as f:
        json.dump({'note':'Exploratory only, NOT externally validated relevance','examples':sample_neighbours},f,indent=2)
    manifest={
        'schema':'pro-adherence-stage3-pubmedbert-P1-outputs/v1',
        'status':'PILOT_PUBMEDBERT_INFERENCE_COMPLETE' if n==1000 else 'BOUNDED_PARTIAL_PILOT',
        'published':False, 'private':True,'model_repo':'microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract',
        'model_revision':EXPECTED_REVISION,'model_weight_sha256':EXPECTED_WEIGHT_SHA,
        'model_config_sha256':EXPECTED_CONFIG_SHA,'model_vocab_sha256':EXPECTED_VOCAB_SHA,
        'input_zip_sha256':EXPECTED_INPUT_ZIP_SHA,'number_articles':n,'expected_pilot_articles':1000,
        'num_fragment_passes':chunks_done,'num_source_text_tokens':int(sum(token_counts)),
        'counts':dict(stats),'fragment_count_max':max(lengths),
        'time_encoder_seconds':dur,'throughput_article_per_second':n/dur,
        'peak_process_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'cpu_threads':args.cpu_threads,'batch_size':args.batch_size,
        'torch_version':torch.__version__,'transformers_version':__import__('transformers').__version__,
        'poolings':['last_hidden_cls','masked_mean_excluding_inserted_special_padding'],
        'fragment_policy':'nontruncated_sentence_first_contiguous_token_coverage_title_first_only',
        'article_aggregation':'content_token_weighted_mean_for_cls_and_mean',
        'normalization':'l2_after_article_aggregation','similarity':'cosine',
        'dtype_raw_unit':'float32','dtype_norm':'float64','external_spend_usd':0,
        'specter2_not_run':True,'node2vec_training_not_run':True,
        'outputs':{},
    }
    for p in sorted(args.output_dir.iterdir()):
        if p.is_file():manifest['outputs'][p.name]={'sha256':file_sha(p),'bytes':p.stat().st_size}
    mp=args.output_dir/'manifest.private.json'
    mp.write_text(json.dumps(manifest,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('MANIFEST',file_sha(mp),json.dumps({k:manifest[k] for k in ('status','number_articles','num_fragment_passes','time_encoder_seconds','counts','peak_process_rss_kib')},sort_keys=True),flush=True)

if __name__=='__main__': main()
