#!/usr/bin/env python3
"""Fail-closed audit of APA EBSCOhost Search History CSV vs frozen PubMed terms.

Only emits metadata, hashes, and Boolean verification flags. Never publishes
licensed RIS, original account details, or an authentication token.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from apa_psycinfo_search_plan import make_plan

REQUIRED = (
    "Поиск", "Тип поиска", "Запрос (введенный пользователем)",
    "Запрос (развернутый/отображаемый термин)",
    "Дата выполнения поиска (ISO)", "Результаты (количество)",
    "Тип документа", "Язык", "Режим поиска",
    "Количество баз данных", "Базы данных", "Интерфейс",
)
CSV_SOURCE = "EBSCOhost Research Databases"
DB = "APA PsycInfo"


class SearchHistoryAuditError(ValueError):
    pass


def audit(history: bytes, frozen_config: bytes, *, search_id: str = "S8",
          expected_count: int | None = None) -> dict:
    try:
        decoded = history.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SearchHistoryAuditError("HISTORY_NOT_UTF8") from exc
    rows = list(csv.DictReader(io.StringIO(decoded, newline="")))
    if not rows:
        raise SearchHistoryAuditError("NO_SEARCH_HISTORY")
    if not set(REQUIRED).issubset(rows[0]):
        raise SearchHistoryAuditError("REQUIRED_SEARCH_HISTORY_COLUMNS_MISSING")
    selected = [r for r in rows if r["Поиск"] == search_id]
    if len(selected) != 1:
        raise SearchHistoryAuditError(f"SEARCH_ID_NOT_UNIQUE_OR_MISSING {search_id}")
    row = selected[0]
    expected = make_plan(frozen_config)["primary_single_query"]
    submitted = row["Запрос (введенный пользователем)"]
    expanded = row["Запрос (развернутый/отображаемый термин)"]
    if expected != submitted:
        raise SearchHistoryAuditError("FROZEN_180_TERM_QUERY_MISMATCH")
    if submitted != expanded:
        raise SearchHistoryAuditError("EXPANDED_QUERY_DIFFERS")
    if row["Базы данных"] != DB or row["Количество баз данных"] != "1":
        raise SearchHistoryAuditError("NOT_APA_ONLY")
    if row["Тип документа"] != "Journal Article" or row["Язык"] != "English":
        raise SearchHistoryAuditError("FILTERS_NOT_MATCHED")
    if row["Режим поиска"] != "Близость":
        raise SearchHistoryAuditError("MODE_NOT_PROXIMITY")
    if row["Интерфейс"] != CSV_SOURCE:
        raise SearchHistoryAuditError("INTERFACE_NOT_EBSCOHOST")
    try:
        count = int(row["Результаты (количество)"])
    except ValueError as exc:
        raise SearchHistoryAuditError("BAD_HISTORY_RECORD_COUNT") from exc
    if count < 1 or (expected_count is not None and count != expected_count):
        raise SearchHistoryAuditError("SEARCH_HISTORY_COUNT_NOT_AS_EXPECTED")
    return {
        "schema": "stage2-apa-ebsco-search-history-audit/v1",
        "source": DB,
        "history_sha256": hashlib.sha256(history).hexdigest(),
        "history_size_bytes": len(history),
        "frozen_config_sha256": hashlib.sha256(frozen_config).hexdigest(),
        "source_search_id": search_id,
        "date_utc": row["Дата выполнения поиска (ISO)"],
        "results": count,
        "terms": 180,
        "blocks": 6,
        "query_length": len(submitted),
        "query_matches_frozen": True,
        "expanded_equals_submitted": True,
        "database_only_apa": True,
        "filters": {"document_type": "Journal Article", "language": "English"},
        "search_mode": "Близость",
        "expanders_individually_logged_in_csv": False,
        "note": "CSV contains no separate column for every expander checkbox; "
                "equality of the query display does not prove every toggle was off.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history_csv", type=Path)
    parser.add_argument("frozen_json", type=Path)
    parser.add_argument("--search-id", default="S8")
    parser.add_argument("--expected-count", type=int, default=None)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = audit(args.history_csv.read_bytes(), args.frozen_json.read_bytes(),
                   search_id=args.search_id, expected_count=args.expected_count)
    result = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        if args.output.exists():
            raise FileExistsError("REPORT_ALREADY_EXISTS")
        args.output.write_text(result, encoding="utf-8")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
