"""The queries against a faked web session: the station feed, the bathing
sites, the cube version, the samples and the Zurich lake stations."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant

from custom_components.swiss_waters import bathing, coordinator
from custom_components.swiss_waters.const import ENVIRONMENT_QUERY_URL, LINDAS_QUERY_URL

from .common import stamp


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        if isinstance(self._payload, Exception):
            raise self._payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple] = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.answers.pop(0))

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.answers.pop(0))


def _bindings(*rows):
    return {"results": {"bindings": [{k: {"value": str(v)} for k, v in row.items()} for row in rows]}}


async def test_station_query(hass: HomeAssistant) -> None:
    session = _Session(_bindings(
        {"id": "2135", "name": "Bern, Schönau", "wkt": "POINT(7.448 46.933)", "water": "https://ld.admin.ch/water/Aare",
         "time": stamp(), "temperature": 10.07, "level": 502.39, "discharge": 126.3, "danger": 1},
        {"id": "2289", "name": "Basel, Rheinhalle", "wkt": "POINT(7.617 47.559)", "water": "https://ld.admin.ch/water/Rhein",
         "time": stamp(), "discharge": 1400.1, "danger": "https://cube.link/Undefined"},
    ))
    with patch.object(coordinator, "async_get_clientsession", return_value=session):
        stations = await coordinator.async_fetch_stations(hass, 46.948, 7.447, 30, {"2289"})
    url, kwargs = session.calls[0]
    assert url == LINDAS_QUERY_URL and "dim:dangerLevel" in kwargs["data"]["query"]
    assert kwargs["headers"]["Accept"] == "application/sparql-results+json"
    assert stations["2135"]["temperature"] == 10.07 and stations["2135"]["danger_level"] == 1
    assert stations["2289"]["danger_level"] is None  # "Undefined" is no level
    assert stations["2289"]["discharge"] == 1400.1 and stations["2289"]["fresh"] is True

    with patch.object(coordinator, "async_get_clientsession", return_value=_Session({})):
        assert await coordinator.async_fetch_stations(hass, 46.948, 7.447, 30) == {}
    with patch.object(coordinator, "async_get_clientsession", return_value=_Session(aiohttp.ClientError("503"))), pytest.raises(aiohttp.ClientError):
        await coordinator.async_fetch_stations(hass, 46.948, 7.447, 30)


def test_unreadable_numbers_are_no_value():
    binding = {"temperature": {"value": "n/a"}, "level": {"value": "1.5"}}
    assert coordinator._float(binding, "temperature") is None
    assert coordinator._float(binding, "level") == 1.5
    assert coordinator._float(binding, "discharge") is None


async def test_bathing_sites_query(hass: HomeAssistant) -> None:
    session = _Session(_bindings(
        {"id": "CH1", "name": "Marzili", "lat": 46.943, "lon": 7.443, "canton": "https://ld.admin.ch/canton/BE"},
        {"id": "CH2", "name": "Lorraine", "lat": 46.955, "lon": 7.445},
        {"id": "CH3", "name": "Ohne Ort", "lat": "x", "lon": 7.4},
        {"name": "ohne Kennung"},
    ))
    with patch.object(bathing, "async_get_clientsession", return_value=session):
        sites = await bathing.async_fetch_sites(hass)
    assert session.calls[0][0] == ENVIRONMENT_QUERY_URL
    assert set(sites) == {"CH1", "CH2"}
    assert sites["CH1"]["canton"] == "BE" and sites["CH2"]["canton"] == ""
    assert sites["CH1"]["latitude"] == 46.943


async def test_latest_cube_version(hass: HomeAssistant) -> None:
    base = "https://environment.ld.admin.ch/foen/ubd01041prod"
    session = _Session(_bindings({"cube": f"{base}/9"}, {"cube": f"{base}/13/"}, {"cube": f"{base}/2"}, {"cube": f"{base}/draft"}), {})
    with patch.object(bathing, "async_get_clientsession", return_value=session):
        assert await bathing.async_latest_cube(hass) == f"{base}/13"
        assert await bathing.async_latest_cube(hass) == f"{base}/1"  # nothing published: the first version


async def test_quality_from_the_samples_of_the_assessment_period(hass: HomeAssistant) -> None:
    rows = [{"id": "CH1", "date": f"2025-0{month}-02", "param": param, "value": value}
            for month in (6, 7, 8) for param, value in (("E.coli", 20), ("Enterokokken", 5))]
    rows += [
        {"id": "CH1", "date": "2025-09-02", "param": "E.coli", "value": 30},
        {"id": "CH2", "date": "2025-08-01", "param": "E.coli", "value": 5000},
        {"id": "CH2", "date": "2025-08-08", "param": "E.coli", "value": 4000},
        {"id": "CH2", "date": "2025-08-15", "param": "E.coli", "value": "viele"},
        {"id": "CH3", "param": "E.coli", "value": 1},
    ]
    session = _Session(_bindings(*rows))
    with patch.object(bathing, "async_get_clientsession", return_value=session):
        quality = await bathing.async_fetch_quality(hass, "https://environment.ld.admin.ch/foen/ubd01041prod/13")
    query = session.calls[0][1]["data"]["query"]
    assert f'"{date.today().year - 4}-01-01"' in query and "/ubd01041prod/13>" in query
    assert "<https://environment.ld.admin.ch/foen/ubd01041prod/>" in query  # dimensions without the version
    ch1 = quality["CH1"]
    assert ch1["quality"] == "excellent" and ch1["season"] == 2025 and ch1["sample_count"] == 7
    assert ch1["last_sample_date"] == "2025-09-02" and ch1["last_values"] == {"E.coli": 30.0}
    assert quality["CH2"]["quality"] == "poor" and quality["CH2"]["sample_count"] == 2
    assert "CH3" not in quality


async def test_lake_temperatures(hass: HomeAssistant) -> None:
    ok = {"result": [{"values": {"water_temperature": {"value": 10.4}, "air_temperature": {"value": "kalt"}, "timestamp_cet": {"value": "2026-11-23T18:10:00+01:00"}}}]}
    with patch.object(bathing, "async_get_clientsession", return_value=_Session(ok, aiohttp.ClientError("down"))):
        result = await bathing.async_fetch_temperatures(hass)
    assert set(result) == {"tiefenbrunnen"}  # the other station's outage does not fail the read
    lake = result["tiefenbrunnen"]
    assert lake["site_id"] == "wapo_tiefenbrunnen" and lake["water_temperature"] == 10.4
    assert lake["air_temperature"] is None and lake["measurement_time"] == "2026-11-23T18:10:00+01:00"
    assert lake["latitude"] == 47.3479

    empty = _Session({"result": []}, {"result": [{"values": {"air_temperature": {"value": 5}}}]})
    with patch.object(bathing, "async_get_clientsession", return_value=empty):
        assert await bathing.async_fetch_temperatures(hass) == {}
    assert empty.calls[0][1]["params"] == {"limit": 1, "sort": "timestamp_cet desc"}
