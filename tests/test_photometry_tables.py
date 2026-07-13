from __future__ import annotations

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.photometry_tables import (
    ColumnRole,
    detect_table_blocks,
    emit_photometry_table_annotations,
    infer_column_roles,
    split_row,
)


def _doc(body: str):
    return render_canonical(circular_id=1, subject="Photometry report", body=body)


def _roles(block) -> dict[int, str]:
    return {index: detail.role for index, detail in infer_column_roles(block).items()}


def _time_subtypes(block) -> dict[int, str | None]:
    return {index: detail.time_subtype for index, detail in infer_column_roles(block).items()}


def test_uvot_whitespace_header_context_and_roles() -> None:
    doc = _doc(
        "No optical afterglow consistent with the BAT position\n"
        "is detected in the initial UVOT exposures.\n"
        "Preliminary 3-sigma upper limits using the UVOT photometric system\n"
        "(Breeveld et al. 2011) for the first finding chart exposure are:\n"
        "\n"
        "Filter         T_start(s)   T_stop(s)      Exp(s)         Mag\n"
        "\n"
        "white_FC           168          318          147         >20.4\n"
        "white              168         1053          334         >20.8\n"
        "v                  656         4661          236         >18.7\n"
        "b                  582          773           39         >18.9\n"
        "u                  729          749           19         >18.3\n"
        "w1                 705         5071          236         >19.5\n"
        "w2                 804          824           19         >18.7\n"
        "\n"
        "The magnitudes in the table are not corrected for Galactic extinction.\n"
    )

    blocks = detect_table_blocks(doc.rendered_text)

    assert len(blocks) == 1
    block = blocks[0]
    assert block.delimiter_type == "whitespace"
    assert block.header_line == "Filter         T_start(s)   T_stop(s)      Exp(s)         Mag"
    assert block.raw_header == "Filter         T_start(s)   T_stop(s)      Exp(s)         Mag"
    assert block.data_rows[0] == ["white_FC", "168", "318", "147", ">20.4"]
    assert len(block.data_rows) == 7
    assert "3-sigma" in block.context_before
    assert "UVOT photometric system" in block.context_before
    assert "Galactic extinction" in block.context_after
    assert _roles(block) == {
        0: "filter",
        1: "time",
        2: "time",
        3: "exposure",
        4: "magnitude",
    }
    assert _time_subtypes(block)[1] == "relative_to_trigger"
    assert _time_subtypes(block)[2] == "relative_to_trigger"
    assert infer_column_roles(block)[3].confidence >= 0.9
    assert infer_column_roles(block)[4].role == "magnitude"


def test_knc_pipe_header_context_roles_and_time_subtypes() -> None:
    doc = _doc(
        "In the following table we report the preliminary photometry of our\n"
        "observations. Upper limits are reported at the 5-sigma limit,\n"
        "in the AB system.\n"
        "\n"
        "T-T0 (day)|    MJD   | Observatory | Exp. | Filter   | Upp.Mag.  | Comments\n"
        "------------------------------------------------------------------------------------------------------------\n"
        "3.58    |60426.477894 | KNC       |10x180s| Johnson V |  16.7     | calibrated in R, Gaia\n"
        "3.63    |60426.528530 | KNC       |7x180s | Rc        |  16.6     | calibrated in sdssg, PS1\n"
        "3.76    |60426.652754 | LesMakes-T60|5x120s | Clear    |  19.5     | calibrated in sdssr, PS1\n"
        "3.80    |60426.696710 | LesMakes-T60|40x120s| sdssr   |  21.2     | calibrated in sdssr, PS1\n"
        "\n"
        "All the data have been reduced by STDPIPE.\n"
    )

    blocks = detect_table_blocks(doc.rendered_text)

    assert len(blocks) == 1
    block = blocks[0]
    assert block.delimiter_type == "pipe"
    assert block.raw_header == "T-T0 (day)|    MJD   | Observatory | Exp. | Filter   | Upp.Mag.  | Comments"
    assert block.header_line == "T-T0 (day)|    MJD   | Observatory | Exp. | Filter   | Upp.Mag.  | Comments"
    assert block.data_rows[0] == [
        "3.58",
        "60426.477894",
        "KNC",
        "10x180s",
        "Johnson V",
        "16.7",
        "calibrated in R, Gaia",
    ]
    assert "AB system" in block.context_before
    assert _roles(block) == {
        0: "time",
        1: "time",
        2: "instrument",
        3: "exposure",
        4: "filter",
        5: "magnitude",
        6: "comment",
    }
    subtypes = _time_subtypes(block)
    assert subtypes[0] == "relative_to_trigger"
    assert subtypes[1] == "mjd"
    assert infer_column_roles(block)[3].confidence >= 0.9
    assert infer_column_roles(block)[5] == ColumnRole(role="magnitude", confidence=0.96)


