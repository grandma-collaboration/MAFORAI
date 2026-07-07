from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


# Lista ampliable; agregar instrumentos nuevos aqui sin tocar la logica del extractor.
@dataclass(frozen=True)
class InstrumentSpec:
    canonical: str
    rule_suffix: str
    aliases: tuple[str, ...]


INSTRUMENTS: tuple[InstrumentSpec, ...] = (
    InstrumentSpec(
        canonical="Swift/BAT",
        rule_suffix="swift_bat",
        aliases=("Swift Burst Alert Telescope", "Swift/BAT", "Swift-BAT", "Swift BAT", "BAT"),
    ),
    InstrumentSpec(
        canonical="Fermi/GBM",
        rule_suffix="fermi_gbm",
        aliases=("Fermi Gamma-ray Burst Monitor", "Fermi/GBM", "Fermi-GBM", "Fermi GBM", "GBM"),
    ),
    InstrumentSpec(
        canonical="Fermi/LAT",
        rule_suffix="fermi_lat",
        aliases=("Fermi/LAT", "Fermi-LAT", "Fermi LAT", "LAT"),
    ),
    InstrumentSpec(
        canonical="SVOM/GRM",
        rule_suffix="svom_grm",
        aliases=("SVOM/GRM", "SVOM-GRM", "SVOM GRM", "GRM"),
    ),
    InstrumentSpec(
        canonical="SVOM/ECLAIRs",
        rule_suffix="svom_eclairs",
        aliases=("SVOM/ECLAIRs", "SVOM-ECLAIRs", "SVOM ECLAIRs", "ECLAIRs"),
    ),
    InstrumentSpec(
        canonical="Konus-Wind",
        rule_suffix="konus_wind",
        aliases=("Konus-Wind", "Wind-KONUS", "Konus Wind", "KONUS"),
    ),
    InstrumentSpec(
        canonical="CALET/CGBM",
        rule_suffix="calet_cgbm",
        aliases=("CALET Gamma-ray Burst Monitor", "CALET/CGBM", "CALET-CGBM", "CALET CGBM", "CGBM"),
    ),
    InstrumentSpec(
        canonical="AGILE/MCAL",
        rule_suffix="agile_mcal",
        aliases=("AGILE Mini-CALorimeter", "AGILE/MCAL", "AGILE-MCAL", "AGILE MCAL", "MCAL"),
    ),
    InstrumentSpec(
        canonical="MAXI",
        rule_suffix="maxi",
        aliases=("MAXI/GSC", "MAXI-GSC", "MAXI GSC", "MAXI"),
    ),
    InstrumentSpec(
        canonical="IceCube",
        rule_suffix="icecube",
        aliases=("IceCube",),
    ),
    InstrumentSpec(
        canonical="INTEGRAL",
        rule_suffix="integral",
        aliases=("INTEGRAL/SPI-ACS", "INTEGRAL SPI-ACS", "SPI-ACS", "INTEGRAL"),
    ),
    InstrumentSpec(
        canonical="GECAM",
        rule_suffix="gecam",
        aliases=("GECAM",),
    ),
    InstrumentSpec(
        canonical="GRBAlpha",
        rule_suffix="grbalpha",
        aliases=("GRBAlpha", "GRB Alpha"),
    ),
    InstrumentSpec(
        canonical="VZLUSAT-2",
        rule_suffix="vzlusat_2",
        aliases=("VZLUSAT-2", "VZLUSAT 2"),
    ),
    InstrumentSpec(
        canonical="AstroSat/CZTI",
        rule_suffix="astrosat_czti",
        aliases=("AstroSat/CZTI", "AstroSat-CZTI", "AstroSat CZTI", "CZTI"),
    ),
    InstrumentSpec(
        canonical="EP/WXT",
        rule_suffix="ep_wxt",
        aliases=("EP/WXT", "EP-WXT", "EP WXT", "Einstein Probe WXT", "WXT"),
    ),
)


_SPEC_BY_CANONICAL = {instrument.canonical: instrument for instrument in INSTRUMENTS}


def match_instrument(text_fragment: str) -> tuple[str, tuple[int, int]] | None:
    best: tuple[str, tuple[int, int]] | None = None
    for spec in INSTRUMENTS:
        for pattern in _alias_patterns(spec.aliases):
            match = pattern.search(text_fragment)
            if match is None:
                continue
            candidate = (spec.canonical, (match.start(), match.end()))
            if best is None or _match_sort_key(candidate) < _match_sort_key(best):
                best = candidate
    return best


def iter_instrument_matches(text: str) -> list[tuple[str, int, int]]:
    matches: list[tuple[str, int, int]] = []
    cursor = 0
    while cursor < len(text):
        match = match_instrument(text[cursor:])
        if match is None:
            break
        canonical, (start, end) = match
        absolute_start = cursor + start
        absolute_end = cursor + end
        matches.append((canonical, absolute_start, absolute_end))
        cursor = max(absolute_start + 1, absolute_end)
    return matches


def rule_id_for_instrument(canonical: str) -> str:
    spec = _SPEC_BY_CANONICAL[canonical]
    return f"trigger_instrument.{spec.rule_suffix}"


@lru_cache(maxsize=None)
def _alias_patterns(aliases: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(_compile_alias(alias) for alias in sorted(aliases, key=len, reverse=True))


def _compile_alias(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    escaped = escaped.replace(r"\ ", r"[\s\-]+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def _match_sort_key(match: tuple[str, tuple[int, int]]) -> tuple[int, int]:
    _, (start, end) = match
    return start, -(end - start)
