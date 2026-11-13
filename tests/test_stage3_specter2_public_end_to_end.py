"""Offline safety checks for the SPECTER2 full public-only integrated witness.

No model downloads, Torch imports, neural inference or private input.
"""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"scripts/stage3_specter2_public_end_to_end.py"

class PublicOnlySpecter2EndToEndContracts(unittest.TestCase):
    def test_explicit_pinned_revisions_checksums_and_synthetic_only(self):
        src=SRC.read_text(encoding="utf-8")
        ast.parse(src)
        for constant in (
            "BASE_SHA = '801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc'",
            "BASE_REV = '3447645e1def9117997203454fa4495937bfbd83'",
            "ADAPTER_SHA = '5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a'",
            "ADAPTER_REV = '2081559630a80fc5851d8f798a05ba81e9468089'",
            "RUNTIME_TORCH = '2.10.0+cpu'",
            "RUNTIME_TRANSFORMERS = '5.22.2'",
        ):
            self.assertIn(constant,src)
        self.assertIn("verify_public_files(base_dir,adapter_path,evidence)",src)
        self.assertIn("pinned_weights_only(adapter_path)",src)
        self.assertIn("synthetic_documents(tokenizer)",src)
        self.assertIn("SourceDerivedReferenceFFN",src)
        self.assertIn("CandidateBertOutputAdapter",src)
        self.assertNotIn("trust_remote_code=True",src)
        self.assertNotIn("private_graph",src)

    def test_fail_closed_and_never_claim_official_reference(self):
        src=SRC.read_text(encoding="utf-8")
        for gate in (
            "'official_adapterhub_package_activated_model_equivalence_verified':False",
            "'full_research_runtime_lock_verified':False",
            "'private_specter2_inference_authorized':False",
            "'production_vectors_generated':False",
            "'publication_authorized':False",
            "'stage3_closed':False",
        ):
            self.assertIn(gate,src)
        self.assertIn("PUBLIC_FULL_BERT_REAL_WEIGHTS_SOURCE_REFERENCE_NUMERIC_PASS_OFFICIAL_ADAPTER_RUNTIME_PENDING",src)
        self.assertIn("weights_only=True",src)
        self.assertNotIn("torch.load(base_dir/'pytorch_model.bin',map_location='cpu',weights_only=False)",src)

if __name__=="__main__": unittest.main()
