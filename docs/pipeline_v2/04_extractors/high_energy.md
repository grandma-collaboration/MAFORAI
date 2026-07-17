# High-Energy Property Extractor

For whom: developers maintaining gamma-ray and X-ray property extraction and annotators reviewing normalized high-energy measurements.

`HighEnergyPropertyExtractor` emits `HIGH_ENERGY_PROPERTY` annotations for named prompt- and high-energy quantities. It requires a property name, keeps the literal source span, and normalizes the property and numeric expression into a stable `value`.

## Output

| Field | Value |
|---|---|
| `label` | `HIGH_ENERGY_PROPERTY` |
| `target` | `event` |
| `certainty` | `confirmed` or `tentative` |
| `method` | `regex` |
| `extractor_id` | `high-energy-v1` |
| `extractor_version` | `0.1` |

`value` is rendered as `<property> <operator> <number and error>`, while `unit` contains only the normalized unit. The dimensionless indices use an empty unit. A missing required unit sets `needs_review=True`; the exact source substring remains in `text`.

## Rules

| Rule ID | What it captures | Example |
|---|---|---|
| `high_energy.epeak` | Fermi-style `Epeak` and Konus-Wind `Ep` peak energies | `Ep = 251(-49,+81) keV` |
| `high_energy.fluence` | energy fluence with `erg/cm^2` units | `fluence (10-1000 keV) ... (1.30 +/- 0.02)E-05 erg/cm^2` |
| `high_energy.peak_flux` | energy or photon peak flux | `peak photon flux ... 7.7 +/- 0.3 ph/s/cm^2` |
| `high_energy.powerlaw_index` | dimensionless power-law indices | `power law index is -1.50 +/- 0.01` |
| `high_energy.photon_index` | dimensionless photon indices and high-energy `Gamma` aliases | `photon index 2.5(+1.7/-1.2)` |
| `high_energy.spectral_index` | spectral indices with explicit high-energy context | `X-ray spectral index is -1.8 +/- 0.2` |
| `high_energy.alpha` | Band/CPL low-energy index values | `alpha = -1.4800 +/- 0.0009` |
| `high_energy.beta` | Band high-energy index values and upper limits | `upper limit on the high energy photon index beta of -2.5` |
| `high_energy.eiso` | isotropic-equivalent energy in `erg` | `E_iso to (6.95 +/- 2.49)x10^52 erg` |
| `high_energy.cutoff_energy` | standalone cutoff energy not identified as `Epeak` | `cutoff energy of 75 +- 10 keV` |

## Property Normalization

Konus-Wind `Ep` is the same modeled quantity as `Epeak` and is normalized accordingly:

```text
Ep = 251(-49,+81) keV  ->  Epeak = 251(-49,+81)
Ep < 41 keV            ->  Epeak < 41
```

The bare `Ep` rule requires `=`, `<`, or `<=` immediately after the token. This excludes model formulas ending in `/Ep)` and rest-frame forms such as `Ep,i,z`. `<=` is normalized to `<`.

`Eiso`, `E_iso to`, `Eiso, is`, and `Eiso of` normalize to `Eiso = ...`. `Liso` and `L_iso` are intentionally outside the rule.

Peak-flux names depend on the unit: energy-rate units produce `peak energy flux`, while photon-rate units produce `peak photon flux`. Fluence has no trailing time denominator and cannot collide with peak flux.

## Index Boundary

`photon index beta` denotes the Band high-energy index, not a generic photon-index measurement. The photon-index rule rejects `photon index` followed by `beta`, and the beta rule emits either `beta = ...` or `beta < ...`.

Radio spectral indices are rejected. `spectral index` and `Gamma` aliases require nearby X-ray, gamma-ray, spectrum, or high-energy instrument context.

## Certainty And Units

`about`, `approximately`, `around`, `roughly`, `preliminary`, and `~` make the annotation `tentative`; other accepted values are `confirmed`.

Physical properties require a recognized unit: `keV`, `MeV`, `GeV`, `erg`, `erg/cm^2`, `erg/cm^2/s`, or `ph/s/cm^2` as appropriate. `power law index`, `photon index`, `spectral index`, `alpha`, and `beta` are legitimately dimensionless.

## Scientific Context Comment

Comments combine the reporting or governing instrument with the energy band belonging to the value's clause: `<instrument>, <band>`. Fluence and peak flux use their sentence; Eiso uses only its own sentence; spectral-fit parameters may use the governing fit paragraph.

Band lookup rejects candidates from sentences containing `rest-frame`, `isotropic`, `Liso`, `Eiso`, `Ep,i,z`, or `Ep,p,z` when resolving observed spectral parameters. This prevents a derived `1-10000 keV` band from leaking into an observed `Epeak` or index. A duration band is also excluded from spectral-fit attribution.

## Non-Property Gates

Optical magnitudes, redshifts, coordinates, radio flux densities in `Jy`, `mJy`, or `uJy`, and hydrogen column density are not emitted. A standalone `cutoff energy` is suppressed when nearby text identifies it as `Epeak`, preventing duplicate properties.

Candidate spans stop at the first complete value and unit. This prevents a later number, such as a column density in the same sentence, from replacing the property's own value.

## De-Overlap

Property-specific rules have stable priorities. When candidates overlap, the higher-priority and then longer match is retained; accepted annotations are returned in source order.

## Known Limitations

The extractor does not emit luminosity (`Liso`), rest-frame peak-energy variants, column density, or arbitrary model parameters. Energy-band and instrument comments depend on explicit clause or paragraph structure, so loosely attributed prose may retain only the instrument or no context comment.
