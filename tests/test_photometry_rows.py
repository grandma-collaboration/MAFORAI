from __future__ import annotations

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.photometry_rows import (
    PhotometryRowParser,
    is_photometry_table,
    parse_table_to_measurements,
)
from skyportal_corpus.extraction_v2.photometry_tables import detect_table_blocks
from skyportal_corpus.extraction_v2.photometry_tables import infer_column_roles


def _doc(body: str):
    return render_canonical(circular_id=35457, subject="Photometry table", body=body)


def _measurements(body: str):
    doc = _doc(body)
    blocks = detect_table_blocks(doc.rendered_text)
    annotations = []
    for block in blocks:
        annotations.extend(parse_table_to_measurements(block, doc))
    return doc, blocks, annotations


def test_uvot_upper_limit_row_from_35457() -> None:
    doc, blocks, annotations = _measurements(
        "Preliminary 3-sigma upper limits using the UVOT photometric\n"
        "system\n"
        "for the first finding chart exposure are:\n"
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
    )

    assert len(blocks) == 1
    assert is_photometry_table(blocks[0])
    first = annotations[0]
    assert first.measurement_type == "upper_limit"
    assert first.magnitude_or_limit == "20.4"
    assert first.limit_sigma == "3"
    assert first.photometric_band == "white_FC"
    assert first.obs_time_raw == "168"
    assert first.obs_time_type == "relative_to_trigger"
    assert first.obs_time_reference == "trigger_time_t0"
    assert first.exposure_time_raw == "147"
    assert first.photometric_system == "Vega"
    assert not first.needs_review
    assert first.comment is None
    assert "system_from_uvot_convention" in first.provenance_inherited
    assert first.verify(doc.rendered_text)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_uvot_detection_with_error_from_35534() -> None:
    doc, _blocks, annotations = _measurements(
        "Preliminary magnitudes using the UVOT photometric system are:\n"
        "\n"
        "Filter         T_start(s)   T_stop(s)      Exp(s)         Mag\n"
        "\n"
        "white              121          236          113         16.98 +/- 0.04\n"
        "u                  310          520          206         >19.2\n"
        "uvw2               590          830          236         >20.1\n"
    )

    white = annotations[0]
    assert white.measurement_type == "detection"
    assert white.magnitude_or_limit == "16.98"
    assert white.magnitude_error == "0.04"
    assert white.limit_sigma is None
    assert white.photometric_band == "white"
    assert white.exposure_time_raw == "113"
    assert white.verify(doc.rendered_text)


def test_knc_row_prefers_mjd_over_relative_time_from_36326() -> None:
    doc, _blocks, annotations = _measurements(
        "Upper limits are reported at the 5-sigma limit,\n"
        "in the AB system.\n"
        "\n"
        "T-T0 (day)|    MJD   | Observatory | Exp. | Filter   | Upp.Mag.  | Comments\n"
        "------------------------------------------------------------------------------------------------------------\n"
        "3.58    |60426.477894 | KNC       |10x180s| Johnson V |  16.7     | calibrated in R, Gaia\n"
        "3.63    |60426.528530 | KNC       |7x180s | Rc        |  16.6     | calibrated in sdssg, PS1\n"
    )

    first = annotations[0]
    assert first.measurement_type == "upper_limit"
    assert first.magnitude_or_limit == "16.7"
    assert first.photometric_band == "Johnson V"
    assert first.instrument == "KNC"
    assert first.exposure_time_raw == "10x180s"
    assert first.obs_time_raw == "60426.477894"
    assert first.obs_time_type == "mjd"
    assert first.obs_time_reference == "absolute_time"
    assert first.photometric_system == "AB"
    assert "secondary_time_col=0:3.58(relative_to_trigger)" in first.provenance_inherited
    assert "calibrated in R, Gaia" not in (first.instrument or "")
    assert not first.needs_review
    assert first.verify(doc.rendered_text)


