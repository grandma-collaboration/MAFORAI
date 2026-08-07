"""Normalise the flattened SkyPortal corpus into data/corpus_skyportal/.

Applies the fifteen normalisation decisions recorded in the final markdown
cell of notebooks/skyportal/A_eda.ipynb. The fifteen decisions are the
complete and closed set: anything they do not name is left untouched and
reported under UNCOVERED CASES, never silently coerced.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = REPO_ROOT / "data/interim/skyportal_corpus"
OUTPUT_ROOT = REPO_ROOT / "data/corpus_skyportal"

TABLE_NAMES = ["sources", "comments", "photometry", "spectra", "followup_requests"]

EMPTY_TOKENS = {"", "[]", "{}"}
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$")

IDENTIFIER_COLUMNS = {
    "sources": ["id"],
    "comments": ["obj_id", "source_dir"],
    "photometry": ["obj_id", "source_dir"],
    "spectra": ["obj_id", "source_dir"],
    "followup_requests": ["obj_id", "source_dir"],
}

STATUS_PREFIXES = ["failed to submit", "submitted for", "submitted", "deleted",
                    "complete", "rejected", "pending"]
PROCESSING_RESULT_PATTERNS = [
    re.compile(r"^Photometry committed to database$"),
    re.compile(r"^No photometry available"),
    re.compile(r"^No photometry to commit to database$"),
    re.compile(r"^\d+ images posted as comment$"),
]

MJD_RANGE_LOW = 55000
MJD_RANGE_HIGH = 61250

FIELD_HISTORY_TABLE = "source_field_history"
HISTORY_COLUMNS = {"redshift_history": "redshift", "summary_history": "summary"}
HISTORY_VALUE_KEYS = {"redshift_history": "value", "summary_history": "summary"}
FIELD_HISTORY_SCHEMA = ["source_id", "field", "entry_index", "value", "value_is_null",
                        "set_at_utc", "set_by_user_id", "uncertainty", "origin", "is_bot"]


# ---------------------------------------------------------------------------
# Shared helpers (not decisions themselves; used by several decisions)
# ---------------------------------------------------------------------------
def _has_content(value: Any) -> bool:
    """True where a cell holds real content. '', '[]', '{}' and blanks are empty."""
    if value is None:
        return False
    if isinstance(value, float) and np.isnan(value):
        return False
    if isinstance(value, str):
        return value.strip() not in EMPTY_TOKENS
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return True


def _strip_column(series: pd.Series) -> tuple[pd.Series, int]:
    """Strip leading/trailing whitespace from string cells; report how many changed."""
    after = series.map(lambda v: v.strip() if isinstance(v, str) else v)
    is_str = series.map(lambda v: isinstance(v, str))
    changed = int((is_str & (series != after)).sum())
    return after, changed


def _canonical_value(value: Any) -> Any:
    """Canonicalise one cell for cross-copy comparison: sort JSON object keys,
    treat every flavour of missing as the same None."""
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, str):
        if value[:1] in "[{":
            try:
                import json
                return json.dumps(json.loads(value), sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":"))
            except (ValueError, TypeError):
                return value
        return value
    return value


def _is_host_family(column: str) -> bool:
    """Columns belonging to the host-enrichment bundle for decision 2's comparison.

    'host.*' (dotted) is the literal nested host object. 'host_offset' is not
    dotted but is derived from host.ra/host.dec and empirically co-varies with
    them (present/absent together) in this corpus, so it is treated as part of
    the same enrichment bundle. 'host_id' (the plain foreign key column) is
    deliberately excluded: it is a different concept and never differs between
    copies in this data.
    """
    return column.startswith("host.") or column == "host_offset"


def new_effect(decision: int, table: str, rows_before: int, rows_after: int,
               rows_affected: int, columns_dropped: list[str], note: str) -> dict:
    return {
        "decision": decision, "table": table, "rows_before": rows_before,
        "rows_after": rows_after, "rows_affected": rows_affected,
        "columns_dropped": columns_dropped, "note": note,
    }


# ---------------------------------------------------------------------------
# Decision 2 — multi-profile canonical diff (analysis only, no mutation)
# ---------------------------------------------------------------------------
def d02_multiprofile_canonical_diff(sources_df: pd.DataFrame):
    """For each id present under more than one profile, determine which columns
    genuinely differ after JSON-key canonicalisation. Raises if a group is not
    exactly two rows. Non-host differences are NOT raised on: they are collected
    as UNCOVERED CASES so decision 1 can leave them untouched and the run can
    still complete and report."""
    exclude = {"id", "source_profile", "source_file"}
    compare_columns = [c for c in sources_df.columns if c not in exclude]
    id_counts = sources_df["id"].value_counts()
    multi_ids = sorted(id_counts[id_counts > 1].index)

    differences: dict[str, list[str]] = {}
    uncovered: list[dict] = []
    for source_id in multi_ids:
        group = sources_df[sources_df["id"] == source_id]
        if len(group) != 2:
            raise RuntimeError(
                f"Decision 2: source id {source_id!r} appears in {len(group)} rows, "
                f"expected exactly 2 for a multi-profile source"
            )
        row_a, row_b = group.iloc[0], group.iloc[1]
        differing = [c for c in compare_columns
                     if _canonical_value(row_a[c]) != _canonical_value(row_b[c])]
        if differing:
            differences[source_id] = differing
            non_host = [c for c in differing if not _is_host_family(c)]
            if non_host:
                uncovered.append({"source_id": source_id, "columns": non_host})

    effect = new_effect(
        decision=2, table="sources", rows_before=len(sources_df), rows_after=len(sources_df),
        rows_affected=len(differences) * 2, columns_dropped=[],
        note=(
            f"{len(multi_ids)} multi-profile ids checked after JSON-key canonicalisation; "
            f"{len(differences)} genuinely differ, confined to the host-enrichment family "
            f"('host.*' plus 'host_offset'); {len(uncovered)} ids differ in a column outside "
            f"that family and are reported under UNCOVERED CASES"
        ),
    )
    return differences, uncovered, effect


# ---------------------------------------------------------------------------
# Decision 1 — sources: one row per source
# ---------------------------------------------------------------------------
def d01_sources_one_row_per_source(sources_df: pd.DataFrame, uncovered_ids: set[str]):
    """Collapse sources to one row per id. Profile membership becomes the list
    column source_profiles; source_file becomes a list column (same name).
    Ids flagged as UNCOVERED (decision 2) are left uncollapsed: both original
    rows are kept, only carrying the new list columns for schema consistency."""
    rows_before = len(sources_df)
    records: list[dict] = []
    for source_id, group in sources_df.groupby("id", sort=True):
        profiles = sorted(group["source_profile"].unique().tolist())
        files = [group.loc[group["source_profile"] == p, "source_file"].iloc[0] for p in profiles]

        if source_id in uncovered_ids:
            for _, row in group.iterrows():
                record = row.to_dict()
                record["source_profiles"] = profiles
                record["source_file"] = files
                del record["source_profile"]
                records.append(record)
            continue

        if len(group) == 1:
            chosen = group.iloc[0]
        else:
            host_cols = [c for c in group.columns if _is_host_family(c)]
            richness = group.apply(
                lambda row: sum(1 for c in host_cols if _canonical_value(row[c]) is not None),
                axis=1,
            )
            chosen = group.loc[richness.idxmax()]

        record = chosen.to_dict()
        record["source_profiles"] = profiles
        record["source_file"] = files
        del record["source_profile"]
        records.append(record)

    result = pd.DataFrame.from_records(records)
    rows_after = len(result)
    effect = new_effect(
        decision=1, table="sources", rows_before=rows_before, rows_after=rows_after,
        rows_affected=rows_before - rows_after, columns_dropped=["source_profile"],
        note=(
            f"{rows_before} -> {rows_after} rows; 'source_profiles' (list) added, "
            f"'source_profile' dropped; 'source_file' converted from scalar to list "
            f"(same column name); {len(uncovered_ids)} ids left uncollapsed as UNCOVERED CASES"
        ),
    )
    return result, effect


# ---------------------------------------------------------------------------
# Decision 3 — followup_requests: keep the row where source_dir == obj_id
# ---------------------------------------------------------------------------
def d03_followup_keep_matching_source_dir(df: pd.DataFrame):
    rows_before = len(df)
    id_counts = df["id"].value_counts()
    duplicated_ids = set(id_counts[id_counts > 1].index)
    is_duplicated = df["id"].isin(duplicated_ids)
    matches = df["source_dir"] == df["obj_id"]
    keep_mask = (~is_duplicated) | (is_duplicated & matches)
    result = df[keep_mask].reset_index(drop=True)
    rows_removed = rows_before - len(result)
    if rows_removed != 20:
        raise RuntimeError(
            f"Decision 3 control failed: expected exactly 20 rows removed, observed {rows_removed}"
        )
    effect = new_effect(
        decision=3, table="followup_requests", rows_before=rows_before, rows_after=len(result),
        rows_affected=rows_removed, columns_dropped=[],
        note=(
            f"{len(duplicated_ids)} duplicated ids checked; kept the row where "
            f"source_dir == obj_id; {rows_removed} rows removed"
        ),
    )
    return result, effect


# ---------------------------------------------------------------------------
# Decision 4 — strip whitespace from identifier columns before any join
# ---------------------------------------------------------------------------
def d04_strip_identifier_whitespace(tables: dict[str, pd.DataFrame]):
    effects = []
    for table_name, columns in IDENTIFIER_COLUMNS.items():
        df = tables[table_name].copy()
        for column in columns:
            stripped, changed = _strip_column(df[column])
            df[column] = stripped
            effects.append(new_effect(
                decision=4, table=table_name, rows_before=len(df), rows_after=len(df),
                rows_affected=changed, columns_dropped=[],
                note=f"stripped whitespace from identifier column '{column}' before any join",
            ))
        tables[table_name] = df
    return tables, effects


# ---------------------------------------------------------------------------
# Decision 5 — strip whitespace from ALL string columns, all five tables
# ---------------------------------------------------------------------------
def d05_strip_all_string_whitespace(tables: dict[str, pd.DataFrame]):
    effects = []
    for table_name in TABLE_NAMES:
        df = tables[table_name].copy()
        for column in df.columns:
            if df[column].dtype != object:
                continue
            stripped, changed = _strip_column(df[column])
            if changed:
                df[column] = stripped
            effects.append(new_effect(
                decision=5, table=table_name, rows_before=len(df), rows_after=len(df),
                rows_affected=changed, columns_dropped=[],
                note=f"'{column}': {changed} rows with leading/trailing whitespace stripped"
                     if changed else f"'{column}': no whitespace anomalies found",
            ))
        tables[table_name] = df
    return tables, effects


# ---------------------------------------------------------------------------
# Decision 6 — drop columns with no content in any row
# ---------------------------------------------------------------------------
def d06_drop_empty_columns(tables: dict[str, pd.DataFrame]):
    effects = []
    dropped_by_table: dict[str, list[str]] = {}
    for table_name in TABLE_NAMES:
        df = tables[table_name]
        empty_columns = [c for c in df.columns if not df[c].map(_has_content).any()]
        dropped_by_table[table_name] = empty_columns
        df = df.drop(columns=empty_columns)
        effects.append(new_effect(
            decision=6, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=0, columns_dropped=empty_columns,
            note=f"dropped {len(empty_columns)} columns with no content in any row",
        ))
        tables[table_name] = df
    return tables, effects, dropped_by_table


# ---------------------------------------------------------------------------
# Decision 7 — drop comments.resourceType only
# ---------------------------------------------------------------------------
def d07_drop_comments_resource_type(comments_df: pd.DataFrame):
    rows_before = len(comments_df)
    dropped: list[str] = []
    if "resourceType" in comments_df.columns:
        comments_df = comments_df.drop(columns=["resourceType"])
        dropped = ["resourceType"]
    effect = new_effect(
        decision=7, table="comments", rows_before=rows_before, rows_after=len(comments_df),
        rows_affected=0, columns_dropped=dropped,
        note="dropped comments.resourceType (endpoint descriptor, not data); "
             "photometry.magsys retained even though constant",
    )
    return comments_df, effect


# ---------------------------------------------------------------------------
# Decision 8 — retain sparse columns, emit a coverage report
# ---------------------------------------------------------------------------
def d08_coverage_report(tables: dict[str, pd.DataFrame]):
    effects = []
    coverage: dict[str, dict[str, float]] = {}
    for table_name in TABLE_NAMES:
        df = tables[table_name]
        col_cov = {}
        for column in df.columns:
            content = df[column].map(_has_content)
            col_cov[column] = round(100 * content.sum() / len(df), 2) if len(df) else 0.0
        coverage[table_name] = col_cov
        sparse = [c for c, pct in col_cov.items() if pct < 5]
        effects.append(new_effect(
            decision=8, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=0, columns_dropped=[],
            note=f"{len(col_cov)} columns retained with documented coverage; "
                 f"{len(sparse)} columns below 5% coverage",
        ))
    return coverage, effects


# ---------------------------------------------------------------------------
# Decision 9 — status_normalised
# ---------------------------------------------------------------------------
def d09_status_normalised(df: pd.DataFrame):
    rows_before = len(df)
    status = df["status"].astype(str).str.strip()
    normalised = pd.Series(pd.NA, index=df.index, dtype="object")

    ordered_prefixes = sorted(STATUS_PREFIXES, key=len, reverse=True)
    for prefix in ordered_prefixes:
        mask = status.str.startswith(prefix) & normalised.isna()
        normalised[mask] = prefix
    for pattern in PROCESSING_RESULT_PATTERNS:
        mask = status.str.match(pattern) & normalised.isna()
        normalised[mask] = "processing_result"

    unassigned = normalised.isna()
    if unassigned.any():
        offending = sorted(status[unassigned].unique())
        raise RuntimeError(
            f"Decision 9 control failed: {int(unassigned.sum())} rows unassigned, "
            f"values={offending}"
        )

    df = df.copy()
    df["status_normalised"] = normalised
    counts = df["status_normalised"].value_counts().to_dict()
    effect = new_effect(
        decision=9, table="followup_requests", rows_before=rows_before, rows_after=len(df),
        rows_affected=rows_before, columns_dropped=[],
        note=f"status_normalised added with 8 values; status retained unchanged; counts={counts}",
    )
    return df, effect, counts


# ---------------------------------------------------------------------------
# Decision 10 — type ISO datetime columns as datetime64[ns, UTC]; MJD untouched
# ---------------------------------------------------------------------------
def d10_type_datetime_columns(tables: dict[str, pd.DataFrame]):
    effects = []
    for table_name in TABLE_NAMES:
        df = tables[table_name].copy()
        for column in list(df.columns):
            series = df[column]
            if series.dtype != object:
                continue
            non_null = series.dropna()
            if non_null.empty:
                continue
            text = non_null.map(lambda v: str(v).strip() if isinstance(v, str) else None)
            text = text.dropna()
            text = text[text != ""]
            if text.empty:
                continue
            if not text.map(lambda v: bool(ISO_RE.match(v))).all():
                continue

            blank_as_missing = series.map(
                lambda v: None if isinstance(v, str) and v.strip() == "" else v
            )
            converted = pd.to_datetime(
                blank_as_missing, utc=True, errors="raise", format="ISO8601"
            )
            df[column] = converted
            after_notna = int(converted.notna().sum())
            effects.append(new_effect(
                decision=10, table=table_name, rows_before=len(df), rows_after=len(df),
                rows_affected=after_notna, columns_dropped=[],
                note=f"'{column}' typed as datetime64[ns, UTC] (was ISO text); "
                     f"non-null cells={after_notna}",
            ))
        tables[table_name] = df
    return tables, effects


# ---------------------------------------------------------------------------
# Decision 11 — photometry.limiting_mag == -1.0 -> null
# ---------------------------------------------------------------------------
def d11_limiting_mag_sentinel_to_null(df: pd.DataFrame):
    rows_before = len(df)
    mask = df["limiting_mag"] == -1.0
    affected = int(mask.sum())
    if affected != 10:
        raise RuntimeError(
            f"Decision 11 control failed: expected 10 rows with limiting_mag == -1.0, "
            f"observed {affected}"
        )
    df = df.copy()
    df.loc[mask, "limiting_mag"] = np.nan
    effect = new_effect(
        decision=11, table="photometry", rows_before=rows_before, rows_after=len(df),
        rows_affected=affected, columns_dropped=[],
        note="limiting_mag == -1.0 (sentinel) set to null",
    )
    return df, effect


# ---------------------------------------------------------------------------
# Decision 12 — photometry.mjd outside [55000, 61250] -> null + flag column
# ---------------------------------------------------------------------------
def d12_mjd_out_of_range_to_null(df: pd.DataFrame):
    rows_before = len(df)
    mask = (df["mjd"] < MJD_RANGE_LOW) | (df["mjd"] > MJD_RANGE_HIGH)
    affected = int(mask.sum())
    if affected != 5:
        raise RuntimeError(
            f"Decision 12 control failed: expected 5 out-of-range mjd rows, observed {affected}"
        )
    df = df.copy()
    df["mjd_out_of_range"] = mask
    df.loc[mask, "mjd"] = np.nan
    effect = new_effect(
        decision=12, table="photometry", rows_before=rows_before, rows_after=len(df),
        rows_affected=affected, columns_dropped=[],
        note=f"mjd outside [{MJD_RANGE_LOW}, {MJD_RANGE_HIGH}] set to null; "
             f"mjd_out_of_range flag added; rows retained",
    )
    return df, effect


# ---------------------------------------------------------------------------
# Decision 13 — flag coordinates exactly equal to 0.0 (not nulled)
# ---------------------------------------------------------------------------
def d13_flag_zero_coordinates(df: pd.DataFrame, table_name: str,
                               column_pairs: list[tuple[str, str]]):
    effects = []
    df = df.copy()
    for source_column, flag_column in column_pairs:
        mask = df[source_column] == 0.0
        affected = int(mask.sum())
        df[flag_column] = mask
        effects.append(new_effect(
            decision=13, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=affected, columns_dropped=[],
            note=f"'{flag_column}' added; marks '{source_column}' == 0.0; value not nulled",
        ))
    return df, effects


# ---------------------------------------------------------------------------
# Decision 14 — origin / redshift_origin: no change beyond decision 5
# ---------------------------------------------------------------------------
def d14_retain_origin_columns(tables: dict[str, pd.DataFrame]):
    effects = []
    for table_name in TABLE_NAMES:
        df = tables[table_name]
        for column in df.columns:
            leaf = column.split(".")[-1]
            if leaf in ("origin", "redshift_origin"):
                effects.append(new_effect(
                    decision=14, table=table_name, rows_before=len(df), rows_after=len(df),
                    rows_affected=0, columns_dropped=[],
                    note=f"'{column}' values retained as free text; only decision 5 "
                         f"whitespace-stripping applied; no mapping or unification",
                ))
    return effects


# ---------------------------------------------------------------------------
# Decision 15 — created_at is the causal truncation anchor: verify 100% coverage
# ---------------------------------------------------------------------------
def d15_verify_created_at_anchor(tables: dict[str, pd.DataFrame]):
    effects = []
    for table_name in TABLE_NAMES:
        df = tables[table_name]
        if "created_at" not in df.columns:
            raise RuntimeError(f"Decision 15: table '{table_name}' has no created_at column")
        nulls = int(df["created_at"].isna().sum())
        if nulls != 0:
            raise RuntimeError(
                f"Decision 15 control failed: {table_name}.created_at has {nulls} null rows"
            )
        effects.append(new_effect(
            decision=15, table=table_name, rows_before=len(df), rows_after=len(df),
            rows_affected=len(df), columns_dropped=[],
            note="created_at verified 100% non-null; causal truncation anchor",
        ))
    return effects


# ---------------------------------------------------------------------------
# Decision 16 — expand the serialised field history into its own table
# ---------------------------------------------------------------------------
def d16_expand_source_field_history(df_sources: pd.DataFrame):
    """Emit one row per recorded change to a source field.

    The history arrives as a JSON array per source. A source returned by several
    profile queries carries the same array on every copy, so identity is collapsed
    before parsing: parsing all 982 interim rows would count every multi-profile
    history twice. Entries carrying no value are retained as deletion events.
    """
    unique_sources = df_sources.drop_duplicates(subset="id", keep="first")
    records: list[dict[str, Any]] = []

    for column, field in HISTORY_COLUMNS.items():
        value_key = HISTORY_VALUE_KEYS[column]
        carrying = unique_sources[unique_sources[column].notna()]
        for _, row in carrying.iterrows():
            source_id = row["id"]
            for entry_index, entry in enumerate(json.loads(row[column])):
                stamp = entry.get("set_at_utc")
                if not stamp:
                    raise RuntimeError(
                        f"Decision 16: {column} entry {entry_index} of source {source_id!r} "
                        f"carries no set_at_utc"
                    )
                user_id = entry.get("set_by_user_id")
                if not isinstance(user_id, int) or isinstance(user_id, bool):
                    raise RuntimeError(
                        f"Decision 16: {column} entry {entry_index} of source {source_id!r} "
                        f"carries set_by_user_id of type {type(user_id).__name__}, expected int"
                    )
                value = entry.get(value_key)
                records.append({
                    "source_id": source_id, "field": field, "entry_index": entry_index,
                    "value": value, "value_is_null": value is None, "set_at_utc": stamp,
                    "set_by_user_id": user_id, "uncertainty": entry.get("uncertainty"),
                    "origin": entry.get("origin"), "is_bot": entry.get("is_bot"),
                })

    if not records:
        raise RuntimeError("Decision 16 produced 0 history rows; refusing to write an empty table")

    frame = pd.DataFrame(records, columns=FIELD_HISTORY_SCHEMA)
    # Some stamps carry an explicit +00:00 offset and most carry none; both are UTC.
    frame["set_at_utc"] = pd.to_datetime(frame["set_at_utc"], format="ISO8601", utc=True)
    frame["is_bot"] = frame["is_bot"].astype("boolean")

    in_array_order = frame.sort_values(["source_id", "field", "entry_index"], kind="stable")
    chronological = in_array_order.groupby(["source_id", "field"])["set_at_utc"].apply(
        lambda stamps: list(stamps) == sorted(stamps))
    unordered = chronological[~chronological]

    frame = frame.sort_values(["source_id", "field", "set_at_utc"], kind="stable")
    frame = frame.reset_index(drop=True)

    per_field = frame["field"].value_counts().to_dict()
    deletions = frame[frame["value_is_null"]]["field"].value_counts().to_dict()
    sources_per_field = frame.groupby("field")["source_id"].nunique().to_dict()
    unordered_per_field = unordered.index.get_level_values("field").value_counts().to_dict()

    effect = new_effect(
        decision=16, table=FIELD_HISTORY_TABLE, rows_before=len(unique_sources),
        rows_after=len(frame), rows_affected=len(frame), columns_dropped=["analysis_id"],
        note=(
            f"{len(frame)} history rows expanded from {frame['source_id'].nunique()} sources; "
            f"rows per field={per_field}; sources per field={sources_per_field}; "
            f"deletion events per field={deletions}; sources not stored in chronological "
            f"order={len(unordered)} {unordered_per_field}; 'analysis_id' dropped as empty; "
            f"the serialised columns remain in sources"
        ),
    )
    effect.update({
        "rows_produced": len(frame), "sources_covered": int(frame["source_id"].nunique()),
        "rows_per_field": per_field, "sources_per_field": sources_per_field,
        "deletion_events_per_field": deletions,
        "sources_not_chronological": len(unordered),
        "sources_not_chronological_per_field": unordered_per_field,
    })
    return frame, effect


# ---------------------------------------------------------------------------
# Printing helpers
# ---------------------------------------------------------------------------
def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> None:
    tables: dict[str, pd.DataFrame] = {}
    for name in TABLE_NAMES:
        path = INPUT_ROOT / f"{name}.parquet"
        df = pd.read_parquet(path)
        if len(df) == 0:
            raise RuntimeError(f"Loaded 0 rows from {path}; refusing to proceed")
        tables[name] = df

    previous_hashes = {
        name: hashlib.sha256((OUTPUT_ROOT / f"{name}.parquet").read_bytes()).hexdigest()
        for name in TABLE_NAMES if (OUTPUT_ROOT / f"{name}.parquet").exists()
    }

    all_effects: list[dict] = []
    uncovered_cases: list[dict] = []

    # Decision 4 first: identifiers must be clean before any grouping or join.
    tables, effects4 = d04_strip_identifier_whitespace(tables)
    all_effects.extend(effects4)

    # Decision 16 (field history, read from the sources table before it is collapsed).
    field_history, effect16 = d16_expand_source_field_history(tables["sources"])
    all_effects.append(effect16)

    # Decisions 1 and 2 (sources shape).
    differences, uncovered2, effect2 = d02_multiprofile_canonical_diff(tables["sources"])
    all_effects.append(effect2)
    for item in uncovered2:
        uncovered_cases.append({
            "decision": 2, "table": "sources",
            "detail": f"source id {item['source_id']!r} differs in non-host column(s) "
                      f"{item['columns']}; left uncollapsed (both rows retained)",
        })
    uncovered_ids = {item["source_id"] for item in uncovered2}
    tables["sources"], effect1 = d01_sources_one_row_per_source(tables["sources"], uncovered_ids)
    all_effects.append(effect1)

    # Decision 3 (followup_requests shape).
    tables["followup_requests"], effect3 = d03_followup_keep_matching_source_dir(
        tables["followup_requests"]
    )
    all_effects.append(effect3)

    # Decision 5 (broad whitespace strip, all tables, post-shape).
    tables, effects5 = d05_strip_all_string_whitespace(tables)
    all_effects.extend(effects5)

    # Decision 6 (drop empty columns, all tables).
    tables, effects6, dropped_by_table = d06_drop_empty_columns(tables)
    all_effects.extend(effects6)

    # Decision 7 (comments.resourceType only).
    tables["comments"], effect7 = d07_drop_comments_resource_type(tables["comments"])
    all_effects.append(effect7)

    # Decision 9 (status_normalised).
    tables["followup_requests"], effect9, status_counts = d09_status_normalised(
        tables["followup_requests"]
    )
    all_effects.append(effect9)

    # Decision 11, 12 (photometry numeric anomalies).
    tables["photometry"], effect11 = d11_limiting_mag_sentinel_to_null(tables["photometry"])
    all_effects.append(effect11)
    tables["photometry"], effect12 = d12_mjd_out_of_range_to_null(tables["photometry"])
    all_effects.append(effect12)

    # Decision 13 (zero-coordinate flags).
    tables["sources"], effects13a = d13_flag_zero_coordinates(
        tables["sources"], "sources", [("ra", "ra_is_zero"), ("dec", "dec_is_zero")]
    )
    all_effects.extend(effects13a)
    tables["followup_requests"], effects13b = d13_flag_zero_coordinates(
        tables["followup_requests"], "followup_requests",
        [("obj.ra", "obj.ra_is_zero"), ("obj.dec", "obj.dec_is_zero")],
    )
    all_effects.extend(effects13b)

    # Decision 10 (datetime typing, all tables).
    tables, effects10 = d10_type_datetime_columns(tables)
    all_effects.extend(effects10)

    # Decision 14 (origin / redshift_origin: report only, no change).
    effects14 = d14_retain_origin_columns(tables)
    all_effects.extend(effects14)

    # Decision 8 (coverage report, final column set).
    coverage, effects8 = d08_coverage_report(tables)
    all_effects.extend(effects8)

    # Decision 15 (created_at anchor verification; hard stop on any null).
    effects15 = d15_verify_created_at_anchor(tables)
    all_effects.extend(effects15)

    for name in TABLE_NAMES:
        if len(tables[name]) == 0:
            raise RuntimeError(f"Table '{name}' has 0 rows after normalisation; refusing to write")
    if len(field_history) == 0:
        raise RuntimeError(f"Table '{FIELD_HISTORY_TABLE}' has 0 rows; refusing to write")

    # -----------------------------------------------------------------
    # CONTROLS
    # -----------------------------------------------------------------
    controls = []

    def check(name: str, observed: Any, expected: Any) -> None:
        controls.append({
            "control": name, "expected": expected, "observed": observed,
            "status": "PASS" if observed == expected else "FAIL",
        })

    check("sources rows", len(tables["sources"]), 800)
    check("comments rows", len(tables["comments"]), 2950)
    check("photometry rows", len(tables["photometry"]), 7968)
    check("spectra rows", len(tables["spectra"]), 1)
    check("followup_requests rows", len(tables["followup_requests"]), 2339)
    created_at_nulls = sum(int(tables[t]["created_at"].isna().sum()) for t in TABLE_NAMES)
    check("created_at null count (all tables)", created_at_nulls, 0)
    check("status_normalised unassigned rows",
          int(tables["followup_requests"]["status_normalised"].isna().sum()), 0)
    check("rows removed by decision 3", effect3["rows_affected"], 20)
    check("limiting_mag nulled", effect11["rows_affected"], 10)
    check("mjd nulled", effect12["rows_affected"], 5)

    redshift_rows = field_history[field_history["field"] == "redshift"]
    summary_rows = field_history[field_history["field"] == "summary"]
    check("source_field_history rows", len(field_history), 1357)
    check("distinct source_id", int(field_history["source_id"].nunique()), 266)
    check("rows where field == 'redshift'", len(redshift_rows), 83)
    check("rows where field == 'summary'", len(summary_rows), 1274)
    check("sources with redshift history", int(redshift_rows["source_id"].nunique()), 60)
    check("sources with summary history", int(summary_rows["source_id"].nunique()), 256)
    check("deletion events, redshift", int(redshift_rows["value_is_null"].sum()), 3)
    check("deletion events, summary", int(summary_rows["value_is_null"].sum()), 25)
    check("set_at_utc null count", int(field_history["set_at_utc"].isna().sum()), 0)
    check("is_bot true count", int((field_history["is_bot"] == True).sum()), 0)  # noqa: E712

    all_pass = all(c["status"] == "PASS" for c in controls)

    # -----------------------------------------------------------------
    # Write output (only if every control passes)
    # -----------------------------------------------------------------
    if all_pass:
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        for name in TABLE_NAMES:
            tables[name].to_parquet(
                OUTPUT_ROOT / f"{name}.parquet", engine="pyarrow", index=False,
            )
        field_history.to_parquet(
            OUTPUT_ROOT / f"{FIELD_HISTORY_TABLE}.parquet", engine="pyarrow", index=False,
        )

    # The five tables decisions 1-15 produce must survive this run unchanged.
    if all_pass and previous_hashes:
        identical = sum(
            1 for name in TABLE_NAMES
            if hashlib.sha256((OUTPUT_ROOT / f"{name}.parquet").read_bytes()).hexdigest()
            == previous_hashes.get(name)
        )
        check("the five existing tables, byte-identical",
              f"{identical} of {len(previous_hashes)}", "5 of 5")
        all_pass = all(c["status"] == "PASS" for c in controls)

    # -----------------------------------------------------------------
    # FINAL SUMMARY
    # -----------------------------------------------------------------
    print_section("1. CONTROLS")
    print(f"{'control':38s} {'expected':>10s} {'observed':>10s} {'status':>8s}")
    for c in controls:
        print(f"{c['control']:38s} {str(c['expected']):>10s} {str(c['observed']):>10s} {c['status']:>8s}")
    if not all_pass:
        print("\nAt least one control FAILED. No Parquet files were written.")

    print_section("2. EFFECT LOG (grouped by decision, 1 to 16)")
    by_decision: "OrderedDict[int, list[dict]]" = OrderedDict()
    for e in sorted(all_effects, key=lambda e: e["decision"]):
        by_decision.setdefault(e["decision"], []).append(e)
    for decision_number in range(1, 17):
        entries = by_decision.get(decision_number, [])
        if not entries:
            print(f"decision {decision_number:2d}: no effect entries recorded")
            continue
        tables_touched = sorted({e["table"] for e in entries})
        total_affected = sum(e["rows_affected"] for e in entries)
        all_dropped = sorted({c for e in entries for c in e["columns_dropped"]})
        print(f"decision {decision_number:2d}: tables={tables_touched} "
              f"rows_affected_total={total_affected} columns_dropped={all_dropped}")
        for e in entries:
            if decision_number == 5 and e["rows_affected"] == 0:
                continue  # zero-affected per-column entries summarised below instead
            print(f"    table={e['table']:20s} rows_before={e['rows_before']:6d} "
                  f"rows_after={e['rows_after']:6d} rows_affected={e['rows_affected']:6d} "
                  f"columns_dropped={e['columns_dropped']} | {e['note']}")

    print_section("2b. Decision 5 detail — per-column whitespace, zero-affected columns omitted above")
    d5_entries = by_decision.get(5, [])
    zero_count = sum(1 for e in d5_entries if e["rows_affected"] == 0)
    print(f"{len(d5_entries)} string columns checked across 5 tables; "
          f"{zero_count} had zero whitespace anomalies; "
          f"{len(d5_entries) - zero_count} had at least one row affected (listed above under decision 5).")

    print_section("3. Decision 2 detail — multi-profile sources genuinely differing")
    print(f"differing ids: {len(differences)}")
    column_frequency: dict[str, int] = {}
    for cols in differences.values():
        for c in cols:
            column_frequency[c] = column_frequency.get(c, 0) + 1
    for column, count in sorted(column_frequency.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {column:28s} differs for {count} id(s)")
    if not differences:
        print("  none")

    print_section("4. Decision 6 detail — dropped columns per table")
    for name in TABLE_NAMES:
        cols = dropped_by_table[name]
        print(f"{name} ({len(cols)} dropped): {cols}")

    print_section("5. Decision 9 detail — status_normalised counts")
    for value, count in sorted(status_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {value:20s} {count:5d}")
    print(f"  {'TOTAL':20s} {sum(status_counts.values()):5d}")

    print_section("6. Decision 16 detail — source_field_history")
    preview = field_history.head(15).copy()
    preview["value"] = preview["value"].map(
        lambda v: None if v is None else (v[:40] + "..." if len(v) > 40 else v))
    print(preview.to_string(index=False))
    print("\nentries per source, by field:")
    for field_name, group in field_history.groupby("field"):
        per_source = group.groupby("source_id").size()
        print(f"  {field_name:10s} sources={len(per_source):4d} min={per_source.min()} "
              f"median={per_source.median():.0f} max={per_source.max()}")

    print_section("7. UNCOVERED CASES")
    if uncovered_cases:
        for case in uncovered_cases:
            print(f"  decision {case['decision']} / table {case['table']}: {case['detail']}")
    else:
        print("  none")

    print_section("8. Output")
    if all_pass:
        for name in TABLE_NAMES:
            print(f"  wrote {OUTPUT_ROOT / f'{name}.parquet'} ({len(tables[name])} rows, "
                  f"{tables[name].shape[1]} columns)")
        print(f"  wrote {OUTPUT_ROOT / f'{FIELD_HISTORY_TABLE}.parquet'} "
              f"({len(field_history)} rows, {field_history.shape[1]} columns)")
    else:
        print("  no files written (controls failed)")

    print_section("9. Decision 8 detail — full column coverage")
    for name in TABLE_NAMES:
        print(f"\n-- {name} ({len(coverage[name])} columns) --")
        for column, pct in coverage[name].items():
            print(f"  {column:45s} {pct:6.2f}%")

    if not all_pass:
        raise RuntimeError("One or more controls failed; no Parquet files were written. See report above.")


if __name__ == "__main__":
    main()
