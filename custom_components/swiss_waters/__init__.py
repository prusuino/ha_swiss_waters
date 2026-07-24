"""Swiss Waters (BAFU) integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SwissWatersCoordinator
from .dashboard import async_ensure_dashboard

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "geo_location"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SwissWatersCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    try:
        await async_ensure_dashboard(hass)
    except Exception:  # noqa: BLE001 - dashboard setup must never block integration setup
        _LOGGER.exception("Automatic Swiss Waters dashboard setup failed")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