def test_vega_system_from_cell_and_observer_column_is_skipped_from_36050() -> None:
    doc, _blocks, annotations = _measurements(
        "Magnitudes are reported in AB system, except where noted in the cell.\n"
        "\n"
        "T-T0 day | MJD | Telescope | Observer | Exposure | Filter | Upper limit\n"
        "-----------------------------------------------------------------------\n"
        "1.10 | 60397.78045138 | Montarrenti 0.53m | S. Leonini | 3x180s | Rc | 18.9 (Vega)\n"
        "1.31 | 60397.98425636 | PlaneWave CDK 17\" | Y. Jongen | 1x180s | Rc | 20.1 (Vega)\n"
    )

    first = annotations[0]
    assert first.photometric_system == "Vega"
    assert first.instrument == "Montarrenti 0.53m"
    assert first.photometric_band == "Rc"
    assert first.magnitude_or_limit == "18.9"
    assert "S. Leonini" not in (first.instrument or "")
    assert first.verify(doc.rendered_text)


def test_magnitude_sanity_marks_row_for_review() -> None:
    doc, _blocks, annotations = _measurements(
        "Photometry in the AB system.\n"
        "\n"
        "T-T0 (day)|    MJD   | Observatory | Exp. | Filter   | Mag\n"
        "-----------------------------------------------------------------\n"
        "3.58    |60426.477894 | KNC       |10x180s| Johnson V |  99.9\n"
        "3.63    |60426.528530 | KNC       |7x180s | Rc        |  16.6\n"
    )

    first = annotations[0]
    assert first.magnitude_or_limit == "99.9"
    assert first.needs_review
    assert "magnitude outside expected optical range" in (first.comment or "")
    assert first.verify(doc.rendered_text)


def test_parser_extracts_all_table_rows_and_verifies() -> None:
    doc = _doc(
        "Photometry in the AB system.\n"
        "\n"
        "| Date | Tel | Exp | Filter | Mag |\n"
        "| 2024-10-25T02:46:16 | KNC-iT11 | 4x180s | R | >18.5 |\n"
        "| 2024-10-25T03:10:00 | KNC-iT11 | 4x180s | R | 19.2 +/- 0.2 |\n"
    )

    annotations = PhotometryRowParser().extract(doc)

    assert len(annotations) == 2
    assert annotations[0].measurement_type == "upper_limit"
    assert annotations[1].measurement_type == "detection"
    assert annotations[1].magnitude_or_limit == "19.2"
    assert annotations[1].magnitude_error == "0.2"
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_master_limit_header_makes_numeric_cell_an_upper_limit_and_clear_band_no_review() -> None:
    doc, _blocks, annotations = _measurements(
        "MASTER inspection table.\n"
        "\n"
        "Tmid | Date | Site | Coords | Filt. | Expt. | Limit\n"
        "----------------------------------------------------\n"
        "57 | 2024-01-01 12:58:15 | MASTER-Tunka | (00h 00m 36.90s , +32d 16m 39.5s) | C | 10 | 18.6\n"
        "77 | 2024-01-01 12:58:15 | MASTER-Tunka | (00h 00m 36.90s , +32d 16m 39.6s) | C | 50 | 19.6\n"
    )

    first = annotations[0]
    assert first.measurement_type == "upper_limit"
    assert first.magnitude_or_limit == "18.6"
    assert first.magnitude_error is None
    assert first.limit_sigma is None
    assert first.photometric_band == "C"
    assert first.photometric_system == "unknown"
    assert not first.needs_review
    assert first.comment is None
    assert "system_expected_unknown_for_clear_unfiltered" in first.provenance_inherited
    assert first.verify(doc.rendered_text)


def test_real_filter_without_system_still_needs_review() -> None:
    doc, _blocks, annotations = _measurements(
        "No photometric system is stated.\n"
        "\n"
        "T-T0 (day)|    MJD   | Observatory | Exp. | Filter   | Mag\n"
        "-----------------------------------------------------------------\n"
        "3.58    |60426.477894 | KNC       |10x180s| R |  18.6\n"
        "3.63    |60426.528530 | KNC       |7x180s | R |  18.8\n"
    )

    first = annotations[0]
    assert first.measurement_type == "detection"
    assert first.photometric_band == "R"
    assert first.photometric_system == "unknown"
    assert first.needs_review
    assert "photometric system is unknown" in (first.comment or "")
    assert first.verify(doc.rendered_text)