def test_bordered_knc_header_and_roles() -> None:
    doc = _doc(
        "Upper limits are reported in the Vega system.\n"
        "\n"
        "| T-T0 [day] |      MJD       | Telescope | Exposure  | Filter | Upperlimit (5 sig.) |\n"
        "+------------+----------------+-----------+-----------+--------+---------------------+\n"
        "|    6.07    | 60430.15036744 |    ASO    |  17x180s  |   L    |         21.8        |\n"
        "|    7.19    | 60431.26727265 |    OPD    |  10x180s  |   R    |         20.8        |\n"
        "|    7.21    | 60431.28910205 |    OPD    |  10x200s  |   R    |         21.1        |\n"
        "+------------+----------------+-----------+-----------+--------+---------------------+\n"
        "\n"
        "ASO and OPD data have been calibrated in V and R.\n"
    )

    blocks = detect_table_blocks(doc.rendered_text)

    assert len(blocks) == 1
    block = blocks[0]
    assert block.delimiter_type == "bordered"
    assert block.raw_header == "| T-T0 [day] |      MJD       | Telescope | Exposure  | Filter | Upperlimit (5 sig.) |"
    assert "Vega system" in block.context_before
    assert _roles(block) == {
        0: "time",
        1: "time",
        2: "instrument",
        3: "exposure",
        4: "filter",
        5: "magnitude",
    }
    assert _time_subtypes(block)[0] == "relative_to_trigger"
    assert _time_subtypes(block)[1] == "mjd"


def test_observer_column_is_not_instrument_when_header_is_observer() -> None:
    doc = _doc(
        "Magnitudes are reported in Vega system.\n"
        "\n"
        "T-T0 day | MJD | Telescope | Observer | Exposure | Filter | Upper limit\n"
        "-----------------------------------------------------------------------\n"
        "1.10 | 60397.78045138 | Montarrenti 0.53m | S. Leonini | 3x180s | Rc | 18.9 (Vega)\n"
        "1.31 | 60397.98425636 | PlaneWave CDK 17\" | Y. Jongen | 1x180s | Rc | 20.1 (Vega)\n"
    )

    blocks = detect_table_blocks(doc.rendered_text)

    assert len(blocks) == 1
    roles = _roles(blocks[0])
    assert roles[2] == "instrument"
    assert roles[3] == "observer"
    assert blocks[0].data_rows[0] == [
        "1.10",
        "60397.78045138",
        "Montarrenti 0.53m",
        "S. Leonini",
        "3x180s",
        "Rc",
        "18.9 (Vega)",
    ]


def test_single_casual_pipe_line_is_not_table() -> None:
    doc = _doc("This is prose with one casual | separator and no table block.")

    assert detect_table_blocks(doc.rendered_text) == []


def test_content_signature_exposure_and_numeric_magnitude_disambiguation() -> None:
    doc = _doc(
        "10x180s  R  16.7\n"
        "7x180s   Rc  16.6\n"
        "5x120s   Clear  19.5\n"
    )

    blocks = detect_table_blocks(doc.rendered_text)

    assert len(blocks) == 1
    roles = infer_column_roles(blocks[0])
    assert roles[0].role == "exposure"
    assert roles[0].confidence >= 0.9
    assert roles[2].role == "magnitude"
    assert roles[2].time_subtype is None


