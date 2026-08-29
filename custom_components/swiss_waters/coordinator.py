"""DataUpdateCoordinator for hydrological data from the Swiss Federal Office
for the Environment (FOEN/BAFU).

Uses the official LINDAS linked-data service (lindas.admin.ch) — the FOEN's
documented machine-readable channel for current hydrological raw data,
updated every 10 minutes. One SPARQL request fetches all stations together
with their latest observation (water temperature, water level, discharge,
flood danger level); the configured radius is then applied locally.

Every record carries a ``fresh`` flag: whether its latest reading lies within
the freshness limit of its source (const.py). The entities turn unavailable
when it is False, so a station that stopped transmitting is not shown with a
days-old value as if it were current.
"""
from __future__ import annotations

import logging
import math
import urllib.parse
from datetime import UTC, datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BATHING_CUBE_MAX_AGE,
    BATHING_TEMP_MAX_AGE,
    BATHING_UPDATE_INTERVAL_MINUTES,
    CONF_BATHING_SITES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_STATIONS,
    DOMAIN,
    HYDRO_DIMENSION,
    HYDRO_MAX_AGE,
    LINDAS_QUERY_URL,
    UPDATE_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

# Exceptions that mean "the service did not answer" — reported as unreachable.
# Anything else raised while reading the answer (an HTML error page, a
# missing key) is a parsing problem and is reported as such.
_TRANSPORT_ERRORS = (aiohttp.ClientError, TimeoutError)
_PARSE_ERRORS = (KeyError, TypeError, ValueError)

_SPARQL = f"""
PREFIX schema: <http://schema.org/>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX dim: <{HYDRO_DIMENSION}>
SELECT ?id ?name ?wkt ?water ?time ?temperature ?level ?discharge ?danger WHERE {{
  ?obs dim:station ?station .
  ?station schema:identifier ?id ; schema:name ?name .
  OPTIONAL {{ ?station geo:hasGeometry/geo:asWKT ?wkt }}
  OPTIONAL {{ ?station schema:containedInPlace ?water }}
  OPTIONAL {{ ?obs dim:measurementTime ?time }}
  OPTIONAL {{ ?obs dim:waterTemperature ?temperature }}
  OPTIONAL {{ ?obs dim:waterLevel ?level }}
  OPTIONAL {{ ?obs dim:discharge ?discharge }}
  OPTIONAL {{ ?obs dim:dangerLevel ?danger }}
}}
"""


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def is_fresh(timestamp: str | None, max_age: timedelta, now: datetime) -> bool:
    """Whether a source timestamp lies within ``max_age`` of ``now``.

    A missing or unparseable timestamp counts as stale: a reading whose age
    is unknown must not be presented as current. Timestamps without a time
    zone are read as UTC.
    """
    if not timestamp:
        return False
    measured = dt_util.parse_datetime(timestamp)
    if measured is None:
        return False
    if measured.tzinfo is None:
        measured = measured.replace(tzinfo=UTC)
    return now - measured <= max_age


def _parse_wkt_point(wkt: str) -> tuple[float, float] | None:
    """Parse 'POINT(lon lat)' → (lat, lon)."""
    try:
        inner = wkt[wkt.index("(") + 1 : wkt.index(")")]
        lon_s, lat_s = inner.split()
        return float(lat_s), float(lon_s)
    except (ValueError, IndexError):
        return None


def _value(binding: dict, key: str) -> str | None:
    return binding.get(key, {}).get("value")


def _float(binding: dict, key: str) -> float | None:
    raw = _value(binding, key)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_bindings(
    bindings: list[dict],
    lat: float,
    lon: float,
    radius_km: float,
    favorite_ids: set[str] | None = None,
    now: datetime | None = None,
) -> dict[str, dict]:
    """Merge SPARQL result rows into one record per station.

    A station is kept when it lies within the radius (radius 0 disables the
    radius search) OR when its ID is in the favorites set — the two selection
    modes combine. A station can appear in more than one row (e.g. separate
    river/lake observation graphs); rows are merged by taking the first
    non-null value per measure, preferring the row with the most recent
    measurement time. The merged record is then flagged ``fresh`` when that
    measurement time lies within HYDRO_MAX_AGE of ``now``.
    """
    favorites = favorite_ids or set()
    now = now or dt_util.utcnow()
    stations: dict[str, dict] = {}
    for b in bindings:
        station_id = _value(b, "id")
        if not station_id:
            continue

        coords = _parse_wkt_point(_value(b, "wkt") or "")
        if coords is None:
            continue
        s_lat, s_lon = coords
        distance = haversine_km(lat, lon, s_lat, s_lon)
        in_radius = radius_km > 0 and distance <= radius_km
        if not in_radius and station_id not in favorites:
            continue

        water_iri = _value(b, "water") or ""
        water = urllib.parse.unquote(water_iri.rsplit("/", 1)[-1]) if water_iri else None

        danger_raw = _value(b, "danger")
        row = {
            "station_id": station_id,
            "name": _value(b, "name"),
            "water_body": water,
            "latitude": s_lat,
            "longitude": s_lon,
            "distance_km": round(distance, 1),
            "measurement_time": _value(b, "time"),
            "temperature": _float(b, "temperature"),
            "water_level": _float(b, "level"),
            "discharge": _float(b, "discharge"),
            "danger_level": int(danger_raw) if danger_raw and danger_raw.isdigit() else None,
        }

        existing = stations.get(station_id)
        if existing is None:
            stations[station_id] = row
            continue
        newer = (row["measurement_time"] or "") > (existing["measurement_time"] or "")
        base, other = (row, existing) if newer else (existing, row)
        for key in ("temperature", "water_level", "discharge", "danger_level", "measurement_time"):
            if base[key] is None:
                base[key] = other[key]
        stations[station_id] = base

    for station in stations.values():
        station["fresh"] = is_fresh(station["measurement_time"], HYDRO_MAX_AGE, now)
    return stations


