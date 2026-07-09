from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from skyportal_corpus.extraction_v2.instruments_vocab import INSTRUMENTS, rule_id_for_instrument
from skyportal_corpus.extraction_v2.sweep import get_active_extractors
from skyportal_corpus.extraction_v2.tagsets import CERTAINTIES, LABELS, TARGETS


MODULE_RESPONSIBILITIES = {
    "src/skyportal_corpus/canonical/document.py": (
        "Builds immutable CanonicalDocument text, segments, hashes, and real-circular loaders."
    ),
    "src/skyportal_corpus/extraction_v2/annotations.py": (
        "Defines EventEvidenceAnnotation with tagset validation and offset verification."
    ),
    "src/skyportal_corpus/extraction_v2/event_identity.py": (
        "Extracts event identity names such as GRB, EP, AT/SN, ZTF, IceCube, GW, and S-names."
    ),
    "src/skyportal_corpus/extraction_v2/event_grouping.py": (
        "Groups candidate Circulars by canonical event aliases and subject-first membership rules."
    ),
    "src/skyportal_corpus/extraction_v2/event_document.py": (
        "Builds immutable EventCanonicalDocument text, Circular segments, hashes, and offset maps."
    ),
    "src/skyportal_corpus/extraction_v2/event_annotations.py": (
        "Runs active extractors per Circular and translates verified local spans to event-global offsets."
    ),
    "src/skyportal_corpus/extraction_v2/instruments_vocab.py": (
        "Central vocabulary of known trigger instruments and their aliases."
    ),
    "src/skyportal_corpus/extraction_v2/localization.py": (
        "Extracts RA/Dec positions and localization uncertainty spans."
    ),
    "src/skyportal_corpus/extraction_v2/redshift.py": (
        "Extracts event and context redshifts with cautious attribution."
    ),
    "src/skyportal_corpus/extraction_v2/sweep.py": (
        "Runs active extractors over real circular batches and builds aggregate diagnostics."
    ),
    "src/skyportal_corpus/extraction_v2/tagsets.py": (
        "Single source of truth for label, target, and certainty tagsets."
    ),
    "src/skyportal_corpus/extraction_v2/trigger_instrument.py": (
        "Extracts instruments that triggered or detected the event, excluding follow-up mentions."
    ),
    "src/skyportal_corpus/extraction_v2/trigger_time.py": (
        "Extracts trigger times with context gates, observation exclusions, and ISO normalization."
    ),
    "src/skyportal_corpus/inception_v2/xmi_export.py": (
        "Exports CanonicalDocument plus annotations to INCEpTION-compatible UIMA CAS XMI."
    ),
    "src/skyportal_corpus/inception_v2/xmi_roundtrip.py": (
        "Reads exported XMI back and verifies text, spans, and features survived unchanged."
    ),
}

EVENT_FLOW_SCRIPTS = {
    "scripts/event_grouping_demo.py": (
        "Reports included and excluded Circulars for the configured event."
    ),
    "scripts/event_document_demo.py": (
        "Builds the configured EventCanonicalDocument and checks segment and offset invariants."
    ),
    "scripts/event_xmi_export.py": (
        "Exports the configured event XMI and manifest, then verifies the XMI round-trip."
    ),
}


TEST_COVERAGE = {
    "tests/test_alerts_report.py": "alerts report grouping, filtering, and output generation",
    "tests/test_canonical_document.py": "canonical text rendering, segments, hashing, and XML-safe text",
    "tests/test_config.py": "project configuration helpers",
    "tests/test_event_annotations.py": "event-global annotation offsets and source-Circular provenance",
    "tests/test_event_document.py": "event canonical text, segments, hashes, and local/global offset maps",
    "tests/test_event_grouping.py": "subject-first event membership and alias matching",
    "tests/test_event_identity.py": "EVENT_IDENTITY extractor and canonical identity validation",
    "tests/test_gcn_circulars_archive.py": "legacy/raw GCN circular archive handling",
    "tests/test_gcn_circulars_index.py": "legacy/interim GCN circular index handling",
    "tests/test_gcn_core_claims.py": "legacy core-claim extraction utilities",
    "tests/test_gcn_event_enrichment.py": "legacy event enrichment utilities",
    "tests/test_gcn_event_matching.py": "legacy event-circular matching utilities",
    "tests/test_gcn_event_review.py": "legacy event review sampling utilities",
    "tests/test_gcn_event_review_export.py": "legacy review export utilities",
    "tests/test_gcn_inception_dossiers.py": "legacy INCEpTION dossier helpers",
    "tests/test_gcn_preannotation_candidates.py": "legacy preannotation candidate generation",
    "tests/test_inventory_profiles.py": "data inventory profile helpers",
    "tests/test_localization.py": "LOCALIZATION extractor",
    "tests/test_redshift.py": "REDSHIFT_EVENT and REDSHIFT_CONTEXT extractor",
    "tests/test_source_selection.py": "source selection utilities",
    "tests/test_sweep.py": "pipeline v2 sweep, aggregation, stratified sampling, and run metadata",
    "tests/test_trigger_instrument.py": "TRIGGER_INSTRUMENT extractor",
    "tests/test_trigger_time.py": "TRIGGER_TIME extractor and pure helper functions",
    "tests/test_xmi_roundtrip.py": "INCEpTION XMI export and round-trip verification",
}


