"""The station entities of an entry on a faked feed: sensors, the trend, the
map markers, stale and missing stations, an unreachable service."""
from __future__ import annotations

from datetime import timedelta

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from custom_components.swiss_waters.const import DOMAIN

from .common import LAKE, Source, marker_id, refresh, sensor_id, setup_stations, stamp, station


async def test_sensors_of_a_river_station(hass: HomeAssistant, source: Source) -> None:
    hass.config.language = "de"
    entry = await setup_stations(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert source.calls[0][2] == 30 and source.calls[0][3] == set()

    temperature = hass.states.get(sensor_id(hass, entry, "2135", "temperature"))
    assert temperature.state == "10.1" and temperature.attributes["unit_of_measurement"] == "°C"
    assert temperature.name == "Aare – Bern, Schönau Wassertemperatur"
    assert temperature.attributes["station_id"] == "2135" and temperature.attributes["water_body"] == "Aare"
    assert temperature.attributes["distance_km"] == 1.7
    assert temperature.attributes["trend"] is None  # no history yet
    assert hass.states.get(sensor_id(hass, entry, "2135", "water_level")).state == "502.4"
    assert hass.states.get(sensor_id(hass, entry, "2135", "discharge")).attributes["unit_of_measurement"] == "m³/s"
    danger = hass.states.get(sensor_id(hass, entry, "2135", "danger_level"))
    assert danger.state == "1" and danger.attributes["danger_scale"]["3"] == "Erhebliche Gefahr"
    assert "trend" not in danger.attributes
    assert sensor_id(hass, entry, "2135", "temperature").endswith(entry.entry_id[-4:].lower())

    marker = hass.states.get(marker_id(hass, entry, "2135"))
    assert marker.attributes["temperature"] == 10.1 and marker.attributes["danger_level"] == 1
    assert marker.attributes["latitude"] == 46.933 and marker.attributes["source"] == "swiss_waters"
    assert float(marker.state) == 1.7


async def test_a_lake_station_has_no_temperature_or_discharge_sensor(hass: HomeAssistant, source: Source) -> None:
    source.stations = {"2004": station("2004", **LAKE)}
    entry = await setup_stations(hass)
    assert sensor_id(hass, entry, "2004", "water_level")
    assert sensor_id(hass, entry, "2004", "danger_level")
    assert sensor_id(hass, entry, "2004", "trend")
    assert sensor_id(hass, entry, "2004", "temperature") is None
    assert sensor_id(hass, entry, "2004", "discharge") is None

    # a probe that starts reporting later gets its sensor without a reload
    source.stations = {"2004": station("2004", **{**LAKE, "temperature": 8.4})}
    await refresh(hass, entry)
    assert hass.states.get(sensor_id(hass, entry, "2004", "temperature")).state == "8.4"


async def test_a_station_without_level_and_discharge_has_no_trend_sensor(hass: HomeAssistant, source: Source) -> None:
    source.stations = {"2500": station("2500", water_level=None, discharge=None, water_body=None, name=None)}
    entry = await setup_stations(hass)
    assert sensor_id(hass, entry, "2500", "trend") is None
    assert hass.states.get(sensor_id(hass, entry, "2500", "temperature")).name == "2500 Water temperature"  # no names: the id


async def test_trend_sensor_follows_the_readings(hass: HomeAssistant, source: Source) -> None:
    hass.config.language = "de"
    now = dt_util.utcnow()
    source.stations = {"2135": station(measurement_time=stamp(70, now), water_level=502.00, discharge=100.0, temperature=10.0)}
    entry = await setup_stations(hass)
    trend_id = sensor_id(hass, entry, "2135", "trend")
    trend = hass.states.get(trend_id)
    assert trend.state == "unknown" and trend.attributes["trend_text"] is None
    assert trend.attributes["icon"] == "mdi:trending-neutral" and trend.attributes["options"] == ["rising", "steady", "falling"]

    source.stations = {"2135": station(measurement_time=stamp(10, now), water_level=502.30, discharge=101.0, temperature=10.0)}
    await refresh(hass, entry)
    trend = hass.states.get(trend_id)
    assert trend.state == "rising" and trend.attributes["trend_text"] == "Steigend"
    assert trend.attributes["based_on"] == "water_level" and trend.attributes["change_per_hour"] == 0.3
    assert trend.attributes["discharge"] == "steady" and trend.attributes["temperature"] == "steady"
    assert trend.attributes["icon"] == "mdi:trending-up"
    level = hass.states.get(sensor_id(hass, entry, "2135", "water_level"))
    assert level.attributes["trend"] == "rising" and level.attributes["change_per_hour"] == 0.3

    source.stations = {"2135": station(measurement_time=stamp(0, now + timedelta(minutes=50)), water_level=501.90, discharge=101.0, temperature=10.0)}
    await refresh(hass, entry)
    assert hass.states.get(trend_id).attributes["icon"] == "mdi:trending-down"
    assert hass.states.get(trend_id).state == "falling"


async def test_a_stale_station_is_unavailable_but_stays_on_the_map(hass: HomeAssistant, source: Source) -> None:
    entry = await setup_stations(hass)
    source.stations = {"2135": station(measurement_time=stamp(60 * 24), fresh=False)}
    await refresh(hass, entry)
    for key in ("temperature", "water_level", "discharge", "danger_level", "trend"):
        assert hass.states.get(sensor_id(hass, entry, "2135", key)).state == "unavailable"
    marker = hass.states.get(marker_id(hass, entry, "2135"))
    assert marker.state != "unavailable"
    assert marker.attributes["temperature"] is None and marker.attributes["water_level"] is None
    assert marker.attributes["measurement_time"] is not None


async def test_a_station_that_leaves_the_feed_and_comes_back(hass: HomeAssistant, source: Source) -> None:
    source.stations = {"2135": station(), "2004": station("2004", **LAKE)}
    entry = await setup_stations(hass)
    source.stations = {"2135": station()}
    await refresh(hass, entry)
    assert hass.states.get(sensor_id(hass, entry, "2004", "water_level")).state == "unavailable"
    assert hass.states.get(marker_id(hass, entry, "2004")).state == "unavailable"
    assert hass.states.get(sensor_id(hass, entry, "2135", "water_level")).state == "502.4"
    source.stations = {"2135": station(), "2004": station("2004", **LAKE)}
    await refresh(hass, entry)
    assert hass.states.get(sensor_id(hass, entry, "2004", "water_level")).state == "429.3"


@pytest.mark.parametrize("error", [aiohttp.ClientError("down"), TimeoutError(), KeyError("results"), ValueError("html")])
async def test_an_unreachable_or_unreadable_service(hass: HomeAssistant, source: Source, error) -> None:
    entry = await setup_stations(hass)
    issue_id = f"unreachable_{entry.entry_id}"
    source.error = error
    await refresh(hass, entry)
    assert hass.states.get(sensor_id(hass, entry, "2135", "temperature")).state == "unavailable"
    assert hass.states.get(marker_id(hass, entry, "2135")).state == "unavailable"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    await refresh(hass, entry)
    await refresh(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id).translation_placeholders == {"host": "lindas.admin.ch"}
    source.error = None
    await refresh(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert hass.states.get(sensor_id(hass, entry, "2135", "temperature")).state == "10.1"


async def test_a_favorite_the_foen_no_longer_lists_raises_a_repair(hass: HomeAssistant, source: Source) -> None:
    entry = await setup_stations(hass, radius=0, favorites=["2135", "9999"], unique_id="station_2135")
    assert source.calls[0][3] == {"2135", "9999"}
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"station_missing_{entry.entry_id}")
    assert issue.translation_placeholders == {"station": "9999"}
    source.stations = {"2135": station(), "9999": station("9999", name="Neu")}
    await refresh(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"station_missing_{entry.entry_id}") is None


async def test_unload_withdraws_repairs_and_a_failed_first_refresh_retries(hass: HomeAssistant, source: Source) -> None:
    entry = await setup_stations(hass, radius=0, favorites=["9999"], unique_id="station_9999")
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"station_missing_{entry.entry_id}")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"station_missing_{entry.entry_id}") is None

    source.error = aiohttp.ClientError("down")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
