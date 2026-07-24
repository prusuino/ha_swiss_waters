"""Config flow for the Swiss Waters (BAFU) integration.

One form combines both selection modes: a radius search around a location
(radius 0 disables it) and/or hand-picked favorite stations chosen by name.
The resulting station set is the union of both.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS_KM,
    CONF_STATIONS,
    DEFAULT_RADIUS_KM,
    DOMAIN,
)
from .coordinator import async_fetch_stations
from .localization import t

_LOGGER = logging.getLogger(__name__)


def _station_options(stations: dict[str, dict]) -> list[selector.SelectOptionDict]:
    options = []
    for s in stations.values():
        water = s.get("water_body")
        name = s.get("name") or s["station_id"]
        label = f"{water} – {name}" if water else name
        options.append(selector.SelectOptionDict(value=s["station_id"], label=label))
    return sorted(options, key=lambda o: o["label"].lower())


class SwissWatersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow: location + radius and/or favorite stations by name."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        try:
            # oversized radius = fetch every station, for the favorites picker
            all_stations = await async_fetch_stations(self.hass, 46.8, 8.2, 100000.0, None)
        except Exception:  # noqa: BLE001 - offline: form still usable for radius-only
            _LOGGER.exception("LINDAS station list unavailable for the favorites picker")
            all_stations = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            radius = user_input[CONF_RADIUS_KM]
            favorites = sorted(user_input.get(CONF_STATIONS, []))

            if radius <= 0 and not favorites:
                errors["base"] = "nothing_selected"

            if not errors:
                unique_id = f"{round(lat, 2)}_{round(lon, 2)}_{radius}_{'-'.join(favorites)}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                try:
                    stations = await async_fetch_stations(
                        self.hass, lat, lon, radius, set(favorites)
                    )
                except Exception:  # noqa: BLE001 - surface any fetch problem as a form error
                    _LOGGER.exception("LINDAS validation query failed")
                    errors["base"] = "cannot_connect"
                    stations = {}

                if not errors and not stations:
                    errors["base"] = "no_stations"

            if not errors:
                if radius > 0 and favorites:
                    title = t(
                        "entry_title_combined",
                        self.hass,
                        radius=round(radius),
                        count=len(favorites),
                    )
                elif favorites:
                    title = t("entry_title_favorites", self.hass, count=len(favorites))
                else:
                    title = t("entry_title", self.hass, radius=round(radius))
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_LATITUDE: lat,
                        CONF_LONGITUDE: lon,
                        CONF_RADIUS_KM: radius,
                        CONF_STATIONS: favorites,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): vol.Coerce(float),
                vol.Required(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): vol.Coerce(float),
                vol.Optional(CONF_STATIONS, default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_station_options(all_stations),
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        sort=False,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
