from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.extraction_v2.event_identity import EventIdentityExtractor
from skyportal_corpus.extraction_v2.event_registry import (
    build_event_registry_rows,
    write_event_registry,
)
from skyportal_corpus.extraction_v2.event_selection import select_event_candidates
from skyportal_corpus.extraction_v2.identity_index import (
    build_identity_index_records,
    write_identity_index,
)


def test_registry_prefers_trigger_like_id_and_merges_all_aliases() -> None:
    sources = [
        _source("2026owq", "grb", tns_name="AT 2026owq"),
        _source("GCN-260610_234614", "gcn", tns_name="AT 2026owq"),
    ]
    term_rows = [
        _term("2026owq", "grb", "GRB 260610B", "alias"),
        _term("2026owq", "grb", "AT 2026owq", "tns_name"),
        _term("GCN-260610_234614", "gcn", "GRB260610B", "alias"),
        _term("GCN-260610_234614", "gcn", "GOTO26fua", "alias"),
    ]

    rows, diagnostics = build_event_registry_rows(sources, term_rows)

    assert len(rows) == 1
    assert diagnostics == [
        {
            "members": ["2026owq", "GCN-260610_234614"],
            "canonical_source_id": "GCN-260610_234614",
        }
    ]
    row = rows[0]
    assert row["source_id"] == "GCN-260610_234614"
    assert row["merged_source_ids"] == "2026owq"
    assert row["gcn_source_type"] == "gcn"
    assert _compact_terms(row["terms"]) == {
        "GRB260610B",
        "AT2026OWQ",
        "GOTO26FUA",
    }


def test_gcn_250706_record_keeps_both_grb_designations() -> None:
    source_id = "GCN-250706_170544"
    sources = [_source(source_id, "gcn")]
    term_rows = [
        _term(source_id, "gcn", source_id, "id"),
        _term(source_id, "gcn", "GRB 250706B", "alias"),
        _term(source_id, "gcn", "GRB 250706C", "alias"),
    ]

    rows, diagnostics = build_event_registry_rows(sources, term_rows)

    assert diagnostics == []
    assert len(rows) == 1
    assert rows[0]["source_id"] == source_id
    assert {"GRB250706B", "GRB250706C"} <= _compact_terms(rows[0]["terms"])


@pytest.mark.parametrize(
    ("source_id", "suffixed_term", "suffixless_term"),
    [
        ("GRB241030", "GRB241030A", "GRB241030"),
        ("EP250704", "EP 250704a", "EP250704"),
    ],
)
def test_registry_prefers_same_date_suffixed_event_term(
    source_id: str,
    suffixed_term: str,
    suffixless_term: str,
) -> None:
    source_type = "ep" if source_id.startswith("EP") else "grb"
    rows, diagnostics = build_event_registry_rows(
        [_source(source_id, source_type)],
        [
            _term(source_id, source_type, suffixed_term, "alias"),
            _term(source_id, source_type, suffixless_term, "id"),
        ],
    )

    assert diagnostics == []
    assert len(rows) == 1
    assert _compact_terms(rows[0]["terms"]) == {
        "".join(character for character in suffixed_term.upper() if character.isalnum())
    }
    assert rows[0]["dropped_terms"] == suffixless_term
    assert rows[0]["n_terms"] == 1


def test_registry_keeps_event_with_only_a_suffixless_term() -> None:
    rows, _ = build_event_registry_rows(
        [_source("GRB240730", "grb")],
        [_term("GRB240730", "grb", "GRB240730", "id")],
    )

    assert rows[0]["terms"] == "GRB240730"
    assert rows[0]["dropped_terms"] == ""
    assert rows[0]["n_terms"] == 1


def test_index_scan_matches_live_grouping_without_id_or_event_date_filter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    circulars = [
        {
            "circular_id": 3,
            "subject": "GRB 240912A: discovery",
            "body": "This circular reports the gamma-ray burst.",
            "created_on": "2023-01-01T00:00:00Z",
            "submitter": "First Author",
        },
        {
            "circular_id": 999999,
            "subject": "Late optical follow-up",
            "body": "The source 2026owq remains visible in late imaging.",
            "created_on": "2026-01-01T00:00:00Z",
            "submitter": "Second Author",
        },
        {
            "circular_id": 4,
            "subject": "GRB 240912B: comparison event",
            "body": "This text compares the event with GRB 240912A.",
            "created_on": "2024-09-12T00:00:00Z",
            "submitter": "Third Author",
        },
    ]
    registry_path = tmp_path / "event_registry.csv"
    write_event_registry(
        [
            {
                "source_id": "event-a",
                "gcn_source_type": "grb",
                "title": "GRB 240912A / 2026owq",
                "terms": "GRB 240912A | 2026owq",
                "merged_source_ids": "",
                "tns_name": "",
                "trigger_time": "59945",
                "n_terms": 2,
                "flags": "",
            }
        ],
        registry_path,
    )
    index_path = tmp_path / "identity_index.parquet"
    write_identity_index(build_identity_index_records(circulars), index_path)
    extractor = EventIdentityExtractor()
    index_path.with_name("index_meta.json").write_text(
        json.dumps(
            {
                "min_year": 2023,
                "extractor_id": extractor.extractor_id,
                "extractor_version": extractor.extractor_version,
            }
        ),
        encoding="utf-8",
    )
    seen_min_years: list[int] = []

    def fake_iter_real_circulars(*, min_year: int):
        seen_min_years.append(min_year)
        yield from circulars

    monkeypatch.setattr(
        "skyportal_corpus.extraction_v2.event_selection.iter_real_circulars",
        fake_iter_real_circulars,
    )

    selection = select_event_candidates(
        "event-a",
        registry_path=registry_path,
        index_path=index_path,
    )

    assert seen_min_years == [2023]
    assert [item["circular_id"] for item in selection["included"]] == [3, 999999]
    assert [item["circular_id"] for item in selection["body_only_name"]] == [999999]
    assert [item["circular_id"] for item in selection["excluded_conflicts"]] == [4]
    assert [item["circular_id"] for item in selection["far_in_time"]] == [999999]
    assert {
        int(item["circular_id"])
        for item in selection["authoritative_group"]["included"]
    } == {3, 999999}


def _source(
    source_id: str,
    source_type: str,
    *,
    tns_name: str | None = None,
) -> dict[str, object]:
    return {
        "id": source_id,
        "gcn_source_type": source_type,
        "tns_name": tns_name,
        "trigger_time": 61201.990442708,
        "ra": 218.159414,
        "dec": 27.004935,
    }


def _term(
    source_id: str,
    source_type: str,
    value: str,
    origin_field: str,
) -> dict[str, object]:
    normalized = "".join(character for character in value.upper() if character.isalnum())
    return {
        "source_id": source_id,
        "gcn_source_type": source_type,
        "origin_field": origin_field,
        "origin_value": value,
        "search_term": value,
        "search_term_normalized": normalized,
        "variant_type": "original",
        "variant_rank": 0,
        "is_trigger_like": False,
        "groups": "",
    }


def _compact_terms(value: object) -> set[str]:
    return {
        "".join(character for character in term.upper() if character.isalnum())
        for term in str(value).split("|")
        if term.strip()
    }
