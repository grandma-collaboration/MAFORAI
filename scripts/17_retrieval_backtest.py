#!/usr/bin/env python
"""Leave-one-out retrieval backtest over the three STATE snapshot windows."""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skyportal_corpus.retrieval.embed import WINDOWS, StateIndex, load_index  # noqa: E402
from skyportal_corpus.retrieval.retrieve import retrieve_from_index  # noqa: E402
from skyportal_corpus.state.state import (  # noqa: E402
    DESCRIPTIVE_FACT_TYPES,
    _redshift_at_T,
    load_ledger,
)

AUDIT_PATH = ROOT / "data/interim/audit/RETR01_backtest.md"
K = 5
RANDOM_SEEDS = (17, 29, 43, 71, 101)


@dataclass(frozen=True)
class Outcome:
    """Observable full-trajectory outcomes used by the backtest."""

    final_classification: str | None
    redshift: float | None
    detection_span_hours: float | None


def event_outcome(event_id: str, ledger) -> Outcome:
    """Derive one event's outcomes from its complete attached fact history."""
    facts = ledger.facts_for(event_id)
    classifications = facts[
        facts["subtype_label"].eq("CLASSIFICATION_INTERPRETATION")
        & facts["value_raw"].notna()
    ].sort_values(["t_known", "fact_id"])
    final_classification = (
        str(classifications.iloc[-1]["value_raw"])
        if not classifications.empty
        else None
    )

    descriptive = facts[facts["fact_type"].isin(DESCRIPTIVE_FACT_TYPES)]
    _, redshift = _redshift_at_T(descriptive)

    detection_times = pd.to_numeric(
        facts.loc[facts["subtype_label"].eq("detection"), "dt_occurred_hours"],
        errors="coerce",
    ).dropna()
    detection_span = (
        float(detection_times.max()) if not detection_times.empty else None
    )
    return Outcome(final_classification, redshift, detection_span)


def retrieved_pairs(state_index: StateIndex) -> list[tuple[str, str]]:
    """Return every leave-one-out query-neighbour pair for one window."""
    pairs: list[tuple[str, str]] = []
    for event_id in sorted(state_index.metadata["event_id"].astype(str)):
        neighbours = retrieve_from_index(event_id, state_index, K)
        pairs.extend((event_id, neighbour) for neighbour in neighbours["event_id"])
    return pairs


def random_pairs(
    state_index: StateIndex,
    seed: int,
) -> list[tuple[str, str]]:
    """Draw a same-class random control with the same per-query k."""
    rng = np.random.default_rng(seed)
    metadata = state_index.metadata
    pairs: list[tuple[str, str]] = []
    for event_id in sorted(metadata["event_id"].astype(str)):
        query = metadata.loc[metadata["event_id"].eq(event_id)].iloc[0]
        candidates = metadata.loc[
            metadata["messenger_class"].eq(query["messenger_class"])
            & metadata["event_id"].ne(event_id),
            "event_id",
        ].astype(str).sort_values().to_numpy()
        n = min(K, len(candidates))
        if n:
            selected = candidates[rng.choice(len(candidates), size=n, replace=False)]
            pairs.extend((event_id, neighbour) for neighbour in selected)
    return pairs


def classification_agreement(
    pairs: list[tuple[str, str]],
    outcomes: dict[str, Outcome],
) -> tuple[float, int]:
    """Mean per-query share of neighbours with the query's final class."""
    by_query: dict[str, list[str]] = {}
    for query, neighbour in pairs:
        by_query.setdefault(query, []).append(neighbour)
    shares = []
    for query, neighbours in by_query.items():
        query_class = outcomes[query].final_classification
        if query_class is None:
            continue
        shares.append(
            sum(
                outcomes[neighbour].final_classification == query_class
                for neighbour in neighbours
            )
            / len(neighbours)
        )
    return (float(np.mean(shares)) if shares else math.nan, len(shares))


def pair_differences(
    pairs: list[tuple[str, str]],
    outcomes: dict[str, Outcome],
    field: str,
) -> list[float]:
    """Absolute outcome differences for pairs where both values exist."""
    differences = []
    for query, neighbour in pairs:
        left = getattr(outcomes[query], field)
        right = getattr(outcomes[neighbour], field)
        if left is not None and right is not None:
            differences.append(abs(float(left) - float(right)))
    return differences


