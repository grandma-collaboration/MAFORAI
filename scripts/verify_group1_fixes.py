from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import CanonicalDocument, iter_real_circulars, render_canonical  # noqa: E402
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation  # noqa: E402
from skyportal_corpus.extraction_v2.duration import DurationExtractor  # noqa: E402
from skyportal_corpus.extraction_v2.high_energy import HighEnergyPropertyExtractor  # noqa: E402


CIRCULAR_IDS = {
    33427,
    33511,
    34511,
    35256,
    35377,
    36553,
    36584,
    37139,
    38104,
    38123,
    39375,
    39498,
    39542,
    43013,
    40087,
    43405,
    43634,
    43712,
    44597,
    44806,
}

EXPECTED_EPEAK = {
    33427: ["Epeak = 1000(-16,+15)", "Epeak = 1321(-62,+60)"],
    34511: ["Epeak = 251(-49,+81)", "Epeak = 259(-45,+64)"],
    35256: ["Epeak = 202(-6,+6)", "Epeak = 782(-52,+55)"],
    36553: ["Epeak = 280 +/- 20", "Epeak = 201 +/- 20"] * 2,
    36584: ["Epeak = 161(-100,+203)", "Epeak = 210(-33,+26)"],
    38104: ["Epeak = 702 +/- 278", "Epeak = 221 +/- 30"],
    38123: ["Epeak = 214 +/- 59", "Epeak = 455 +/- 335"],
    39498: [
        "Epeak = 634(-181,+393)",
        "Epeak = 361(-118,+292)",
        "Epeak = 187(-74,+228)",
    ],
    40087: ["Epeak = 56(-5,+4)", "Epeak = 68(-9,+8)"],
    43013: ["Epeak < 41", "Epeak = 154(-5,+5)", "Epeak = 251(-12,+12)"],
    43405: ["Epeak = 354(-47,+64)", "Epeak = 350(-85,+147)"],
    43634: [
        "Epeak = 350 +/- 65",
        "Epeak = 32 +/- 4",
        "Epeak = 67 +/- 9",
        "Epeak = 52 +/- 10",
    ],
    43712: ["Epeak = 495(-60,+72)", "Epeak = 44(-19,+11)"],
}

EXPECTED_BETA_LIMITS = {
    33427: ["beta < -5.4", "beta < -4.3"],
    34511: ["beta < -2.5", "beta < -2.7"],
    35256: ["beta < -3.3"],
    39498: ["beta < -1.7"] * 3,
    40087: ["beta < -3.5", "beta < -4.2"],
    43013: ["beta < -2.8"],
    43405: ["beta < -2.2", "beta < -2.8"],
    43712: ["beta < -3.1", "beta < -3.0"],
}

EXPECTED_PEAK_FLUX = {
    33427: ["peak energy flux = 6.66(-0.42,+0.46)x10^-4"],
    34511: ["peak energy flux = (3.08 +/- 0.90)x10^-6"],
    35256: ["peak energy flux = 4.16(-0.52,+0.54)x10^-5"],
    36553: ["peak photon flux = 10.9 +/- 0.3"] * 2,
    36584: ["peak energy flux = 3.40(-0.93,+1.10)x10^-6"],
    38104: ["peak photon flux = 11 +/- 3"],
    38123: [],
    39498: ["peak energy flux = 1.14(-0.24,+0.35)x10^-5"],
    40087: ["peak energy flux = (1.78 +/- 0.22)x10^-6"],
    43013: ["peak energy flux = 2.03(-0.15,+0.15)x10^-5"],
    43405: ["peak energy flux = 2.51(-0.71,+0.80)x10^-6"],
    43634: ["peak photon flux = 16.6 +/- 0.3"],
    43712: ["peak energy flux = 4.41(-0.54,+0.58)x10^-5"],
}

EXPECTED_EISO = {
    34511: ["Eiso = (6.95 +/- 2.49)x10^52"],
    36584: ["Eiso = 2.2(-0.8,+0.7)x10^54"],
    38104: ["Eiso = 1.5e+53"],
    38123: ["Eiso = (1.76 +/- 0.76)E+53"],
    40087: ["Eiso = (4.60 +/- 0.14)x10^53"],
}

