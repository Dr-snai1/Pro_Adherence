"""Public pinned adapter, 12-layer source-equation math probe on synthetic tensors ONLY.

This is NOT numeric equivalence to an upstream activated SPECTER2 model, does
NOT load base pretrained weights or private records and authorizes no inference.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F

APPROVED_WEIGHT_SHA = '5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'
LAYERS=12


def load_candidate(path:Path):
    spec=importlib.util.spec_from_file_location('specter2_compat_candidate',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe(weights:Path,compat_path:Path)->dict:
    module=load_candidate(compat_path)
    tensors=module.pinned_weights_only(weights)  # exact SHA before torch.load(weights_only=True)
    assert len(tensors)==48
    torch.manual_seed(20261113)
    torch.set_num_threads(2)
    max_diffs=[]
    activations=[]
    class SyntheticOutput(nn.Module):
        def __init__(self):
            super().__init__()
            self.dense=nn.Linear(3072,768)
            self.dropout=nn.Dropout(p=0.0)
            self.LayerNorm=nn.LayerNorm(768,eps=1e-12)
    for layer_index in range(LAYERS):
        base=SyntheticOutput().eval()
        candidate=module.CandidateBertOutputAdapter(base,tensors,layer_index).eval()
        x=torch.randn(1,3,3072)
        residual=torch.randn(1,3,768)
        prefix=f'bert.encoder.layer.{layer_index}.output.adapters.[PRX].'
        with torch.no_grad():
            actual=candidate(x,residual)
            ffn=base.dropout(base.dense(x))
            pre=F.layer_norm(ffn+residual, (768,), base.LayerNorm.weight, base.LayerNorm.bias, 1e-12)
            down=F.relu(F.linear(pre,tensors[prefix+'adapter_down.0.weight'],tensors[prefix+'adapter_down.0.bias']))
            up=F.linear(down,tensors[prefix+'adapter_up.weight'],tensors[prefix+'adapter_up.bias'])
            expected=F.layer_norm(up+ffn+residual,(768,),base.LayerNorm.weight,base.LayerNorm.bias,1e-12)
            unadapted=F.layer_norm(ffn+residual,(768,),base.LayerNorm.weight,base.LayerNorm.bias,1e-12)
            max_diffs.append(float((actual-expected).abs().max()))
            activations.append(float((actual-unadapted).abs().max()))
            if not torch.isfinite(actual).all() or actual.shape!=(1,3,768):
                raise RuntimeError('nonfinite or malformed 12-layer candidate')
    if max(max_diffs)>1e-6 or min(activations)<=0:
        raise RuntimeError('source equation mismatch or inactive adapter')
    return {
        'schema':'pro-adherence-specter2-pinned-adapter-full12-synthetic-algebra/v1',
        'status':'PUBLIC_ACTUAL_ADAPTER_12_LAYER_SYNTHETIC_ALGEBRA_PASS_NOT_OFFICIAL_EQUIVALENCE',
        'adapter_sha256':APPROVED_WEIGHT_SHA,
        'adapter_layers_tested':LAYERS,
        'actual_pinned_weights_loaded_with_weights_only':True,
        'max_abs_vs_independent_source_equation':max(max_diffs),
        'min_adapter_activation_delta_vs_plain_bert_output':min(activations),
        'max_adapter_activation_delta_vs_plain_bert_output':max(activations),
        'deterministic_seed':20261113,
        'upstream_source':{
            'AdapterHub_v1.3.0_Adapter_blob':'fb7bed348345e244cace47305e9e67b6d7a0a528',
            'AdapterHub_v1.3.0_BottleneckLayer_blob':'1271cc215ddbfc172d114d9715321f436042542f',
            'Transformers_v5.22.2_BertOutput_blob':'a10a59c7e4da62f6727c9f6670ff725436aea929',
        },
        'torch_version':torch.__version__,
        'gates':{
            'real_base_weights_loaded':False,
            'official_adapters_activated_numeric_equivalence':False,
            'private_specter2_inference_authorized':False,
            'scientific_corpus_used':False,
            'production_embeddings_created':False,
            'publication_authorized':False,
            'stage3_closed':False,
        },
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--weights',required=True,type=Path)
    p.add_argument('--candidate',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    if a.out.exists():raise RuntimeError('refuse evidence overwrite')
    x=probe(a.weights,a.candidate)
    a.out.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(x['status'])
if __name__=='__main__':main()
