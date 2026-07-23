from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.photometry_annotations import PhotometricMeasurementAnnotation
from skyportal_corpus.extraction_v2.photometry_tables import (
    FILTER_VALUES,
    TableBlock,
    detect_table_blocks,
    infer_column_roles,
    split_row,
)


@dataclass(frozen=True)
class MagnitudeParse:
    measurement_type: str
    magnitude_or_limit: str | None
    magnitude_error: str | None
    limit_sigma: str | None
    system_in_cell: str | None
    principal_value: float | None
    needs_review: bool
    review_reasons: tuple[str, ...]


@dataclass(frozen=True)
class TimeParse:
    obs_time_raw: str
    obs_time_type: str | None
    obs_time_reference: str | None
    needs_review: bool
    review_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _RowLine:
    text: str
    start: int
    end: int
    cells: list[str]


_NUMBER_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")
_SYSTEM_RE = re.compile(r"\(\s*(AB|Vega)(?:\s+mag)?\s*\)", re.IGNORECASE)
_CELL_LIMIT_SIGMA_RE = re.compile(
    r"\(\s*(?P<sigma>\d+(?:\.\d+)?)\s*sig(?:ma)?\.?\s*\)",
    re.IGNORECASE,
)
_LIMIT_SIGMA_RE = re.compile(
    r"\b(?P<sigma>\d+(?:\.\d+)?)[\s-]*sig(?:ma)?\.?\b",
    re.IGNORECASE,
)
_CONTEXT_LIMIT_SIGMA_RE = re.compile(
    r"\b(?P<sigma>\d+(?:\.\d+)?)[\s-]*sigma\s+(?:upper\s+)?limits?\b",
    re.IGNORECASE,
)
_ISO_DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CLOCK_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?")
_TRANSIENT_NAME_RE = re.compile(
    r"\b(?:ZTF\d{2}[a-z]{7}|(?:AT|SN)\s?2\d{3}[a-z]{2,4})\b",
    re.IGNORECASE,
)
_LIMIT_HEADER_RE = re.compile(
    r"\b(?:limit|limiting|upper\s*limit|upperlimit|upp\.?\s*mag|upp\.?\s*lim|u\.?l\.?|ul)\b",
    re.IGNORECASE,
)
_PHOTOMETRY_HEADER_RE = re.compile(
    r"\b(?:mag|magnitude|abmag|brightness|limit|limiting|upper\s*limit|upperlimit|filter|band|photometry)\b",
    re.IGNORECASE,
)
_PHOTOMETRY_CONTEXT_RE = re.compile(
    r"\b(?:photometry|photometric|magnitudes?|mag(?:\.|\b)|ab system|vega system|uvot photometric system)\b",
    re.IGNORECASE,
)
_DIMENSION_RE = re.compile(r"^\s*\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?\s*$", re.IGNORECASE)
# Header-derived column roles are always scored at 0.96 confidence; content-
# inferred instrument columns are scored at 0.65 (see photometry_tables.py
# _role_from_content). This threshold distinguishes the two provenance paths
# without re-deriving the role.
_EXPLICIT_INSTRUMENT_ROLE_CONFIDENCE = 0.9
CLEAR_UNFILTERED_BANDS = frozenset({"C", "clear", "Clear", "CR", "P", "P-", "P/", "P\\", "W", "N"})
_MONTH_DATE_RE = re.compile(
    r"\b\d{1,2}\s+"
    r"(Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|"
    r"Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\b",
    re.IGNORECASE,
)


def parse_magnitude_cell(
    cell: str,
    header_cell: str | None = None,
    is_limit_column: bool = False,
) -> tuple[str, str | None, str | None]:
    """Parse a photometric magnitude cell.

    The returned magnitude/limit is the clean principal value. If a caller needs
    the photometric error, use the detailed internal parser.
    """

    details = _parse_magnitude_cell_details(
        cell,
        header_cell=header_cell,
        is_limit_column=is_limit_column,
    )
    return details.measurement_type, details.magnitude_or_limit, details.system_in_cell


def parse_time_cell(
    cell: str,
    time_subtype_from_header: str | None,
) -> tuple[str, str | None, str | None]:
    """Parse an observation-time cell while preserving the raw cell text."""

    details = _parse_time_cell_details(cell, time_subtype_from_header)
    return details.obs_time_raw, details.obs_time_type, details.obs_time_reference