NON_COMMENT_FIELDS = (
    "span_start",
    "span_end",
    "text",
    "label",
    "target",
    "certainty",
    "value",
    "unit",
    "rule_id",
    "needs_review",
)
BASELINE_NON_COMMENT_DIGESTS = {
    33427: "c7cc49af1bed4c580bee39c0de4944c9d6e4fb7d18063cbee07918a668d48982",
    33511: "ae99a9bace3bf9ca0f871ae90b63123d7e2bb399ac6acd5dabf8f044bd4f497c",
    34511: "53143a4cac2bb8d9a2adf0624311d563fb899337c729ffa6d3b3ce603fb60afa",
    35256: "5eb11e6e3c4ab6dc7516c4c68137053ab31fc4d667962039e18eaac61ffee737",
    35377: "87d8d042bb89e0da74d6577a95914f83baf442d7e67aa4f1bcc7187cb6b68a51",
    36553: "4ca40c8af044fdf38746ae3693111adfd16fb2459aecc1de6f17c507be9a4b10",
    36584: "90ef150e02b16e8790742956c325bc678ba7461c278bae5a200801893abec9d3",
    37139: "cc35e6f39a00e2d24fafa43948f9fff65c98c898119b69e758eaa92d77708d02",
    38104: "d155ac9622f8d7f001c32bf2a0b701172e801aff790da53829851829802d3522",
    38123: "2b823d0edc4c779755c192b01a85904abe9051f7e7255bd1f3cf89ef972aff9a",
    39375: "f852b6d37637dcc2d3f993128edecc7f628f6c6b57e88242eb99e527a1e0b844",
    39498: "c72846220fa608d6be5003ac72a6e24978998c853d601319fa33d791977e296c",
    39542: "dc8a2769e02444f40348c60892941af40c817cfb25c9fa79294bf81e6680bf0f",
    40087: "7a01783c277db49248134cb2ee11cfe2e556e665c8581a6902a1d035b6cf5049",
    43013: "b6cca6368b5931afe77f71cc12de0fc69cb81605e93b3a7af97bf5379fcfa2fe",
    43405: "66178075f11178c4b9d524afdfe2fdec7cf1f1dbceda1d1d34e0cf3102eed1fe",
    43634: "6ef144f1e2dbe658b94de52a139e76a874f50f4aa761473066d4378dba31f7ef",
    43712: "5ec7139902e8887c05db90f0ca977babdb7dff4511e30d964729b651d4d801e4",
    44597: "6d221f3ee8277b6742ffb8894d09bce6e8e8bfb2f8df2d6b1192351cabe92a47",
    44806: "904eba4125cdb13c2bf077c628b30dc2eadb58ce3f7f5cbd452baedcc647e04c",
}
EXPECTED_COMMENT_ANCHORS = {
    34511: [
        ("~ 10", "Konus-Wind"),
        ("fluence = (4.91 +/- 1.76)x10^-6", "Konus-Wind, 20 keV - 10 MeV"),
        (
            "peak energy flux = (3.08 +/- 0.90)x10^-6",
            "Konus-Wind, 20 keV - 10 MeV",
        ),
        ("alpha = -1.00(-0.23,+0.27)", "Konus-Wind, 20 keV - 15 MeV"),
        ("Epeak = 251(-49,+81)", "Konus-Wind, 20 keV - 15 MeV"),
        ("beta < -2.5", "Konus-Wind, 20 keV - 15 MeV"),
        ("alpha = -0.40(-0.44,+0.56)", "Konus-Wind, 20 keV - 15 MeV"),
        ("Epeak = 259(-45,+64)", "Konus-Wind, 20 keV - 15 MeV"),
        ("beta < -2.7", "Konus-Wind, 20 keV - 15 MeV"),
        ("Eiso = (6.95 +/- 2.49)x10^52", "Konus-Wind"),
    ],
    36553: [
        ("about 24.8", "Fermi/GBM, 50-300 keV"),
        ("about 24.8", "Fermi/GBM, 50-300 keV"),
        ("power law index = -1.07 +/- 0.03", "Fermi/GBM, 10-1000 keV"),
        ("power law index = -1.07 +/- 0.03", "Fermi/GBM, 10-1000 keV"),
        ("Epeak = 280 +/- 20", "Fermi/GBM, 10-1000 keV"),
        ("Epeak = 280 +/- 20", "Fermi/GBM, 10-1000 keV"),
        ("fluence = (1.46 +/- 0.04)E-05", "Fermi/GBM, 10-1000 keV"),
        ("fluence = (1.46 +/- 0.04)E-05", "Fermi/GBM, 10-1000 keV"),
        ("peak photon flux = 10.9 +/- 0.3", "Fermi/GBM, 10-1000 keV"),
        ("peak photon flux = 10.9 +/- 0.3", "Fermi/GBM, 10-1000 keV"),
        ("Epeak = 201 +/- 20", "Fermi/GBM, 10-1000 keV"),
        ("Epeak = 201 +/- 20", "Fermi/GBM, 10-1000 keV"),
        ("alpha = -0.95 +/- 0.05", "Fermi/GBM, 10-1000 keV"),
        ("alpha = -0.95 +/- 0.05", "Fermi/GBM, 10-1000 keV"),
        ("beta = -2.1 +/- 0.1", "Fermi/GBM, 10-1000 keV"),
        ("beta = -2.1 +/- 0.1", "Fermi/GBM, 10-1000 keV"),
    ],
    36584: [
        ("~ 150", "Konus-Wind"),
        ("fluence = 1.3(-0.5,+0.4)x10^-4", "Konus-Wind, 20 keV - 10 MeV"),
        (
            "peak energy flux = 3.40(-0.93,+1.10)x10^-6",
            "Konus-Wind, 20 keV - 10 MeV",
        ),
        ("alpha = -1.11(-0.36,+1.61)", "Konus-Wind, 20 keV - 3 MeV"),
        ("beta = -2.02(-7.98,+0.22)", "Konus-Wind, 20 keV - 3 MeV"),
        ("Epeak = 161(-100,+203)", "Konus-Wind, 20 keV - 3 MeV"),
        ("alpha = -1.00(-0.10,+0.15)", "Konus-Wind, 20 keV - 3 MeV"),
        ("beta = -2.85(-1.37,+0.50)", "Konus-Wind, 20 keV - 3 MeV"),
        ("Epeak = 210(-33,+26)", "Konus-Wind, 20 keV - 3 MeV"),
        ("Eiso = 2.2(-0.8,+0.7)x10^54", "Konus-Wind"),
    ],
    38104: [
        ("about 1.4", "Fermi/GBM, 50-300 keV"),
        ("power law index = -1.2 +/- 0.1", "Fermi/GBM"),
        ("Epeak = 702 +/- 278", "Fermi/GBM"),
        ("fluence = (2.8 +/- 0.2)E-06", "Fermi/GBM, 10-1000 keV"),
        ("Eiso = 1.5e+53", "Fermi/GBM, 1-10000 keV"),
    ],
    43634: [
        ("about 56", "Fermi/GBM, 50-300 keV"),
        ("power law index = -1.18 +/- 0.07", "Fermi/GBM, 10-1000 keV"),
        ("Epeak = 350 +/- 65", "Fermi/GBM, 10-1000 keV"),
        ("fluence = (2.7 +/- 0.1)E-06", "Fermi/GBM, 10-1000 keV"),
        ("Epeak = 32 +/- 4", "Fermi/GBM, 10-1000 keV"),
        ("alpha = -1.7 +/- 0.1", "Fermi/GBM, 10-1000 keV"),
        ("beta = -2.4 +/- 0.1", "Fermi/GBM, 10-1000 keV"),
        ("fluence = (7.5 +/- 0.4)E-06", "Fermi/GBM, 10-1000 keV"),
        ("power law index = -1.83 +/- 0.05", "Fermi/GBM, 10-1000 keV"),
        ("Epeak = 67 +/- 9", "Fermi/GBM, 10-1000 keV"),
        ("Epeak = 52 +/- 10", "Fermi/GBM, 10-1000 keV"),
        ("alpha = -1.7 +/- 0.1", "Fermi/GBM, 10-1000 keV"),
        ("beta = -2.2 +/- 0.1", "Fermi/GBM, 10-1000 keV"),
        ("fluence = (9.6 +/- 0.5)E-06", "Fermi/GBM, 10-1000 keV"),
        ("peak photon flux = 16.6 +/- 0.3", "Fermi/GBM, 10-1000 keV"),
    ],
}

