"""Deterministic one-to-one comparison of automatic and expert INCEpTION XMI.

Matching is layer-local and proceeds in three phases:

1. exact span with the same label;
2. any overlapping span with the same label;
3. exact or sufficiently strong overlap with a different label.

Candidates within each phase are greedily resolved by the explicit score

``0.60 * span_iou + 0.25 * text_similarity + 0.15 * boundary_similarity``.

Stable span, label, and original-index fields break ties. This guarantees one-to-one
matching and deterministic output without pretending to reconstruct the missing
historical evaluator.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from cassis import load_cas_from_xmi, load_typesystem

EVENT_EVIDENCE_LAYER = "EVENT_EVIDENCE"
PHOTOMETRY_LAYER = "PHOTOMETRIC_MEASUREMENT"
EXACT_MATCH = "EXACT_MATCH"
FEATURE_CHANGED = "FEATURE_CHANGED"
SPAN_ADJUSTED = "SPAN_ADJUSTED"
RELABELED = "RELABELED"
AUTOMATIC_ONLY = "AUTOMATIC_ONLY"
EXPERT_ONLY = "EXPERT_ONLY"
HUMAN_REJECTION_MARKER_EXCLUDED = "HUMAN_REJECTION_MARKER_EXCLUDED"

DEFAULT_RELABEL_IOU_THRESHOLD = 0.50
MATCH_SCORE_FORMULA = (
    "0.60 * span_iou + 0.25 * covered_text_similarity + "
    "0.15 * boundary_similarity"
)


class ComparisonError(RuntimeError):
    """Base class for explicit evaluator failures."""


class CanonicalTextMismatchError(ComparisonError):
    """Raised when automatic and expert CAS sofa texts differ."""


class TypeSystemCompatibilityError(ComparisonError):
    """Raised when a CAS cannot be loaded with the declared TypeSystem."""


class InvalidAnnotationError(ComparisonError):
    """Raised for invalid spans, missing labels, or inconsistent covered text."""


class MissingLayerError(ComparisonError):
    """Raised when a required comparison layer has no annotations."""


@dataclass(frozen=True)
class LayerDefinition:
    """UIMA type and features that define one evaluation layer."""

    name: str
    type_name: str
    label_feature: str
    compared_features: tuple[str, ...]


LAYER_DEFINITIONS = (
    LayerDefinition(
        name=EVENT_EVIDENCE_LAYER,
        type_name="webanno.custom.ASTRO_EVIDENCE",
        label_feature="label",
        compared_features=("target", "certainty", "value", "unit", "comment"),
    ),
    LayerDefinition(
        name=PHOTOMETRY_LAYER,
        type_name="webanno.custom.PHOTOMETRIC_MEASUREMENT",
        label_feature="measurement_type",
        compared_features=(
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
        ),
    ),
)
LAYER_BY_NAME = {definition.name: definition for definition in LAYER_DEFINITIONS}

# Camille.xmi contains this document-metadata feature, but the surviving TypeSystem
# revision does not. The feature is not part of either evaluated annotation layer. We
# add it explicitly in memory, record the augmentation, and otherwise load strictly.
KNOWN_COMPATIBILITY_FEATURES = (
    ("webanno.custom.EVENT_SUMMARY", "corpus_value", "uima.cas.String"),
)


@dataclass(frozen=True)
class AnnotationRecord:
    """A validated, serializable annotation from one comparison layer."""

    layer: str
    original_index: int
    begin: int
    end: int
    label: str
    covered_text: str
    raw_features: Mapping[str, Any]
    normalized_features: Mapping[str, str]


@dataclass(frozen=True)
class FeatureDifference:
    """Raw and normalized values for one unequal feature."""

    feature: str
    automatic_raw: Any
    expert_raw: Any
    automatic_normalized: str
    expert_normalized: str


@dataclass(frozen=True)
class MatchRecord:
    """One paired or orphaned comparison result."""

    layer: str
    category: str
    automatic: AnnotationRecord | None
    expert: AnnotationRecord | None
    score: float | None
    feature_differences: tuple[FeatureDifference, ...] = ()
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class LoadedXmi:
    """Validated sofa text and annotations loaded from one XMI."""

    path: Path
    file_sha256: str
    text: str
    text_sha256: str
    annotations: Mapping[str, tuple[AnnotationRecord, ...]]
    missing_label_annotations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComparisonResult:
    """Inputs, deterministic matches, and metrics with two rejection policies."""

    automatic: LoadedXmi
    expert: LoadedXmi
    typesystem_path: Path
    typesystem_sha256: str
    typesystem_augmentations: tuple[str, ...]
    relabel_iou_threshold: float
    allowed_missing_expert_labels: bool
    matches: tuple[MatchRecord, ...]
    metrics: Mapping[str, Any]
    matches_including_rejections: tuple[MatchRecord, ...]
    metrics_including_rejections: Mapping[str, Any]


_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)
_WS_RE = re.compile(r"\s+")
_OBSERVATION_REJECTION_RE = re.compile(
    r"(?i)(?:observation|\bobs\b|not\s+(?:the\s+)?trigger\s+time)"
)


def file_sha256(path: str | Path) -> str:
    """Return a streaming SHA-256 for one file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    """Return the UTF-8 SHA-256 of canonical sofa text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_feature_value(value: Any) -> str:
    """Normalize representational differences without erasing scientific meaning.

    Rules are intentionally conservative:

    * missing, ``None``, and empty strings become ``""``;
    * surrounding and repeated whitespace is collapsed;
    * booleans use lowercase JSON spelling;
    * pure numeric strings use a canonical decimal representation;
    * ISO-8601 timestamps normalize ``Z`` to an explicit UTC offset;
    * sequences and mappings are serialized deterministically while preserving order;
    * scientific units and ordinary strings remain case-sensitive.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Mapping):
        normalized = {
            str(key): normalize_feature_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
        return json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return json.dumps(
            [normalize_feature_value(item) for item in value],
            separators=(",", ":"),
        )
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _normalize_number(str(value))

    text = _WS_RE.sub(" ", str(value).strip())
    if not text:
        return ""
    lowered = text.casefold()
    if lowered in {"true", "false"}:
        return lowered
    if _NUMBER_RE.fullmatch(text):
        return _normalize_number(text)
    if _ISO_RE.fullmatch(text):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat()
    return text


def _normalize_number(value: str) -> str:
    try:
        number = Decimal(value)
    except InvalidOperation:
        return value
    if not number.is_finite():
        return value
    normalized = format(number.normalize(), "f")
    return "0" if normalized in {"-0", "+0"} else normalized


def compare_xmi(
    automatic_xmi: str | Path,
    expert_xmi: str | Path,
    typesystem_path: str | Path,
    *,
    relabel_iou_threshold: float = DEFAULT_RELABEL_IOU_THRESHOLD,
    allow_missing_expert_labels: bool = False,
) -> ComparisonResult:
    """Load two XMI files, validate comparability, and compute both policies."""
    if not 0.0 < relabel_iou_threshold <= 1.0:
        raise ValueError("relabel_iou_threshold must be in (0, 1]")

    automatic_path = Path(automatic_xmi)
    expert_path = Path(expert_xmi)
    typesystem_file = Path(typesystem_path)
    for path in (automatic_path, expert_path, typesystem_file):
        if not path.is_file():
            raise ComparisonError(f"Required input file does not exist: {path}")

    typesystem, augmentations = _load_comparison_typesystem(
        typesystem_file,
        (automatic_path, expert_path),
    )
    automatic = _load_xmi(automatic_path, typesystem, allow_missing_labels=False)
    expert = _load_xmi(
        expert_path,
        typesystem,
        allow_missing_labels=allow_missing_expert_labels,
    )
    if automatic.text != expert.text:
        divergence = _first_divergence(automatic.text, expert.text)
        raise CanonicalTextMismatchError(
            "Canonical sofa texts differ: "
            f"automatic length={len(automatic.text)} sha256={automatic.text_sha256}; "
            f"expert length={len(expert.text)} sha256={expert.text_sha256}; "
            f"first_divergence={divergence}"
        )

    primary_matches: list[MatchRecord] = []
    inclusive_matches: list[MatchRecord] = []
    for definition in LAYER_DEFINITIONS:
        automatic_annotations = automatic.annotations[definition.name]
        expert_annotations = expert.annotations[definition.name]
        primary_matches.extend(
            match_annotations(
                automatic_annotations,
                expert_annotations,
                relabel_iou_threshold=relabel_iou_threshold,
                exclude_human_rejection_markers=True,
            )
        )
        inclusive_matches.extend(
            match_annotations(
                automatic_annotations,
                expert_annotations,
                relabel_iou_threshold=relabel_iou_threshold,
                exclude_human_rejection_markers=False,
            )
        )

    primary = tuple(sorted(primary_matches, key=_match_output_key))
    inclusive = tuple(sorted(inclusive_matches, key=_match_output_key))
    return ComparisonResult(
        automatic=automatic,
        expert=expert,
        typesystem_path=typesystem_file,
        typesystem_sha256=file_sha256(typesystem_file),
        typesystem_augmentations=augmentations,
        relabel_iou_threshold=relabel_iou_threshold,
        allowed_missing_expert_labels=allow_missing_expert_labels,
        matches=primary,
        metrics=calculate_metrics(primary),
        matches_including_rejections=inclusive,
        metrics_including_rejections=calculate_metrics(inclusive),
    )


def _load_comparison_typesystem(typesystem_path: Path, xmi_paths: Sequence[Path]):
    with typesystem_path.open("rb") as handle:
        typesystem = load_typesystem(handle)
    augmentations: list[str] = []
    xmi_bytes = b"\n".join(path.read_bytes() for path in xmi_paths)
    for type_name, feature_name, range_name in KNOWN_COMPATIBILITY_FEATURES:
        marker = f"{feature_name}=".encode("utf-8")
        layer = typesystem.get_type(type_name)
        available = {feature.name for feature in layer.features}
        if marker in xmi_bytes and feature_name not in available:
            typesystem.create_feature(type_name, feature_name, range_name)
            augmentations.append(f"{type_name}.{feature_name}:{range_name}")

    for definition in LAYER_DEFINITIONS:
        try:
            layer = typesystem.get_type(definition.type_name)
        except TypeError as exc:
            raise TypeSystemCompatibilityError(
                f"TypeSystem lacks required type {definition.type_name}"
            ) from exc
        available = {feature.name for feature in layer.features}
        required = {definition.label_feature, *definition.compared_features}
        missing = sorted(required - available)
        if missing:
            raise TypeSystemCompatibilityError(
                f"TypeSystem type {definition.type_name} lacks features: {missing}"
            )
    return typesystem, tuple(augmentations)


def _load_xmi(path: Path, typesystem, *, allow_missing_labels: bool) -> LoadedXmi:
    try:
        with path.open("rb") as handle:
            cas = load_cas_from_xmi(handle, typesystem=typesystem, lenient=False)
    except Exception as exc:
        raise TypeSystemCompatibilityError(
            f"Could not load {path} with the declared TypeSystem: {type(exc).__name__}: {exc}"
        ) from exc
    text = cas.sofa_string
    if not isinstance(text, str):
        raise ComparisonError(f"XMI has no sofa text: {path}")

    by_layer: dict[str, tuple[AnnotationRecord, ...]] = {}
    missing_labels: list[str] = []
    for definition in LAYER_DEFINITIONS:
        feature_structures = list(cas.select(definition.type_name))
        if not feature_structures:
            raise MissingLayerError(
                f"Required layer {definition.type_name} has no annotations in {path}"
            )
        records = []
        for original_index, feature_structure in enumerate(feature_structures):
            begin = int(feature_structure.begin)
            end = int(feature_structure.end)
            covered_text = feature_structure.get_covered_text()
            raw_label = getattr(feature_structure, definition.label_feature, None)
            label = str(raw_label or "").strip()
            if not label and allow_missing_labels:
                label = "<unset>"
                missing_labels.append(
                    f"{definition.name}:{begin}:{end}:original_index={original_index}"
                )
            raw_features = {
                feature: getattr(feature_structure, feature, None)
                for feature in definition.compared_features
            }
            record = AnnotationRecord(
                layer=definition.name,
                original_index=original_index,
                begin=begin,
                end=end,
                label=label,
                covered_text=covered_text,
                raw_features=raw_features,
                normalized_features={
                    feature: normalize_feature_value(value)
                    for feature, value in raw_features.items()
                },
            )
            validate_annotation_record(record, text)
            records.append(record)
        by_layer[definition.name] = tuple(sorted(records, key=_annotation_key))

    return LoadedXmi(
        path=path,
        file_sha256=file_sha256(path),
        text=text,
        text_sha256=text_sha256(text),
        annotations=by_layer,
        missing_label_annotations=tuple(missing_labels),
    )


def validate_annotation_record(record: AnnotationRecord, canonical_text: str) -> None:
    """Validate offsets, covered text, and required label for one annotation."""
    if not 0 <= record.begin < record.end <= len(canonical_text):
        raise InvalidAnnotationError(
            f"Invalid {record.layer} span {record.begin}:{record.end} for text length "
            f"{len(canonical_text)}"
        )
    expected = canonical_text[record.begin : record.end]
    if record.covered_text != expected:
        raise InvalidAnnotationError(
            f"Covered-text mismatch in {record.layer} at {record.begin}:{record.end}: "
            f"{record.covered_text!r} != {expected!r}"
        )
    if not record.label:
        raise InvalidAnnotationError(
            f"Missing required label in {record.layer} at {record.begin}:{record.end}"
        )


def match_annotations(
    automatic: Sequence[AnnotationRecord],
    expert: Sequence[AnnotationRecord],
    *,
    relabel_iou_threshold: float = DEFAULT_RELABEL_IOU_THRESHOLD,
    exclude_human_rejection_markers: bool = True,
) -> tuple[MatchRecord, ...]:
    """Pair one layer greedily in deterministic phases and retain all orphans."""
    automatic_sorted = tuple(sorted(automatic, key=_annotation_key))
    expert_sorted = tuple(sorted(expert, key=_annotation_key))
    if automatic_sorted and expert_sorted:
        layers = {record.layer for record in (*automatic_sorted, *expert_sorted)}
        if len(layers) != 1:
            raise ValueError(f"match_annotations requires one layer, got {sorted(layers)}")

    remaining_automatic = set(range(len(automatic_sorted)))
    remaining_expert = set(range(len(expert_sorted)))
    results: list[MatchRecord] = []

    if exclude_human_rejection_markers:
        for expert_index, expert_record in enumerate(expert_sorted):
            if not is_human_rejection_marker(expert_record):
                continue
            candidates = [
                automatic_index
                for automatic_index in remaining_automatic
                if _same_span(automatic_sorted[automatic_index], expert_record)
                and automatic_sorted[automatic_index].label == expert_record.label
            ]
            automatic_index = min(
                candidates,
                key=lambda index: _annotation_key(automatic_sorted[index]),
                default=None,
            )
            automatic_record = (
                automatic_sorted[automatic_index]
                if automatic_index is not None
                else None
            )
            if automatic_index is not None:
                remaining_automatic.remove(automatic_index)
            remaining_expert.remove(expert_index)
            results.append(
                MatchRecord(
                    layer=expert_record.layer,
                    category=HUMAN_REJECTION_MARKER_EXCLUDED,
                    automatic=automatic_record,
                    expert=expert_record,
                    score=1.0 if automatic_record else None,
                    feature_differences=_feature_differences(
                        automatic_record,
                        expert_record,
                    ),
                    exclusion_reason=(
                        "Expert TRIGGER_TIME annotation has certainty=rejected and an "
                        "explicit comment identifying an observation time, matching the "
                        "documented pilot rejection convention."
                    ),
                )
            )

    phases = (
        lambda left, right: _same_span(left, right) and left.label == right.label,
        lambda left, right: _overlap(left, right) > 0 and left.label == right.label,
        lambda left, right: left.label != right.label
        and (
            _same_span(left, right)
            or _span_iou(left, right) >= relabel_iou_threshold
        ),
    )
    for predicate in phases:
        candidates = []
        for automatic_index in remaining_automatic:
            for expert_index in remaining_expert:
                left = automatic_sorted[automatic_index]
                right = expert_sorted[expert_index]
                if predicate(left, right):
                    candidates.append(
                        (
                            _match_score(left, right),
                            automatic_index,
                            expert_index,
                        )
                    )
        candidates.sort(
            key=lambda item: _candidate_key(
                item[0],
                automatic_sorted[item[1]],
                expert_sorted[item[2]],
            )
        )
        for score, automatic_index, expert_index in candidates:
            if (
                automatic_index not in remaining_automatic
                or expert_index not in remaining_expert
            ):
                continue
            left = automatic_sorted[automatic_index]
            right = expert_sorted[expert_index]
            remaining_automatic.remove(automatic_index)
            remaining_expert.remove(expert_index)
            differences = _feature_differences(left, right)
            if left.label != right.label:
                category = RELABELED
            elif not _same_span(left, right):
                category = SPAN_ADJUSTED
            elif differences:
                category = FEATURE_CHANGED
            else:
                category = EXACT_MATCH
            results.append(
                MatchRecord(
                    layer=left.layer,
                    category=category,
                    automatic=left,
                    expert=right,
                    score=score,
                    feature_differences=differences,
                )
            )

    for index in sorted(remaining_automatic, key=lambda value: _annotation_key(automatic_sorted[value])):
        record = automatic_sorted[index]
        results.append(
            MatchRecord(record.layer, AUTOMATIC_ONLY, record, None, None)
        )
    for index in sorted(remaining_expert, key=lambda value: _annotation_key(expert_sorted[value])):
        record = expert_sorted[index]
        results.append(MatchRecord(record.layer, EXPERT_ONLY, None, record, None))
    return tuple(sorted(results, key=_match_output_key))


def is_human_rejection_marker(record: AnnotationRecord) -> bool:
    """Return whether a record follows the documented pilot rejection convention."""
    if record.layer != EVENT_EVIDENCE_LAYER or record.label != "TRIGGER_TIME":
        return False
    certainty = record.normalized_features.get("certainty", "")
    comment = record.normalized_features.get("comment", "")
    return certainty == "rejected" and bool(_OBSERVATION_REJECTION_RE.search(comment))


def _feature_differences(
    automatic: AnnotationRecord | None,
    expert: AnnotationRecord,
) -> tuple[FeatureDifference, ...]:
    if automatic is None:
        return ()
    features = LAYER_BY_NAME[expert.layer].compared_features
    differences = []
    for feature in features:
        automatic_normalized = automatic.normalized_features.get(feature, "")
        expert_normalized = expert.normalized_features.get(feature, "")
        if automatic_normalized == expert_normalized:
            continue
        differences.append(
            FeatureDifference(
                feature=feature,
                automatic_raw=automatic.raw_features.get(feature),
                expert_raw=expert.raw_features.get(feature),
                automatic_normalized=automatic_normalized,
                expert_normalized=expert_normalized,
            )
        )
    return tuple(differences)


def _overlap(left: AnnotationRecord, right: AnnotationRecord) -> int:
    return max(0, min(left.end, right.end) - max(left.begin, right.begin))


def _span_iou(left: AnnotationRecord, right: AnnotationRecord) -> float:
    intersection = _overlap(left, right)
    if not intersection:
        return 0.0
    union = max(left.end, right.end) - min(left.begin, right.begin)
    return intersection / union


def _boundary_similarity(left: AnnotationRecord, right: AnnotationRecord) -> float:
    scale = max(left.end - left.begin, right.end - right.begin, 1)
    distance = abs(left.begin - right.begin) + abs(left.end - right.end)
    return max(0.0, 1.0 - distance / (2.0 * scale))


def _match_score(left: AnnotationRecord, right: AnnotationRecord) -> float:
    text_similarity = SequenceMatcher(
        None,
        normalize_feature_value(left.covered_text),
        normalize_feature_value(right.covered_text),
        autojunk=False,
    ).ratio()
    return (
        0.60 * _span_iou(left, right)
        + 0.25 * text_similarity
        + 0.15 * _boundary_similarity(left, right)
    )


def _same_span(left: AnnotationRecord, right: AnnotationRecord) -> bool:
    return left.begin == right.begin and left.end == right.end


def _annotation_key(record: AnnotationRecord) -> tuple[Any, ...]:
    return (
        record.begin,
        record.end,
        record.label,
        record.original_index,
    )


def _candidate_key(
    score: float,
    automatic: AnnotationRecord,
    expert: AnnotationRecord,
) -> tuple[Any, ...]:
    return (
        -score,
        automatic.begin,
        automatic.end,
        expert.begin,
        expert.end,
        automatic.label,
        expert.label,
        automatic.original_index,
        expert.original_index,
    )


_CATEGORY_ORDER = {
    HUMAN_REJECTION_MARKER_EXCLUDED: 0,
    EXACT_MATCH: 1,
    FEATURE_CHANGED: 2,
    SPAN_ADJUSTED: 3,
    RELABELED: 4,
    AUTOMATIC_ONLY: 5,
    EXPERT_ONLY: 6,
}


def _match_output_key(match: MatchRecord) -> tuple[Any, ...]:
    automatic = match.automatic
    expert = match.expert
    starts = [record.begin for record in (automatic, expert) if record is not None]
    ends = [record.end for record in (automatic, expert) if record is not None]
    return (
        0 if match.layer == EVENT_EVIDENCE_LAYER else 1,
        min(starts, default=-1),
        min(ends, default=-1),
        _CATEGORY_ORDER[match.category],
        automatic.label if automatic else "",
        expert.label if expert else "",
        automatic.original_index if automatic else -1,
        expert.original_index if expert else -1,
    )


def calculate_metrics(matches: Sequence[MatchRecord]) -> dict[str, Any]:
    """Calculate all required metric families independently for each layer."""
    output: dict[str, Any] = {}
    for definition in LAYER_DEFINITIONS:
        layer_matches = [match for match in matches if match.layer == definition.name]
        included = [
            match
            for match in layer_matches
            if match.category != HUMAN_REJECTION_MARKER_EXCLUDED
        ]
        paired = [
            match
            for match in included
            if match.automatic is not None and match.expert is not None
        ]
        automatic_total = sum(match.automatic is not None for match in included)
        expert_total = sum(match.expert is not None for match in included)
        exact_span = sum(
            _same_span(match.automatic, match.expert)  # type: ignore[arg-type]
            for match in paired
        )
        overlap_span = len(paired)
        same_label = sum(
            match.automatic.label == match.expert.label  # type: ignore[union-attr]
            for match in paired
        )
        exact_annotation = sum(
            _same_span(match.automatic, match.expert)  # type: ignore[arg-type]
            and match.automatic.label == match.expert.label  # type: ignore[union-attr]
            and not match.feature_differences
            for match in paired
        )
        relaxed_annotation = sum(
            match.automatic.label == match.expert.label  # type: ignore[union-attr]
            for match in paired
        )
        feature_exact = sum(not match.feature_differences for match in paired)

        per_feature = {}
        for feature in definition.compared_features:
            equal = 0
            missing_automatic = 0
            missing_expert = 0
            for match in paired:
                left = match.automatic.normalized_features.get(feature, "")  # type: ignore[union-attr]
                right = match.expert.normalized_features.get(feature, "")  # type: ignore[union-attr]
                equal += left == right
                missing_automatic += not left and bool(right)
                missing_expert += bool(left) and not right
            per_feature[feature] = {
                "n": len(paired),
                "equal": equal,
                "accuracy": _ratio(equal, len(paired)),
                "missing_automatic": missing_automatic,
                "missing_expert": missing_expert,
            }

        category_counts = Counter(match.category for match in layer_matches)
        output[definition.name] = {
            "automatic_total": automatic_total,
            "expert_total": expert_total,
            "paired_total": len(paired),
            "excluded_rejection_markers": category_counts[
                HUMAN_REJECTION_MARKER_EXCLUDED
            ],
            "category_counts": {
                category: category_counts.get(category, 0)
                for category in _CATEGORY_ORDER
            },
            "exact_span": _prf(exact_span, automatic_total, expert_total),
            "overlap_span": _prf(overlap_span, automatic_total, expert_total),
            "label_accuracy_on_matched": _ratio(same_label, len(paired)),
            "relabeled_count": category_counts[RELABELED],
            "full_feature_agreement_on_matched": _ratio(feature_exact, len(paired)),
            "annotations_with_feature_change": sum(
                bool(match.feature_differences) for match in paired
            ),
            "per_feature": per_feature,
            "exact_end_to_end": _prf(
                exact_annotation,
                automatic_total,
                expert_total,
            ),
            "relaxed_same_label": _prf(
                relaxed_annotation,
                automatic_total,
                expert_total,
            ),
        }
    return output


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _prf(true_positive: int, automatic_total: int, expert_total: int) -> dict[str, Any]:
    precision = _ratio(true_positive, automatic_total)
    recall = _ratio(true_positive, expert_total)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {
        "true_positive": true_positive,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def write_comparison_outputs(result: ComparisonResult, output_dir: str | Path) -> None:
    """Write deterministic JSON, CSV, Markdown, and input hash outputs."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics_payload = {
        "schema_version": "1.0",
        "inputs": _input_payload(result),
        "matching": {
            "phases": [
                "exact span and same label",
                "overlapping span and same label",
                "exact or strong overlap and different label",
            ],
            "score_formula": MATCH_SCORE_FORMULA,
            "relabel_iou_threshold": result.relabel_iou_threshold,
            "tie_break": (
                "automatic begin/end, expert begin/end, labels, original indexes"
            ),
            "one_to_one": True,
            "allowed_missing_expert_labels": result.allowed_missing_expert_labels,
        },
        "normalization": _normalization_rules(),
        "primary_policy": "documented human rejection markers excluded",
        "layers": result.metrics,
        "including_human_rejection_markers": result.metrics_including_rejections,
    }
    (output / "metrics.json").write_text(
        json.dumps(metrics_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_annotation_diff(output / "annotation_diff.csv", result.matches)
    _write_feature_metrics(output / "feature_metrics.csv", result.metrics)
    _write_label_confusion(output / "label_confusion.csv", result.matches)
    (output / "evaluation_report.md").write_text(
        _build_markdown_report(result),
        encoding="utf-8",
    )
    manifest_lines = [
        f"{result.automatic.file_sha256}  {result.automatic.path}",
        f"{result.expert.file_sha256}  {result.expert.path}",
        f"{result.typesystem_sha256}  {result.typesystem_path}",
    ]
    (output / "input_manifest.sha256").write_text(
        "\n".join(manifest_lines) + "\n",
        encoding="utf-8",
    )


def _input_payload(result: ComparisonResult) -> dict[str, Any]:
    def document_payload(document: LoadedXmi) -> dict[str, Any]:
        return {
            "path": str(document.path),
            "file_sha256": document.file_sha256,
            "text_length": len(document.text),
            "text_sha256": document.text_sha256,
            "annotation_counts": {
                layer: len(records) for layer, records in document.annotations.items()
            },
            "missing_label_annotations": list(document.missing_label_annotations),
        }

    return {
        "automatic": document_payload(result.automatic),
        "expert": document_payload(result.expert),
        "typesystem": {
            "path": str(result.typesystem_path),
            "sha256": result.typesystem_sha256,
            "in_memory_compatibility_augmentations": list(
                result.typesystem_augmentations
            ),
        },
        "canonical_text_equal": True,
    }


def _normalization_rules() -> list[str]:
    return [
        "None, missing values, and empty strings normalize to an empty string.",
        "Leading, trailing, and repeated internal whitespace is collapsed.",
        "Booleans normalize to lowercase true/false.",
        "Pure numeric strings normalize through Decimal without changing magnitude.",
        "ISO-8601 timestamps normalize Z to an explicit UTC offset.",
        "Sequences preserve order; mappings sort keys before deterministic JSON serialization.",
        "Ordinary strings and scientific unit strings remain case-sensitive.",
    ]


def _write_annotation_diff(path: Path, matches: Sequence[MatchRecord]) -> None:
    fieldnames = [
        "layer",
        "category",
        "automatic_index",
        "expert_index",
        "automatic_span",
        "expert_span",
        "automatic_label",
        "expert_label",
        "automatic_text",
        "expert_text",
        "score",
        "raw_feature_differences",
        "normalized_feature_differences",
        "exclusion_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for match in matches:
            raw_differences = {
                difference.feature: {
                    "automatic": difference.automatic_raw,
                    "expert": difference.expert_raw,
                }
                for difference in match.feature_differences
            }
            normalized_differences = {
                difference.feature: {
                    "automatic": difference.automatic_normalized,
                    "expert": difference.expert_normalized,
                }
                for difference in match.feature_differences
            }
            writer.writerow(
                {
                    "layer": match.layer,
                    "category": match.category,
                    "automatic_index": _record_attr(match.automatic, "original_index"),
                    "expert_index": _record_attr(match.expert, "original_index"),
                    "automatic_span": _span_text(match.automatic),
                    "expert_span": _span_text(match.expert),
                    "automatic_label": _record_attr(match.automatic, "label"),
                    "expert_label": _record_attr(match.expert, "label"),
                    "automatic_text": _excerpt(match.automatic),
                    "expert_text": _excerpt(match.expert),
                    "score": "" if match.score is None else f"{match.score:.8f}",
                    "raw_feature_differences": json.dumps(
                        raw_differences,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "normalized_feature_differences": json.dumps(
                        normalized_differences,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "exclusion_reason": match.exclusion_reason or "",
                }
            )


def _write_feature_metrics(path: Path, metrics: Mapping[str, Any]) -> None:
    fieldnames = [
        "layer",
        "feature",
        "matched_pairs",
        "equal",
        "accuracy",
        "missing_automatic",
        "missing_expert",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for layer in (EVENT_EVIDENCE_LAYER, PHOTOMETRY_LAYER):
            for feature, values in metrics[layer]["per_feature"].items():
                writer.writerow(
                    {
                        "layer": layer,
                        "feature": feature,
                        "matched_pairs": values["n"],
                        "equal": values["equal"],
                        "accuracy": _csv_float(values["accuracy"]),
                        "missing_automatic": values["missing_automatic"],
                        "missing_expert": values["missing_expert"],
                    }
                )


def _write_label_confusion(path: Path, matches: Sequence[MatchRecord]) -> None:
    counts = Counter(
        (match.layer, match.automatic.label, match.expert.label)
        for match in matches
        if match.category != HUMAN_REJECTION_MARKER_EXCLUDED
        and match.automatic is not None
        and match.expert is not None
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["layer", "automatic_label", "expert_label", "count"])
        for (layer, automatic_label, expert_label), count in sorted(counts.items()):
            writer.writerow([layer, automatic_label, expert_label, count])


def _build_markdown_report(result: ComparisonResult) -> str:
    lines = [
        "# Reproducible XMI comparison: 2026owq",
        "",
        "## 1. Inputs",
        "",
        "| Role | Path | File SHA-256 | Text length | Text SHA-256 | Evidence | Photometry |",
        "|---|---|---|---:|---|---:|---:|",
    ]
    for role, document in (("automatic", result.automatic), ("expert", result.expert)):
        lines.append(
            f"| {role} | `{document.path}` | `{document.file_sha256}` | "
            f"{len(document.text)} | `{document.text_sha256}` | "
            f"{len(document.annotations[EVENT_EVIDENCE_LAYER])} | "
            f"{len(document.annotations[PHOTOMETRY_LAYER])} |"
        )
    lines += [
        "",
        f"TypeSystem: `{result.typesystem_path}` (`{result.typesystem_sha256}`).",
        "",
        "The canonical texts are byte-identical after UTF-8 decoding. The preserved "
        "automatic XMI has 193 evidence annotations and 76 photometric annotations; "
        "there is no surviving automatic XMI with the historical current-rule count "
        "193/68.",
        "",
        "TypeSystem compatibility augmentation applied in memory: "
        + (
            ", ".join(f"`{value}`" for value in result.typesystem_augmentations)
            if result.typesystem_augmentations
            else "none"
        )
        + ". It affects EVENT_SUMMARY metadata only, not either evaluated layer.",
        "",
        "Missing expert labels accepted explicitly: "
        + (
            ", ".join(f"`{value}`" for value in result.expert.missing_label_annotations)
            if result.expert.missing_label_annotations
            else "none"
        )
        + ". Strict mode rejects these annotations; this run preserves them as the "
        "visible sentinel `<unset>` because the historical report documents the same "
        "two evidence relabellings and one expert-only photometric annotation.",
        "",
        "## 2. Matching Definitions",
        "",
        "Matching is one-to-one and layer-local. Phases are exact span/same label, "
        "overlap/same label, then exact or strong overlap/different label. Candidate "
        f"score: `{MATCH_SCORE_FORMULA}`. The relabel IoU threshold is "
        f"{result.relabel_iou_threshold:.2f}. Ties use automatic span, expert span, "
        "labels, then original indexes.",
        "",
        "Categories: EXACT_MATCH, FEATURE_CHANGED, SPAN_ADJUSTED, RELABELED, "
        "AUTOMATIC_ONLY, EXPERT_ONLY, and HUMAN_REJECTION_MARKER_EXCLUDED.",
        "",
        "## 3. Feature Normalization",
        "",
    ]
    lines.extend(f"- {rule}" for rule in _normalization_rules())
    lines += [
        "",
        "## 4. Human Rejection Markers",
        "",
        "The primary metrics exclude only expert TRIGGER_TIME annotations carrying "
        "certainty `rejected` and an explicit comment identifying an observation time. "
        "This is the convention documented in the preserved historical report. Both "
        "the marker and its exact automatic counterpart are removed from primary "
        "denominators. Metrics including them are retained in metrics.json.",
        "",
    ]
    excluded = [
        match
        for match in result.matches
        if match.category == HUMAN_REJECTION_MARKER_EXCLUDED
    ]
    for match in excluded:
        expert = match.expert
        lines.append(
            f"- {match.layer} {expert.begin}:{expert.end} `{expert.label}` "
            f"“{_excerpt(expert)}” - {match.exclusion_reason}"
        )

    lines += [
        "",
        "The primary policy and the inclusive diagnostic are both reported below. "
        "The inclusive values retain the five documented human rejection markers "
        "and their automatic counterparts.",
        "",
        "| Layer | Policy | Automatic | Expert | Relaxed precision | Relaxed recall | Exact automatic agreement |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for layer in (EVENT_EVIDENCE_LAYER, PHOTOMETRY_LAYER):
        for policy, metrics in (
            ("primary (markers excluded)", result.metrics[layer]),
            ("inclusive", result.metrics_including_rejections[layer]),
        ):
            lines.append(
                f"| {layer} | {policy} | {metrics['automatic_total']} | "
                f"{metrics['expert_total']} | "
                f"{_pct(metrics['relaxed_same_label']['precision'])} | "
                f"{_pct(metrics['relaxed_same_label']['recall'])} | "
                f"{_pct(metrics['exact_end_to_end']['precision'])} |"
            )

    lines += ["", "## 5. Span, Label, and End-to-End Metrics", ""]
    for layer in (EVENT_EVIDENCE_LAYER, PHOTOMETRY_LAYER):
        metric = result.metrics[layer]
        lines += [
            f"### {layer}",
            "",
            "| Metric | Precision | Recall | F1 | TP |",
            "|---|---:|---:|---:|---:|",
        ]
        for label, key in (
            ("Exact span", "exact_span"),
            ("Overlap span", "overlap_span"),
            ("Exact end-to-end", "exact_end_to_end"),
            ("Relaxed overlap + same label", "relaxed_same_label"),
        ):
            values = metric[key]
            lines.append(
                f"| {label} | {_pct(values['precision'])} | {_pct(values['recall'])} | "
                f"{_pct(values['f1'])} | {values['true_positive']} |"
            )
        lines += [
            "",
            f"Automatic={metric['automatic_total']}; expert={metric['expert_total']}; "
            f"paired={metric['paired_total']}; relabelled={metric['relabeled_count']}; "
            f"label accuracy on matched spans={_pct(metric['label_accuracy_on_matched'])}; "
            f"full-feature agreement on matched spans="
            f"{_pct(metric['full_feature_agreement_on_matched'])}.",
            "",
        ]

    lines += [
        "## 6. Feature Metrics",
        "",
        "Complete per-feature results are in `feature_metrics.csv`. Photometric span "
        "performance is not complete annotation correctness.",
        "",
        "| Photometric feature | Accuracy |",
        "|---|---:|",
    ]
    photometry_features = result.metrics[PHOTOMETRY_LAYER]["per_feature"]
    for feature in (
        "instrument",
        "photometric_band",
        "obs_time_type",
        "obs_time_reference",
        "magnitude_or_limit",
        "magnitude_error",
        "measurement_type",
    ):
        if feature == "measurement_type":
            accuracy = result.metrics[PHOTOMETRY_LAYER]["label_accuracy_on_matched"]
        else:
            accuracy = photometry_features[feature]["accuracy"]
        lines.append(f"| {feature} | {_pct(accuracy)} |")

    historical = {
        EVENT_EVIDENCE_LAYER: {
            "precision": 0.9896,
            "recall": 0.9845,
            "exact": 0.6736,
        },
        PHOTOMETRY_LAYER: {
            "precision": 1.0,
            "recall": 0.9855,
            "exact": 0.0,
        },
    }
    lines += [
        "",
        "## 7. Comparison With Historical Metrics",
        "",
        "Historical values came from a missing script that re-ran corrected rules on "
        "the 28-circular text. The reproducible comparison below instead uses the "
        "surviving automatic XMI (193/76). Differences must not be tuned away.",
        "",
        "| Layer | Measure | Historical | Reproducible | Absolute difference |",
        "|---|---|---:|---:|---:|",
    ]
    for layer in (EVENT_EVIDENCE_LAYER, PHOTOMETRY_LAYER):
        current = result.metrics[layer]
        for measure, historical_value, current_value in (
            (
                "relaxed precision",
                historical[layer]["precision"],
                current["relaxed_same_label"]["precision"],
            ),
            (
                "relaxed recall",
                historical[layer]["recall"],
                current["relaxed_same_label"]["recall"],
            ),
            (
                "exact automatic agreement",
                historical[layer]["exact"],
                current["exact_end_to_end"]["precision"],
            ),
        ):
            difference = (
                current_value - historical_value if current_value is not None else None
            )
            lines.append(
                f"| {layer} | {measure} | {_pct(historical_value)} | "
                f"{_pct(current_value)} | {_signed_pp(difference)} |"
            )

    lines += [
        "",
        "Strict historical reconstruction did not succeed because the automatic "
        "193/68 current-rule annotation set was never exported as a surviving XMI. "
        "The different input annotation set is the principal discrepancy; the new "
        "matching formula, overlap threshold, normalization, and rejection policy are "
        "also now explicit instead of inferred.",
        "",
        "## 8. Known Limitations",
        "",
        "- One event was reviewed; results do not generalize to the ten documents.",
        "- The same pilot informed rule corrections, so this is not an independent test.",
        "- There is no inter-annotator agreement measurement.",
        "- The expert XMI contains a metadata feature absent from the surviving "
        "TypeSystem; the controlled in-memory augmentation is documented above.",
        "- Feature normalization is conservative and keeps case-sensitive scientific "
        "strings distinct.",
        "",
        "## 9. Interpretation Allowed in the PRe",
        "",
        "The pilot supports a qualified statement about span recovery and reveals "
        "substantial feature correction work. Photometric span precision must never be "
        "presented as complete photometric correctness. The historical metrics are not "
        "strictly reproducible; these new results are reproducible for the preserved "
        "193/76 baseline XMI and must be reported with the single-pilot, non-independent "
        "evaluation limitation.",
    ]
    return "\n".join(lines) + "\n"


def _first_divergence(left: str, right: str) -> int | None:
    for index, (left_char, right_char) in enumerate(zip(left, right)):
        if left_char != right_char:
            return index
    return min(len(left), len(right)) if len(left) != len(right) else None


def _record_attr(record: AnnotationRecord | None, attribute: str) -> Any:
    return "" if record is None else getattr(record, attribute)


def _span_text(record: AnnotationRecord | None) -> str:
    return "" if record is None else f"{record.begin}:{record.end}"


def _excerpt(record: AnnotationRecord | None, limit: int = 160) -> str:
    if record is None:
        return ""
    text = _WS_RE.sub(" ", record.covered_text.strip())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _csv_float(value: float | None) -> str:
    return "" if value is None else f"{value:.8f}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:.2f}%"


def _signed_pp(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:+.2f} pp"


__all__ = [
    "AnnotationRecord",
    "AUTOMATIC_ONLY",
    "CanonicalTextMismatchError",
    "ComparisonError",
    "ComparisonResult",
    "EXACT_MATCH",
    "EXPERT_ONLY",
    "FEATURE_CHANGED",
    "HUMAN_REJECTION_MARKER_EXCLUDED",
    "InvalidAnnotationError",
    "MatchRecord",
    "MissingLayerError",
    "PHOTOMETRY_LAYER",
    "RELABELED",
    "SPAN_ADJUSTED",
    "TypeSystemCompatibilityError",
    "calculate_metrics",
    "compare_xmi",
    "is_human_rejection_marker",
    "match_annotations",
    "normalize_feature_value",
    "validate_annotation_record",
    "write_comparison_outputs",
]
