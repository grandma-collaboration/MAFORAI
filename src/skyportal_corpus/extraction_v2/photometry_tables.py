from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

TABLE_ROLES = frozenset(
    {
        "time",
        "exposure",
        "filter",
        "magnitude",
        "mag_error",
        "instrument",
        "observer",
        "coordinate",
        "name",
        "comment",
        "unknown",
    }
)

# Filter vocabulary is intentionally centralized and easy to extend. CP2 will use
# the same list when deciding whether a cell is a filter rather than a value.
FILTER_VALUES = frozenset(
    {
        "U",
        "B",
        "V",
        "R",
        "I",
        "Rc",
        "Ic",
        "u",
        "g",
        "r",
        "i",
        "z",
        "u'",
        "g'",
        "r'",
        "i'",
        "z'",
        "sdssu",
        "sdssg",
        "sdssr",
        "sdssi",
        "sdssz",
        "VT_B",
        "VT_R",
        "white",
        "white_FC",
        "v",
        "b",
        "u_FC",
        "w1",
        "w2",
        "w",
        "m2",
        "uvw1",
        "uvw2",
        "uvm2",
        "J",
        "H",
        "K",
        "Ks",
        "Clear",
        "clear",
        "C",
        "L",
        "Luminance",
        "P",
        "P-",
        "P/",
        "P\\",
        "GOTO-L",
        "Johnson V",
        "Johnson R",
        "Johnson I",
        "Gaia G",
        "orange",
        "cyan",
        "none",
    }
)