def test_multi_object_catalog_table_is_marked_for_review() -> None:
    doc, _blocks, annotations = _measurements(
        "Candidate table from a survey.\n"
        "\n"
        "| Name | AT | RA | DEC | Filter | Mag | Err |\n"
        "| ZTF23abtgfpu | AT2023ackx | 072.67 | +11.19 | r | 21.36 | 0.14 |\n"
        "| ZTF23abnoapt | AT2023wue | 102.91 | +48.07 | g | 17.98 | 0.03 |\n"
    )

    assert len(annotations) == 2
    first = annotations[0]
    assert first.measurement_type == "detection"
    assert first.photometric_band == "r"
    assert first.needs_review
    assert "multi-object catalog table" in (first.comment or "")
    assert first.verify(doc.rendered_text)


def test_numeric_non_photometry_table_is_not_parsed_as_measurements() -> None:
    doc = render_canonical(
        circular_id=35505,
        subject="Radio upper limits",
        body=(
            "Radio source-parameter table.\n"
            "\n"
            "T_mid  Freq  UL  r.m.s.  Beam      PA\n"
            "\n"
            "17.0     6        24     8         0.68x0.29    -71\n"
            "17.0     10       24     8         0.50x0.18    -65\n"
            "38.0     6        21     7         0.60x0.29    -74\n"
        ),
    )
    blocks = detect_table_blocks(doc.rendered_text)
    annotations = []
    for block in blocks:
        annotations.extend(parse_table_to_measurements(block, doc))

    assert len(blocks) == 1
    assert not is_photometry_table(blocks[0])
    assert annotations == []
    assert all((annotation.instrument or "") != "0.68x0.29" for annotation in annotations)


def test_positive_table_classification_for_master_uvot_and_knc() -> None:
    master_doc = _doc(
        "MASTER inspection table.\n"
        "\n"
        "Tmid | Date | Site | Coords | Filt. | Expt. | Limit\n"
        "----------------------------------------------------\n"
        "57 | 2024-01-01 12:58:15 | MASTER-Tunka | (00h 00m 36.90s , +32d 16m 39.5s) | C | 10 | 18.6\n"
        "77 | 2024-01-01 12:58:15 | MASTER-Tunka | (00h 00m 36.90s , +32d 16m 39.6s) | C | 50 | 19.6\n"
    )
    uvot_doc = _doc(
        "Preliminary upper limits using the UVOT photometric system are:\n"
        "\n"
        "Filter         T_start(s)   T_stop(s)      Exp(s)         Mag\n"
        "\n"
        "white_FC           168          318          147         >20.4\n"
        "white              168         1053          334         >20.8\n"
    )
    knc_doc = _doc(
        "Upper limits are reported in the AB system.\n"
        "\n"
        "T-T0 (day)|    MJD   | Observatory | Exp. | Filter   | Upp.Mag.  | Comments\n"
        "------------------------------------------------------------------------------------------------------------\n"
        "3.58    |60426.477894 | KNC       |10x180s| Johnson V |  16.7     | calibrated in R, Gaia\n"
        "3.63    |60426.528530 | KNC       |7x180s | Rc        |  16.6     | calibrated in sdssg, PS1\n"
    )

    assert is_photometry_table(detect_table_blocks(master_doc.rendered_text)[0])
    assert is_photometry_table(detect_table_blocks(uvot_doc.rendered_text)[0])
    assert is_photometry_table(detect_table_blocks(knc_doc.rendered_text)[0])


def test_separate_error_column_does_not_replace_magnitude_with_error_from_35584() -> None:
    doc, blocks, annotations = _measurements(
        "Near-infrared photometry.\n"
        "\n"
        "| Time | Mag | error | Filter |\n"
        "| 2024-01-06T05:22:36 | 15.10 | 0.04 | J |\n"
        "| 2024-01-07T02:43:37 | 15.56 | 0.07 | J |\n"
    )

    roles = infer_column_roles(blocks[0])
    assert roles[1].role == "magnitude"
    assert roles[2].role == "mag_error"
    first = annotations[0]
    assert first.magnitude_or_limit == "15.10"
    assert first.magnitude_error == "0.04"
    assert first.photometric_band == "J"
    assert "0.04" != first.magnitude_or_limit
    assert "magnitude outside expected optical range" not in (first.comment or "")
    assert first.verify(doc.rendered_text)


