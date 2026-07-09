from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.extraction_v2.event_grouping import (
    canonical_aliases,
    circular_matches_event,
    group_event_circulars,
    normalize_for_match,
)


ALIASES = ["GRB 260610B", "AT2026owq", "2026owq"]


def test_normalize_for_match_collapses_event_names() -> None:
    assert normalize_for_match("GRB 260610B") == "grb260610b"
    assert normalize_for_match("AT2026owq") == "at2026owq"
    assert normalize_for_match("2026owq") == "2026owq"


def test_grouping_includes_confirmed_subject_match() -> None:
    result = _group(
        [
            _circular(
                circular_id=1,
                subject="GRB 260610B: Swift detection",
                body="This circular reports the burst.",
            )
        ]
    )

    assert result["n_included"] == 1
    assert result["included"][0]["reason"] == "confirmed_subject_match"
    assert result["included"][0]["evidence"]["identity"]["value"] == "GRB 260610B"


def test_grouping_excludes_confirmed_other_event_even_with_body_mention() -> None:
    result = _group(
        [
            _circular(
                circular_id=44891,
                subject="GRB 260610A: Fermi GBM",
                body="This report mentions GRB 260610b only as a nearby comparison.",
            )
        ]
    )

    assert result["n_included"] == 0
    assert result["excluded"][0]["reason"] == "confirmed_other_event"
    evidence = result["excluded"][0]["evidence"]
    assert evidence["confirmed_subject_identities"][0]["value"] == "GRB 260610A"
    assert evidence["suppressed_body_match"]["identity"]["value"] == "GRB 260610B"


def test_grouping_includes_body_mention_when_subject_has_no_confirmed_identity() -> None:
    result = _group(
        [
            _circular(
                circular_id=2,
                subject="Optical follow-up report",
                body="We detect AT2026owq in follow-up imaging.",
            )
        ]
    )

    assert result["n_included"] == 1
    assert result["included"][0]["reason"] == "body_mention"
    assert result["included"][0]["evidence"]["identity"]["value"] == "AT 2026owq"


def test_nonstandard_alias_matches_by_normalized_direct_text() -> None:
    result = _group(
        [
            _circular(
                circular_id=3,
                subject="Optical follow-up report",
                body="The source 2026owq is detected in the image.",
            )
        ],
        aliases=["2026owq"],
    )

    assert result["n_included"] == 1
    assert result["included"][0]["reason"] == "body_mention"
    assert result["included"][0]["evidence"]["match_type"] == "normalized_body_text"


def test_canonical_aliases_marks_unrecognized_aliases() -> None:
    aliases = canonical_aliases(["GRB 260610B", "2026owq"])

    assert aliases["GRB 260610B"]["canonical"] == "GRB 260610B"
    assert aliases["GRB 260610B"]["recognizable"] is True
    assert aliases["2026owq"]["canonical"] is None
    assert aliases["2026owq"]["recognizable"] is False


def test_circular_matches_event_supports_normalized_subject_identity() -> None:
    alias_info = {"aliases": list(canonical_aliases(["2026owq"]).values()), "body_text": ""}

    belongs, reason, evidence = circular_matches_event(
        subject_identities=[{"value": "2026owq", "text": "2026owq"}],
        body_identities=[],
        event_alias_info=alias_info,
    )

    assert belongs is True
    assert reason == "confirmed_subject_match"
    assert evidence["alias"]["raw"] == "2026owq"


def test_grouping_includes_format_variation_via_canonical_identity() -> None:
    result = _group(
        [
            _circular(
                circular_id=4,
                subject="GRB260610B",
                body="This circular reports the same event.",
            )
        ]
    )

    assert result["n_included"] == 1
    assert result["included"][0]["reason"] == "confirmed_subject_match"
    assert result["included"][0]["evidence"]["identity"]["value"] == "GRB 260610B"


def test_grouping_excludes_unrelated_circular_without_event_mention_as_no_match() -> None:
    result = _group(
        [
            _circular(
                circular_id=5,
                subject="GRB 251201A",
                body="This circular reports a different burst without mentioning the target.",
            )
        ]
    )

    assert result["n_included"] == 0
    assert result["excluded"][0]["reason"] == "no_match"


def _group(circulars: list[dict[str, object]], aliases: list[str] | None = None) -> dict[str, object]:
    return group_event_circulars(
        source_id="2026owq",
        title="GRB 260610B / AT2026owq",
        aliases=aliases or ALIASES,
        circulars=circulars,
    )


def _circular(circular_id: int, subject: str, body: str) -> dict[str, object]:
    return {
        "circular_id": circular_id,
        "subject": subject,
        "body": body,
        "created_on": f"2026-06-10T00:{circular_id % 60:02d}:00Z",
        "submitter": "Unit Test",
    }