async def async_fetch_stations(
    hass: HomeAssistant,
    lat: float,
    lon: float,
    radius_km: float,
    favorite_ids: set[str] | None = None,
) -> dict[str, dict]:
    session = async_get_clientsession(hass)
    async with session.post(
        LINDAS_QUERY_URL,
        data={"query": _SPARQL},
        headers={"Accept": "application/sparql-results+json"},
        timeout=30,
    ) as resp:
        resp.raise_for_status()
        payload = await resp.json()
    bindings = payload.get("results", {}).get("bindings", [])
    return _parse_bindings(bindings, lat, lon, radius_km, favorite_ids)


class SwissWatersCoordinator(DataUpdateCoordinator[dict]):
    """Fetches current FOEN hydrological data for stations within the radius."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )

    async def _async_update_data(self) -> dict:
        data = self.config_entry.data
        try:
            stations = await async_fetch_stations(
                self.hass,
                data[CONF_LATITUDE],
                data[CONF_LONGITUDE],
                data[CONF_RADIUS_KM],
                set(data.get(CONF_STATIONS, [])),
            )
        except _TRANSPORT_ERRORS as err:
            raise UpdateFailed(f"FOEN hydrological data unreachable: {err}") from err
        except _PARSE_ERRORS as err:
            raise UpdateFailed(f"FOEN hydrological data unreadable: {err}") from err
        return {"stations": stations, "count": len(stations)}


class SwissBathingCoordinator(DataUpdateCoordinator[dict]):
    """Fetches bathing water quality and lake bathing temperatures.

    Data: {"sites": {site_id: {...}}, "count": n}. Quality is a seasonal
    assessment (see bathing.py); the Zurich lake temperatures are live. Each
    site record is flagged ``fresh``: a quality site when it has a sample
    within the assessment period, a lake station when its reading lies
    within BATHING_TEMP_MAX_AGE.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_bathing",
            update_interval=timedelta(minutes=BATHING_UPDATE_INTERVAL_MINUTES),
        )
        self._cube: str | None = None
        self._cube_resolved: datetime | None = None
        self._empty_quality_logged = False

    async def _async_cube(self, now: datetime, force: bool = False) -> tuple[str, bool]:
        """IRI of the published bathing cube and whether it was resolved just now.

        The version is cached for BATHING_CUBE_MAX_AGE so a newly published
        cube is picked up without a restart; ``force`` resolves it again
        regardless, used when the cached version stopped returning rows.
        """
        from .bathing import async_latest_cube

        expired = (
            self._cube_resolved is None or now - self._cube_resolved > BATHING_CUBE_MAX_AGE
        )
        if force or self._cube is None or expired:
            self._cube = await async_latest_cube(self.hass)
            self._cube_resolved = now
            return self._cube, True
        return self._cube, False

    async def _async_update_data(self) -> dict:
        from .bathing import (
            async_fetch_quality,
            async_fetch_sites,
            async_fetch_temperatures,
        )

        data = self.config_entry.data
        lat = data[CONF_LATITUDE]
        lon = data[CONF_LONGITUDE]
        radius = data.get(CONF_RADIUS_KM) or 0
        favorites = set(data.get(CONF_BATHING_SITES) or [])
        now = dt_util.utcnow()

        try:
            all_sites = await async_fetch_sites(self.hass)
            cube, resolved_now = await self._async_cube(now)
            quality = await async_fetch_quality(self.hass, cube)
            if not quality and not resolved_now:
                # A cached cube version that stopped returning rows was most
                # likely withdrawn in favour of a newer one: resolve again.
                cube, _ = await self._async_cube(now, force=True)
                quality = await async_fetch_quality(self.hass, cube)
            # Live lake temperatures are added when they fall inside the radius
            # or were picked as favourites.
            temperatures = await async_fetch_temperatures(self.hass)
        except _TRANSPORT_ERRORS as err:
            raise UpdateFailed(f"FOEN bathing water data unreachable: {err}") from err
        except _PARSE_ERRORS as err:
            raise UpdateFailed(f"FOEN bathing water data unreadable: {err}") from err

        if not quality:
            if not self._empty_quality_logged:
                _LOGGER.warning(
                    "The bathing water cube %s returned no samples; the quality "
                    "entities stay unavailable until the FOEN publishes data",
                    cube,
                )
                self._empty_quality_logged = True
        else:
            self._empty_quality_logged = False

        # Records without usable coordinates never get here: async_fetch_sites
        # drops them while parsing, and the temperature stations carry fixed
        # coordinates from const.py.
        sites: dict[str, dict] = {}
        for site_id, site in all_sites.items():
            distance = haversine_km(lat, lon, site["latitude"], site["longitude"])
            in_radius = radius > 0 and distance <= radius
            if not in_radius and site_id not in favorites:
                continue
            assessment = quality.get(site_id) or {}
            sites[site_id] = {
                **site,
                **assessment,
                "distance_km": round(distance, 1),
                # No sample within the assessment period means no assessment.
                "fresh": bool(assessment.get("last_sample_date")),
            }

        for station in temperatures.values():
            site_id = station["site_id"]
            distance = haversine_km(lat, lon, station["latitude"], station["longitude"])
            in_radius = radius > 0 and distance <= radius
            if not in_radius and site_id not in favorites:
                continue
            sites[site_id] = {
                **station,
                "distance_km": round(distance, 1),
                "fresh": is_fresh(station.get("measurement_time"), BATHING_TEMP_MAX_AGE, now),
            }

        return {"sites": sites, "count": len(sites)}
