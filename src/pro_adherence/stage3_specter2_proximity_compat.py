"""EXPERIMENTAL adapter arithmetic candidate, NOT a certified SPECTER2 backend.

Implements the selected AdapterHub 1.3.0 BERT output bottleneck algebra using
only PyTorch. Never downloads models or changes an existing pretrained model.
Numeric equivalence to the official activated proximity adapter is UNVERIFIED.
No scientific inference or production compute is authorized by this module.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F

WEIGHTS_SHA = '5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'
LAYERS=12
HIDDEN=768
BOTTLENECK=48
NUM_TENSORS=48
EXPERIMENTAL_NOT_VALIDATED=True


def expected_shapes():
    result={}
    for i in range(LAYERS):
        pre=f'bert.encoder.layer.{i}.output.adapters.[PRX].'
        result[pre+'adapter_down.0.weight']=(BOTTLENECK,HIDDEN)
        result[pre+'adapter_down.0.bias']=(BOTTLENECK,)
        result[pre+'adapter_up.weight']=(HIDDEN,BOTTLENECK)
        result[pre+'adapter_up.bias']=(HIDDEN,)
    return result


def pinned_weights_only(path:Path)->dict:
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for buf in iter(lambda:f.read(1<<20),b''):h.update(buf)
    if h.hexdigest()!=WEIGHTS_SHA:
        raise ValueError('proximity adapter SHA256 mismatch: refuse deserialization')
    tensors=torch.load(path,map_location='cpu',weights_only=True)
    shapes=expected_shapes()
    if not isinstance(tensors,dict) or set(tensors)!=set(shapes):
        raise ValueError('pinned proximity checkpoint tensor inventory mismatch')
    for k,shape in shapes.items():
        t=tensors[k]
        if not isinstance(t,torch.Tensor) or tuple(t.shape)!=shape or t.dtype!=torch.float32:
            raise ValueError('proximity tensor shape/dtype mismatch: '+k)
        if not torch.isfinite(t).all().item():
            raise ValueError('nonfinite adapter weight: '+k)
    return tensors


class CandidateBertOutputAdapter(nn.Module):
    """Candidate exact bottleneck operator for ONE FFN block; no model patching.

    Source configuration: original_ln_before/after=True, residual_before_ln=True,
    adapter_residual_before_ln=False, output_adapter=True, mh_adapter=False,
    no extra layer norm, ReLU, scaling=1, no adapter dropout at eval.
    """
    def __init__(self, bert_output_module:nn.Module, tensors:dict, layer_index:int):
        super().__init__()
        if not isinstance(layer_index,int) or not 0<=layer_index<LAYERS:
            raise ValueError('invalid BERT layer index')
        for attr in ('dense','dropout','LayerNorm'):
            if not isinstance(getattr(bert_output_module,attr,None),nn.Module):
                raise ValueError('not a compatible BERT FFN output module')
        self.base_output=bert_output_module
        self.down=nn.Linear(HIDDEN,BOTTLENECK)
        self.up=nn.Linear(BOTTLENECK,HIDDEN)
        prefix=f'bert.encoder.layer.{layer_index}.output.adapters.[PRX].'
        with torch.no_grad():
            self.down.weight.copy_(tensors[prefix+'adapter_down.0.weight'])
            self.down.bias.copy_(tensors[prefix+'adapter_down.0.bias'])
            self.up.weight.copy_(tensors[prefix+'adapter_up.weight'])
            self.up.bias.copy_(tensors[prefix+'adapter_up.bias'])
        self.requires_grad_(False)
        self.eval()

    def forward(self, hidden_states, input_tensor):
        if self.training:
            raise RuntimeError('adapter candidate is eval-only')
        # Source AdapterHub v1.3.0: BertOutput -> BottleneckLayer -> Adapter.
        ffn=self.base_output.dropout(self.base_output.dense(hidden_states))
        # Adapter.pre_forward(): residual is the pre-LN FFN tensor.
        pre=self.base_output.LayerNorm(ffn+input_tensor)
        # Adapter.forward(): up(relu(down(pre))) + pre-LN FFN residual.
        adapted=self.up(F.relu(self.down(pre)))+ffn
        # Adapter.post_forward(): original LayerNorm after original residual.
        return self.base_output.LayerNorm(adapted+input_tensor)
