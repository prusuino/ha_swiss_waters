"""Bathing sites: water quality (FOEN) and lake bathing temperatures (Zurich).

Two sources, both official open data:

* Bathing water quality — the FOEN's "Qualität der Badegewässer" cube on the
  same LINDAS service the hydrological data comes from. The cantons sample
  E. coli and intestinal enterococci at the ~215 official bathing sites during
  the season and report them to the FOEN. This is a seasonal assessment, not
  a live reading: the published data covers completed seasons, so the
  classification refers to the most recent season with samples.
* Bathing water temperature — the two lake stations of the Zurich water police
  (Tiefenbrunnen, Mythenquai), published by the city of Zurich as open data
  (CC0) and updated every 10 minutes.

Classification follows the EU Bathing Water Directive (2006/7/EC, Annex I) for
inland waters, which Switzerland applies as well: percentiles of the
log-normally distributed sample values per season.
"""
from __future__ import annotations

import math
import statistics
from datetime import date

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    BATHING_CUBE_BASE,
    BATHING_SITE_TERM_SET,
    BATHING_TEMP_STATIONS,
    BATHING_TEMP_URL,
    ENVIRONMENT_QUERY_URL,
)

# EU Bathing Water Directive 2006/7/EC, Annex I — inland waters (cfu/100 ml).
# excellent/good use the 95th percentile, sufficient the 90th percentile.
_LIMITS = {
    "excellent": {"E.coli": 500, "Enterokokken": 200, "percentile": 95},
    "good": {"E.coli": 1000, "Enterokokken": 400, "percentile": 95},
    "sufficient": {"E.coli": 900, "Enterokokken": 330, "percentile": 90},
}
QUALITY_CLASSES = ["excellent", "good", "sufficient", "poor"]

_SITES_SPARQL = f"""
PREFIX schema: <http://schema.org/>
SELECT ?id ?name ?lat ?lon ?canton WHERE {{
  ?loc schema:inDefinedTermSet <{BATHING_SITE_TERM_SET}> ;
       schema:identifier ?id ; schema:name ?name ;
       schema:latitude ?lat ; schema:longitude ?lon .
  OPTIONAL {{ ?loc schema:containedInPlace ?canton }}
}}
"""

# Note: the dimension IRIs live on the cube base *without* the version
# segment, while the observation set is addressed with the version.
_MEASUREMENTS_SPARQL = """
PREFIX cube: <https://cube.link/>
PREFIX dim: <{dimensions}/>
PREFIX schema: <http://schema.org/>
SELECT ?id ?date ?param ?value WHERE {{
  <{cube}> cube:observationSet/cube:observation ?obs .
  ?obs dim:dateofprobing ?date ; dim:parametertype ?param ;
       dim:value ?value ; dim:location ?loc .
  ?loc schema:identifier ?id .
  FILTER(?date >= "{since}"^^<http://www.w3.org/2001/XMLSchema#date>)
}}
"""

_VERSION_SPARQL = f"""
PREFIX schema: <http://schema.org/>
SELECT ?cube WHERE {{
  ?cube a <https://cube.link/Cube> ;
        schema:creativeWorkStatus <https://ld.admin.ch/vocabulary/CreativeWorkStatus/Published> .
  FILTER(STRSTARTS(STR(?cube), "{BATHING_CUBE_BASE}"))
}}
"""


def _percentile_lognormal(values: list[float], percentile: int) -> float:
    """Percentile of log-normally distributed sample values (Annex II method)."""
    logs = [math.log10(max(v, 1.0)) for v in values]
    mean = statistics.fmean(logs)
    sigma = statistics.stdev(logs) if len(logs) > 1 else 0.0
    factor = 1.65 if percentile == 95 else 1.282
    return 10 ** (mean + factor * sigma)


def classify(samples: dict[str, list[float]]) -> str | None:
    """Classify one bathing site from its season samples per parameter."""
    if not any(samples.get(p) for p in ("E.coli", "Enterokokken")):
        return None
    for quality in ("excellent", "good", "sufficient"):
        limits = _LIMITS[quality]
        ok = True
        for parameter in ("E.coli", "Enterokokken"):
            values = samples.get(parameter) or []
            if not values:
                continue
            if _percentile_lognormal(values, limits["percentile"]) > limits[parameter]:
                ok = False
                break
        if ok:
            return quality
    return "poor"


