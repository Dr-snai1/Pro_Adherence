"""Read-only SPECTER2 approved PUBLIC base/tokenizer provenance and byte preflight.

Only exact immutable allenai/specter2_base revision, no unpickle, no model
inference, no private corpus, no publish or Stage transition.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

REPO="allenai/specter2_base"
REV="3447645e1def9117997203454fa4495937bfbd83"
EXPECTED_WEIGHT_SHA="801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc"
FILES={
    "config.json": 16384,
    "pytorch_model.bin": 600_000_000,
    "special_tokens_map.json": 8192,
    "tokenizer.json": 2_000_000,
    "tokenizer_config.json": 8192,
    "vocab.txt": 1_000_000,
}
HEX64=re.compile(r"^[a-f0-9]{64}$")

class Rejected(ValueError): pass

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""):
            h.update(chunk)
    return h.hexdigest()

def metadata_check(response:dict)->dict:
    if not isinstance(response,dict) or response.get("sha")!=REV:
        raise Rejected("HF immutable revision does not match approved base")
    s=response.get("siblings")
    if not isinstance(s,list):
        raise Rejected("HF public metadata has no sibling inventory")
    names={}
    for row in s:
        if not isinstance(row,dict) or not isinstance(row.get("rfilename"),str):
            raise Rejected("malformed public sibling metadata")
        key=row["rfilename"]
        if key in names: raise Rejected("duplicate provider filename")
        names[key]=row
    if not set(FILES).issubset(names):raise Rejected("approved base file inventory incomplete")
    weight=names["pytorch_model.bin"]
    lfs=weight.get("lfs")
    if not isinstance(lfs,dict) or lfs.get("sha256")!=EXPECTED_WEIGHT_SHA:
        raise Rejected("pinned weight LFS digest differs from approved weight reference")
    size=weight.get("size")
    if size is not None and (type(size) is not int or not 400_000_000<size<600_000_000):
        raise Rejected("unexpected model weight size metadata")
    return {
        "approved_revision":REV,"repository":REPO,
        "required_files":sorted(FILES),
        "provider_lfs_sha256":EXPECTED_WEIGHT_SHA,
        "provider_weight_size_bytes":size,
        "provider_revision_matches_approved":True,
    }

def check_base_config(obj:dict)->None:
    expected={
        "model_type":"bert","hidden_size":768,"num_hidden_layers":12,
        "num_attention_heads":12,"intermediate_size":3072,
        "max_position_embeddings":512,"vocab_size":31090,
        "layer_norm_eps":1e-12,"hidden_act":"gelu",
    }
    for name,value in expected.items():
        if name not in obj or type(obj[name]) is not type(value) or obj[name]!=value:
            raise Rejected("approved SPECTER2 base architecture mismatch: "+name)

def file_check(file_dir:Path, metadata:dict)->dict:
    result={}
    for filename,cap in FILES.items():
        path=file_dir/filename
        if not path.is_file() or path.is_symlink():raise Rejected("missing/unsafe base file: "+filename)
        size=path.stat().st_size
        if size<=0 or size>cap:raise Rejected("base file size bound: "+filename)
        digest=sha256_file(path)
        if not HEX64.fullmatch(digest):raise Rejected("invalid SHA256")
        result[filename]={"sha256":digest,"size_bytes":size,"provider_revision":REV}
    weights=result["pytorch_model.bin"]
    if weights["sha256"] != EXPECTED_WEIGHT_SHA:
        raise Rejected("actual base weight bytes SHA256 differs from pinned official LFS")
    if metadata["provider_weight_size_bytes"] is not None and (
        weights["size_bytes"]!=metadata["provider_weight_size_bytes"]
    ):
        raise Rejected("actual base weight bytes differ from provider size")
    model_path=file_dir/"pytorch_model.bin"
    if not zipfile.is_zipfile(model_path):
        raise Rejected("base model checkpoint not PyTorch ZIP")
    with zipfile.ZipFile(model_path) as z:
        if z.testzip() is not None:raise Rejected("base model archive CRC failure")
        members=z.namelist()
        if not members or len(members)>1000 or not any(n.endswith("/data.pkl") for n in members):
            raise Rejected("base model ZIP member inventory invalid")
    for filename in ("config.json","special_tokens_map.json","tokenizer_config.json"):
        if result[filename]["size_bytes"]>16384:raise Rejected("oversized small JSON")
    config=json.loads((file_dir/"config.json").read_text(encoding="utf-8"))
    check_base_config(config)
    tokenizer=json.loads((file_dir/"tokenizer.json").read_text(encoding="utf-8"))
    if tokenizer.get("model",{}).get("type")!="WordPiece":
        raise Rejected("not an approved WordPiece tokenizer")
    if (file_dir/"vocab.txt").stat().st_size<100_000:raise Rejected("vocabulary truncated")
    return result

def audit(metadata_path:Path,file_dir:Path|None=None)->dict:
    metadata=metadata_check(json.loads(metadata_path.read_text(encoding="utf-8")))
    files=file_check(file_dir,metadata) if file_dir is not None else None
    verified=files is not None
    return {
        "schema":"pro-adherence-stage3-specter2-approved-base-public/v1",
        "status":"PUBLIC_BASE_AND_TOKENIZER_BYTES_VERIFIED_RUNTIME_BLOCKED"
            if verified else "HF_METADATA_ONLY_MODEL_BYTES_PENDING",
        "model":metadata,"files":files,
        "pickle_or_model_executed":False,
        "gates":{
            "approved_public_base_bytes_verified":verified,
            "supported_safe_adapter_runtime":False,
            "numeric_equivalence_to_official_adapter":False,
            "private_specter2_inference_authorized":False,
            "production_vectors_created":False,
            "publication_authorized":False,
            "stage3_closed":False,
        },
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--metadata",type=Path,required=True)
    p.add_argument("--files-dir",type=Path)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():raise Rejected("do not overwrite previous evidence")
    obj=audit(args.metadata,args.files_dir)
    args.out.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(obj["status"])

if __name__=="__main__":main()
