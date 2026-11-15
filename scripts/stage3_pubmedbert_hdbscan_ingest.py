#!/usr/bin/env python3
"""Source-free Stage 3 verifier: frozen PubMedBERT ZIP shards -> local PRIVATE 57,204 x 768 unit matrices.

Requires explicit local paths. Never emits private source rows to stdout or a public repository.
"""
import argparse, gzip,hashlib,io,json,os,sys,zipfile
from pathlib import Path
from collections import Counter
import numpy as np
from numpy.lib.format import open_memmap

def digest_bytes(b):return hashlib.sha256(b).hexdigest()
def digest_path(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def prepare(src,dst):
 if dst.exists():raise FileExistsError(f'New private output dir required: {dst}')
 dst.mkdir(parents=True,mode=0o700);os.chmod(dst,0o700)
 paths=sorted(src.glob('STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_SHARD_???.zip'))
 if len(paths)!=58:raise ValueError(f'Required exactly 58 PubMedBERT shards, got {len(paths)}')
 cls=open_memmap(dst/'cls_unit.float32.npy',mode='w+',dtype=np.float32,shape=(57204,768))
 mean=open_memmap(dst/'mean_unit.float32.npy',mode='w+',dtype=np.float32,shape=(57204,768))
 seen=set();roster=[];sha_list=[];states=Counter();row=0
 for k,path in enumerate(paths):
  if path.name!=f'STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_SHARD_{k:03d}.zip':raise ValueError(path.name)
  with zipfile.ZipFile(path) as z:
   if z.testzip() is not None:raise ValueError(f'ZIP CRC failed {path.name}')
   m=json.loads(z.read('manifest.private.json'))
   if m['shard_index']!=k or m['start_index']!=row or m['full_expected']!=57204:raise ValueError(f'Manifest cohort index mismatch {k}')
   if m['method']!='same approved PubMedBERT P1 CLS + masked mean weighted-fragments 768d raw norm unit':raise ValueError('Unexpected representation')
   for member,item in m['outputs'].items():
    b=z.read(member)
    if len(b)!=item['bytes'] or digest_bytes(b)!=item['sha256']:raise ValueError(f'Inner source SHA mismatch {path.name}:{member}')
   count=m['article_count'];end=row+count
   if end!=m['end_index_exclusive'] or count not in (1000,204):raise ValueError('Noncontiguous shard')
   a=np.load(io.BytesIO(z.read('cls_unit.npy')),allow_pickle=False)
   b=np.load(io.BytesIO(z.read('mean_unit.npy')),allow_pickle=False)
   if a.shape!=(count,768) or b.shape!=(count,768) or a.dtype!=np.float32 or b.dtype!=np.float32:raise ValueError('vector shape/dtype')
   for name,x in [('cls',a),('mean',b)]:
    if not np.isfinite(x).all():raise ValueError(f'{name} nonfinite in {k}')
    norms=np.linalg.norm(x.astype(np.float64),axis=1)
    if not np.all(np.abs(norms-1)<3e-5):raise ValueError(f'{name} nonunit in {k}')
   cls[row:end]=a;mean[row:end]=b
   text=gzip.decompress(z.read('article_status.private.jsonl.gz')).decode()
   lines=text.splitlines()
   if len(lines)!=count:raise ValueError(f'Status rows wrong count in shard {k}')
   for line in lines:
    r=json.loads(line)
    aid=r['article_id'];states[r['text_state']]+=1
    if aid in seen:raise ValueError(f'Duplicate ID: {aid}')
    seen.add(aid);roster.append({'article_id':aid,'text_state':r['text_state']})
   sha_list.append({'shard':k,'zip_sha256':digest_path(path),'zip_bytes':path.stat().st_size,
                    'article_count':count,'manifest_sha256':digest_bytes(z.read('manifest.private.json'))})
   row=end
   if k%10==9 or k==57:print(json.dumps({'loaded_shards':k+1,'rows':row}),flush=True)
 if row!=57204 or len(seen)!=57204:raise ValueError(f'Expected full cohort got {row}/{len(seen)}')
 cls.flush();mean.flush();del cls,mean
 status=dst/'cohort.article_roster.private.jsonl.gz'
 with open(status,'xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as gz:
  for r in roster:gz.write((json.dumps(r,sort_keys=True,separators=(',',':'))+'\n').encode())
 files=[dst/'cls_unit.float32.npy',dst/'mean_unit.float32.npy',status]
 manifest={'schema':'pro-adherence-stage3-pubmedbert-hdbscan-input-preflight/v1',
           'status':'FULL_FROZEN_INPUT_VERIFIED','date_utc':'2026-11-15',
           'article_count':57204,'dimension':768,'shards':sha_list,'source_states':dict(states),
           'outputs':{p.name:{'bytes':p.stat().st_size,'sha256':digest_path(p)} for p in files},
           'scope':'two original L2-unit embeddings (CLS, masked-Mean); no PCA, no projection; no scientific clustering acceptance'}
 p=dst/'input_manifest.private.json';p.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'result':'INPUT_VERIFIED','rows':row,'members':len(sha_list),'shard_zip_bytes':sum(x['zip_bytes'] for x in sha_list),'outputs_sha':{k:v['sha256'] for k,v in manifest['outputs'].items()},'text_states':dict(states)}),flush=True)
 return manifest
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
 a=ap.parse_args();prepare(a.source,a.out)
