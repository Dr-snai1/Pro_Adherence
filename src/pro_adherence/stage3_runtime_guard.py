"""Stage3 read-only ML security/dependency gate; never installs or loads packages.

The AdapterHub 1.3.0 *published* package requires transformers~=4.57.6.
The listed GHSA ranges are independent provider-published risk signals.
No currently discovered published AdapterHub release provides a supported
transformers>=5.10.0 pair. New releases need their own metadata and smoke
evidence: this module does not assert that none can ever exist.
"""
from __future__ import annotations

import json
import re

ADAPTERS_130_SOURCE = "https://github.com/adapter-hub/adapters/blob/v1.3.0/setup.py"
ADAPTERS_RELEASE_SOURCE = "https://pypi.org/project/adapters/1.3.0/"
TRANSFORMERS_RELEASE_SOURCE = "https://pypi.org/project/transformers/5.22.2/"
ADVISORIES = (
    ("GHSA-29pf-2h5f-8g72", "5.3.0"),
    ("GHSA-fgcw-684q-jj6r", "5.5.0"),
    ("GHSA-xrqw-3rrv-vx5w", "5.10.0"),
)
ADD_ON_ADVISORY = "GHSA-x9r9-c232-4q39"  # affected >=4.49.0, <=5.8.1
MIN_KNOWN_REVIEWED_FLOOR = (5, 10, 0)
_MIN_ADAPTER_130_TF = (4, 57, 6)
_MAX_ADAPTER_130_TF = (4, 58, 0)


def _release(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+){1,3}", value):
        raise ValueError("expected an exact numeric stable package version")
    version = tuple(int(v) for v in value.split("."))
    return version + (0,) * max(0, 3 - len(version))


def audit_transformers_security(transformers: str) -> list[str]:
    """Known advisory matches; absence is NOT a comprehensive safety claim."""
    v = _release(transformers)
    findings = []
    for advisory, patched in ADVISORIES:
        if v < _release(patched):
            findings.append("KNOWN_TRANSFORMERS_ADVISORY:" + advisory)
    if (4, 49, 0) <= v <= (5, 8, 1):
        findings.append("KNOWN_TRANSFORMERS_ADVISORY:" + ADD_ON_ADVISORY)
    return sorted(findings)


def audit_runtime_versions(*, transformers: str, adapters: str | None) -> dict:
    """Never certify a proposed dependency pair without installed smoke evidence."""
    tf = _release(transformers)
    problems = audit_transformers_security(transformers)
    if problems:
        problems.append("TRANSFORMERS_BELOW_REVIEWED_SECURITY_FLOOR")
    if adapters is None:
        problems.append("SPECTER2_ADAPTERS_PACKAGE_NOT_PINNED")
    else:
        av = _release(adapters)
        if av == (1, 3, 0):
            if not (_MIN_ADAPTER_130_TF <= tf < _MAX_ADAPTER_130_TF):
                problems.append("ADAPTERS_1_3_0_TRANSFORMERS_CONSTRAINT_CONFLICT")
            if tf >= MIN_KNOWN_REVIEWED_FLOOR:
                problems.append("ADAPTERS_1_3_0_HAS_NO_SECURITY_FLOOR_OVERLAP")
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
        "reviewed_advisory_set_date": "2026-11-11",
        "full_security_scan_completed": False,
        "sources": [
            ADAPTERS_130_SOURCE, ADAPTERS_RELEASE_SOURCE, TRANSFORMERS_RELEASE_SOURCE,
            *("https://github.com/advisories/" + key for key, _ in ADVISORIES),
            "https://github.com/advisories/" + ADD_ON_ADVISORY,
        ],
        "no_model_download_or_inference": True,
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--transformers", required=True)
    p.add_argument("--adapters", default=None)
    args = p.parse_args()
    print(json.dumps(audit_runtime_versions(
        transformers=args.transformers, adapters=args.adapters,
    ), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