def test_adjacent_small_numeric_column_is_mag_error_not_magnitude_from_35687() -> None:
    doc, blocks, annotations = _measurements(
        "We obtained photometry in B, V, R, and I filters.\n"
        "\n"
        "T-T0 | Filter | Mag | Err | MJD\n"
        "223.98 | B | 16.12 | 0.017 | 60346.030\n"
        "233.30 | V | 15.74 | 0.009 | 60346.032\n"
    )

    roles = infer_column_roles(blocks[0])
    assert roles[2].role == "magnitude"
    assert roles[3].role == "mag_error"
    first = annotations[0]
    assert first.magnitude_or_limit == "16.12"
    assert first.magnitude_error == "0.017"
    assert first.photometric_band == "B"
    assert "0.017" != first.magnitude_or_limit
    assert "magnitude outside expected optical range" not in (first.comment or "")
    assert first.verify(doc.rendered_text)


def test_mag_err_header_with_plus_minus_cells_does_not_replace_magnitude_from_38758() -> None:
    doc, blocks, annotations = _measurements(
        "Optical photometry with CGFT.\n"
        "\n"
        "(T-T0)_mid(s)      mag     mag_err  band\n"
        "82          18.38    +/- 0.26  i\n"
        "172         17.37    +/- 0.08  g\n"
        "262         16.83    +/- 0.05  r\n"
    )

    roles = infer_column_roles(blocks[0])
    assert roles[1].role == "magnitude"
    assert roles[2].role == "mag_error"
    first = annotations[0]
    assert first.magnitude_or_limit == "18.38"
    assert first.magnitude_error == "0.26"
    assert first.photometric_band == "i"
    assert "magnitude outside expected optical range" not in (first.comment or "")
    assert first.verify(doc.rendered_text)


def test_adjacent_error_column_is_inferred_without_header() -> None:
    doc, blocks, annotations = _measurements(
        "Photometry in J band.\n"
        "\n"
        "| 2024-01-06T05:22:36 | 15.10 | 0.04 | J |\n"
        "| 2024-01-07T02:43:37 | 15.56 | 0.07 | J |\n"
    )

    roles = infer_column_roles(blocks[0])
    assert roles[1].role == "magnitude"
    assert roles[2].role == "mag_error"
    assert annotations[0].magnitude_or_limit == "15.10"
    assert annotations[0].magnitude_error == "0.04"
    assert annotations[0].photometric_band == "J"


def test_upper_limit_error_parentheses_are_preserved_from_33228() -> None:
    doc, blocks, annotations = _measurements(
        "The upper limits are given as follows.\n"
        "\n"
        "Sources | Tmid-T0 (day) | UT (start) | Upper Limit (error) | Exposure Time | Filter\n"
        "--------------------------------------------------------------------------------------------------------------\n"
        "Best-fit position | 0.764 | 23-01-22 22:10:44.8 | 18.79 (0.22) | 2*300s (co-added) | Clear\n"
        "\n"
        "4FGL J0100.3+0745 | 0.699 | 23-01-22 20:36:22.3 | 19.51 (0.03) | 8*300s (co-added) | Clear\n"
        "---------------------------------------------------------------------------------------------------------------\n"
    )

    assert infer_column_roles(blocks[0])[3].role == "magnitude"
    first = annotations[0]
    assert first.measurement_type == "upper_limit"
    assert first.magnitude_or_limit == "18.79"
    assert first.magnitude_error == "0.22"
    assert first.photometric_band == "Clear"
    assert first.exposure_time_raw == "2*300s (co-added)"
    assert first.verify(doc.rendered_text)


