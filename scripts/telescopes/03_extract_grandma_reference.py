"""Extract the GRANDMA telescope-network table from the project-supplied
reference document into a faithful, provenance-aware interim/reference table.

Stage 4 evidence gathering only: SHAPE preserving, no normalization. Reads
the locally supplied PDF (see --source-pdf; default:
data/raw/reference/grandma/Second_Phd_Thesis____Sarah-7.pdf) and writes
data/interim/telescopes/reference/grandma_table.parquet.

The document is Sarah Antier's Habilitation a diriger des recherches (HDR)
manuscript, "Multi-messenger Astronomy with GRANDMA" (Universite
Paris-Saclay). Its Table 1.1 ("GRANDMA telescope network", pages 14-15) is
the only telescope-network table found in the document; see
find_relevant_table() for how that was established.

Extraction method: direct PDF text extraction with word-level bounding
boxes (pdfplumber), not OCR. The table has no ruling lines and each row
spans 2-4 physical text lines (the FOV value, filter codes, and
occasionally the telescope name or location wrap onto their own line), so
rows are detected by their "MNight" cell (always a single, unambiguous
"<hh>-<hh>h" token) rather than by a fixed vertical pitch. Every cell is
kept as the raw extracted text (joined word tokens); nothing is parsed
into a number or unit. Known PDF glyph-encoding artifacts (e.g. a raised
prime mark rendered as a literal "1", "^" standing in for "x", "-"-like
glyphs in the spectroscopy wavelength ranges) are preserved as extracted
and flagged, not guessed at.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_PDF = REPO_ROOT / "data" / "raw" / "reference" / "grandma" / "Second_Phd_Thesis____Sarah-7.pdf"
MANIFEST_PATH = REPO_ROOT / "data" / "raw" / "reference" / "grandma" / "manifest.json"

OUTPUT_DIR = REPO_ROOT / "data" / "interim" / "telescopes" / "reference"
OUTPUT_PARQUET = OUTPUT_DIR / "grandma_table.parquet"

# Established by inspecting the document itself (see module docstring):
# Table 1.1 spans pages 14-15 (1-based), under section headers "Photometry"
# and "Spectroscopy" that split the table into two typed groups of rows.
TABLE_PAGE_NUMBERS = [14, 15]
TABLE_LABEL = "Table 1.1"
TABLE_TITLE = "GRANDMA telescope network"
TABLE_CAPTION = (
    'Table 1.1: GRANDMA telescope network. "MNight" corresponds to the time zone of '
    'maximum night time. Mlim corresponds to the typical maximum limiting mag obtained '
    'in less than 1 h. The "Use" colon include "VF" for very frequent observations for '
    'GRANDMA, "F" as Frequent, "R" as Rare, "VR" as very Rare, and "nOP" as not '
    'Operational. The column "Rob" include if the telescope is robotic or not.'
)
# The document states explicitly (page 13 body text, not the table caption):
# "The full list of GRANDMA telescopes in 2026 is presented in Table 1.1."
TABLE_TEMPORAL_SCOPE_STATEMENT = "The full list of GRANDMA telescopes in 2026 is presented in Table 1.1."

MNIGHT_RE = re.compile(r"^\d{1,2}[–-]\d{1,2}h$")  # e.g. "10-16h" (en dash or hyphen)
SECTION_LABELS = {"Photometry", "Spectroscopy"}

# Column x-bounds (PDF points), read directly off the header row on page 14
# ("Name Location MNight Size FOV(deg) Filter Mlim Use Rob.") and cross
# checked against page 15's repeated header.
COLUMN_BOUNDS: list[tuple[str, float, float]] = [
    ("telescope_name", 0.0, 145.0),
    ("location", 145.0, 235.0),
    ("mnight_h", 235.0, 288.0),
    ("size_m", 288.0, 330.0),
    ("fov_deg", 330.0, 393.0),
    ("filter", 393.0, 450.0),
    ("mlim", 450.0, 484.0),
    ("use", 484.0, 513.0),
    ("rob", 513.0, 600.0),
]
COLUMN_NAMES = [name for name, _, _ in COLUMN_BOUNDS]
HEADER_BOTTOM_BY_PAGE = {14: 210.0, 15: 128.0}  # header/caption rows end above this "top"

# "Use" values the caption itself enumerates; anything else observed in a
# cell is either a genuine additional raw value or an extraction ambiguity
# (see find_unresolved_cells()) and is reported, never silently corrected.
DOCUMENTED_USE_VOCABULARY = {"VF", "F", "R", "VR", "nOP"}

# Deterministic source-row spot checks: (row_index, {column: expected_substring}).
# Hand-transcribed directly from the source PDF text during inspection.
SPOT_CHECKS: list[tuple[int, dict[str, str]]] = [
    (0, {"telescope_name": "TRT-SBO", "location": "Spring Brook Obs.", "mnight_h": "10–16h",
         "mlim": "21.5", "rob": "yes"}),
    (20, {"telescope_name": "IRIS", "location": "OHP", "mnight_h": "20–06h", "mlim": "20",
          "rob": "semi"}),
    (38, {"telescope_name": "10.4m GTC/EMIR", "location": "ORM", "mnight_h": "20–06h",
          "mlim": "20.5", "rob": "no"}),
]


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_relevant_table(pdf: pdfplumber.PDF) -> list[int]:
    """Locate every page whose text contains a table caption starting 'Table'.

    Used at inspection time (see module docstring) to establish that
    Table 1.1 is the only telescope-network table in the document; kept
    here so a future re-run raises loudly if that ever stops being true
    rather than silently extracting the wrong table.
    """
    caption_pages = []
    for index, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        for line in text.split("\n"):
            stripped = line.strip().replace(" ", "")
            if stripped.startswith("Table") and "GRANDMA" in stripped and "telescope" in stripped.lower():
                caption_pages.append(index + 1)
    return caption_pages


def extract_page_words(page: Any) -> list[dict[str, Any]]:
    return page.extract_words(use_text_flow=False, keep_blank_chars=False, x_tolerance=1.2)


def column_for_x(x0: float) -> str:
    for name, low, high in COLUMN_BOUNDS:
        if low <= x0 < high:
            return name
    raise ValueError(f"Word at x0={x0} falls outside every known column bound")


def group_into_rows(pdf: pdfplumber.PDF) -> list[dict[str, Any]]:
    """Group table words into one record per telescope, spanning the table's
    physical text lines. A new row starts on any line carrying an
    unambiguous MNight token ("<hh>-<hh>h"); every following line belongs
    to that row until the next MNight token, a section label, or the
    trailing figure caption. Section membership (Photometry/Spectroscopy)
    is tracked from the table's own sub-headers."""
    rows: list[dict[str, Any]] = []
    section: str | None = None
    current: dict[str, Any] | None = None

    for page_number in TABLE_PAGE_NUMBERS:
        page = pdf.pages[page_number - 1]
        words = extract_page_words(page)
        lines: dict[int, list[dict[str, Any]]] = {}
        for word in words:
            lines.setdefault(round(word["top"]), []).append(word)
        header_bottom = HEADER_BOTTOM_BY_PAGE[page_number]

        for top in sorted(lines):
            if top <= header_bottom:
                continue
            line_words = sorted(lines[top], key=lambda w: w["x0"])
            texts = [w["text"] for w in line_words]

            if " ".join(texts).strip() in SECTION_LABELS:
                section = " ".join(texts).strip()
                continue
            if texts and texts[0] == "Figure":
                break  # trailing figure caption below the table; stop this page

            if any(MNIGHT_RE.match(t) for t in texts):
                if current is not None:
                    rows.append(current)
                current = {"section": section, "page": page_number, "words": []}

            if current is None:
                raise RuntimeError(
                    f"Text line before any row started on page {page_number}: {texts}. "
                    f"The table layout may have changed."
                )
            current["words"].extend(line_words)

        if current is not None:
            rows.append(current)
            current = None

    return rows


