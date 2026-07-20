from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.extraction_v2.identity_index import (
    build_identity_index_records,
    read_identity_index,
    write_identity_index,
)


def test_identity_index_preserves_raw_body_and_subject_body_partition() -> None:
    body = "We compare this event with GRB 240912B.\nThe source remains detectable."

    records = build_identity_index_records(
        [
            {
                "circular_id": 100,
                "subject": "GRB 240912A: discovery",
                "body": body,
                "created_on": "2024-09-12T12:00:00Z",
                "submitter": "Unit Test",
            }
        ]
    )

    assert len(records) == 1
    record = records[0]
    assert record["body_text"] == body
    assert [item["value"] for item in record["subject_identities"]] == [
        "GRB 240912A"
    ]
    assert [item["value"] for item in record["body_identities"]] == [
        "GRB 240912B"
    ]
    assert record["subject_identities"][0]["needs_review"] is False
    assert record["body_identities"][0]["needs_review"] is True


def test_identity_index_parquet_roundtrip_is_exact(tmp_path: Path) -> None:
    records = build_identity_index_records(
        [
            {
                "circular_id": 101,
                "subject": "GRB240912A: follow-up",
                "body": "The source AT 2024xyz is the optical counterpart of GRB 240912A.",
                "created_on": "2024-09-13T00:00:00Z",
                "submitter": "Unit Test",
            }
        ]
    )
    output_path = tmp_path / "identity_index.parquet"

    write_identity_index(records, output_path)

    assert read_identity_index(output_path) == records
