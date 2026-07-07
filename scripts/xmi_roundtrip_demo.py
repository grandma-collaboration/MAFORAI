from __future__ import annotations

import pprint
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import iter_real_circulars, render_canonical  # noqa: E402
from skyportal_corpus.extraction_v2.event_identity import EventIdentityExtractor  # noqa: E402
from skyportal_corpus.extraction_v2.trigger_time import TriggerTimeExtractor  # noqa: E402
from skyportal_corpus.inception_v2.xmi_export import (  # noqa: E402
    MISSING_TYPESYSTEM_MESSAGE,
    TYPESYSTEM_PATH,
    export_document_to_xmi,
)
from skyportal_corpus.inception_v2.xmi_roundtrip import roundtrip_check  # noqa: E402


def main() -> int:
    typesystem_path = PROJECT_ROOT / TYPESYSTEM_PATH
    if not typesystem_path.exists():
        print(MISSING_TYPESYSTEM_MESSAGE)
        return 1

    identity_extractor = EventIdentityExtractor()
    trigger_time_extractor = TriggerTimeExtractor()
    chosen = None

    for circular in iter_real_circulars(limit=50):
        doc = render_canonical(**circular)
        identity_annotations = identity_extractor.extract(doc)
        trigger_time_annotations = trigger_time_extractor.extract(doc)
        annotations = [*identity_annotations, *trigger_time_annotations]
        if identity_annotations and trigger_time_annotations:
            chosen = (doc, annotations)
            break

    if chosen is None:
        print("No circular with both identity and trigger time was found in the first 50 circulars.")
        return 1

    doc, annotations = chosen
    out_path = PROJECT_ROOT / "data" / "inception" / "out" / f"{doc.circular_id}.xmi"
    export_document_to_xmi(doc, annotations, typesystem_path, out_path)
    result = roundtrip_check(out_path, typesystem_path, annotations, doc.rendered_text)

    pprint.pp(result)
    final_ok = (
        result["text_matches"]
        and result["all_spans_ok"]
        and result["all_features_ok"]
        and result["n_original"] == result["n_roundtripped"]
    )
    print(f"XMI: {out_path}")
    print("OK final" if final_ok else "FAIL final")
    return 0 if final_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
