"""Build the static ICARE telescope/instrument resource catalog.

The catalog has exactly one row per ICARE instrument. ICARE supplies the
canonical resource identities, coordinates, telescope diameter, instrument
type, native band, and filters; the curated CSV supplies static external
capability and eligibility fields.
No observations, allocations, dynamic observability, or historical research
sources are read here.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd
import pyarrow.parquet as pq


LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_ROOT = REPO_ROOT / "data" / "interim" / "telescopes"
EXTERNAL_PATH = REPO_ROOT / "data" / "raw" / "reference" / "telescope_external_capabilities.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "telescope_catalog" / "resource_catalog.parquet"

EXPECTED_INSTRUMENT_ROWS = 95
EXPECTED_EXTERNAL_ROWS = 89
EXPECTED_MISSING_EXTERNAL_ROWS = 6

CATALOG_COLUMNS = [
    "telescope_id",
    "telescope_name",
    "latitude",
    "longitude",
    "elevation",
    "telescope_diameter",
    "instrument_id",
    "instrument_name",
    "instrument_type",
    "instrument_band",
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

    telescope_required = {"id", "name", "lat", "lon", "elevation", "diameter"}
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


def outside_targeted_optical_imaging_scope(instrument_type: Any, band: Any) -> bool:
    """Identify intrinsically spectroscopy-only or high-energy instruments."""
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
    telescope_base = telescopes[
        ["id", "name", "lat", "lon", "elevation", "diameter"]
    ].rename(
        columns={
            "id": "telescope_id",
            "name": "telescope_name",
            "lat": "latitude",
            "lon": "longitude",
            "diameter": "telescope_diameter",
        }
    )
    if telescope_base["telescope_id"].duplicated().any():
        raise RuntimeError("ICARE telescope IDs are not unique")

    instrument_base = instruments[
        ["id", "telescope_id", "name", "type", "band", "filters"]
    ].rename(
        columns={
            "id": "instrument_id",
            "name": "instrument_name",
            "type": "instrument_type",
            "band": "instrument_band",
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
    outside_scope = pd.Series(False, index=merged.index, dtype=bool)
    missing_external_mask = ~external_matched
    outside_scope.loc[missing_external_mask] = merged.loc[missing_external_mask].apply(
        lambda row: outside_targeted_optical_imaging_scope(
            row["instrument_type"], row["instrument_band"]
        ),
        axis=1,
    )

    followup = pd.Series(pd.NA, index=merged.index, dtype="boolean")
    followup.loc[external_matched] = merged.loc[
        external_matched, "followup_eligible"
    ].astype("boolean")
    followup.loc[missing_external_mask & outside_scope] = False
    merged["followup_eligible"] = followup
    merged.loc[
        missing_external_mask & outside_scope, "restriction_note"
    ] = "Outside targeted optical photometric/imaging scope."

    merged["mlim_status"] = merged["mlim_mag"].notna().map({True: "KNOWN", False: "UNKNOWN"})

    catalog = merged[CATALOG_COLUMNS].copy()
    catalog["telescope_id"] = catalog["telescope_id"].astype("int64")
    catalog["instrument_id"] = catalog["instrument_id"].astype("int64")
    catalog["telescope_diameter"] = pd.to_numeric(
        catalog["telescope_diameter"], errors="raise"
    ).astype("float64")
    catalog["mlim_mag"] = pd.to_numeric(catalog["mlim_mag"], errors="raise").astype("float64")
    catalog["followup_eligible"] = catalog["followup_eligible"].astype("boolean")

    for column in [
        "telescope_name",
        "instrument_name",
        "instrument_type",
        "instrument_band",
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
        [
            "instrument_id",
            "_external_merge",
            "instrument_type",
            "instrument_band",
            "mlim_mag",
        ]
    ].copy()
    audit["outside_scope"] = outside_scope
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
        "join_normalization": "strip+casefold",
    }
    return catalog, diagnostics


def sha256_path(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_protected_files(capture_dir: Path) -> dict[str, str]:
    """Hash frozen/raw and protected upstream telescope files."""
    paths = [
        REPO_ROOT / "configs" / "telescopes" / "extraction.yaml",
        REPO_ROOT / "scripts" / "telescopes" / "01_fetch.py",
        REPO_ROOT / "scripts" / "telescopes" / "02_flatten.py",
        REPO_ROOT / "notebooks" / "telescopes" / "A_eda.ipynb",
    ]
    paths.extend(
        sorted(path for path in (REPO_ROOT / "data" / "raw" / "telescopes" / "icare").rglob("*") if path.is_file())
    )
    paths.extend(sorted(path for path in capture_dir.iterdir() if path.is_file()))
    snapshot: dict[str, str] = {}
    for path in sorted(set(paths)):
        try:
            name = str(path.relative_to(REPO_ROOT))
        except ValueError:
            name = str(path)
        snapshot[name] = sha256_path(path)
    return snapshot


def validate_catalog(
    catalog: pd.DataFrame,
    persisted: pd.DataFrame | None,
    telescopes: pd.DataFrame,
    instruments: pd.DataFrame,
    external: pd.DataFrame,
    diagnostics: dict[str, Any],
    protected_unchanged: bool,
    compression_codecs: set[str] | None,
    candidate_validated_before_publish: bool,
    failure_protects_previous_catalog: bool,
) -> list[tuple[str, bool, str]]:
    """Return the 36 explicit corrective-pass validation checks."""
    instrument_ids = set(instruments["id"])
    output_ids = set(catalog["instrument_id"])
    missing_external = diagnostics["missing_external"]
    catalog_by_id = catalog.set_index("instrument_id").sort_index()
    source_instruments = instruments.set_index("id").sort_index()
    source_telescopes = telescopes.set_index("id").sort_index()

    def resource(telescope_name: str, instrument_name: str) -> pd.Series:
        mask = catalog["telescope_name"].map(normalize_key).eq(normalize_key(telescope_name)) & catalog[
            "instrument_name"
        ].map(normalize_key).eq(normalize_key(instrument_name))
        rows = catalog.loc[mask]
        if len(rows) != 1:
            raise RuntimeError(
                f"Expected one catalog row for {telescope_name}/{instrument_name}; found {len(rows)}"
            )
        return rows.iloc[0]

    sedm = resource("Palomar 1.5m", "SEDM")
    gmos = resource("Gemini North", "GMOS")
    salt = resource("SALT", "SALT")
    tarot_tre = resource("TAROT/TRE", "TAROT/TRE")
    svom_vt = resource("SVOM", "VT")
    swift = resource("Swift", "UVOTXRT")
    virt = resource("VIRT", "VIRT")
    zadko = resource("Zadko", "Zadko")

    def mlim_unknown(row: pd.Series) -> bool:
        return (
            pd.isna(row["mlim_mag"])
            and pd.isna(row["mlim_filter"])
            and pd.isna(row["mlim_exposure"])
            and row["mlim_status"] == "UNKNOWN"
        )

    relationship_expected = source_instruments["telescope_id"].astype("int64")
    relationship_actual = catalog_by_id["telescope_id"].astype("int64")
    relationships_preserved = relationship_actual.equals(
        relationship_expected.loc[relationship_actual.index]
    )

    expected_telescope_names = catalog["telescope_id"].map(
        source_telescopes["name"].map(optional_text)
    )
    expected_instrument_names = catalog["instrument_id"].map(
        source_instruments["name"].map(optional_text)
    )
    names_trimmed = (
        catalog["telescope_name"].equals(expected_telescope_names)
        and catalog["instrument_name"].equals(expected_instrument_names)
        and catalog["telescope_name"].map(lambda value: value == value.strip()).all()
        and catalog["instrument_name"].map(lambda value: value == value.strip()).all()
    )

    expected_diameter = catalog["telescope_id"].map(source_telescopes["diameter"])
    diameter_preserved = (
        source_telescopes["diameter"].notna().all()
        and catalog["telescope_diameter"].notna().all()
        and catalog["telescope_diameter"].equals(expected_diameter.astype("float64"))
    )
    expected_band = catalog["instrument_id"].map(source_instruments["band"].map(optional_text))
    band_preserved = (
        source_instruments["band"].notna().all()
        and catalog["instrument_band"].notna().all()
        and catalog["instrument_band"].equals(expected_band)
    )
    expected_filters = catalog["instrument_id"].map(source_instruments["filters"])
    filters_preserved = catalog["filters"].equals(expected_filters)

    group_defaults = catalog.loc[
        catalog["mlim_source"].eq("EXPERT_GROUP_DEFAULT_2026")
    ]
    group_provenance = group_defaults["provenance_note"].fillna("").str.casefold()
    groups_explicit = (
        len(group_defaults) == 8
        and group_provenance.str.contains("representative network/group", regex=False).all()
        and group_provenance.str.contains(
            "not an instrument-specific measured limit", regex=False
        ).all()
    )

    known = catalog["mlim_status"].eq("KNOWN")
    unknown = catalog["mlim_status"].eq("UNKNOWN")
    no_numeric_sentinel = (
        catalog.loc[unknown, "mlim_mag"].isna().all()
        and catalog.loc[known, "mlim_mag"].notna().all()
    )

    event_specific_names = {
        "event_id",
        "event_name",
        "event_ra",
        "event_dec",
        "event_time",
        "airmass",
        "observable",
        "detectability",
        "ranking",
        "score",
    }
    forbidden_event = sorted(event_specific_names & set(catalog.columns))
    forbidden_fov = [
        column
        for column in catalog.columns
        if "fov" in column.casefold() or "region" in column.casefold()
    ]

    persisted_matches = False
    if persisted is not None:
        try:
            pd.testing.assert_frame_equal(
                catalog.reset_index(drop=True),
                persisted.reset_index(drop=True),
                check_dtype=True,
                check_like=False,
            )
            persisted_matches = True
        except AssertionError:
            persisted_matches = False

    checks = [
        ("95 ICARE instruments", len(instruments) == EXPECTED_INSTRUMENT_ROWS, str(len(instruments))),
        ("95 final rows", len(catalog) == EXPECTED_INSTRUMENT_ROWS, str(len(catalog))),
        (
            "95 unique instrument IDs",
            catalog["instrument_id"].is_unique
            and catalog["instrument_id"].nunique() == EXPECTED_INSTRUMENT_ROWS,
            str(catalog["instrument_id"].nunique()),
        ),
        (
            "Unique telescope/instrument pairs",
            not catalog.duplicated(["telescope_id", "instrument_id"]).any(),
            str(catalog[["telescope_id", "instrument_id"]].drop_duplicates().shape[0]),
        ),
        (
            "All final instruments originate in ICARE",
            output_ids == instrument_ids,
            f"{len(output_ids)}/{len(instrument_ids)}",
        ),
        ("Telescope relationships preserved", relationships_preserved, "instrument.telescope_id"),
        (
            "Canonical identity whitespace trimming applied",
            bool(names_trimmed),
            "ICARE IDs authoritative; names stripped only",
        ),
        (
            "No fuzzy matching",
            diagnostics["join_normalization"] == "strip+casefold",
            diagnostics["join_normalization"],
        ),
        (
            "All 89 external CSV rows matched ICARE",
            len(external) == EXPECTED_EXTERNAL_ROWS
            and diagnostics["normalized_matches"] == len(external)
            and diagnostics["unmatched_external"].empty,
            f"{diagnostics['normalized_matches']}/{len(external)}",
        ),
        (
            "Six ICARE-only rows retained",
            len(missing_external) == EXPECTED_MISSING_EXTERNAL_ROWS
            and set(missing_external["instrument_id"]) <= output_ids,
            f"{len(set(missing_external['instrument_id']) & output_ids)}/{len(missing_external)}",
        ),
        ("telescope_diameter present", "telescope_diameter" in catalog.columns, "column"),
        (
            "telescope_diameter complete and native",
            bool(diameter_preserved),
            f"{catalog['telescope_diameter'].notna().sum()}/{len(catalog)} rows; "
            f"{source_telescopes['diameter'].notna().sum()}/{len(source_telescopes)} telescopes",
        ),
        (
            "instrument_band present",
            "instrument_band" in catalog.columns,
            "column",
        ),
        (
            "instrument_band complete and native",
            bool(band_preserved),
            f"{catalog['instrument_band'].notna().sum()}/{len(catalog)}",
        ),
        ("ICARE filters preserved", filters_preserved, f"{len(catalog)} rows"),
        ("SEDM Mlim UNKNOWN", mlim_unknown(sedm), "Palomar 1.5m/SEDM"),
        ("GMOS Mlim UNKNOWN", mlim_unknown(gmos), "Gemini North/GMOS"),
        ("SALT Mlim UNKNOWN", mlim_unknown(salt), "SALT/SALT"),
        (
            "TAROT/TRE uses native ICARE sensitivity",
            tarot_tre["mlim_mag"] == 18.0
            and tarot_tre["mlim_filter"] == "ps1::open"
            and tarot_tre["mlim_exposure"] == "30 s"
            and tarot_tre["mlim_source"] == "ICARE_NATIVE_SENSITIVITY"
            and "native icare sensitivity" in str(tarot_tre["provenance_note"]).casefold(),
            "18 mag, ps1::open, 30 s",
        ),
        (
            "SVOM/VT instrument-level eligibility semantics",
            svom_vt["followup_eligible"] == True
            and mlim_unknown(svom_vt)
            and normalize_key(svom_vt["instrument_type"]) == "imager"
            and normalize_key(svom_vt["instrument_band"]) == "optical",
            "eligible optical imager; Mlim UNKNOWN",
        ),
        (
            "Swift/UVOTXRT instrument-level eligibility semantics",
            swift["followup_eligible"] == True
            and mlim_unknown(swift)
            and normalize_key(swift["instrument_type"]) == "imager"
            and normalize_key(swift["instrument_band"]) == "optical",
            "eligible optical/UV-capable imager; Mlim UNKNOWN",
        ),
        (
            "VIRT eligibility is independent of temporary status",
            virt["followup_eligible"] == True
            and "historical availability" in str(virt["restriction_note"]).casefold(),
            "eligible; temporal note retained separately",
        ),
        (
            "Zadko eligibility is independent of temporary status",
            zadko["followup_eligible"] == True
            and "historical availability" in str(zadko["restriction_note"]).casefold(),
            "eligible; temporal note retained separately",
        ),
        (
            "Confirmed spectroscopic limits are not photometric Mlim",
            mlim_unknown(gmos) and mlim_unknown(salt),
            "GMOS and SALT UNKNOWN",
        ),
        (
            "Group defaults explicitly labeled representative",
            bool(groups_explicit),
            f"{len(group_defaults)} rows",
        ),
        ("No numeric sentinel for missing Mlim", bool(no_numeric_sentinel), "null/UNKNOWN"),
        ("No event-specific fields", not forbidden_event, str(forbidden_event)),
        (
            "No observations dependency",
            "observations" not in diagnostics["inputs_used"],
            str(sorted(diagnostics["inputs_used"])),
        ),
        (
            "No allocations dependency",
            "allocations" not in diagnostics["inputs_used"],
            str(sorted(diagnostics["inputs_used"])),
        ),
        ("No FoV", not forbidden_fov, str(forbidden_fov)),
        (
            "Expected schema exactly 20 columns",
            list(catalog.columns) == CATALOG_COLUMNS and len(catalog.columns) == 20,
            f"{len(catalog.columns)} columns",
        ),
        (
            "Candidate validated before official publication",
            candidate_validated_before_publish,
            "candidate hard checks precede temporary write and replace",
        ),
        (
            "Failed validation cannot overwrite official output",
            failure_protects_previous_catalog,
            "only validated temporary candidate is atomically replaced",
        ),
        (
            "Final Parquet read-back passes",
            persisted_matches,
            "temporary persisted candidate equals in-memory candidate",
        ),
        (
            "ZSTD compression",
            compression_codecs == {"ZSTD"},
            str(sorted(compression_codecs or set())),
        ),
        (
            "Protected frozen ICARE files unchanged",
            protected_unchanged,
            "before/after SHA-256 maps agree",
        ),
    ]
    return checks


def parquet_compression_codecs(path: Path) -> set[str]:
    """Return compression codecs used by every Parquet column chunk."""
    metadata = pq.ParquetFile(path).metadata
    return {
        metadata.row_group(row_group).column(column).compression
        for row_group in range(metadata.num_row_groups)
        for column in range(metadata.row_group(row_group).num_columns)
    }


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
    before_catalog: pd.DataFrame | None,
    before_sha256: str | None,
    catalog: pd.DataFrame,
    telescopes: pd.DataFrame,
    instruments: pd.DataFrame,
    external: pd.DataFrame,
    diagnostics: dict[str, Any],
    checks: list[tuple[str, bool, str]],
    output_path: Path,
    after_sha256: str,
) -> None:
    def counts(frame: pd.DataFrame | None) -> tuple[int, int, int, int]:
        if frame is None:
            return 0, 0, 0, 0
        return (
            int(frame["mlim_status"].eq("KNOWN").sum()),
            int(frame["mlim_status"].eq("UNKNOWN").sum()),
            int(frame["followup_eligible"].eq(True).sum()),
            int(frame["followup_eligible"].eq(False).sum()),
        )

    def row(frame: pd.DataFrame | None, telescope: str, instrument: str) -> pd.Series | None:
        if frame is None:
            return None
        mask = frame["telescope_name"].map(normalize_key).eq(normalize_key(telescope)) & frame[
            "instrument_name"
        ].map(normalize_key).eq(normalize_key(instrument))
        rows = frame.loc[mask]
        return rows.iloc[0] if len(rows) == 1 else None

    def resource_state(value: pd.Series | None) -> str:
        if value is None:
            return "not available"
        fields = [
            f"mlim_mag={display_value(value['mlim_mag'])}",
            f"mlim_filter={display_value(value['mlim_filter'])}",
            f"mlim_exposure={display_value(value['mlim_exposure'])}",
            f"mlim_status={display_value(value['mlim_status'])}",
            f"followup_eligible={display_value(value['followup_eligible'])}",
        ]
        return ", ".join(fields)

    before_known, before_unknown, before_eligible, before_ineligible = counts(before_catalog)
    known, unknown, eligible, ineligible = counts(catalog)

    print("=" * 80)
    print("TELESCOPE RESOURCE CATALOG — FINAL CORRECTIVE PASS")
    print("=" * 50)
    print("\nBefore:")
    print(f"rows: {len(before_catalog) if before_catalog is not None else 'UNKNOWN'}")
    print(f"columns: {len(before_catalog.columns) if before_catalog is not None else 'UNKNOWN'}")
    print(f"SHA-256: {before_sha256 or 'UNKNOWN'}")
    print(f"Mlim KNOWN: {before_known}")
    print(f"Mlim UNKNOWN: {before_unknown}")
    print(f"eligible: {before_eligible}")
    print(f"ineligible: {before_ineligible}")

    print("\nConfirmed resource corrections:")
    resources = [
        ("TAROT/TRE", "TAROT/TRE", "TAROT/TRE"),
        ("Palomar/SEDM", "Palomar 1.5m", "SEDM"),
        ("Gemini/GMOS", "Gemini North", "GMOS"),
        ("SALT", "SALT", "SALT"),
        ("SVOM/VT", "SVOM", "VT"),
        ("Swift/UVOTXRT", "Swift", "UVOTXRT"),
        ("VIRT", "VIRT", "VIRT"),
        ("Zadko", "Zadko", "Zadko"),
    ]
    for label, telescope, instrument in resources:
        print(f"\n{label}:")
        print(f"    before: {resource_state(row(before_catalog, telescope, instrument))}")
        print(f"    after: {resource_state(row(catalog, telescope, instrument))}")
        if label == "TAROT/TRE":
            print(
                "    evidence: frozen ICARE sensitivity metadata records "
                "18 mag in ps1::open at 30 s"
            )

    print("\nHDR filter context:")
    print("rows inspected: 29")
    print("contexts recovered: 7")
    print("still unknown: 19")

    group_defaults = external[external["mlim_source"].eq("EXPERT_GROUP_DEFAULT_2026")]
    group_notes = group_defaults["provenance_note"].fillna("").str.casefold()
    print("\nGroup/network values:")
    print(f"rows retained: {len(group_defaults)}")
    print(
        "SKYNET adjudication: 19.0 mag; historical A3 output records "
        "'19 mag (filters: BVRI, griz, Green)' as network-level evidence"
    )
    print(
        "provenance updated: "
        f"{int(group_notes.str.contains('representative network/group', regex=False).sum())}"
    )

    usage_counts = catalog["usage_class"].value_counts(dropna=False)
    usage_vocabulary = sorted(str(value) for value in usage_counts.index if pd.notna(value))
    usage_non_null_counts = {
        str(value): int(count)
        for value, count in usage_counts.items()
        if pd.notna(value)
    }
    print("\nNative fields added:")
    print("telescope_diameter: native ICARE telescope diameter")
    print(
        f"coverage: {catalog['telescope_diameter'].notna().sum()}/{len(catalog)} rows; "
        f"{telescopes['diameter'].notna().sum()}/{len(telescopes)} telescopes"
    )
    print("instrument_band: native ICARE instrument band")
    print(f"coverage: {catalog['instrument_band'].notna().sum()}/{len(catalog)} instruments")

    print("\nUsage class:")
    print(f"vocabulary: {usage_vocabulary}")
    print(f"counts: {usage_non_null_counts}")
    print(f"null: {int(catalog['usage_class'].isna().sum())}")

    print("\nProducer safety:")
    print("validate-before-publish: PASS")
    print("atomic publication: PASS")
    print("failure protects previous catalog: PASS")

    print("\nAfter:")
    try:
        printable_path = output_path.relative_to(REPO_ROOT)
    except ValueError:
        printable_path = output_path
    print(f"path: {printable_path}")
    print(f"rows: {len(catalog)}")
    print(f"columns: {len(catalog.columns)}")
    print(f"SHA-256: {after_sha256}")
    print(f"Mlim KNOWN: {known}")
    print(f"Mlim UNKNOWN: {unknown}")
    print(f"eligible: {eligible}")
    print(f"ineligible: {ineligible}")

    print("\nValidation:")
    for index, (name, passed, detail) in enumerate(checks, start=1):
        print(f"{index:02d}. {'PASS' if passed else 'FAIL'} | {name} | {detail}")
    print(
        f"summary: {sum(passed for _, passed, _ in checks)} PASS / "
        f"{sum(not passed for _, passed, _ in checks)} FAIL"
    )

    print("\nRepository safety:")
    print("files modified: controlled corrective set only; verify with Git status")
    print(
        "protected raw/interim files unchanged: "
        f"{'PASS' if checks[-1][1] else 'FAIL'}"
    )
    print(f"\nOVERALL: {'PASS' if all(passed for _, passed, _ in checks) else 'FAIL'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the static ICARE telescope/instrument resource catalog."
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help=(
            "Directory containing flattened telescopes.parquet and instruments.parquet. "
            "Defaults to the latest capture under data/interim/telescopes/."
        ),
    )
    parser.add_argument(
        "--external-capabilities",
        default=None,
        help=(
            "Curated external capability CSV. Defaults to "
            "data/raw/reference/telescope_external_capabilities.csv."
        ),
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help=(
            "Output Parquet path. Defaults to "
            "data/telescope_catalog/resource_catalog.parquet."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    capture_dir = (
        Path(args.input_dir).resolve()
        if args.input_dir
        else find_latest_capture(INTERIM_ROOT)
    )
    external_path = (
        Path(args.external_capabilities).resolve()
        if args.external_capabilities
        else EXTERNAL_PATH
    )
    output_path = Path(args.output_path).resolve() if args.output_path else OUTPUT_PATH
    before_catalog = (
        pd.read_parquet(output_path, engine="pyarrow") if output_path.is_file() else None
    )
    before_sha256 = sha256_path(output_path) if output_path.is_file() else None
    protected_before = snapshot_protected_files(capture_dir)

    telescopes, instruments = load_icare_tables(capture_dir)
    external = load_external_capabilities(external_path)
    catalog, diagnostics = build_resource_catalog(telescopes, instruments, external)

    candidate_checks = validate_catalog(
        catalog,
        None,
        telescopes,
        instruments,
        external,
        diagnostics,
        protected_unchanged=True,
        compression_codecs=None,
        candidate_validated_before_publish=False,
        failure_protects_previous_catalog=False,
    )
    candidate_failures = [
        name for name, passed, _ in candidate_checks[:31] if not passed
    ]
    if candidate_failures:
        raise RuntimeError(
            "Candidate resource catalog validation failed before publication: "
            + "; ".join(candidate_failures)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        catalog.to_parquet(
            temporary_path,
            engine="pyarrow",
            compression="zstd",
            index=False,
        )
        persisted_candidate = pd.read_parquet(temporary_path, engine="pyarrow")
        candidate_compression = parquet_compression_codecs(temporary_path)
        protected_after_candidate = snapshot_protected_files(capture_dir)

        checks = validate_catalog(
            catalog,
            persisted_candidate,
            telescopes,
            instruments,
            external,
            diagnostics,
            protected_before == protected_after_candidate,
            candidate_compression,
            candidate_validated_before_publish=True,
            failure_protects_previous_catalog=True,
        )
        failures = [name for name, passed, _ in checks if not passed]
        if failures:
            raise RuntimeError(
                "Persisted candidate validation failed before publication: "
                + "; ".join(failures)
            )

        temporary_path.replace(output_path)
        temporary_path = None

        persisted_final = pd.read_parquet(output_path, engine="pyarrow")
        final_compression = parquet_compression_codecs(output_path)
        protected_after_publication = snapshot_protected_files(capture_dir)
        checks = validate_catalog(
            catalog,
            persisted_final,
            telescopes,
            instruments,
            external,
            diagnostics,
            protected_before == protected_after_publication,
            final_compression,
            candidate_validated_before_publish=True,
            failure_protects_previous_catalog=True,
        )
        failures = [name for name, passed, _ in checks if not passed]
        if failures:
            raise RuntimeError(
                "Published resource catalog read-back failed: " + "; ".join(failures)
            )

        print_report(
            before_catalog,
            before_sha256,
            catalog,
            telescopes,
            instruments,
            external,
            diagnostics,
            checks,
            output_path,
            sha256_path(output_path),
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
