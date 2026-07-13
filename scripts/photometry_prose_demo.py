from __future__ import annotations

from skyportal_corpus.canonical.document import iter_stratified_circulars, render_canonical
from skyportal_corpus.extraction_v2.photometry_prose import (
    ProsePhotometryExtractor,
    is_optical_circular,
)


PER_YEAR = 50
MAX_EXAMPLES = 8


def main() -> None:
    extractor = ProsePhotometryExtractor()
    total = 0
    optical = 0
    discarded = 0
    circulars_with_measurements = 0
    measurements_total = 0
    examples: list[tuple[dict, object, list]] = []

    for circular in iter_stratified_circulars(per_year=PER_YEAR):
        total += 1
        doc = render_canonical(
            circular_id=int(circular["circular_id"]),
            subject=str(circular.get("subject", "")),
            body=str(circular.get("body", "")),
            event_id=circular.get("event_id"),
            created_on=circular.get("created_on"),
            submitter=circular.get("submitter"),
        )
        if not is_optical_circular(doc.rendered_text):
            discarded += 1
            continue
        optical += 1
        annotations = extractor.extract(doc)
        if not annotations:
            continue
        circulars_with_measurements += 1
        measurements_total += len(annotations)
        if len(examples) < MAX_EXAMPLES:
            examples.append((circular, doc, annotations))

    for circular, doc, annotations in examples:
        print("=" * 100)
        print(f"circular_id: {circular['circular_id']}")
        print(f"subject: {circular.get('subject', '')}")
        print(f"measurements: {len(annotations)}")
        for index, annotation in enumerate(annotations, start=1):
            print("-" * 100)
            print(f"measurement: {index}")
            print(f"measurement_type: {annotation.measurement_type}")
            print(f"magnitude_or_limit: {annotation.magnitude_or_limit}")
            print(f"magnitude_error: {annotation.magnitude_error}")
            print(f"unit: {annotation.unit}")
            print(f"photometric_band: {annotation.photometric_band}")
            print(f"photometric_system: {annotation.photometric_system}")
            print(f"obs_time_raw: {annotation.obs_time_raw}")
            print(f"obs_time_type: {annotation.obs_time_type}")
            print(f"obs_time_reference: {annotation.obs_time_reference}")
            print(f"exposure_time_raw: {annotation.exposure_time_raw}")
            print(f"instrument: {annotation.instrument}")
            print(f"target: {annotation.target}")
            print(f"certainty: {annotation.certainty}")
            print(f"needs_review: {annotation.needs_review}")
            print(f"comment: {annotation.comment or ''}")
            print(f"rule_id: {annotation.rule_id}")
            print(f"SOURCE_LINE: {annotation.text}")
            print(f"verify: {'OK' if annotation.verify(doc.rendered_text) else 'FAIL'}")

    print("=" * 100)
    print("SUMMARY")
    print(f"circulars_processed: {total}")
    print(f"optical_prefilter_passed: {optical}")
    print(f"optical_prefilter_discarded: {discarded}")
    print(f"circulars_with_measurements: {circulars_with_measurements}")
    print(f"measurements_total: {measurements_total}")
    print(f"examples_printed: {len(examples)}")


if __name__ == "__main__":
    main()