class ColumnRole(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    confidence: float
    time_subtype: str | None = None

    @model_validator(mode="after")
    def _validate_role(self) -> ColumnRole:
        if self.role not in TABLE_ROLES:
            raise ValueError(f"invalid column role: {self.role!r}")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.role != "time" and self.time_subtype is not None:
            raise ValueError("time_subtype is only valid for time columns")
        return self


class TableBlock(BaseModel):
    """A contiguous table-like block anchored in canonical text.

    Detection is heuristic by design. Strong signals are pipe-delimited rows and
    bordered ASCII tables. Whitespace tables require multiple aligned rows. After
    finding data rows, the detector looks upward across blank/separator lines to
    recover the header, because real UVOT and KNC/GRANDMA tables often separate
    the header from the data with a blank line or ASCII rule. The new roles
    ``mag_error``, ``coordinate``, ``name``, and ``comment`` exist so CP2 can
    distinguish measurement values from uncertainty/metadata columns while
    extracting photometric measurements.
    """

    model_config = ConfigDict(frozen=True)

    start_offset: int
    end_offset: int
    lines: list[str] = Field(default_factory=list)
    delimiter_type: str
    header_line_index: int | None = None
    header_line: str | None = None
    raw_header: str | None = None
    data_rows: list[list[str]] = Field(default_factory=list)
    context_before: str = ""
    context_after: str = ""

    @model_validator(mode="after")
    def _validate_span(self) -> TableBlock:
        if self.start_offset < 0:
            raise ValueError("start_offset must be >= 0")
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be > start_offset")
        if self.delimiter_type not in {"pipe", "whitespace", "bordered"}:
            raise ValueError(f"invalid delimiter_type: {self.delimiter_type!r}")
        if self.header_line_index is not None and not 0 <= self.header_line_index < len(self.lines):
            raise ValueError("header_line_index out of range")
        return self


@dataclass(frozen=True)
class _Line:
    index: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class _HeaderRole:
    role: str
    time_subtype: str | None = None


_IKI_HEADER_RE = re.compile(
    r"\bdate,?.*\but\s*start\b.*\bt\s*-\s*t0\b.*\bexp\.?\b.*\bfilter\b.*"
    r"\b(?:mag|ot)\b.*\berr\.?\b.*\bul\b",
    re.IGNORECASE,
)
_DFOT_HEADER_RE = re.compile(
    r"\bdate\b.*\bmid_?ut\b.*\bt_?start\s*-\s*t0\b.*\bfilter\b.*"
    r"\bexp(?:osure)?\s+time\b.*\bmagnitude\b",
    re.IGNORECASE,
)
_IKI_DATA_ROW_RE = re.compile(
    r"^\s*(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<clock>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"(?P<relative>~?[+-]?\d+(?:\.\d+)?)\s+"
    r"(?P<exposure>(?:\d+\s*[xX*]\s*\d+)(?:\s*\+\s*\d+\s*[xX*]\s*\d+)*)\s+"
    r"(?P<filter>\S+)\s+"
    r"(?P<mag>\d+(?:\.\d+)?(?:\s*(?:\+/-|±)\s*\d+(?:\.\d+)?)?"
    r"(?:\s*\((?:AB|Vega)\))?)\s+"
    r"(?P<err>\d+(?:\.\d+)?)\s+"
    r"(?P<ul>\d+(?:\.\d+)?(?:\s*\(\s*\d+(?:\.\d+)?\s*sig(?:ma)?\.?\s*\))?)"
    r"(?:\s+(?P<instrument>\S+))?\s*$",
    re.IGNORECASE,
)
_DFOT_DATA_ROW_RE = re.compile(
    r"^\s*(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<clock>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"(?P<relative>~?[+-]?\d+(?:\.\d+)?)\s+"
    r"(?P<filter>\S+)\s+"
    r"(?P<exposure>\d+(?:\.\d+)?\s*(?:s|sec)?\s*[xX*]\s*\d+(?:\.\d+)?"
    r"(?:\s*(?:s|sec))?)\s+"
    r"(?P<mag>\d+(?:\.\d+)?(?:\s*(?:\+/-|±)\s*\d+(?:\.\d+)?)?)\s*$",
    re.IGNORECASE,
)
_FILTER_MAG_DEPTH_HEADER_RE = re.compile(
    r"\bfilter\b.*\bmag\b.*\bmag[_ -]?err\b.*\bdate[-_ ]?obs\b.*"
    r"\bexp(?:\.?\s*time)?\b.*\bdepth\b",
    re.IGNORECASE,
)
_FILTER_MAG_DEPTH_DATA_ROW_RE = re.compile(
    r"^\s*(?P<filter>\S+)\s+"
    r"(?P<mag>[<>]?[+-]?\d+(?:\.\d+)?)\s+"
    r"(?P<err>[+-]?\d+(?:\.\d+)?)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"(?P<exposure>\d+(?:\.\d+)?)\s+"
    r"(?P<depth>[<>]?[+-]?\d+(?:\.\d+)?)"
    r"(?:\s+(?P<note>.*\S))?\s*$",
    re.IGNORECASE,
)


def detect_table_blocks(rendered_text: str) -> list[TableBlock]:
    lines = list(_iter_lines(rendered_text))
    consumed: set[int] = set()
    blocks: list[TableBlock] = []

    # IKI/SAO RAS and DFOT publish compact whitespace tables whose date/time and
    # magnitude/error cells are separated by one space. Their semantic header is
    # strong enough to detect even a one-row table, which the generic aligned-
    # whitespace heuristic deliberately requires more evidence to accept.
    for start_index, end_index in _structured_whitespace_ranges(lines):
        block = _build_block(lines, start_index, end_index, "whitespace")
        if not _is_noise_block(block):
            blocks.append(block)
        consumed.update(range(start_index, end_index + 1))

    for start_index, end_index in _bordered_ranges(lines):
        if any(index in consumed for index in range(start_index, end_index + 1)):
            continue
        if _count_data_rows(lines[start_index : end_index + 1], "bordered") >= 2:
            start_index, end_index = _expand_range_with_header(lines, start_index, end_index, "bordered")
            block = _build_block(lines, start_index, end_index, "bordered")
            if not _is_noise_block(block):
                blocks.append(block)
            consumed.update(range(start_index, end_index + 1))

    blocks.extend(
        _run_blocks(
            lines,
            consumed,
            delimiter_type="pipe",
            predicate=_is_pipe_line,
            min_lines=2,
            allow_single_blank_gap=True,
        )
    )
    consumed.update(line_index for block in blocks for line_index in _covered_line_indexes(lines, block))
    blocks.extend(
        _run_blocks(
            lines,
            consumed,
            delimiter_type="whitespace",
            predicate=_is_whitespace_table_line,
            min_lines=3,
            allow_single_blank_gap=True,
        )
    )

    return sorted((block for block in blocks if not _is_noise_block(block)), key=lambda block: (block.start_offset, block.end_offset))


def split_row(line: str, delimiter_type: str) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return []
    if delimiter_type in {"pipe", "bordered"}:
        if _is_separator_line(stripped):
            return []
        return [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]
    if delimiter_type == "whitespace":
        if "|" in stripped and not _is_separator_line(stripped):
            return [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]
        structured = _split_structured_whitespace_data_row(stripped)
        if structured is not None:
            return structured
        return _merge_unit_cells([cell.strip() for cell in re.split(r"\s{2,}", stripped) if cell.strip()])
    raise ValueError(f"invalid delimiter_type: {delimiter_type!r}")


def infer_column_roles(block: TableBlock) -> dict[int, ColumnRole]:
    rows = _rows_for_block(block)
    if not rows:
        return {}

    header = split_row(block.raw_header or "", block.delimiter_type) if block.raw_header else []
    data_rows = _data_rows_for_block(block)
    n_columns = max(len(row) for row in rows)
    roles: dict[int, ColumnRole] = {}

    for column_index in range(n_columns):
        header_cell = header[column_index] if column_index < len(header) else ""
        header_role = _role_from_header(header_cell)
        column_values = [row[column_index] for row in data_rows if column_index < len(row)]
        if header_role.role != "unknown":
            roles[column_index] = ColumnRole(
                role=header_role.role,
                confidence=0.96,
                time_subtype=header_role.time_subtype if header_role.role == "time" else None,
            )
            continue
        roles[column_index] = _role_from_content(column_values)
    return _refine_magnitude_error_roles(data_rows, roles)


def infer_column_role_confidences(block: TableBlock) -> dict[int, float]:
    return {index: role.confidence for index, role in infer_column_roles(block).items()}


def infer_time_subtypes(block: TableBlock) -> dict[int, str | None]:
    return {index: role.time_subtype for index, role in infer_column_roles(block).items() if role.role == "time"}


def _iter_lines(text: str) -> list[_Line]:
    lines: list[_Line] = []
    offset = 0
    for index, chunk in enumerate(text.splitlines(keepends=True)):
        line_text = chunk[:-1] if chunk.endswith("\n") else chunk
        lines.append(_Line(index=index, start=offset, end=offset + len(chunk), text=line_text))
        offset += len(chunk)
    if text and not lines:
        lines.append(_Line(index=0, start=0, end=len(text), text=text))
    return lines


def _bordered_ranges(lines: list[_Line]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if not _is_border_line(lines[index].text):
            index += 1
            continue
        start = index
        border_count = 1
        pipe_count = 0
        index += 1
        while index < len(lines) and (_is_border_line(lines[index].text) or _is_pipe_line(lines[index].text)):
            if _is_border_line(lines[index].text):
                border_count += 1
            if _is_pipe_line(lines[index].text):
                pipe_count += 1
            index += 1
        if border_count >= 1 and pipe_count >= 2:
            ranges.append((start, index - 1))
    return ranges


def _run_blocks(
    lines: list[_Line],
    consumed: set[int],
    delimiter_type: str,
    predicate: Callable[[str], bool],
    min_lines: int,
    allow_single_blank_gap: bool,
) -> list[TableBlock]:
    blocks: list[TableBlock] = []
    index = 0
    while index < len(lines):
        if index in consumed or not predicate(lines[index].text):
            index += 1
            continue
        start = index
        while index < len(lines) and index not in consumed:
            if predicate(lines[index].text):
                index += 1
                continue
            if (
                allow_single_blank_gap
                and not lines[index].text.strip()
                and index + 1 < len(lines)
                and predicate(lines[index + 1].text)
            ):
                index += 1
                continue
            break
        end = index - 1
        run = lines[start : end + 1]
        if sum(1 for line in run if predicate(line.text)) >= min_lines:
            start, end = _expand_range_with_header(lines, start, end, delimiter_type)
            blocks.append(_build_block(lines, start, end, delimiter_type))
    return blocks


def _expand_range_with_header(
    lines: list[_Line],
    start_index: int,
    end_index: int,
    delimiter_type: str,
) -> tuple[int, int]:
    data_row = _first_data_row(lines[start_index : end_index + 1], delimiter_type)
    if data_row is None:
        return start_index, end_index
    data_columns = len(data_row)

    index = start_index - 1
    first_skipped = start_index
    while index >= 0 and _is_separator_line(lines[index].text):
        first_skipped = index
        index -= 1

    if index < 0:
        return start_index, end_index

    candidate = lines[index]
    if _is_header_candidate(candidate.text, delimiter_type, data_columns):
        return index, end_index
    return first_skipped if first_skipped < start_index and delimiter_type == "bordered" else start_index, end_index


def _build_block(
    all_lines: list[_Line],
    start_index: int,
    end_index: int,
    delimiter_type: str,
) -> TableBlock:
    block_lines = all_lines[start_index : end_index + 1]
    header_abs_index, raw_header = _detect_header(block_lines, delimiter_type, start_index=start_index)
    header_line_index = None if header_abs_index is None else header_abs_index - start_index
    context_start = header_abs_index if header_abs_index is not None else start_index
    data_rows = _data_rows_from_lines(
        block_lines,
        delimiter_type,
        header_line_index,
        raw_header,
    )
    return TableBlock(
        start_offset=block_lines[0].start,
        end_offset=block_lines[-1].end,
        lines=[line.text for line in block_lines],
        delimiter_type=delimiter_type,
        header_line_index=header_line_index,
        header_line=(
            block_lines[header_line_index].text
            if header_line_index is not None
            else None
        ),
        raw_header=raw_header,
        data_rows=data_rows,
        context_before=_collect_context_before(all_lines, context_start, max_lines=5),
        context_after=_collect_context_after(all_lines, end_index, max_lines=3),
    )


def _is_noise_block(block: TableBlock) -> bool:
    header = block.raw_header or ""
    if not block.data_rows:
        return True
    if "http://" in header or "https://" in header:
        return True
    if len(re.findall(r"[A-Za-z]+", header)) > 12 and len(split_row(header, block.delimiter_type)) <= 2:
        return True
    return False


def _detect_header(
    lines: list[_Line],
    delimiter_type: str,
    start_index: int,
) -> tuple[int | None, str | None]:
    del start_index
    for local_index, line in enumerate(lines):
        known_cells = _known_whitespace_header_cells(line.text)
        if known_cells is not None:
            continuation = (
                lines[local_index + 1].text
                if local_index + 1 < len(lines)
                and _is_header_continuation_line(lines[local_index + 1].text)
                else None
            )
            combined_cells = _combine_header_continuation(known_cells, continuation)
            return line.index, " | ".join(combined_cells)
        cells = split_row(line.text, delimiter_type)
        if not cells:
            continue
        if any(_role_from_header(cell).role != "unknown" for cell in cells):
            return line.index, line.text
    return None, None


def _collect_context_before(lines: list[_Line], before_index: int, max_lines: int) -> str:
    selected: list[str] = []
    index = before_index - 1
    while index >= 0 and len(selected) < max_lines:
        text = lines[index].text.strip()
        if text and not _is_separator_line(text):
            selected.append(lines[index].text)
        index -= 1
    return "\n".join(reversed(selected))


def _collect_context_after(lines: list[_Line], after_index: int, max_lines: int) -> str:
    selected: list[str] = []
    index = after_index + 1
    while index < len(lines) and len(selected) < max_lines:
        text = lines[index].text.strip()
        if text and not _is_separator_line(text):
            selected.append(lines[index].text)
        index += 1
    return "\n".join(selected)


def _covered_line_indexes(lines: list[_Line], block: TableBlock) -> list[int]:
    return [
        line.index
        for line in lines
        if block.start_offset <= line.start and line.end <= block.end_offset
    ]


def _rows_for_block(block: TableBlock) -> list[list[str]]:
    rows: list[list[str]] = []
    if block.raw_header:
        header = split_row(block.raw_header, block.delimiter_type)
        if header:
            rows.append(header)
    rows.extend(block.data_rows)
    return rows


def _data_rows_for_block(block: TableBlock) -> list[list[str]]:
    return block.data_rows


def _data_rows_from_lines(
    lines: list[_Line],
    delimiter_type: str,
    header_line_index: int | None,
    raw_header: str | None,
) -> list[list[str]]:
    rows: list[list[str]] = []
    header_cells = (
        split_row(raw_header, delimiter_type)
        if raw_header is not None
        else []
    )
    for index, line in enumerate(lines):
        if header_line_index is not None and index == header_line_index:
            continue
        if _is_header_continuation_line(line.text):
            continue
        row = split_row(line.text, delimiter_type)
        row = _align_row_to_header(row, header_cells)
        if row and not _is_separator_row(row) and not _is_unit_row(row) and not _is_header_row(row):
            rows.append(row)
    return rows


def _first_data_row(lines: list[_Line], delimiter_type: str) -> list[str] | None:
    for line in lines:
        row = split_row(line.text, delimiter_type)
        if row and not _is_separator_row(row) and not _is_header_row(row):
            return row
    return None


def _count_data_rows(lines: list[_Line], delimiter_type: str) -> int:
    return sum(1 for line in lines if split_row(line.text, delimiter_type))


def _is_header_candidate(line: str, delimiter_type: str, data_columns: int) -> bool:
    cells = split_row(line, delimiter_type)
    if delimiter_type == "whitespace" and len(cells) <= 1 and "|" in line:
        cells = split_row(line, "pipe")
    if not cells:
        return False
    if not _is_header_row(cells):
        return False
    return abs(len(cells) - data_columns) <= 1


def _is_unit_row(row: list[str]) -> bool:
    return all(re.fullmatch(r"\(?\[?[A-Za-z%./ -]+\]?\)?", cell.strip()) for cell in row)


def _is_separator_row(row: list[str]) -> bool:
    return bool(row) and all(re.fullmatch(r"[-—–+=_|: ]+", cell.strip()) for cell in row)


def _is_header_row(row: list[str]) -> bool:
    if not row:
        return False
    header_roles = [_role_from_header(cell).role for cell in row]
    n_header_roles = sum(1 for role in header_roles if role != "unknown")
    if n_header_roles < 2:
        return False
    # Real rows can contain values like "Xinglong 80-cm Telescope"; do not treat
    # them as headers merely because one cell contains a header-looking word.
    data_like = sum(
        1
        for cell in row
        if _looks_like_magnitude(cell)
        or _looks_like_exposure(cell)
        or _looks_like_filter(cell)
        or _looks_like_mjd(cell)
        or _looks_like_utc_datetime(cell)
        or _looks_like_relative_time(cell)
    )
    return data_like < max(1, len(row) // 2)


def _align_row_to_header(row: list[str], header_cells: list[str]) -> list[str]:
    if not row or not header_cells:
        return row
    first_header_role = _role_from_header(header_cells[0]).role
    if first_header_role == "name" and len(row) + 1 == len(header_cells) and _looks_like_relative_time(row[0]):
        return [""] + row
    return row


def _is_separator_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return bool(re.fullmatch(r"[-—–+=_|: ]+", stripped))


def _is_border_line(line: str) -> bool:
    return bool(re.fullmatch(r"\s*\+(?:[-=]+\+)+\s*", line))


def _is_pipe_line(line: str) -> bool:
    return not _is_border_line(line) and line.count("|") >= 2


def _is_whitespace_table_line(line: str) -> bool:
    if not line.strip() or "|" in line or _is_border_line(line) or _is_separator_line(line):
        return False
    return len(split_row(line, "whitespace")) >= 3


def _structured_whitespace_ranges(lines: list[_Line]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for start_index, line in enumerate(lines):
        if _known_whitespace_header_cells(line.text) is None:
            continue

        index = start_index + 1
        while index < len(lines) and (
            _is_header_continuation_line(lines[index].text)
            or _is_separator_line(lines[index].text)
        ):
            index += 1

        last_data_index: int | None = None
        while index < len(lines):
            if _split_structured_whitespace_data_row(lines[index].text.strip()) is not None:
                last_data_index = index
                index += 1
                continue
            if not lines[index].text.strip() and index + 1 < len(lines):
                if _split_structured_whitespace_data_row(lines[index + 1].text.strip()) is not None:
                    index += 1
                    continue
            break

        if last_data_index is not None:
            ranges.append((start_index, last_data_index))
    return ranges


def _known_whitespace_header_cells(line: str) -> list[str] | None:
    if _IKI_HEADER_RE.search(line):
        cells = ["Date", "UTstart", "t-T0", "Exp.", "Filter", "Mag", "Err.", "UL"]
        if re.search(r"\b(?:telescope|instrument|facility)\b", line, re.IGNORECASE):
            cells.append("Telescope")
        return cells
    if _DFOT_HEADER_RE.search(line):
        return [
            "Date",
            "Mid_UT",
            "T_start-T0 (days)",
            "Filter",
            "Exp time (s)",
            "Magnitude",
        ]
    if _FILTER_MAG_DEPTH_HEADER_RE.search(line):
        return [
            "Filter",
            "Mag",
            "Mag_err",
            "Date-obs[UT]",
            "Exp.time[s]",
            "Depth(5sigma)",
            "Note",
        ]
    return None


def _is_header_continuation_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or "(" not in stripped:
        return False
    remainder = re.sub(r"\([^)]*\)", "", stripped)
    return not remainder.strip()


def _combine_header_continuation(
    header_cells: list[str],
    continuation: str | None,
) -> list[str]:
    if continuation is None or len(header_cells) < 8:
        return header_cells
    combined = list(header_cells)
    for fragment in re.findall(r"\([^)]*\)", continuation):
        normalized = fragment.lower()
        if "sigma" in normalized:
            combined[7] = f"{combined[7]} {fragment}"
        elif "mid" in normalized or "day" in normalized:
            combined[2] = f"{combined[2]} {fragment}"
        elif "n*s" in normalized or "sec" in normalized:
            combined[3] = f"{combined[3]} {fragment}"
    return combined


def _split_structured_whitespace_data_row(line: str) -> list[str] | None:
    iki_match = _IKI_DATA_ROW_RE.fullmatch(line)
    if iki_match is not None:
        cells = [
            iki_match.group("date"),
            iki_match.group("clock"),
            iki_match.group("relative"),
            iki_match.group("exposure"),
            iki_match.group("filter"),
            iki_match.group("mag"),
            iki_match.group("err"),
            iki_match.group("ul"),
        ]
        instrument = iki_match.group("instrument")
        if instrument:
            cells.append(instrument)
        return cells

    dfot_match = _DFOT_DATA_ROW_RE.fullmatch(line)
    if dfot_match is not None:
        return [
            dfot_match.group("date"),
            dfot_match.group("clock"),
            dfot_match.group("relative"),
            dfot_match.group("filter"),
            dfot_match.group("exposure"),
            dfot_match.group("mag"),
        ]
    filter_mag_depth_match = _FILTER_MAG_DEPTH_DATA_ROW_RE.fullmatch(line)
    if filter_mag_depth_match is not None:
        cells = [
            filter_mag_depth_match.group("filter"),
            filter_mag_depth_match.group("mag"),
            filter_mag_depth_match.group("err"),
            filter_mag_depth_match.group("date"),
            filter_mag_depth_match.group("exposure"),
            filter_mag_depth_match.group("depth"),
        ]
        note = filter_mag_depth_match.group("note")
        if note:
            cells.append(note)
        return cells
    return None


def _role_from_header(cell: str) -> _HeaderRole:
    normalized = re.sub(r"\s+", " ", cell.strip().lower())
    normalized = normalized.replace("_", "-")

    if re.search(r"\b(flux|flux density|jy|ujy|µjy|mjy|erg|counts?|count rate)\b", normalized):
        return _HeaderRole("unknown")
    if re.search(r"\b(?:peak\s+)?(?:surface|surf\.?)\s+brightness\b", normalized):
        return _HeaderRole("unknown")
    if re.fullmatch(r"observers?", normalized):
        return _HeaderRole("observer")
    if re.search(r"\b(ra|r\.a\.?|dec|decl|coord|coordinate|j2000)\b", normalized):
        return _HeaderRole("coordinate")
    if re.search(r"\b(name|object|source|id)\b", normalized):
        return _HeaderRole("name")
    if re.search(r"\bdepth\b", normalized):
        return _HeaderRole("comment")
    if re.search(r"\b(comment|comments|note|notes)\b", normalized):
        return _HeaderRole("comment")
    if re.search(r"\b(exp|expt|exposure|exp\(s\)|texp)\b", normalized):
        return _HeaderRole("exposure")
    if re.search(r"\b(filter|band|filt|passband)\b", normalized):
        return _HeaderRole("filter")
    if _header_is_pure_error(normalized):
        return _HeaderRole("mag_error")
    if _header_is_magnitude_like(normalized):
        return _HeaderRole("magnitude")
    if re.search(r"\b(site|tel|telescope|instrument|facility|observatory|obser\.?|observ\.)\b", normalized):
        return _HeaderRole("instrument")
    if "mjd" in normalized:
        return _HeaderRole("time", "mjd")
    if re.search(r"\bjd\b", normalized):
        return _HeaderRole("time", "jd")
    if re.search(r"\bt\s*-?\s*t0\b|\bt-?t0\b|t[_ -]?(start|stop|mid)|tmid|day", normalized):
        return _HeaderRole("time", "relative_to_trigger")
    if re.search(r"\b(date|ut|utc|time|epoch|start|stop)\b", normalized):
        return _HeaderRole("time", "utc_datetime")
    return _HeaderRole("unknown")


def _header_is_magnitude_like(normalized_header: str) -> bool:
    # "3 sigma UL (AB)", "Limiting Magnitude (5 sigma)", and
    # "Upper Limit (error)" are magnitude columns. The sigma/error text describes
    # the confidence level or parenthetical error, not a separate error column.
    return bool(
        re.search(
            r"\b(mag|magnitude|limit|upper\s*limit|upperlimit|upp\.?\s*mag|"
            r"upp\.?\s*lim|limiting|ul|u\.l|brightness|ab\s*mag|abmag)\b",
            normalized_header,
        )
    )


def _header_is_pure_error(normalized_header: str) -> bool:
    return normalized_header in {
        "err",
        "error",
        "e-mag",
        "emag",
        "e mag",
        "mag-err",
        "magerr",
        "mag err",
        "uncertainty",
        "sigma-mag",
        "sigma_mag",
        "+/-",
        "±",
    }


def _role_from_content(values: list[str]) -> ColumnRole:
    # Signature priority is deliberate: exposure patterns and coordinates are
    # highly specific; MJD/UTC come before plain magnitudes; plain numeric values
    # in [8, 30] are treated as magnitudes rather than times.
    signatures: tuple[tuple[str, Callable[[str], bool], float, str | None], ...] = (
        ("exposure", _looks_like_exposure, 0.92, None),
        ("coordinate", _looks_like_coordinate, 0.88, None),
        ("filter", _looks_like_filter, 0.9, None),
        ("time", _looks_like_utc_datetime, 0.9, "utc_datetime"),
        ("time", _looks_like_mjd, 0.9, "mjd"),
        ("time", _looks_like_jd, 0.86, "jd"),
        ("magnitude", _looks_like_magnitude, 0.82, None),
        ("time", _looks_like_relative_time, 0.68, "relative_to_trigger"),
        ("instrument", _looks_like_instrument, 0.65, None),
        ("name", _looks_like_name, 0.62, None),
    )
    for role, predicate, confidence, time_subtype in signatures:
        if _mostly(values, predicate):
            return ColumnRole(role=role, confidence=confidence, time_subtype=time_subtype)
    return ColumnRole(role="unknown", confidence=0.0)


def _mostly(values: list[str], predicate: Callable[[str], bool]) -> bool:
    stripped_values = [value.strip() for value in values if value.strip()]
    if not stripped_values:
        return False
    matches = sum(1 for value in stripped_values if predicate(value))
    return matches / len(stripped_values) >= 0.6


def _refine_magnitude_error_roles(
    data_rows: list[list[str]],
    roles: dict[int, ColumnRole],
) -> dict[int, ColumnRole]:
    if not data_rows:
        return roles
    refined = dict(roles)
    magnitude_columns = [index for index, role in roles.items() if role.role == "magnitude"]
    if not magnitude_columns:
        return refined

    for column_index, role in roles.items():
        if role.role == "mag_error":
            values = [row[column_index] for row in data_rows if column_index < len(row)]
            if not _mostly(values, _looks_like_mag_error):
                refined[column_index] = ColumnRole(role="unknown", confidence=0.0)
            continue
        if not any(abs(column_index - magnitude_index) == 1 for magnitude_index in magnitude_columns):
            continue
        values = [row[column_index] for row in data_rows if column_index < len(row)]
        if _mostly(values, _looks_like_mag_error):
            refined[column_index] = ColumnRole(role="mag_error", confidence=0.9)
    return refined


def _looks_like_magnitude(value: str) -> bool:
    stripped = value.strip()
    if _looks_like_exposure(stripped) or _looks_like_mjd(stripped) or _looks_like_utc_datetime(stripped):
        return False
    if re.search(r"[<>]|\+/-|\bmag\b|\(u\.?l\.?\)|\(vega\)|\(ab\)", stripped, re.IGNORECASE):
        return bool(re.search(r"\d{1,2}(?:\.\d+)?", stripped))
    number = _single_float(stripped)
    return number is not None and 8 <= number <= 30


def _looks_like_mag_error(value: str) -> bool:
    stripped = value.strip()
    if _looks_like_mjd(stripped) or _looks_like_utc_datetime(stripped) or _looks_like_exposure(stripped):
        return False
    error_match = re.fullmatch(
        r"(?:\+/-|±)?\s*\(?\s*([+-]?\d+(?:\.\d+)?)\s*\)?",
        stripped,
    )
    number = float(error_match.group(1)) if error_match is not None else _single_float(stripped)
    return number is not None and 0 <= number < 1


def _looks_like_filter(value: str) -> bool:
    stripped = re.sub(r"\s+", " ", value.strip())
    if stripped in FILTER_VALUES:
        return True
    return stripped.rstrip(".") in FILTER_VALUES


def _looks_like_exposure(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:\d+\s*[x*]\s*)?\d+(?:\.\d+)?\s*s(?:ec|econds)?(?:\s*\([^)]*\))?"
            r"|\d+(?:\.\d+)?\s*\([^)]*stack[^)]*\)",
            value.strip(),
            re.IGNORECASE,
        )
    )


def _looks_like_utc_datetime(value: str) -> bool:
    stripped = value.strip()
    return bool(
        re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", stripped)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", stripped)
        or re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?", stripped)
    )