def test_photometry_table_annotation_verifies_and_needs_review() -> None:
    doc = _doc(
        "| Date | Tel | Exp | Filter | Mag |\n"
        "| 2024-10-25T02:46:16 | KNC-iT11 | 4x180s | R | >18.5 (U.L) |\n"
        "| 2024-10-25T03:10:00 | KNC-iT11 | 4x180s | R | 19.2 +/- 0.2 |\n"
    )

    annotations = emit_photometry_table_annotations(doc)

    assert len(annotations) == 1
    assert annotations[0].label == "PHOTOMETRY_TABLE"
    assert annotations[0].rule_id == "photometry_table.pipe"
    assert annotations[0].needs_review
    assert annotations[0].comment == "Photometry table detected; per-row measurements pending parsing."
    assert annotations[0].verify(doc.rendered_text)


def test_sigma_ul_and_limiting_magnitude_headers_are_magnitude_not_error() -> None:
    sigma_doc = _doc(
        "| Mid time (UT) | Time since trigger (hr) | Band | 3 sigma UL (AB) |\n"
        "| ----- | ----- | ----- | ----- |\n"
        "| 2026-01-11 01:46:32 | 13.80 | r | 23.5 |\n"
        "| 2026-01-11 02:04:27 | 14.10 | z | 22.3 |\n"
    )
    limiting_doc = _doc(
        "JD (mid) | t_mid-t0 (hours)| Filter | Exposure (s) | Limiting Magnitude (5 sigma) |\n"
        "2460295.3278711 | 1.27 | r' | 5100 (stacked) | 22.0 |\n"
        "2460295.3648310 | 2.16 | g' | 1500 (stacked) | 21.0 |\n"
    )

    sigma_block = detect_table_blocks(sigma_doc.rendered_text)[0]
    limiting_block = detect_table_blocks(limiting_doc.rendered_text)[0]

    assert infer_column_roles(sigma_block)[3].role == "magnitude"
    assert infer_column_roles(limiting_block)[4].role == "magnitude"
    assert sigma_block.data_rows[0] == ["2026-01-11 01:46:32", "13.80", "r", "23.5"]


def test_upper_limit_error_header_is_magnitude_and_separator_rows_are_excluded() -> None:
    doc = _doc(
        "Sources | Tmid-T0 (day) | UT (start) | Upper Limit (error) | Exposure Time | Filter\n"
        "--------------------------------------------------------------------------------------------------------------\n"
        "Best-fit position | 0.764 | 23-01-22 22:10:44.8 | 18.79 (0.22) | 2*300s (co-added) | Clear\n"
        "\n"
        "4FGL J0100.3+0745 | 0.699 | 23-01-22 20:36:22.3 | 19.51 (0.03) | 8*300s (co-added) | Clear\n"
        "---------------------------------------------------------------------------------------------------------------\n"
    )

    block = detect_table_blocks(doc.rendered_text)[0]

    assert infer_column_roles(block)[3].role == "magnitude"
    assert block.data_rows[0][0] == "Best-fit position"
    assert all(not all(set(cell) <= {"-"} for cell in row) for row in block.data_rows)


def test_svom_pipe_header_with_whitespace_rows_is_captured() -> None:
    doc = _doc(
        "The preliminary measurements are in the AB magnitude:\n"
        "\n"
        "Mid time  |  Band | Exposure Time |  Brightness\n"
        "1.906  hr    VT_B      53*50 sec    19.70+/-0.05 mag\n"
        "1.906  hr    VT_R      53*50 sec    19.98+/-0.06 mag\n"
        "19.75  d     VT_B      17*50 sec    17.48+/-0.03 mag\n"
        "19.75  d     VT_R      17*50 sec    17.21+/-0.02 mag\n"
    )

    block = detect_table_blocks(doc.rendered_text)[0]

    assert block.delimiter_type == "whitespace"
    assert block.raw_header == "Mid time  |  Band | Exposure Time |  Brightness"
    assert len(block.data_rows) == 4
    assert block.data_rows[0] == ["1.906 hr", "VT_B", "53*50 sec", "19.70+/-0.05 mag"]
    assert _roles(block) == {0: "time", 1: "filter", 2: "exposure", 3: "magnitude"}