def parse_exposure_cell(cell: str) -> str:
    """Preserve exposure text exactly as written in the table cell."""

    return cell.strip()


def parse_table_to_measurements(
    block: TableBlock,
    doc: CanonicalDocument,
) -> list[PhotometricMeasurementAnnotation]:
    roles = infer_column_roles(block)
    if not is_photometry_table(block):
        return []

    header_cells = split_row(block.raw_header or "", block.delimiter_type)
    is_catalog_table = _is_multi_object_catalog_block(block, roles)
    row_lines = _row_lines_for_block(block, doc.rendered_text)
    annotations: list[PhotometricMeasurementAnnotation] = []

    for row_line in row_lines:
        magnitude_candidates: list[tuple[int, MagnitudeParse]] = []
        photometric_band: str | None = None
        exposure_time_raw: str | None = None
        instrument: str | None = None
        instrument_provenance: str | None = None
        mag_error_raw: str | None = None
        time_candidates: list[tuple[int, TimeParse]] = []
        provenance: list[str] = []
        review_reasons: list[str] = []

        for column_index, cell in enumerate(row_line.cells):
            role = roles.get(column_index)
            if role is None:
                continue
            if role.role == "magnitude":
                header_cell = header_cells[column_index] if column_index < len(header_cells) else None
                if _is_empty_magnitude_cell(cell):
                    continue
                magnitude = _parse_magnitude_cell_details(cell, header_cell=header_cell)
                if magnitude.magnitude_or_limit is not None:
                    magnitude_candidates.append((column_index, magnitude))
            elif role.role == "mag_error":
                mag_error_raw = cell.strip() or None
            elif role.role == "time":
                time_candidates.append((column_index, _parse_time_cell_details(cell, role.time_subtype)))
            elif role.role == "exposure":
                exposure_time_raw = parse_exposure_cell(cell)
            elif role.role == "filter":
                photometric_band = cell.strip() or None
            elif role.role == "instrument":
                stripped_cell = cell.strip()
                if _is_valid_instrument_value(stripped_cell):
                    instrument = stripped_cell
                    instrument_provenance = (
                        "explicit_column"
                        if role.confidence >= _EXPLICIT_INSTRUMENT_ROLE_CONFIDENCE
                        else "inferred_column"
                    )
            # coordinate, observer, name, comment, and unknown columns are
            # intentionally skipped. They describe the row but are not the
            # measurement value itself.

        time_candidates, combined_time_columns = _combine_date_and_clock_candidates(
            time_candidates
        )
        if combined_time_columns is not None:
            provenance.append(
                f"combined_time_cols={combined_time_columns[0]},{combined_time_columns[1]}"
            )

        magnitude_candidates = _discard_spurious_parallel_magnitude_columns(magnitude_candidates)
        magnitude_candidates = _drop_depth_limits_for_detected_rows(magnitude_candidates)
        if not magnitude_candidates:
            continue
        if not _row_has_minimum_photometry_signal(block, roles, header_cells, photometric_band):
            continue

        primary_time, secondary_times = _select_primary_time(time_candidates)
        if primary_time is not None:
            review_reasons.extend(primary_time.review_reasons)
        else:
            review_reasons.append("missing observation time")

        for column_index, secondary_time in secondary_times:
            provenance.append(
                f"secondary_time_col={column_index}:"
                f"{secondary_time.obs_time_raw}({secondary_time.obs_time_type or 'unknown'})"
            )

        if is_catalog_table:
            review_reasons.append(
                "Photometry from a multi-object catalog table; verify association with the event."
            )

        # A trailing limiting-magnitude column describes image depth. It is not a
        # second source measurement when this row already contains a detection.
        row_systems = {
            magnitude.system_in_cell
            for _column_index, magnitude in magnitude_candidates
            if magnitude.system_in_cell is not None
        }
        shared_row_system = next(iter(row_systems)) if len(row_systems) == 1 else None

        for _column_index, magnitude in magnitude_candidates:
            magnitude_header = (
                header_cells[_column_index]
                if _column_index < len(header_cells)
                else None
            )
            candidate_band = (
                photometric_band
                or _band_from_magnitude_header(magnitude_header)
            )
            candidate_review_reasons = [*review_reasons, *magnitude.review_reasons]
            if not candidate_band:
                candidate_review_reasons.append("missing photometric band")
            candidate_provenance = list(provenance)
            magnitude_error = magnitude.magnitude_error
            if magnitude.measurement_type == "detection" and magnitude_error is None:
                magnitude_error = _parse_error_column(mag_error_raw)
            limit_sigma = magnitude.limit_sigma
            if magnitude.measurement_type == "upper_limit" and limit_sigma is None:
                limit_sigma = _limit_sigma_from_context(block.context_before)

            measurement_system = magnitude.system_in_cell
            if measurement_system is None and shared_row_system is not None:
                measurement_system = shared_row_system
                candidate_provenance.append(
                    f"photometric_system=row_measurement_cell:{shared_row_system}"
                )
            photometric_system, system_review, system_provenance = _resolve_photometric_system(
                measurement_system,
                block.context_before,
                candidate_band,
            )
            candidate_provenance.extend(system_provenance)
            candidate_review_reasons.extend(system_review)

            needs_review = bool(candidate_review_reasons)
            comment = "; ".join(dict.fromkeys(candidate_review_reasons)) if needs_review else None
            annotation = PhotometricMeasurementAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=row_line.start,
                span_end=row_line.end,
                text=row_line.text,
                measurement_type=magnitude.measurement_type,
                target="counterpart",
                certainty="confirmed",
                magnitude_or_limit=magnitude.magnitude_or_limit,
                magnitude_error=magnitude_error,
                limit_sigma=limit_sigma,
                unit="mag",
                photometric_band=candidate_band,
                photometric_system=photometric_system,
                obs_time_raw=primary_time.obs_time_raw if primary_time else None,
                obs_time_type=primary_time.obs_time_type if primary_time else None,
                obs_time_reference=primary_time.obs_time_reference if primary_time else None,
                exposure_time_raw=exposure_time_raw,
                instrument=instrument,
                instrument_provenance=instrument_provenance,
                comment=comment,
                provenance_inherited=candidate_provenance,
                extractor_id=PhotometryRowParser.extractor_id,
                extractor_version=PhotometryRowParser.extractor_version,
                method="table-parse",
                rule_id=f"photometry_row.{block.delimiter_type}",
                confidence=0.7 if needs_review else 0.95,
                needs_review=needs_review,
            )
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    f"PhotometricMeasurementAnnotation failed offset verification: "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)

    return annotations


