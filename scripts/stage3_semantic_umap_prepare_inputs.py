#!/usr/bin/env python3
"""Rebuild approved frozen 57,204 x 768 semantic vectors, without refitting the encoders.
Source-free: requires owner-private ZIP archives and acceptance manifests locally.
Results remain private; never commit matrices to Git.
"""
from pathlib import Path
import hashlib, gzip, io, json, os, zipfile
import numpy as np

N=57204; D=768
EXPECTED={
 'pubmedbert_cls':'1713705e982ba6a7c804be47ae7dcf21aee7e9a32fb151753c66a1e42eeb41fc',
 'pubmedbert_mean':'54c09c019c748adf8f0a2125082c63ea56de9d98f30b82975c0c82b97a506204',
 'specter2_proximity':'10ec4ad05e85b59e8ae204d0d0fa273537dd48dea1baf974d9cce4c08d6fff42',
}
ROSTER_SHA='3435a2e83d44e42db6c0f7de685f3e1e80ca6b4762b665af2daa9eef2fc09acf'

def sha(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def digest(b):return hashlib.sha256(b).hexdigest()

def private_chmod(path):os.chmod(path,0o600)

def run(root:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(out,0o700)
    input_doc=json.loads((root/'STAGE3_20261115_PRIVATE_PUBMEDBERT_HDBSCAN_input_manifest.json').read_text())
    spec_doc=json.loads((root/'STAGE3_20261114_PRIVATE_SPECTER2_FULL_57204_MANIFEST.json').read_text())
    rs=root/'STAGE3_20261115_PRIVATE_PUBMEDBERT_HDBSCAN_roster.jsonl.gz'
    roster=[json.loads(v) for v in gzip.open(rs,'rt')]
    assert len(roster)==N and len({r['article_id'] for r in roster})==N
    matrices={v:out/f'{v}_unit.float32.npy' for v in EXPECTED}
    for name,p in matrices.items():
        if p.exists():raise FileExistsError(f'Preserving existing output: {p}')
    arr={name:np.lib.format.open_memmap(path,mode='w+',dtype=np.float32,shape=(N,D)) for name,path in matrices.items()}
    records=[]
    offset=0
    assert len(input_doc['shards'])==58 and len(spec_doc['shard_files'])==58
    for i in range(58):
        pf=root/f'STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_SHARD_{i:03d}.zip'
        sf=(root/f'STAGE3_20261113_PRIVATE_SPECTER2_FULL_SHARD_{i:03d}.zip') if i<49 else (root/f'STAGE3_20261114_PRIVATE_SPECTER2_FULL_SHARD_{i:03d}.zip')
        mi=input_doc['shards'][i]; sm=spec_doc['shard_files'][i]
        assert pf.stat().st_size==mi['zip_bytes'] and sha(pf)==mi['zip_sha256'],('pubmedbert',i)
        assert sf.stat().st_size==sm['size_bytes'] and sha(sf)==sm['sha256'],('specter2',i)
        with zipfile.ZipFile(pf) as z:
            assert z.testzip() is None,('pubmedbert_zip_crc',i)
            m=json.loads(z.read('manifest.private.json'))
            assert m['start_index']==offset and m['article_count']==min(1000,N-offset)
            states=[json.loads(v) for v in gzip.decompress(z.read('article_status.private.jsonl.gz')).splitlines()]
            assert len(states)==m['article_count']
            for j,r in enumerate(states):
                assert r['article_id']==roster[offset+j]['article_id']
                assert r['text_state']==roster[offset+j]['text_state']
            for view,member in [('pubmedbert_cls','cls_unit.npy'),('pubmedbert_mean','mean_unit.npy')]:
                data=z.read(member)
                assert len(data)==m['outputs'][member]['bytes'] and digest(data)==m['outputs'][member]['sha256']
                block=np.load(io.BytesIO(data),allow_pickle=False)
                assert block.shape==(len(states),D) and block.dtype==np.float32 and np.isfinite(block).all()
                arr[view][offset:offset+len(block)]=block
        with zipfile.ZipFile(sf) as z:
            assert z.testzip() is None,('specter_zip_crc',i)
            m=json.loads(z.read('manifest.private.json'))
            assert m['global_start']==offset and m['count']==len(states)
            spec_states=[json.loads(v) for v in gzip.decompress(z.read('status.private.jsonl.gz')).splitlines()]
            assert len(spec_states)==len(states)
            for j,r in enumerate(spec_states):
                assert r['canonical_article_id']==roster[offset+j]['article_id']
                assert r['text_state']==roster[offset+j]['text_state']
                assert r['vector_row_global']==offset+j
            data=z.read('unit.float32.npy')
            assert len(data)==m['files']['unit.float32.npy']['bytes'] and digest(data)==m['files']['unit.float32.npy']['sha256']
            block=np.load(io.BytesIO(data),allow_pickle=False)
            assert block.shape==(len(states),D) and block.dtype==np.float32 and np.isfinite(block).all()
            arr['specter2_proximity'][offset:offset+len(block)]=block
        records.append({'shard':i,'rows':len(states),'pubmedbert_zip_sha256':mi['zip_sha256'],'specter2_zip_sha256':sm['sha256']})
        offset+=len(states)
        if i%10==0 or i==57:print(json.dumps({'stage':'frozen_rebuild','shard':i,'rows':offset}),flush=True)
    assert offset==N
    for a in arr.values():a.flush()
    del arr
    results={}
    for name,p in matrices.items():
        private_chmod(p)
        h=sha(p)
        assert h==EXPECTED[name],('source sha mismatch',name,h,EXPECTED[name])
        a=np.load(p,mmap_mode='r')
        norm=np.linalg.norm(np.asarray(a[::71],dtype=np.float64),axis=1)
        assert abs(norm-1).max()<3e-5
        results[name]={'path':str(p),'sha256':h,'shape':[N,D],'dtype':'float32','bytes':p.stat().st_size}
    data={'schema':'stage3-umap-hdbscan-frozen-input-preflight/v1','status':'FROZEN_INPUT_REBUILT_VERIFIED__UMAP_NOT_RUN',
          'source':{'pubmedbert_acceptance_manifest':'STAGE3_20261115_PRIVATE_PUBMEDBERT_HDBSCAN_input_manifest.json',
                    'specter2_acceptance_manifest':'STAGE3_20261114_PRIVATE_SPECTER2_FULL_57204_MANIFEST.json',
                    'roster_file':rs.name,'roster_file_sha256':sha(rs),'expected_article_roster_sha256':ROSTER_SHA},
          'matrices':results,'shard_checks':records,'notes':'No dimensionality reduction or clustering conducted in this preflight.'}
    target=out/'frozen_input_preflight.private.json'
    target.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n');private_chmod(target)
    print(json.dumps({'status':data['status'],'matrices':{x:y['sha256'] for x,y in results.items()},'manifest_sha256':sha(target)}),flush=True)

if __name__=='__main__':run(Path('/mnt/data'),Path('/mnt/data/stage3_umap_hdbscan_20261127_private'))
