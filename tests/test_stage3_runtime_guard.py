"""Offline security-compatibility gates for approved Stage3 model family."""
import unittest
from pro_adherence.stage3_runtime_guard import (
    audit_runtime_versions, audit_transformers_security,
)


class RuntimeGuardTests(unittest.TestCase):
    def test_matching_adapters_package_is_known_unpatched(self):
        r = audit_runtime_versions(transformers="4.57.6", adapters="1.3.0")
        self.assertEqual(r["status"], "BLOCKED")
        self.assertIn("TRANSFORMERS_BELOW_REVIEWED_SECURITY_FLOOR", r["blockers"])
        self.assertIn("KNOWN_TRANSFORMERS_ADVISORY:GHSA-29pf-2h5f-8g72", r["blockers"])
        self.assertIn("KNOWN_TRANSFORMERS_ADVISORY:GHSA-fgcw-684q-jj6r", r["blockers"])
        self.assertIn("KNOWN_TRANSFORMERS_ADVISORY:GHSA-xrqw-3rrv-vx5w", r["blockers"])
        self.assertNotIn("ADAPTERS_1_3_0_TRANSFORMERS_CONSTRAINT_CONFLICT", r["blockers"])

    def test_updated_transformers_conflicts_with_published_adapters(self):
        r = audit_runtime_versions(transformers="5.22.2", adapters="1.3.0")
        self.assertIn("ADAPTERS_1_3_0_TRANSFORMERS_CONSTRAINT_CONFLICT", r["blockers"])
        self.assertIn("ADAPTERS_1_3_0_HAS_NO_SECURITY_FLOOR_OVERLAP", r["blockers"])
        self.assertFalse(r["compatible_and_security_verified"])
        self.assertEqual(audit_transformers_security("5.22.2"), [])

    def test_intermediate_version_still_matches_advisory(self):
        self.assertIn("KNOWN_TRANSFORMERS_ADVISORY:GHSA-x9r9-c232-4q39",
                      audit_transformers_security("5.8.1"))
        self.assertEqual(audit_transformers_security("5.10.0"), [])

    def test_unverified_future_adapter_release_does_not_pass(self):
        r = audit_runtime_versions(transformers="5.22.2", adapters="1.4.0")
        self.assertIn("ADAPTERS_VERSION_REQUIRES_NEW_DEPENDENCY_AND_SMOKE_EVIDENCE",
                      r["blockers"])

    def test_invalid_version_fails_closed(self):
        for candidate in ("main", "4.57.x", "5.3.0 --no-deps", ""):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    audit_runtime_versions(transformers=candidate, adapters="1.3.0")
