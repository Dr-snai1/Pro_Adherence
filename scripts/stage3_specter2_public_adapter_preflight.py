"""Read-only public pinned SPECTER2 proximity checkpoint preflight. No inference."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ADAPTER_REPO = 'allenai/specter2'
ADAPTER_REV = '2081559630a80fc5851d8f798a05ba81e9468089'
BASE_REPO = 'allenai/specter2_base'
BASE_REV = '3447645e1def9117997203454fa4495937bfbd83'
# Published HF checkpoint SHA256; actual content must match to pass.
WEIGHTS_SHA = '5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'
SEMANTICS = dict(non_linearity='relu', reduction_factor=16, mh_adapter=False,
    output_adapter=True, ln_before=False, ln_after=False, original_ln_before=True,
    original_ln_after=True, residual_before_ln=True, adapter_residual_before_ln=False,
    scaling=1.0, leave_out=[], use_gating=False, is_parallel=False,
    cross_adapter=False, phm_layer=False)

class Rejected(ValueError): pass

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()

def check_config(path):
    raw=Path(path).read_bytes()
    if len(raw)>65536: raise Rejected('unexpected config size')
    obj=json.loads(raw)
    c=obj.get('config')
    if not isinstance(c,dict):raise Rejected('missing adapter config')
    for k,v in SEMANTICS.items():
        if k not in c or c[k]!=v or type(c[k]) is not type(v):
            raise Rejected('unexpected adapter semantics: '+k)
    for k,v in {'hidden_size':768,'model_class':'BertAdapterModel','model_type':'bert',
                'name':'[PRX]','version':'3.1.0',
                'model_name':'allenai/specter_plus_plus'}.items():
        if obj.get(k)!=v: raise Rejected('wrong adapter identity: '+k)
    return {'sha256':hashlib.sha256(raw).hexdigest(),'semantic_fields':len(SEMANTICS),
            'checkpoint_historical_base_alias':obj['model_name']}

def check_weights(path):
    path=Path(path)
    if digest(path)!=WEIGHTS_SHA:raise Rejected('checkpoint SHA256 mismatch')
    if path.stat().st_size>12*1024*1024:raise Rejected('checkpoint too large')
    if not zipfile.is_zipfile(path):raise Rejected('checkpoint not PyTorch ZIP')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise Rejected('checkpoint ZIP CRC failure')
        entries=z.namelist()
        if not entries or len(entries)>512:raise Rejected('unexpected checkpoint inventory')
        for name in entries:
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name:
                raise Rejected('unsafe checkpoint member path')
        if not any(n.endswith('/data.pkl') or n=='data.pkl' for n in entries):
            raise Rejected('checkpoint missing data.pkl')
    return {'sha256':WEIGHTS_SHA,'size_bytes':path.stat().st_size,
            'zip_crc':'PASS','zip_members':len(entries),'pickle_executed':False}

def audit(config,weights=None):
    c=check_config(config)
    w=check_weights(weights) if weights else None
    return {'schema':'pro-adherence-stage3-specter2-public-adapter-preflight/v1',
            'model':{'adapter_repo':ADAPTER_REPO,'adapter_revision':ADAPTER_REV,
                     'base_repo':BASE_REPO,'base_revision':BASE_REV},
            'config':c,'weights':w,
            'status':'ADAPTER_BYTES_VERIFIED_RUNTIME_BLOCKED' if w else 'CONFIG_ONLY_RUNTIME_BLOCKED',
            'gates':{'supported_safe_adapter_runtime':False,'base_weight_bytes_verified':False,
                     'numeric_equivalence_verified':False,'inference_authorized':False,
                     'production_vectors_created':False,'publication_authorized':False,
                     'stage3_closed':False}}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--weights',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise Rejected('no overwrite of previous evidence')
    r=audit(a.config,a.weights)
    a.output.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(r['status'])

if __name__=='__main__':main()
