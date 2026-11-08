"""Triggers for Swiss Waters.

"Flood danger level reached", "Water temperature crossed a threshold",
"Water level crossed a threshold" and "Discharge crossed a threshold" for
the automation editor's trigger list. Each trigger targets the
integration's own entities: a target that expands to other entities (a
device, an area) is narrowed to the ones this integration created, and to
the measure the trigger is about.

The trigger platform API arrived in Home Assistant 2026.10. On an older
version the module still imports, but offers no triggers.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, SensorDeviceClass
from homeassistant.const import CONF_FOR, CONF_OPTIONS, CONF_TARGET
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import DOMAIN

CONF_MINIMUM_LEVEL = "minimum_level"
DEFAULT_MINIMUM_LEVEL = 3

try:
    from homeassistant.helpers.automation import DomainSpec
    from homeassistant.helpers.trigger import (
        ATTR_BEHAVIOR,
        BEHAVIOR_ALL,
        BEHAVIOR_EACH,
        BEHAVIOR_FIRST,
        EntityTriggerBase,
        Trigger,
        make_entity_numerical_state_crossed_threshold_trigger,
    )
except ImportError:  # Home Assistant before 2026.10: no trigger platform API
    TRIGGERS: dict = {}
else:
    ANY_SENSOR_SPECS = {SENSOR_DOMAIN: DomainSpec()}
    TEMPERATURE_SPECS = {SENSOR_DOMAIN: DomainSpec(device_class=SensorDeviceClass.TEMPERATURE)}

    # The core's entity-state schema (target + behavior + for) plus the
    # danger level option, spelled out because the nested options mapping
    # cannot be extended in place.
    DANGER_LEVEL_SCHEMA = vol.Schema(
        {
            vol.Required(CONF_TARGET): cv.TARGET_FIELDS,
            vol.Required(CONF_OPTIONS, default={}): {
                vol.Required(ATTR_BEHAVIOR, default=BEHAVIOR_EACH): vol.In(
                    [BEHAVIOR_FIRST, BEHAVIOR_ALL, BEHAVIOR_EACH]
                ),
                vol.Optional(CONF_FOR): cv.positive_time_period,
                vol.Optional(CONF_MINIMUM_LEVEL, default=DEFAULT_MINIMUM_LEVEL): vol.All(
                    vol.Coerce(int), vol.Range(min=2, max=5)
                ),
            },
        }
    )

    def _own_entities(hass: HomeAssistant, entities: set[str], measure: str | None = None) -> set[str]:
        """Keep only entities created by this integration, optionally only
        those of one measure (the unique id ends with the measure's key)."""
        registry = er.async_get(hass)
        kept: set[str] = set()
        for entity_id in entities:
            entry = registry.async_get(entity_id)
            if entry is None or entry.platform != DOMAIN:
                continue
            if measure is not None and not (entry.unique_id or "").endswith(f"_{measure}"):
                continue
            kept.add(entity_id)
        return kept

    def _level(state: State) -> int | None:
        try:
            return int(float(state.state))
        except (TypeError, ValueError):
            return None

    class _FloodDangerLevelReached(EntityTriggerBase):
        """A station's flood danger level rises to the minimum level or above.

        Fires when the level goes from below the minimum (or from no value)
        to the minimum or higher; a change between two levels above the
        minimum does not fire again."""

        _domain_specs = ANY_SENSOR_SPECS
        _schema = DANGER_LEVEL_SCHEMA

        def __init__(self, hass: HomeAssistant, config) -> None:
            super().__init__(hass, config)
            self._minimum = int(self._options.get(CONF_MINIMUM_LEVEL) or DEFAULT_MINIMUM_LEVEL)

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_entities(self._hass, super().entity_filter(entities), "danger_level")

        def is_valid_transition(self, from_state: State, to_state: State) -> bool:
            before = _level(from_state)
            after = _level(to_state)
            return after is not None and after >= self._minimum and (before is None or before < self._minimum)

        def is_valid_state(self, state: State, report_not_triggered) -> bool:
            level = _level(state)
            if level is None:
                report_not_triggered("level_not_numeric", entity_id=state.entity_id)
                return False
            return level >= self._minimum

    class _WaterTemperatureCrossed(
        make_entity_numerical_state_crossed_threshold_trigger(TEMPERATURE_SPECS, "°C")
    ):
        """A station's water temperature crosses the configured threshold."""

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_entities(self._hass, super().entity_filter(entities), "temperature")

    class _WaterLevelCrossed(
        make_entity_numerical_state_crossed_threshold_trigger(ANY_SENSOR_SPECS, "m")
    ):
        """A station's water level crosses the configured threshold."""

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_entities(self._hass, super().entity_filter(entities), "water_level")

    class _DischargeCrossed(
        make_entity_numerical_state_crossed_threshold_trigger(ANY_SENSOR_SPECS, "m³/s")
    ):
        """A station's discharge crosses the configured threshold."""

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_entities(self._hass, super().entity_filter(entities), "discharge")

    TRIGGERS: dict[str, type[Trigger]] = {
        "flood_danger_level_reached": _FloodDangerLevelReached,
        "water_temperature_crossed_threshold": _WaterTemperatureCrossed,
        "water_level_crossed_threshold": _WaterLevelCrossed,
        "discharge_crossed_threshold": _DischargeCrossed,
    }


async def async_get_triggers(hass: HomeAssistant) -> dict:
    """Return the triggers of this integration."""
    return TRIGGERS
