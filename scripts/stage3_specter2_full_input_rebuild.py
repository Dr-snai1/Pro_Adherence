#!/usr/bin/env python3
"""Losslessly rebuild full 57,204 x 768 SPECTER2 unit vectors from frozen shards.
All data stay private. Code contains no private observations.
"""
import json,glob,gzip,io,os,hashlib,zipfile,collections
from pathlib import Path
import numpy as np

def sha(f):
 with open(f,'rb') as b:return hashlib.file_digest(b,'sha256').hexdigest()

def main():
 root=Path('/mnt/data')
 src=root/'STAGE3_20261114_PRIVATE_SPECTER2_FULL_57204_MANIFEST.json'
 mf=json.loads(src.read_text());assert mf['article_count']==57204 and len(mf['shard_files'])==58
 out=root/'stage3_full_semantic_20261115_private';os.makedirs(out,exist_ok=True)
 matrix=out/'specter2_proximity_unit.float32.npy'
 if matrix.exists():raise FileExistsError(matrix)
 rosters=[json.loads(line) for line in gzip.open(root/'stage3_pubmedbert_hdbscan_20261115_private/cohort.article_roster.private.jsonl.gz','rt')]
 assert len(rosters)==57204
 X=np.lib.format.open_memmap(matrix,mode='w+',dtype=np.float32,shape=(57204,768))
 checks=[]; global_records=0
 files=sorted(root.glob('STAGE3_2026111[34]_PRIVATE_SPECTER2_FULL_SHARD_*.zip'))
 assert len(files)==58,[str(x) for x in files]
 for i,(f,source_shard) in enumerate(zip(files,mf['shard_files'])):
  assert f.name.endswith(f'_{i:03d}.zip'),f.name
  assert f.stat().st_size==source_shard['size_bytes'],(i,f.stat().st_size,source_shard['size_bytes'])
  assert sha(f)==source_shard['sha256'],i
  with zipfile.ZipFile(f) as z:
   assert z.testzip() is None
   mn=json.loads(z.read('manifest.private.json'))
   assert mn['shard_index']==i and mn['global_start']==global_records
   for k,v in mn['files'].items():
    b=z.read(k)
    assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256'],(i,k)
   block=np.load(io.BytesIO(z.read('unit.float32.npy')))
   assert block.shape==(mn['count'],768) and block.dtype==np.float32
   assert np.isfinite(block).all()
   norms=np.linalg.norm(block.astype(np.float64),axis=1)
   assert np.max(np.abs(norms-1.0))<3e-5
   recs=[json.loads(line) for line in gzip.decompress(z.read('status.private.jsonl.gz')).splitlines()]
   assert len(recs)==len(block)
   for j,r in enumerate(recs):
    assert r['vector_row_global']==global_records+j and r['vector_row_in_shard']==j
    assert r['canonical_article_id']==rosters[global_records+j]['article_id']
    assert r['text_state']==rosters[global_records+j]['text_state']
   X[global_records:global_records+len(block),:]=block
   global_records+=len(block)
   checks.append({'shard':i,'rows':len(block),'zip_sha256':sha(f),'source':f.name})
  print(json.dumps({'verified_specter_shard':i,'rows_done':global_records}),flush=True)
 assert global_records==57204
 X.flush();del X
 manifest={'schema':'stage3-specter2-full-unit-rebuild-private/v1','status':'FULL_57204_INPUT_INTEGRITY_VERIFIED',
           'article_count':57204,'dimension':768,'source_manifest_sha256':sha(src),
           'reassembled_matrix_sha256':sha(matrix),'roster_sha256':sha(root/'stage3_pubmedbert_hdbscan_20261115_private/cohort.article_roster.private.jsonl.gz'),
           'per_shard':checks,'code_sha256':sha(__file__)}
 (out/'specter2_input_manifest.private.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'result':'FULL_SPECTER2_REBUILD_PASS','sha256':manifest['reassembled_matrix_sha256'],'size':matrix.stat().st_size}),flush=True)
if __name__=='__main__':main()
