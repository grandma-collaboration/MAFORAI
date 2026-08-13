"""Build the static ICARE telescope/instrument resource catalog.

The catalog has exactly one row per ICARE instrument. ICARE supplies the
canonical resource identities, coordinates, instrument type, and filters;
the curated CSV supplies static external capability and eligibility fields.
No observations, allocations, dynamic observability, or historical research
sources are read here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd


LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_ROOT = REPO_ROOT / "data" / "interim" / "telescopes"
EXTERNAL_PATH = REPO_ROOT / "data" / "raw" / "reference" / "telescope_external_capabilities.csv"
OUTPUT_PATH = INTERIM_ROOT / "resource_catalog.parquet"

EXPECTED_INSTRUMENT_ROWS = 95
EXPECTED_EXTERNAL_ROWS = 89
EXPECTED_MISSING_EXTERNAL_ROWS = 6

CATALOG_COLUMNS = [
    "telescope_id",
    "telescope_name",
    "latitude",
    "longitude",
    "elevation",
    "instrument_id",
    "instrument_name",
    "instrument_type",
    "filters",
    "mlim_mag",
    "mlim_filter",
    "mlim_exposure",
    "mlim_status",
    "mlim_source",
    "usage_class",
    "followup_eligible",
    "restriction_note",
    "provenance_note",
]

EXTERNAL_COLUMNS = [
    "icare_telescope",
    "icare_instrument",
    "mlim_mag",
    "mlim_filter",
    "mlim_exposure",
    "mlim_source",
    "usage_class",
    "followup_eligible",
    "restriction_note",
    "provenance_note",
]


def normalize_key(value: Any) -> str:
    """Apply the complete allowed join normalization: strip and casefold."""
    if pd.isna(value):
        return ""
    return str(value).strip().casefold()


def optional_text(value: Any) -> str | None:
    """Return stripped text, using None for a missing or empty value."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def find_latest_capture(interim_root: Path) -> Path:
    """Return the latest capture directory containing both required tables."""
    candidates = [
        path
        for path in sorted(interim_root.glob("capture_*"))
        if path.is_dir()
        and (path / "telescopes.parquet").is_file()
        and (path / "instruments.parquet").is_file()
    ]
    if not candidates:
        raise RuntimeError(f"No complete ICARE telescope capture found under {interim_root}")
    return candidates[-1]


