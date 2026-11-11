"""Read-only Stage 3 ML runtime compatibility audit (no installation or inference).

Sources: AdapterHub v1.3.0 setup.py requires transformers~=4.57.6;
GitHub Advisory GHSA-29pf-2h5f-8g72 requires transformers>=5.3.0.
This is an evidence-based readiness gate, NOT a change of scientific lens.
"""
from __future__ import annotations

import json
import re

ADAPTERS_130_SOURCE = "https://github.com/adapter-hub/adapters/blob/v1.3.0/setup.py"
TRANSFORMERS_ADVISORY = "https://github.com/advisories/GHSA-29pf-2h5f-8g72"
_MIN_PATCHED_TRANSFORMERS = (5, 3, 0)
_MIN_ADAPTER_130_TRANSFORMERS = (4, 57, 6)
_MAX_ADAPTER_130_TRANSFORMERS = (4, 58, 0)


def _release(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+){1,3}", value):
        raise ValueError("expected a numeric exact package version")
    return tuple(int(v) for v in value.split("."))


def audit_runtime_versions(*, transformers: str, adapters: str | None) -> dict:
    """No new package version is certified without actual dependency and smoke evidence."""
    tf = _release(transformers)
    tf += (0,) * (3 - len(tf))
    problems = []
    if tf < _MIN_PATCHED_TRANSFORMERS:
        problems.append("TRANSFORMERS_BELOW_GHSA_29PF_PATCH_FLOOR")
    if adapters is None:
        problems.append("SPECTER2_ADAPTERS_PACKAGE_NOT_PINNED")
    else:
        av = _release(adapters)
        av += (0,) * (3 - len(av))
        if av == (1, 3, 0):
            if not (_MIN_ADAPTER_130_TRANSFORMERS <= tf < _MAX_ADAPTER_130_TRANSFORMERS):
                problems.append("ADAPTERS_1_3_0_TRANSFORMERS_CONSTRAINT_CONFLICT")
        else:
            problems.append("ADAPTERS_VERSION_REQUIRES_NEW_DEPENDENCY_AND_SMOKE_EVIDENCE")
    if not problems:
        problems.append("SAFE_ADAPTER_RUNTIME_NOT_DEMONSTRATED")
    return {
        "schema": "pro-adherence-stage3-runtime-compatibility/v1",
        "transformers": transformers,
        "adapters": adapters,
        "status": "BLOCKED",
        "compatible_and_security_verified": False,
        "blockers": sorted(set(problems)),
        "sources": [ADAPTERS_130_SOURCE, TRANSFORMERS_ADVISORY],
        "no_model_download_or_inference": True,
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--transformers", required=True)
    p.add_argument("--adapters", default=None)
    args = p.parse_args()
    print(json.dumps(audit_runtime_versions(
        transformers=args.transformers, adapters=args.adapters
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