def test_svom_vt_rows_with_units_from_42887() -> None:
    doc, blocks, annotations = _measurements(
        "The measurements are given below in AB magnitudes:\n"
        "\n"
        "  Mid_time        Band        Exposure Time       Magnitude (AB)\n"
        "12.43 min         VT_B            50 sec         18.16+/-0.03 mag\n"
        "12.43 min         VT_R            50 sec         17.89+/-0.03 mag\n"
        "44.96 min         VT_B            50 sec         19.11+/-0.04 mag\n"
        "44.96 min         VT_R            50 sec         18.80+/-0.03 mag\n"
    )

    assert len(blocks[0].data_rows) == 4
    first = annotations[0]
    assert first.measurement_type == "detection"
    assert first.magnitude_or_limit == "18.16"
    assert first.magnitude_error == "0.03"
    assert first.photometric_band == "VT_B"
    assert first.exposure_time_raw == "50 sec"
    assert first.obs_time_raw == "12.43 min"
    assert first.obs_time_type == "relative_to_trigger"
    assert first.obs_time_reference == "trigger_time_t0"
    assert first.photometric_system == "AB"
    assert first.verify(doc.rendered_text)


def test_radio_surface_brightness_table_is_rejected_from_37978() -> None:
    doc = _doc(
        "Radio VLA results.\n"
        "\n"
        "+-----------+-----------------------+--------------+----------+----------+\n"
        "| Frequency | Peak surf. brightness | r.m.s. noise | Beam size | Beam P.A. |\n"
        "+-----------+-----------------------+--------------+----------+----------+\n"
        "|   (GHz)   |      (uJy/beam)       |  (uJy/beam)  | arcsec^2 |   deg    |\n"
        "|     6     |         171           |      8       | 1.34x0.28 |    60    |\n"
        "|    10     |         138           |      7       | 0.93x0.17 |    57    |\n"
        "+-----------+-----------------------+--------------+----------+----------+\n"
    )

    blocks = detect_table_blocks(doc.rendered_text)
    assert len(blocks) == 1
    assert not is_photometry_table(blocks[0])
    assert parse_table_to_measurements(blocks[0], doc) == []


def test_svom_vt_pipe_header_and_whitespace_rows_from_44284() -> None:
    doc, blocks, annotations = _measurements(
        "The preliminary measurements are in the AB magnitude:\n"
        "\n"
        "Mid time  |  Band | Exposure Time |  Brightness\n"
        "1.906  hr    VT_B      53*50 sec    19.70+/-0.05 mag\n"
        "1.906  hr    VT_R      53*50 sec    19.98+/-0.06 mag\n"
        "19.75  d     VT_B      17*50 sec    17.48+/-0.03 mag\n"
        "19.75  d     VT_R      17*50 sec    17.21+/-0.02 mag\n"
    )

    assert blocks[0].raw_header == "Mid time  |  Band | Exposure Time |  Brightness"
    assert len(annotations) == 4
    first = annotations[0]
    assert first.magnitude_or_limit == "19.70"
    assert first.magnitude_error == "0.05"
    assert first.photometric_band == "VT_B"
    assert first.exposure_time_raw == "53*50 sec"
    assert first.obs_time_raw == "1.906 hr"
    assert first.obs_time_type == "relative_to_trigger"
    assert first.photometric_system == "AB"
    assert first.verify(doc.rendered_text)


