"""STATE(event, T): fold the ledger up to a cutoff and produce two views of the state.

The two views are deliberately separate and must never be conflated:

* ``matching_text``  — built ONLY from descriptive facts (``gcn_evidence``, ``photometry``,
  ``redshift_version``). These describe the OBJECT. It is the text that gets embedded.
* ``dossier_text``   — the full view, which MAY include decisions (summaries,
  classifications, catalogue annotations). It is for the answer side, never for matching.

The non-leakage rule is the point of this layer: only facts with ``t_known <= T`` may enter
a state. No "known at T" flag is ever evaluated from the full trajectory.

Localisation is classified PER CIRCULAR and then combined across the circulars known at T
(see ``_localization_at_T``). A coordinate accompanied by a degree-scale box in the same
circular is a coarse centroid and is suppressed; a coordinate reported without one is a
genuine refinement. Shape is tested before unit, because 581 coordinate facts carry
``unit_raw='deg'`` — the unit of the coordinate itself, not an error radius.

Read-only over ``data/ledger/``. Pure and deterministic: the same (event_id, T) always
returns the same object. Engine is pandas/pyarrow — DuckDB is not installed in this venv.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

STATE_TEXT_VERSION = "v3"

DEFAULT_LEDGER_ROOT = "/home/meneses/project_astronomical/MAFORAI/data/ledger"

# Coarse wavelength-region classifier for the raw bands present in the ledger. This is
# intentionally independent of the canonical band-normalisation map. Exact raw tokens
# stay visible in matching_text; unmapped tokens are reported as "unknown".
BAND_REGION_MAP = {
    # Optical broadband, clear/open, survey, and medium-band filters.
    "B": "optical",
    "B (Vega)": "optical",
    "b": "optical",
    "C": "optical",
    "c": "optical",
    "clear": "optical",
    "Clear": "optical",
    "Clear (G)": "optical",
    "CR": "optical",
    "cyan": "optical",
    "DECam-r": "optical",
    "DECam-z": "optical",
    "G": "optical",
    "g": "optical",
    "g (AB)": "optical",
    "g'": "optical",
    "g\u2019": "optical",
    "G+Gbp+Grp": "optical",
    "Gaia G": "optical",
    "Gbp": "optical",
    "Grp": "optical",
    "I": "optical",
    "i": "optical",
    "i (AB)": "optical",
    "i'": "optical",
    "i\u2019": "optical",
    "i\u2019 (AB)": "optical",
    "Ic": "optical",
    "Ic (Vega)": "optical",
    "Johnson V": "optical",
    "L": "optical",
    "Lim-excluded": "optical",
    "Luminance": "optical",
    "m400": "optical",
    "m425": "optical",
    "m450": "optical",
    "m475": "optical",
    "m500": "optical",
    "m525": "optical",
    "m550": "optical",
    "m575": "optical",
    "m600": "optical",
    "m625": "optical",
    "m650": "optical",
    "m675": "optical",
    "m700": "optical",
    "m725": "optical",
    "m750": "optical",
    "m775": "optical",
    "m800": "optical",
    "m825": "optical",
    "m850": "optical",
    "m875": "optical",
    "Mg": "optical",
    "Mr": "optical",
    "Mu": "optical",
    "Mv": "optical",
    "o": "optical",
    "Open": "optical",
    "orange": "optical",
    "P": "optical",
    "P-": "optical",
    "P/": "optical",
    "P\\": "optical",
    "P\\\\": "optical",
    "R": "optical",
    "R (AB)": "optical",
    "R (Vega)": "optical",
    "r": "optical",
    "r (AB)": "optical",
    "r'": "optical",
    "r\u2019": "optical",
    "Rc": "optical",
    "Rc (Vega)": "optical",
    "Red": "optical",
    "SDSS": "optical",
    "SDSS-g": "optical",
    "SDSS-i": "optical",
    "SDSS-r": "optical",
    "sdssg": "optical",
    "sdssg (AB)": "optical",
    "sdssi": "optical",
    "sdssi (AB)": "optical",
    "sdssr": "optical",
    "sdssr (AB)": "optical",
    "U": "optical",
    "u": "optical",
    "u (fc)": "optical",
    "u (FC)": "optical",
    "u_FC": "optical",
    "V": "optical",
    "v": "optical",
    "v_FC": "optical",
    "VT_B": "optical",
    "VT_R": "optical",
    "w": "optical",
    "Wh": "optical",
    "wh": "optical",
    "wh_FC": "optical",
    "white": "optical",
    "White": "optical",
    "WHITE": "optical",
    "white (FC)": "optical",
    "white (fc)": "optical",
    "white_FC": "optical",
    "Z": "optical",
    "z": "optical",
    "z'": "optical",
    "z\u2019": "optical",
    "ztfg": "optical",
    # Near-infrared filters.
    "Y": "infrared",
    "y": "infrared",
    "J": "infrared",
    "H": "infrared",
    "Hs": "infrared",
    "K": "infrared",
    "Ks": "infrared",
    "2massj": "infrared",
    "2massh": "infrared",
    "2massks": "infrared",
    # Swift/UVOT ultraviolet aliases. Lowercase u remains optical above.
    "m2": "uv",
    "M2": "uv",
    "um2": "uv",
    "uvm2": "uv",
    "UVM2": "uv",
    "uvw1": "uv",
    "UVW1": "uv",
    "uvw2": "uv",
    "UVW2": "uv",
    "uw1": "uv",
    "uw2": "uv",
    "w1": "uv",
    "W1": "uv",
    "w2": "uv",
    "W2": "uv",
    "u_uvot": "uv",
    # No X-ray token is currently present, but these explicit forms prevent accidental
    # optical classification if they enter the ledger.
    "X-ray": "xray",
    "xray": "xray",
    "XRT": "xray",
    "0.3-10 keV": "xray",
    "0.5-4 keV": "xray",
    "0.5-10 keV": "xray",
}
BAND_REGION_ORDER = ("optical", "infrared", "uv", "xray", "unknown")

# Descriptive fact types — these describe the object and are the only input to
# matching_text. Everything else is a decision or derived.
DESCRIPTIVE_FACT_TYPES = ("gcn_evidence", "photometry", "redshift_version")
DOSSIER_ONLY_FACT_TYPES = ("summary_version", "classification", "skyportal_annotation",
                           "comment", "followup_request")

# Localisation scale boundaries, in arcsec.
PRECISE_RADIUS_ARCSEC = 5.0       # a radius this tight is precise on its own
DEGREE_SCALE_ARCSEC = 3600.0      # >= 1 deg is a coarse box

# ---------------------------------------------------------------------------------------
# Text templates. One visible dict so the wording is auditable and versioned; never build
# state wording with inline f-strings elsewhere in this module.
# ---------------------------------------------------------------------------------------
TEXT_TEMPLATES = {
    "header": "{messenger} observed at {dt_hours:g} h after trigger.",
    "trigger_instrument": "Triggered by {instrument}.",
    # localisation, one clause per localization_state (v2 wording)
    "localization_precise": "Precise position available.",
    "localization_precise_coarse": "Precise position available. Initial localisation about"
                                   " {coarse:g}°.",
    "localization_arcmin": "Localised to about {best:g} arcsec.",
    "localization_unlocalized": "Localised only to a coarse {coarse:g}° box; no precise"
                                " position yet.",
    "localization_unknown": "No localisation reported yet.",
    # other presence clauses
    "counterpart": "An optical counterpart is associated.",
    "classification": "Interpreted as {labels}.",
    "redshift": "Redshift z = {z}.",
    "t90": "Burst duration T90 about {t90:g} s.",
    "duration_general": "A burst duration is reported.",
    "detections": "{n} detection{s} in {bands}, magnitude {mag_min:.2f} to {mag_max:.2f}{span}.",
    "detections_span": ", between {t_min:.1f} and {t_max:.1f} h after trigger",
    "detections_nomag": "{n} detection{s} reported in {bands}.",
    "upper_limits": "{n} upper limit{s} reported.",
    "upper_limits_bands": "{n} upper limit{s} reported in {bands}.",
    "lightcurve": "Light-curve evolution is reported.",
    "spectroscopy": "A spectroscopic observation is reported.",
    "host": "Host-galaxy context is reported.",
    "high_energy": "High-energy properties are reported.",
    "negative": "Negative results are reported.",
    # absence clauses — absence at T is phase information, so it is stated explicitly
    "absent_redshift": "No redshift measured yet.",
    "absent_t90": "No reported burst duration.",
    "absent_classification": "No physical classification reported yet.",
    "absent_counterpart": "No counterpart association reported yet.",
    "absent_detection": "No detection reported yet.",
    "absent_lightcurve": "No light-curve evolution reported yet.",
    "absent_spectroscopy": "No spectroscopy reported yet.",
    "absent_host": "No host-galaxy context reported yet.",
    # dossier view
    "dossier_header": "Dossier for {event_id} at {dt_hours:g} h after trigger.",
    "dossier_summary": "Latest summary: {summary}",
    "dossier_classification": "Operational classifications: {labels}.",
    "dossier_annotation": "Catalogue annotations: {n} record{s}.",
}

# Which descriptive concept each fact_subtype supports; drives the absent set at T.
# Localisation is NOT here: it always emits one of the four localization_* clauses.
CONCEPT_SUBTYPES = {
    "redshift": {"REDSHIFT_EVENT", "redshift_version"},
    "t90": {"T90"},
    "classification": {"CLASSIFICATION_INTERPRETATION"},
    "counterpart": {"COUNTERPART_ASSOCIATION"},
    "detection": {"detection"},
    "lightcurve": {"LIGHTCURVE_EVOLUTION"},
    "spectroscopy": {"SPECTROSCOPY"},
    "host": {"HOST_CONTEXT"},
}
ABSENT_ORDER = ["redshift", "t90", "classification", "counterpart", "detection",
                "lightcurve", "spectroscopy", "host"]

_NEUTRINO = {"IceCube", "ANTARES", "KM3NeT"}
_GW = {"LIGO", "Virgo", "KAGRA"}
_NAME_MESSENGER = {
    "gcn_internal": "High-energy transient",
    "grb_internal": "Gamma-ray burst",
    "grb_named": "Gamma-ray burst",
    "ep_internal": "X-ray transient",
    "ztf_like": "Optical transient",
    "tns_like": "Optical transient",
    "other": "Transient",
}

_FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_BARE_NUMBER_RE = re.compile(r"^\s*[-+]?\d+(?:\.\d+)?\s*$")
# Coordinate SHAPE: 'RA=..', 'RA: ..', 'R.A. =', or a Dec field. Tested BEFORE any unit.
_COORD_RE = re.compile(r"(R\.?\s*A\.?\s*[:=])|(\bDec\.?\s*[:=])", re.IGNORECASE)
_ARCSEC_PER = {"arcsec": 1.0, "arcmin": 60.0, "deg": 3600.0}


def _leading_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    m = _FLOAT_RE.search(str(value))
    return float(m.group()) if m else None


def classify_localization_fact(value_raw, unit_raw) -> tuple[str, float | None]:
    """Classify one LOCALIZATION fact. SHAPE FIRST, unit second.

    Returns ('coordinate', None) | ('radius', arcsec) | ('other', None).

    The shape test must precede the unit test: 581 coordinate facts carry unit_raw='deg'
    because the coordinate itself is expressed in degrees ('RA: 23.78 deg'). Keying on the
    unit first would silently reclassify them as degree-scale error radii.
    """
    raw = "" if value_raw is None else str(value_raw)
    if _COORD_RE.search(raw):
        return "coordinate", None
    if _BARE_NUMBER_RE.match(raw):
        unit = ("" if unit_raw is None else str(unit_raw)).strip().lower()
        factor = _ARCSEC_PER.get(unit)
        if factor is not None:
            return "radius", float(raw.strip()) * factor
    return "other", None


# ---------------------------------------------------------------------------------------
# Ledger loading
# ---------------------------------------------------------------------------------------
@dataclass
class Ledger:
    """Facts already joined to their events through BOTH map files, plus the events table."""

    attached: pd.DataFrame          # one row per (event_id, fact)
    events: pd.DataFrame
    by_event: dict[str, pd.DataFrame] = field(default_factory=dict)

    def event_row(self, event_id: str) -> pd.Series:
        rows = self.events[self.events.event_id == event_id]
        if rows.empty:
            raise KeyError(f"Event not in the events table: {event_id}")
        return rows.iloc[0]

    def facts_for(self, event_id: str) -> pd.DataFrame:
        return self.by_event.get(event_id, self.attached.iloc[0:0])


def load_ledger(ledger_root: str = DEFAULT_LEDGER_ROOT) -> Ledger:
    """Load facts, events and both map files, and attach every fact to its event(s)."""
    parts = sorted(glob.glob(os.path.join(
        ledger_root, "facts", "source_system=*", "year=*", "part-*.parquet")))
    if not parts:
        raise FileNotFoundError(f"No fact partitions under {ledger_root}")
    facts = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    if "t_occurred_offset_hours" not in facts.columns:
        facts["t_occurred_offset_hours"] = pd.NA
    for col in ("t_known", "t_occurred"):
        facts[col] = pd.to_datetime(facts[col], utc=True)

    events = pd.read_parquet(os.path.join(ledger_root, "events", "events.parquet"))
    events["t0"] = pd.to_datetime(events["t0"], utc=True)

    map_paths = sorted(glob.glob(os.path.join(ledger_root, "event_container_map", "*.parquet")))
    maps = pd.concat([pd.read_parquet(p) for p in map_paths], ignore_index=True)
    maps = maps[["event_id", "container_type", "container_id"]].drop_duplicates()

    attached = facts.merge(maps, on=["container_type", "container_id"], how="inner")
    attached = attached.merge(events[["event_id", "t0"]], on="event_id", how="left")
    # both clocks in hours from t0; the offset resolves t_occurred when it is absent
    offset = pd.to_numeric(attached["t_occurred_offset_hours"], errors="coerce")
    t_occ_eff = attached["t_occurred"].fillna(
        attached["t0"] + pd.to_timedelta(offset, unit="h"))
    attached["t_occurred_effective"] = t_occ_eff
    attached["dt_known_hours"] = (attached["t_known"] - attached["t0"]).dt.total_seconds() / 3600
    attached["dt_occurred_hours"] = (t_occ_eff - attached["t0"]).dt.total_seconds() / 3600
    # a stable subtype label: the SkyPortal fact types carry a NULL fact_subtype
    attached["subtype_label"] = attached["fact_subtype"].where(
        attached["fact_subtype"].notna(), attached["fact_type"])
    attached = attached.sort_values(["event_id", "t_known", "fact_id"]).reset_index(drop=True)
    by_event = {eid: g for eid, g in attached.groupby("event_id", sort=True)}
    return Ledger(attached=attached, events=events, by_event=by_event)


# ---------------------------------------------------------------------------------------
# The state object
# ---------------------------------------------------------------------------------------
@dataclass
class State:
    event_id: str
    T: pd.Timestamp
    t0: pd.Timestamp
    dt_hours: float
    structured_values: dict[str, Any]
    matching_text: str
    dossier_text: str
    state_text_version: str
    n_descriptive_facts: int
    facts: pd.DataFrame  # the folded rows actually included, for the non-leakage assertion


def _messenger_class(name_pattern_class, instrument: str | None) -> str:
    if instrument:
        head = str(instrument).split("/")[0]
        if head in _NEUTRINO:
            return "Neutrino event"
        if head in _GW:
            return "Gravitational-wave event"
        return "High-energy transient"
    return _NAME_MESSENGER.get(str(name_pattern_class), "Transient")


def _localization_at_T(loc_rows: pd.DataFrame) -> tuple[str, float | None, float | None]:
    """Per-circular classification, combined across the circulars known at T.

    Returns (localization_state, best_radius_arcsec, coarse_radius_deg).

    Within one circular: a coordinate is a genuine refinement only if that circular carries
    no degree-scale radius (a coordinate beside a degree box is a coarse centroid and is
    suppressed). A radius <= 5 arcsec is precise on its own, coordinate or not.
    """
    if loc_rows.empty:
        return "unknown", None, None

    any_precise = False
    sub_degree_radii: list[float] = []   # < 1 deg -> the real localisation scale
    degree_radii: list[float] = []       # >= 1 deg -> the initial coarse box
    for _, circ in loc_rows.groupby("container_id", sort=True):
        coords, radii = [], []
        for _, r in circ.iterrows():
            kind, arcsec = classify_localization_fact(r["value_raw"], r["unit_raw"])
            if kind == "coordinate":
                coords.append(r)
            elif kind == "radius":
                radii.append(arcsec)
        has_degree_box = any(a >= DEGREE_SCALE_ARCSEC for a in radii)
        # a coordinate counts only when this circular reports no degree-scale box
        if coords and not has_degree_box:
            any_precise = True
        # a tight radius is precise regardless of what else the circular says
        if any(a <= PRECISE_RADIUS_ARCSEC for a in radii):
            any_precise = True
        for a in radii:
            (degree_radii if a >= DEGREE_SCALE_ARCSEC else sub_degree_radii).append(a)

    best_radius = min(sub_degree_radii) if sub_degree_radii else None
    coarse_deg = max(degree_radii) / 3600.0 if degree_radii else None

    if any_precise:
        state = "precise"
    elif best_radius is not None:
        state = "arcmin"          # 5 arcsec < r < 1 deg
    elif degree_radii:
        state = "unlocalized"     # only coarse boxes / suppressed centroids
    else:
        # a LOCALIZATION fact was reported but yields no usable precision
        state = "unlocalized"
    return state, best_radius, coarse_deg


def _t90_seconds(rows: pd.DataFrame) -> float | None:
    for _, r in rows.sort_values("t_known").iterrows():
        val = _leading_float(r["value_raw"])
        if val is None:
            continue
        unit = str(r["unit_raw"] or "").strip().lower()
        return val / 1000.0 if unit == "ms" else val
    return None


def _redshift_at_T(desc: pd.DataFrame) -> tuple[bool, float | None]:
    """Redshift in effect at T: latest redshift_version, else latest GCN REDSHIFT_EVENT."""
    versions = desc[desc.fact_type == "redshift_version"].sort_values("t_known")
    for _, r in versions.iloc[::-1].iterrows():
        val = _leading_float(r["value_raw"])
        if val is not None:
            return True, val
    gcn_z = desc[desc.subtype_label == "REDSHIFT_EVENT"].sort_values("t_known")
    for _, r in gcn_z.iloc[::-1].iterrows():
        val = _leading_float(r["value_raw"])
        if val is not None:
            return True, val
    return (not versions.empty or not gcn_z.empty), None


def _grouped_band_text(rows: pd.DataFrame) -> str | None:
    """List every distinct raw band under a coarse wavelength region."""
    bands = {
        str(value).strip()
        for value in rows["band_raw"].dropna().tolist()
        if str(value).strip()
    }
    if not bands:
        return None

    grouped = {region: [] for region in BAND_REGION_ORDER}
    for band in sorted(bands, key=lambda value: (value.casefold(), value)):
        grouped[BAND_REGION_MAP.get(band, "unknown")].append(band)

    return " and ".join(
        f"{region} ({', '.join(grouped[region])})"
        for region in BAND_REGION_ORDER
        if grouped[region]
    )


def compute_state(event_id: str, T, ledger: Ledger) -> State:
    """Fold the ledger for one event up to T and build both views. Pure."""
    T = pd.Timestamp(T)
    if T.tzinfo is None:
        T = T.tz_localize("UTC")
    event = ledger.event_row(event_id)
    t0 = event["t0"]
    rows = ledger.facts_for(event_id)
    folded = rows[rows["t_known"] <= T]                     # THE non-leakage rule
    desc = folded[folded.fact_type.isin(DESCRIPTIVE_FACT_TYPES)]
    dt_hours = float((T - t0).total_seconds() / 3600) if pd.notna(t0) else float("nan")
    present = set(desc["subtype_label"].dropna().unique())

    def sub(label):
        return desc[desc.subtype_label == label]

    instrument = None
    ti = sub("TRIGGER_INSTRUMENT")
    if not ti.empty:
        vals = ti.sort_values("t_known")["value_raw"].dropna()
        instrument = str(vals.iloc[0]) if not vals.empty else None

    loc_rows = sub("LOCALIZATION")
    loc_state, best_radius, coarse_deg = _localization_at_T(loc_rows)
    t90 = _t90_seconds(sub("T90"))
    z_known, z_value = _redshift_at_T(desc)

    dets, lims = sub("detection"), sub("upper_limit")
    dets_timed = dets[dets["dt_occurred_hours"].notna() & dets["mag"].notna()].sort_values(
        ["dt_occurred_hours", "fact_id"])
    first_mag = last_mag = first_band = last_band = None
    if not dets_timed.empty:
        first_mag = float(dets_timed.iloc[0]["mag"])
        first_band = dets_timed.iloc[0]["band_raw"]
        last_mag = float(dets_timed.iloc[-1]["mag"])
        last_band = dets_timed.iloc[-1]["band_raw"]

    clf = sub("CLASSIFICATION_INTERPRETATION")
    clf_labels = sorted({str(v) for v in clf["value_raw"].dropna().unique()})

    structured = {
        "event_id": event_id,
        "dt_hours": round(dt_hours, 6),
        "messenger_class": _messenger_class(event.get("name_pattern_class"), instrument),
        "trigger_instrument": instrument,
        "has_localization": bool(not loc_rows.empty),
        "localization_state": loc_state,
        "best_radius_arcsec": best_radius,
        "coarse_radius_deg": coarse_deg,
        "has_counterpart": bool(not sub("COUNTERPART_ASSOCIATION").empty),
        "first_detection_mag": first_mag,
        "first_detection_band": (None if first_band is None or pd.isna(first_band)
                                 else str(first_band)),
        "last_detection_mag": last_mag,
        "last_detection_band": (None if last_band is None or pd.isna(last_band)
                                else str(last_band)),
        "n_detections": int(len(dets)),
        "n_upper_limits": int(len(lims)),
        "z_known_at_T": bool(z_known),
        "z_value_at_T": z_value,
        "t90_known_at_T": bool(not sub("T90").empty),
        "t90_seconds_at_T": t90,
        "classification_known": bool(not clf.empty),
        "classification_labels": clf_labels or None,
    }

    matching = _build_matching_text(structured, present, dets, lims, clf_labels)
    dossier = _build_dossier_text(event_id, dt_hours, folded, matching)
    return State(event_id=event_id, T=T, t0=t0, dt_hours=dt_hours,
                 structured_values=structured, matching_text=matching, dossier_text=dossier,
                 state_text_version=STATE_TEXT_VERSION, n_descriptive_facts=int(len(desc)),
                 facts=folded)


def _localization_clause(sv) -> str:
    t = TEXT_TEMPLATES
    state, best, coarse = (sv["localization_state"], sv["best_radius_arcsec"],
                           sv["coarse_radius_deg"])
    if state == "precise":
        return (t["localization_precise_coarse"].format(coarse=round(coarse, 2))
                if coarse is not None else t["localization_precise"])
    if state == "arcmin":
        return t["localization_arcmin"].format(best=round(best, 1))
    if state == "unlocalized":
        return (t["localization_unlocalized"].format(coarse=round(coarse, 2))
                if coarse is not None else t["localization_unknown"])
    return t["localization_unknown"]


def _build_matching_text(sv, present, dets, lims, clf_labels) -> str:
    """Descriptive facts only. No decision content ever enters this text."""
    t = TEXT_TEMPLATES
    out = [t["header"].format(messenger=sv["messenger_class"], dt_hours=round(sv["dt_hours"], 1))]
    if sv["trigger_instrument"]:
        out.append(t["trigger_instrument"].format(instrument=sv["trigger_instrument"]))
    out.append(_localization_clause(sv))
    if clf_labels:
        out.append(t["classification"].format(labels=", ".join(clf_labels)))
    if sv["t90_known_at_T"] and sv["t90_seconds_at_T"] is not None:
        out.append(t["t90"].format(t90=sv["t90_seconds_at_T"]))
    elif sv["t90_known_at_T"]:
        out.append(t["duration_general"])
    if sv["z_known_at_T"] and sv["z_value_at_T"] is not None:
        out.append(t["redshift"].format(z=sv["z_value_at_T"]))
    if sv["has_counterpart"]:
        out.append(t["counterpart"])
    # photometry is summarised, never enumerated
    if len(dets):
        mags = dets["mag"].dropna()
        times = dets["dt_occurred_hours"].dropna()
        bands = _grouped_band_text(dets) or "unknown (unspecified)"
        span = (t["detections_span"].format(t_min=float(times.min()), t_max=float(times.max()))
                if len(times) else "")
        if len(mags):
            out.append(t["detections"].format(
                n=len(dets), s="" if len(dets) == 1 else "s", bands=bands,
                mag_min=float(mags.min()), mag_max=float(mags.max()), span=span))
        else:
            out.append(t["detections_nomag"].format(
                n=len(dets), s="" if len(dets) == 1 else "s", bands=bands))
    if len(lims):
        bands = _grouped_band_text(lims)
        template = t["upper_limits_bands"] if bands else t["upper_limits"]
        out.append(template.format(
            n=len(lims), s="" if len(lims) == 1 else "s", bands=bands))
    for label, key in (("LIGHTCURVE_EVOLUTION", "lightcurve"), ("SPECTROSCOPY", "spectroscopy"),
                       ("HOST_CONTEXT", "host"), ("HIGH_ENERGY_PROPERTY", "high_energy"),
                       ("NEGATIVE_STATEMENT", "negative")):
        if label in present:
            out.append(t[key])
    # absence is phase information: state what is not yet known
    for concept in ABSENT_ORDER:
        if not (CONCEPT_SUBTYPES[concept] & present):
            out.append(t[f"absent_{concept}"])
    return " ".join(out)


def _build_dossier_text(event_id, dt_hours, folded, matching) -> str:
    """Full view for the answer side. MAY carry decisions; never used for matching."""
    t = TEXT_TEMPLATES
    out = [t["dossier_header"].format(event_id=event_id, dt_hours=round(dt_hours, 1)), matching]
    summaries = folded[folded.fact_type == "summary_version"].sort_values("t_known")
    summaries = summaries[summaries["text"].notna()]
    if not summaries.empty:
        out.append(t["dossier_summary"].format(
            summary=str(summaries.iloc[-1]["text"]).strip().replace("\n", " ")))
    clf = folded[folded.fact_type == "classification"]
    labels = sorted({str(v) for v in clf["value_raw"].dropna().unique()})
    if labels:
        out.append(t["dossier_classification"].format(labels=", ".join(labels)))
    ann = folded[folded.fact_type == "skyportal_annotation"]
    if len(ann):
        out.append(t["dossier_annotation"].format(n=len(ann), s="" if len(ann) == 1 else "s"))
    return " ".join(out)


def STATE(event_id: str, T, ledger: Ledger | None = None,
          ledger_root: str = DEFAULT_LEDGER_ROOT) -> State:
    """Public entry point: STATE(event, T)."""
    return compute_state(event_id, T, ledger if ledger is not None else load_ledger(ledger_root))


state_at = STATE  # backward-compatible alias

__all__ = ["STATE", "State", "Ledger", "load_ledger", "compute_state", "state_at",
           "classify_localization_fact", "TEXT_TEMPLATES", "STATE_TEXT_VERSION",
           "DESCRIPTIVE_FACT_TYPES", "DOSSIER_ONLY_FACT_TYPES"]
