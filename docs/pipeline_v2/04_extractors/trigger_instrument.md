# Trigger Instrument Extractor

For whom: developers maintaining trigger-instrument extraction and annotators reviewing instrument preannotations.

`TriggerInstrumentExtractor` identifies instruments that triggered or detected the event. It deliberately ignores follow-up instruments unless the local verb says they were part of the trigger/detection evidence.

## Output

| Field | Value |
|---|---|
| `label` | `TRIGGER_INSTRUMENT` |
| `target` | `instrument` |
| `certainty` | `confirmed` |
| `method` | `regex` |
| `extractor_id` | `trigger-instrument-v1` |
| `extractor_version` | `0.1` |

## Vocabulary

The instrument vocabulary lives in `src/skyportal_corpus/extraction_v2/instruments_vocab.py`. It is the place to add new aliases without touching extractor logic.

Current canonical instruments are:

```text
Swift/BAT, Fermi/GBM, Fermi/LAT, SVOM/GRM, SVOM/ECLAIRs,
Konus-Wind, CALET/CGBM, AGILE/MCAL, MAXI, IceCube,
INTEGRAL, GECAM, GRBAlpha, VZLUSAT-2, AstroSat/CZTI, EP/WXT
```

Each accepted annotation uses a `rule_id` such as `trigger_instrument.fermi_gbm` and a canonical `value` such as `Fermi/GBM`.

## Trigger Versus Follow-Up

The extractor first finds instrument mentions, then applies context gates.

```text
instrument mention
    |
    v
non-trigger reference gates
    |
    v
follow-up gate
    |
    v
trigger/detection verb gate
    |
    v
deduplicate by canonical instrument
```

Trigger verbs include `triggered`, `was triggered`, `detected`, `was detected by`, and a restricted active form of `located`. Follow-up language such as `observed`, `began observing`, `followed up`, `imaging`, `reported photometry`, and `monitoring` excludes a match.

This sentence emits `Swift/BAT`:

```text
At 21:04:43 UT, the Swift Burst Alert Telescope (BAT) triggered and located GRB 230116D
```

This sentence emits nothing:

```text
The XRT began observing the field at 21:06:54 UT.
```

## Non-Trigger Reference Gates

Several systematic false positives are excluded before trigger verbs are considered:

| Gate | Example rejected | Reason |
|---|---|---|
| `boresight` suffix | `Fermi LAT boresight` | Geometry, not trigger evidence. |
| `catalog`, `catalogue`, `collaboration` suffix | `Fermi-LAT catalog` | Catalog or citation reference. |
| `detection:` suffix | `Fermi GBM detection: Lesage et al.` | Bibliographic heading, not the current trigger instrument. |
| short LAT `data` suffix | `LAT data` | Data-analysis reference. The window is short so `GBM trigger data` remains valid. |

The word `located` is also restricted. Passive spatial phrases such as `are located within the region` do not count as trigger language. Active event-localization phrases such as `triggered and located` and `located the burst` still count.

## Multi-Instrument And De-Duplication

If more than one distinct trigger instrument appears, all are emitted and marked `needs_review=True`. This is common in IPN or multi-instrument reports:

```text
was detected by Fermi (GBM trigger 697674761), Konus-Wind, INTEGRAL (SPI-ACS), Swift (BAT)
```

If the same canonical instrument appears several times with trigger context, only the first occurrence is kept. The goal is one evidence span per instrument, not repeated mentions of the same source of trigger evidence.

## Known Limitations

The vocabulary is finite. Coverage drops when new missions or instrument aliases appear before they are added to `instruments_vocab.py`. The sweep by year is the main tool for discovering those gaps, especially for EP and SVOM-era Circulars.
