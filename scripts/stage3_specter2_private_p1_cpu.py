"""Owner-authorized PRIVATE Stage3 SPECTER2 P1 pilot, 64 nested gate + exact 1000.

Never processes 57,204 full cohort, never uses the unsupported Adapters package,
never publishes article IDs, texts or embeddings. Exact pinned public CPU model.
"""
from __future__ import annotations
if not __debug__:
    raise SystemExit('SPECTER2 P1 -O disabled: integrity assertions are mandatory')
import argparse, gzip, hashlib, io, json, os, platform, resource, sys, time, zipfile
from collections import Counter,defaultdict
from importlib.metadata import version
from pathlib import Path
import numpy as np
import torch
from transformers import BertTokenizerFast
from pro_adherence.stage3_specter2_proximity_compat import CandidateBertOutputAdapter,pinned_weights_only
from stage3_specter2_public_end_to_end import load_pinned_base,verify_public_files

APPROVED_INPUT_ZIP_SHA='cc60cefdaa62a60712425b0f1ea1719338ec4250ec8bcaf1fd465329c677395e'
APPROVED_INPUT_MEMBER_SHA='1611f07e18ccf999493938e552d1a73ad049db931a11399fc01f0ca7b07dc053'
APPROVED_SAMPLE_SHA='b37128da2ef9fc6f15834c48a537b4ddb9ae7475dafcf7e0bb7fec586737d23b'
APPROVED_GRAPH_SHA='33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c'
P1_COUNT,SMOKE_COUNT,DIM,MAX_TOKENS,BATCH=1000,64,768,512,2
APPROVED_SOURCE_COUNTS={'pubmed':873,'woscc':90,'apa_psycinfo':37}
SMOKE_SEED='stage3-specter2-64-p1-20261113'

