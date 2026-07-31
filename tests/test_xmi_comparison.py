from __future__ import annotations

from pathlib import Path

import pytest
from cassis import Cas, TypeSystem

from skyportal_corpus.evaluation.xmi_comparison import (
    AUTOMATIC_ONLY,
    EVENT_EVIDENCE_LAYER,
    EXACT_MATCH,
    EXPERT_ONLY,
    FEATURE_CHANGED,
    HUMAN_REJECTION_MARKER_EXCLUDED,
    PHOTOMETRY_LAYER,
    RELABELED,
    SPAN_ADJUSTED,
    AnnotationRecord,
    CanonicalTextMismatchError,
    InvalidAnnotationError,
    MissingLayerError,
    compare_xmi,
    match_annotations,
    normalize_feature_value,
    validate_annotation_record,
)


def _record(
    begin: int,
    end: int,
    label: str,
    *,
    layer: str = EVENT_EVIDENCE_LAYER,
    index: int = 0,
    text: str = "synthetic",
    features: dict[str, object] | None = None,
) -> AnnotationRecord:
    raw = features or {}
    return AnnotationRecord(
        layer=layer,
        original_index=index,
        begin=begin,
        end=end,
        label=label,
        covered_text=text,
        raw_features=raw,
        normalized_features={
            name: normalize_feature_value(value) for name, value in raw.items()
        },
    )


def test_exact_annotation_match() -> None:
    automatic = _record(0, 9, "EVENT_IDENTITY", features={"target": "event"})
    expert = _record(0, 9, "EVENT_IDENTITY", features={"target": "event"})

    matches = match_annotations([automatic], [expert])

    assert [match.category for match in matches] == [EXACT_MATCH]
    assert matches[0].score == pytest.approx(1.0)


def test_feature_only_change() -> None:
    automatic = _record(0, 9, "EVENT_IDENTITY", features={"comment": ""})
    expert = _record(0, 9, "EVENT_IDENTITY", features={"comment": "reviewed"})

    match = match_annotations([automatic], [expert])[0]

    assert match.category == FEATURE_CHANGED
    assert [difference.feature for difference in match.feature_differences] == ["comment"]


def test_adjusted_boundaries() -> None:
    automatic = _record(0, 9, "REDSHIFT_EVENT", text="synthetic")
    expert = _record(1, 9, "REDSHIFT_EVENT", text="ynthetic")

    match = match_annotations([automatic], [expert])[0]

    assert match.category == SPAN_ADJUSTED


def test_relabelled_annotation() -> None:
    automatic = _record(0, 9, "LIGHTCURVE_EVOLUTION")
    expert = _record(0, 9, "CLASSIFICATION_INTERPRETATION")

    match = match_annotations([automatic], [expert])[0]

    assert match.category == RELABELED


def test_automatic_only_annotation() -> None:
    automatic = _record(0, 9, "EVENT_IDENTITY")

    match = match_annotations([automatic], [])[0]

    assert match.category == AUTOMATIC_ONLY
    assert match.expert is None


def test_expert_only_annotation() -> None:
    expert = _record(0, 9, "EVENT_IDENTITY")

    match = match_annotations([], [expert])[0]

    assert match.category == EXPERT_ONLY
    assert match.automatic is None


def test_one_to_one_conflict_resolution_prefers_exact_span() -> None:
    automatic = _record(0, 9, "EVENT_IDENTITY")
    exact = _record(0, 9, "EVENT_IDENTITY", index=1)
    overlap = _record(0, 8, "EVENT_IDENTITY", index=0, text="syntheti")

    matches = match_annotations([automatic], [overlap, exact])

    paired = [match for match in matches if match.automatic and match.expert]
    assert len(paired) == 1
    assert paired[0].expert == exact
    assert sum(match.category == EXPERT_ONLY for match in matches) == 1


