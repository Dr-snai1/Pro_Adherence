#!/usr/bin/env python3
"""Private, offline, resumable PubMedBERT Stage3 full-corpus execution by fixed shards.

Scientific operations exactly match the accepted 1,000-article CPU pilot:
768-d CLS and masked mean; title-once sentence-first nontruncated fragmentation;
content-token-weighted aggregation, raw/norm/L2 unit vectors, cosine semantics.
No network or external compute. The roster and input file are immutable and
verified by SHA. One deterministic shard per call, cannot overwrite outputs.
"""
from __future__ import annotations
import argparse,gzip,hashlib,importlib.util,json,os,resource,time,zipfile
from collections import Counter
from pathlib import Path

EXPECTED_FULL_INPUT_SHA='1611f07e18ccf999493938e552d1a73ad049db931a11399fc01f0ca7b07dc053'
EXPECTED_WEIGHT_SHA='d513412d396cecec5f67936ac871b4aaf1178dfb5193776e790fd2b28bba240c'
EXPECTED_CONFIG_SHA='56bab767c02bc792897638feb8addc06d483d9c73769a5f554bbabea1f5507a1'
EXPECTED_TOKENIZER_SHA='53b6f42b8b8daddbdc6d3532c324187a92b46c1602bd6e8d4ad5a413b4fc90e1'
EXPECTED_VOCAB_SHA='7b36651908a88bc38bda41b728b2a598191e0d3b553cbacf7b1e5f026d5b5b9f'
FULL_COUNT=57204
SHARD_COUNT=1000

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for c in iter(lambda:f.read(4*1024*1024),b''):h.update(c)
 return h.hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--full-input',type=Path,required=True)
 p.add_argument('--model-dir',type=Path,required=True)
 p.add_argument('--pilot-executed-runner',type=Path,required=True)
 p.add_argument('--output-dir',type=Path,required=True)
 p.add_argument('--shard-index',type=int,required=True)
 p.add_argument('--batch-size',type=int,default=4)
 p.add_argument('--cpu-threads',type=int,default=3)
 a=p.parse_args()
 if not 0<=a.shard_index<58 or not 1<=a.batch_size<=8 or not 1<=a.cpu_threads<=5:p.error('bounded full CPU shard index or resources invalid')
 if a.output_dir.exists():p.error('refuse overwrite shard output')
 if sha(a.full_input)!=EXPECTED_FULL_INPUT_SHA:p.error('full source input SHA mismatch')
 for fname,expected in [('pytorch_model.bin',EXPECTED_WEIGHT_SHA),('config.json',EXPECTED_CONFIG_SHA),('tokenizer_config.json',EXPECTED_TOKENIZER_SHA),('vocab.txt',EXPECTED_VOCAB_SHA)]:
  if sha(a.model_dir/fname)!=expected:p.error('frozen model mismatch '+fname)
 if os.environ.get('HF_HUB_OFFLINE')!='1' or os.environ.get('TRANSFORMERS_OFFLINE')!='1':p.error('offline flags required')
 import numpy as np,torch
 from transformers import BertModel,BertTokenizer
 spec=importlib.util.spec_from_file_location('p1_frozen_runner',a.pilot_executed_runner)
 p1=importlib.util.module_from_spec(spec);spec.loader.exec_module(p1)
 assert p1.EXPECTED_WEIGHT_SHA==EXPECTED_WEIGHT_SHA
 torch.set_num_threads(a.cpu_threads);torch.set_num_interop_threads(1)
 tok=BertTokenizer.from_pretrained(str(a.model_dir),local_files_only=True,do_lower_case=True)
 model=BertModel.from_pretrained(str(a.model_dir),local_files_only=True);model.eval()
 if model.config.hidden_size!=768 or model.config.max_position_embeddings!=512:raise ValueError('unexpected model config')
 selected=[];start=a.shard_index*SHARD_COUNT;stop=min(FULL_COUNT,start+SHARD_COUNT)
 with gzip.open(a.full_input,'rt',encoding='utf8') as f:
  for i,line in enumerate(f):
   if start<=i<stop:selected.append(json.loads(line))
   elif i>=stop:break
 if len(selected)!=stop-start:raise ValueError('shard incomplete')
 if len({r['article_id'] for r in selected})!=len(selected):raise ValueError('duplicate article')
 n=len(selected);raw_cls=np.zeros((n,768),np.float32);raw_mean=np.zeros((n,768),np.float32)
 den=np.zeros(n,np.int64);rowmeta=[];stats=Counter();tasks=[]
 for i,r in enumerate(selected):
  ch,forced,fallback,ti,ai=p1.prepare_chunks(r,tok)
  stats['fragmented_articles']+=len(ch)>1;stats['fragments']+=len(ch)
  stats['forced_token_splits']+=forced;stats['sentence_tokenization_fallbacks']+=int(fallback)
  stats['title_only']+=r['text_state']=='title_only'
  for c in ch:tasks.append((i,c))
  rowmeta.append({'article_id':r['article_id'],'source_record_id':r['source_record_id'],
                  'source_id':r['source_id'],'raw_export_sha256':r['raw_export_sha256'],
                  'text_state':r['text_state'],'fragment_count':len(ch),
                  'title_content_tokens':ti,'abstract_content_tokens':ai,
                  'forced_token_splits':forced,'sentence_tokenization_fallback':fallback})
 tasks.sort(key=lambda x:(len(x[1]['ids']),x[0]));t0=time.monotonic()
 with torch.inference_mode():
  for off in range(0,len(tasks),a.batch_size):
   batch=tasks[off:off+a.batch_size];L=max(len(c['ids']) for _,c in batch)
   ids=np.full((len(batch),L),tok.pad_token_id,np.int64);mask=np.zeros((len(batch),L),np.int64)
   cm=np.zeros((len(batch),L),np.float32)
   for j,(_,c) in enumerate(batch):
    k=len(c['ids']);ids[j,:k]=c['ids'];mask[j,:k]=1;cm[j,:k]=c['content_mask']
   hidden=model(input_ids=torch.from_numpy(ids),attention_mask=torch.from_numpy(mask)).last_hidden_state.numpy()
   for j,(idx,c) in enumerate(batch):
    weight=int(cm[j].sum())
    if weight<=0 or weight!=c['content_tokens']:raise ValueError('invalid content weight')
    cls=hidden[j,0,:].astype(np.float64)
    mn=(hidden[j,:,:].astype(np.float64)*cm[j,:,None]).sum(axis=0)/weight
    raw_cls[idx]+=np.float32(cls*weight);raw_mean[idx]+=np.float32(mn*weight)
    den[idx]+=weight
   if off%160==0:print('PROGRESS',a.shard_index,off,'/',len(tasks),'elapsed',round(time.monotonic()-t0,2),flush=True)
 if any(den[i]!=rowmeta[i]['title_content_tokens']+rowmeta[i]['abstract_content_tokens'] for i in range(n)):
  raise ValueError('content token accounting fails')
 if np.any(den==0):raise ValueError('zero denominator')
 raw_cls/=den.astype(np.float32)[:,None];raw_mean/=den.astype(np.float32)[:,None]
 norms_cls=np.linalg.norm(raw_cls.astype(np.float64),axis=1)
 norms_mean=np.linalg.norm(raw_mean.astype(np.float64),axis=1)
 if np.any(norms_cls<=0) or np.any(norms_mean<=0):raise ValueError('zero vectors')
 unit_cls=(raw_cls/norms_cls[:,None]).astype(np.float32)
 unit_mean=(raw_mean/norms_mean[:,None]).astype(np.float32)
 if not all(np.isfinite(x).all() for x in (raw_cls,raw_mean,unit_cls,unit_mean)):
  raise ValueError('nonfinite vectors')
 if not np.allclose(np.linalg.norm(unit_cls,axis=1),1.,atol=1e-5) or not np.allclose(np.linalg.norm(unit_mean,axis=1),1.,atol=1e-5):
  raise ValueError('unit vector normalization fails')
 elapsed=time.monotonic()-t0
 a.output_dir.mkdir(mode=0o700,parents=True)
 for filename,arr in [('cls_raw.npy',raw_cls),('mean_raw.npy',raw_mean),('cls_unit.npy',unit_cls),('mean_unit.npy',unit_mean),('cls_norm.npy',norms_cls),('mean_norm.npy',norms_mean)]:
  np.save(a.output_dir/filename,arr,allow_pickle=False)
 with (a.output_dir/'article_status.private.jsonl.gz').open('xb') as f:
  with gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0,compresslevel=6) as gz:
   for r in rowmeta:gz.write((json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode())
 manifest={'schema':'pro-adherence-stage3-pubmedbert-full-shard/v1','state':'COMPLETED_VERIFIED_LOCALLY',
           'start_index':start,'end_index_exclusive':stop,'shard_index':a.shard_index,'article_count':n,
           'full_expected':FULL_COUNT,'shard_size':SHARD_COUNT,'source_input_sha256':EXPECTED_FULL_INPUT_SHA,
           'model_weight_sha256':EXPECTED_WEIGHT_SHA,'model_revision':p1.EXPECTED_REVISION,
           'method':'same approved PubMedBERT P1 CLS + masked mean weighted-fragments 768d raw norm unit',
           'cpu_seconds':elapsed,'external_cost_usd':0,'cpu_threads':a.cpu_threads,
           'torch_version':torch.__version__,'transformers_version':__import__('transformers').__version__,
           'counts':dict(stats),'publication_authorized':False,'outputs':{}}
 for f in sorted(a.output_dir.iterdir()):
  if f.is_file():manifest['outputs'][f.name]={'sha256':sha(f),'bytes':f.stat().st_size}
 (a.output_dir/'manifest.private.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 print('DONE',a.shard_index,n,round(elapsed,2),dict(stats),'manifest_sha256',sha(a.output_dir/'manifest.private.json'),flush=True)
if __name__=='__main__':main()
