# MAFORAI PRE 2026 Reproducibility Freeze

Freeze ID: `pre2026-freeze-v1-pilot-20260731`  
Created at: `2026-07-31T20:07:21+02:00`  
Evaluated source commit: `3d8b23ec77b0f4ae107921784c068f35ac98b9ff`  
Access: restricted internal snapshot

This is a reproducible snapshot of the MAFORAI pipeline and its single-event expert pilot evaluation. The scientific validation of the ten event documents remains in progress.

It does not claim complete corpus validation, an independent or multi-annotator evaluation, a validated RAG system, or an implemented LLM assistant.

## Contents

| Directory | Role |
|---|---|
| `inputs/` | Frozen GCN archive, normalized Circular index, SkyPortal inventory/detail captures, and non-secret configuration. |
| `derived/` | Current registry, identity index, event selections, baseline, ten XMI documents, manifests, and validation reports. |
| `evaluation/` | Historical automatic pilot, expert XMI, historical comparison outputs, reproducible evaluator outputs, and audit reports. |
| `ongoing_temporal/` | Dated facts, event maps, 6 h/24 h/7 d states, small BGE-M3 indexes, and preliminary retrieval audits. |
| `historical_evidence/` | Dated API, priority-selection, aggregate-prototype, and superseded matcher evidence. |

`SOURCE_INVENTORY.tsv` records the source path, destination, original byte size, Git status, inclusion reason, and importance for every copied preservation unit.

## Preserved Current Results

- 574 deduplicated registry events.
- 146 viable events: 80 GRB, 47 GCN, and 19 EP.
- 10 automatically generated event documents.
- 297 Circulars, 1,683 `EVENT_EVIDENCE` annotations, and 670 `PHOTOMETRIC_MEASUREMENT` annotations.
- Zero extraction errors in the ten-event preflight; all ten XMI build/round-trip verdicts are `OK`.
- 727 collected and passing tests, with zero failures, skips, or warnings.

These are technical pipeline results. The ten documents have not completed expert scientific validation.

## Pilot Evaluation Versions

The evaluated historical pilot is `evaluation/automatic/event_2026owq.xmi`: 28 Circulars, 193 scientific evidence annotations, 76 photometric annotations, canonical-text SHA-256 `a51b058b1e19cdbaa71dd858451999825147b8f38ac9d36f6fe45e45e9c234d6`.

The expert document is `evaluation/expert/Camille.xmi` and has the same canonical text. The reproducible evaluation is under `evaluation/reproducible_outputs/`.

The regenerated current pilot is separate: `derived/inception/2026owq/event_2026owq.xmi` contains 30 Circulars, 204 scientific evidence annotations, and 68 photometric annotations. It was not substituted into the historical expert comparison.

Historical comparison outputs are retained for provenance but are not strictly reproducible because their original comparison script and exact 193/68 automatic XMI were not preserved.

## Ongoing Temporal Work

The temporal representation is implemented. Retrospective retrieval is preliminary, performance is not stabilized, the RAG system is not finalized, and no LLM assistant is implemented. Backtest percentages in `ongoing_temporal/audits/` are exploratory evidence rather than report results.

## Intentional Exclusions

- The extracted 45,000-file GCN JSON tree, because the compressed archive and acquisition manifest preserve the same source and regenerate it.
- Python virtual environments, Git internals, bytecode, test caches, notebook checkpoints, and temporary files.
- LaTeX auxiliary files and other regenerable build products.
- Credentials, `.env`, API tokens, passwords, and private access URLs.
- Unrelated raw data and duplicate cache copies.

The small state vectors are included because they are only about 1.4 MiB in total and directly support the current preliminary backtest.

## Verification

From this directory:

```bash
sha256sum -c FREEZE_MANIFEST.sha256
git bundle verify MAFORAI_pre2026_freeze_v1.bundle
```

The manifest covers the preserved payload except itself and `FREEZE_METADATA.yaml`; excluding the metadata avoids an impossible checksum self-reference. The Git bundle is produced after the local tag so that it contains the freeze commit and tag; it is verified and hashed separately in `BUNDLE_VERIFICATION.txt` and the execution report.

## Storage Status

The snapshot is local on the same physical machine as the working repository. The intended institutional destination is IJCLab OwnCloud, but upload is pending and was not performed during this task. External protection is therefore not complete.