def test_svom_vt_rows_with_continuation_source_from_43720() -> None:
    doc, blocks, annotations = _measurements(
        "The following preliminary magnitudes are in AB system:\n"
        "\n"
        "    ID.          Mid time.        Band        Exposure Time     Magnitude (AB)\n"
        "Source1.         2.35 hour        VT_R        16*70 sec         22.5+/-0.3 mag\n"
        "                 5.63 hour        VT_R        12*70 sec         >22.6 mag\n"
        "                 1.52 hour        VT_B        16*70 sec         >23.0 mag\n"
        "                 5.95 hour        VT_B        6*70 sec          >22.5 mag\n"
    )

    assert len(blocks[0].data_rows) == 4
    assert len(annotations) == 4
    second = annotations[1]
    assert second.measurement_type == "upper_limit"
    assert second.magnitude_or_limit == "22.6"
    assert second.magnitude_error is None
    assert second.photometric_band == "VT_R"
    assert second.exposure_time_raw == "12*70 sec"
    assert second.obs_time_raw == "5.63 hour"
    assert second.obs_time_type == "relative_to_trigger"
    assert second.photometric_system == "AB"
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_band_encoded_in_magnitude_header_from_34078() -> None:
    doc, blocks, annotations = _measurements(
        "Optical photometry is reported below.\n"
        "\n"
        "UT-start              MJD_mid       t-T0(d)     R_mag\n"
        "2023-03-10 01:23:45   60013.12345   1.23        21.68 +/- 0.05\n"
        "2023-03-10 02:23:45   60013.16499   1.27        22.12 +/- 0.08\n"
    )

    assert is_photometry_table(blocks[0])
    first = annotations[0]
    assert first.photometric_band == "R"
    assert first.magnitude_or_limit == "21.68"
    assert first.magnitude_error == "0.05"
    assert first.obs_time_raw == "60013.12345"
    assert first.obs_time_type == "mjd"
    assert first.verify(doc.rendered_text)


def test_xinglong_pipe_rows_with_blank_lines_from_38607() -> None:
    doc, blocks, annotations = _measurements(
        "We summarize our observation results as follows:\n"
        "\n"
        "Obs. No. | Time (UTC)        | Exposure Time (s) | Filter | Apparent mag (AB) | Telescope Name\n"
        "\n"
        "1      | 2024-12-17 10:12:27 | 6x600 s        | Clear |> 21.0           | Xinglong 80-cm Telescope\n"
        "\n"
        "2      | 2024-12-17 16:50:08 | 6x600 s        | Clear | 21.4 +/- 0.14   | Xinglong 2.16-m Telescope\n"
    )

    assert len(blocks[0].data_rows) == 2
    assert annotations[0].measurement_type == "upper_limit"
    assert annotations[0].magnitude_or_limit == "21.0"
    assert annotations[0].magnitude_error is None
    assert annotations[1].measurement_type == "detection"
    assert annotations[1].magnitude_or_limit == "21.4"
    assert annotations[1].magnitude_error == "0.14"
    assert annotations[1].photometric_band == "Clear"
    assert annotations[1].photometric_system == "AB"
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_goto_abmag_rows_with_blank_lines_from_44837() -> None:
    doc, blocks, annotations = _measurements(
        "Observations were taken in the GOTO-L filter. The optical counterpart was detected:\n"
        "\n"
        "| mid-time(UT) | t-t0(hr) | ABmag |\n"
        "\n"
        "| 2026-06-04 23:46:15 | 3.46 | 18.45 ± 0.04 |\n"
        "\n"
        "| 2026-06-05 00:54:05 | 4.59 | 18.70 ± 0.08 |\n"
        "\n"
        "| 2026-06-05 02:00:28 | 5.70 | 19.06 ± 0.12 |\n"
    )

    assert len(blocks[0].data_rows) == 3
    assert len(annotations) == 3
    first = annotations[0]
    assert first.magnitude_or_limit == "18.45"
    assert first.magnitude_error == "0.04"
    assert first.photometric_system == "AB"
    assert first.photometric_band is None
    assert first.verify(doc.rendered_text)


