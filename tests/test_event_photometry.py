from __future__ import annotations

from pathlib import Path

from cassis import load_cas_from_xmi, load_typesystem

from skyportal_corpus.canonical.document import CanonicalDocument, render_canonical
from skyportal_corpus.extraction_v2.event_annotations import extract_event_annotations
from skyportal_corpus.extraction_v2.event_document import build_event_document
from skyportal_corpus.extraction_v2.event_photometry import extract_event_photometry
from skyportal_corpus.extraction_v2.photometry_annotations import (
    deduplicate_photometry_measurements,
)
from skyportal_corpus.extraction_v2.photometry_prose import ProsePhotometryExtractor
from skyportal_corpus.inception_v2.event_xmi_export import (
    event_layers_roundtrip_check,
    export_event_layers_xmi,
)
from skyportal_corpus.inception_v2.photometry_xmi_export import PHOTOMETRY_TYPE
from skyportal_corpus.inception_v2.xmi_export import ASTRO_EVIDENCE_TYPE


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TYPESYSTEM_PATH = PROJECT_ROOT / "data" / "inception" / "TypeSystem.xml"


def test_event_photometry_translates_local_offsets_and_keeps_provenance() -> None:
    circulars = _circulars()
    event_doc = build_event_document("evt", "GRB 260610B", circulars)
    circular_docs = _canonical_documents(circulars)
    errors: list[dict[str, object]] = []

    measurements = extract_event_photometry(
        event_doc,
        circular_docs,
        errors=errors,
    )

    assert errors == []
    assert measurements
    assert all(item.verify(event_doc.event_rendered_text) for item in measurements)
    assert all(
        event_doc.event_rendered_text[item.span_start : item.span_end] == item.text
        for item in measurements
    )
    assert all(item.text_sha256 == event_doc.event_text_sha256 for item in measurements)

    first = [item for item in measurements if item.source_circular_id == 1]
    second = [item for item in measurements if item.source_circular_id == 2]
    assert first
    assert second
    assert min(item.span_start for item in second) > max(item.span_start for item in first)
    assert all(item.circular_id == item.source_circular_id for item in measurements)


def test_event_xmi_contains_both_layers_and_roundtrips(tmp_path: Path) -> None:
    circulars = _circulars()
    event_doc = build_event_document("evt", "GRB 260610B", circulars)
    circular_docs = _canonical_documents(circulars)
    evidence_errors: list[dict[str, object]] = []
    photometry_errors: list[dict[str, object]] = []
    evidence = extract_event_annotations(
        event_doc,
        circular_docs,
        errors=evidence_errors,
    )
    measurements = extract_event_photometry(
        event_doc,
        circular_docs,
        errors=photometry_errors,
    )
    out_path = tmp_path / "event-with-photometry.xmi"

    export_event_layers_xmi(
        event_doc,
        evidence,
        measurements,
        TYPESYSTEM_PATH,
        out_path,
    )
    result = event_layers_roundtrip_check(
        out_path,
        TYPESYSTEM_PATH,
        event_doc,
        evidence,
        measurements,
    )

    assert evidence_errors == []
    assert photometry_errors == []
    assert result["all_ok"] is True
    assert result["event_evidence"]["n_original"] == len(evidence)
    assert result["event_evidence"]["n_roundtripped"] == len(evidence)
    assert result["event_evidence"]["all_spans_ok"] is True
    assert result["event_evidence"]["all_features_ok"] is True
    assert result["photometry"]["n_original"] == len(measurements)
    assert result["photometry"]["n_roundtripped"] == len(measurements)
    assert result["photometry"]["all_spans_ok"] is True
    assert result["photometry"]["all_features_ok"] is True

    with TYPESYSTEM_PATH.open("rb") as handle:
        typesystem = load_typesystem(handle)
    with out_path.open("rb") as handle:
        cas = load_cas_from_xmi(handle, typesystem=typesystem)
    assert cas.sofa_string == event_doc.event_rendered_text
    assert len(list(cas.select(ASTRO_EVIDENCE_TYPE))) == len(evidence)
    assert len(list(cas.select(PHOTOMETRY_TYPE))) == len(measurements)


