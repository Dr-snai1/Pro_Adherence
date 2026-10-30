#!/usr/bin/env python3
"""Offline private Stage-2 one-shot CLI (NO source download; NO public release)."""
from __future__ import annotations
import argparse
from pathlib import Path
import json
from pro_adherence.stage2_integrate import load_sources, save_private_candidate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pubmed-raw-dir", type=Path, required=True,
                        help="accepted V05 extracted stage1-v05-private/<run_id>/raw, 250 XML")
    parser.add_argument("--wos-first", type=Path, required=True,
                        help="original 000001-000500 tagged TXT")
    parser.add_argument("--wos-zip", type=Path, required=True,
                        help="original 000501-030635 archive ZIP")
    parser.add_argument("--apa-ris", type=Path, required=True,
                        help="original 006878 APA RIS")
    parser.add_argument("--out", type=Path, required=True,
                        help="NEW EMPTY PRIVATE location; not a public Git checkout")
    args = parser.parse_args(argv)
    records = load_sources(args.pubmed_raw_dir, args.wos_first, args.wos_zip, args.apa_ris)
    manifest = save_private_candidate(records, args.out)
    print("STAGE2_PRIVATE_PROVISIONAL_CANDIDATE",
          json.dumps({"source_record_count": manifest["source_record_count"],
                      "source_counts": manifest["source_counts"],
                      "artifact_hashes": {name: item["sha256"] for name, item in manifest["artifacts"].items()},
                      "stage_gate": "OPEN",
                      "public_promotion": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