def test_deterministic_tie_breaking_uses_span_then_index() -> None:
    automatic = _record(1, 4, "EVENT_IDENTITY", text="bcd")
    left = _record(0, 3, "EVENT_IDENTITY", index=4, text="abc")
    right = _record(2, 5, "EVENT_IDENTITY", index=0, text="cde")

    first = match_annotations([automatic], [right, left])
    second = match_annotations([automatic], [left, right])

    first_paired = next(match for match in first if match.automatic and match.expert)
    second_paired = next(match for match in second if match.automatic and match.expert)
    assert first_paired.expert.begin == 0
    assert second_paired.expert.begin == 0
    assert first == second


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("  repeated\n whitespace  ", "repeated whitespace"),
        ("001.2300", "1.23"),
        (True, "true"),
        ("2026-01-02T03:04:05Z", "2026-01-02T03:04:05+00:00"),
        ([" a ", "2.0"], '["a","2"]'),
        ("mJy", "mJy"),
    ],
)
def test_feature_normalization(value: object, expected: str) -> None:
    assert normalize_feature_value(value) == expected


def test_human_rejection_marker_exclusion() -> None:
    automatic = _record(
        0,
        9,
        "TRIGGER_TIME",
        features={"certainty": "confirmed", "comment": ""},
    )
    expert = _record(
        0,
        9,
        "TRIGGER_TIME",
        features={
            "certainty": "rejected",
            "comment": "Start of observation, not trigger time",
        },
    )

    excluded = match_annotations([automatic], [expert])
    included = match_annotations(
        [automatic],
        [expert],
        exclude_human_rejection_markers=False,
    )

    assert excluded[0].category == HUMAN_REJECTION_MARKER_EXCLUDED
    assert included[0].category == FEATURE_CHANGED


def test_invalid_span_failure() -> None:
    record = _record(0, 20, "EVENT_IDENTITY", text="too long")

    with pytest.raises(InvalidAnnotationError, match="Invalid EVENT_EVIDENCE span"):
        validate_annotation_record(record, "short")


def test_missing_label_failure() -> None:
    record = _record(0, 5, "", text="short")

    with pytest.raises(InvalidAnnotationError, match="Missing required label"):
        validate_annotation_record(record, "short")


def _synthetic_typesystem(path: Path) -> TypeSystem:
    typesystem = TypeSystem()
    evidence = typesystem.create_type(
        "webanno.custom.ASTRO_EVIDENCE",
        supertypeName="uima.tcas.Annotation",
    )
    for feature in ("label", "target", "certainty", "value", "unit", "comment"):
        typesystem.create_feature(evidence, feature, "uima.cas.String")
    photometry = typesystem.create_type(
        "webanno.custom.PHOTOMETRIC_MEASUREMENT",
        supertypeName="uima.tcas.Annotation",
    )
    for feature in (
        "measurement_type",
        "target",
        "certainty",
        "magnitude_or_limit",
        "magnitude_error",
        "limit_sigma",
        "unit",
        "photometric_band",
        "photometric_system",
        "obs_time_raw",
        "obs_time_type",
        "obs_time_reference",
        "exposure_time_raw",
        "timezone_raw",
        "instrument",
        "comment",
    ):
        typesystem.create_feature(photometry, feature, "uima.cas.String")
    summary = typesystem.create_type(
        "webanno.custom.EVENT_SUMMARY",
        supertypeName="uima.cas.AnnotationBase",
    )
    typesystem.create_feature(summary, "review_priority", "uima.cas.String")
    typesystem.to_xml(path)
    return typesystem


def _write_synthetic_xmi(
    path: Path,
    typesystem: TypeSystem,
    text: str,
    *,
    include_evidence: bool = True,
    include_photometry: bool = True,
    invalid_span: bool = False,
    missing_evidence_label: bool = False,
) -> None:
    cas = Cas(typesystem=typesystem)
    cas.sofa_string = text
    if include_evidence:
        evidence = typesystem.get_type("webanno.custom.ASTRO_EVIDENCE")
        cas.add(
            evidence(
                begin=0,
                end=len(text) + 1 if invalid_span else 5,
                label=None if missing_evidence_label else "EVENT_IDENTITY",
                target="event",
                certainty="confirmed",
                value="synthetic",
                unit="",
                comment="",
            )
        )
    if include_photometry:
        photometry = typesystem.get_type("webanno.custom.PHOTOMETRIC_MEASUREMENT")
        cas.add(
            photometry(
                begin=6,
                end=min(10, len(text)),
                measurement_type="detection",
                target="counterpart",
                certainty="confirmed",
                magnitude_or_limit="19.2",
                magnitude_error="0.1",
                limit_sigma="",
                unit="mag",
                photometric_band="r",
                photometric_system="AB",
                obs_time_raw="",
                obs_time_type="unclear",
                obs_time_reference="unknown",
                exposure_time_raw="",
                timezone_raw="",
                instrument="",
                comment="",
            )
        )
    cas.to_xmi(path)


