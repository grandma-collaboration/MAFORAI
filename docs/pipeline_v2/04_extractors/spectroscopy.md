# Spectroscopy Extractor

For whom: developers maintaining optical/NIR spectroscopy extraction and annotators reviewing observation, spectrum, and spectral-feature spans.

`SpectroscopyExtractor` emits `SPECTROSCOPY` for reported spectroscopic observations, optical/NIR spectra, and diagnostic spectral features. It keeps the spectroscopy evidence separate from a redshift value or the physical class inferred from the spectrum.

## Output

| Field | Value |
|---|---|
| `label` | `SPECTROSCOPY` |
| `target` | `counterpart` or `event` |
| `certainty` | `confirmed` |
| `method` | `regex` |
| `extractor_id` | `spectroscopy-v1` |
| `extractor_version` | `0.1` |

`value` and `unit` are unset because the selected span is qualitative observation evidence. `comment` is unset and `needs_review=False` for current captures.

## Rules

| Rule ID | What it captures | Example |
|---|---|---|
| `spectroscopy.observation` | performed spectroscopy, obtained spectra, spectroscopic observations, and named spectrographs | `We obtained spectroscopy with ALFOSC` |
| `spectroscopy.spectrum` | generic spectrum phrases with optical/NIR evidence and no high-energy context | `The optical spectrum` |
| `spectroscopy.features` | absorption or emission lines, P-Cygni profiles, named ions, spectral features, and contextual continua | `Mg II and Ca II absorption features` |

## Optical And NIR Spectrum Gate

The generic `spectroscopy.spectrum` rule requires positive optical/NIR evidence in the containing sentence. Accepted evidence includes an optical or NIR qualifier, a known optical spectrograph or facility, an Angstrom or nanometer wavelength, an emission or absorption feature, a P-Cygni profile, or a named ion.

It rejects a generic spectrum candidate when the sentence contains a keV/MeV range, an X-ray or gamma-ray instrument, or high-energy fit language such as `power law`, `CPL`, `Band model`, `cutoff power law`, `time-averaged spectrum`, `count spectrum`, `energy spectrum`, or `photon spectrum`.

Examples rejected by this gate include:

```text
The time-averaged WXT 0.5-4 keV spectrum
The average FXT 0.5-10 keV spectrum
the prompt gamma-ray spectrum fitted with a cutoff power law
```

These quantities belong to high-energy analysis rather than optical/NIR spectroscopy.

## Observation And Feature Evidence

Observation rules recognize explicit `spectroscopy` or `spectroscopic` language and named instruments including ALFOSC, FORS2, OSIRIS, X-shooter, GMOS, LRIS, MISTRAL, DEIMOS, MODS, and LRS2.

Feature rules recognize line lists and families such as `Mg II`, `Ca II`, `[O II]`, `[O III]`, `H-alpha`, `H-beta`, `He II`, absorption or emission lines, P-Cygni profiles, flash-ionisation features, and continua. A bare continuum descriptor requires other spectral context in the sentence.

## Target Selection

`counterpart` is the default and is retained for explicit spectroscopy or spectrograph observations. A generic spectrum is targeted to `event` only when its span or containing sentence explicitly describes the spectrum of the burst, GRB, or event.

## Redshift And Classification Gates

A bare `z=...` or redshift statement does not satisfy the spectroscopy rules and belongs to `REDSHIFT_EVENT` or `REDSHIFT_CONTEXT`. The extractor captures a line or observation span without copying the redshift value.

A bare class claim such as `type II supernova` is not spectroscopy evidence and belongs to `CLASSIFICATION_INTERPRETATION`. When a spectrum supports a class, this extractor covers the observation or features, while the class extractor owns the interpretation.

Follow-up requests such as `Further spectroscopic observations are encouraged` are excluded unless the sentence also reports that spectroscopy was obtained or performed. A lone `spectroscopy` token in a program, pipeline, survey, or collaboration name is also rejected.

## De-Overlap

Specific observation and line-feature spans outrank broad `spectroscopy`, spectrum, or continuum matches. The highest-priority and then longest overlapping candidate is retained, and annotations are returned in source order.

## Known Limitations

The optical/high-energy exclusion is applied explicitly to the generic `spectroscopy.spectrum` rule; highly unusual explicit observation wording may still require review. The spectrograph and line vocabularies are finite, and the extractor does not normalize wavelengths, identify every ion, or derive redshift and classification from features.
