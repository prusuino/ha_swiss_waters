"""Conditions for Swiss Waters.

"Flood danger level is at least" and "Flood danger level is below" for the
automation editor's condition list, so an automation can check a river's
official flood danger level without a numeric state condition on a
specific entity. As with the triggers, a target that expands to other
entities is narrowed to the danger-level sensors this integration created.

The condition platform API arrived in Home Assistant 2026.11. On an older
version the module still imports, but offers no conditions.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_FOR, CONF_OPTIONS, CONF_TARGET
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import DOMAIN

CONF_LEVEL = "level"
DEFAULT_LEVEL = 3
_BEHAVIOR = "behavior"
_BEHAVIOR_ANY = "any"
_BEHAVIOR_ALL = "all"

try:
    from homeassistant.helpers.automation import DomainSpec
    from homeassistant.helpers.condition import Condition, EntityConditionBase
except ImportError:  # Home Assistant before 2026.11: no condition platform API
    CONDITIONS: dict = {}
else:
    DANGER_SPECS = {SENSOR_DOMAIN: DomainSpec()}

    # The core's entity-state condition schema (target + behavior any/all +
    # for) plus the level option.
    LEVEL_SCHEMA = vol.Schema(
        {
            vol.Required(CONF_TARGET): cv.TARGET_FIELDS,
            vol.Required(CONF_OPTIONS, default={}): {
                vol.Required(_BEHAVIOR, default=_BEHAVIOR_ANY): vol.In([_BEHAVIOR_ANY, _BEHAVIOR_ALL]),
                vol.Optional(CONF_FOR): cv.positive_time_period,
                vol.Optional(CONF_LEVEL, default=DEFAULT_LEVEL): vol.All(
                    vol.Coerce(int), vol.Range(min=2, max=5)
                ),
            },
        }
    )

    def _own_danger_entities(hass: HomeAssistant, entities: set[str]) -> set[str]:
        """Keep only the flood danger level sensors of this integration."""
        registry = er.async_get(hass)
        return {
            entity_id
            for entity_id in entities
            if (entry := registry.async_get(entity_id)) is not None
            and entry.platform == DOMAIN
            and (entry.unique_id or "").endswith("_danger_level")
        }

    def _level(state: State) -> int | None:
        try:
            return int(float(state.state))
        except (TypeError, ValueError):
            return None

    class _DangerLevelConditionBase(EntityConditionBase):
        _domain_specs = DANGER_SPECS
        _schema = LEVEL_SCHEMA

        def __init__(self, hass: HomeAssistant, config) -> None:
            super().__init__(hass, config)
            self._level = int((config.options or {}).get(CONF_LEVEL) or DEFAULT_LEVEL)

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_danger_entities(self._hass, super().entity_filter(entities))

    class _IsFloodDangerAtLeast(_DangerLevelConditionBase):
        """The flood danger level is at the configured level or above."""

        def is_valid_state(self, entity_state: State) -> bool:
            level = _level(entity_state)
            return level is not None and level >= self._level

    class _IsFloodDangerBelow(_DangerLevelConditionBase):
        """The flood danger level is below the configured level."""

        def is_valid_state(self, entity_state: State) -> bool:
            level = _level(entity_state)
            return level is not None and level < self._level

    CONDITIONS: dict[str, type[Condition]] = {
        "is_flood_danger_at_least": _IsFloodDangerAtLeast,
        "is_flood_danger_below": _IsFloodDangerBelow,
    }


async def async_get_conditions(hass: HomeAssistant) -> dict:
    """Return the conditions of this integration."""
    return CONDITIONS