def test_grandma_detection_and_limit_columns_emit_two_measurements_per_row_from_34887() -> None:
    doc, blocks, annotations = _measurements(
        "Magnitudes and upper limits are reported in the AB and Vega system "
        "depending on the filter set.\n"
        "\n"
        "T-T0 day|MJD|Obser.|Exposure|Filter|Mag +/- err|Upp.Lim.\n"
        "15.5|60237.097|KAO|13X180s|i|20.5+/-0.1 (AB)|22.0 (5sig)\n"
        "15.8|60237.438|KNC-T21|11x300s|Rc|19.5+/-0.15 (Vega)|20 (5sig)\n"
    )

    roles = infer_column_roles(blocks[0])
    assert roles[5].role == "magnitude"
    assert roles[6].role == "magnitude"
    assert len(annotations) == 4

    first_row = [annotation for annotation in annotations if annotation.text.startswith("15.5|")]
    assert [(annotation.measurement_type, annotation.magnitude_or_limit) for annotation in first_row] == [
        ("detection", "20.5"),
        ("upper_limit", "22.0"),
    ]
    assert first_row[0].magnitude_error == "0.1"
    assert first_row[0].limit_sigma is None
    assert first_row[1].magnitude_error is None
    assert first_row[1].limit_sigma == "5"
    assert all(annotation.photometric_system == "AB" for annotation in first_row)
    assert all(annotation.photometric_band == "i" for annotation in first_row)

    second_row = [annotation for annotation in annotations if annotation.text.startswith("15.8|")]
    assert [(annotation.measurement_type, annotation.magnitude_or_limit) for annotation in second_row] == [
        ("detection", "19.5"),
        ("upper_limit", "20"),
    ]
    assert second_row[0].magnitude_error == "0.15"
    assert second_row[0].limit_sigma is None
    assert second_row[1].limit_sigma == "5"
    assert all(annotation.photometric_system == "Vega" for annotation in second_row)
    assert all(annotation.photometric_band == "Rc" for annotation in second_row)
    assert all("photometric_system=context" not in annotation.provenance_inherited for annotation in annotations)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_limit_sigma_from_limiting_magnitude_header() -> None:
    _doc, _blocks, annotations = _measurements(
        "Photometry in the AB system.\n\n"
        "MJD|Filter|Limiting Magnitude (5 sigma)\n"
        "60397.100|r|22.0\n"
        "60397.200|i|21.0\n"
    )

    assert len(annotations) == 2
    assert annotations[0].measurement_type == "upper_limit"
    assert annotations[0].magnitude_or_limit == "22.0"
    assert annotations[0].magnitude_error is None
    assert annotations[0].limit_sigma == "5"


def test_limit_sigma_from_prefix_header_with_system() -> None:
    _doc, _blocks, annotations = _measurements(
        "Optical upper limits.\n\n"
        "MJD|Filter|3 sigma UL (AB)\n"
        "60397.100|r|23.5\n"
        "60397.200|i|22.3\n"
    )

    assert len(annotations) == 2
    assert annotations[0].measurement_type == "upper_limit"
    assert annotations[0].magnitude_or_limit == "23.5"
    assert annotations[0].limit_sigma == "3"
    assert annotations[0].photometric_system == "AB"


def test_context_sigma_applies_only_to_uvot_upper_limits() -> None:
    _doc, _blocks, annotations = _measurements(
        "Preliminary 3-sigma upper limits using the UVOT photometric system are:\n\n"
        "Filter|T_start(s)|T_stop(s)|Exp(s)|Mag\n"
        "white|38363|67383|4551|21.46+/-0.11\n"
        "white|90644|106641|4612|>22.76\n"
    )

    assert len(annotations) == 2
    detection, upper_limit = annotations
    assert detection.measurement_type == "detection"
    assert detection.magnitude_or_limit == "21.46"
    assert detection.magnitude_error == "0.11"
    assert detection.limit_sigma is None
    assert upper_limit.measurement_type == "upper_limit"
    assert upper_limit.magnitude_or_limit == "22.76"
    assert upper_limit.magnitude_error is None
    assert upper_limit.limit_sigma == "3"


