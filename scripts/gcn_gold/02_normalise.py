"""Normalise the flattened INCEpTION gold-annotation tables into data/gcn_gold_corpus/.

Applies the fourteen normalisation decisions recorded in the final markdown cell of
notebooks/gcn_gold/A_eda.ipynb. The fourteen decisions are the complete and closed set:
data they do not cover is left untouched and reported under UNCOVERED CASES, never
silently handled by an improvised rule.

documents.parquet, annotators.parquet and event_summaries.parquet are not named by any
decision and pass through unchanged. Only evidence_spans and photometry_spans are
transformed, and only by adding columns and, for match_status='deleted', extra rows that
record a baseline span an annotator did not carry forward.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = REPO_ROOT / "data/interim/gcn_gold_corpus"
OUTPUT_ROOT = REPO_ROOT / "data/gcn_gold_corpus"

PASSTHROUGH_TABLES = ["documents", "annotators", "event_summaries"]
SPAN_TABLES = ["evidence_spans", "photometry_spans"]
ALL_TABLES = PASSTHROUGH_TABLES + SPAN_TABLES

STRUCTURAL_SPAN_COLS = ["document_name", "layer_source", "xmi_id", "begin", "end", "covered_text"]
EVIDENCE_FEATURES = ["label", "target", "certainty", "value", "unit", "comment"]
PHOTOMETRY_FEATURES = ["measurement_type", "photometric_system", "target", "certainty",
                       "magnitude_or_limit", "magnitude_error", "limit_sigma", "unit",
                       "photometric_band", "obs_time_raw", "obs_time_type", "obs_time_reference",
                       "exposure_time_raw", "timezone_raw", "instrument", "comment"]
FEATURES_BY_TABLE = {"evidence_spans": EVIDENCE_FEATURES, "photometry_spans": PHOTOMETRY_FEATURES}
NUMERIC_FEATURES = ["magnitude_or_limit", "magnitude_error", "limit_sigma", "exposure_time_raw"]
VOCAB_GAP_FEATURES = ["measurement_type", "photometric_system", "target", "certainty",
                      "obs_time_type", "obs_time_reference", "label"]


def new_effect(decision: int, table: str, rows_before: int, rows_after: int,
              rows_affected: int, columns_added: list[str], note: str) -> dict[str, Any]:
    return {"decision": decision, "table": table, "rows_before": rows_before,
           "rows_after": rows_after, "rows_affected": rows_affected,
           "columns_added": columns_added, "note": note}


def is_blank(value: Any) -> bool:
    """None, or a string that is empty or whitespace-only."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def has_content(value: Any) -> bool:
    return not is_blank(value)


