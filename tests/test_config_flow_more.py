"""More of the config flow: the bathing modes, the pickers when the service
is down, and reconfiguring each kind of entry with its clean-up."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swiss_waters import async_setup_entry
from custom_components.swiss_waters.config_flow import entry_mode
from custom_components.swiss_waters.const import (
    CONF_BATHING_SITE,
    CONF_BATHING_SITES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_RADIUS_KM,
    CONF_STATION,
    CONF_STATIONS,
    DOMAIN,
    MODE_BATHING_FAVORITE,
    MODE_BATHING_RADIUS,
    MODE_FAVORITE,
    MODE_RADIUS,
)
from custom_components.swiss_waters.diagnostics import REDACTED, _compact
from custom_components.swiss_waters.localization import bathing_quality_text, t

from .common import LAKE, SITES, Bathing, Source, lake_station, marker_id, sensor_id, setup_bathing, setup_stations, station

FLOW = "custom_components.swiss_waters.config_flow."
BERN = {CONF_LATITUDE: 46.948, CONF_LONGITUDE: 7.447, CONF_RADIUS_KM: 10}


async def _sites(hass):
    return {k: dict(v) for k, v in SITES.items()}


async def _start(hass, mode):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    return await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_MODE: mode})


async def _reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})


async def test_bathing_radius_setup(hass: HomeAssistant, enable_custom_integrations) -> None:
    with patch(FLOW + "async_fetch_sites", side_effect=_sites):
        result = await _start(hass, MODE_BATHING_RADIUS)
        assert result["step_id"] == "bathing_radius"
        # nothing within one kilometre of a place in the Jura
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LATITUDE: 47.3, CONF_LONGITUDE: 7.0, CONF_RADIUS_KM: 1})
        assert result["errors"] == {"base": "no_sites"}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], BERN)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_MODE: MODE_BATHING_RADIUS, **BERN, CONF_RADIUS_KM: 10.0, CONF_BATHING_SITES: []}
    assert result["result"].unique_id == "bathing_radius_46.95_7.45_10.0"


async def test_bathing_radius_counts_the_lake_stations(hass: HomeAssistant, enable_custom_integrations) -> None:
    with patch(FLOW + "async_fetch_sites", side_effect=_sites):
        result = await _start(hass, MODE_BATHING_RADIUS)
        # around Zurich there is no official site in the fake list, but the two lake stations
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LATITUDE: 47.35, CONF_LONGITUDE: 8.55, CONF_RADIUS_KM: 5})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_bathing_favourite_setup_with_a_site_and_with_a_lake_station(hass: HomeAssistant, enable_custom_integrations) -> None:
    with patch(FLOW + "async_fetch_sites", side_effect=_sites):
        result = await _start(hass, MODE_BATHING_FAVORITE)
        assert result["step_id"] == "bathing_favorite"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_BATHING_SITE: "CH1"})
        assert result["type"] is FlowResultType.CREATE_ENTRY and result["title"] == "Marzili"
        assert result["data"][CONF_BATHING_SITES] == ["CH1"] and result["data"][CONF_MODE] == MODE_BATHING_FAVORITE
        assert result["result"].unique_id == "bathing_CH1"

        result = await _start(hass, MODE_BATHING_FAVORITE)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_BATHING_SITE: "wapo_mythenquai"})
        assert result["title"] == "Zürichsee Mythenquai"


async def test_the_pickers_when_the_service_is_down(hass: HomeAssistant, enable_custom_integrations) -> None:
    with patch(FLOW + "async_fetch_sites", side_effect=OSError("down")), patch(FLOW + "async_fetch_stations", side_effect=OSError("down")):
        result = await _start(hass, MODE_BATHING_FAVORITE)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_BATHING_SITE: "wapo_mythenquai"})
        assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "cannot_connect"}

        result = await _start(hass, MODE_BATHING_RADIUS)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], BERN)
        assert result["errors"] == {"base": "cannot_connect"}

        # the station picker has nothing to offer then: the form comes back empty
        result = await _start(hass, MODE_FAVORITE)
        assert result["type"] is FlowResultType.FORM and result["step_id"] == "favorite"


def test_entry_mode():
    def entry(**data):
        return MockConfigEntry(domain=DOMAIN, data=data)
    assert entry_mode(entry(**{CONF_MODE: MODE_BATHING_RADIUS})) == MODE_BATHING_RADIUS
    assert entry_mode(entry(**{CONF_MODE: MODE_BATHING_FAVORITE})) == MODE_BATHING_FAVORITE
    assert entry_mode(entry(**{CONF_STATIONS: ["2135"]})) == MODE_FAVORITE  # entries from before the mode field
    assert entry_mode(entry(**{CONF_STATIONS: []})) == MODE_RADIUS


async def test_reconfigure_a_radius_drops_what_left_it(hass: HomeAssistant, source: Source) -> None:
    source.stations = {"2135": station(), "2004": station("2004", **LAKE)}
    entry = await setup_stations(hass, radius=30, unique_id="radius_46.95_7.45_30.0")
    assert sensor_id(hass, entry, "2004", "water_level") and marker_id(hass, entry, "2004")
    lake_device = next(d for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
                       if (DOMAIN, f"{entry.entry_id}_2004") in d.identifiers)

    async def _fetch(hass, lat, lon, radius_km, favorite_ids=None):
        return {"2135": station()}

    with patch(FLOW + "async_fetch_stations", side_effect=_fetch):
        result = await _reconfigure(hass, entry)
        assert result["step_id"] == "reconfigure_radius"
        source.stations = {"2135": station()}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {**BERN, CONF_RADIUS_KM: 5})
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_RADIUS_KM] == 5.0 and entry.unique_id == "radius_46.95_7.45_5.0"
    assert sensor_id(hass, entry, "2004", "water_level") is None and marker_id(hass, entry, "2004") is None
    assert dr.async_get(hass).async_get(lake_device.id) is None
    # the station that stays keeps all its entities, the trend among them
    for key in ("temperature", "water_level", "discharge", "danger_level", "trend"):
        assert sensor_id(hass, entry, "2135", key)
    assert marker_id(hass, entry, "2135")


async def test_reconfigure_the_bathing_entries(hass: HomeAssistant, bathing: Bathing) -> None:
    entry = await setup_bathing(hass, radius=10)
    assert sensor_id(hass, entry, "CH2", "quality")
    with patch(FLOW + "async_fetch_sites", side_effect=_sites):
        result = await _reconfigure(hass, entry)
        assert result["step_id"] == "reconfigure_bathing_radius"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LATITUDE: 46.940, CONF_LONGITUDE: 7.443, CONF_RADIUS_KM: 1})
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert sensor_id(hass, entry, "CH1", "quality") and sensor_id(hass, entry, "CH2", "quality") is None

    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MODE: MODE_BATHING_FAVORITE, CONF_BATHING_SITES: ["CH404"], CONF_RADIUS_KM: 0})
    bathing.temperatures = {"tiefenbrunnen": lake_station()}
    with patch(FLOW + "async_fetch_sites", side_effect=_sites):
        result = await _reconfigure(hass, entry)
        assert result["step_id"] == "reconfigure_bathing_favorite"  # the site that is gone is not preselected
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_BATHING_SITE: "wapo_tiefenbrunnen"})
        await hass.async_block_till_done()
    assert entry.title == "Zürichsee Tiefenbrunnen" and entry.data[CONF_BATHING_SITES] == ["wapo_tiefenbrunnen"]
    assert sensor_id(hass, entry, "wapo_tiefenbrunnen", "water_temperature")
    assert sensor_id(hass, entry, "CH1", "quality") is None


async def test_reconfigure_a_favourite_whose_station_is_gone(hass: HomeAssistant, source: Source) -> None:
    entry = await setup_stations(hass, radius=0, favorites=["9999"], unique_id="station_9999")

    async def _all(hass, lat, lon, radius_km, favorite_ids=None):
        return {"2135": station()}

    with patch(FLOW + "async_fetch_stations", side_effect=_all):
        result = await _reconfigure(hass, entry)
        assert result["step_id"] == "reconfigure_favorite"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STATION: "2135"})
        await hass.async_block_till_done()
    assert entry.data[CONF_STATIONS] == ["2135"] and entry.title == "Aare – Bern, Schönau"


async def test_setup_goes_on_when_the_dashboard_file_cannot_be_served(hass: HomeAssistant, source: Source, caplog) -> None:
    with patch("custom_components.swiss_waters.async_serve_frontend", side_effect=RuntimeError("no http")):
        entry = await setup_stations(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert "Serving the bundled dashboard strategy failed" in caplog.text
    assert async_setup_entry  # imported for the patch target above


async def test_frontend_registration_is_retried_after_a_failure(hass: HomeAssistant) -> None:
    from custom_components.swiss_waters import frontend

    class _Http:
        def __init__(self):
            self.calls = 0
            self.fail = True

        async def async_register_static_paths(self, paths):
            self.calls += 1
            if self.fail:
                raise RuntimeError("busy")

    hass.http = _Http()
    try:
        await frontend.async_serve_frontend(hass)
    except RuntimeError:
        pass
    hass.http.fail = False
    await frontend.async_serve_frontend(hass)
    await frontend.async_serve_frontend(hass)  # served: nothing more to do
    assert hass.http.calls == 2


def test_strings_fall_back_to_english(hass: HomeAssistant) -> None:
    hass.config.language = "rm"
    assert t("sensor_trend", hass) == "Trend"
    assert t("no_such_key", hass) == "no_such_key"
    assert bathing_quality_text("good", hass) == "Good"
    assert bathing_quality_text("odd", hass) == "odd" and bathing_quality_text(None, hass) is None
    hass.config.language = "fr-CH"
    assert t("trend_rising", hass) == "En hausse"


def test_compact_limits_and_redacts():
    @dataclass
    class Thing:
        longitude: float
        label: str

    value = _compact({
        "latitude": 46.9, "address": "Musterweg 1", "when": datetime(2026, 11, 23, 12, tzinfo=timezone.utc), "day": date(2026, 11, 23),
        "span": timedelta(minutes=5), "long": "x" * 1000, "many": list(range(100)), "set": {1}, "thing": Thing(7.4, "ok"), "other": object(), "flag": True,
    })
    assert value["latitude"] == REDACTED and value["address"] == REDACTED
    assert value["when"].startswith("2026-11-23") and len(value["long"]) < 400 and len(value["many"]) <= 27
    assert value["thing"]["longitude"] == REDACTED and value["thing"]["label"] == "ok"
    assert isinstance(value["other"], str) and value["flag"] is True
