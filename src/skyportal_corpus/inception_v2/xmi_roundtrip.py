from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cassis import load_cas_from_xmi, load_typesystem

from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.inception_v2.xmi_export import ASTRO_EVIDENCE_TYPE


def roundtrip_check(
    xmi_path: str | Path,
    typesystem_path: str | Path,
    original_annotations: Sequence[EventEvidenceAnnotation],
    original_text: str,
) -> dict[str, Any]:
    with Path(typesystem_path).open("rb") as handle:
        typesystem = load_typesystem(handle)
    with Path(xmi_path).open("rb") as handle:
        cas = load_cas_from_xmi(handle, typesystem=typesystem)

    roundtripped = list(cas.select(ASTRO_EVIDENCE_TYPE))
    originals_by_span = {
        (annotation.span_start, annotation.span_end): annotation for annotation in original_annotations
    }

    discrepancies: list[str] = []
    text_matches = cas.sofa_string == original_text

    all_spans_ok = True
    for annotation in roundtripped:
        span = (int(annotation.begin), int(annotation.end))
        original = originals_by_span.get(span)
        if original is None:
            discrepancies.append(f"Missing original annotation for span {span[0]}-{span[1]}")
            all_spans_ok = False
            continue
        if cas.sofa_string[span[0] : span[1]] != original.text:
            discrepancies.append(f"Span text mismatch for {span[0]}-{span[1]}")
            all_spans_ok = False

    all_features_ok = True
    roundtripped_by_span = {(int(annotation.begin), int(annotation.end)): annotation for annotation in roundtripped}
    for span, original in originals_by_span.items():
        annotation = roundtripped_by_span.get(span)
        if annotation is None:
            discrepancies.append(f"Missing roundtripped annotation for span {span[0]}-{span[1]}")
            all_spans_ok = False
            all_features_ok = False
            continue
        for feature_name in ("label", "target", "certainty", "value", "unit", "comment"):
            original_value = _annotation_value(original, feature_name)
            roundtrip_value = str(getattr(annotation, feature_name, "") or "")
            if original_value != roundtrip_value:
                discrepancies.append(
                    f"Feature mismatch for {span[0]}-{span[1]} {feature_name}: "
                    f"{original_value!r} != {roundtrip_value!r}"
                )
                all_features_ok = False

    return {
        "text_matches": text_matches,
        "n_original": len(original_annotations),
        "n_roundtripped": len(roundtripped),
        "all_spans_ok": all_spans_ok,
        "all_features_ok": all_features_ok,
        "discrepancies": discrepancies,
    }


def _annotation_value(annotation: EventEvidenceAnnotation, feature_name: str) -> str:
    value = getattr(annotation, feature_name)
    return str(value or "")
