"""DataUpdateCoordinator for hydrological data from the Swiss Federal Office
for the Environment (FOEN/BAFU).

Uses the official LINDAS linked-data service (lindas.admin.ch) — the FOEN's
documented machine-readable channel for current hydrological raw data,
updated every 10 minutes. One SPARQL request fetches all stations together
with their latest observation (water temperature, water level, discharge,
flood danger level); the configured radius is then applied locally.
"""
from __future__ import annotations

import logging
import math
import urllib.parse
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BATHING_UPDATE_INTERVAL_MINUTES,
    CONF_BATHING_SITES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_STATIONS,
    DOMAIN,
    HYDRO_DIMENSION,
    LINDAS_QUERY_URL,
    UPDATE_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

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


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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
) -> dict[str, dict]:
    """Merge SPARQL result rows into one record per station.

    A station is kept when it lies within the radius (radius 0 disables the
    radius search) OR when its ID is in the favorites set — the two selection
    modes combine. A station can appear in more than one row (e.g. separate
    river/lake observation graphs); rows are merged by taking the first
    non-null value per measure, preferring the row with the most recent
    measurement time.
    """
    favorites = favorite_ids or set()
    stations: dict[str, dict] = {}
    for b in bindings:
        station_id = _value(b, "id")
        if not station_id:
            continue

        coords = _parse_wkt_point(_value(b, "wkt") or "")
        if coords is None:
            continue
        s_lat, s_lon = coords
        distance = _haversine_km(lat, lon, s_lat, s_lon)
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
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._entry = entry

    async def _async_update_data(self) -> dict:
        data = self._entry.data
        try:
            stations = await async_fetch_stations(
                self.hass,
                data[CONF_LATITUDE],
                data[CONF_LONGITUDE],
                data[CONF_RADIUS_KM],
                set(data.get(CONF_STATIONS, [])),
            )
        except Exception as err:
            raise UpdateFailed(f"FOEN hydrological data unreachable: {err}") from err
        return {"stations": stations, "count": len(stations)}


class SwissBathingCoordinator(DataUpdateCoordinator[dict]):
    """Fetches bathing water quality and lake bathing temperatures.

    Data: {"sites": {site_id: {...}}, "count": n}. Quality is a seasonal
    assessment (see bathing.py); the Zurich lake temperatures are live.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_bathing",
            update_interval=timedelta(minutes=BATHING_UPDATE_INTERVAL_MINUTES),
        )
        self._entry = entry
        self._cube: str | None = None

    async def _async_update_data(self) -> dict:
        from .bathing import (
            async_fetch_quality,
            async_fetch_sites,
            async_fetch_temperatures,
            async_latest_cube,
        )

        data = self._entry.data
        lat = data[CONF_LATITUDE]
        lon = data[CONF_LONGITUDE]
        radius = data.get(CONF_RADIUS_KM) or 0
        favorites = set(data.get(CONF_BATHING_SITES) or [])

        try:
            if self._cube is None:
                self._cube = await async_latest_cube(self.hass)
            all_sites = await async_fetch_sites(self.hass)
            quality = await async_fetch_quality(self.hass, self._cube)
        except Exception as err:
            raise UpdateFailed(f"FOEN bathing water data unreachable: {err}") from err

        sites: dict[str, dict] = {}
        for site_id, site in all_sites.items():
            distance = _haversine_km(lat, lon, site["latitude"], site["longitude"])
            in_radius = radius > 0 and distance <= radius
            if not in_radius and site_id not in favorites:
                continue
            sites[site_id] = {
                **site,
                **(quality.get(site_id) or {}),
                "distance_km": round(distance, 1),
            }

        # Live lake temperatures are added when they fall inside the radius or
        # were picked as favourites.
        temperatures = await async_fetch_temperatures(self.hass)
        for station in temperatures.values():
            site_id = station["site_id"]
            distance = _haversine_km(lat, lon, station["latitude"], station["longitude"])
            in_radius = radius > 0 and distance <= radius
            if not in_radius and site_id not in favorites:
                continue
            sites[site_id] = {**station, "distance_km": round(distance, 1)}

        return {"sites": sites, "count": len(sites)}
