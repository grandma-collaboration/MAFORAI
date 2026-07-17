"""Validated tagsets for EVENT_EVIDENCE annotations."""

LABELS = frozenset(
    {
        "EVENT_IDENTITY",
        "TRIGGER_TIME",
        "TRIGGER_INSTRUMENT",
        "LOCALIZATION",
        "COUNTERPART_ASSOCIATION",
        "REDSHIFT_EVENT",
        "REDSHIFT_CONTEXT",
        "T90",
        "DURATION_GENERAL",
        "SPECTROSCOPY",
        "HIGH_ENERGY_PROPERTY",
        "HOST_CONTEXT",
        "CLASSIFICATION_INTERPRETATION",
        "NEGATIVE_STATEMENT",
        "LIGHTCURVE_EVOLUTION",
    }
)

TARGETS = frozenset({"event", "counterpart", "host", "nearby_galaxy", "instrument", "unknown"})

CERTAINTIES = frozenset({"confirmed", "candidate", "tentative", "rejected", "unclear"})
