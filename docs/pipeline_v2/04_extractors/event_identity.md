# Event Identity Extractor

For whom: developers maintaining event-name extraction and annotators who want to understand identity preannotations.

`EventIdentityExtractor` finds names and trigger identifiers that can identify the event discussed by a Circular. It emits `EVENT_IDENTITY` annotations with `target="event"` and preserves the exact raw name in `text` while normalizing `value` into a canonical form for downstream matching.

## Output

| Field | Value |
|---|---|
| `label` | `EVENT_IDENTITY` |
| `target` | `event` |
| `certainty` | `confirmed` |
| `method` | `regex` |
| `extractor_id` | `event-identity-v1` |
| `extractor_version` | `0.1` |

## Patterns

| Rule ID | Family | Example raw text | Example value |
|---|---|---|---|
| `event_identity.grb_dayfraction` | GRB day-fraction identifiers | `GRB230101.09` | `GRB 230101.09` |
| `event_identity.ep_wxt_trigger` | Einstein Probe WXT trigger identifiers | `EP-WXT trigger 01709176712` | `EP-WXT 01709176712` |
| `event_identity.ep_fxt_trigger` | Einstein Probe FXT trigger identifiers | `EP-FXT 01709177837` | `EP-FXT 01709177837` |
| `event_identity.ep_dayfraction` | EP day-fraction identifiers | `EP 260225.148` | `EP 260225.148` |
| `event_identity.grb` | Canonical GRB names | `GRB230101A` | `GRB 230101A` |
| `event_identity.ep` | Short EP names | `EP240315a` | `EP 240315a` |
| `event_identity.at_sn` | TNS AT and SN names | `AT2023bic` | `AT 2023bic` |
| `event_identity.ztf` | ZTF names | `ZTF23aaarlti` | `ZTF23aaarlti` |
| `event_identity.icecube` | IceCube alert names | `IceCube 230101A` | `IceCube-230101A` |
| `event_identity.gw` | GW names | `GW230529_123456` | `GW230529_123456` |
| `event_identity.sname` | LVK S-names | `S231113a` | `S231113a` |

The extractor also exposes `is_canonical_identity(value)`. The sweep uses that function for `identity_value_weird` instead of maintaining a duplicate copy of the canonical formats. This is a deliberate single-source-of-truth rule: the code that produces canonical identity values also defines what valid canonical identity values look like.

## Review Semantics

The extractor compares normalized values against the canonical document header. If the value appears in the header, it is treated as the main event identity and `needs_review=False`. If it appears only in the body, the annotation remains `target="event"` but gets `needs_review=True` because it may be an alias, a comparison event, or a referenced event.

Some formats always require review:

| Rule | Why |
|---|---|
| `event_identity.grb_dayfraction` | A day-fraction value such as `GRB 230101.09` may map to a later lettered GRB name. |
| `event_identity.ep_wxt_trigger` | EP-WXT trigger identifiers are not always the final source name. |
| `event_identity.ep_fxt_trigger` | EP-FXT trigger identifiers also need canonical source verification. |
| `event_identity.ep_dayfraction` | EP day-fraction identifiers need event/source mapping verification. |

## Table-Row Filter

Catalog-like Circulars can contain rows such as:

```text
| SN_LIKE | 2290036 | AT2025gek | 145.199481 | 10.828527 | 20.77 | 0.04 |
```

Those names are listed objects, not the identity of the Circular. The helper `is_in_table_row()` suppresses `AT/SN` and `ZTF` matches inside table-like rows. The filter is intentionally limited to those families; GRB, EP, GW, IceCube, and S-names are not suppressed by this table heuristic.

## Real Example: Circular 33130

The subject contains:

```text
GRB 230101A: Fermi GBM Final Real-time Localization
```

The extractor emits `GRB 230101A` as `EVENT_IDENTITY`. The same normalized value appears in the header, so the annotation is not marked for review.

## Known Limitations

The extractor is still regex-based. It cannot prove that a body-only identity is the main event, and it cannot map all trigger identifiers to final canonical aliases by itself. Those cases are intentionally handed to the annotator through `needs_review=True`.