def sha_bytes(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def lock_check(public_bundle:Path)->dict:
 lockpath=public_bundle/'lock.json'
 lock=json.loads(lockpath.read_text())
 assert lock['python']=='3.13' and lock['architecture']=='linux-x86_64'
 wheels=lock['wheels']
 assert all((public_bundle/'wheels'/s['filename']).is_file() for s in wheels.values())
 for pkg,spec in wheels.items():
  f=public_bundle/'wheels'/spec['filename']
  if sha(f)!=spec['sha256'] or f.stat().st_size!=spec['bytes'] or version(pkg)!=spec['version']:
   raise RuntimeError('unsafe CPU runtime wheel/hash/version: '+pkg)
 for pkg,v in {'transformers':'5.22.2','tokenizers':'0.23.3','safetensors':'0.8.0','huggingface-hub':'2.4.0','numpy':'2.5.4'}.items():
  if version(pkg)!=v:raise RuntimeError('SPECTER2 runtime critical version mismatch: '+pkg)
 if torch.__version__!='2.10.0+cpu' or platform.machine().lower()!='x86_64' or sys.version_info[:2]!=(3,13):
  raise RuntimeError('unverified architecture/python/torch')
 return {'runtime_hash_lock_sha256':sha(lockpath),'wheel_count':len(wheels),
         'wheel_file_shas_verified':True,'installed_package_versions_match_wheel_lock':True,
         'torch':torch.__version__,'transformers':version('transformers'),
         'tokenizers':version('tokenizers'),'safetensors':version('safetensors'),
         'numpy':version('numpy'),'huggingface_hub':version('huggingface-hub')}

def private_inputs(inputzip:Path,samplezip:Path,graphzip:Path)->tuple[list[dict],dict[str,int]]:
 if sha(inputzip)!=APPROVED_INPUT_ZIP_SHA or sha(samplezip)!=APPROVED_SAMPLE_SHA:
  raise RuntimeError('frozen private P1 input identity mismatch')
 with zipfile.ZipFile(inputzip) as z:
  if z.testzip() is not None:raise RuntimeError('private input ZIP CRC fail')
  if sha_bytes(z.read('full_pubmedbert_inputs.private.jsonl.gz'))!=APPROVED_INPUT_MEMBER_SHA:
   raise RuntimeError('full input frozen member SHA fail')
 with gzip.open(samplezip,'rt',encoding='utf-8') as f:
  rows=[json.loads(x) for x in f]
 if len(rows)!=P1_COUNT or len({r['article_id'] for r in rows})!=P1_COUNT:
  raise RuntimeError('approved 1000 subset membership/uniqueness mismatch')
 if dict(Counter(x['source_id'] for x in rows))!=APPROVED_SOURCE_COUNTS:
  raise RuntimeError('approved P1 source count mismatch')
 if any(x['text_state'] not in ('title_abstract','title_only') or not x['title'] for x in rows):
  raise RuntimeError('unresolved or empty private pilot text')
 if any(x['text_state']=='title_only' and x['abstract'] for x in rows):
  raise RuntimeError('title-only row must not contain abstract')
 if sha(graphzip)!=APPROVED_GRAPH_SHA:raise RuntimeError('frozen graph ZIP SHA mismatch')
 degree=Counter()
 with zipfile.ZipFile(graphzip) as z:
  if z.testzip() is not None:raise RuntimeError('frozen graph ZIP CRC mismatch')
  with gzip.open(z.open('node2vec_training_edges.private.jsonl.gz'),'rt') as f:
   n=0
   for line in f:
    r=json.loads(line);degree[r['source_article_id']]+=1;degree[r['target_article_id']]+=1;n+=1
  if n!=328298:raise RuntimeError('approved graph edge count mismatch')
 if sum(degree[r['article_id']]==0 for r in rows)!=252:
  raise RuntimeError('approved pilot isolates mismatch')
 return rows,degree

def choose_64(rows:list[dict], degree:dict[str,int])->list[int]:
 def rank(r):return hashlib.sha256((SMOKE_SEED+':'+r['article_id']).encode()).hexdigest()
 def labels(r):
  out=['source_'+r['source_id'],'text_'+r['text_state']]
  d=degree[r['article_id']]
  out.append('degree_zero' if d==0 else 'degree_1_4' if d<=4 else 'degree_5_19' if d<20 else 'degree_20plus')
  if r['peer_review_unknown']:out.append('peer_unknown')
  if r['wos_nr_cr_mismatch']:out.append('wos_mismatch')
  if len(r.get('abstract') or '')>=2500:out.append('long_text')
  return out
 buckets=defaultdict(list)
 for i,r in enumerate(rows):
  for a in labels(r):buckets[a].append(i)
 selected={}
 for tag in sorted(buckets):
  for i in sorted(buckets[tag],key=lambda i:(rank(rows[i]),rows[i]['article_id']))[:3]:
   if len(selected)>=SMOKE_COUNT:break
   selected[i]=True
 for i in sorted(range(len(rows)),key=lambda i:(rank(rows[i]),rows[i]['article_id'])):
  if len(selected)>=SMOKE_COUNT:break
  selected[i]=True
 assert len(selected)==SMOKE_COUNT
 return sorted(selected)

def text_of(r):
 return r['title'] + '[SEP]' + (r.get('abstract') or '')

def encoded_tokens(tokenizer, rows):
 report=[]
 for r in rows:
  text=r['title']+tokenizer.sep_token+(r.get('abstract') or '')
  total=len(tokenizer(text,add_special_tokens=True,truncation=False)['input_ids'])
  clipped=len(tokenizer(text,add_special_tokens=True,truncation=True,max_length=MAX_TOKENS)['input_ids'])
  if clipped>MAX_TOKENS or total<clipped:
   raise RuntimeError('token-loss accounting invalid')
  report.append({'total':total,'encoded':clipped,'lost':total-clipped,'text_sha256':sha_bytes(text.encode('utf-8'))})
 return report

def model_vectors(model,tokenizer,rows:list[dict]):
 arrays=[]
 with torch.inference_mode():
  for pos in range(0,len(rows),BATCH):
   texts=[r['title']+tokenizer.sep_token+(r.get('abstract') or '') for r in rows[pos:pos+BATCH]]
   tok=tokenizer(texts,return_tensors='pt',padding=True,truncation=True,max_length=MAX_TOKENS,
                 return_token_type_ids=False)
   out=model(**tok).last_hidden_state[:,0,:].detach().to(torch.float32).numpy().copy()
   if out.shape!=(len(texts),DIM) or not np.isfinite(out).all():
    raise RuntimeError('invalid finite first token 768d output')
   arrays.append(out)
 return np.ascontiguousarray(np.concatenate(arrays,axis=0),dtype=np.float32)

def numeric(raw):
 norms=np.linalg.norm(raw.astype(np.float64),axis=1)
 if not np.isfinite(norms).all() or np.any(norms<=0):raise RuntimeError('invalid raw norm')
 unit=np.ascontiguousarray((raw.astype(np.float64)/norms[:,None]).astype(np.float32))
 unorm=np.linalg.norm(unit.astype(np.float64),axis=1)
 if not np.allclose(unorm,1,atol=1e-5,rtol=0):raise RuntimeError('bad unit vector norm')
 if not np.allclose(unit.astype(np.float64)*norms[:,None],raw.astype(np.float64),atol=3e-6,rtol=3e-6):
  raise RuntimeError('raw-unit reconstruct failed')
 return norms.astype(np.float64),unit

def numpy_bytes(arr):
 b=io.BytesIO();np.save(b,arr,allow_pickle=False);return b.getvalue()
def stable_zip(z,name,raw):
 info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o600<<16
 z.writestr(info,raw)
def peak_rss_mib():return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2)