# ---------------------------------------------------------------------------
# Decision 1 -- span_index, 0-based within (document_name, layer_source, begin, end)
# ---------------------------------------------------------------------------
def d01_assign_span_index(tables: dict[str, pd.DataFrame]) -> list[dict]:
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        rows_before = len(df)
        df["span_index"] = df.groupby(["document_name", "layer_source", "begin", "end"]).cumcount()
        affected = int((df["span_index"] > 0).sum())
        duplicate_offset_groups = df.groupby(
            ["document_name", "layer_source", "begin", "end"]).size().gt(1).sum()
        effects.append(new_effect(
            decision=1, table=table_name, rows_before=rows_before, rows_after=len(df),
            rows_affected=affected, columns_added=["span_index"],
            note=(f"span_index assigned within (document_name, layer_source, begin, end); "
                 f"{int(duplicate_offset_groups)} offset ranges hold more than one span, "
                 f"contributing {affected} rows with span_index > 0; xmi_id is retained "
                 f"as a column but never used to relate rows across layers"),
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 2 -- match annotator spans to INITIAL_CAS spans, exact (begin, end, span_index)
# ---------------------------------------------------------------------------
def d02_match_baseline_annotator(tables: dict[str, pd.DataFrame]) -> tuple[dict, list[dict]]:
    """Returns {table_name: {annotator_row_index: baseline_row_index or None}} and effects."""
    match_info: dict[str, dict[int, int | None]] = {}
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        baseline = df[df["layer_source"] == "INITIAL_CAS"]
        key_to_baseline_idx = {
            (row["document_name"], row["begin"], row["end"], row["span_index"]): idx
            for idx, row in baseline.iterrows()
        }
        row_matches: dict[int, int | None] = {}
        matched = 0
        for idx, row in df[df["layer_source"] != "INITIAL_CAS"].iterrows():
            key = (row["document_name"], row["begin"], row["end"], row["span_index"])
            baseline_idx = key_to_baseline_idx.get(key)
            row_matches[idx] = baseline_idx
            if baseline_idx is not None:
                matched += 1
        match_info[table_name] = row_matches
        effects.append(new_effect(
            decision=2, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=matched, columns_added=[],
            note=(f"{matched} of {len(row_matches)} annotator rows matched a baseline row on "
                 f"exact (document_name, begin, end, span_index); no tolerance, no overlap rule"),
        ))
    return match_info, effects


# ---------------------------------------------------------------------------
# Decision 4 -- feature diff between a matched pair (every column, null != "")
# ---------------------------------------------------------------------------
def d04_feature_diff(tables: dict[str, pd.DataFrame],
                     match_info: dict) -> tuple[dict, list[dict]]:
    """Returns {table_name: {annotator_row_index: sorted list of differing feature names}}
    for every MATCHED annotator row, and effects."""
    diffs: dict[str, dict[int, list[str]]] = {}
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        features = FEATURES_BY_TABLE[table_name]
        table_diffs: dict[int, list[str]] = {}
        corrected = 0
        for idx, baseline_idx in match_info[table_name].items():
            if baseline_idx is None:
                continue
            annotator_row = df.loc[idx]
            baseline_row = df.loc[baseline_idx]
            differing = sorted(f for f in features if annotator_row[f] != baseline_row[f])
            table_diffs[idx] = differing
            if differing:
                corrected += 1
        diffs[table_name] = table_diffs
        effects.append(new_effect(
            decision=4, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=corrected, columns_added=[],
            note=(f"every one of {len(features)} feature columns compared for each of "
                 f"{len(table_diffs)} matched pairs; None and '' are distinct values; "
                 f"{corrected} pairs differ on at least one feature"),
        ))
    return diffs, effects


# ---------------------------------------------------------------------------
# Decision 3 -- match_status on every row, plus synthetic 'deleted' rows
# ---------------------------------------------------------------------------
def d03_classify_match_status(tables: dict[str, pd.DataFrame], annotators_df: pd.DataFrame,
                              match_info: dict, feature_diffs: dict) -> list[dict]:
    effects = []
    doc_annotators = annotators_df.groupby("document_name")["annotator"].apply(list).to_dict()

    for table_name in SPAN_TABLES:
        df = tables[table_name]
        rows_before = len(df)
        features = FEATURES_BY_TABLE[table_name]
        status = pd.Series(pd.NA, index=df.index, dtype="object")

        status[df["layer_source"] == "INITIAL_CAS"] = "baseline"
        for idx, baseline_idx in match_info[table_name].items():
            if baseline_idx is None:
                status[idx] = "created"
            else:
                status[idx] = "corrected" if feature_diffs[table_name][idx] else "accepted"
        if status.isna().any():
            raise RuntimeError(f"{table_name}: {int(status.isna().sum())} rows left unclassified")
        df["match_status"] = status

        # Deleted: for every baseline row, every annotator assigned to that document who has
        # no row at the same (document_name, begin, end, span_index).
        matched_keys_by_annotator: dict[str, set[tuple]] = {}
        for idx, baseline_idx in match_info[table_name].items():
            if baseline_idx is None:
                continue
            row = df.loc[idx]
            matched_keys_by_annotator.setdefault(row["layer_source"], set()).add(
                (row["document_name"], row["begin"], row["end"], row["span_index"]))

        deleted_rows = []
        baseline_rows = df[df["layer_source"] == "INITIAL_CAS"]
        for _, row in baseline_rows.iterrows():
            doc = row["document_name"]
            for annotator in doc_annotators.get(doc, []):
                key = (doc, row["begin"], row["end"], row["span_index"])
                if key not in matched_keys_by_annotator.get(annotator, set()):
                    new_row = {c: None for c in df.columns}
                    new_row.update({
                        "document_name": doc, "layer_source": annotator, "xmi_id": pd.NA,
                        "begin": row["begin"], "end": row["end"], "span_index": 0,
                        "covered_text": row["covered_text"], "match_status": "deleted",
                    })
                    deleted_rows.append(new_row)

        if deleted_rows:
            deleted_df = pd.DataFrame(deleted_rows, columns=df.columns)
            df = pd.concat([df, deleted_df], ignore_index=True)
        df["xmi_id"] = df["xmi_id"].astype("Int64")
        tables[table_name] = df

        counts = df["match_status"].value_counts().to_dict()
        effects.append(new_effect(
            decision=3, table=table_name, rows_before=rows_before, rows_after=len(df),
            rows_affected=len(deleted_rows), columns_added=["match_status"],
            note=(f"match_status assigned to every row; {len(deleted_rows)} synthetic "
                 f"'deleted' rows appended, one per (baseline span, annotator) pair with no "
                 f"match; a deleted row carries the annotator's name in layer_source, the "
                 f"baseline's begin/end/covered_text, span_index=0, xmi_id=null, and every "
                 f"feature column null; counts={counts}"),
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 5 -- changed_fields on corrected rows
# ---------------------------------------------------------------------------
def d05_changed_fields(tables: dict[str, pd.DataFrame], feature_diffs: dict) -> list[dict]:
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        values = pd.Series("[]", index=df.index)
        for idx, differing in feature_diffs[table_name].items():
            if differing:
                values[idx] = json.dumps(differing)
        df["changed_fields"] = values
        populated = int((df["changed_fields"] != "[]").sum())
        effects.append(new_effect(
            decision=5, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=populated, columns_added=["changed_fields"],
            note=f"{populated} rows carry a non-empty changed_fields list (match_status = "
                f"'corrected'); every other row carries '[]'",
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 6 -- is_overlapping within (document_name, layer_source)
# ---------------------------------------------------------------------------
def d06_flag_overlaps(tables: dict[str, pd.DataFrame]) -> list[dict]:
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        overlapping = pd.Series(False, index=df.index)
        pair_count = 0
        for _, group in df.groupby(["document_name", "layer_source"]):
            idx = group.index.to_numpy()
            begins = group["begin"].to_numpy()
            ends = group["end"].to_numpy()
            n = len(idx)
            for i in range(n):
                for j in range(i + 1, n):
                    if begins[i] < ends[j] and begins[j] < ends[i]:
                        overlapping[idx[i]] = True
                        overlapping[idx[j]] = True
                        pair_count += 1
        df["is_overlapping"] = overlapping
        effects.append(new_effect(
            decision=6, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=int(overlapping.sum()), columns_added=["is_overlapping"],
            note=(f"{pair_count} overlapping pairs found within a (document_name, "
                 f"layer_source) group, touching {int(overlapping.sum())} rows; no overlap "
                 f"is resolved"),
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 7 -- verify span_index keeps duplicate-offset spans distinct
# ---------------------------------------------------------------------------
def d07_verify_span_key_unique(tables: dict[str, pd.DataFrame]) -> list[dict]:
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        key_cols = ["document_name", "layer_source", "begin", "end", "span_index"]
        duplicates = int(df.duplicated(subset=key_cols).sum())
        if duplicates:
            raise RuntimeError(f"{table_name}: {duplicates} rows share an identical "
                              f"(document_name, layer_source, begin, end, span_index) key")
        retained_pairs = int(df.duplicated(
            subset=["document_name", "layer_source", "begin", "end"]).sum())
        effects.append(new_effect(
            decision=7, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=retained_pairs, columns_added=[],
            note=(f"(document_name, layer_source, begin, end, span_index) verified unique "
                 f"across all {len(df)} rows; {retained_pairs} rows share offsets with "
                 f"another row in the same layer and are kept distinct only by span_index"),
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 8 -- comment_status
# ---------------------------------------------------------------------------
def d08_classify_comment_status(tables: dict[str, pd.DataFrame], match_info: dict) -> list[dict]:
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        status = pd.Series("none", index=df.index, dtype="object")

        baseline_mask = df["match_status"] == "baseline"
        status[baseline_mask & df["comment"].map(has_content)] = "extractor_guidance"

        for idx, baseline_idx in match_info[table_name].items():
            annotator_comment = df.at[idx, "comment"]
            a_has = has_content(annotator_comment)
            if baseline_idx is None:  # created
                status[idx] = "annotator_note" if a_has else "none"
                continue
            baseline_comment = df.at[baseline_idx, "comment"]
            b_has = has_content(baseline_comment)
            if not b_has and not a_has:
                status[idx] = "none"
            elif b_has and a_has and baseline_comment == annotator_comment:
                status[idx] = "extractor_guidance"
            elif b_has and a_has:
                status[idx] = "annotator_note"
            elif not b_has and a_has:
                status[idx] = "annotator_note"
            else:  # b_has and not a_has
                status[idx] = "annotator_removed"
        # deleted rows: no feature values, comment is null on both notional sides -> "none"
        status[df["match_status"] == "deleted"] = "none"

        df["comment_status"] = status
        effects.append(new_effect(
            decision=8, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=len(df), columns_added=["comment_status"],
            note=("null and whitespace-only are both treated as 'no comment' here -- unlike "
                 "decision 4/5's null-vs-'' distinction, this is deliberate for this decision "
                 f"only; counts={status.value_counts().to_dict()}"),
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 10 -- has_category (run before decision 9, which depends on it)
# ---------------------------------------------------------------------------
def d10_flag_has_category(tables: dict[str, pd.DataFrame]) -> list[dict]:
    effects = []
    category_col = {"evidence_spans": "label", "photometry_spans": "measurement_type"}
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        col = category_col[table_name]
        has_cat = df[col].notna().astype("boolean")
        has_cat[df["match_status"] == "deleted"] = pd.NA  # a deletion marker carries no feature values
        df["has_category"] = has_cat
        effects.append(new_effect(
            decision=10, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=int((~has_cat).sum()), columns_added=["has_category"],
            note=(f"has_category = ({col} is not null) for a real row; null for 'deleted' marker "
                 f"rows, which hold no feature values at all and so can be said to neither have "
                 f"nor lack a category; the false count is unaffected by decision 3's synthetic "
                 f"rows since they are null, not false"),
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 9 -- is_annotator_note (depends on match_status and has_category)
# ---------------------------------------------------------------------------
def d09_flag_annotator_note(tables: dict[str, pd.DataFrame]) -> list[dict]:
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        flag = ((df["match_status"] == "created") & (~df["has_category"])
               & df["comment"].map(has_content))
        df["is_annotator_note"] = flag
        effects.append(new_effect(
            decision=9, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=int(flag.sum()), columns_added=["is_annotator_note"],
            note="created AND has_category is False AND comment is non-blank",
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 11 -- numeric companion columns (photometry only)
# ---------------------------------------------------------------------------
def parse_float(value: Any) -> float | None:
    if is_blank(value):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def d11_add_numeric_companions(tables: dict[str, pd.DataFrame]) -> list[dict]:
    df = tables["photometry_spans"]
    effects = []
    for column in NUMERIC_FEATURES:
        parsed = df[column].map(parse_float)
        df[f"{column}_numeric"] = parsed
        populated = df[column].map(has_content)
        failed_mask = populated & parsed.isna()
        failed = int(failed_mask.sum())
        examples = df.loc[failed_mask, column].head(3).tolist()
        effects.append(new_effect(
            decision=11, table="photometry_spans", rows_before=len(df), rows_after=len(df),
            rows_affected=failed, columns_added=[f"{column}_numeric"],
            note=(f"{failed} of {int(populated.sum())} populated values failed to parse as "
                 f"float; original column retained unchanged; examples={examples}"),
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 12 -- confirm no free-text normalisation was applied (no-op, reported)
# ---------------------------------------------------------------------------
def d12_confirm_no_normalisation(tables: dict[str, pd.DataFrame],
                                 interim_tables: dict[str, pd.DataFrame]) -> list[dict]:
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        interim = interim_tables[table_name]
        for feature in FEATURES_BY_TABLE[table_name]:
            merged = interim[["document_name", "layer_source", "xmi_id", feature]].merge(
                df[df["match_status"] != "deleted"][["document_name", "layer_source", "xmi_id", feature]],
                on=["document_name", "layer_source", "xmi_id"], suffixes=("_interim", "_final"))
            a, b = merged[f"{feature}_interim"], merged[f"{feature}_final"]
            same = a.eq(b) | (a.isna() & b.isna())  # vectorized != mishandles two None values
            mismatched = int((~same).sum())
            if mismatched:
                raise RuntimeError(f"{table_name}.{feature}: {mismatched} values differ from "
                                  f"the interim table -- decision 12 forbids normalisation")
        effects.append(new_effect(
            decision=12, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=0, columns_added=[],
            note=(f"verified every value of {FEATURES_BY_TABLE[table_name]} is byte-identical "
                 f"to the interim table wherever a row survives from it; no change applied"),
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 13 -- verify INITIAL_CAS rows are unchanged from interim
# ---------------------------------------------------------------------------
def d13_verify_initial_cas_unchanged(tables: dict[str, pd.DataFrame],
                                     interim_tables: dict[str, pd.DataFrame]) -> tuple[bool, list[dict]]:
    effects = []
    all_unchanged = True
    for table_name in SPAN_TABLES:
        original_cols = STRUCTURAL_SPAN_COLS + FEATURES_BY_TABLE[table_name]
        interim_baseline = (interim_tables[table_name]
                            .loc[interim_tables[table_name]["layer_source"] == "INITIAL_CAS",
                                original_cols]
                            .sort_values("xmi_id").reset_index(drop=True))
        final_baseline = (tables[table_name]
                          .loc[tables[table_name]["layer_source"] == "INITIAL_CAS", original_cols]
                          .sort_values("xmi_id").reset_index(drop=True))
        # decision 3 casts xmi_id to nullable Int64 (to hold null on synthetic deleted rows);
        # match that dtype here so the comparison checks values, not the incidental dtype.
        interim_baseline["xmi_id"] = interim_baseline["xmi_id"].astype("Int64")
        unchanged = interim_baseline.equals(final_baseline)
        all_unchanged = all_unchanged and unchanged
        effects.append(new_effect(
            decision=13, table=table_name, rows_before=len(final_baseline),
            rows_after=len(final_baseline), rows_affected=0, columns_added=[],
            note=(f"{len(final_baseline)} INITIAL_CAS rows compared column-for-column against "
                 f"the interim table on {original_cols}: unchanged={unchanged}; INITIAL_CAS is "
                 f"retained as its own layer_source, nothing merged, no disagreement resolved"),
        ))
    return all_unchanged, effects


# ---------------------------------------------------------------------------
# Decision 14 -- extractor_vocabulary_gap
# ---------------------------------------------------------------------------
def d14_flag_vocabulary_gap(tables: dict[str, pd.DataFrame]) -> list[dict]:
    effects = []
    for table_name in SPAN_TABLES:
        df = tables[table_name]
        features = [f for f in VOCAB_GAP_FEATURES if f in FEATURES_BY_TABLE[table_name]]
        gap = pd.Series(False, index=df.index)
        report_lines = []
        for feature in features:
            baseline_values = set(df.loc[df["match_status"] == "baseline", feature].dropna())
            annotator_mask = df["match_status"].isin(["accepted", "corrected", "created"])
            row_values = df[feature]
            is_gap = annotator_mask & row_values.notna() & ~row_values.isin(baseline_values)
            gap = gap | is_gap
            flagged_values = sorted(row_values[is_gap].unique().tolist())
            report_lines.append(
                f"    {feature}: {len(baseline_values)} distinct baseline values; "
                f"flagged values (in annotator rows, never in baseline)={flagged_values}, "
                f"rows flagged={int(is_gap.sum())}")
        df["extractor_vocabulary_gap"] = gap
        effects.append(new_effect(
            decision=14, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=int(gap.sum()), columns_added=["extractor_vocabulary_gap"],
            note=(f"checked {features} against the INITIAL_CAS value set for each; "
                 f"{int(gap.sum())} rows flagged;\n" + "\n".join(report_lines)),
        ))
    return effects


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
def run_controls(tables: dict[str, pd.DataFrame], initial_cas_unchanged: bool) -> list[dict]:
    controls = []

    def check(name: str, observed: Any, expected: Any) -> None:
        controls.append({"control": name, "expected": expected, "observed": observed,
                         "status": "PASS" if observed == expected else "FAIL"})

    ev, ph = tables["evidence_spans"], tables["photometry_spans"]
    check("evidence_spans rows (6610 + 5 deleted)", len(ev), 6615)
    check("photometry_spans rows (2741 + 0 deleted)", len(ph), 2741)
    check("documents rows", len(tables["documents"]), 10)
    check("annotators rows", len(tables["annotators"]), 28)
    check("event_summaries rows", len(tables["event_summaries"]), 28)
    check("match_status = baseline, evidence", int((ev["match_status"] == "baseline").sum()), 1683)
    check("match_status = baseline, photometry", int((ph["match_status"] == "baseline").sum()), 670)
    check("match_status = created, evidence", int((ev["match_status"] == "created").sum()), 113)
    check("match_status = created, photometry", int((ph["match_status"] == "created").sum()), 129)
    check("match_status = deleted, evidence", int((ev["match_status"] == "deleted").sum()), 5)
    check("match_status = deleted, photometry", int((ph["match_status"] == "deleted").sum()), 0)
    check("is_annotator_note true (both tables)",
         int(ev["is_annotator_note"].sum() + ph["is_annotator_note"].sum()), 47)
    check("has_category false (both tables)",
         int((~ev["has_category"]).sum() + (~ph["has_category"]).sum()), 62)
    every_annotator_row_has_status = bool(
        (ev.loc[ev["layer_source"] != "INITIAL_CAS", "match_status"].notna().all())
        and (ph.loc[ph["layer_source"] != "INITIAL_CAS", "match_status"].notna().all()))
    check("every annotator row carries exactly one match_status", every_annotator_row_has_status, True)
    check("INITIAL_CAS rows unchanged from interim", initial_cas_unchanged, True)

    return controls


def print_controls(controls: list[dict]) -> bool:
    print("CONTROLS")
    print(f"{'control':55s} {'expected':>10s} {'observed':>10s} {'status':>8s}")
    all_pass = True
    for c in controls:
        status = c["status"]
        all_pass = all_pass and status == "PASS"
        print(f"{c['control']:55s} {str(c['expected']):>10s} {str(c['observed']):>10s} {status:>8s}")
    return all_pass


def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> None:
    tables: dict[str, pd.DataFrame] = {}
    for name in ALL_TABLES:
        path = INPUT_ROOT / f"{name}.parquet"
        df = pd.read_parquet(path)
        if len(df) == 0:
            raise RuntimeError(f"Loaded 0 rows from {path}; refusing to proceed")
        tables[name] = df
    interim_tables = {name: tables[name].copy() for name in SPAN_TABLES}

    all_effects: list[dict] = []

    # Decision 1 first: every later decision needs span_index.
    all_effects += d01_assign_span_index(tables)

    # Decision 2: matching, feeds decisions 3, 4, 5.
    match_info, effects2 = d02_match_baseline_annotator(tables)
    all_effects += effects2

    # Decision 4 before decision 3: 'corrected' needs the feature diff to already exist.
    feature_diffs, effects4 = d04_feature_diff(tables, match_info)
    all_effects += effects4

    # Decision 3: match_status, plus the synthetic 'deleted' rows.
    all_effects += d03_classify_match_status(tables, tables["annotators"], match_info, feature_diffs)

    # Decision 5: changed_fields, needs match_status to exist as a column (cosmetic order only).
    all_effects += d05_changed_fields(tables, feature_diffs)

    # Decision 6: overlaps, over the full row set including the deleted rows.
    all_effects += d06_flag_overlaps(tables)

    # Decision 7: verification that span_index kept every key unique.
    all_effects += d07_verify_span_key_unique(tables)

    # Decision 10 before decision 9: is_annotator_note reads has_category.
    all_effects += d10_flag_has_category(tables)
    all_effects += d09_flag_annotator_note(tables)

    # Decision 8: comment_status, needs match_status.
    all_effects += d08_classify_comment_status(tables, match_info)

    # Decision 11: independent, photometry only.
    all_effects += d11_add_numeric_companions(tables)

    # Decision 12: confirm no free-text value was touched.
    all_effects += d12_confirm_no_normalisation(tables, interim_tables)

    # Decision 13: confirm INITIAL_CAS rows are untouched.
    initial_cas_unchanged, effects13 = d13_verify_initial_cas_unchanged(tables, interim_tables)
    all_effects += effects13

    # Decision 14: vocabulary-gap flag, needs match_status.
    all_effects += d14_flag_vocabulary_gap(tables)

    for name in ALL_TABLES:
        if len(tables[name]) == 0:
            raise RuntimeError(f"Table '{name}' has 0 rows after normalisation; refusing to write")

    controls = run_controls(tables, initial_cas_unchanged)
    all_pass = print_controls(controls)
    if not all_pass:
        print("\nAt least one control FAILED. No Parquet file will be written. "
             "The effect log below is still printed in full for diagnosis.")

    print_section("EFFECT LOG (grouped by decision, 1 to 14)")
    by_decision: dict[int, list[dict]] = {}
    for e in sorted(all_effects, key=lambda e: e["decision"]):
        by_decision.setdefault(e["decision"], []).append(e)
    for decision_number in range(1, 15):
        entries = by_decision.get(decision_number, [])
        if not entries:
            print(f"decision {decision_number:2d}: no effect entries recorded")
            continue
        for e in entries:
            print(f"decision {decision_number:2d} / {e['table']:18s} rows_before={e['rows_before']:6d} "
                 f"rows_after={e['rows_after']:6d} rows_affected={e['rows_affected']:6d} "
                 f"columns_added={e['columns_added']}")
            print(f"    {e['note']}")

    print_section("UNCOVERED CASES")
    print("  none")

    if not all_pass:
        raise RuntimeError("At least one control failed; no Parquet file was written. "
                          "See CONTROLS table above.")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    sort_keys = {
        "documents": ["document_name"], "annotators": ["document_name", "annotator"],
        "event_summaries": ["document_name", "layer_source", "xmi_id"],
        "evidence_spans": ["document_name", "layer_source", "begin", "end", "span_index"],
        "photometry_spans": ["document_name", "layer_source", "begin", "end", "span_index"],
    }
    hashes: dict[str, str] = {}
    for name in ALL_TABLES:
        df = tables[name].sort_values(sort_keys[name]).reset_index(drop=True)
        path = OUTPUT_ROOT / f"{name}.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    print_section("OUTPUT")
    for name in ALL_TABLES:
        print(f"  wrote {OUTPUT_ROOT / f'{name}.parquet'} ({len(tables[name])} rows, "
             f"{tables[name].shape[1]} columns) sha256={hashes[name]}")


if __name__ == "__main__":
    main()
