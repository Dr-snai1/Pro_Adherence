import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "schemas"

SCHEMA_FILES = [
    "ids.schema.json",
    "access-license.schema.json",
    "entities.schema.json",
    "provenance.schema.json",
    "corpus-release.schema.json",
    "release-manifest.schema.json",
]

SCHEMAS = {
    name: json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    for name in SCHEMA_FILES
}
STORE = {schema["$id"]: schema for schema in SCHEMAS.values()}
FORMAT = FormatChecker()


def validator(schema_name):
    schema = SCHEMAS[schema_name]
    resolver = RefResolver.from_schema(schema, store=STORE)
    return Draft202012Validator(schema, resolver=resolver, format_checker=FORMAT)


def ref_validator(ref):
    wrapper = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": ref}
    resolver = RefResolver(base_uri="", referrer=wrapper, store=STORE)
    return Draft202012Validator(wrapper, resolver=resolver, format_checker=FORMAT)


def uid(n):
    return f"018f0c50-7b1d-7cc3-8a5b-{n:012d}"


class Stage0ContractRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for schema in SCHEMAS.values():
            Draft202012Validator.check_schema(schema)
        cls.prov = validator("provenance.schema.json")
        cls.entities = validator("entities.schema.json")
        cls.ids_immutable = ref_validator("ids.schema.json#/$defs/immutable_version_ref")

    def test_run_input_and_output_each_match_exactly_one_root_alternative(self):
        run_input = {
            "record_type": "run_input",
            "run_id": uid(1),
            "artifact_id": uid(2),
            "role": "input",
        }
        run_output = {
            "record_type": "run_output",
            "run_id": uid(1),
            "artifact_id": uid(3),
            "role": "result",
        }
        for record in (run_input, run_output):
            self.assertTrue(self.prov.is_valid(record))
            matches = 0
            for alt in SCHEMAS["provenance.schema.json"]["oneOf"]:
                ref = alt["$ref"].replace("#/", "provenance.schema.json#/")
                matches += ref_validator(ref).is_valid(record)
            self.assertEqual(matches, 1)

    def test_complete_lineage_bundle_passes_and_incomplete_fails(self):
        fixture = json.loads(
            (ROOT / "contracts" / "manifests" / "minimal_lineage.example.json").read_text(encoding="utf-8")
        )
        self.assertTrue(self.prov.is_valid(fixture), list(self.prov.iter_errors(fixture)))
        incomplete = copy.deepcopy(fixture)
        del incomplete["environment_refs"]
        self.assertFalse(self.prov.is_valid(incomplete))

    def test_identity_history_examples_pass(self):
        fixture = json.loads(
            (ROOT / "contracts" / "examples" / "identity_resolution_history.example.json").read_text(encoding="utf-8")
        )
        self.assertTrue(self.entities.is_valid(fixture), list(self.entities.iter_errors(fixture)))
        self.assertEqual(
            {e["event_type"] for e in fixture["events"]},
            {"alias", "merge", "split", "supersession"},
        )

    def test_mutable_aliases_fail_immutable_version_contract(self):
        aliases = ["latest", "LATEST", "current", "HEAD", "head", "main", "master", "tip", "trunk", "default", "stable", "newest"]
        for alias in aliases:
            with self.subTest(alias=alias):
                self.assertFalse(self.ids_immutable.is_valid(alias))

    def test_concrete_immutable_versions_pass(self):
        for value in ["1.0.0", "resolver-2026-10-08.1", "1111111111111111111111111111111111111111"]:
            with self.subTest(value=value):
                self.assertTrue(self.ids_immutable.is_valid(value))

    def test_corpus_exact_versions_reject_latest(self):
        fixture = json.loads(
            (ROOT / "contracts" / "manifests" / "empty_corpus.manifest.json").read_text(encoding="utf-8")
        )
        corpus_validator = validator("corpus-release.schema.json")
        self.assertTrue(corpus_validator.is_valid(fixture))
        for field in ("canonical_schema_version", "entity_resolution_version"):
            mutated = copy.deepcopy(fixture)
            mutated[field] = "latest"
            self.assertFalse(corpus_validator.is_valid(mutated))

    def test_release_artifact_schema_version_rejects_latest(self):
        access = {
            "access_class": "public",
            "license_class": "fixture",
            "license_status": "confirmed",
            "license_evidence_ref": "fixture",
            "publication_permissions": {"metadata": "allow", "raw_text": "deny", "derived": "deny"},
        }
        artifact = {
            "artifact_id": uid(20),
            "artifact_type": "bibliography",
            "content_hash": "a" * 64,
            "schema_version": "1.0.0",
            "role": "bibliography",
            "public_path": "data/bibliography.json",
            "publication_permission_basis": "metadata",
            "access_license": access,
        }
        v = ref_validator("release-manifest.schema.json#/$defs/release_artifact")
        self.assertTrue(v.is_valid(artifact))
        artifact["schema_version"] = "latest"
        self.assertFalse(v.is_valid(artifact))


if __name__ == "__main__":
    unittest.main()