def run(args):
 if not args.owner_p1_scope:raise RuntimeError('owner P1 authorization flag required')
 if args.out.exists() or Path(str(args.out)+'.incomplete').exists():raise RuntimeError('no overwrite')
 if os.environ.get('HF_HUB_OFFLINE')!='1' or os.environ.get('TRANSFORMERS_OFFLINE')!='1':
  raise RuntimeError('model inference must be offline')
 if 'adapters' in sys.modules:raise RuntimeError('old Adapters package not allowed')
 mem=Path('/sys/fs/cgroup/memory.max')
 if mem.exists() and mem.read_text().strip()!='max':
  limit=int(mem.read_text());current=int(Path('/sys/fs/cgroup/memory.current').read_text())
  if limit-current<1_000_000_000:raise RuntimeError('insufficient CPU memory headroom')
 else:limit=None
 runtime=lock_check(args.bundle)
 t0=time.monotonic()
 rows,degree=private_inputs(args.input_zip,args.sample,args.graph)
 smoke_ix=choose_64(rows,degree)
 public_evidence=json.loads(args.evidence.read_text())
 verify_public_files(args.bundle/'base',args.bundle/'adapter'/'pytorch_adapter.bin',public_evidence)
 real_adapter=pinned_weights_only(args.bundle/'adapter'/'pytorch_adapter.bin')
 torch.set_num_threads(2);torch.manual_seed(20261113)
 base,load_report=load_pinned_base(args.bundle/'base')
 tokenizer=BertTokenizerFast.from_pretrained(str(args.bundle/'base'),local_files_only=True)
 originals=[layer.output for layer in base.encoder.layer]
 if len(originals)!=12:raise RuntimeError('not exactly 12 BERT adapter layers')
 for i,layer in enumerate(base.encoder.layer):
  layer.output=CandidateBertOutputAdapter(originals[i],real_adapter,i).eval()
 base.requires_grad_(False);base.eval()
 del real_adapter
 print(json.dumps({'status':'PRIVATE_P1_NUMERIC64_START','selection':len(smoke_ix)},sort_keys=True),flush=True)
 start=time.monotonic()
 smoke_rows=[rows[i] for i in smoke_ix]
 smoke_audit=encoded_tokens(tokenizer,smoke_rows)
 smoke_raw=model_vectors(base,tokenizer,smoke_rows)
 smoke_norm,smoke_unit=numeric(smoke_raw)
 replay_raw=model_vectors(base,tokenizer,smoke_rows[:8])
 if not np.allclose(smoke_raw[:8],replay_raw,atol=5e-6,rtol=5e-6):
  raise RuntimeError('smoke numeric deterministic replay failed')
 smoke_sec=round(time.monotonic()-start,3)
 print(json.dumps({'status':'PRIVATE_P1_NUMERIC64_PASS','seconds':smoke_sec,'rss_mib':peak_rss_mib()},sort_keys=True),flush=True)
 start=time.monotonic()
 token_stats=encoded_tokens(tokenizer,rows)
 all_raw=model_vectors(base,tokenizer,rows)
 all_norm,all_unit=numeric(all_raw)
 if not np.allclose(all_raw[smoke_ix],smoke_raw,atol=5e-5,rtol=3e-5):
  raise RuntimeError('smoke/full vector row alignment or numerical drift')
 compute_sec=round(time.monotonic()-start,3)
 print(json.dumps({'status':'PRIVATE_P1_1000_VECTORS_PASS','seconds':compute_sec,'rss_mib':peak_rss_mib()},sort_keys=True),flush=True)
 n_source=Counter(x['source_id'] for x in rows)
 full_stats={
  'article_count':len(rows),'smoke_count':SMOKE_COUNT,'source_counts':dict(n_source),
  'text_state_counts':dict(Counter(r['text_state'] for r in rows)),
  'smoke_source_counts':dict(Counter(r['source_id'] for r in smoke_rows)),
  'isolates_in_1000':sum(degree[r['article_id']]==0 for r in rows),
  'isolate_has_valid_semantic_vector':True,
  'truncated_count':sum(s['lost']>0 for s in token_stats),
  'title_only_count':sum(r['text_state']=='title_only' for r in rows),
  'token_count_min':min(x['total'] for x in token_stats),
  'token_count_max':max(x['total'] for x in token_stats),
  'lost_tokens_total':sum(x['lost'] for x in token_stats),
  'lost_tokens_max':max(x['lost'] for x in token_stats),
  'smoke_truncated_count':sum(x['lost']>0 for x in smoke_audit),
  'smoke_lost_tokens_total':sum(x['lost'] for x in smoke_audit),
  'smoke_seconds':smoke_sec,'full_1000_seconds':compute_sec,
  'peak_rss_mib':peak_rss_mib(),'cgroup_memory_limit_bytes':limit,
  'torch_device':'cpu','batch_size':BATCH,'bert_layers':12,
  '64_replay_first8_max_abs':float(np.max(np.abs(smoke_raw[:8]-replay_raw))),
  '64_vs_full1000_max_abs':float(np.max(np.abs(all_raw[smoke_ix]-smoke_raw))),
  'all_finite_raw_norm_unit':True,'all_768d_ready':True,
  'l2_unit_norm_max_abs_deviation':float(np.max(np.abs(np.linalg.norm(all_unit.astype(np.float64),axis=1)-1))),
 }
 rosterbuf=io.BytesIO()
 with gzip.GzipFile(filename='',fileobj=rosterbuf,mode='wb',mtime=0,compresslevel=6) as gz:
  for i,(r,s) in enumerate(zip(rows,token_stats)):
   obj={'canonical_article_id':r['article_id'],'vector_row':i,'status':'ready',
        'source_id':r['source_id'],'source_record_id':r['source_record_id'],
        'raw_export_sha256':r['raw_export_sha256'],'raw_record_ordinal':r['raw_record_ordinal'],
        'title_only':r['text_state']=='title_only','text_sha256':s['text_sha256'],
        'untruncated_tokens':s['total'],'encoded_tokens':s['encoded'],'tokens_lost':s['lost'],
        'peer_review_unknown':r['peer_review_unknown'],'wos_nr_cr_mismatch':r['wos_nr_cr_mismatch'],
        'p1_64_numeric_gate':i in smoke_ix}
   gz.write((json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
 files={'raw.float32.npy':numpy_bytes(all_raw),'raw_l2_norm.float64.npy':numpy_bytes(all_norm),
        'unit.float32.npy':numpy_bytes(all_unit),'pilot_1000_status.private.jsonl.gz':rosterbuf.getvalue()}
 report={'schema':'pro-adherence-stage3-specter2-private-p1-1000-report/v1',
         'status':'64_NUMERIC_GATE_AND_APPROVED_P1_1000_PASS',
         'model':{'base_revision':'3447645e1def9117997203454fa4495937bfbd83',
                  'adapter_revision':'2081559630a80fc5851d8f798a05ba81e9468089',
                  'proximity_enabled':True,'finetuned':False,'encoder_first_token_768d':True,
                  'base_loading':load_report},'counts':full_stats,'runtime':runtime,
         'frozen_private_input_archive_sha256':APPROVED_INPUT_ZIP_SHA,
         'frozen_sample_sha256':APPROVED_SAMPLE_SHA,'frozen_graph_sha256':APPROVED_GRAPH_SHA,
         'public_official_numeric_reference':'PUBLIC_OFFICIAL_ADAPTER_REFERENCE_NUMERIC_PASS_TEMPORARY_UNSUPPORTED_ENV_ONLY',
         'complete_private_corpus_inference_executed':False,'full_57204_production_vectors_created':False,
         'stage3_closed':False,'publication_authorized':False,'pr_merge_authorized':False}
 report_bytes=(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
 files['report.private.json']=report_bytes
 identity={'sha256_pilot_input':APPROVED_SAMPLE_SHA,'runtime_lock':runtime['runtime_hash_lock_sha256'],
           'sha256_raw_vectors':sha_bytes(files['raw.float32.npy']),
           'sha256_script':sha(Path(__file__)),'base':'801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc',
           'adapter':'5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'}
 manifest={'schema':'pro-adherence-stage3-specter2-p1-cpu-private-asset/v1',
           'status':'P1_COMPLETE_LOCAL_QA_AWAITING_INDEPENDENT_REMOTE_READBACK',
           'model_identity_hash':sha_bytes(json.dumps(identity,sort_keys=True).encode()),
           'code_sha256':sha(Path(__file__)),'pilot_sample_sha256':APPROVED_SAMPLE_SHA,
           'public_bundle_wheel_lock_sha256':runtime['runtime_hash_lock_sha256'],
           'files':{name:{'sha256':sha_bytes(b),'bytes':len(b)} for name,b in files.items()},
           'owner_scoped_p1_64_and_1000_authorized':True,'full_inference_authorized':False,
           'public_release_authorized':False,'stage_gate_authorized':False,
           'quality':'all_64_smoke_and_1000_numeric_contracts_pass'}
 files['manifest.private.json']=(json.dumps(manifest,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
 tmp=Path(str(args.out)+'.incomplete');args.out.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(tmp,'w') as z:
  for name,b in files.items():stable_zip(z,name,b)
 with zipfile.ZipFile(tmp) as z:
  if z.testzip() is not None:raise RuntimeError('private P1 output archive CRC mismatch')
  for name,s in manifest['files'].items():
   if sha_bytes(z.read(name))!=s['sha256'] or len(z.read(name))!=s['bytes']:
    raise RuntimeError('archive member SHA/readback mismatch: '+name)
  if np.load(io.BytesIO(z.read('raw.float32.npy')),allow_pickle=False).shape!=(P1_COUNT,DIM):
   raise RuntimeError('private ZIP vector readback shape mismatch')
 tmp.replace(args.out)
 print(json.dumps({'status':'PRIVATE_SPECTER2_P1_LOCAL_QA_PASS','zip_sha256':sha(args.out),
                   'zip_bytes':args.out.stat().st_size,'model_identity_hash':manifest['model_identity_hash'],
                   'peak_rss_mib':peak_rss_mib(),'seconds_total':round(time.monotonic()-t0,3)},sort_keys=True),flush=True)
 return report,manifest

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--bundle',type=Path,required=True)
 p.add_argument('--input-zip',type=Path,required=True)
 p.add_argument('--sample',type=Path,required=True)
 p.add_argument('--graph',type=Path,required=True)
 p.add_argument('--evidence',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 p.add_argument('--owner-p1-scope',action='store_true')
 args=p.parse_args();run(args)
if __name__=='__main__':main()
