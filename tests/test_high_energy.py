from __future__ import annotations

import pytest

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.high_energy import HighEnergyPropertyExtractor


def _extract(body: str, subject: str = "GRB high-energy report"):
    doc = render_canonical(circular_id=1, subject=subject, body=body)
    annotations = HighEnergyPropertyExtractor().extract(doc)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)
    assert all(
        annotation.text == doc.rendered_text[annotation.span_start : annotation.span_end]
        for annotation in annotations
    )
    return annotations


def test_epeak_from_parameterized_cutoff_energy() -> None:
    annotations = _extract(
        "The cutoff energy, parameterized as Epeak, is 46.8 +/- 0.4 keV."
    )

    assert len(annotations) == 1
    assert annotations[0].value == "Epeak = 46.8 +/- 0.4"
    assert annotations[0].unit == "keV"
    assert annotations[0].rule_id == "high_energy.epeak"


def test_fluence_preserves_scientific_notation_and_energy_band() -> None:
    annotations = _extract(
        "The event fluence (10-1000 keV) in this time interval is "
        "(1.30 +/- 0.02)E-05 erg/cm^2."
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.value == "fluence = (1.30 +/- 0.02)E-05"
    assert annotation.unit == "erg/cm^2"
    assert annotation.comment is not None
    assert "10-1000 keV" in annotation.comment
    assert annotation.needs_review is False


def test_power_law_index_is_dimensionless() -> None:
    annotations = _extract("The power law index is -1.50 +/- 0.01.")

    assert len(annotations) == 1
    assert annotations[0].value == "power law index = -1.50 +/- 0.01"
    assert annotations[0].unit == ""
    assert annotations[0].needs_review is False


def test_alpha_and_beta_are_separate_properties() -> None:
    annotations = _extract("alpha = -1.4800 +/- 0.0009 and beta = -3.17 +/- 0.01")

    assert [(annotation.value, annotation.unit) for annotation in annotations] == [
        ("alpha = -1.4800 +/- 0.0009", ""),
        ("beta = -3.17 +/- 0.01", ""),
    ]


def test_eiso_about_is_tentative() -> None:
    annotations = _extract("From these values we calculate the isotropic energy Eiso is about 8.8E51 erg.")

    assert len(annotations) == 1
    assert annotations[0].value == "Eiso = 8.8E51"
    assert annotations[0].unit == "erg"
    assert annotations[0].certainty == "tentative"


def test_peak_photon_flux() -> None:
    annotations = _extract(
        "The 1-sec peak photon flux measured starting from T0+3.8 s in the "
        "10-1000 keV band is 7.7 +/- 0.3 ph/s/cm^2."
    )

    assert len(annotations) == 1
    assert annotations[0].value == "peak photon flux = 7.7 +/- 0.3"
    assert annotations[0].unit == "ph/s/cm^2"


def test_peak_flux_stops_at_first_value_and_not_column_density() -> None:
    annotations = _extract(
        "The peak flux is around 9.09 x 10^-9 erg/s/cm^2 with a fixed Galactic "
        "hydrogen column density of 2.98 x 10^20 cm^-2."
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.value == "peak energy flux = 9.09 x 10^-9"
    assert annotation.unit == "erg/cm^2/s"
    assert "2.98" not in annotation.text
    assert annotation.needs_review is False


@pytest.mark.parametrize(
    ("body", "expected_value", "expected_unit"),
    [
        (
            "The peak flux is 2.5 x 10^-7 erg/cm^2/s.",
            "peak energy flux = 2.5 x 10^-7",
            "erg/cm^2/s",
        ),
        (
            "The fluence is 1.3 x 10^-5 erg/cm^2.",
            "fluence = 1.3 x 10^-5",
            "erg/cm^2",
        ),
        (
            "The isotropic energy Eiso is 8.8 x 10^51 erg.",
            "Eiso = 8.8 x 10^51",
            "erg",
        ),
    ],
)
def test_times_ten_scientific_notation(
    body: str,
    expected_value: str,
    expected_unit: str,
) -> None:
    annotations = _extract(body)

    assert len(annotations) == 1
    assert annotations[0].value == expected_value
    assert annotations[0].unit == expected_unit


def test_plus_hyphen_error_and_alternate_photon_flux_unit() -> None:
    annotations = _extract(
        "The 1-sec peak photon flux in the 15-150 keV band is "
        "2.1 + - 0.3 ph/cm2/sec."
    )

    assert len(annotations) == 1
    assert annotations[0].value == "peak photon flux = 2.1 +/- 0.3"
    assert annotations[0].unit == "ph/s/cm^2"
    assert annotations[0].needs_review is False


@pytest.mark.parametrize(
    ("body", "expected_value"),
    [
        (
            "The spectrum is described by a powerlaw model with a photon index of 2.",
            "photon index = 2",
        ),
        (
            "The fitted photon index 2.5(+1.7/-1.2), and the unabsorbed flux follows.",
            "photon index = 2.5(+1.7/-1.2)",
        ),
        (
            "The average X-ray spectrum has a photon index of 1.7.",
            "photon index = 1.7",
        ),
        (
            "The X-ray spectral index is -1.8 +/- 0.2.",
            "spectral index = -1.8 +/- 0.2",
        ),
        (
            "The X-ray spectrum has Gamma = 1.7.",
            "photon index = 1.7",
        ),
    ],
)
def test_photon_and_spectral_index_aliases(body: str, expected_value: str) -> None:
    annotations = _extract(body)

    assert len(annotations) == 1
    assert annotations[0].value == expected_value
    assert annotations[0].unit == ""
    assert annotations[0].needs_review is False


@pytest.mark.parametrize(
    ("body", "expected_value"),
    [
        (
            "The power law index of the time-averaged\nspectrum is 1.77 +- 0.08.",
            "power law index = 1.77 +/- 0.08",
        ),
        (
            "The X-ray model has photon index fixed at 2.",
            "photon index = 2",
        ),
        (
            "The X-ray spectrum has a photon index of approximately 4.2.",
            "photon index = 4.2",
        ),
    ],
)
def test_index_bridge_variants(body: str, expected_value: str) -> None:
    annotations = _extract(body)

    assert len(annotations) == 1
    assert annotations[0].value == expected_value


def test_radio_spectral_index_is_rejected() -> None:
    assert _extract(
        "The MeerKAT radio source has a spectral index of -0.7 at 3 GHz."
    ) == []


def test_column_density_is_not_a_high_energy_property() -> None:
    assert _extract(
        "The fixed Galactic hydrogen column density is 2.98 x 10^20 cm^-2."
    ) == []


def test_konus_fluence_with_parenthesized_error_and_multiplier() -> None:
    annotations = _extract(
        "As observed by Konus-Wind, the burst had a fluence of "
        "2.74(-0.35,+0.39)x10^-5 erg/cm2."
    )

    assert len(annotations) == 1
    assert annotations[0].value == "fluence = 2.74(-0.35,+0.39)x10^-5"
    assert annotations[0].unit == "erg/cm^2"
    assert annotations[0].needs_review is False


def test_bat_fluence_with_plus_minus_and_times_ten_notation() -> None:
    annotations = _extract(
        "The fluence in the 15-150 keV band is 1.6 +- 0.3 x 10^-7 erg/cm2."
    )

    assert len(annotations) == 1
    assert annotations[0].value == "fluence = 1.6 +/- 0.3 x 10^-7"
    assert annotations[0].unit == "erg/cm^2"


def test_fluence_with_star_e_exponent() -> None:
    annotations = _extract(
        "The total 4-120 keV fluence is (1.08 +/- 0.06)*E-6 erg/cm^2."
    )

    assert len(annotations) == 1
    assert annotations[0].value == "fluence = (1.08 +/- 0.06)*E-6"
    assert annotations[0].unit == "erg/cm^2"
    assert annotations[0].needs_review is False


@pytest.mark.parametrize(
    "body",
    [
        "The optical counterpart has r = 21.3 +/- 0.2 mag.",
        "The host redshift is z = 0.473.",
        "We measure a flux density of approximately 0.3 mJy.",
    ],
)
def test_non_high_energy_values_are_rejected(body: str) -> None:
    assert _extract(body) == []


@pytest.mark.parametrize(
    ("body", "expected_values"),
    [
        (
            "with alpha = -1.00(-0.23,+0.27) and Ep = 251(-49,+81) keV.\n"
            "with alpha = -0.40(-0.44,+0.56) and Ep = 259(-45,+64) keV.",
            ["Epeak = 251(-49,+81)", "Epeak = 259(-45,+64)"],
        ),
        (
            "and Ep = 1000(-16,+15) keV.\n"
            "and Ep = 1321(-62,+60) keV.",
            ["Epeak = 1000(-16,+15)", "Epeak = 1321(-62,+60)"],
        ),
        (
            "the peak energy Ep = 202(-6,+6) keV\n"
            "and Ep = 782(-52,+55) keV.",
            ["Epeak = 202(-6,+6)", "Epeak = 782(-52,+55)"],
        ),
        (
            "and Ep = 634(-181,+393) keV.\n"
            "and Ep = 361(-118,+292) keV.\n"
            "and Ep = 187(-74,+228) keV.",
            [
                "Epeak = 634(-181,+393)",
                "Epeak = 361(-118,+292)",
                "Epeak = 187(-74,+228)",
            ],
        ),
        (
            "and Ep < 41 keV.\n"
            "the peak energy Ep = 154(-5,+5) keV\n"
            "the peak energy Ep = 251(-12,+12) keV",
            ["Epeak < 41", "Epeak = 154(-5,+5)", "Epeak = 251(-12,+12)"],
        ),
        (
            "with alpha = -1.38(-0.13,+0.14) and Ep = 56(-5,+4) keV.\n"
            "with alpha = -1.16(-0.17,+0.19) and Ep = 68(-9,+8) keV.",
            ["Epeak = 56(-5,+4)", "Epeak = 68(-9,+8)"],
        ),
        (
            "and Ep = 495(-60,+72) keV.\n"
            "and Ep = 44 (-19,+11) keV.",
            ["Epeak = 495(-60,+72)", "Epeak = 44(-19,+11)"],
        ),
        (
            "and Ep = 354(-47,+64) keV.\n"
            "and Ep = 350(-85,+147) keV.",
            ["Epeak = 354(-47,+64)", "Epeak = 350(-85,+147)"],
        ),
    ],
)
def test_konus_ep_is_normalized_to_epeak(
    body: str,
    expected_values: list[str],
) -> None:
    epeak = [
        annotation
        for annotation in _extract(body)
        if annotation.rule_id == "high_energy.epeak"
    ]

    assert [annotation.value for annotation in epeak] == expected_values
    assert all(annotation.unit == "keV" for annotation in epeak)
    assert all(annotation.certainty == "confirmed" for annotation in epeak)


def test_konus_ep_excludes_model_formula_and_rest_frame_quantities() -> None:
    annotations = _extract(
        "dN/dE ~ (E^alpha)*exp(-E*(2+alpha)/Ep).\n"
        "The rest-frame energies are Ep,i,z to ~860 keV and Ep,p,z to ~890 keV.\n"
        "The peak energy flux is 3.08 x 10^-6 erg/cm^2/s.\n"
        "The cutoff energy, parameterized as Epeak, is 46.8 +/- 0.4 keV."
    )

    epeak = [annotation for annotation in annotations if annotation.rule_id == "high_energy.epeak"]
    assert [annotation.value for annotation in epeak] == ["Epeak = 46.8 +/- 0.4"]
    assert all("Ep,i,z" not in annotation.text for annotation in annotations)
    assert all("Ep,p,z" not in annotation.text for annotation in annotations)


@pytest.mark.parametrize(
    ("body", "expected_values"),
    [
        (
            "an upper limit on the high energy photon index beta of -2.5.\n"
            "an upper limit on the high energy photon index beta of -2.7.",
            ["beta < -2.5", "beta < -2.7"],
        ),
        (
            "an upper limit on the high energy photon index: beta < -5.4\n"
            "an upper limit on the high energy photon index: beta < -4.3",
            ["beta < -5.4", "beta < -4.3"],
        ),
        (
            "an upper limit on the high energy photon index: beta < -3.3",
            ["beta < -3.3"],
        ),
        (
            "an upper limit on the high energy photon index: beta < -1.7\n"
            "an upper limit on the high energy photon index: beta < -1.7\n"
            "an upper limit on the high energy photon index: beta < -1.7",
            ["beta < -1.7", "beta < -1.7", "beta < -1.7"],
        ),
        (
            "only an upper limit on the high energy photon index\nbeta of -2.8",
            ["beta < -2.8"],
        ),
        (
            "an upper limit on the high energy photon index: beta <= -3.1\n"
            "beta < -3.0",
            ["beta < -3.1", "beta < -3.0"],
        ),
        (
            "an upper limit on the high energy photon index: beta < -2.2\n"
            "an upper limit on the high energy photon index: beta < -2.8",
            ["beta < -2.2", "beta < -2.8"],
        ),
    ],
)
def test_beta_upper_limits_are_not_photon_index_measurements(
    body: str,
    expected_values: list[str],
) -> None:
    annotations = _extract(body)

    assert [annotation.value for annotation in annotations] == expected_values
    assert all(annotation.rule_id == "high_energy.beta" for annotation in annotations)
    assert all(annotation.unit == "" for annotation in annotations)
    assert all(annotation.certainty == "confirmed" for annotation in annotations)
    assert all(annotation.comment is None for annotation in annotations)
    assert not any(annotation.value.startswith("photon index =") for annotation in annotations)


def test_power_law_and_photon_indices_remain_point_estimates() -> None:
    annotations = _extract(
        "photon index -1.42 +/- 0.04.\n"
        "power law index is -1.2 +/- 0.1.\n"
        "power-law index of -0.03 +/- 0.4."
    )

    assert [annotation.value for annotation in annotations] == [
        "photon index = -1.42 +/- 0.04",
        "power law index = -1.2 +/- 0.1",
        "power law index = -0.03 +/- 0.4",
    ]


def test_existing_beta_measurements_remain_point_estimates() -> None:
    annotations = _extract(
        "beta = -2.95(-0.12,+0.10), beta = -2.56(-0.08,+0.07), "
        "beta = -2.4 +/- 0.1 and beta = -2.2 +/- 0.1"
    )

    assert [annotation.value for annotation in annotations] == [
        "beta = -2.95(-0.12,+0.10)",
        "beta = -2.56(-0.08,+0.07)",
        "beta = -2.4 +/- 0.1",
        "beta = -2.2 +/- 0.1",
    ]


@pytest.mark.parametrize(
    ("body", "expected_value"),
    [
        ("Using z=2.702, we find Eiso = 1.5e+53 erg.", "Eiso = 1.5e+53"),
        (
            "we estimate the burst isotropic energy release E_iso to "
            "(6.95 ± 2.49)x10^52 erg",
            "Eiso = (6.95 +/- 2.49)x10^52",
        ),
        (
            "we estimate the burst isotropic energy release E_iso to "
            "(4.60 ± 0.14)x10^53 erg",
            "Eiso = (4.60 +/- 0.14)x10^53",
        ),
        (
            "the burst isotropic equivalent radiated energy, parameterized as Eiso, "
            "is (1.76 +/- 0.76)E+53 erg",
            "Eiso = (1.76 +/- 0.76)E+53",
        ),
        ("The inferred Eiso of 8.8e+51 erg is preliminary.", "Eiso = 8.8e+51"),
    ],
)
def test_eiso_notation_variants(body: str, expected_value: str) -> None:
    annotations = _extract(body)

    assert len(annotations) == 1
    assert annotations[0].value == expected_value
    assert annotations[0].unit == "erg"


def test_liso_is_out_of_scope() -> None:
    assert _extract(
        "the isotropic peak luminosity L_iso to (1.49 ± 0.44)x10^53 erg/s and "
        "Liso = 7.5e+52 erg s-1"
    ) == []


@pytest.mark.parametrize(
    ("body", "expected_value", "expected_unit"),
    [
        (
            "a 64-ms peak energy flux, measured from T0,\n"
            "of (3.08 ± 0.90)x10^-6 erg/cm^2/s",
            "peak energy flux = (3.08 +/- 0.90)x10^-6",
            "erg/cm^2/s",
        ),
        (
            "a 64-ms peak flux, measured from T0+6.224 s,\n"
            "of 6.66(-0.42,+0.46)x10^-4 erg/cm2/s",
            "peak energy flux = 6.66(-0.42,+0.46)x10^-4",
            "erg/cm^2/s",
        ),
        (
            "a 64-ms peak flux, measured from T0+0.106s,\n"
            "of 4.16(-0.52,+0.54)x10^-5 erg/cm2/s",
            "peak energy flux = 4.16(-0.52,+0.54)x10^-5",
            "erg/cm^2/s",
        ),
        (
            "a 64-ms peak flux, measured from T0+0.262 s,\n"
            "of 1.14(-0.24,+0.35)x10^-5 erg/cm2/s",
            "peak energy flux = 1.14(-0.24,+0.35)x10^-5",
            "erg/cm^2/s",
        ),
        (
            "the 64-ms peak flux, measured from T0+35.776 s,\n"
            "of 2.03(-0.15,+0.15)x10^-5 erg/cm2/s",
            "peak energy flux = 2.03(-0.15,+0.15)x10^-5",
            "erg/cm^2/s",
        ),
        (
            "a 64-ms peak energy flux, measured from T0 + 0.832 s,\n"
            "of (1.78 ± 0.22)x10^-6 erg/cm^2/s",
            "peak energy flux = (1.78 +/- 0.22)x10^-6",
            "erg/cm^2/s",
        ),
        (
            "the 16-ms peak flux, measured from T0+0.104 s,\n"
            "of 4.41(-0.54,+0.58)x10^-5 erg/cm2/s",
            "peak energy flux = 4.41(-0.54,+0.58)x10^-5",
            "erg/cm^2/s",
        ),
        (
            "the 64-ms peak flux, measured from T0-0.224 s,\n"
            "of 2.51(-0.71,+0.80)x10^-6 erg/cm2/s",
            "peak energy flux = 2.51(-0.71,+0.80)x10^-6",
            "erg/cm^2/s",
        ),
        (
            "The 1-sec peak photon flux measured\nstarting from T0+14 s in the "
            "10-1000 keV band is 10.9 +/- 0.3 ph/s/cm^2.",
            "peak photon flux = 10.9 +/- 0.3",
            "ph/s/cm^2",
        ),
        (
            "The 64-ms peak photon flux measured\nstarting from T0-0.19 s in the "
            "10-1000 keV band is 11 +/- 3 ph/s/cm^2.",
            "peak photon flux = 11 +/- 3",
            "ph/s/cm^2",
        ),
        (
            "The 1-sec peak photon flux measured starting from T0+0.0024 s in the "
            "10-1000 keV band\nis 16.6 +/- 0.3 ph/s/cm^2.",
            "peak photon flux = 16.6 +/- 0.3",
            "ph/s/cm^2",
        ),
    ],
)
def test_real_peak_flux_formats(
    body: str,
    expected_value: str,
    expected_unit: str,
) -> None:
    annotations = _extract(body)

    assert len(annotations) == 1
    assert annotations[0].value == expected_value
    assert annotations[0].unit == expected_unit
    assert annotations[0].certainty == "confirmed"
    assert annotations[0].rule_id == "high_energy.peak_flux"


def test_circular_without_peak_flux_does_not_invent_one() -> None:
    annotations = _extract(
        "The time-integrate spectrum is best fit by a power law function. "
        "The event fluence (10-1000 keV) is (2.13 +/- 0.48)E-07 erg/cm^2. "
        "The isotropic energy, parameterized as Eiso, is (1.76 +/- 0.76)E+53 erg."
    )

    assert not any(annotation.rule_id == "high_energy.peak_flux" for annotation in annotations)


def test_multiline_and_single_line_fluences_are_all_captured() -> None:
    annotations = _extract(
        "The total fluence (10-1000 keV)\n"
        "in this time interval is (2.7 +/- 0.1)E-06 erg/cm^2.\n"
        "The total fluence (10-1000 keV) during this time interval is "
        "(7.5 +/- 0.4)E-06 erg/cm^2.\n"
        "The event fluence (10-1000 keV) in this time interval is "
        "(9.6 +/- 0.5)E-06 erg/cm^2."
    )

    assert [annotation.value for annotation in annotations] == [
        "fluence = (2.7 +/- 0.1)E-06",
        "fluence = (7.5 +/- 0.4)E-06",
        "fluence = (9.6 +/- 0.5)E-06",
    ]


def test_konus_comments_use_each_governing_clause_band() -> None:
    annotations = _extract(
        "As observed by Konus-Wind, the burst had\n"
        "a total fluence of (4.91 ± 1.76)x10^-6 erg/cm^2 and\n"
        "a 64-ms peak energy flux, measured from T0,\n"
        "of (3.08 ± 0.90)x10^-6 erg/cm^2/s "
        "(both in the 20 keV - 10 MeV energy range).\n\n"
        "The time-integrated spectrum of the burst is best fit in the "
        "20 keV - 15 MeV range by a power law with exponential cutoff model\n"
        "with alpha = -1.00(-0.23,+0.27) and Ep = 251(-49,+81) keV.\n"
        "Fitting this spectrum by a Band function yields an upper limit on the "
        "high energy photon index beta of -2.5.\n\n"
        "The spectrum near the peak count rate is best fit in the "
        "20 keV - 15 MeV range by a CPL model\n"
        "with alpha = -0.40(-0.44,+0.56) and Ep = 259(-45,+64) keV.\n"
        "Fitting this spectrum by a Band function yields an upper limit on the "
        "high energy photon index beta of -2.7.\n\n"
        "We estimate the burst isotropic energy release E_iso to "
        "(6.95 ± 2.49)x10^52 erg.",
        subject="Konus-Wind detection of GRB 230818A",
    )
    comments = {annotation.value: annotation.comment for annotation in annotations}

    assert comments["fluence = (4.91 +/- 1.76)x10^-6"] == (
        "Konus-Wind, 20 keV - 10 MeV"
    )
    assert comments["peak energy flux = (3.08 +/- 0.90)x10^-6"] == (
        "Konus-Wind, 20 keV - 10 MeV"
    )
    for value in (
        "alpha = -1.00(-0.23,+0.27)",
        "Epeak = 251(-49,+81)",
        "beta < -2.5",
        "alpha = -0.40(-0.44,+0.56)",
        "Epeak = 259(-45,+64)",
        "beta < -2.7",
    ):
        assert comments[value] == "Konus-Wind, 20 keV - 15 MeV"
    assert comments["Eiso = (6.95 +/- 2.49)x10^52"] == "Konus-Wind"
    assert all(annotation.comment is not None for annotation in annotations)


def test_fermi_comments_propagate_observation_band_across_analysis_paragraphs() -> None:
    annotations = _extract(
        "The time-averaged spectrum from T0+0.003 to T0+29.440 s is best fit by\n"
        "a power law function with an exponential high-energy cutoff.\n"
        "The power law index is -1.07 +/- 0.03 and the cutoff energy,\n"
        "parameterized as Epeak, is 280 +/- 20 keV.\n\n"
        "The event fluence (10-1000 keV) in this time interval is\n"
        "(1.46 +/- 0.04)E-05 erg/cm^2. The 1-sec peak photon flux measured\n"
        "starting from T0+14 s in the 10-1000 keV band is "
        "10.9 +/- 0.3 ph/s/cm^2.\n\n"
        "A Band function fits the spectrum equally well with Epeak= 201 +/- 20 keV, "
        "alpha = -0.95 +/- 0.05 and beta = -2.1 +/- 0.1.",
        subject="GRB 240527B: Fermi GBM Observation",
    )

    assert {annotation.comment for annotation in annotations} == {
        "Fermi/GBM, 10-1000 keV"
    }
    assert [annotation.value for annotation in annotations] == [
        "power law index = -1.07 +/- 0.03",
        "Epeak = 280 +/- 20",
        "fluence = (1.46 +/- 0.04)E-05",
        "peak photon flux = 10.9 +/- 0.3",
        "Epeak = 201 +/- 20",
        "alpha = -0.95 +/- 0.05",
        "beta = -2.1 +/- 0.1",
    ]


def test_derived_energy_band_does_not_leak_into_observed_spectral_parameters() -> None:
    annotations = _extract(
        "The time-averaged spectrum is best fit by a power law function with an "
        "exponential high-energy cutoff. The power law index is -1.2 +/- 0.1 and "
        "the cutoff energy, parameterized as Epeak, is 702 +/- 278 keV. "
        "Considering the redshift and best fit model, we find the isotropic "
        "equivalent luminosity Liso = 7.5e+52 erg s-1 (1-10000 keV).\n\n"
        "The event fluence (10-1000 keV) in this time interval is "
        "(2.8 +/- 0.2)E-06 erg/cm^2.\n\n"
        "Using z=2.702, we find Eiso = 1.5e+53 erg (1-10000 keV) when fitting "
        "the spectrum with a power-law index of -0.03 +/- 0.4 and cutoff energy, "
        "parameterized as Epeak, of 221 +/- 30 keV.",
        subject=(
            "GRB 241105A: Fermi GBM Observation of a Short Burst with "
            "Extended Emission"
        ),
    )
    comments = {annotation.value: annotation.comment for annotation in annotations}

    assert comments["power law index = -1.2 +/- 0.1"] == "Fermi/GBM"
    assert comments["Epeak = 702 +/- 278"] == "Fermi/GBM"
    assert comments["fluence = (2.8 +/- 0.2)E-06"] == "Fermi/GBM, 10-1000 keV"
    assert comments["Eiso = 1.5e+53"] == "Fermi/GBM, 1-10000 keV"
    assert comments["power law index = -0.03 +/- 0.4"] == "Fermi/GBM"
    assert comments["Epeak = 221 +/- 30"] == "Fermi/GBM"
    assert "1-10000 keV" not in comments["Epeak = 702 +/- 278"]
    assert all(annotation.comment is not None for annotation in annotations)


def test_neighboring_instrument_does_not_override_high_energy_reporter() -> None:
    annotations = _extract(
        "The event fluence (20-1000 keV) is 1.3e-05 erg/cm^2, while Swift-BAT "
        "reported a later episode.",
        subject="Konus-Wind detection of GRB 240529A",
    )

    assert len(annotations) == 1
    assert annotations[0].value == "fluence = 1.3e-05"
    assert annotations[0].comment == "Konus-Wind, 20-1000 keV"


def test_same_clause_instrument_overrides_high_energy_reporter() -> None:
    annotations = _extract(
        "Swift-BAT reports the fluence in the 15-150 keV band is "
        "1.6e-07 erg/cm^2.",
        subject="Fermi GBM follow-up of a joint detection",
    )

    assert len(annotations) == 1
    assert annotations[0].value == "fluence = 1.6e-07"
    assert annotations[0].comment == "Swift/BAT, 15-150 keV"
