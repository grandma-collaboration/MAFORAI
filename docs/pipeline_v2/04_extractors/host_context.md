# Host Context Extractor

For whom: developers maintaining host-galaxy context extraction and annotators reviewing host, offset, and nearby-galaxy spans.

`HostContextExtractor` emits `HOST_CONTEXT` for host-galaxy relationships, candidate or ambiguous hosts, projected offsets, and nearby galaxies used only as context. It captures the relationship clause rather than duplicating a redshift value.

## Output

| Field | Host context | Nearby-galaxy context |
|---|---|---|
| `label` | `HOST_CONTEXT` | `HOST_CONTEXT` |
| `target` | `host` | `nearby_galaxy` |
| `certainty` | `unclear` or `confirmed` | `unclear` |
| `method` | `regex` | `regex` |
| `extractor_id` | `host-context-v1` | `host-context-v1` |
| `extractor_version` | `0.1` | `0.1` |

`value` and `unit` are unset. `comment` is unset and `needs_review=False`; the exact host or galaxy relationship remains in `text`.

## Rules

| Rule ID | What it captures | Example |
|---|---|---|
| `host_context.ambiguous` | unclear host associations and explicit host absence | `host association is not obvious` |
| `host_context.candidate` | candidate, possible, likely, or putative hosts | `host candidate` |
| `host_context.offset` | angular or projected offsets, separations, and galaxy vicinity | `offset from the host galaxy` |
| `host_context.host` | explicit host-galaxy and galaxy-association language | `association with the galaxy` |
| `host_context.context` | nearby galaxies mentioned only as field context | `nearby galaxies` |

## Target Selection

Host, candidate-host, ambiguity, and offset rules use `target="host"`. Only `host_context.context` uses `target="nearby_galaxy"`, because `nearby galaxies` does not propose a host association by itself.

## Certainty

`unclear` is the default, including candidate hosts, offsets, nearby galaxies, and ambiguous associations. The extractor upgrades to `confirmed` only when nearby text explicitly establishes a host, for example `confirmed host galaxy` or `the host galaxy at z=0.473`.

The confirmed annotation still spans only `host galaxy`; the redshift token is not included.

## Host Phrase Scope

The broad host rule covers `host galaxy`, `host association`, `underlying galaxy`, explicit `association with the galaxy`, and relation verbs such as `hosted by`, `resides in`, and `coincident with`. A generic galaxy mention without one of these relationships is not treated as a host proposal.

## Redshift Gate

Pure redshift statements such as `A galaxy at z=0.473` or `We measure a redshift of z=0.473` are not host-context evidence. They belong to `REDSHIFT_CONTEXT` or `REDSHIFT_EVENT` according to attribution.

Host rules require an explicit relationship term such as `host`, `candidate`, `association`, `offset`, `underlying`, `vicinity`, `nearby`, `hosted`, `resides`, or `coincident`. This prevents a bare field-galaxy redshift from becoming `HOST_CONTEXT`.

## Offset Gate

Direct forms such as `offset from the host` and `5 kpc in projection from the galaxy` carry their own host context. A generic `offset of <number> arcsec` is accepted only when the containing sentence also mentions host or galaxy context.

Supported distance expressions include arcseconds, arcminutes, and kiloparsecs. Numeric values remain part of the evidence span but are not copied into `value`.

## De-Overlap

Ambiguous-host clauses have highest priority, followed by candidate and explicit offset forms, then broad host and nearby-galaxy phrases. The higher-priority and then longer overlapping span is retained.

## Known Limitations

The extractor does not decide whether a candidate galaxy is physically associated, normalize projected distances, or distinguish every foreground and background galaxy. Confirmed-host certainty depends on a small set of explicit establishment phrases.