def _looks_like_mjd(value: str) -> bool:
    number = _single_float(value.strip())
    return number is not None and 40000 <= number <= 80000 and "." in value


def _looks_like_jd(value: str) -> bool:
    number = _single_float(value.strip())
    return number is not None and 2400000 <= number <= 2500000


def _looks_like_relative_time(value: str) -> bool:
    stripped = value.strip().rstrip(".")
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*(?:s|sec|seconds|min|minutes?|h|hr|hrs|hours?|d|day|days)", stripped, re.IGNORECASE):
        return True
    number = _single_float(stripped)
    if number is None:
        return False
    return 0 <= number <= 1000 and not 8 <= number <= 30


def _looks_like_coordinate(value: str) -> bool:
    stripped = value.strip()
    return bool(
        re.search(r"\d{1,2}h\s*\d{1,2}m", stripped, re.IGNORECASE)
        or re.search(r"[+-]?\d{1,3}\.\d+[, ]+[+-]?\d{1,2}\.\d+", stripped)
        or re.fullmatch(r"[+-]?\d{1,3}\.\d{3,}", stripped)
    )


_TRANSIENT_DESIGNATION_RE = re.compile(
    r"^(?:AT|SN)\s?2\d{3}[A-Za-z]{1,4}$"
    r"|^GRB\s?\d{6}[A-Za-z]?$"
    r"|^EP\s?\d{6}[A-Za-z]?$"
    r"|^ZTF\d{2}[a-z]{7}$"
    r"|^IceCube-?\d{6}[A-Za-z]?$"
    r"|^GW\d{6}[A-Za-z]?$",
    re.IGNORECASE,
)
_CATALOG_DESIGNATION_RE = re.compile(r"^J\d{4}", re.IGNORECASE)
_INSTRUMENT_FREE_TEXT_RE = re.compile(
    r"\bposition\b|\bcomment\b|\bupper\s*limit\b|\bnote\b|\bremark\b",
    re.IGNORECASE,
)