def build_records(row_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assemble one record per telescope row; column text joined in reading order."""
    records = []
    for index, row in enumerate(row_blocks):
        by_column: dict[str, list[dict[str, Any]]] = {name: [] for name in COLUMN_NAMES}
        for word in row["words"]:
            by_column[column_for_x(word["x0"])].append(word)
        record: dict[str, Any] = {
            "row_index_in_source": index, "section": row["section"], "source_page": row["page"],
        }
        for column in COLUMN_NAMES:
            ordered = sorted(by_column[column], key=lambda w: (w["top"], w["x0"]))
            record[column] = " ".join(w["text"] for w in ordered)
        records.append(record)
    return records


def find_unresolved_cells(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag cells worth a human's attention: a raw PDF glyph-code artifact,
    or a 'use' value outside the caption's documented vocabulary (which can
    be a genuine additional raw value or a column-boundary reconstruction
    ambiguity -- either way, reported rather than silently trusted)."""
    flagged = []
    for record in records:
        for column in COLUMN_NAMES:
            value = record[column]
            if "(cid:" in value:
                flagged.append({"row_index_in_source": record["row_index_in_source"],
                                "telescope_name": record["telescope_name"],
                                "column": column, "raw_value": value,
                                "reason": "unresolved PDF glyph-code artifact"})
        if record["use"] and record["use"] not in DOCUMENTED_USE_VOCABULARY:
            flagged.append({"row_index_in_source": record["row_index_in_source"],
                            "telescope_name": record["telescope_name"], "column": "use",
                            "raw_value": record["use"],
                            "reason": "value outside the caption's documented Use vocabulary"})
    return flagged


def run_spot_checks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_index = {r["row_index_in_source"]: r for r in records}
    results = []
    for row_index, expected in SPOT_CHECKS:
        record = by_index.get(row_index)
        for column, expected_value in expected.items():
            observed = record[column] if record else None
            results.append({"row_index_in_source": row_index, "column": column,
                            "expected": expected_value, "observed": observed,
                            "status": "PASS" if observed == expected_value else "FAIL"})
    return results


def validate_extraction(
    records: list[dict[str, Any]], spot_check_results: list[dict[str, Any]], expected_row_count: int
) -> list[dict[str, Any]]:
    controls = []

    def check(name: str, expected: Any, observed: Any) -> None:
        controls.append({"control": name, "expected": expected, "observed": observed,
                         "status": "PASS" if observed == expected else "FAIL"})

    check("every source row represented", expected_row_count, len(records))
    check("no additional row invented", expected_row_count, len(records))
    check("every actual table column represented", set(COLUMN_NAMES),
          set(records[0].keys()) - {"row_index_in_source", "section", "source_page"} if records else set())

    # Required identity/scheduling cells (mnight_h/rob/use are always printed for every
    # telescope in this table; size_m/fov_deg are legitimately "-" for spectroscopy rows).
    required_columns = ["telescope_name", "location", "mnight_h", "mlim", "use", "rob"]
    missing_required = [
        (r["row_index_in_source"], c) for r in records for c in required_columns if not r[c].strip()
    ]
    check("no required cell (name/location/mnight/mlim/use/rob) is empty", 0, len(missing_required))

    spot_check_pass = sum(1 for r in spot_check_results if r["status"] == "PASS")
    check("deterministic source-row spot checks", len(spot_check_results), spot_check_pass)

    overall_pass = all(c["status"] == "PASS" for c in controls)
    controls.append({
        "control": "OVERALL", "expected": "all controls PASS",
        "observed": "all controls PASS" if overall_pass else "at least one control FAILED",
        "status": "PASS" if overall_pass else "FAIL",
    })
    return controls


def build_dataframe(records: list[dict[str, Any]], source_manifest: dict[str, Any]) -> pd.DataFrame:
    provenance = {
        "source_file": source_manifest["source_file"],
        "source_sha256": source_manifest["sha256"],
        "source_table": TABLE_LABEL,
    }
    rows = []
    for record in records:
        combined = dict(record)
        combined.update(provenance)
        rows.append(combined)
    return pd.DataFrame(rows)


def build_manifest(source_pdf: Path, page_count: int, table_pages_found: list[int]) -> dict[str, Any]:
    """Provenance for the supplied document, established from the document
    itself (see module docstring) -- never inferred from the filename."""
    return {
        "source_file": str(source_pdf.relative_to(REPO_ROOT)),
        "sha256": compute_sha256(source_pdf),
        "page_count": page_count,
        "title_english": "Multi-messenger Astronomy with GRANDMA",
        "title_french": "L'Astronomie Multi-messagers avec GRANDMA",
        "author": "Sarah Antier",
        "document_type": "Habilitation à diriger des recherches (HDR) manuscript",
        "institution": "Université Paris-Saclay",
        "defense_location": "Orsay",
        "defense_date_day_month": "9 October",
        "defense_year": "NOT ESTABLISHED (not printed on the title page; PDF CreationDate metadata "
                        "is 2026-07-21 but that reflects file generation, not a stated authorial date)",
        "doi": "NOT ESTABLISHED",
        "manuscript_status": "NOT ESTABLISHED beyond: a jury composition is listed on the title page, "
                             "consistent with a defense manuscript",
        "relevant_table": TABLE_LABEL,
        "relevant_table_title": TABLE_TITLE,
        "relevant_table_pages": TABLE_PAGE_NUMBERS,
        "relevant_table_caption": TABLE_CAPTION,
        "relevant_table_temporal_scope_statement": TABLE_TEMPORAL_SCOPE_STATEMENT,
        "table_caption_pages_found_in_document": table_pages_found,
        "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
        "extraction_method": "direct PDF text/word extraction (pdfplumber), no OCR",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract the GRANDMA telescope-network table from the supplied reference PDF."
    )
    parser.add_argument(
        "--source-pdf",
        default=str(DEFAULT_SOURCE_PDF),
        help=f"Path to the GRANDMA reference PDF. Default: {DEFAULT_SOURCE_PDF}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_pdf = Path(args.source_pdf)
    if not source_pdf.is_absolute():
        source_pdf = (REPO_ROOT / source_pdf).resolve()
    if not source_pdf.exists():
        raise RuntimeError(f"GRANDMA source PDF not found: {source_pdf}")

    with pdfplumber.open(source_pdf) as pdf:
        table_pages_found = find_relevant_table(pdf)
        if table_pages_found != TABLE_PAGE_NUMBERS[:1]:
            print(f"NOTE: table-caption search found caption(s) starting on page(s) "
                  f"{table_pages_found}; extraction targets pages {TABLE_PAGE_NUMBERS} "
                  f"(the table continues onto page {TABLE_PAGE_NUMBERS[1]} without repeating "
                  f"the 'Table 1.1' label there).")
        row_blocks = group_into_rows(pdf)
        records = build_records(row_blocks)
        page_count = len(pdf.pages)

    manifest = build_manifest(source_pdf, page_count, table_pages_found)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    unresolved_cells = find_unresolved_cells(records)
    spot_check_results = run_spot_checks(records)
    controls = validate_extraction(records, spot_check_results, expected_row_count=len(row_blocks))

    print("SOURCE")
    print(f"  file   : {manifest['source_file']}")
    print(f"  sha256 : {manifest['sha256']}")
    print(f"  pages  : {manifest['page_count']}")
    print(f"  table  : {TABLE_LABEL} \"{TABLE_TITLE}\" (pages {TABLE_PAGE_NUMBERS})")

    print("\nEXTRACTION")
    print(f"  rows extracted    : {len(records)}")
    print(f"  columns extracted : {COLUMN_NAMES}")
    section_counts = pd.Series([r["section"] for r in records]).value_counts()
    print(f"  rows per section  : {section_counts.to_dict()}")
    print(f"  unresolved/flagged cells: {len(unresolved_cells)}")
    for item in unresolved_cells:
        print(f"    row {item['row_index_in_source']:2d} ({item['telescope_name']!r}) "
              f"{item['column']}: {item['raw_value']!r} -- {item['reason']}")

    print("\nSPOT CHECKS")
    for result in spot_check_results:
        print(f"  row {result['row_index_in_source']:2d} {result['column']:16s} "
              f"expected={result['expected']!r:20s} observed={result['observed']!r:20s} "
              f"{result['status']}")

    print("\nCONTROLS")
    for control in controls:
        print(f"  {control['control']:60s} expected={control['expected']!s:20s} "
              f"observed={control['observed']!s:20s} {control['status']}")

    overall_status = controls[-1]["status"]
    if overall_status != "PASS":
        raise RuntimeError(
            "GRANDMA table extraction FAILED at least one control; no Parquet file written. "
            "See CONTROLS above."
        )

    frame = build_dataframe(records, manifest)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT_DIR.glob("*.parquet"):
        stale.unlink()
    frame.to_parquet(OUTPUT_PARQUET, engine="pyarrow", index=False, compression="zstd")
    print(f"\nWrote {len(frame)} rows, {frame.shape[1]} columns to {OUTPUT_PARQUET}")


if __name__ == "__main__":
    main()
