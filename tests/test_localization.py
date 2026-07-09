from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.localization import LocalizationExtractor


def test_localization_decimal_position() -> None:
    doc = render_canonical(
        circular_id=1,
        subject="Localization report",
        body="the location is RA = 206.3, Dec = -21.9 (J2000 degrees)",
    )

    annotations = LocalizationExtractor().extract(doc)

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.label == "LOCALIZATION"
    assert annotation.target == "event"
    assert annotation.certainty == "confirmed"
    assert "206.3" in str(annotation.value)
    assert "-21.9" in str(annotation.value)
    assert annotation.text == doc.rendered_text[annotation.span_start : annotation.span_end]
    assert annotation.verify(doc.rendered_text)


def test_localization_decimal_position_deduplicates_nearby_sexagesimal() -> None:
    doc = render_canonical(
        circular_id=2,
        subject="Localization report",
        body=(
            "RA = 206.3, Dec = -21.9 (J2000 degrees, equivalent to "
            "J2000 13h 45m, -21d 53')"
        ),
    )

    annotations = LocalizationExtractor().extract(doc)

    assert len([annotation for annotation in annotations if annotation.rule_id == "localization.radec_decimal"]) == 1
    assert len([annotation for annotation in annotations if annotation.rule_id == "localization.radec_sexagesimal"]) == 0
    assert len(annotations) == 1
    assert annotations[0].verify(doc.rendered_text)


def test_localization_error_radius() -> None:
    doc = render_canonical(
        circular_id=3,
        subject="Localization report",
        body="The localization has a statistical uncertainty of 2.8 degrees.",
    )

    annotations = LocalizationExtractor().extract(doc)

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.rule_id == "localization.error_radius"
    assert annotation.unit in {"deg", "degrees"}
    assert annotation.value == "2.8"
    assert annotation.comment is None
    assert annotation.verify(doc.rendered_text)


def test_localization_counterpart_target() -> None:
    doc = render_canonical(
        circular_id=4,
        subject="Counterpart report",
        body="the optical counterpart is at RA = 150.1, Dec = 22.2",
    )

    annotations = LocalizationExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].target == "counterpart"
    assert annotations[0].verify(doc.rendered_text)


def test_localization_negative_without_coordinates() -> None:
    doc = render_canonical(
        circular_id=5,
        subject="Follow-up report",
        body="The source was observed in poor conditions and no position was reported.",
    )

    assert LocalizationExtractor().extract(doc) == []
