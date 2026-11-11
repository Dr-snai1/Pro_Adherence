"""Synthetic no-internet checks for immutable small HF file identities."""
from hashlib import sha256
import unittest

from pro_adherence.stage3_small_file_integrity import (
    SMALL_FILE_LIMIT, audit_small_bytes, git_blob_id, small_file_url,
)
from pro_adherence.stage3_preflight import Stage3PreflightError


class Stage3SmallFileIntegrityTests(unittest.TestCase):
    def test_small_git_blob_and_sha256_readback(self):
        raw = b'{"model_type":"bert","hidden_size":768}'
        sibling = {"size":len(raw), "blobId":git_blob_id(raw)}
        got = audit_small_bytes(raw, sibling, "config.json")
        self.assertEqual(got["local_sha256"],sha256(raw).hexdigest())
        self.assertEqual(got["provider_blob_id"],git_blob_id(raw))
        self.assertTrue(got["provider_git_blob_identity_verified"])
        self.assertFalse(got["model_weights_downloaded"])

    def test_fail_closed_on_wrong_blob_or_size_or_binary(self):
        raw = b"test model config\n"
        for evidence in (
            {"size":len(raw), "blobId":"f"*40},
            {"size":len(raw)-1, "blobId":git_blob_id(raw)},
            {"size":SMALL_FILE_LIMIT+1, "blobId":git_blob_id(raw)},
        ):
            with self.subTest(evidence=evidence):
                with self.assertRaises(Stage3PreflightError):
                    audit_small_bytes(raw, evidence,"config.json")
        with self.assertRaises(Stage3PreflightError):
            audit_small_bytes(raw,{"size":len(raw)},"pytorch_model.bin")

    def test_absent_provider_blob_not_falsely_certified(self):
        raw=b"alpha"
        got=audit_small_bytes(raw,{"size":5},"tokenizer_config.json")
        self.assertFalse(got["provider_git_blob_identity_verified"])
        self.assertTrue(got["local_bytes_readback_verified"])

    def test_safe_exact_url_never_allows_weights_or_paths(self):
        sha="d"*40
        u=small_file_url("allenai/specter2",sha,"adapter_config.json")
        self.assertIn(sha,u)
        for name in ("pytorch_model.bin","pytorch_adapter.bin","../weights.bin","sub/config.json",""):
            with self.subTest(name=name):
                with self.assertRaises(Stage3PreflightError):
                    small_file_url("allenai/specter2",sha,name)


if __name__ == "__main__":
    unittest.main()
