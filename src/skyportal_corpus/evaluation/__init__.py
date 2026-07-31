"""Reproducible evaluation utilities for expert-reviewed corpus annotations."""

from skyportal_corpus.evaluation.xmi_comparison import (
    AnnotationRecord,
    CanonicalTextMismatchError,
    ComparisonError,
    ComparisonResult,
    InvalidAnnotationError,
    MissingLayerError,
    compare_xmi,
    match_annotations,
    normalize_feature_value,
    write_comparison_outputs,
)

__all__ = [
    "AnnotationRecord",
    "CanonicalTextMismatchError",
    "ComparisonError",
    "ComparisonResult",
    "InvalidAnnotationError",
    "MissingLayerError",
    "compare_xmi",
    "match_annotations",
    "normalize_feature_value",
    "write_comparison_outputs",
]