def test_event_xmi_uses_valid_defaults_for_missing_photometry_tagsets(
    tmp_path: Path,
) -> None:
    circulars = _circulars()
    event_doc = build_event_document("evt", "GRB 260610B", circulars)
    circular_docs = _canonical_documents(circulars)
    evidence = extract_event_annotations(event_doc, circular_docs)
    measurements = extract_event_photometry(event_doc, circular_docs)
    missing_values = measurements[0].model_copy(
        update={
            "photometric_system": None,
            "obs_time_raw": None,
            "obs_time_type": None,
            "obs_time_reference": None,
        }
    )
    out_path = tmp_path / "event-missing-tagsets.xmi"

    export_event_layers_xmi(
        event_doc,
        evidence,
        [missing_values],
        TYPESYSTEM_PATH,
        out_path,
    )
    result = event_layers_roundtrip_check(
        out_path,
        TYPESYSTEM_PATH,
        event_doc,
        evidence,
        [missing_values],
    )

    with TYPESYSTEM_PATH.open("rb") as handle:
        typesystem = load_typesystem(handle)
    with out_path.open("rb") as handle:
        cas = load_cas_from_xmi(handle, typesystem=typesystem)
    recovered = list(cas.select(PHOTOMETRY_TYPE))

    assert result["all_ok"] is True
    assert len(recovered) == 1
    assert recovered[0].obs_time_type == "unclear"
    assert recovered[0].obs_time_reference == "unknown"
    assert recovered[0].photometric_system == "unknown"
    assert str(recovered[0].obs_time_raw or "") == ""


def test_event_photometry_suppresses_prose_measurements_inside_table_rows() -> None:
    circulars = [
        {
            "circular_id": 38220,
            "subject": "GRB 241030A: optical photometry",
            "body": (
                "Photometry is reported in AB magnitudes.\n"
                "Date        UTstart-end          t-T0 (hours)  Exp (sec)  Filter  Magnitude\n"
                "2024-10-30  19:55:20--20:05:50  14.21          2 x 300    B       B = 19.52 +/- 0.14\n"
                "2024-10-30  19:48:10--20:08:18  14.17          2 x 600    V       V = 19.51 +/- 0.14\n"
                "2024-10-30  20:07:31--20:17:59  14.41          2 x 300    R       R = 19.10 +/- 0.04\n"
            ),
            "created_on": "2024-10-31T00:00:00Z",
            "submitter": "Observer",
        }
    ]
    event_doc = build_event_document("GRB241030", "GRB 241030A", circulars)
    circular_docs = _canonical_documents(circulars)

    prose = ProsePhotometryExtractor().extract(circular_docs[38220])
    measurements = extract_event_photometry(event_doc, circular_docs)

    assert {item.photometric_band for item in prose} >= {"B", "V", "R"}
    assert len(measurements) == 3
    assert {item.rule_id for item in measurements} == {"photometry_row.whitespace"}
    assert [item.magnitude_or_limit for item in measurements] == ["19.52", "19.51", "19.10"]
    assert all(item.verify(event_doc.event_rendered_text) for item in measurements)


def test_defensive_photometry_dedup_is_field_aware() -> None:
    circulars = _circulars()
    doc = _canonical_documents(circulars)[1]
    original = ProsePhotometryExtractor().extract(doc)[0]
    duplicate = original.model_copy()
    distinct = original.model_copy(
        update={
            "magnitude_or_limit": "20.2",
            "photometric_band": "I",
        }
    )

    deduplicated = deduplicate_photometry_measurements(
        [original, duplicate, distinct]
    )

    assert deduplicated == [original, distinct]


def _circulars() -> list[dict[str, object]]:
    return [
        {
            "circular_id": 1,
            "subject": "GRB 260610B: optical detection",
            "body": (
                "Optical observations on 2026-06-10T23:55:00 UT detected the "
                "counterpart at R = 19.2 +/- 0.1 mag (AB)."
            ),
            "created_on": "2026-06-10T23:56:00Z",
            "submitter": "First Author",
        },
        {
            "circular_id": 2,
            "subject": "GRB 260610B: tabulated photometry",
            "body": (
                "Photometry is reported in the AB system.\n\n"
                "MJD|Filter|Mag\n"
                "61102.010|r|20.1 +/- 0.1\n"
                "61102.020|r|>21.5\n"
            ),
            "created_on": "2026-06-11T00:30:00Z",
            "submitter": "Second Author",
        },
    ]


def _canonical_documents(
    circulars: list[dict[str, object]],
) -> dict[int, CanonicalDocument]:
    documents: dict[int, CanonicalDocument] = {}
    for circular in circulars:
        document = render_canonical(
            circular_id=int(circular["circular_id"]),
            subject=str(circular["subject"]),
            body=str(circular["body"]),
            created_on=str(circular["created_on"]),
            submitter=str(circular["submitter"]),
        )
        documents[document.circular_id] = document
    return documents
