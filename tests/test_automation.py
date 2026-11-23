"""The triggers and conditions for the automation editor, tried with real
automations while the faked feed changes, plus the diagnostics download."""
from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.swiss_waters import condition, trigger
from custom_components.swiss_waters.const import DOMAIN
from custom_components.swiss_waters.diagnostics import REDACTED, async_get_config_entry_diagnostics

from .common import HOME, Source, refresh, sensor_id, setup_stations, station

FOREIGN = "sensor.cellar_humidity"


async def _automation(hass: HomeAssistant, *, trigger: dict | None = None, condition: dict | None = None) -> list:
    calls = async_mock_service(hass, "test", "automation")
    config = {
        "alias": "Tell me",
        "trigger": trigger or {"trigger": "event", "event_type": "check_now"},
        "action": {"action": "test.automation"},
    }
    if condition:
        config["condition"] = condition
    assert await async_setup_component(hass, "automation", {"automation": config})
    await hass.async_block_till_done()
    assert hass.states.get("automation.tell_me") is not None, "the automation was rejected"
    return calls


async def _check(hass: HomeAssistant, calls: list) -> bool:
    before = len(calls)
    hass.bus.async_fire("check_now")
    await hass.async_block_till_done()
    return len(calls) > before


async def _play(hass, source, entry, **values) -> None:
    source.stations = {"2135": station(**values)}
    await refresh(hass, entry)


async def test_platforms_offer_their_triggers_and_conditions(hass: HomeAssistant) -> None:
    assert set(await trigger.async_get_triggers(hass)) == {
        "flood_danger_level_reached", "water_temperature_crossed_threshold", "water_level_crossed_threshold", "discharge_crossed_threshold"}
    assert set(await condition.async_get_conditions(hass)) == {"is_flood_danger_at_least", "is_flood_danger_below"}


async def test_flood_danger_level_reached(hass: HomeAssistant, source: Source) -> None:
    entry = await setup_stations(hass)
    danger = sensor_id(hass, entry, "2135", "danger_level")
    level = sensor_id(hass, entry, "2135", "water_level")
    hass.states.async_set(FOREIGN, "1")
    calls = await _automation(hass, trigger={
        "trigger": "swiss_waters.flood_danger_level_reached",
        "target": {"entity_id": [danger, level, FOREIGN]}, "options": {"minimum_level": 3},
    })
    hass.states.async_set(FOREIGN, "5")  # not ours
    await hass.async_block_till_done()
    await _play(hass, source, entry, danger_level=2, water_level=503.0)  # below the minimum; the level sensor is no danger sensor
    assert len(calls) == 0
    await _play(hass, source, entry, danger_level=3)
    assert len(calls) == 1
    await _play(hass, source, entry, danger_level=4)  # already above: quiet
    assert len(calls) == 1
    # a gap without a value: the level was already above the minimum before it
    await _play(hass, source, entry, danger_level=None)
    await _play(hass, source, entry, danger_level=5)
    assert len(calls) == 1
    # the river rises during an outage: it was below the minimum before the gap
    await _play(hass, source, entry, danger_level=1)
    source.stations = {"2135": station(fresh=False)}  # the station goes stale: unavailable
    await refresh(hass, entry)
    await _play(hass, source, entry, danger_level=3)
    assert len(calls) == 2
    await _play(hass, source, entry, danger_level=None)
    await _play(hass, source, entry, danger_level=None)
    assert len(calls) == 2


async def test_threshold_triggers(hass: HomeAssistant, source: Source) -> None:
    entry = await setup_stations(hass)
    temperature = sensor_id(hass, entry, "2135", "temperature")
    level = sensor_id(hass, entry, "2135", "water_level")
    discharge = sensor_id(hass, entry, "2135", "discharge")
    warm = await _automation(hass, trigger=[
        {"trigger": "swiss_waters.water_temperature_crossed_threshold", "target": {"entity_id": [temperature, level]},
         "options": {"threshold": {"type": "above", "value": {"number": 18}}}},
        {"trigger": "swiss_waters.water_level_crossed_threshold", "target": {"entity_id": [level, temperature]},
         "options": {"threshold": {"type": "above", "value": {"number": 503}}}},
        {"trigger": "swiss_waters.discharge_crossed_threshold", "target": {"entity_id": [discharge, level]},
         "options": {"threshold": {"type": "below", "value": {"number": 50}}}},
    ])
    await _play(hass, source, entry, temperature=17.9)
    assert len(warm) == 0
    await _play(hass, source, entry, temperature=18.4)  # the temperature crosses 18; the level (502.4) is not a temperature
    assert len(warm) == 1
    await _play(hass, source, entry, temperature=18.4, water_level=503.2)
    assert len(warm) == 2
    await _play(hass, source, entry, temperature=18.4, water_level=503.2, discharge=40.0)
    assert len(warm) == 3


async def test_conditions(hass: HomeAssistant, source: Source) -> None:
    entry = await setup_stations(hass)
    danger = sensor_id(hass, entry, "2135", "danger_level")
    hass.states.async_set(FOREIGN, "5")
    high = await _automation(hass, condition={
        "condition": "swiss_waters.is_flood_danger_at_least", "target": {"entity_id": [danger, FOREIGN]}, "options": {"level": 3}})
    assert await _check(hass, high) is False  # level 1; the foreign 5 does not count
    await _play(hass, source, entry, danger_level=3)
    assert await _check(hass, high) is True
    await _play(hass, source, entry, danger_level=None)
    assert await _check(hass, high) is False


async def test_condition_below(hass: HomeAssistant, source: Source) -> None:
    entry = await setup_stations(hass)
    danger = sensor_id(hass, entry, "2135", "danger_level")
    low = await _automation(hass, condition={"condition": "swiss_waters.is_flood_danger_below", "target": {"entity_id": danger}})
    assert await _check(hass, low) is True  # level 1 is below the default 3
    await _play(hass, source, entry, danger_level=4)
    assert await _check(hass, low) is False
    await _play(hass, source, entry, danger_level=None)
    assert await _check(hass, low) is False  # no value is not "below"


async def test_diagnostics(hass: HomeAssistant, source: Source) -> None:
    entry = await setup_stations(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(diag)
    assert diag["entry"]["title"] == REDACTED and diag["entry"]["unique_id"] == REDACTED
    assert diag["entry"]["data"]["latitude"] == REDACTED and diag["entry"]["data"]["radius_km"] == 30
    assert str(HOME[0]) not in text and str(HOME[1]) not in text  # the configured location stays private
    assert any(e["unique_id"] == f"{entry.entry_id}_2135_trend" for e in diag["entities"])
    assert "2135" in text

    bare = MockConfigEntry(domain=DOMAIN, title="x", data={"name": "Daheim"})
    bare.add_to_hass(hass)
    diag = await async_get_config_entry_diagnostics(hass, bare)
    assert diag["entities"] == [] and diag["entry"]["unique_id"] is None
