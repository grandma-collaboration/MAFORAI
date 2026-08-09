"""Flatten the INCEpTION GCN gold-annotation export into interim Parquet tables.

Reads the fixed export at data/inception/project-2026-08-08-072803/: the
zipped per-annotator XMI under annotation/, the plain source XMI under
source/, and exportedproject.json. Writes five flat tables to
data/interim/gcn_gold_corpus/.

Shape only. This script takes no decisions: it does not compare an
annotator's layer against INITIAL_CAS, does not classify an annotation
as accepted/corrected/deleted/created, does not drop, trim, recode, type
or deduplicate any feature value. Every value lands in the table exactly
as it appears in the XMI; an attribute that is wholly absent on an
element becomes a null cell, an attribute present with an empty string
stays an empty string. That comparison, and any decision built on it,
belongs to a later script and must remain visible as a difference
between this interim layer and whatever corpus is built from it.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_ROOT = REPO_ROOT / "data/inception/project-2026-08-08-072803"
OUTPUT_ROOT = REPO_ROOT / "data/interim/gcn_gold_corpus"

EXCLUDED_USERS = {"admin", "Patrick", "Thomas"}
IN_SCOPE_STATE = "FINISHED"

XMI_NS = "http://www.omg.org/XMI"
CAS_NS = "http:///uima/cas.ecore"
CUSTOM_NS = "http:///webanno/custom.ecore"
SENTENCE_NS = "http:///de/tudarmstadt/ukp/dkpro/core/api/segmentation/type.ecore"

# Local layer name -> fully-qualified layer name as it appears in exportedproject.json.
LAYER_FULL_NAMES = {
    "ASTRO_EVIDENCE": "webanno.custom.ASTRO_EVIDENCE",
    "PHOTOMETRIC_MEASUREMENT": "webanno.custom.PHOTOMETRIC_MEASUREMENT",
    "EVENT_SUMMARY": "webanno.custom.EVENT_SUMMARY",
}

# Attributes that are CAS/UIMA structure, not a declared feature of any layer. Never
# reported as an "undeclared attribute"; xmi:id/begin/end are emitted under their own
# named columns, "sofa" is a fixed single-sofa reference and carries no information here.
CORE_SPAN_ATTRS = {f"{{{XMI_NS}}}id", "sofa", "begin", "end"}
CORE_DOC_LEVEL_ATTRS = {f"{{{XMI_NS}}}id", "sofa"}


def qtag(uri: str, local: str) -> str:
    return f"{{{uri}}}{local}"


def load_project_json() -> dict[str, Any]:
    path = EXPORT_ROOT / "exportedproject.json"
    return json.loads(path.read_text(encoding="utf-8"))


def declared_features(project: dict[str, Any]) -> dict[str, list[str]]:
    """Local layer name -> ordered list of declared feature names, read from the project."""
    by_full_name = {layer["name"]: layer for layer in project["layers"]}
    result: dict[str, list[str]] = {}
    for local, full in LAYER_FULL_NAMES.items():
        if full not in by_full_name:
            raise RuntimeError(f"exportedproject.json: layer '{full}' not found among "
                               f"declared layers {sorted(by_full_name)}")
        result[local] = [f["name"] for f in by_full_name[full]["features"]]
    return result


def derive_perimeter(project: dict[str, Any]) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (sorted list of (document, annotator) pairs in state FINISHED, excluded users
    already removed; sorted list of the 10 source document names)."""
    pairs = sorted({
        (entry["name"], entry["user"])
        for entry in project["annotation_documents"]
        if entry["state"] == IN_SCOPE_STATE and entry["user"] not in EXCLUDED_USERS
    })
    documents = sorted({entry["name"] for entry in project["source_documents"]})
    if not pairs:
        raise RuntimeError("derived perimeter is empty: 0 FINISHED pairs after exclusions")
    if not documents:
        raise RuntimeError("derived perimeter is empty: 0 source documents")
    return pairs, documents


def read_zip_xmi(zip_path: Path, stem: str) -> ET.Element:
    """Read <stem>.xmi out of one annotation zip. Fails loudly on any mismatch."""
    if not zip_path.exists():
        raise RuntimeError(f"expected annotation zip not found: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        member = f"{stem}.xmi"
        names = zf.namelist()
        if member not in names:
            raise RuntimeError(f"{zip_path}: member '{member}' not found; zip contains {names}")
        raw_bytes = zf.read(member)
    if not raw_bytes:
        raise RuntimeError(f"{zip_path} :: {member}: zero bytes read")
    return ET.fromstring(raw_bytes)


def read_source_xmi(document: str) -> ET.Element:
    path = EXPORT_ROOT / "source" / document
    if not path.exists():
        raise RuntimeError(f"expected source document not found: {path}")
    raw_bytes = path.read_bytes()
    if not raw_bytes:
        raise RuntimeError(f"{path}: zero bytes read")
    return ET.fromstring(raw_bytes)


def sofa_string(root: ET.Element, where: str) -> str:
    elems = root.findall(qtag(CAS_NS, "Sofa"))
    if len(elems) != 1:
        raise RuntimeError(f"{where}: expected exactly one cas:Sofa element, found {len(elems)}")
    value = elems[0].get("sofaString")
    if value is None:
        raise RuntimeError(f"{where}: cas:Sofa element has no sofaString attribute")
    return value


def sources_for_document(document: str, perimeter: list[tuple[str, str]]) -> list[tuple[str, Path, str]]:
    """(layer_source, zip_path, member_stem) for INITIAL_CAS plus every in-scope annotator
    of this document."""
    out = [("INITIAL_CAS", EXPORT_ROOT / "annotation" / document / "INITIAL_CAS.zip", "INITIAL_CAS")]
    for doc, annotator in perimeter:
        if doc == document:
            out.append((annotator, EXPORT_ROOT / "annotation" / document / f"{annotator}.zip", annotator))
    return out


# ---------------------------------------------------------------------------
# Table 1: documents
# ---------------------------------------------------------------------------
def build_documents_table(documents: list[str]) -> pd.DataFrame:
    rows = []
    for document in documents:
        where = f"source/{document}"
        root = read_source_xmi(document)
        sofa = sofa_string(root, where)
        sentence_elems = root.findall(qtag(SENTENCE_NS, "Sentence"))
        if not sentence_elems:
            raise RuntimeError(f"{where}: zero Sentence elements found; reader bug, "
                               f"not a true zero -- source documents are segmented on import")
        rows.append({
            "document_name": document,
            "source_file": f"source/{document}",
            "text_length": len(sofa),
            "text_sha256": hashlib.sha256(sofa.encode("utf-8")).hexdigest(),
            "sentence_count": len(sentence_elems),
        })
    df = pd.DataFrame(rows).sort_values("document_name").reset_index(drop=True)
    if len(df) == 0:
        raise RuntimeError("documents table has 0 rows")
    return df


# ---------------------------------------------------------------------------
# Table 2: annotators (the project's own workflow-state record, per pair in scope)
# ---------------------------------------------------------------------------
def build_annotators_table(project: dict[str, Any], perimeter: list[tuple[str, str]]) -> pd.DataFrame:
    perimeter_set = set(perimeter)
    rows = []
    for entry in project["annotation_documents"]:
        key = (entry["name"], entry["user"])
        if key not in perimeter_set:
            continue
        row: dict[str, Any] = {"document_name": entry["name"], "annotator": entry["user"]}
        for field, value in entry.items():
            if field in ("name", "user"):
                continue
            row[field] = value
        rows.append(row)
    df = pd.DataFrame(rows).sort_values(["document_name", "annotator"]).reset_index(drop=True)
    if len(df) == 0:
        raise RuntimeError("annotators table has 0 rows")
    if len(df) != len(perimeter):
        raise RuntimeError(f"annotators table has {len(df)} rows but the derived perimeter "
                           f"has {len(perimeter)} pairs -- exportedproject.json lookup mismatch")
    return df


# ---------------------------------------------------------------------------
# Shared: collect every element of one custom layer across the in-scope sources of every
# in-scope document, alongside the sofa string it belongs to.
# ---------------------------------------------------------------------------
def collect_layer_elements(layer_local: str, documents: list[str], perimeter: list[tuple[str, str]]):
    collected = []
    for document in documents:
        for layer_source, zip_path, stem in sources_for_document(document, perimeter):
            where = f"{zip_path} :: {stem}.xmi"
            root = read_zip_xmi(zip_path, stem)
            sofa = sofa_string(root, where)
            for elem in root.findall(qtag(CUSTOM_NS, layer_local)):
                collected.append((document, layer_source, sofa, elem, where))
    return collected


def discover_extra_attrs(elements, declared: list[str], core_attrs: set[str]) -> list[str]:
    """Attribute names observed on the actual elements that neither the declared feature
    list nor the fixed CAS-structure set account for."""
    observed: set[str] = set()
    for _, _, _, elem, _ in elements:
        observed.update(elem.attrib.keys())
    return sorted(observed - set(declared) - core_attrs)


# ---------------------------------------------------------------------------
# Table 3 / 4: span layers (ASTRO_EVIDENCE, PHOTOMETRIC_MEASUREMENT)
# ---------------------------------------------------------------------------
def build_span_table(layer_local: str, declared: list[str], documents: list[str],
                     perimeter: list[tuple[str, str]]) -> tuple[pd.DataFrame, list[str]]:
    elements = collect_layer_elements(layer_local, documents, perimeter)
    if not elements:
        raise RuntimeError(f"{layer_local}: zero elements found across the whole perimeter")

    extra_attrs = discover_extra_attrs(elements, declared, CORE_SPAN_ATTRS)

    rows = []
    for document, layer_source, sofa, elem, where in elements:
        xmi_id_raw = elem.get(qtag(XMI_NS, "id"))
        if xmi_id_raw is None:
            raise RuntimeError(f"{where}: {layer_local} element carries no xmi:id")
        begin_raw, end_raw = elem.get("begin"), elem.get("end")
        if begin_raw is None or end_raw is None:
            raise RuntimeError(f"{where}: {layer_local} xmi:id={xmi_id_raw} missing begin/end")
        begin, end = int(begin_raw), int(end_raw)
        if not (0 <= begin <= end <= len(sofa)):
            raise RuntimeError(f"{where}: {layer_local} xmi:id={xmi_id_raw} offsets "
                               f"[{begin}:{end}] fall outside document text length {len(sofa)}")
        row: dict[str, Any] = {
            "document_name": document,
            "layer_source": layer_source,
            "xmi_id": int(xmi_id_raw),
            "begin": begin,
            "end": end,
            "covered_text": sofa[begin:end],
        }
        for feature in declared:
            row[feature] = elem.get(feature)  # None if absent, "" if present-but-empty
        for feature in extra_attrs:
            row[feature] = elem.get(feature)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values(
        ["document_name", "layer_source", "xmi_id"]).reset_index(drop=True)
    if len(df) == 0:
        raise RuntimeError(f"{layer_local} table has 0 rows")
    return df, extra_attrs


# ---------------------------------------------------------------------------
# Table 5: EVENT_SUMMARY (document-level, no offsets)
# ---------------------------------------------------------------------------
def build_event_summary_table(declared: list[str], documents: list[str],
                              perimeter: list[tuple[str, str]]) -> tuple[pd.DataFrame, list[str]]:
    elements = collect_layer_elements("EVENT_SUMMARY", documents, perimeter)
    if not elements:
        raise RuntimeError("EVENT_SUMMARY: zero elements found across the whole perimeter")

    extra_attrs = discover_extra_attrs(elements, declared, CORE_DOC_LEVEL_ATTRS)

    rows = []
    for document, layer_source, _sofa, elem, where in elements:
        xmi_id_raw = elem.get(qtag(XMI_NS, "id"))
        if xmi_id_raw is None:
            raise RuntimeError(f"{where}: EVENT_SUMMARY element carries no xmi:id")
        row: dict[str, Any] = {
            "document_name": document,
            "layer_source": layer_source,
            "xmi_id": int(xmi_id_raw),
        }
        for feature in declared:
            row[feature] = elem.get(feature)
        for feature in extra_attrs:
            row[feature] = elem.get(feature)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values(
        ["document_name", "layer_source", "xmi_id"]).reset_index(drop=True)
    if len(df) == 0:
        raise RuntimeError("event_summaries table has 0 rows")
    return df, extra_attrs


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
def run_controls(documents: list[str], perimeter: list[tuple[str, str]],
                 documents_df: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []

    def check(name: str, observed: Any, expected: Any) -> None:
        controls.append({"control": name, "expected": expected, "observed": observed,
                         "status": "PASS" if observed == expected else "FAIL"})

    check("documents", len(documents_df), 10)
    check("annotator layers in scope (excluding INITIAL_CAS)", len(perimeter), 28)
    check("distinct annotators", len({a for _, a in perimeter}), 10)
    check("INITIAL_CAS layers", len(documents), 10)

    per_doc_annotator_count = {d: sum(1 for doc, _ in perimeter if doc == d) for d in documents}
    at_least_two = all(count >= 2 for count in per_doc_annotator_count.values())
    check("every document has at least 2 annotator layers", at_least_two, True)

    sofa_consistent = True
    for document in documents:
        hashes = set()
        for layer_source, zip_path, stem in sources_for_document(document, perimeter):
            where = f"{zip_path} :: {stem}.xmi"
            root = read_zip_xmi(zip_path, stem)
            sofa = sofa_string(root, where)
            hashes.add(hashlib.sha256(sofa.encode("utf-8")).hexdigest())
        if len(hashes) != 1:
            sofa_consistent = False
    check("sofa sha256 identical across all layers of a document, all 10", sofa_consistent, True)

    # Offset-range checking is enforced as a hard failure at build time (build_span_table
    # raises immediately on any violation), so by the time this control is evaluated every
    # span already satisfies it -- confirmed here by re-checking the written tables directly.
    total_spans = 0
    out_of_range = 0
    length_by_doc = dict(zip(documents_df["document_name"], documents_df["text_length"]))
    for table_name in ("evidence_spans", "photometry_spans"):
        df = tables[table_name]
        total_spans += len(df)
        # text_length in documents.parquet is measured from source/, which was already
        # confirmed identical to every annotation layer's sofa by the control above.
        bad = df[(df["begin"] < 0) | (df["end"] < df["begin"]) |
                (df["end"] > df["document_name"].map(length_by_doc))]
        out_of_range += len(bad)
    check("every span offset within its document text length "
         f"({total_spans} spans checked)", out_of_range, 0)

    forbidden_hits = 0
    if "annotator" in tables.get("annotators", pd.DataFrame()).columns:
        forbidden_hits += tables["annotators"]["annotator"].isin(EXCLUDED_USERS).sum()
    for table_name in ("evidence_spans", "photometry_spans", "event_summaries"):
        forbidden_hits += tables[table_name]["layer_source"].isin(EXCLUDED_USERS).sum()
    check("admin, Patrick, Thomas present anywhere in the output", bool(forbidden_hits), False)

    return controls


def print_controls(controls: list[dict[str, Any]]) -> bool:
    print("CONTROLS")
    print(f"{'control':60s} {'expected':>10s} {'observed':>10s} {'status':>8s}")
    all_pass = True
    for c in controls:
        status = c["status"]
        all_pass = all_pass and status == "PASS"
        print(f"{c['control']:60s} {str(c['expected']):>10s} {str(c['observed']):>10s} {status:>8s}")
    return all_pass


def main() -> None:
    project = load_project_json()
    features = declared_features(project)
    perimeter, documents = derive_perimeter(project)

    print("PERIMETER (derived from exportedproject.json)")
    print(f"  excluded users: {sorted(EXCLUDED_USERS)}")
    print(f"  in-scope state: {IN_SCOPE_STATE!r}")
    print(f"  {len(perimeter)} (document, annotator) pairs:")
    for pair in perimeter:
        print(f"    {pair}")
    print(f"  {len(documents)} source documents: {documents}")

    documents_df = build_documents_table(documents)
    annotators_df = build_annotators_table(project, perimeter)
    evidence_df, evidence_extra = build_span_table(
        "ASTRO_EVIDENCE", features["ASTRO_EVIDENCE"], documents, perimeter)
    photometry_df, photometry_extra = build_span_table(
        "PHOTOMETRIC_MEASUREMENT", features["PHOTOMETRIC_MEASUREMENT"], documents, perimeter)
    event_summary_df, event_summary_extra = build_event_summary_table(
        features["EVENT_SUMMARY"], documents, perimeter)

    tables = {
        "documents": documents_df,
        "annotators": annotators_df,
        "evidence_spans": evidence_df,
        "photometry_spans": photometry_df,
        "event_summaries": event_summary_df,
    }

    controls = run_controls(documents, perimeter, documents_df, tables)
    all_pass = print_controls(controls)
    if not all_pass:
        raise RuntimeError("at least one control failed; no Parquet file was written. "
                           "See CONTROLS table above.")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for name, df in tables.items():
        path = OUTPUT_ROOT / f"{name}.parquet"
        df.to_parquet(path, engine="pyarrow", index=False)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    print("\nFINAL SUMMARY")

    print("\n1. CONTROLS: see table above; all PASS." if all_pass else "\n1. CONTROLS: FAILED.")

    print("\n2. Derived perimeter:")
    for pair in perimeter:
        print(f"   {pair}")
    print(f"   excluded users: {sorted(EXCLUDED_USERS)}")

    print("\n3. Per table: rows, columns, full column list")
    for name, df in tables.items():
        print(f"   {name}.parquet: rows={len(df)} columns={df.shape[1]}")
        print(f"     {list(df.columns)}")

    print("\n4. Rows per layer_source per table")
    print(f"   annotators.parquet by 'annotator':")
    print(f"     {annotators_df['annotator'].value_counts().sort_index().to_dict()}")
    for name in ("evidence_spans", "photometry_spans", "event_summaries"):
        counts = tables[name]["layer_source"].value_counts().sort_index().to_dict()
        print(f"   {name}.parquet by 'layer_source':")
        print(f"     {counts}")

    print("\n5. Absent-vs-empty convention")
    print("   Every declared/extra feature column is written with pandas 'object' dtype "
         "(pyarrow nullable string on write). elem.get(feature) returns None when the "
         "attribute is wholly absent, and returns '' when the attribute is present with "
         "an empty string; both are stored as-is. This dtype already distinguishes a null "
         "cell from an empty-string cell in the Parquet output, so NO companion boolean "
         "'*_is_present' column was added for any feature.")

    print("\n6. Undeclared attributes found in the XMI (emitted as columns anyway)")
    print(f"   ASTRO_EVIDENCE: {evidence_extra if evidence_extra else 'none'}")
    print(f"   PHOTOMETRIC_MEASUREMENT: {photometry_extra if photometry_extra else 'none'}")
    print(f"   EVENT_SUMMARY: {event_summary_extra if event_summary_extra else 'none'} "
         "(i7n_uiOrder is INCEpTION interface state, not data, per the task instructions; "
         "it is emitted as a column here rather than dropped, since dropping it would be a decision)")

    print("\n7. UNCOVERED CASES")
    print("   - Comparing an annotator's layer against INITIAL_CAS to classify a span as "
         "accepted, corrected, deleted or created: NOT done here by design. xmi_id is not "
         "stable across layers (confirmed during reconnaissance: an identical span can "
         "carry a different xmi:id in INITIAL_CAS vs. an annotator copy), so that "
         "comparison needs its own offset-based matching logic, which belongs to the "
         "corpus-building script that follows this one, not to this flattening script.")
    print("   - Whether a 'comment' value on an INITIAL_CAS annotation originates from an "
         "automatic extractor versus a human curator, or whether an annotator-authored "
         "'comment' is a note-to-self versus a substantive correction: not determined here. "
         "No feature in the schema marks provenance of a comment; this script stores every "
         "comment value exactly as written and takes no position on its origin.")
    print("   - xmi:id, begin and end are stored as integers (parsed from the XMI's numeric "
         "string attributes) rather than left as strings, since they are needed to check the "
         "offset-range control and to slice covered_text; this is the one place a raw string "
         "attribute is parsed into a different Python type, and it is reported here for "
         "transparency rather than treated as implicit.")

    print("\n8. Idempotency: this run's five output SHA-256 hashes")
    for name, digest in hashes.items():
        print(f"   {name}.parquet: {digest}")
    print("   (compare against a second run's hashes to confirm byte-identical output)")


if __name__ == "__main__":
    main()
