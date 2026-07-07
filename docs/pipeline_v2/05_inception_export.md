# INCEpTION Export

For whom: developers who export XMI and annotators who import preannotations into INCEpTION.

Pipeline v2 exports annotations as UIMA CAS XMI so INCEpTION can load the canonical text and the machine-proposed spans. A round-trip check reloads the XMI and verifies that text, offsets, and features survived unchanged.

## Terms

A CAS, or Common Analysis Structure, is the UIMA container that holds the document text and annotations. XMI is the XML serialization format used to save that CAS. A round-trip means exporting the CAS to XMI, loading it back, and checking that the result matches the original.

## INCEpTION Coupling

The real TypeSystem exported from INCEpTION must be available at:

```text
data/inception/TypeSystem.xml
```

The active span layer is:

```text
webanno.custom.ASTRO_EVIDENCE
```

In the TypeSystem, this layer extends `uima.tcas.Annotation`, so every annotation has `begin` and `end` offsets. It has six string features:

```text
label
target
certainty
value
unit
comment
```

The exporter also adds minimal `Sentence` and `Token` annotations if those DKPro segmentation types exist in the TypeSystem. This helps INCEpTION import the document in the expected shape.

## Export Flow

```text
CanonicalDocument + EventEvidenceAnnotation[]
        |
        | export_document_to_xmi()
        v
CAS with sofa_string = rendered_text
        |
        | ASTRO_EVIDENCE annotations
        v
data/inception/out/<circular_id>.xmi
```

Before writing, the exporter checks every annotation:

```python
cas.sofa_string[a.span_start:a.span_end] == a.text
```

If that fails, export stops because the XMI would contain a broken span.

## Demo Command

```bash
.venv/bin/python scripts/xmi_roundtrip_demo.py
```

The current real demo uses Circular `33130` and writes:

```text
data/inception/out/33130.xmi
```

The round-trip result should have:

```text
text_matches=True
all_spans_ok=True
all_features_ok=True
n_original == n_roundtripped
```

## Importing Into INCEpTION

1. In INCEpTION, use the same project whose TypeSystem was exported to `data/inception/TypeSystem.xml`.
2. Choose the UIMA CAS XMI XML 1.0 import format.
3. Import the generated `.xmi`, for example `data/inception/out/33130.xmi`.
4. Open the document and inspect the `ASTRO_EVIDENCE` span layer.
5. Review the machine annotations and correct them where needed.

## What The Round-Trip Guarantees

`text_matches` means the loaded CAS text is exactly the original canonical text.

`all_spans_ok` means every loaded annotation has a span that matches an original annotation and selects the expected substring.

`all_features_ok` means `label`, `target`, `certainty`, `value`, `unit`, and `comment` survived export and reload.

The round-trip proves that the file preserves the evidence exactly enough for a human to review it.

