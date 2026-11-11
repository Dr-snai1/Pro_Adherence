"""Synthetic, network-free tests for documented Stage3 ML dependency conflict."""
import unittest
from pro_adherence.stage3_runtime_guard import audit_runtime_versions


class RuntimeGuardTests(unittest.TestCase):
    def test_adapters_matching_transformers_still_unpatched(self):
        result = audit_runtime_versions(transformers="4.57.6", adapters="1.3.0")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("TRANSFORMERS_BELOW_GHSA_29PF_PATCH_FLOOR", result["blockers"])
        self.assertNotIn("ADAPTERS_1_3_0_TRANSFORMERS_CONSTRAINT_CONFLICT", result["blockers"])

    def test_patched_transformers_cannot_satisfy_adapters_130(self):
        result = audit_runtime_versions(transformers="5.3.0", adapters="1.3.0")
        self.assertIn("ADAPTERS_1_3_0_TRANSFORMERS_CONSTRAINT_CONFLICT", result["blockers"])
        self.assertFalse(result["compatible_and_security_verified"])

    def test_unproven_adapters_release_does_not_become_approved(self):
        result = audit_runtime_versions(transformers="5.3.0", adapters="1.4.0")
        self.assertIn("ADAPTERS_VERSION_REQUIRES_NEW_DEPENDENCY_AND_SMOKE_EVIDENCE", result["blockers"])

    def test_invalid_versions_fail_closed(self):
        for candidate in ("main", "4.57.x", "5.3.0 --no-deps", ""):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    audit_runtime_versions(transformers=candidate, adapters="1.3.0")


if __name__ == "__main__":
    unittest.main()