def _looks_like_instrument(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped in {"not", "the", "and", "with"}:
        return False
    if re.search(r"\bS\s*/\s*N\b|\bsigma\b|~", stripped, re.IGNORECASE):
        return False
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", stripped):
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?", stripped, re.IGNORECASE):
        return False
    # A candidate cell that is itself a transient/source/catalog designation, a
    # position, a date/time value, a filter/magnitude/exposure token, or a
    # generic free-text label is metadata about the row, not an observing
    # facility, even though it may superficially look like one (mixed case,
    # digits, or a hyphen).
    if _TRANSIENT_DESIGNATION_RE.search(stripped) or _CATALOG_DESIGNATION_RE.match(stripped):
        return False
    if _looks_like_coordinate(stripped):
        return False
    if _looks_like_utc_datetime(stripped) or _looks_like_mjd(stripped) or _looks_like_jd(stripped):
        return False
    if _looks_like_filter(stripped) or _looks_like_magnitude(stripped) or _looks_like_exposure(stripped):
        return False
    if _INSTRUMENT_FREE_TEXT_RE.search(stripped):
        return False
    return bool(
        re.search(r"[A-Z]", stripped)
        or re.search(r"[-_]", stripped)
        or re.search(r"\d+(?:\.\d+)?\s*-?m\b", stripped, re.IGNORECASE)
    )


def _looks_like_name(value: str) -> bool:
    stripped = value.strip()
    return bool(re.search(r"[A-Za-z]", stripped) and re.search(r"\d", stripped) and len(stripped) > 8)


def _single_float(value: str) -> float | None:
    stripped = value.strip()
    if not re.fullmatch(r"[<>]?\s*[+-]?\d+(?:\.\d+)?", stripped):
        return None
    try:
        return float(stripped.replace(">", "").replace("<", "").strip())
    except ValueError:
        return None


def _merge_unit_cells(cells: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(cells):
        current = cells[index]
        next_cell = cells[index + 1] if index + 1 < len(cells) else None
        if (
            next_cell is not None
            and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", current)
            and re.fullmatch(r"s|sec|seconds|min|minutes?|h|hr|hrs|hours?|d|day|days", next_cell.rstrip("."), re.IGNORECASE)
        ):
            merged.append(f"{current} {next_cell}")
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged
