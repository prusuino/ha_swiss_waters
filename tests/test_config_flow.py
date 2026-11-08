"""Config flow tests: radius overview, favorite station, duplicate detection,
an unreachable data service and the reconfigure flow. The LINDAS queries
are faked."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swiss_waters.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_RADIUS_KM,
    CONF_STATION,
    CONF_STATIONS,
    DOMAIN,
    MODE_FAVORITE,
    MODE_RADIUS,
)

STATIONS = {
    "2135": {"station_id": "2135", "name": "Bern, Schönau", "water_body": "Aare", "latitude": 46.93, "longitude": 7.45, "distance_km": 1.2},
    "2029": {"station_id": "2029", "name": "Basel", "water_body": "Rhein", "latitude": 47.56, "longitude": 7.59, "distance_km": 70.0},
}


async def _fetch(hass, lat, lon, radius_km, favorite_ids=None):
    if radius_km >= 1000:  # the picker list
        return STATIONS
    if radius_km < 10:
        return {}
    return {"2135": STATIONS["2135"]}


@pytest.fixture
def fake_lindas():
    with patch("custom_components.swiss_waters.config_flow.async_fetch_stations", side_effect=_fetch):
        yield


async def _start(hass, mode):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_MODE: mode})


async def test_radius_overview_setup(hass: HomeAssistant, enable_custom_integrations, fake_lindas) -> None:
    result = await _start(hass, MODE_RADIUS)
    assert result["step_id"] == "radius"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LATITUDE: 46.948, CONF_LONGITUDE: 7.447, CONF_RADIUS_KM: 25}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_LATITUDE: 46.948, CONF_LONGITUDE: 7.447, CONF_RADIUS_KM: 25.0, CONF_STATIONS: []}
    assert result["result"].unique_id == "radius_46.95_7.45_25.0"  # the number selector delivers a float


async def test_empty_radius_is_a_form_error(hass: HomeAssistant, enable_custom_integrations, fake_lindas) -> None:
    result = await _start(hass, MODE_RADIUS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LATITUDE: 46.948, CONF_LONGITUDE: 7.447, CONF_RADIUS_KM: 5}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_stations"}


async def test_unreachable_service_is_a_form_error(hass: HomeAssistant, enable_custom_integrations) -> None:
    with patch("custom_components.swiss_waters.config_flow.async_fetch_stations", side_effect=OSError("down")):
        result = await _start(hass, MODE_RADIUS)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_LATITUDE: 46.948, CONF_LONGITUDE: 7.447, CONF_RADIUS_KM: 25}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_favorite_station_setup(hass: HomeAssistant, enable_custom_integrations, fake_lindas) -> None:
    result = await _start(hass, MODE_FAVORITE)
    assert result["step_id"] == "favorite"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STATION: "2135"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Aare – Bern, Schönau"  # water body – station
    assert result["data"][CONF_STATIONS] == ["2135"]
    assert result["data"][CONF_RADIUS_KM] == 0
    assert result["result"].unique_id == "station_2135"


async def test_same_favorite_twice_is_refused(hass: HomeAssistant, enable_custom_integrations, fake_lindas) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="station_2135", title="Aare", data={CONF_STATIONS: ["2135"], CONF_RADIUS_KM: 0}).add_to_hass(hass)
    result = await _start(hass, MODE_FAVORITE)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STATION: "2135"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_favorite_to_another_station(hass: HomeAssistant, enable_custom_integrations, fake_lindas) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="station_2135", title="Aare – Bern, Schönau",
        data={CONF_LATITUDE: 46.9, CONF_LONGITUDE: 7.4, CONF_RADIUS_KM: 0, CONF_STATIONS: ["2135"]},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.swiss_waters.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        assert result["step_id"] == "reconfigure_favorite"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STATION: "2029"})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.unique_id == "station_2029"
    assert entry.data[CONF_STATIONS] == ["2029"]
    assert entry.title == "Rhein – Basel"