def load_icare_tables(capture_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load only the canonical ICARE telescope and instrument tables."""
    telescope_path = capture_dir / "telescopes.parquet"
    instrument_path = capture_dir / "instruments.parquet"
    telescopes = pd.read_parquet(telescope_path, engine="pyarrow")
    instruments = pd.read_parquet(instrument_path, engine="pyarrow")

    telescope_required = {"id", "name", "lat", "lon", "elevation"}
    instrument_required = {"id", "telescope_id", "name", "type", "band", "filters"}
    missing_telescope = sorted(telescope_required - set(telescopes.columns))
    missing_instrument = sorted(instrument_required - set(instruments.columns))
    if missing_telescope or missing_instrument:
        raise RuntimeError(
            "Required ICARE columns are missing: "
            f"telescopes={missing_telescope}, instruments={missing_instrument}"
        )

    LOGGER.info(
        "Loaded ICARE capture %s: %d telescopes, %d instruments",
        capture_dir.name,
        len(telescopes),
        len(instruments),
    )
    return telescopes, instruments


def load_external_capabilities(path: Path) -> pd.DataFrame:
    """Load and validate the curated external capability contract."""
    external = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = sorted(set(EXTERNAL_COLUMNS) - set(external.columns))
    if missing:
        raise RuntimeError(f"Curated external CSV is missing columns: {missing}")

    external = external[EXTERNAL_COLUMNS].copy()
    external["_telescope_key"] = external["icare_telescope"].map(normalize_key)
    external["_instrument_key"] = external["icare_instrument"].map(normalize_key)
    key_columns = ["_telescope_key", "_instrument_key"]
    duplicate_keys = external[external.duplicated(key_columns, keep=False)]
    if not duplicate_keys.empty:
        raise RuntimeError(
            "Curated external CSV has duplicate normalized keys:\n"
            + duplicate_keys[["icare_telescope", "icare_instrument"]].to_string(index=False)
        )

    raw_mlim = external["mlim_mag"].str.strip()
    parsed_mlim = pd.to_numeric(raw_mlim.replace("", pd.NA), errors="coerce")
    invalid_mlim = raw_mlim.ne("") & parsed_mlim.isna()
    if invalid_mlim.any():
        raise RuntimeError(
            "Curated external CSV has non-numeric Mlim values:\n"
            + external.loc[
                invalid_mlim, ["icare_telescope", "icare_instrument", "mlim_mag"]
            ].to_string(index=False)
        )
    external["mlim_mag"] = parsed_mlim.astype("float64")

    raw_eligibility = external["followup_eligible"].str.strip().str.casefold()
    invalid_eligibility = ~raw_eligibility.isin({"true", "false"})
    if invalid_eligibility.any():
        raise RuntimeError(
            "Curated external CSV has invalid followup_eligible values:\n"
            + external.loc[
                invalid_eligibility,
                ["icare_telescope", "icare_instrument", "followup_eligible"],
            ].to_string(index=False)
        )
    external["followup_eligible"] = raw_eligibility.map({"true": True, "false": False})

    for column in [
        "mlim_filter",
        "mlim_exposure",
        "mlim_source",
        "usage_class",
        "restriction_note",
        "provenance_note",
    ]:
        external[column] = external[column].map(optional_text)

    LOGGER.info("Loaded %d curated external capability rows", len(external))
    return external


def outside_photometry_mvp(instrument_type: Any, band: Any) -> bool:
    """Identify clearly spectroscopic-only or high-energy native instruments."""
    type_key = normalize_key(instrument_type)
    band_key = normalize_key(band).replace("-", " ")
    spectroscopic_only = "spectro" in type_key and "imaging" not in type_key
    high_energy = "xray" in band_key.replace(" ", "") or "gamma" in band_key
    return spectroscopic_only or high_energy


def build_resource_catalog(
    telescopes: pd.DataFrame,
    instruments: pd.DataFrame,
    external: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build one left-joined catalog row per canonical ICARE instrument."""
    telescope_base = telescopes[["id", "name", "lat", "lon", "elevation"]].rename(
        columns={
            "id": "telescope_id",
            "name": "telescope_name",
            "lat": "latitude",
            "lon": "longitude",
        }
    )
    if telescope_base["telescope_id"].duplicated().any():
        raise RuntimeError("ICARE telescope IDs are not unique")

    instrument_base = instruments[["id", "telescope_id", "name", "type", "band", "filters"]].rename(
        columns={
            "id": "instrument_id",
            "name": "instrument_name",
            "type": "instrument_type",
            "band": "_native_band",
        }
    )
    if instrument_base["instrument_id"].duplicated().any():
        raise RuntimeError("ICARE instrument IDs are not unique")

    canonical = instrument_base.merge(
        telescope_base,
        on="telescope_id",
        how="left",
        validate="many_to_one",
    )
    if canonical["telescope_name"].isna().any():
        missing_ids = canonical.loc[canonical["telescope_name"].isna(), "telescope_id"].tolist()
        raise RuntimeError(f"ICARE instruments reference missing telescope IDs: {missing_ids}")

    canonical["_telescope_key"] = canonical["telescope_name"].map(normalize_key)
    canonical["_instrument_key"] = canonical["instrument_name"].map(normalize_key)
    key_columns = ["_telescope_key", "_instrument_key"]
    duplicate_icare_keys = canonical[canonical.duplicated(key_columns, keep=False)]
    if not duplicate_icare_keys.empty:
        raise RuntimeError(
            "ICARE has duplicate normalized telescope/instrument keys:\n"
            + duplicate_icare_keys[
                ["telescope_id", "instrument_id", "telescope_name", "instrument_name"]
            ].to_string(index=False)
        )

    icare_exact_keys = set(zip(canonical["telescope_name"], canonical["instrument_name"]))
    external_exact_keys = list(zip(external["icare_telescope"], external["icare_instrument"]))
    exact_matches = sum(key in icare_exact_keys for key in external_exact_keys)

    icare_normalized_keys = set(map(tuple, canonical[key_columns].to_numpy()))
    external_normalized_keys = list(map(tuple, external[key_columns].to_numpy()))
    normalized_matches = sum(key in icare_normalized_keys for key in external_normalized_keys)
    unmatched_external = external[
        ~external[key_columns].apply(tuple, axis=1).isin(icare_normalized_keys)
    ].copy()

    external_payload_columns = key_columns + [
        "mlim_mag",
        "mlim_filter",
        "mlim_exposure",
        "mlim_source",
        "usage_class",
        "followup_eligible",
        "restriction_note",
        "provenance_note",
    ]
    merged = canonical.merge(
        external[external_payload_columns],
        on=key_columns,
        how="left",
        validate="one_to_one",
        indicator="_external_merge",
    )
    external_matched = merged["_external_merge"].eq("both")
    outside_mvp = pd.Series(False, index=merged.index, dtype=bool)
    missing_external_mask = ~external_matched
    outside_mvp.loc[missing_external_mask] = merged.loc[missing_external_mask].apply(
        lambda row: outside_photometry_mvp(row["instrument_type"], row["_native_band"]),
        axis=1,
    )

    followup = pd.Series(pd.NA, index=merged.index, dtype="boolean")
    followup.loc[external_matched] = merged.loc[
        external_matched, "followup_eligible"
    ].astype("boolean")
    followup.loc[missing_external_mask & outside_mvp] = False
    merged["followup_eligible"] = followup
    merged.loc[
        missing_external_mask & outside_mvp, "restriction_note"
    ] = "Outside photometry/imaging MVP"

    merged["mlim_status"] = merged["mlim_mag"].notna().map({True: "KNOWN", False: "UNKNOWN"})

    catalog = merged[CATALOG_COLUMNS].copy()
    catalog["telescope_id"] = catalog["telescope_id"].astype("int64")
    catalog["instrument_id"] = catalog["instrument_id"].astype("int64")
    catalog["mlim_mag"] = pd.to_numeric(catalog["mlim_mag"], errors="raise").astype("float64")
    catalog["followup_eligible"] = catalog["followup_eligible"].astype("boolean")

    for column in [
        "telescope_name",
        "instrument_name",
        "instrument_type",
        "mlim_filter",
        "mlim_exposure",
        "mlim_status",
        "mlim_source",
        "usage_class",
        "restriction_note",
        "provenance_note",
    ]:
        catalog[column] = catalog[column].map(optional_text)

    audit = merged[
        ["instrument_id", "_external_merge", "instrument_type", "_native_band", "mlim_mag"]
    ].copy()
    audit["outside_mvp"] = outside_mvp
    audit["expected_followup"] = followup

    missing_external = merged.loc[
        missing_external_mask,
        ["telescope_id", "instrument_id", "telescope_name", "instrument_name", "instrument_type"],
    ].copy()
    diagnostics: dict[str, Any] = {
        "exact_matches": exact_matches,
        "normalized_matches": normalized_matches,
        "unmatched_external": unmatched_external,
        "missing_external": missing_external,
        "audit": audit,
        "inputs_used": {"telescopes", "instruments", "external_capabilities"},
    }
    return catalog, diagnostics


def snapshot_protected_files(capture_dir: Path) -> dict[str, tuple[int, int]]:
    """Snapshot protected file size/mtime without reading non-input data."""
    paths = [
        REPO_ROOT / "configs" / "telescopes" / "extraction.yaml",
        REPO_ROOT / "scripts" / "telescopes" / "01_fetch.py",
        REPO_ROOT / "scripts" / "telescopes" / "02_flatten.py",
        REPO_ROOT / "notebooks" / "telescopes" / "A_eda.ipynb",
        REPO_ROOT / "notebooks" / "telescopes" / "B_decisions.ipynb",
        EXTERNAL_PATH,
    ]
    paths.extend(
        sorted(path for path in (REPO_ROOT / "data" / "raw" / "telescopes" / "icare").rglob("*") if path.is_file())
    )
    paths.extend(sorted(path for path in capture_dir.iterdir() if path.is_file()))
    snapshot = {}
    for path in sorted(set(paths)):
        stat = path.stat()
        snapshot[str(path.relative_to(REPO_ROOT))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def validate_catalog(
    catalog: pd.DataFrame,
    persisted: pd.DataFrame,
    telescopes: pd.DataFrame,
    instruments: pd.DataFrame,
    external: pd.DataFrame,
    diagnostics: dict[str, Any],
    protected_unchanged: bool,
) -> list[tuple[str, bool, str]]:
    """Return the required twenty explicit catalog validation checks."""
    instrument_ids = set(instruments["id"])
    output_ids = set(catalog["instrument_id"])
    missing_external = diagnostics["missing_external"]
    audit = diagnostics["audit"].set_index("instrument_id")
    catalog_by_id = catalog.set_index("instrument_id")

    known = catalog["mlim_status"].eq("KNOWN")
    unknown = catalog["mlim_status"].eq("UNKNOWN")
    output_filters = catalog.sort_values("instrument_id")["filters"].fillna("<NA>").tolist()
    input_filters = instruments.sort_values("id")["filters"].fillna("<NA>").tolist()

    eligibility_matches_rule = catalog_by_id["followup_eligible"].equals(
        audit.loc[catalog_by_id.index, "expected_followup"].astype("boolean")
    )
    forbidden_fov = [column for column in catalog.columns if "fov" in column.casefold() or "region" in column.casefold()]
    dynamic_tokens = {"airmass", "morning", "evening", "weather", "availability", "observable", "is_night"}
    forbidden_dynamic = [
        column
        for column in catalog.columns
        if any(token in column.casefold() for token in dynamic_tokens)
    ]

    produced_schema = [(column, str(catalog[column].dtype)) for column in catalog.columns]
    persisted_schema = [(column, str(persisted[column].dtype)) for column in persisted.columns]

    checks = [
        ("ICARE instruments input = 95", len(instruments) == EXPECTED_INSTRUMENT_ROWS, str(len(instruments))),
        ("Output rows = ICARE instrument rows", len(catalog) == len(instruments), f"{len(catalog)}={len(instruments)}"),
        ("Expected output currently = 95 rows", len(catalog) == EXPECTED_INSTRUMENT_ROWS, str(len(catalog))),
        ("Unique instrument IDs in output", catalog["instrument_id"].is_unique, str(catalog["instrument_id"].nunique())),
        (
            "Unique (telescope_id, instrument_id) pairs",
            not catalog.duplicated(["telescope_id", "instrument_id"]).any(),
            str(catalog[["telescope_id", "instrument_id"]].drop_duplicates().shape[0]),
        ),
        ("All output instrument IDs originate from ICARE", output_ids <= instrument_ids, f"{len(output_ids)}/{len(instrument_ids)}"),
        (
            "All 89 external CSV rows matched ICARE",
            len(external) == EXPECTED_EXTERNAL_ROWS
            and diagnostics["normalized_matches"] == len(external)
            and diagnostics["unmatched_external"].empty,
            f"{diagnostics['normalized_matches']}/{len(external)}",
        ),
        (
            "No external-only row was introduced",
            output_ids == instrument_ids and len(catalog) == len(instruments),
            f"output IDs={len(output_ids)}",
        ),
        (
            "Six ICARE instruments currently have no external CSV row",
            len(missing_external) == EXPECTED_MISSING_EXTERNAL_ROWS,
            str(len(missing_external)),
        ),
        (
            "Missing external rows were retained",
            set(missing_external["instrument_id"]) <= output_ids,
            f"{len(set(missing_external['instrument_id']) & output_ids)}/{len(missing_external)}",
        ),
        (
            "mlim_status only contains KNOWN/UNKNOWN",
            set(catalog["mlim_status"].dropna()) <= {"KNOWN", "UNKNOWN"},
            str(sorted(catalog["mlim_status"].dropna().unique())),
        ),
        ("KNOWN implies numeric mlim_mag", bool(catalog.loc[known, "mlim_mag"].notna().all()), str(int(known.sum()))),
        ("UNKNOWN implies null mlim_mag", bool(catalog.loc[unknown, "mlim_mag"].isna().all()), str(int(unknown.sum()))),
        (
            "Missing Mlim did not automatically make a resource ineligible",
            eligibility_matches_rule and bool((unknown & catalog["followup_eligible"].eq(True)).any()),
            "eligibility follows CSV or native out-of-scope classification",
        ),
        ("ICARE filters were preserved", output_filters == input_filters, f"{len(output_filters)} rows"),
        ("No FoV field exists", not forbidden_fov, str(forbidden_fov)),
        ("No dynamic observability field exists", not forbidden_dynamic, str(forbidden_dynamic)),
        (
            "No observations or allocations were used",
            diagnostics["inputs_used"] == {"telescopes", "instruments", "external_capabilities"},
            str(sorted(diagnostics["inputs_used"])),
        ),
        (
            "Persisted parquet row count and schema match",
            len(persisted) == len(catalog) and persisted_schema == produced_schema,
            f"rows={len(persisted)}, columns={len(persisted.columns)}",
        ),
        ("No previous telescope files were modified", protected_unchanged, "before/after size/mtime maps agree"),
    ]
    return checks


def display_value(value: Any) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    if isinstance(value, bool):
        return str(value)
    return str(value)


def print_rows(frame: pd.DataFrame, columns: list[str]) -> None:
    if frame.empty:
        print("(none)")
        return
    for values in frame[columns].itertuples(index=False, name=None):
        print(" | ".join(display_value(value) for value in values))


def print_report(
    catalog: pd.DataFrame,
    telescopes: pd.DataFrame,
    instruments: pd.DataFrame,
    external: pd.DataFrame,
    diagnostics: dict[str, Any],
    checks: list[tuple[str, bool, str]],
) -> None:
    print("=" * 100)
    print("ICARE TELESCOPE RESOURCE CATALOG")
    print("=" * len("ICARE TELESCOPE RESOURCE CATALOG"))

    print("\n1. INPUTS\n")
    print(f"ICARE telescopes: {len(telescopes)}")
    print(f"ICARE instruments: {len(instruments)}")
    print(f"external capability rows: {len(external)}")

    print("\n2. JOIN\n")
    print(f"exact external matches: {diagnostics['exact_matches']}")
    print(f"normalized external matches: {diagnostics['normalized_matches']}")
    print(f"unmatched external rows: {len(diagnostics['unmatched_external'])}")
    print(f"ICARE instruments without external row: {len(diagnostics['missing_external'])}")
    print("\ntelescope | instrument | instrument_type")
    print_rows(
        diagnostics["missing_external"],
        ["telescope_name", "instrument_name", "instrument_type"],
    )

    print("\n3. OUTPUT\n")
    print(f"rows: {len(catalog)}")
    print(f"columns: {len(catalog.columns)} ({', '.join(catalog.columns)})")
    print(f"unique telescope IDs: {catalog['telescope_id'].nunique()}")
    print(f"unique instrument IDs: {catalog['instrument_id'].nunique()}")

    print("\n4. MLIM\n")
    known = catalog["mlim_status"].eq("KNOWN")
    unknown = catalog["mlim_status"].eq("UNKNOWN")
    print(f"KNOWN: {int(known.sum())}")
    print(f"UNKNOWN: {int(unknown.sum())}")
    print("\ntelescope | instrument | followup_eligible")
    print_rows(
        catalog.loc[unknown],
        ["telescope_name", "instrument_name", "followup_eligible"],
    )

    print("\n5. FOLLOW-UP ELIGIBILITY\n")
    eligible = catalog["followup_eligible"].eq(True)
    ineligible = catalog["followup_eligible"].eq(False)
    undetermined = catalog["followup_eligible"].isna()
    print(f"eligible: {int(eligible.sum())}")
    print(f"ineligible: {int(ineligible.sum())}")
    print(f"undetermined: {int(undetermined.sum())}")
    print("\ntelescope | instrument | reason")
    print_rows(
        catalog.loc[ineligible],
        ["telescope_name", "instrument_name", "restriction_note"],
    )

    print("\n6. VALIDATION\n")
    for index, (name, passed, detail) in enumerate(checks, start=1):
        print(f"{index:02d}. {'PASS' if passed else 'FAIL'} | {name} | {detail}")

    print("\n7. OUTPUT PATH\n")
    print(OUTPUT_PATH.relative_to(REPO_ROOT))
    print(f"\nOVERALL: {'PASS' if all(passed for _, passed, _ in checks) else 'FAIL'}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    capture_dir = find_latest_capture(INTERIM_ROOT)
    protected_before = snapshot_protected_files(capture_dir)

    telescopes, instruments = load_icare_tables(capture_dir)
    external = load_external_capabilities(EXTERNAL_PATH)
    catalog, diagnostics = build_resource_catalog(telescopes, instruments, external)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    catalog.to_parquet(
        OUTPUT_PATH,
        engine="pyarrow",
        compression="zstd",
        index=False,
    )
    persisted = pd.read_parquet(OUTPUT_PATH, engine="pyarrow")
    protected_after = snapshot_protected_files(capture_dir)

    checks = validate_catalog(
        catalog,
        persisted,
        telescopes,
        instruments,
        external,
        diagnostics,
        protected_before == protected_after,
    )
    print_report(catalog, telescopes, instruments, external, diagnostics, checks)

    failures = [name for name, passed, _ in checks if not passed]
    if failures:
        raise RuntimeError("Resource catalog validation failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
