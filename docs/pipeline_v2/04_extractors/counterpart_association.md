# Counterpart Association Extractor

For whom: developers maintaining counterpart-link extraction and annotators reviewing candidate and confirmed association spans.

`CounterpartAssociationExtractor` emits `COUNTERPART_ASSOCIATION` only when a phrase establishes a source's role as the event counterpart or afterglow. It is deliberately conservative: bare mentions of an afterglow or counterpart do not establish an association.

## Output

| Field | Value |
|---|---|
| `label` | `COUNTERPART_ASSOCIATION` |
| `target` | `counterpart` |
| `certainty` | `candidate` or `confirmed` |
| `method` | `regex` |
| `extractor_id` | `counterpart-association-v1` |
| `extractor_version` | `0.1` |

`value` and `unit` are unset because the selected clause is the association evidence. `comment` is unset and `needs_review=False` for current captures.

## Rules

| Rule ID | What it captures | Example |
|---|---|---|
| `counterpart_association.identify` | a role phrase governed by `we identify`, `report`, `detect`, `propose`, or `confirm` | `We detected a candidate optical afterglow` |
| `counterpart_association.identify_as` | identification language followed by `as the` counterpart or afterglow | `identified the transient as the optical counterpart` |
| `counterpart_association.suggest` | an explicit strong suggestion that `this` is the counterpart or afterglow | `strongly suggest this is the optical counterpart` |
| `counterpart_association.confirmed_role` | a role with an explicit confirmation marker | `spectroscopically confirmed optical counterpart` |
| `counterpart_association.candidate_role` | qualified role phrases and role-plus-candidate forms | `candidate optical counterpart` |
| `counterpart_association.likely_role` | likely, possible, probable, or potential roles | `possible counterpart` |
| `counterpart_association.role_relation` | counterpart or afterglow explicitly related `of` or `to` an event | `the optical afterglow of` |
| `counterpart_association.modality_counterpart` | a modality-qualified counterpart role | `radio counterpart` |

## Certainty

`candidate` is the default, including explicit `candidate`, `possible`, `likely`, and `strongly suggest` language. The extractor uses `confirmed` only when the matched evidence contains `confirmed`, `spectroscopically confirmed`, `unambiguously`, `firmly associated`, or an equivalent confirmation phrase.

The certainty expresses association status, not detection significance.

## Association-Establishing Gate

Accepted spans contain a scientific role plus enough syntax to establish the link. Examples include a modality-qualified `optical counterpart`, a `candidate optical afterglow`, or an identification verb governing the role.

The following do not establish the role and are rejected:

```text
afterglow model
afterglow emission
The counterpart was discussed in the previous circular.
```

## Negation Gate

Clause-level prefix and suffix checks reject `no`, `not`, `without`, failed detection, inability, and unlikely-identity contexts. For example, `No optical counterpart consistent with the INTEGRAL position` belongs to `NEGATIVE_STATEMENT`, not this extractor.

The telescope acronym `NOT` in a subject is treated as an instrument name rather than negation.

## Identity Gate

Pure alias equations and slash links such as `GOTO26fua / AT2026owq` or `A = B` belong to `EVENT_IDENTITY`. They are not counterpart-role evidence.

## De-Overlap

Identification, suggestion, and confirmed-role rules outrank qualified and generic role rules. When two rules overlap, the higher-priority and then longer span is retained; results are returned in source order.

## Known Limitations

The extractor recognizes a finite event-name and modality vocabulary and does not resolve pronouns or multi-sentence association arguments. Unqualified role mentions are intentionally under-captured when local syntax does not establish the event link.