class PhotometryRowParser:
    extractor_id = "photometry-row-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[PhotometricMeasurementAnnotation]:
        annotations: list[PhotometricMeasurementAnnotation] = []
        for block in detect_table_blocks(doc.rendered_text):
            annotations.extend(parse_table_to_measurements(block, doc))
        return annotations


def is_photometry_table(block: TableBlock) -> bool:
    """Return True only for tables that plausibly contain photometric rows.

    CP1 detects generic numeric tables. CP2 is stricter: a photometry table must
    have a magnitude-like column plus either a filter column, a photometry-specific
    header, or clear photometry context. This rejects radio/source-parameter
    tables such as ``T_mid Freq UL r.m.s. Beam PA`` where ``UL`` is an upper limit
    but not an optical magnitude.
    """

    roles = infer_column_roles(block)
    has_magnitude = any(role.role == "magnitude" for role in roles.values())
    if not has_magnitude:
        return False
    has_filter = any(role.role == "filter" for role in roles.values())
    return has_filter or _has_photometry_header_signal(block) or _has_photometry_context(block)


def _parse_magnitude_cell_details(
    cell: str,
    header_cell: str | None = None,
    is_limit_column: bool = False,
) -> MagnitudeParse:
    cleaned, system = _extract_system_from_cell(cell)
    cleaned, cell_limit_sigma = _extract_limit_sigma_from_cell(cleaned)
    if system is None:
        system = _system_from_header(header_cell)
    normalized = re.sub(r"\s+", " ", cleaned.replace("±", "+/-").strip())
    number_match = _NUMBER_RE.search(normalized)
    review_reasons: list[str] = []

    if number_match is None:
        return MagnitudeParse(
            measurement_type="unclear",
            magnitude_or_limit=None,
            magnitude_error=None,
            limit_sigma=None,
            system_in_cell=system,
            principal_value=None,
            needs_review=True,
            review_reasons=("magnitude cell has no numeric value",),
        )

    principal_text = number_match.group(0)
    principal_value = _safe_float(principal_text)
    starts_with_limit = bool(re.match(r"^\s*[<>]", normalized))
    limit_from_header = is_limit_column or _header_indicates_limit(header_cell)
    error_text = _parse_inline_magnitude_error(normalized) or _parse_parenthetical_magnitude_error(normalized)

    if starts_with_limit or limit_from_header:
        measurement_type = "upper_limit"
        magnitude_or_limit = principal_text.lstrip("+")
        magnitude_error = error_text
        limit_sigma = cell_limit_sigma or _limit_sigma_from_header(header_cell)
    elif "+/-" in normalized:
        measurement_type = "detection"
        magnitude_or_limit = principal_text.lstrip("+")
        magnitude_error = error_text
        limit_sigma = None
    else:
        measurement_type = "detection"
        magnitude_or_limit = principal_text.lstrip("+")
        magnitude_error = None
        limit_sigma = None

    if principal_value is None or not 5 <= principal_value <= 30:
        review_reasons.append("magnitude outside expected optical range")

    return MagnitudeParse(
        measurement_type=measurement_type,
        magnitude_or_limit=magnitude_or_limit,
        magnitude_error=magnitude_error,
        limit_sigma=limit_sigma,
        system_in_cell=system,
        principal_value=principal_value,
        needs_review=bool(review_reasons),
        review_reasons=tuple(review_reasons),
    )


