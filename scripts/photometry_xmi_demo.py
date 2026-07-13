from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import iter_real_circulars, render_canonical  # noqa: E402
from skyportal_corpus.extraction_v2.photometry_prose import ProsePhotometryExtractor  # noqa: E402
from skyportal_corpus.extraction_v2.photometry_rows import parse_table_to_measurements  # noqa: E402
from skyportal_corpus.extraction_v2.photometry_tables import detect_table_blocks  # noqa: E402
from skyportal_corpus.inception_v2.photometry_xmi_export import (  # noqa: E402
    PHOTOMETRY_FEATURES,
    export_photometry_xmi,
    get_photometry_typesystem_features,
    photometry_feature_values,
    photometry_roundtrip_check,
)


TARGET_CIRCULAR_ID = 34887
TYPESYSTEM_PATH = PROJECT_ROOT / "data" / "inception" / "TypeSystem.xml"


def main() -> int:
    circular = next(
        (
            item
            for item in iter_real_circulars(min_year=2023, limit=None)
            if int(item["circular_id"]) == TARGET_CIRCULAR_ID
        ),
        None,
    )
    if circular is None:
        print(f"Circular {TARGET_CIRCULAR_ID} was not found in the local corpus.")
        return 1

    doc = render_canonical(**circular)
    table_measurements = [
        measurement
        for block in detect_table_blocks(doc.rendered_text)
        for measurement in parse_table_to_measurements(block, doc)
    ]
    prose_measurements = ProsePhotometryExtractor().extract(doc)
    measurements = sorted(
        [*table_measurements, *prose_measurements],
        key=lambda item: (item.span_start, item.span_end, item.measurement_type),
    )
    if not measurements:
        print(f"Circular {TARGET_CIRCULAR_ID} produced no photometry measurements.")
        return 1

    for measurement in measurements:
        if not measurement.verify(doc.rendered_text):
            raise ValueError(
                f"Measurement failed offset verification: "
                f"{measurement.span_start}-{measurement.span_end}"
            )

    out_path = (
        PROJECT_ROOT
        / "data"
        / "inception"
        / "out"
        / f"{doc.circular_id}_photometry.xmi"
    )
    export_photometry_xmi(doc, measurements, TYPESYSTEM_PATH, out_path)
    roundtrip = photometry_roundtrip_check(
        out_path,
        doc.rendered_text,
        measurements,
        TYPESYSTEM_PATH,
    )
    roundtrip_ok = bool(
        roundtrip["text_matches"]
        and roundtrip["all_spans_ok"]
        and roundtrip["all_features_ok"]
        and roundtrip["n_original"] == roundtrip["n_roundtripped"]
    )

    print("REAL PHOTOMETRY TYPESYSTEM FEATURES")
    for feature_name, range_type in get_photometry_typesystem_features(TYPESYSTEM_PATH):
        print(f"  {feature_name}: {range_type}")

    print("\nSUMMARY")
    print(f"circular_id: {doc.circular_id}")
    print(f"subject: {doc.subject}")
    print(f"measurements: {len(measurements)}")
    print(f"by_type: {dict(sorted(Counter(item.measurement_type for item in measurements).items()))}")
    print(f"by_source: {{'table': {len(table_measurements)}, 'prose': {len(prose_measurements)}}}")

    print("\nEXPORTED MEASUREMENTS")
    available_features = {
        feature_name for feature_name, _range_type in get_photometry_typesystem_features(TYPESYSTEM_PATH)
    }
    for index, measurement in enumerate(measurements, start=1):
        values = photometry_feature_values(measurement)
        print(
            f"[{index}] span={measurement.span_start}-{measurement.span_end} "
            f"text={measurement.text!r}"
        )
        for feature_name in PHOTOMETRY_FEATURES:
            if feature_name in available_features:
                print(f"    {feature_name}={values[feature_name]!r}")

    print("\nROUND-TRIP")
    print(f"text_matches: {roundtrip['text_matches']}")
    print(f"all_spans_ok: {roundtrip['all_spans_ok']}")
    print(f"all_features_ok: {roundtrip['all_features_ok']}")
    print(f"n_original: {roundtrip['n_original']}")
    print(f"n_roundtripped: {roundtrip['n_roundtripped']}")
    print(f"discrepancies: {roundtrip['discrepancies']}")
    print(f"FINAL: {'OK' if roundtrip_ok else 'FAIL'}")
    print(f"XMI: {out_path}")
    return 0 if roundtrip_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
