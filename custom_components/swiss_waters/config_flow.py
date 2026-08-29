"""Config flow for the Swiss Waters (BAFU) integration.

Setup wizard: first pick a mode — a radius overview (all stations around a
location), a single favorite station picked by name, all bathing sites
within a radius, or a single favourite bathing site. Repeatable: add the
integration again for another radius or another favorite; each favorite is
its own entry.

The station and site lists for the pickers are fetched once per flow and
reused between rendering the form and handling its submission.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    BATHING_TEMP_STATIONS,
    CONF_BATHING_SITE,
    CONF_BATHING_SITES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_RADIUS_KM,
    CONF_STATION,
    CONF_STATIONS,
    DEFAULT_RADIUS_KM,
    DOMAIN,
    MODE_BATHING_FAVORITE,
    MODE_BATHING_RADIUS,
    MODE_FAVORITE,
    MODE_RADIUS,
)
from .bathing import async_fetch_sites
from .coordinator import async_fetch_stations, haversine_km
from .localization import t

_LOGGER = logging.getLogger(__name__)


def _station_label(s: dict) -> str:
    water = s.get("water_body")
    name = s.get("name") or s["station_id"]
    return f"{water} – {name}" if water else name


def _bathing_sites_within(sites: dict[str, dict], lat: float, lon: float, radius_km: float) -> int:
    """Number of bathing sites inside the radius — the official sites plus the
    Zurich lake stations, which the coordinator includes the same way."""
    candidates = list(sites.values()) + list(BATHING_TEMP_STATIONS.values())
    return sum(
        1
        for site in candidates
        if haversine_km(lat, lon, site["latitude"], site["longitude"]) <= radius_km
    )


class SwissWatersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup wizard: pick radius overview or favorite mode, then configure it."""

    VERSION = 1

    def __init__(self) -> None:
        # Picker lists, fetched once per flow (see _async_station_list).
        self._stations: dict[str, dict] = {}
        self._sites: dict[str, dict] = {}

    async def _async_station_list(self) -> dict[str, dict]:
        """Every monitoring station, for the favorite picker.

        Fetched once per flow; an empty result means LINDAS was unreachable
        (logged as a warning — a transient outage is not an error of ours)
        and is retried on the next call.
        """
        if not self._stations:
            try:
                # oversized radius = fetch every station
                self._stations = await async_fetch_stations(self.hass, 46.8, 8.2, 100000.0)
            except Exception as err:  # noqa: BLE001 - any fetch problem becomes a form error
                _LOGGER.warning("LINDAS station list unavailable: %s", err)
                self._stations = {}
        return self._stations

    async def _async_site_list(self) -> dict[str, dict]:
        """Every official bathing site; same caching and failure handling as
        the station list."""
        if not self._sites:
            try:
                self._sites = await async_fetch_sites(self.hass)
            except Exception as err:  # noqa: BLE001 - any fetch problem becomes a form error
                _LOGGER.warning("LINDAS bathing site list unavailable: %s", err)
                self._sites = {}
        return self._sites

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            mode = user_input[CONF_MODE]
            if mode == MODE_FAVORITE:
                return await self.async_step_favorite()
            if mode == MODE_BATHING_RADIUS:
                return await self.async_step_bathing_radius()
            if mode == MODE_BATHING_FAVORITE:
                return await self.async_step_bathing_favorite()
            return await self.async_step_radius()

        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=MODE_RADIUS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=MODE_RADIUS, label=t("mode_radius", self.hass)
                            ),
                            selector.SelectOptionDict(
                                value=MODE_FAVORITE, label=t("mode_favorite", self.hass)
                            ),
                            selector.SelectOptionDict(
                                value=MODE_BATHING_RADIUS,
                                label=t("mode_bathing_radius", self.hass),
                            ),
                            selector.SelectOptionDict(
                                value=MODE_BATHING_FAVORITE,
                                label=t("mode_bathing_favorite", self.hass),
                            ),
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_radius(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Radius overview: every station within a radius around a location."""
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            radius = user_input[CONF_RADIUS_KM]
            await self.async_set_unique_id(f"radius_{round(lat, 2)}_{round(lon, 2)}_{radius}")
            self._abort_if_unique_id_configured()

            try:
                stations = await async_fetch_stations(self.hass, lat, lon, radius)
            except Exception as err:  # noqa: BLE001 - surface any fetch problem as a form error
                _LOGGER.warning("LINDAS validation query failed: %s", err)
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
                        CONF_STATIONS: [],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): vol.Coerce(float),
                vol.Required(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=1000,
                        step="any",
                        unit_of_measurement="km",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="radius", data_schema=schema, errors=errors)

    async def async_step_favorite(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A single favorite station, picked by name — one entry per favorite."""
        errors: dict[str, str] = {}
        all_stations = await self._async_station_list()

        if user_input is not None:
            station_id = user_input[CONF_STATION]
            await self.async_set_unique_id(f"station_{station_id}")
            self._abort_if_unique_id_configured()

            if not all_stations:
                errors["base"] = "cannot_connect"

            if not errors:
                station = all_stations.get(station_id)
                title = _station_label(station) if station else station_id
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_LATITUDE: self.hass.config.latitude,
                        CONF_LONGITUDE: self.hass.config.longitude,
                        CONF_RADIUS_KM: 0,
                        CONF_STATIONS: [station_id],
                    },
                )

        options = sorted(
            (
                selector.SelectOptionDict(value=s["station_id"], label=_station_label(s))
                for s in all_stations.values()
            ),
            key=lambda o: o["label"].lower(),
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_STATION): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        sort=False,
                    )
                )
            }
        )
        return self.async_show_form(step_id="favorite", data_schema=schema, errors=errors)

    async def async_step_bathing_radius(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """All official bathing sites within a radius around a location."""
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            radius = user_input[CONF_RADIUS_KM]
            await self.async_set_unique_id(
                f"bathing_radius_{round(lat, 2)}_{round(lon, 2)}_{radius}"
            )
            self._abort_if_unique_id_configured()

            sites = await self._async_site_list()
            if not sites:
                errors["base"] = "cannot_connect"
            elif not _bathing_sites_within(sites, lat, lon, radius):
                errors["base"] = "no_sites"

            if not errors:
                return self.async_create_entry(
                    title=t("bathing_entry_title", self.hass, radius=round(radius)),
                    data={
                        CONF_MODE: MODE_BATHING_RADIUS,
                        CONF_LATITUDE: lat,
                        CONF_LONGITUDE: lon,
                        CONF_RADIUS_KM: radius,
                        CONF_BATHING_SITES: [],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): vol.Coerce(float),
                vol.Required(CONF_RADIUS_KM, default=DEFAULT_RADIUS_KM): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=1000,
                        step="any",
                        unit_of_measurement="km",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="bathing_radius", data_schema=schema, errors=errors
        )

    async def async_step_bathing_favorite(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A single favourite bathing site, picked by name."""
        errors: dict[str, str] = {}
        official_sites = await self._async_site_list()

        # The live lake stations are offered alongside the official sites.
        # They are merged in after the emptiness check below: an unreachable
        # LINDAS must not be masked by a picker that still lists two stations.
        all_sites = dict(official_sites)
        for code, station in BATHING_TEMP_STATIONS.items():
            site_id = f"wapo_{code}"
            all_sites[site_id] = {**station, "site_id": site_id}

        if user_input is not None:
            site_id = user_input[CONF_BATHING_SITE]
            await self.async_set_unique_id(f"bathing_{site_id}")
            self._abort_if_unique_id_configured()

            if not official_sites:
                errors["base"] = "cannot_connect"

            if not errors:
                site = all_sites.get(site_id) or {}
                return self.async_create_entry(
                    title=site.get("name") or site_id,
                    data={
                        CONF_MODE: MODE_BATHING_FAVORITE,
                        CONF_LATITUDE: self.hass.config.latitude,
                        CONF_LONGITUDE: self.hass.config.longitude,
                        CONF_RADIUS_KM: 0,
                        CONF_BATHING_SITES: [site_id],
                    },
                )

        options = sorted(
            (
                selector.SelectOptionDict(
                    value=site.get("site_id", site_id),
                    label=site.get("name") or site_id,
                )
                for site_id, site in all_sites.items()
            ),
            key=lambda o: o["label"].lower(),
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_BATHING_SITE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        sort=False,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="bathing_favorite", data_schema=schema, errors=errors
        )
