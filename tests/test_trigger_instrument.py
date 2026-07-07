from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.trigger_instrument import TriggerInstrumentExtractor


def test_trigger_instrument_clear_swift_bat_trigger() -> None:
    doc = render_canonical(
        circular_id=1,
        subject="Swift BAT trigger report",
        body="At 21:04:43 UT, the Swift Burst Alert Telescope (BAT) triggered and located GRB 230116D",
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.label == "TRIGGER_INSTRUMENT"
    assert annotation.value == "Swift/BAT"
    assert annotation.target == "instrument"
    assert annotation.certainty == "confirmed"
    assert annotation.needs_review is False
    assert annotation.text == doc.rendered_text[annotation.span_start : annotation.span_end]
    assert annotation.verify(doc.rendered_text)


def test_trigger_instrument_followup_is_not_captured() -> None:
    doc = render_canonical(
        circular_id=2,
        subject="Swift XRT follow-up report",
        body="The XRT began observing the field at 21:06:54 UT.",
    )

    assert TriggerInstrumentExtractor().extract(doc) == []


def test_trigger_instrument_mixed_trigger_and_followup_keeps_only_trigger() -> None:
    doc = render_canonical(
        circular_id=3,
        subject="Swift follow-up report",
        body=(
            "the BAT triggered and located the burst. "
            "The XRT began observing the field. UVOT took a finding chart"
        ),
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].value == "Swift/BAT"
    assert annotations[0].text == "BAT"
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_instrument_multi_trigger_instruments_need_review() -> None:
    doc = render_canonical(
        circular_id=4,
        subject="Multi-instrument trigger report",
        body="GRB 230328B was triggered by Swift-BAT and Fermi-GBM",
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert [annotation.value for annotation in annotations] == ["Swift/BAT", "Fermi/GBM"]
    assert all(annotation.needs_review is True for annotation in annotations)
    assert all(annotation.target == "instrument" for annotation in annotations)
    assert all(annotation.certainty == "confirmed" for annotation in annotations)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_trigger_instrument_deduplicates_same_canonical_instrument() -> None:
    doc = render_canonical(
        circular_id=5,
        subject="Repeated instrument report",
        body="Swift/BAT triggered and located the burst; later the BAT detected extended emission.",
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].value == "Swift/BAT"
    assert annotations[0].text == "Swift/BAT"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_instrument_negative_optical_followup_only() -> None:
    doc = render_canonical(
        circular_id=6,
        subject="Optical follow-up report",
        body="MASTER observed the field and reported photometry from optical imaging.",
    )

    assert TriggerInstrumentExtractor().extract(doc) == []


def test_trigger_instrument_rejects_fermi_lat_boresight_reference_but_keeps_gbm_trigger_time() -> None:
    doc = render_canonical(
        circular_id=7,
        subject="Boresight geometry report",
        body="The angle from the Fermi LAT boresight at the GBM trigger time is 104 degrees.",
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert [annotation.value for annotation in annotations] == ["Fermi/GBM"]
    assert annotations[0].text == "GBM"
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_instrument_rejects_fermi_lat_catalog_reference() -> None:
    doc = render_canonical(
        circular_id=8,
        subject="Catalog reference report",
        body=(
            "Three gamma-ray sources listed in the 4FGL Fermi-LAT catalog "
            "are located within the 90% containment region."
        ),
    )

    assert TriggerInstrumentExtractor().extract(doc) == []


def test_trigger_instrument_rejects_fermi_lat_collaboration_citation() -> None:
    doc = render_canonical(
        circular_id=9,
        subject="Citation report",
        body="The Fermi-LAT collaboration 2022, ApJS, 260, 53.",
    )

    assert TriggerInstrumentExtractor().extract(doc) == []


def test_trigger_instrument_rejects_detection_reference_heading() -> None:
    doc = render_canonical(
        circular_id=10,
        subject="Reference heading report",
        body="Fermi GBM detection: Lesage et al., GCN Circ. 33288.",
    )

    assert TriggerInstrumentExtractor().extract(doc) == []


def test_trigger_instrument_keeps_legitimate_ipn_multi_instrument_detection() -> None:
    doc = render_canonical(
        circular_id=11,
        subject="IPN multi-instrument report",
        body=(
            "This burst was detected by Fermi (GBM trigger 697674761), "
            "Konus-Wind, INTEGRAL (SPI-ACS), Swift (BAT)."
        ),
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert {annotation.value for annotation in annotations} == {
        "Fermi/GBM",
        "Konus-Wind",
        "INTEGRAL",
        "Swift/BAT",
    }
    assert all(annotation.needs_review is True for annotation in annotations)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_trigger_instrument_keeps_legitimate_icecube_detection() -> None:
    doc = render_canonical(
        circular_id=12,
        subject="IceCube event report",
        body="On 2023-02-01 at 06:20:54.42 UT IceCube detected a track-like event.",
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].value == "IceCube"
    assert annotations[0].text == "IceCube"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_instrument_keeps_fermi_gbm_triggered_and_located() -> None:
    doc = render_canonical(
        circular_id=13,
        subject="Fermi report",
        body="the Fermi Gamma-ray Burst Monitor (GBM) triggered and located GRB 230101A",
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].value == "Fermi/GBM"
    assert annotations[0].text == "Fermi Gamma-ray Burst Monitor"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_instrument_rejects_lat_data_analysis_reference() -> None:
    doc = render_canonical(
        circular_id=14,
        subject="LAT analysis report",
        body=(
            "Based on a preliminary analysis of the LAT data, "
            "these objects are not significantly detected."
        ),
    )

    assert TriggerInstrumentExtractor().extract(doc) == []


def test_trigger_instrument_rejects_available_lat_data_after_gbm_trigger_context() -> None:
    doc = render_canonical(
        circular_id=15,
        subject="Analysis after trigger report",
        body="10 ks since the GBM trigger, based on available LAT data.",
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert "Fermi/LAT" not in {annotation.value for annotation in annotations}
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_trigger_instrument_keeps_gbm_trigger_data_reference() -> None:
    doc = render_canonical(
        circular_id=16,
        subject="Trigger data report",
        body="using the Fermi GBM trigger data, is RA = 206.3",
    )

    annotations = TriggerInstrumentExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].value == "Fermi/GBM"
    assert annotations[0].text == "Fermi GBM"
    assert annotations[0].verify(doc.rendered_text)