def test_noise_master_prose_block_is_discarded_but_real_pipe_table_remains() -> None:
    doc = _doc(
        "MASTER-Tavrida robotic telescope  (Global MASTER-Net: http://observ.pereplet.ru)  "
        "located in Russia started inspect of the Fermi GRB errorbox 32 sec after "
        "trigger time at 2023-10-28 22:26:37 UT, with upper limit up to 17.5 mag. "
        "The observations began at zenith distance = 57 deg. The sun altitude is -56.6 deg.\n"
        "\n"
        "Tmid-T0  |      Date Time      |          Site       | Coord (J2000) |Filt.| Expt. | Limit| Comment\n"
        "_________|_____________________|_____________________|______________|_____|_______|_______|________\n"
        "48 | 2023-10-28 22:26:37 | MASTER-Tavrida | (21h 09m 58.71s , +51d 52m 10.9s) | C | 10 | 16.6 |\n"
        "55 | 2023-10-28 22:26:43 | MASTER-Kislovodsk | (21h 00m 09.06s , +52d 25m 47.6s) | C | 10 | 14.4 |\n"
    )

    blocks = detect_table_blocks(doc.rendered_text)

    assert len(blocks) == 1
    assert blocks[0].delimiter_type == "pipe"
    assert len(blocks[0].data_rows) == 2


def test_detection_and_upper_limit_headers_remain_distinct_magnitude_columns() -> None:
    doc = _doc(
        "Magnitudes use a system declared in each row.\n"
        "\n"
        "T-T0 day|MJD|Obser.|Exposure|Filter|Mag +/- err|Upp.Lim.\n"
        "15.5|60237.097|KAO|13X180s|i|20.5+/-0.1 (AB)|22.0 (5sig)\n"
        "15.8|60237.438|KNC-T21|11x300s|Rc|19.5+/-0.15 (Vega)|20 (5sig)\n"
    )

    block = detect_table_blocks(doc.rendered_text)[0]
    roles = infer_column_roles(block)

    assert roles[5].role == "magnitude"
    assert roles[6].role == "magnitude"


def test_instrument_content_signature_rejects_remarks_and_lowercase_not() -> None:
    doc = _doc(
        "Photometry results.\n"
        "\n"
        "60237.097  R  18.5  not\n"
        "60237.198  R  18.7  S/N ~ 8\n"
        "60237.299  R  18.9  NOT\n"
    )

    block = detect_table_blocks(doc.rendered_text)[0]
    roles = infer_column_roles(block)

    assert roles[3].role != "instrument"


def test_iki_two_line_header_is_combined_and_rows_are_structured() -> None:
    doc = _doc(
        "The observational properties and preliminary photometry are provided below:\n\n"
        "Date,      UTstart, t-T0,   Exp., Filter, Mag, Err., UL\n"
        "                    (mid,d) (n*s)                    (3-sigma)\n"
        "2026-06-11 19:43:01 1.40315 2*300 Rc      19.73 0.03 22.6\n"
    )

    blocks = detect_table_blocks(doc.rendered_text)

    assert len(blocks) == 1
    block = blocks[0]
    assert block.header_line == "Date,      UTstart, t-T0,   Exp., Filter, Mag, Err., UL"
    assert block.raw_header == (
        "Date | UTstart | t-T0 (mid,d) | Exp. (n*s) | Filter | Mag | Err. | "
        "UL (3-sigma)"
    )
    assert block.data_rows == [
        ["2026-06-11", "19:43:01", "1.40315", "2*300", "Rc", "19.73", "0.03", "22.6"]
    ]
    assert _roles(block) == {
        0: "time",
        1: "time",
        2: "time",
        3: "exposure",
        4: "filter",
        5: "magnitude",
        6: "mag_error",
        7: "magnitude",
    }


def test_dfot_single_row_whitespace_table_is_detected() -> None:
    doc = _doc(
        "Date Mid_UT T_start-T0 (days) Filter  Exp time (s)  Magnitude\n"
        "=================================================================\n"
        "2026-06-15 17:24:09.406   ~4.73   R     300s*12     20.88 +/-0.05\n"
    )

    blocks = detect_table_blocks(doc.rendered_text)

    assert len(blocks) == 1
    assert blocks[0].data_rows == [
        ["2026-06-15", "17:24:09.406", "~4.73", "R", "300s*12", "20.88 +/-0.05"]
    ]