def _parse_time_cell_details(cell: str, time_subtype_from_header: str | None) -> TimeParse:
    raw = cell.strip()
    inferred_type = _infer_time_type(raw)
    if (
        time_subtype_from_header == "utc_datetime"
        and inferred_type == "relative_to_trigger"
    ):
        obs_time_type = inferred_type
    else:
        obs_time_type = time_subtype_from_header or inferred_type or "unclear"
    review_reasons: list[str] = []

    if time_subtype_from_header and inferred_type and inferred_type != time_subtype_from_header and obs_time_type == time_subtype_from_header:
        review_reasons.append(
            f"time value does not match expected subtype {time_subtype_from_header}"
        )
    if obs_time_type == "unclear":
        review_reasons.append("observation time subtype is unclear")

    return TimeParse(
        obs_time_raw=raw,
        obs_time_type=obs_time_type,
        obs_time_reference=_reference_for_time_type(obs_time_type),
        needs_review=bool(review_reasons),
        review_reasons=tuple(review_reasons),
    )


def _row_lines_for_block(block: TableBlock, rendered_text: str) -> list[_RowLine]:
    expected_rows = [_normalize_cells(row) for row in block.data_rows]
    matched_rows: list[_RowLine] = []
    expected_index = 0
    offset = block.start_offset
    block_text = rendered_text[block.start_offset : block.end_offset]
    header_cells = split_row(block.raw_header or "", block.delimiter_type)

    for chunk in block_text.splitlines(keepends=True):
        line_text = chunk[:-1] if chunk.endswith("\n") else chunk
        line_start = offset
        line_end = line_start + len(line_text)
        offset += len(chunk)

        cells = split_row(line_text, block.delimiter_type)
        cells = _align_row_cells_to_header(cells, header_cells)
        if not cells or expected_index >= len(expected_rows):
            continue
        if _normalize_cells(cells) == expected_rows[expected_index]:
            matched_rows.append(_RowLine(text=line_text, start=line_start, end=line_end, cells=cells))
            expected_index += 1

    return matched_rows


def _select_primary_time(
    time_candidates: list[tuple[int, TimeParse]],
) -> tuple[TimeParse | None, list[tuple[int, TimeParse]]]:
    if not time_candidates:
        return None, []

    # When a row has both relative time and absolute time, prefer the absolute
    # value. MJD is usually the most precise table column, so it is the primary
    # observation time; relative T-T0 is preserved in provenance for later review.
    priority = {
        "mjd": 0,
        "utc_datetime": 1,
        "calendar_date": 2,
        "jd": 3,
        "relative_to_trigger": 4,
        "start_time_plus_exposure": 5,
        "other_timezone": 6,
        "unclear": 7,
        None: 8,
    }
    selected_index, selected_time = min(
        time_candidates,
        key=lambda item: (priority.get(item[1].obs_time_type, 9), item[0]),
    )
    secondary = [(index, time) for index, time in time_candidates if index != selected_index]
    return selected_time, secondary


def _combine_date_and_clock_candidates(
    time_candidates: list[tuple[int, TimeParse]],
) -> tuple[list[tuple[int, TimeParse]], tuple[int, int] | None]:
    """Combine adjacent absolute date and clock columns before time selection.

    Tables commonly split ``YYYY-MM-DD`` and ``HH:MM:SS`` into separate columns.
    Neither value is the full observation epoch on its own; together they form a
    precise UTC datetime. Relative T-T0 and MJD columns remain separate candidates
    and retain the existing primary/secondary selection semantics.
    """

    date_candidates = [
        (column_index, parsed)
        for column_index, parsed in time_candidates
        if _ISO_DATE_RE.fullmatch(parsed.obs_time_raw.strip())
    ]
    clock_candidates = [
        (column_index, parsed)
        for column_index, parsed in time_candidates
        if _CLOCK_RE.fullmatch(parsed.obs_time_raw.strip())
    ]
    if not date_candidates or not clock_candidates:
        return time_candidates, None

    date_column, date_value = date_candidates[0]
    clock_column, clock_value = min(
        clock_candidates,
        key=lambda item: (abs(item[0] - date_column), item[0]),
    )
    combined = TimeParse(
        obs_time_raw=f"{date_value.obs_time_raw.strip()} {clock_value.obs_time_raw.strip()}",
        obs_time_type="utc_datetime",
        obs_time_reference="absolute_time",
        needs_review=False,
        review_reasons=(),
    )
    consumed = {date_column, clock_column}
    remaining = [
        candidate for candidate in time_candidates if candidate[0] not in consumed
    ]
    remaining.append((min(consumed), combined))
    return sorted(remaining, key=lambda item: item[0]), (date_column, clock_column)


def _resolve_photometric_system(
    system_in_cell: str | None,
    context_before: str,
    photometric_band: str | None = None,
) -> tuple[str, list[str], list[str]]:
    if system_in_cell is not None:
        return system_in_cell, [], []

    context = re.sub(r"\s+", " ", context_before.lower())
    has_ab = bool(re.search(
        r"\bab\s+(?:mag(?:nitude)?s?\s+)?system\b|\bin\s+the\s+ab\s+system\b|"
        r"\bab\s+mag(?:nitude)?s?\b|\bin\s+ab\s+mag(?:nitude)?s?\b",
        context,
    ))
    has_vega = bool(
        re.search(r"\bvega\s+(?:mag(?:nitude)?s?\s+)?system\b|\bin\s+the\s+vega\s+system\b", context)
    )
    mixed_system_context = bool(
        re.search(r"\bab\b", context)
        and re.search(r"\bvega\b", context)
        and re.search(r"\bsystems?\b|depending\s+on", context)
    )
    if mixed_system_context or (has_ab and has_vega):
        # Mixed systems such as "AB and Vega depending on the filter" cannot be
        # inherited globally. A system explicitly attached to another magnitude
        # cell in the same row is resolved before this context fallback.
        return "unknown", ["photometric system varies by row or filter"], []
    if has_ab:
        return "AB", [], ["photometric_system=context:AB"]
    if has_vega:
        return "Vega", [], ["photometric_system=context:Vega"]
    if "uvot photometric system" in context:
        # Swift/UVOT magnitudes are reported in the UVOT Vega system by
        # convention (Breeveld et al. 2011). Explicit AB declarations above still
        # take precedence.
        return "Vega", [], ["system_from_uvot_convention"]
    if _is_clear_unfiltered_band(photometric_band):
        return "unknown", [], ["system_expected_unknown_for_clear_unfiltered"]
    return "unknown", ["photometric system is unknown"], []


def _extract_system_from_cell(cell: str) -> tuple[str, str | None]:
    match = _SYSTEM_RE.search(cell)
    if match is None:
        return cell, None
    raw_system = match.group(1).lower()
    system = "AB" if raw_system == "ab" else "Vega"
    cleaned = f"{cell[: match.start()]} {cell[match.end() :]}"
    return cleaned, system


def _extract_limit_sigma_from_cell(cell: str) -> tuple[str, str | None]:
    """Remove a parenthetical limit confidence without treating it as magnitude."""

    match = _CELL_LIMIT_SIGMA_RE.search(cell)
    if match is None:
        return cell, None
    cleaned = f"{cell[: match.start()]} {cell[match.end() :]}"
    return cleaned, match.group("sigma")


def _limit_sigma_from_header(header_cell: str | None) -> str | None:
    if header_cell is None or not _header_indicates_limit(header_cell):
        return None
    match = _LIMIT_SIGMA_RE.search(header_cell)
    return match.group("sigma") if match is not None else None


def _limit_sigma_from_context(context_before: str) -> str | None:
    match = _CONTEXT_LIMIT_SIGMA_RE.search(context_before)
    return match.group("sigma") if match is not None else None


def _system_from_header(header_cell: str | None) -> str | None:
    if header_cell is None:
        return None
    normalized = re.sub(r"\s+", " ", header_cell.strip().lower())
    if re.search(r"\bab\s*mag\b|\babmag\b|\(\s*ab\s*\)", normalized):
        return "AB"
    if re.search(r"\bvega\b|\(\s*vega\s*\)", normalized):
        return "Vega"
    return None


def _infer_time_type(value: str) -> str | None:
    stripped = value.strip()
    if re.fullmatch(
        r"[+-]?\d+(?:\.\d+)?\s*(?:s|sec|seconds|min|minutes?|h|hr|hrs|hours?|d|day|days)\.?",
        stripped,
        re.IGNORECASE,
    ):
        return "relative_to_trigger"
    number = _safe_float(stripped)
    if number is not None and 40000 <= number <= 80000 and "." in stripped:
        return "mjd"
    if number is not None and 2400000 <= number <= 2500000:
        return "jd"
    if _ISO_DATETIME_RE.search(stripped) or re.search(r"\b\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}", stripped):
        return "utc_datetime"
    if _ISO_DATE_RE.fullmatch(stripped) or _MONTH_DATE_RE.search(stripped):
        return "calendar_date"
    if number is not None:
        return "relative_to_trigger"
    return None


def _reference_for_time_type(obs_time_type: str | None) -> str | None:
    if obs_time_type in {"mjd", "jd", "utc_datetime", "calendar_date"}:
        return "absolute_time"
    if obs_time_type == "relative_to_trigger":
        return "trigger_time_t0"
    if obs_time_type in {"start_time_plus_exposure"}:
        return "observation_start"
    return "unknown"


def _safe_float(value: str) -> float | None:
    try:
        return float(value.strip().replace(">", "").replace("<", ""))
    except ValueError:
        return None


def _normalize_cells(cells: list[str]) -> list[str]:
    return [re.sub(r"\s+", " ", cell.strip()) for cell in cells]


def _header_indicates_limit(header_cell: str | None) -> bool:
    if header_cell is None:
        return False
    return bool(_LIMIT_HEADER_RE.search(header_cell))


def _is_clear_unfiltered_band(photometric_band: str | None) -> bool:
    if photometric_band is None:
        return False
    normalized = photometric_band.strip()
    return normalized in CLEAR_UNFILTERED_BANDS


def _row_has_minimum_photometry_signal(
    block: TableBlock,
    roles: dict[int, object],
    header_cells: list[str],
    photometric_band: str | None,
) -> bool:
    has_magnitude = any(getattr(role, "role", None) == "magnitude" for role in roles.values())
    if not has_magnitude:
        return False
    return (
        _is_recognized_band(photometric_band)
        or _has_photometry_context(block)
        or _has_photometry_header_signal(block, header_cells)
    )


def _has_photometry_header_signal(block: TableBlock, header_cells: list[str] | None = None) -> bool:
    header = " ".join(header_cells) if header_cells is not None else block.raw_header or ""
    header = header.replace("_", " ").replace("-", " ")
    return bool(_PHOTOMETRY_HEADER_RE.search(header))


def _has_photometry_context(block: TableBlock) -> bool:
    return bool(_PHOTOMETRY_CONTEXT_RE.search(block.context_before))


def _is_recognized_band(photometric_band: str | None) -> bool:
    if photometric_band is None:
        return False
    stripped = re.sub(r"\s+", " ", photometric_band.strip())
    return stripped in FILTER_VALUES or stripped.rstrip(".") in FILTER_VALUES or _is_clear_unfiltered_band(stripped)


def _align_row_cells_to_header(cells: list[str], header_cells: list[str]) -> list[str]:
    if not cells or not header_cells:
        return cells
    if len(cells) + 1 == len(header_cells):
        first_header = header_cells[0].strip().lower()
        if re.search(r"\b(?:id|source|name|object)\b", first_header) and _infer_time_type(cells[0]) == "relative_to_trigger":
            return [""] + cells
    return cells


def _band_from_magnitude_header(header_cell: str | None) -> str | None:
    if header_cell is None:
        return None
    normalized = re.sub(r"\s+", "", header_cell.strip())
    if re.fullmatch(r"AB_?mag|ABmag|Magnitude\(AB\)|Brightness", normalized, re.IGNORECASE):
        return None
    match = re.fullmatch(
        r"([A-Za-z][A-Za-z0-9_']{0,10})[_-]?(?:mag|magnitude)"
        r"(?:\((?:AB|Vega)\))?",
        normalized,
        re.IGNORECASE,
    )
    if match is None:
        return None
    band = match.group(1).rstrip("_.-")
    return band if band in FILTER_VALUES else band.rstrip(".")


def _is_empty_magnitude_cell(value: str) -> bool:
    return bool(re.fullmatch(r"\s*(?:-|--|---|n/?a)?\s*", value, re.IGNORECASE))


def _discard_spurious_parallel_magnitude_columns(
    candidates: list[tuple[int, MagnitudeParse]],
) -> list[tuple[int, MagnitudeParse]]:
    if len(candidates) <= 1:
        return candidates
    plausible = [
        candidate
        for candidate in candidates
        if candidate[1].principal_value is not None and 5 <= candidate[1].principal_value <= 30
    ]
    # A misaligned whitespace header can label an exposure column as ``Mag`` while
    # content inference correctly finds the actual magnitude one column later.
    # When parallel candidates exist, retain the optically plausible values. A
    # single out-of-range magnitude is still emitted for human review as before.
    return plausible or candidates


def _drop_depth_limits_for_detected_rows(
    candidates: list[tuple[int, MagnitudeParse]],
) -> list[tuple[int, MagnitudeParse]]:
    if len(candidates) <= 1:
        return candidates

    has_detection = any(
        magnitude.measurement_type == "detection"
        for _column_index, magnitude in candidates
    )
    if not has_detection:
        return candidates
    return [
        candidate
        for candidate in candidates
        if candidate[1].measurement_type == "detection"
    ]


def _is_valid_instrument_value(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped in {"not", "the", "and", "with"}:
        return False
    if re.search(r"\bS\s*/\s*N\b|\bsigma\b|~", stripped, re.IGNORECASE):
        return False
    if _DIMENSION_RE.fullmatch(stripped) or re.fullmatch(r"[+-]?\d+(?:\.\d+)?", stripped):
        return False
    if not re.search(r"[A-Za-z]", stripped):
        return False
    # Telescope/observatory names normally expose an acronym, capitalization, a
    # site-name separator, or an aperture. This preserves NOT while rejecting the
    # common word "not" and numeric/remarks columns misclassified as instruments.
    return bool(
        re.search(r"[A-Z]", stripped)
        or re.search(r"[-_]", stripped)
        or re.search(r"\d+(?:\.\d+)?\s*-?m\b", stripped, re.IGNORECASE)
    )


def _parse_inline_magnitude_error(value: str) -> str | None:
    match = re.search(r"\+/-\s*([+-]?\d+(?:\.\d+)?)", value)
    if match is None:
        return None
    return match.group(1)


def _parse_parenthetical_magnitude_error(value: str) -> str | None:
    match = re.search(r"\(\s*([+-]?\d+(?:\.\d+)?)\s*\)", value)
    if match is None:
        return None
    return match.group(1)


def _parse_error_column(mag_error_raw: str | None) -> str | None:
    if not mag_error_raw:
        return None
    error_match = _NUMBER_RE.search(mag_error_raw)
    if error_match is None:
        return None
    return error_match.group(0)


def _is_multi_object_catalog_block(block: TableBlock, roles: dict[int, object]) -> bool:
    # Survey/catalog tables list many objects with names and coordinates. They
    # are useful evidence, but the row is not clean photometry of the circular's
    # event, so CP2 marks derived measurements for review instead of treating
    # them as event-associated measurements.
    name_columns = [
        column_index
        for column_index, role in roles.items()
        if getattr(role, "role", None) == "name"
    ]
    coordinate_columns = [
        column_index
        for column_index, role in roles.items()
        if getattr(role, "role", None) == "coordinate"
    ]
    if not name_columns or not coordinate_columns:
        return False

    rows_with_transient_names = 0
    for row in block.data_rows:
        if any(column_index < len(row) and _TRANSIENT_NAME_RE.search(row[column_index]) for column_index in name_columns):
            rows_with_transient_names += 1
    return rows_with_transient_names >= 2
