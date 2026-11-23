"""Shared pieces of the Swiss Waters tests: station and bathing data shaped
like the real answers, and entries set up on faked sources."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swiss_waters.const import (
    CONF_BATHING_SITES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_RADIUS_KM,
    CONF_STATIONS,
    DOMAIN,
    MODE_BATHING_FAVORITE,
    MODE_BATHING_RADIUS,
)

HOME = (46.948, 7.447)  # Bern


def stamp(minutes_ago: float = 10, now: datetime | None = None) -> str:
    return ((now or dt_util.utcnow()) - timedelta(minutes=minutes_ago)).isoformat()


def station(station_id: str = "2135", **changes) -> dict:
    """A station record as the coordinator's fetch returns it."""
    base = {
        "station_id": station_id,
        "name": "Bern, Schönau",
        "water_body": "Aare",
        "latitude": 46.933,
        "longitude": 7.448,
        "distance_km": 1.7,
        "measurement_time": stamp(),
        "temperature": 10.1,
        "water_level": 502.40,
        "discharge": 126.4,
        "danger_level": 1,
        "fresh": True,
    }
    base.update(changes)
    return base


LAKE = dict(name="Murten", water_body="Murtensee", latitude=46.93, longitude=7.12, distance_km=25.0,
            temperature=None, discharge=None, water_level=429.3)


class Source:
    """The faked FOEN station feed: set `stations` (a dict by id) or `error`."""

    def __init__(self) -> None:
        self.stations: dict[str, dict] = {"2135": station()}
        self.error: Exception | None = None
        self.calls: list[tuple] = []

    async def fetch(self, hass, lat, lon, radius_km, favorite_ids=None):
        self.calls.append((lat, lon, radius_km, favorite_ids))
        if self.error:
            raise self.error
        return {k: dict(v) for k, v in self.stations.items()}

    def patch(self):
        return patch("custom_components.swiss_waters.coordinator.async_fetch_stations", side_effect=self.fetch)


SITES = {
    "CH1": {"site_id": "CH1", "name": "Marzili", "latitude": 46.943, "longitude": 7.443, "canton": "BE"},
    "CH2": {"site_id": "CH2", "name": "Lorraine", "latitude": 46.955, "longitude": 7.445, "canton": "BE"},
    "CH9": {"site_id": "CH9", "name": "Lido Locarno", "latitude": 46.16, "longitude": 8.80, "canton": "TI"},
}
QUALITY = {
    "CH1": {"quality": "excellent", "season": 2025, "last_sample_date": "2025-09-02",
            "last_values": {"E.coli": 20.0, "Enterokokken": 5.0}, "sample_count": 24},
}


def lake_station(code: str = "tiefenbrunnen", minutes_ago: float = 20, **changes) -> dict:
    base = {
        "name": "Zürichsee Tiefenbrunnen", "latitude": 47.3479, "longitude": 8.5610,
        "site_id": f"wapo_{code}", "water_temperature": 10.4, "air_temperature": 6.2,
        "measurement_time": stamp(minutes_ago),
    }
    base.update(changes)
    return base


class Bathing:
    """The faked bathing sources."""

    def __init__(self) -> None:
        self.sites = dict(SITES)
        self.quality = dict(QUALITY)
        self.temperatures: dict[str, dict] = {}
        self.cube = "https://environment.ld.admin.ch/foen/ubd01041prod/13"
        self.error: Exception | None = None
        self.cube_calls = 0
        self.quality_calls: list[str] = []

    async def _sites(self, hass):
        if self.error:
            raise self.error
        return {k: dict(v) for k, v in self.sites.items()}

    async def _cube(self, hass):
        self.cube_calls += 1
        return self.cube

    async def _quality(self, hass, cube):
        self.quality_calls.append(cube)
        return {k: dict(v) for k, v in self.quality.items()}

    async def _temperatures(self, hass):
        return {k: dict(v) for k, v in self.temperatures.items()}

    def patches(self):
        base = "custom_components.swiss_waters.bathing."
        return (
            patch(base + "async_fetch_sites", side_effect=self._sites),
            patch(base + "async_latest_cube", side_effect=self._cube),
            patch(base + "async_fetch_quality", side_effect=self._quality),
            patch(base + "async_fetch_temperatures", side_effect=self._temperatures),
        )


async def setup_stations(hass: HomeAssistant, radius: float = 30, favorites: list[str] | None = None, unique_id: str = "radius") -> MockConfigEntry:
    hass.config.latitude, hass.config.longitude = HOME
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=unique_id, title="Waters",
        data={CONF_LATITUDE: HOME[0], CONF_LONGITUDE: HOME[1], CONF_RADIUS_KM: radius, CONF_STATIONS: favorites or []},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def setup_bathing(hass: HomeAssistant, radius: float = 10, favorites: list[str] | None = None) -> MockConfigEntry:
    hass.config.latitude, hass.config.longitude = HOME
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="bathing", title="Bathing",
        data={CONF_MODE: MODE_BATHING_FAVORITE if favorites else MODE_BATHING_RADIUS, CONF_LATITUDE: HOME[0],
              CONF_LONGITUDE: HOME[1], CONF_RADIUS_KM: radius, CONF_BATHING_SITES: favorites or []},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def sensor_id(hass: HomeAssistant, entry: MockConfigEntry, item: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{item}_{key}")


def marker_id(hass: HomeAssistant, entry: MockConfigEntry, station_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id("geo_location", DOMAIN, f"{DOMAIN}_{entry.entry_id}_{station_id}")
