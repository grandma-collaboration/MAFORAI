#!/usr/bin/env python
"""Compare automatic and expert INCEpTION XMI with deterministic metrics."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from skyportal_corpus.evaluation.xmi_comparison import (  # noqa: E402
    ComparisonError,
    EVENT_EVIDENCE_LAYER,
    PHOTOMETRY_LAYER,
    compare_xmi,
    write_comparison_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser without side effects."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare two INCEpTION XMI files after validating their canonical text, "
            "layers, labels, and spans."
        )
    )
    parser.add_argument("--automatic-xmi", required=True, type=Path)
    parser.add_argument("--expert-xmi", required=True, type=Path)
    parser.add_argument("--typesystem", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--relabel-iou-threshold",
        type=float,
        default=0.50,
        help="Minimum span IoU for pairing different labels (default: 0.50).",
    )
    parser.add_argument(
        "--allow-missing-expert-labels",
        action="store_true",
        help=(
            "Preserve missing expert labels as the explicit <unset> sentinel. "
            "Without this flag, missing labels are fatal."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run comparison and print compact, actionable metrics."""
    args = build_parser().parse_args(argv)
    try:
        result = compare_xmi(
            args.automatic_xmi,
            args.expert_xmi,
            args.typesystem,
            relabel_iou_threshold=args.relabel_iou_threshold,
            allow_missing_expert_labels=args.allow_missing_expert_labels,
        )
        write_comparison_outputs(result, args.output_dir)
    except (ComparisonError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"automatic_text_sha256: {result.automatic.text_sha256}")
    print(f"expert_text_sha256: {result.expert.text_sha256}")
    print("canonical_text_equal: True")
    for layer in (EVENT_EVIDENCE_LAYER, PHOTOMETRY_LAYER):
        metrics = result.metrics[layer]
        relaxed = metrics["relaxed_same_label"]
        exact = metrics["exact_end_to_end"]
        print(
            f"{layer}: automatic={metrics['automatic_total']} "
            f"expert={metrics['expert_total']} "
            f"relaxed_precision={relaxed['precision']:.6f} "
            f"relaxed_recall={relaxed['recall']:.6f} "
            f"exact_precision={exact['precision']:.6f}"
        )
    print(f"output_dir: {args.output_dir}")
    print("FINAL: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
