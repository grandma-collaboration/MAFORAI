from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.inception_v2.xmi_export import TYPESYSTEM_PATH


def test_xmi_roundtrip_preserves_offsets_and_features(tmp_path: Path) -> None:
    typesystem_path = PROJECT_ROOT / TYPESYSTEM_PATH
    if not typesystem_path.exists():
        pytest.skip("Falta TypeSystem.xml")

    from skyportal_corpus.inception_v2.xmi_export import export_document_to_xmi
    from skyportal_corpus.inception_v2.xmi_roundtrip import roundtrip_check

    doc = render_canonical(
        circular_id=240625,
        subject="GRB 240625A synthetic report",
        created_on="2024-06-25T03:00:00+00:00",
        body="At 02:16:38 UT on 1 Jan 2023, the Fermi GBM triggered and located GRB 240625A.",
    )
    identity_text = "GRB 240625A"
    trigger_text = "02:16:38 UT on 1 Jan 2023"
    identity_start = doc.rendered_text.index(identity_text)
    trigger_start = doc.rendered_text.index(trigger_text)

    annotations = [
        EventEvidenceAnnotation(
            circular_id=doc.circular_id,
            text_sha256=doc.text_sha256,
            span_start=identity_start,
            span_end=identity_start + len(identity_text),
            text=identity_text,
            label="EVENT_IDENTITY",
            target="event",
            certainty="confirmed",
            value="GRB 240625A",
            extractor_id="test",
            extractor_version="0.1",
            method="manual",
            rule_id="test.identity",
        ),
        EventEvidenceAnnotation(
            circular_id=doc.circular_id,
            text_sha256=doc.text_sha256,
            span_start=trigger_start,
            span_end=trigger_start + len(trigger_text),
            text=trigger_text,
            label="TRIGGER_TIME",
            target="event",
            certainty="confirmed",
            value="2023-01-01T02:16:38",
            extractor_id="test",
            extractor_version="0.1",
            method="manual",
            rule_id="test.trigger_time",
        ),
    ]

    out_path = tmp_path / "roundtrip.xmi"
    export_document_to_xmi(doc, annotations, typesystem_path, out_path)
    result = roundtrip_check(out_path, typesystem_path, annotations, doc.rendered_text)

    assert result["text_matches"] is True
    assert result["all_spans_ok"] is True
    assert result["all_features_ok"] is True
    assert result["n_original"] == result["n_roundtripped"]