def main() -> None:
    print("PIPELINE V2 INVENTORY")
    print("=====================")
    print()
    print_active_extractors()
    print()
    print_pipeline_modules()
    print()
    print_event_flow_scripts()
    print()
    print_tagsets()
    print()
    print_inception_typesystem_status()
    print()
    print_tests()


def print_active_extractors() -> None:
    print("ACTIVE EXTRACTORS")
    print("-----------------")
    for extractor in get_active_extractors():
        short_name = _short_name(extractor)
        print(
            f"- {short_name}: extractor_id={extractor.extractor_id}, "
            f"extractor_version={getattr(extractor, 'extractor_version', 'unknown')}"
        )
        rule_ids = rule_ids_for_extractor(extractor)
        if rule_ids:
            for rule_id in rule_ids:
                print(f"  - {rule_id}")
        else:
            print("  - rule_ids: not introspectable")


def print_pipeline_modules() -> None:
    print("PIPELINE V2 MODULES")
    print("-------------------")
    for path in sorted(MODULE_RESPONSIBILITIES):
        status = "present" if (PROJECT_ROOT / path).exists() else "missing"
        print(f"- {path} [{status}]: {MODULE_RESPONSIBILITIES[path]}")


def print_event_flow_scripts() -> None:
    print("EVENT FLOW SCRIPTS")
    print("------------------")
    for path in sorted(EVENT_FLOW_SCRIPTS):
        status = "present" if (PROJECT_ROOT / path).exists() else "missing"
        print(f"- {path} [{status}]: {EVENT_FLOW_SCRIPTS[path]}")


def print_tagsets() -> None:
    print("TAGSETS")
    print("-------")
    _print_tagset("LABELS", LABELS)
    _print_tagset("TARGETS", TARGETS)
    _print_tagset("CERTAINTIES", CERTAINTIES)


def print_inception_typesystem_status() -> None:
    print("INCEPTION TYPESYSTEM CHECK")
    print("--------------------------")
    path = PROJECT_ROOT / "data" / "inception" / "TypeSystem.xml"
    if not path.exists():
        print("- data/inception/TypeSystem.xml: missing")
        return

    text = path.read_text(encoding="utf-8", errors="replace")
    layer_ok = "webanno.custom.ASTRO_EVIDENCE" in text
    expected_features = ("label", "target", "certainty", "value", "unit", "comment")
    missing_features = [feature for feature in expected_features if f"<name>{feature}</name>" not in text]
    print(f"- data/inception/TypeSystem.xml: present")
    print(f"- layer webanno.custom.ASTRO_EVIDENCE: {'OK' if layer_ok else 'MISSING'}")
    if missing_features:
        print(f"- features: MISSING {', '.join(missing_features)}")
    else:
        print("- features: OK label, target, certainty, value, unit, comment")
    print("- tagset values: code-side source of truth in extraction_v2/tagsets.py")


def print_tests() -> None:
    print("TEST FILES")
    print("----------")
    test_files = sorted((PROJECT_ROOT / "tests").glob("test_*.py"))
    print(f"- count: {len(test_files)}")
    for path in test_files:
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        coverage = TEST_COVERAGE.get(rel, "coverage not classified in inventory")
        print(f"- {rel}: {coverage}")


def rule_ids_for_extractor(extractor: Any) -> list[str]:
    rule_ids: set[str] = set()

    for rule in getattr(extractor, "_rules", ()):
        rule_id = getattr(rule, "rule_id", None)
        if rule_id:
            rule_ids.add(str(rule_id))

    for attr_name in ("_decimal_rule", "_sexagesimal_rule", "_error_radius_rule"):
        rule = getattr(extractor, attr_name, None)
        rule_id = getattr(rule, "rule_id", None)
        if rule_id:
            rule_ids.add(str(rule_id))

    module = inspect.getmodule(extractor.__class__)
    if module is not None:
        for rule in getattr(module, "_RULES", ()):
            rule_id = getattr(rule, "rule_id", None)
            if rule_id:
                rule_ids.add(str(rule_id))

    if _short_name(extractor) == "trigger_instrument":
        for instrument in INSTRUMENTS:
            rule_ids.add(rule_id_for_instrument(instrument.canonical))

    return sorted(rule_ids)


def _short_name(extractor: Any) -> str:
    raw_name = str(getattr(extractor, "extractor_id", extractor.__class__.__name__))
    if raw_name.endswith("-v1"):
        raw_name = raw_name[: -len("-v1")]
    return raw_name.replace("-", "_")


def _print_tagset(name: str, values: frozenset[str]) -> None:
    ordered = sorted(values)
    print(f"- {name} ({len(ordered)}):")
    for value in ordered:
        print(f"  - {value}")


if __name__ == "__main__":
    main()
