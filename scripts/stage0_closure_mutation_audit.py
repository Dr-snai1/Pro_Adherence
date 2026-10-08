#!/usr/bin/env python3
"""Independent closure-class semantic mutation audit for Stage 0."""
from __future__ import annotations

import copy
import importlib.util
import tempfile
from pathlib import Path

from pro_adherence import materialize as m
from pro_adherence import stage0_fixture as f
from pro_adherence import validate as v

ROOT = Path(__file__).resolve().parents[1]
_PREQA_SPEC = importlib.util.spec_from_file_location("preqa_audit", ROOT / "scripts/pre_qa_gate.py")
PREQA = importlib.util.module_from_spec(_PREQA_SPEC)
_PREQA_SPEC.loader.exec_module(PREQA)

failures = []
checks = 0


def expect_invalid(name, fn):
    global checks
    checks += 1
    try:
        result = fn()
        invalid = bool(result) if isinstance(result, list) else False
    except Exception:
        invalid = True
    print(f"MUTATION {name}: {'REJECTED' if invalid else 'ACCEPTED'}")
    if not invalid:
        failures.append(name)


def uid(n):
    return f"018f0c50-7b1d-7cc3-8a5b-{n:012d}"


def add_run(bundle, run_id, input_ids, output_ids):
    run = copy.deepcopy(bundle["runs"][0])
    run["run_id"] = run_id
    bundle["runs"].append(run)
    bundle["run_inputs"].extend(
        {"record_type": "run_input", "run_id": run_id, "artifact_id": x, "role": f"input_{i}"}
        for i, x in enumerate(input_ids)
    )
    bundle["run_outputs"].extend(
        {"record_type": "run_output", "run_id": run_id, "artifact_id": x, "role": f"result_{i}"}
        for i, x in enumerate(output_ids)
    )


base = v.load_json(ROOT / "contracts/manifests/minimal_lineage.example.json")
root = base["root_output_artifact_id"]
canonical = base["run_inputs"][0]["artifact_id"]

x = copy.deepcopy(base)
x["run_inputs"][0]["artifact_id"] = root
expect_invalid("lineage self-loop", lambda: v.reconstruct_lineage(x, root))

x = copy.deepcopy(base)
add_run(x, uid(1301), [root], [canonical])
expect_invalid("lineage two-node cycle", lambda: v.reconstruct_lineage(x, root))

x = copy.deepcopy(base)
middle = copy.deepcopy(x["artifacts"][-1])
middle["artifact_id"] = uid(1302)
middle["content_hash"] = "8" * 64
middle["uri"] = "derived/synthetic/middle.json"
x["artifacts"].append(middle)
add_run(x, uid(1303), [root], [middle["artifact_id"]])
add_run(x, uid(1304), [middle["artifact_id"]], [canonical])
expect_invalid("lineage long cycle", lambda: v.reconstruct_lineage(x, root))

for path in (
    "data/raw/x", "data/normalized/x", "data/canonical/x", "data/derived/x",
    "data/research/x", "data/restricted/x", "research/x", "restricted/x",
    r"data\\research\\x", "nested/secrets/key.json", "nested/.env.prod",
    "serving/data/releases/unselected.json",
):
    expect_invalid(f"boundary {path}", lambda path=path: v.validate_public_paths([path]))

expect_invalid(
    "status live claim",
    lambda: PREQA.scan_live_status("docs/new.md", "# x\nQA-S0-008 — OPEN / BLOCKING\n"),
)

fixture = f.build_fixture(ROOT)
catalog_errors = []
catalog = v.catalog_from_bundle(fixture["lineage"], catalog_errors)
v.add_evidence_record(catalog, fixture["report"], catalog_errors)
v.add_evidence_record(catalog, fixture["event"], catalog_errors)
if catalog_errors:
    raise SystemExit("fixture catalog invalid: " + "; ".join(catalog_errors))
corpora = {fixture["corpus"]["corpus_release_id"]: fixture["corpus"]}
lineage_ids = {fixture["lineage"]["root_output_artifact_id"]}

with tempfile.TemporaryDirectory() as td:
    src = Path(td) / "payload.json"
    src.write_bytes(fixture["payload"])
    expect_invalid(
        "serving extra unselected payload",
        lambda: m.validate_materialization_inputs(
            fixture["release"], catalog=catalog, corpora=corpora,
            lineage_artifact_ids=lineage_ids,
            artifact_sources={fixture["artifact_id"]: src, uid(1310): src},
        ),
    )
    bad = Path(td) / "bad.json"
    bad.write_bytes(b"tampered\n")
    expect_invalid(
        "serving selected hash mismatch",
        lambda: m.validate_materialization_inputs(
            fixture["release"], catalog=catalog, corpora=corpora,
            lineage_artifact_ids=lineage_ids,
            artifact_sources={fixture["artifact_id"]: bad},
        ),
    )
    restricted_catalog = copy.deepcopy(catalog)
    restricted_catalog.artifacts[fixture["artifact_id"]]["access_license"]["access_class"] = "restricted-license"
    expect_invalid(
        "serving restricted artifact",
        lambda: m.validate_materialization_inputs(
            fixture["release"], catalog=restricted_catalog, corpora=corpora,
            lineage_artifact_ids=lineage_ids,
            artifact_sources={fixture["artifact_id"]: src},
        ),
    )

if failures:
    print("CLOSURE MUTATION AUDIT FAIL:", ", ".join(failures))
    raise SystemExit(1)
print(f"CLOSURE MUTATION AUDIT PASS: {checks}/{checks} injected defects rejected")
