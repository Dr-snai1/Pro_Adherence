"""Ephemeral PUBLIC-ONLY SPECTER2 official Adapters 1.3.0 numerical witness.

This script deliberately needs old UNSUPPORTED Transformers 4.57.6, strictly
as an isolated, synthetic-only reference; never use this runtime to process
private documents or as an endorsed production backend. All downloaded public
model/adapter files must match exact approved immutable SHA before importing
the upstream package and executing model code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

import numpy as np
import torch

BASE_SHA = '801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc'
ADAPTER_SHA = '5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'
ADAPTER_CONFIG_SHA = '1065ad610a661c5169f05d81040fe14429d2cc7ecdf83ed654dca4a62aaf9a8c'
VALIDATED_REF_TRANSFORMERS = '4.57.6'
VALIDATED_REF_ADAPTERS = '1.3.0'
N, DIM = 3,768

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):
            h.update(chunk)
    return h.hexdigest()

def witness(base:Path, adapter:Path, ids:Path, safe_vectors:Path)->dict:
    if os.environ.get('HF_HUB_OFFLINE')!='1':
        raise RuntimeError('reference runtime MUST run offline')
    if platform.machine().lower() not in ('x86_64','amd64'):
        raise RuntimeError('reference architecture not x86-64')
    for file,want in [(base/'pytorch_model.bin',BASE_SHA),
                      (adapter/'pytorch_adapter.bin',ADAPTER_SHA),
                      (adapter/'adapter_config.json',ADAPTER_CONFIG_SHA)]:
        if not file.is_file() or digest(file)!=want:
            raise RuntimeError('unverified public frozen reference checkpoint: '+str(file))
    import adapters
    import transformers
    from adapters import AutoAdapterModel
    from importlib.metadata import version
    if transformers.__version__!=VALIDATED_REF_TRANSFORMERS or version('adapters')!=VALIDATED_REF_ADAPTERS:
        raise RuntimeError('wrong upstream temporary reference package version')
    if torch.__version__!='2.10.0+cpu':
        raise RuntimeError('wrong reference Torch')
    with np.load(ids,allow_pickle=False) as d:
        tokens={k:torch.from_numpy(d[k].copy()).to(torch.long) for k in d.files}
    expected=np.load(safe_vectors,allow_pickle=False)
    if expected.shape!=(N,DIM) or tokens['input_ids'].shape[0]!=N:
        raise RuntimeError('public synthetic comparison inputs changed')
    torch.manual_seed(20261113)
    torch.set_num_threads(2)
    # Critical: local_files_only; all underlying base weights SHA checked above.
    model=AutoAdapterModel.from_pretrained(str(base),local_files_only=True,
                                           use_safetensors=False,
                                           attn_implementation='eager')
    loaded=model.load_adapter(str(adapter),load_as='proximity',set_active=True)
    if not loaded:
        raise RuntimeError('official proximity adapter did not load')
    if 'proximity' not in str(model.active_adapters).lower():
        raise RuntimeError('official proximity adapter not activated')
    model.eval()
    with torch.inference_mode():
        actual=model(**tokens).last_hidden_state[:,0,:].detach().cpu().to(torch.float32).numpy()
    if actual.shape!=(N,DIM) or not np.isfinite(actual).all():
        raise RuntimeError('official reference output invalid')
    if not np.isfinite(expected).all():
        raise RuntimeError('safe-runtime synthetic witness contains nonfinite values')
    diff=np.abs(actual.astype('float64')-expected.astype('float64'))
    max_abs=float(diff.max())
    cos=np.sum(actual.astype('float64')*expected.astype('float64'),axis=1)/(
        np.linalg.norm(actual.astype('float64'),axis=1)*
        np.linalg.norm(expected.astype('float64'),axis=1))
    min_cos=float(cos.min())
    same=np.allclose(actual,expected,atol=5e-5,rtol=3e-5)
    if not same or max_abs>5e-5 or min_cos < 0.999999:
        raise RuntimeError(f'official reference NUMERIC FAIL maxabs={max_abs:.9g}, mincos={min_cos:.12g}')
    return {
      'schema':'pro-adherence-stage3-specter2-public-official-adapter-reference-equivalence/v1',
      'status':'PUBLIC_OFFICIAL_ADAPTER_REFERENCE_NUMERIC_PASS_TEMPORARY_UNSUPPORTED_ENV_ONLY',
      'approved_base_sha256':BASE_SHA,'approved_adapter_sha256':ADAPTER_SHA,
      'adapter_config_sha256':ADAPTER_CONFIG_SHA,
      'actual_official_package':'adapters==1.3.0',
      'temporary_reference_transformers':'4.57.6',
      'official_active_adapter':str(model.active_adapters),
      'safe_candidate_output_sha256':hashlib.sha256(expected.tobytes()).hexdigest(),
      'official_output_sha256':hashlib.sha256(actual.tobytes()).hexdigest(),
      'shape':list(actual.shape),'max_abs_safe_vs_official':max_abs,
      'min_cosine_safe_vs_official':min_cos,
      'numerical_tolerance':{'atol':5e-5,'rtol':3e-5,'max_abs_ceiling':5e-5,'min_cosine':0.999999},
      'gates':{
          'official_activated_proximity_public_synthetic_equivalence_verified':True,
          'temporary_old_transformers_reference_is_approved_for_private_inference':False,
          'permanent_secure_production_runtime_pinned_hash_lock_verified':False,
          'private_specter2_inference_authorized':False,
          'production_vectors_generated':False,
          'publication_authorized':False,
          'stage3_closed':False,
      }
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--adapter',type=Path,required=True)
    p.add_argument('--tokens',type=Path,required=True)
    p.add_argument('--safe-vectors',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise RuntimeError('refuse official public witness overwrite')
    r=witness(a.base,a.adapter,a.tokens,a.safe_vectors)
    a.out.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(r['status'])

if __name__=='__main__':main()