EXPECTED_DURATION_COMMENTS = {
    33511: [("~ 68.9", "Konus-Wind")],
    34511: [("~ 10", "Konus-Wind")],
    35377: [("~ 25", "Konus-Wind")],
    36553: [("about 24.8", "Fermi/GBM, 50-300 keV")] * 2,
    36584: [("~ 150", "Konus-Wind")],
    37139: [("~ 36.9", "Konus-Wind")],
    39375: [("~ 22", "Konus-Wind")],
    39542: [("~ 32", "Konus-Wind")],
    43013: [
        ("about 25.8", "Konus-Wind"),
        ("~ 25", "Konus-Wind"),
        ("~ 48", "Konus-Wind"),
    ],
    43634: [("about 56", "Fermi/GBM, 50-300 keV")],
    44597: [("~ 43.4", "Konus-Wind")],
    44806: [("~ 230", "Konus-Wind")],
}


def main() -> int:
    circulars = {
        int(circular["circular_id"]): dict(circular)
        for circular in iter_real_circulars(limit=100000)
        if int(circular["circular_id"]) in CIRCULAR_IDS
    }
    checks: list[tuple[str, bool, str]] = []
    extracted: dict[int, list[EventEvidenceAnnotation]] = {}

    _add_check(
        checks,
        "all requested circulars loaded",
        set(circulars) == CIRCULAR_IDS,
        f"loaded={sorted(circulars)}",
    )

    duration_extractor = DurationExtractor()
    high_energy_extractor = HighEnergyPropertyExtractor()
    durations: dict[int, list[EventEvidenceAnnotation]] = {}
    all_extracted: dict[int, list[EventEvidenceAnnotation]] = {}
    for circular_id in sorted(circulars):
        doc = _render(circulars[circular_id])
        duration = duration_extractor.extract(doc)
        high_energy = high_energy_extractor.extract(doc)
        durations[circular_id] = duration
        extracted[circular_id] = high_energy
        all_annotations = duration + high_energy
        all_extracted[circular_id] = all_annotations
        _add_check(
            checks,
            f"{circular_id} all offsets verify",
            all(
                annotation.verify(doc.rendered_text)
                and annotation.text
                == doc.rendered_text[annotation.span_start : annotation.span_end]
                for annotation in all_annotations
            ),
            f"duration={len(duration)}, high_energy={len(high_energy)}",
        )
        digest = _non_comment_digest(all_annotations)
        _add_check(
            checks,
            f"{circular_id} non-comment fields unchanged",
            digest == BASELINE_NON_COMMENT_DIGESTS[circular_id],
            f"sha256={digest}",
        )

    for circular_id, expected in sorted(EXPECTED_EPEAK.items()):
        actual = _rule_values(extracted[circular_id], "high_energy.epeak")
        _add_counter_check(checks, f"{circular_id} Epeak", actual, expected)

    for circular_id, expected in sorted(EXPECTED_BETA_LIMITS.items()):
        actual = [
            annotation.value
            for annotation in extracted[circular_id]
            if annotation.rule_id == "high_energy.beta" and annotation.value.startswith("beta <")
        ]
        _add_counter_check(checks, f"{circular_id} beta limits", actual, expected)

    for circular_id, expected in sorted(EXPECTED_PEAK_FLUX.items()):
        actual = _rule_values(extracted[circular_id], "high_energy.peak_flux")
        _add_counter_check(checks, f"{circular_id} peak flux", actual, expected)

    for circular_id, expected in sorted(EXPECTED_EISO.items()):
        actual = _rule_values(extracted[circular_id], "high_energy.eiso")
        _add_counter_check(checks, f"{circular_id} Eiso", actual, expected)

    _add_counter_check(
        checks,
        "38104 point-estimate indices",
        [
            annotation.value
            for annotation in extracted[38104]
            if annotation.rule_id in {
                "high_energy.photon_index",
                "high_energy.powerlaw_index",
            }
        ],
        [
            "power law index = -1.2 +/- 0.1",
            "photon index = -1.42 +/- 0.04",
            "power law index = -0.03 +/- 0.4",
        ],
    )
    _add_counter_check(
        checks,
        "43634 multiline and single-line fluences",
        _rule_values(extracted[43634], "high_energy.fluence"),
        [
            "fluence = (2.7 +/- 0.1)E-06",
            "fluence = (7.5 +/- 0.4)E-06",
            "fluence = (9.6 +/- 0.5)E-06",
        ],
    )

    for circular_id, expected in EXPECTED_COMMENT_ANCHORS.items():
        expected_values = {value for value, _ in expected}
        actual = [
            (annotation.value, annotation.comment)
            for annotation in all_extracted[circular_id]
            if annotation.value in expected_values
        ]
        _add_counter_check(
            checks,
            f"{circular_id} comment anchors",
            actual,
            expected,
        )

    for circular_id, expected in EXPECTED_DURATION_COMMENTS.items():
        actual = [
            (annotation.value, annotation.comment)
            for annotation in durations[circular_id]
        ]
        _add_counter_check(
            checks,
            f"{circular_id} duration reporting instrument",
            actual,
            expected,
        )

    _add_check(
        checks,
        "all requested circulars have comments on every Group 1 annotation",
        all(
            annotation.comment is not None
            for annotations in all_extracted.values()
            for annotation in annotations
        ),
        "duration and high-energy annotations checked",
    )
    epeak_702 = next(
        annotation
        for annotation in extracted[38104]
        if annotation.value == "Epeak = 702 +/- 278"
    )
    _add_check(
        checks,
        "38104 Epeak band does not leak from Liso",
        epeak_702.comment == "Fermi/GBM"
        and "1-10000 keV" not in (epeak_702.comment or ""),
        f"comment={epeak_702.comment!r}",
    )
    _add_counter_check(
        checks,
        "T90 comments remain exact",
        [
            (annotation.value, annotation.comment)
            for circular_id in (36553, 38104, 43634)
            for annotation in durations[circular_id]
            if annotation.label == "T90"
        ],
        [
            ("about 24.8", "Fermi/GBM, 50-300 keV"),
            ("about 24.8", "Fermi/GBM, 50-300 keV"),
            ("about 1.4", "Fermi/GBM, 50-300 keV"),
            ("about 56", "Fermi/GBM, 50-300 keV"),
        ],
    )

    all_high_energy = [annotation for values in extracted.values() for annotation in values]
    forbidden_photon_values = {
        "photon index = -2.5",
        "photon index = -2.7",
        "photon index = -3.5",
        "photon index = -4.2",
        "photon index = -2.8",
    }
    _add_check(
        checks,
        "mislabelled photon-index beta values absent",
        not any(annotation.value in forbidden_photon_values for annotation in all_high_energy),
        "forbidden values checked",
    )
    _add_check(
        checks,
        "Liso and L_iso absent",
        not any("liso" in annotation.text.lower().replace("_", "") for annotation in all_high_energy),
        "all annotation spans checked",
    )
    _add_check(
        checks,
        "rest-frame Ep variants absent",
        not any(
            token in annotation.text
            for annotation in all_high_energy
            for token in ("Ep,i,z", "Ep,p,z", "Ep,z")
        ),
        "all annotation spans checked",
    )
    _add_check(
        checks,
        "model-formula Ep absent",
        not any("/Ep)" in annotation.text for annotation in all_high_energy),
        "all annotation spans checked",
    )

    failures = [result for result in checks if not result[1]]
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'} | {name} | {detail}")
    print(f"FINAL | passed={len(checks) - len(failures)} failed={len(failures)} total={len(checks)}")
    return 1 if failures else 0


def _render(circular: Mapping[str, Any]) -> CanonicalDocument:
    return render_canonical(
        circular_id=int(circular["circular_id"]),
        subject=str(circular.get("subject") or ""),
        body=str(circular.get("body") or ""),
        event_id=circular.get("event_id"),
        created_on=circular.get("created_on"),
        submitter=circular.get("submitter"),
    )


def _rule_values(
    annotations: list[EventEvidenceAnnotation],
    rule_id: str,
) -> list[str]:
    return [annotation.value for annotation in annotations if annotation.rule_id == rule_id]


def _non_comment_digest(annotations: list[EventEvidenceAnnotation]) -> str:
    payload = [
        {field: getattr(annotation, field) for field in NON_COMMENT_FIELDS}
        for annotation in annotations
    ]
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _add_counter_check(
    checks: list[tuple[str, bool, str]],
    name: str,
    actual: list[Any],
    expected: list[Any],
) -> None:
    passed = Counter(actual) == Counter(expected)
    _add_check(checks, name, passed, f"actual={actual!r}")


def _add_check(
    checks: list[tuple[str, bool, str]],
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append((name, passed, detail))


if __name__ == "__main__":
    raise SystemExit(main())