def distribution(values: list[float]) -> dict[str, float]:
    """Compact distribution used in the report tables."""
    if not values:
        return {"n": 0, "mean": math.nan, "median": math.nan, "p90": math.nan}
    array = np.asarray(values, dtype=float)
    return {
        "n": float(len(array)),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "p90": float(np.quantile(array, 0.90)),
    }


def average_distributions(items: list[dict[str, float]]) -> dict[str, float]:
    """Average random-control statistics over independent fixed seeds."""
    return {
        key: float(np.nanmean([item[key] for item in items]))
        for key in ("n", "mean", "median", "p90")
    }


def fmt(value: float, digits: int = 3) -> str:
    """Format finite metrics and preserve missing denominators visibly."""
    return "NA" if not math.isfinite(value) else f"{value:.{digits}f}"


def evaluate_window(
    state_index: StateIndex,
    outcomes: dict[str, Outcome],
) -> dict:
    """Evaluate dense retrieval and same-class random controls for one window."""
    dense_pairs = retrieved_pairs(state_index)
    random_by_seed = {
        seed: random_pairs(state_index, seed) for seed in RANDOM_SEEDS
    }

    metadata_class = state_index.metadata.set_index("event_id")["messenger_class"]
    self_hits = sum(query == neighbour for query, neighbour in dense_pairs)
    hard_filter_hits = sum(
        metadata_class[query] == metadata_class[neighbour]
        for query, neighbour in dense_pairs
    )
    hard_filter_rate = hard_filter_hits / len(dense_pairs) if dense_pairs else math.nan
    if self_hits:
        raise AssertionError(f"{state_index.window}: retrieval returned {self_hits} self hits")
    if hard_filter_rate != 1.0:
        raise AssertionError(
            f"{state_index.window}: messenger hard-filter agreement is {hard_filter_rate}"
        )

    class_dense, class_queries = classification_agreement(dense_pairs, outcomes)
    class_random_values = [
        classification_agreement(pairs, outcomes)[0]
        for pairs in random_by_seed.values()
    ]
    class_random = float(np.nanmean(class_random_values))

    dense_redshift = distribution(
        pair_differences(dense_pairs, outcomes, "redshift")
    )
    random_redshift = average_distributions(
        [
            distribution(pair_differences(pairs, outcomes, "redshift"))
            for pairs in random_by_seed.values()
        ]
    )
    dense_detection = distribution(
        pair_differences(dense_pairs, outcomes, "detection_span_hours")
    )
    random_detection = average_distributions(
        [
            distribution(
                pair_differences(pairs, outcomes, "detection_span_hours")
            )
            for pairs in random_by_seed.values()
        ]
    )
    return {
        "n_events": len(state_index.metadata),
        "n_pairs": len(dense_pairs),
        "hard_filter_rate": hard_filter_rate,
        "self_hits": self_hits,
        "classification_dense": class_dense,
        "classification_random": class_random,
        "classification_queries": class_queries,
        "redshift_dense": dense_redshift,
        "redshift_random": random_redshift,
        "detection_dense": dense_detection,
        "detection_random": random_detection,
    }


def improvement(dense: float, random: float) -> float:
    """Percent reduction in error; positive means retrieval beats random."""
    if not math.isfinite(dense) or not math.isfinite(random) or random == 0:
        return math.nan
    return 100.0 * (random - dense) / random


