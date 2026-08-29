"""Swiss Waters (BAFU) integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MODE, DOMAIN, MODE_BATHING_FAVORITE, MODE_BATHING_RADIUS
from .coordinator import SwissBathingCoordinator, SwissWatersCoordinator

PLATFORMS = ["sensor", "geo_location"]

BATHING_MODES = (MODE_BATHING_RADIUS, MODE_BATHING_FAVORITE)


def is_bathing_entry(entry: ConfigEntry) -> bool:
    """Whether this entry tracks bathing sites instead of monitoring stations."""
    return entry.data.get(CONF_MODE) in BATHING_MODES


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if is_bathing_entry(entry):
        coordinator: SwissBathingCoordinator | SwissWatersCoordinator = (
            SwissBathingCoordinator(hass, entry)
        )
    else:
        coordinator = SwissWatersCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
