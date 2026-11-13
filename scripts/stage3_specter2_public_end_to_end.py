"""Public pinned SPECTER2 base + proximity numeric integration probe, synthetic text only.

Uses an approved recent Transformers BertModel and verified pinned public bytes.
Compares a candidate adapter-integrated full 12-layer BERT forward against an
independently written AdapterHub v1.3.0 source-equation reference. This is NOT
an execution of the official Adapters package and NOT authorized private inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
import transformers
from transformers import BertConfig, BertModel, BertTokenizerFast

from pro_adherence.stage3_specter2_proximity_compat import (
    CandidateBertOutputAdapter, pinned_weights_only,
)

BASE_SHA = '801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc'
BASE_REV = '3447645e1def9117997203454fa4495937bfbd83'
ADAPTER_SHA = '5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'
ADAPTER_REV = '2081559630a80fc5851d8f798a05ba81e9468089'
RUNTIME_TORCH = '2.10.0+cpu'
RUNTIME_TRANSFORMERS = '5.22.2'
REQUIRED_NAMES = ('config.json', 'pytorch_model.bin', 'special_tokens_map.json',
                  'tokenizer.json', 'tokenizer_config.json', 'vocab.txt')
BERT_DIM, LAYERS = 768, 12


def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def verify_public_files(base_dir: Path, adapter: Path, evidence: dict):
    if set(REQUIRED_NAMES) != set(evidence['files']):
        raise RuntimeError('base evidence filenames changed')
    for name in REQUIRED_NAMES:
        p = base_dir/name
        if not p.is_file() or p.is_symlink():
            raise RuntimeError('missing public base file: '+name)
        record = evidence['files'][name]
        if p.stat().st_size != record['bytes'] or file_sha(p) != record['sha256']:
            raise RuntimeError('public pinned base byte mismatch: '+name)
    if file_sha(base_dir/'pytorch_model.bin') != BASE_SHA:
        raise RuntimeError('base weight SHA does not match approved immutable identity')
    if file_sha(adapter) != ADAPTER_SHA:
        raise RuntimeError('adapter weight SHA does not match approved immutable identity')


def load_pinned_base(base_dir: Path):
    config = BertConfig.from_json_file(str(base_dir/'config.json'))
    for name, expected in {'hidden_size':768,'num_hidden_layers':12,
                           'intermediate_size':3072,'num_attention_heads':12}.items():
        if getattr(config, name) != expected:
            raise RuntimeError('BERT architecture mismatch: '+name)
    # Force a predictable eager attention implementation, avoiding platform
    # differences in fused attention kernels in candidate/reference comparisons.
    config._attn_implementation = 'eager'
    model = BertModel(config, add_pooling_layer=False).eval()
    checkpoint = torch.load(base_dir/'pytorch_model.bin', map_location='cpu', weights_only=True)
    if not isinstance(checkpoint,dict):
        raise RuntimeError('base checkpoint is not a tensor dictionary')
    expected_state = model.state_dict()
    filtered = {}
    ignored = []
    for original_name, value in checkpoint.items():
        if not isinstance(original_name,str) or not isinstance(value,torch.Tensor):
            raise RuntimeError('base checkpoint tensor/type mismatch')
        stripped = original_name.removeprefix('bert.')
        if stripped in expected_state:
            if stripped in filtered:
                raise RuntimeError('base checkpoint collision after prefix normalization')
            if expected_state[stripped].shape != value.shape:
                raise RuntimeError('base checkpoint tensor shape mismatch: '+stripped)
            filtered[stripped] = value
        elif stripped == 'embeddings.position_ids':
            # Historical checkpoint buffer is nonpersistent in Transformers 5.x.
            # Accept it ONLY after exact shape/content verification.
            count = int(model.config.max_position_embeddings)
            if tuple(value.shape) != (1,count) or not torch.equal(
                value.cpu(), torch.arange(count, dtype=value.dtype).reshape(1,-1)
            ):
                raise RuntimeError('upstream positional buffer mismatch')
            ignored.append(original_name)
        elif stripped == 'embeddings.token_type_ids':
            if tuple(value.shape) != (1,int(model.config.max_position_embeddings)) or torch.any(value):
                raise RuntimeError('upstream token_type_ids buffer mismatch')
            ignored.append(original_name)
        elif stripped.startswith('pooler.dense.'):
            ignored.append(original_name)
        else:
            raise RuntimeError('unexpected pretrained base checkpoint key: '+original_name)
    missing = set(expected_state) - set(filtered)
    if missing:
        raise RuntimeError('pretrained base missing required tensors: '+str(sorted(missing)[:5]))
    model.load_state_dict(filtered, strict=True)
    return model, {'pretrained_base_tensors_loaded':len(filtered),
                   'discarded_pooler_only':ignored,
                   'base_weights_only_safe_load':True}


class SourceDerivedReferenceFFN(nn.Module):
    """Independent source-equation transcription: AdapterHub v1.3.0 on BERT FFN.

    Not the official old package; full-model official runtime comparison PENDING.
    Config: residual_before_ln=True, original_ln_before/after=True,
    adapter_residual_before_ln=False, ReLU, no extra LN, scaling=1.
    """
    def __init__(self, original_output:nn.Module, real_weights:dict, i:int):
        super().__init__()
        self.original = original_output
        p = f'bert.encoder.layer.{i}.output.adapters.[PRX].'
        self.down_w = real_weights[p+'adapter_down.0.weight']
        self.down_b = real_weights[p+'adapter_down.0.bias']
        self.up_w = real_weights[p+'adapter_up.weight']
        self.up_b = real_weights[p+'adapter_up.bias']

    def forward(self, hidden_states, input_tensor):
        # Original AdapterHub BertOutput + BottleneckLayer + Adapter.
        ffn = self.original.dropout(self.original.dense(hidden_states))
        first_ln = self.original.LayerNorm(ffn+input_tensor)
        down = F.linear(first_ln,self.down_w,self.down_b)
        activated = F.relu(down)
        adapter_up = F.linear(activated,self.up_w,self.up_b)
        # Adapter.forward: residual_input is FFN output (pre original LN).
        adapted = adapter_up + ffn
        # Adapter.post_forward: original_ln_after=True.
        return self.original.LayerNorm(adapted+input_tensor)


def synthetic_documents(tokenizer):
    cases = [
      ('Medication adherence', 'We evaluate a controlled synthetic scientific article.'),
      ('Clinical research', ''),
      ('Citation networks', 'Representation learning and scientific retrieval can be compared.'),
    ]
    strings = [title+tokenizer.sep_token+abstract for title, abstract in cases]
    stats = []
    for text in strings:
        untruncated = tokenizer(text,add_special_tokens=True,truncation=False)['input_ids']
        truncated = tokenizer(text,add_special_tokens=True,truncation=True,max_length=512)['input_ids']
        stats.append({'untruncated_tokens':len(untruncated), 'encoded_tokens':len(truncated),
                      'tokens_lost':max(0,len(untruncated)-len(truncated))})
    # The very long synthetic input is ONLY tokenized, not passed through the model.
    long_text = 'A long synthetic article'+tokenizer.sep_token+(' medicine clinical evidence'*260)
    long_raw = tokenizer(long_text,add_special_tokens=True,truncation=False)['input_ids']
    long_short = tokenizer(long_text,add_special_tokens=True,truncation=True,max_length=512)['input_ids']
    stats.append({'untruncated_tokens':len(long_raw), 'encoded_tokens':len(long_short),
                  'tokens_lost':max(0,len(long_raw)-len(long_short))})
    if stats[-1]['tokens_lost'] <= 0 or any(x['tokens_lost']>0 for x in stats[:-1]):
        raise RuntimeError('512-token policy test failed')
    encoded = tokenizer(strings,return_tensors='pt',padding=True,truncation=True,
                        max_length=512,return_token_type_ids=False)
    return encoded,stats


def public_numeric_probe(base_dir:Path, adapter_path:Path, evidence_path:Path, public_vectors_out:Path|None=None):
    if platform.machine().lower() not in ('x86_64','amd64'):
        raise RuntimeError('unsupported CPU architecture for this witness')
    if torch.__version__ != RUNTIME_TORCH or transformers.__version__ != RUNTIME_TRANSFORMERS:
        raise RuntimeError('unexpected unverified public probe package versions')
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    verify_public_files(base_dir,adapter_path,evidence)
    real_adapter = pinned_weights_only(adapter_path)
    torch.set_num_threads(2)
    torch.manual_seed(20261113)
    model, base_load = load_pinned_base(base_dir)
    tokenizer = BertTokenizerFast.from_pretrained(str(base_dir),local_files_only=True)
    inputs,token_stats = synthetic_documents(tokenizer)
    originals = [layer.output for layer in model.encoder.layer]
    if len(originals) != LAYERS or any(int(x.shape[1])!=BERT_DIM for x in [model.embeddings.word_embeddings.weight]):
        raise RuntimeError('not exactly 12-layer/768d BERT')
    model.eval()
    with torch.inference_mode():
        base_out = model(**inputs).last_hidden_state[:,0,:].clone()
        for i,layer in enumerate(model.encoder.layer):
            layer.output = CandidateBertOutputAdapter(originals[i],real_adapter,i).eval()
        candidate = model(**inputs).last_hidden_state[:,0,:].clone()
        candidate_repeat = model(**inputs).last_hidden_state[:,0,:].clone()
        for i,layer in enumerate(model.encoder.layer):
            layer.output = SourceDerivedReferenceFFN(originals[i],real_adapter,i).eval()
        independent = model(**inputs).last_hidden_state[:,0,:].clone()
    if base_out.shape != (3,BERT_DIM) or candidate.shape != (3,BERT_DIM):
        raise RuntimeError('SPECTER2 synthetic first-token output dims wrong')
    if not all(torch.isfinite(v).all().item() for v in (base_out,candidate,independent)):
        raise RuntimeError('SPECTER2 synthetic forward produced nonfinite embeddings')
    max_abs = float((candidate-independent).abs().max().item())
    adapter_delta = float((candidate-base_out).abs().max().item())
    repeat_max_abs = float((candidate-candidate_repeat).abs().max().item())
    norms = torch.linalg.vector_norm(candidate.to(torch.float64),dim=1)
    unit = candidate.to(torch.float64)/norms[:,None]
    if max_abs>1e-5 or adapter_delta <= 1e-4 or repeat_max_abs != 0.0:
        raise RuntimeError(f'full public model numerical mismatch: {max_abs=} {adapter_delta=} {repeat_max_abs=}')
    if torch.any(norms<=0) or not torch.allclose(torch.linalg.vector_norm(unit,dim=1),torch.ones(3,dtype=torch.float64),atol=1e-8):
        raise RuntimeError('full public output L2 normalization invalid')
    arr = candidate.cpu().numpy().astype('float32',copy=False)
    digest = hashlib.sha256(arr.tobytes(order='C')).hexdigest()
    if public_vectors_out is not None:
        if public_vectors_out.exists():
            raise RuntimeError('refuse overwrite of public synthetic vectors')
        np.save(public_vectors_out,arr,allow_pickle=False)  # public synthetic ONLY
    return {
       'schema':'pro-adherence-specter2-pinned-public-full-bert-activated-adapter-source-reference/v1',
       'status':'PUBLIC_FULL_BERT_REAL_WEIGHTS_SOURCE_REFERENCE_NUMERIC_PASS_OFFICIAL_ADAPTER_RUNTIME_PENDING',
       'base_revision':BASE_REV, 'base_sha256':BASE_SHA,
       'adapter_revision':ADAPTER_REV,'adapter_sha256':ADAPTER_SHA,
       'model':{'base':base_load,'adapter_layers_enabled':LAYERS,
                'synthetic_first_token_vectors_shape':list(arr.shape),
                'public_input_count':3,'tokenization_audit_including_long_text':token_stats,
                'max_abs_candidate_vs_independent_source_reference':max_abs,
                'max_abs_adapter_vs_plain_bert':adapter_delta,
                'max_abs_repeated_same_process':repeat_max_abs,
                'candidate_output_bytes_sha256':digest,
                'min_raw_l2_norm':float(norms.min().item()),
                'max_raw_l2_norm':float(norms.max().item())},
       'runtime':{'python':sys.version.split()[0],'torch':torch.__version__,
                  'transformers':transformers.__version__,
                  'safetensors':__import__('safetensors').__version__,
                  'torch_threads':2,'eval_only':True,'device':'cpu'},
       'gates':{'public_pinned_real_base_and_adapter_numeric_source_equation_reference_verified':True,
                'official_adapterhub_package_activated_model_equivalence_verified':False,
                'full_research_runtime_lock_verified':False,
                'private_specter2_inference_authorized':False,
                'production_vectors_generated':False,'publication_authorized':False,
                'stage3_closed':False},
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-dir',type=Path,required=True)
    p.add_argument('--adapter',type=Path,required=True)
    p.add_argument('--public-evidence',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--public-synthetic-vectors-out',type=Path)
    a=p.parse_args()
    if a.out.exists():raise RuntimeError('refuse overwrite of numeric witness')
    r=public_numeric_probe(a.base_dir,a.adapter,a.public_evidence,a.public_synthetic_vectors_out)
    a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(r['status'])

if __name__=='__main__':main()
