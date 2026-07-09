from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from cassis import Cas, load_typesystem

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


ASTRO_EVIDENCE_TYPE = "webanno.custom.ASTRO_EVIDENCE"
SENTENCE_TYPE = "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Sentence"
TOKEN_TYPE = "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Token"
TYPESYSTEM_PATH = "data/inception/TypeSystem.xml"
MISSING_TYPESYSTEM_MESSAGE = (
    "Copy your TypeSystem.xml (exported from INCEpTION as UIMA CAS XMI XML 1.0) "
    "to data/inception/TypeSystem.xml and run the command again"
)


def export_document_to_xmi(
    doc: CanonicalDocument,
    annotations: Sequence[EventEvidenceAnnotation],
    typesystem_path: str | Path,
    out_path: str | Path,
) -> None:
    typesystem_file = Path(typesystem_path)
    if not typesystem_file.exists():
        print(MISSING_TYPESYSTEM_MESSAGE)
        return

    with typesystem_file.open("rb") as handle:
        typesystem = load_typesystem(handle)

    cas = Cas(typesystem=typesystem)
    cas.sofa_string = doc.rendered_text

    _add_minimal_segmentation(cas, typesystem, doc.rendered_text)
    layer = typesystem.get_type(ASTRO_EVIDENCE_TYPE)

    for annotation in annotations:
        expected_text = cas.sofa_string[annotation.span_start : annotation.span_end]
        if expected_text != annotation.text:
            raise ValueError(
                f"Annotation text mismatch at {annotation.span_start}-{annotation.span_end}: "
                f"{annotation.text!r} != {expected_text!r}"
            )
        cas.add(
            layer(
                begin=annotation.span_start,
                end=annotation.span_end,
                label=annotation.label,
                target=annotation.target,
                certainty=annotation.certainty,
                value=annotation.value or "",
                unit=annotation.unit or "",
                comment=annotation.comment or "",
            )
        )

    output_file = Path(out_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    cas.to_xmi(output_file)


def _add_minimal_segmentation(cas: Cas, typesystem: object, text: str) -> None:
    try:
        sentence_type = typesystem.get_type(SENTENCE_TYPE)  # type: ignore[attr-defined]
        token_type = typesystem.get_type(TOKEN_TYPE)  # type: ignore[attr-defined]
    except Exception:
        return

    for begin, end in _line_spans(text):
        if begin < end:
            cas.add(sentence_type(begin=begin, end=end))

    for match in re.finditer(r"\S+", text):
        cas.add(token_type(begin=match.start(), end=match.end()))


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"\n", text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return spans