async def _sparql(hass: HomeAssistant, query: str) -> list[dict]:
    session = async_get_clientsession(hass)
    async with session.post(
        ENVIRONMENT_QUERY_URL,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=45,
    ) as resp:
        resp.raise_for_status()
        payload = await resp.json(content_type=None)
    return payload.get("results", {}).get("bindings", [])


async def async_latest_cube(hass: HomeAssistant) -> str:
    """IRI of the most recent published version of the bathing water cube."""
    bindings = await _sparql(hass, _VERSION_SPARQL)
    best_iri = f"{BATHING_CUBE_BASE}/1"
    best_version = 0
    for binding in bindings:
        iri = binding["cube"]["value"].rstrip("/")
        tail = iri.rsplit("/", 1)[-1]
        if tail.isdigit() and int(tail) > best_version:
            best_version = int(tail)
            best_iri = iri
    return best_iri


async def async_fetch_sites(hass: HomeAssistant) -> dict[str, dict]:
    """All official bathing sites with their coordinates."""
    sites: dict[str, dict] = {}
    for binding in await _sparql(hass, _SITES_SPARQL):
        try:
            site_id = binding["id"]["value"]
            sites[site_id] = {
                "site_id": site_id,
                "name": binding["name"]["value"],
                "latitude": float(binding["lat"]["value"]),
                "longitude": float(binding["lon"]["value"]),
                "canton": (binding.get("canton", {}).get("value") or "").rsplit("/", 1)[-1],
            }
        except (KeyError, ValueError):
            continue
    return sites


async def async_fetch_quality(hass: HomeAssistant, cube: str) -> dict[str, dict]:
    """Classification per bathing site from the assessment period.

    The directive classifies a site from the samples of the last four bathing
    seasons, which is what the cantons and the FOEN report. The published data
    lags the running season, so the newest sample date is exposed as an
    attribute to make the age of the assessment visible.
    """
    since = f"{date.today().year - 4}-01-01"
    bindings = await _sparql(
        hass,
        _MEASUREMENTS_SPARQL.format(
            dimensions=BATHING_CUBE_BASE, cube=cube, since=since
        ),
    )

    by_site: dict[str, dict] = {}
    for binding in bindings:
        try:
            site_id = binding["id"]["value"]
            probing = binding["date"]["value"]
            parameter = binding["param"]["value"]
            value = float(binding["value"]["value"])
        except (KeyError, ValueError):
            continue
        site = by_site.setdefault(
            site_id, {"samples": {}, "last_date": "", "last_values": {}}
        )
        site["samples"].setdefault(parameter, []).append(value)
        if probing > site["last_date"]:
            site["last_date"] = probing
            site["last_values"] = {}
        if probing == site["last_date"]:
            site["last_values"][parameter] = value

    result: dict[str, dict] = {}
    for site_id, site in by_site.items():
        result[site_id] = {
            "quality": classify(site["samples"]),
            "season": int(site["last_date"][:4]) if site["last_date"] else None,
            "last_sample_date": site["last_date"],
            "last_values": site["last_values"],
            "sample_count": sum(len(v) for v in site["samples"].values()),
        }
    return result


async def async_fetch_temperatures(hass: HomeAssistant) -> dict[str, dict]:
    """Current bathing water temperature of the Zurich lake stations."""
    session = async_get_clientsession(hass)
    result: dict[str, dict] = {}
    for code, station in BATHING_TEMP_STATIONS.items():
        try:
            async with session.get(
                BATHING_TEMP_URL.format(station=code),
                params={"limit": 1, "sort": "timestamp_cet desc"},
                timeout=30,
            ) as resp:
                resp.raise_for_status()
                payload = await resp.json(content_type=None)
        except Exception:  # noqa: BLE001 - a station outage must not fail the update
            continue
        records = payload.get("result") or []
        if not records:
            continue
        values = records[0].get("values") or {}

        def _val(key: str) -> float | None:
            entry = values.get(key) or {}
            value = entry.get("value")
            return float(value) if isinstance(value, (int, float)) else None

        water = _val("water_temperature")
        if water is None:
            continue
        result[code] = {
            **station,
            "site_id": f"wapo_{code}",
            "water_temperature": water,
            "air_temperature": _val("air_temperature"),
            "measurement_time": (values.get("timestamp_cet") or {}).get("value"),
        }
    return result