def build_audit(
    indexes: dict[str, StateIndex],
    results: dict[str, dict],
    neighbours_2026owq: pd.DataFrame,
) -> list[str]:
    """Build the bounded Markdown audit report."""
    lines = [
        "# RETR01 - state retrieval backtest",
        "",
        "## 1. INDEX",
        "",
        "| window | vectors | dimension | dtype | embed seconds | deterministic re-embed |",
        "|---|---:|---:|---|---:|---|",
    ]
    for window in WINDOWS:
        index = indexes[window]
        metadata = index.build_metadata
        deterministic_status = (
            metadata.get("deterministic_reembed_6h", "UNKNOWN")
            if window == "6h"
            else "not rerun"
        )
        lines.append(
            f"| {window} | {len(index.metadata)} | {index.vectors.shape[1]} | "
            f"{index.vectors.dtype} | {float(metadata['embedding_seconds']):.3f} | "
            f"{deterministic_status} |"
        )

    lines += [
        "",
        "## 2. RETRIEVAL",
        "",
        "1. Retrieval is within one fixed window; windows are never mixed.",
        "2. Candidates are hard-filtered on exact `messenger_class` before scoring.",
        "3. The query event is removed before scoring.",
        "4. Dense score is cosine similarity of normalized BGE-M3 vectors in memory.",
        "5. Results sort by descending score, then `event_id` for deterministic ties.",
        "",
        "## 3. BACKTEST RESULTS",
        "",
        f"`k={K}`; random same-class controls averaged over seeds "
        f"`{', '.join(map(str, RANDOM_SEEDS))}`.",
        "",
        "### Final Classification Agreement",
        "",
        "| window | queries with final class | retrieved | random | pairs | hard filter |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for window in WINDOWS:
        result = results[window]
        lines.append(
            f"| {window} | {result['classification_queries']} | "
            f"{fmt(100 * result['classification_dense'], 2)}% | "
            f"{fmt(100 * result['classification_random'], 2)}% | "
            f"{result['n_pairs']} | {fmt(100 * result['hard_filter_rate'], 2)}% |"
        )

    lines += [
        "",
        "The final class is the latest non-null `CLASSIFICATION_INTERPRETATION` value "
        "over the full trajectory. A neighbour without that class counts as no agreement.",
        "",
        "### Redshift Proximity: Absolute Delta-z",
        "",
        "| window | retrieved n | retrieved mean | retrieved median | retrieved p90 | "
        "random n/seed | random mean | random median | random p90 | median gain |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for window in WINDOWS:
        dense = results[window]["redshift_dense"]
        random = results[window]["redshift_random"]
        lines.append(
            f"| {window} | {int(dense['n'])} | {fmt(dense['mean'])} | "
            f"{fmt(dense['median'])} | {fmt(dense['p90'])} | "
            f"{fmt(random['n'], 1)} | {fmt(random['mean'])} | "
            f"{fmt(random['median'])} | {fmt(random['p90'])} | "
            f"{fmt(improvement(dense['median'], random['median']), 1)}% |"
        )

    lines += [
        "",
        "### Detection-Timescale Proximity: Absolute Delta-hours",
        "",
        "| window | retrieved n | retrieved mean | retrieved median | retrieved p90 | "
        "random n/seed | random mean | random median | random p90 | median gain |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for window in WINDOWS:
        dense = results[window]["detection_dense"]
        random = results[window]["detection_random"]
        lines.append(
            f"| {window} | {int(dense['n'])} | {fmt(dense['mean'], 1)} | "
            f"{fmt(dense['median'], 1)} | {fmt(dense['p90'], 1)} | "
            f"{fmt(random['n'], 1)} | {fmt(random['mean'], 1)} | "
            f"{fmt(random['median'], 1)} | {fmt(random['p90'], 1)} | "
            f"{fmt(improvement(dense['median'], random['median']), 1)}% |"
        )

    redshift_gains = {
        window: improvement(
            results[window]["redshift_dense"]["median"],
            results[window]["redshift_random"]["median"],
        )
        for window in WINDOWS
    }
    detection_gains = {
        window: improvement(
            results[window]["detection_dense"]["median"],
            results[window]["detection_random"]["median"],
        )
        for window in WINDOWS
    }
    best_redshift = max(
        redshift_gains,
        key=lambda key: (
            redshift_gains[key]
            if math.isfinite(redshift_gains[key])
            else -math.inf
        ),
    )
    lines += [
        "",
        "## 4. HEADLINE",
        "",
        f"On median redshift error, the strongest window is **{best_redshift}** "
        f"with a {fmt(redshift_gains[best_redshift], 1)}% reduction versus random. "
        f"Median detection-timescale gains are "
        f"{', '.join(f'{w} {fmt(detection_gains[w], 1)}%' for w in WINDOWS)}. "
        "The result is not consistently predictive: only 6h redshift improves slightly, "
        "while redshift at later windows and detection timescale at every window are "
        "worse than random. Positive gains mean lower error than random.",
        "",
        "## 5. C4 - 2026owq at 24h",
        "",
    ]
    if neighbours_2026owq.empty:
        lines.append("`2026owq` is absent or has no same-class neighbours in the 24h index.")
    else:
        for row in neighbours_2026owq.itertuples(index=False):
            lines.append(
                f"{row.rank}. `{row.event_id}` score={row.score:.6f}: {row.matching_text}"
            )

    classes_6h = indexes["6h"].metadata["messenger_class"].value_counts().to_dict()
    lines += [
        "",
        "## 6. LIMITS",
        "",
        f"- Cohort size is only {len(indexes['6h'].metadata)}/"
        f"{len(indexes['24h'].metadata)}/{len(indexes['7d'].metadata)} events at "
        "6h/24h/7d.",
        f"- The 6h messenger distribution is `{classes_6h}`; the hard filter therefore "
        "has little discriminatory effect in this cohort even though it prevents "
        "cross-messenger contamination.",
        "- Outcome comparisons omit redshift or detection-span pairs when either event "
        "lacks that outcome; the reported `n` values expose those denominators.",
        "- Redshift can already be present in `matching_text` at T, so its metric tests "
        "physical similarity as well as future prediction; it is not a pure "
        "unknown-redshift forecasting score.",
        "- Early states can be thin, and repeated events across windows make per-window "
        "results correlated rather than independent experiments.",
        "",
        "## 7. JUDGMENT CALLS AND DISCREPANCIES",
        "",
        "- BGE-M3 is loaded from the local cache with `HF_HUB_OFFLINE=1`, "
        "`TRANSFORMERS_OFFLINE=1`, CPU float32, and no query instruction because this "
        "is symmetric event-to-event similarity.",
        "- Final classification uses the latest extracted physical interpretation, not "
        "SkyPortal operational classifications.",
        "- Eventual redshift uses the state layer's precedence: latest "
        "`redshift_version`, then latest GCN `REDSHIFT_EVENT`.",
        "- Detection timescale follows the requested coarse proxy exactly: maximum "
        "`dt_occurred_hours` among all detection facts, not max-minus-min.",
        "- Measured CPU embedding times were 65.4-95.1 seconds per window, materially "
        "slower than a short single-digit-seconds expectation despite the small index.",
        "- The C4 text for `GRB-250702_210643` contains exposure strings (`4x180s`, "
        "`5x180s`, `8x180s`) as unknown bands. This is inherited STATE/ledger data and "
        "was not changed in this retrieval-only task.",
        f"- Self hits are {sum(results[w]['self_hits'] for w in WINDOWS)}; hard-filter "
        "messenger agreement is 100% in every window.",
    ]
    if len(lines) >= 160:
        raise AssertionError(f"Audit report is {len(lines)} lines; expected under 160")
    return lines


def main() -> int:
    """Run all window backtests, write the audit, and print a compact result."""
    indexes = {window: load_index(window) for window in WINDOWS}
    ledger = load_ledger()
    all_event_ids = sorted(
        set().union(*(set(index.metadata["event_id"]) for index in indexes.values()))
    )
    outcomes = {event_id: event_outcome(event_id, ledger) for event_id in all_event_ids}
    results = {
        window: evaluate_window(indexes[window], outcomes) for window in WINDOWS
    }

    neighbours_2026owq = retrieve_from_index("2026owq", indexes["24h"], K)
    audit = build_audit(indexes, results, neighbours_2026owq)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text("\n".join(audit) + "\n", encoding="utf-8")

    for window in WINDOWS:
        print(f"{window}: {len(indexes[window].metadata)} vectors")
    for row in neighbours_2026owq.itertuples(index=False):
        print(f"2026owq 24h #{row.rank}: {row.event_id} score={row.score:.6f}")
    for window in WINDOWS:
        dense = results[window]["redshift_dense"]
        random = results[window]["redshift_random"]
        print(
            f"{window} redshift |dz| median: retrieved={fmt(dense['median'])}, "
            f"random={fmt(random['median'])}; n={int(dense['n'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
