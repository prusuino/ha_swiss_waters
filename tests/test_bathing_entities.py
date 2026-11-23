"""Bathing sites of an entry on faked sources: the quality class, the last
sample, the lake temperature, the cube version and the failures."""
from __future__ import annotations

from datetime import timedelta

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from custom_components.swiss_waters.const import DOMAIN

from .common import Bathing, lake_station, marker_id, refresh, sensor_id, setup_bathing


async def test_quality_and_last_sample_of_the_sites_in_the_radius(hass: HomeAssistant, bathing: Bathing) -> None:
    hass.config.language = "de"
    entry = await setup_bathing(hass, radius=10)
    quality = hass.states.get(sensor_id(hass, entry, "CH1", "quality"))
    assert quality.state == "excellent"
    assert quality.attributes["quality_text"] == "Ausgezeichnet" and quality.attributes["live"] is False
    assert "2025-09-02" in quality.attributes["note"]
    assert quality.attributes["e_coli"] == 20.0 and quality.attributes["enterococci"] == 5.0
    assert quality.attributes["season"] == 2025 and quality.attributes["sample_count"] == 24
    assert quality.attributes["canton"] == "BE" and quality.attributes["distance_km"] < 1
    assert quality.name == "Marzili Wasserqualität (Saisonbeurteilung)" or "Marzili" in quality.name
    sample = hass.states.get(sensor_id(hass, entry, "CH1", "last_sample"))
    assert sample.state == "2025-09-02" and sample.attributes["live"] is False

    # a site in the radius without a sample in the assessment period: no assessment
    assert hass.states.get(sensor_id(hass, entry, "CH2", "quality")).state == "unavailable"
    assert hass.states.get(sensor_id(hass, entry, "CH2", "last_sample")).state == "unavailable"
    assert sensor_id(hass, entry, "CH9", "quality") is None  # Locarno is far away
    assert marker_id(hass, entry, "CH1") is None  # bathing sites have no map markers


async def test_lake_temperature_as_a_favourite(hass: HomeAssistant, bathing: Bathing) -> None:
    bathing.temperatures = {"tiefenbrunnen": lake_station(), "mythenquai": lake_station("mythenquai", name="Zürichsee Mythenquai")}
    entry = await setup_bathing(hass, radius=0, favorites=["wapo_tiefenbrunnen"])
    lake = hass.states.get(sensor_id(hass, entry, "wapo_tiefenbrunnen", "water_temperature"))
    assert lake.state == "10.4" and lake.attributes["air_temperature"] == 6.2
    assert lake.attributes["site_id"] == "wapo_tiefenbrunnen" and lake.attributes["measurement_time"]
    assert sensor_id(hass, entry, "wapo_mythenquai", "water_temperature") is None  # not picked
    assert sensor_id(hass, entry, "wapo_tiefenbrunnen", "quality") is None

    # the community API lags beyond the limit: unavailable rather than an old value as live
    bathing.temperatures = {"tiefenbrunnen": lake_station(minutes_ago=60 * 7)}
    await refresh(hass, entry)
    assert hass.states.get(sensor_id(hass, entry, "wapo_tiefenbrunnen", "water_temperature")).state == "unavailable"
    bathing.temperatures = {}
    await refresh(hass, entry)
    assert hass.states.get(sensor_id(hass, entry, "wapo_tiefenbrunnen", "water_temperature")).state == "unavailable"


async def test_lake_station_inside_a_radius(hass: HomeAssistant, bathing: Bathing) -> None:
    bathing.temperatures = {"tiefenbrunnen": lake_station()}
    entry = await setup_bathing(hass, radius=150)
    assert hass.states.get(sensor_id(hass, entry, "wapo_tiefenbrunnen", "water_temperature")).state == "10.4"
    assert sensor_id(hass, entry, "CH9", "quality")  # Locarno is inside 150 km


async def test_a_broken_sample_date_reads_unknown(hass: HomeAssistant, bathing: Bathing) -> None:
    bathing.quality = {"CH1": {"quality": None, "season": None, "last_sample_date": "soon", "last_values": {}, "sample_count": 1}}
    entry = await setup_bathing(hass)
    assert hass.states.get(sensor_id(hass, entry, "CH1", "last_sample")).state == "unknown"
    quality = hass.states.get(sensor_id(hass, entry, "CH1", "quality"))
    assert quality.state == "unknown" and quality.attributes["quality_text"] is None


async def test_the_cube_version_is_resolved_again_when_it_returns_nothing_or_gets_old(hass: HomeAssistant, bathing: Bathing, caplog) -> None:
    entry = await setup_bathing(hass)
    assert bathing.cube_calls == 1
    await refresh(hass, entry)
    assert bathing.cube_calls == 1  # cached

    # the cached version stopped returning rows: resolve again, once, and say so once
    bathing.quality = {}
    bathing.cube = "https://environment.ld.admin.ch/foen/ubd01041prod/14"
    await refresh(hass, entry)
    assert bathing.cube_calls == 2 and bathing.quality_calls[-1].endswith("/14")
    assert caplog.text.count("returned no samples") == 1
    await refresh(hass, entry)
    assert caplog.text.count("returned no samples") == 1
    assert hass.states.get(sensor_id(hass, entry, "CH1", "quality")).state == "unavailable"

    # after a day the version is looked up again
    entry.runtime_data._cube_resolved = dt_util.utcnow() - timedelta(hours=25)
    before = bathing.cube_calls
    await refresh(hass, entry)
    assert bathing.cube_calls == before + 1


@pytest.mark.parametrize("error", [aiohttp.ClientError("down"), KeyError("results")])
async def test_bathing_source_failures(hass: HomeAssistant, bathing: Bathing, error) -> None:
    entry = await setup_bathing(hass)
    bathing.error = error
    for _ in range(3):
        await refresh(hass, entry)
    assert hass.states.get(sensor_id(hass, entry, "CH1", "quality")).state == "unavailable"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"unreachable_{entry.entry_id}")
    assert issue.translation_placeholders == {"host": "environment.ld.admin.ch"}
    bathing.error = None
    await refresh(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"unreachable_{entry.entry_id}") is None


async def test_a_favourite_site_that_is_gone_raises_a_repair(hass: HomeAssistant, bathing: Bathing) -> None:
    entry = await setup_bathing(hass, radius=0, favorites=["CH1", "CH404", "wapo_tiefenbrunnen"])
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"site_missing_{entry.entry_id}")
    assert issue.translation_placeholders == {"site": "CH404"}  # the lake stations are never "missing"
    bathing.sites["CH404"] = {"site_id": "CH404", "name": "Neu", "latitude": 46.9, "longitude": 7.4, "canton": "BE"}
    await refresh(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"site_missing_{entry.entry_id}") is None
