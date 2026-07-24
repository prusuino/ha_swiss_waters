"""Config flow for the Swiss Waters (BAFU) integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    DEFAULT_RADIUS_KM,
    DOMAIN,
)
from .coordinator import async_fetch_stations
from .localization import t

_LOGGER = logging.getLogger(__name__)


class SwissWatersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow: location + radius; validates that stations exist in range."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            radius = user_input[CONF_RADIUS_KM]
            unique_id = f"{round(lat, 2)}_{round(lon, 2)}_{radius}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                stations = await async_fetch_stations(self.hass, lat, lon, radius)
            except Exception:  # noqa: BLE001 - surface any fetch problem as a form error
                _LOGGER.exception("LINDAS validation query failed")
                errors["base"] = "cannot_connect"
                stations = {}

            if not errors and not stations:
                errors["base"] = "no_stations"

            if not errors:
                return self.async_create_entry(
                    title=t("entry_title", self.hass, radius=round(radius)),
                    data={
                        CONF_LATITUDE: lat,
                        CONF_LONGITUDE: lon,
                        CONF_RADIUS_KM: radius,
                    },
                )

        default_lat = self.hass.config.latitude
        default_lon = self.hass.config.longitude

        schema = vol.Schema(
            {
                vol.Required(CONF_LATITUDE, default=default_lat): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=default_lon): vol.Coerce(float),
                vol.Required(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