def test_iki_row_emits_detection_and_three_sigma_limit_with_combined_time() -> None:
    doc, blocks, annotations = _measurements(
        "The observational properties and preliminary photometry are provided below:\n\n"
        "Date,      UTstart, t-T0,   Exp., Filter, Mag, Err., UL\n"
        "                    (mid,d) (n*s)                    (3-sigma)\n"
        "2026-06-11 19:43:01 1.40315 2*300 Rc      19.73 0.03 22.6\n"
    )

    assert len(blocks) == 1
    assert len(annotations) == 2
    detection, upper_limit = annotations
    assert detection.measurement_type == "detection"
    assert detection.magnitude_or_limit == "19.73"
    assert detection.magnitude_error == "0.03"
    assert detection.limit_sigma is None
    assert upper_limit.measurement_type == "upper_limit"
    assert upper_limit.magnitude_or_limit == "22.6"
    assert upper_limit.magnitude_error is None
    assert upper_limit.limit_sigma == "3"
    assert all(annotation.photometric_band == "Rc" for annotation in annotations)
    assert all(annotation.exposure_time_raw == "2*300" for annotation in annotations)
    assert all(annotation.obs_time_raw == "2026-06-11 19:43:01" for annotation in annotations)
    assert all(annotation.obs_time_type == "utc_datetime" for annotation in annotations)
    assert all(annotation.obs_time_reference == "absolute_time" for annotation in annotations)
    assert all("time value does not match" not in (annotation.comment or "") for annotation in annotations)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_separate_date_and_clock_columns_are_combined_from_44919() -> None:
    doc, _blocks, annotations = _measurements(
        "| Date | UTstart | t-T0 (d) | Exp (n*s) | Filter | Mag | Err |\n"
        "| 2026-06-11 | 21:41:52 | 0.913 | 3*180 | SDSS-r | 20.04 | 0.06 |\n"
        "| 2026-06-11 | 22:03:58 | 0.928 | 3*180 | Rc | 19.85 | 0.06 |\n"
    )

    first = annotations[0]
    assert first.obs_time_raw == "2026-06-11 21:41:52"
    assert first.obs_time_type == "utc_datetime"
    assert first.obs_time_reference == "absolute_time"
    assert "time value does not match expected subtype" not in (first.comment or "")
    assert "secondary_time_col=2:0.913(relative_to_trigger)" in first.provenance_inherited
    assert first.verify(doc.rendered_text)


def test_dfot_single_row_uses_combined_date_and_clock() -> None:
    doc, _blocks, annotations = _measurements(
        "Date Mid_UT T_start-T0 (days) Filter  Exp time (s)  Magnitude\n"
        "=================================================================\n"
        "2026-06-15 17:24:09.406   ~4.73   R     300s*12     20.88 +/-0.05\n"
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.magnitude_or_limit == "20.88"
    assert annotation.magnitude_error == "0.05"
    assert annotation.photometric_band == "R"
    assert annotation.exposure_time_raw == "300s*12"
    assert annotation.obs_time_raw == "2026-06-15 17:24:09.406"
    assert annotation.verify(doc.rendered_text)


def test_mixed_system_context_is_not_inherited_without_a_row_system() -> None:
    _doc, _blocks, annotations = _measurements(
        "Magnitudes are in AB and Vega systems depending on the filter.\n"
        "\n"
        "MJD|Telescope|Filter|Upper limit\n"
        "60237.097|KAO|i|22.0\n"
        "60237.438|KNC-T21|Rc|20.0\n"
    )

    assert all(annotation.photometric_system == "unknown" for annotation in annotations)
    assert all("varies by row or filter" in (annotation.comment or "") for annotation in annotations)


def test_invalid_instrument_cells_are_rejected_but_uppercase_not_is_valid() -> None:
    _doc, _blocks, annotations = _measurements(
        "Photometry in the AB system.\n"
        "\n"
        "MJD|Filter|Mag|Telescope\n"
        "60237.097|R|18.5|not\n"
        "60237.198|R|18.7|S/N ~ 8\n"
        "60237.299|R|18.9|NOT\n"
    )

    assert [annotation.instrument for annotation in annotations] == [None, None, "NOT"]


def test_misaligned_uvot_header_does_not_emit_exposure_as_second_magnitude() -> None:
    _doc, _blocks, annotations = _measurements(
        "UVOT photometry.\n"
        "\n"
        "Filter      T_start(s) T_stop(s)   Exp(s)   Mag\n"
        "white        99525      110441      2265     21.28 +/- 0.16\n"
        "white       133031      208070      2931     22.09 +/- 0.32\n"
        "white       212899      420530      3418    >22.25\n"
    )

    assert [annotation.magnitude_or_limit for annotation in annotations] == [
        "21.28",
        "22.09",
        "22.25",
    ]