def test_canonical_text_mismatch_failure(tmp_path: Path) -> None:
    typesystem_path = tmp_path / "TypeSystem.xml"
    typesystem = _synthetic_typesystem(typesystem_path)
    automatic = tmp_path / "automatic.xmi"
    expert = tmp_path / "expert.xmi"
    _write_synthetic_xmi(automatic, typesystem, "alpha beta")
    _write_synthetic_xmi(expert, typesystem, "alpha zeta")

    with pytest.raises(CanonicalTextMismatchError, match="Canonical sofa texts differ"):
        compare_xmi(automatic, expert, typesystem_path)


@pytest.mark.filterwarnings("ignore:Not mapping .* offset:UserWarning")
def test_invalid_xmi_span_failure(tmp_path: Path) -> None:
    typesystem_path = tmp_path / "TypeSystem.xml"
    typesystem = _synthetic_typesystem(typesystem_path)
    automatic = tmp_path / "automatic.xmi"
    expert = tmp_path / "expert.xmi"
    _write_synthetic_xmi(automatic, typesystem, "alpha beta", invalid_span=True)
    _write_synthetic_xmi(expert, typesystem, "alpha beta")

    with pytest.raises(InvalidAnnotationError, match="Invalid EVENT_EVIDENCE span"):
        compare_xmi(automatic, expert, typesystem_path)


def test_missing_annotation_layer_failure(tmp_path: Path) -> None:
    typesystem_path = tmp_path / "TypeSystem.xml"
    typesystem = _synthetic_typesystem(typesystem_path)
    automatic = tmp_path / "automatic.xmi"
    expert = tmp_path / "expert.xmi"
    _write_synthetic_xmi(
        automatic,
        typesystem,
        "alpha beta",
        include_photometry=False,
    )
    _write_synthetic_xmi(expert, typesystem, "alpha beta")

    with pytest.raises(MissingLayerError, match="PHOTOMETRIC_MEASUREMENT"):
        compare_xmi(automatic, expert, typesystem_path)


def test_missing_expert_label_requires_explicit_compatibility_flag(tmp_path: Path) -> None:
    typesystem_path = tmp_path / "TypeSystem.xml"
    typesystem = _synthetic_typesystem(typesystem_path)
    automatic = tmp_path / "automatic.xmi"
    expert = tmp_path / "expert.xmi"
    _write_synthetic_xmi(automatic, typesystem, "alpha beta")
    _write_synthetic_xmi(
        expert,
        typesystem,
        "alpha beta",
        missing_evidence_label=True,
    )

    with pytest.raises(InvalidAnnotationError, match="Missing required label"):
        compare_xmi(automatic, expert, typesystem_path)

    result = compare_xmi(
        automatic,
        expert,
        typesystem_path,
        allow_missing_expert_labels=True,
    )
    assert result.expert.missing_label_annotations == (
        "EVENT_EVIDENCE:0:5:original_index=0",
    )
    assert any(match.category == RELABELED for match in result.matches)


def test_repeated_evaluation_has_deterministic_ordering(tmp_path: Path) -> None:
    typesystem_path = tmp_path / "TypeSystem.xml"
    typesystem = _synthetic_typesystem(typesystem_path)
    automatic = tmp_path / "automatic.xmi"
    expert = tmp_path / "expert.xmi"
    _write_synthetic_xmi(automatic, typesystem, "alpha beta")
    _write_synthetic_xmi(expert, typesystem, "alpha beta")

    first = compare_xmi(automatic, expert, typesystem_path)
    second = compare_xmi(automatic, expert, typesystem_path)

    assert first.matches == second.matches
    assert first.metrics == second.metrics
