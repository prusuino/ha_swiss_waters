"""Config flow for the Swiss Waters (BAFU) integration.

Setup wizard: first pick a mode — a radius overview (all stations around a
location), a single favorite station picked by name, all bathing sites
within a radius, or a single favourite bathing site. Repeatable: add the
integration again for another radius or another favorite; each favorite is
its own entry.

Reconfigure (the entry's menu under Settings → Devices & services) changes
an entry in place with the same form as its setup: another radius or
location, another station or site. The entry keeps its id, so the
entities of stations and sites that stay selected keep their ids and
history; the entities and devices of those that drop out of the selection
are removed, and the reload creates the new ones.

The station and site lists for the pickers are fetched once per flow and
reused between rendering the form and handling its submission.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
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

# Unique-id suffixes the sensor platform uses per station / per bathing site
# (see sensor.py). Reconfigure uses them to tell the entities of stations
# that stay selected from those that have to go.
_STATION_MEASURES = ("temperature", "water_level", "discharge", "danger_level")
_BATHING_MEASURES = ("quality", "last_sample", "water_temperature")


def _station_label(s: dict) -> str:
    water = s.get("water_body")
    name = s.get("name") or s["station_id"]
    return f"{water} – {name}" if water else name


def _bathing_site_ids_within(
    sites: dict[str, dict], lat: float, lon: float, radius_km: float
) -> set[str]:
    """Ids of the bathing sites inside the radius — the official sites plus
    the Zurich lake stations, which the coordinator includes the same way."""
    ids = {
        site_id
        for site_id, site in sites.items()
        if haversine_km(lat, lon, site["latitude"], site["longitude"]) <= radius_km
    }
    ids |= {
        f"wapo_{code}"
        for code, station in BATHING_TEMP_STATIONS.items()
        if haversine_km(lat, lon, station["latitude"], station["longitude"]) <= radius_km
    }
    return ids


def entry_mode(entry: ConfigEntry) -> str:
    """The setup mode of an entry. Station entries predate CONF_MODE: a
    favorite lists its station, a radius overview has an empty list."""
    mode = entry.data.get(CONF_MODE)
    if mode in (MODE_BATHING_RADIUS, MODE_BATHING_FAVORITE):
        return mode
    return MODE_FAVORITE if entry.data.get(CONF_STATIONS) else MODE_RADIUS


@callback
def remove_entities_outside(hass: HomeAssistant, entry: ConfigEntry, keep_ids: set[str]) -> None:
    """Drop the registry entries (entities and devices) of this entry whose
    station or bathing site is not in keep_ids any more.

    Called before the reload of a reconfigured entry: the platforms only ever
    add entities for what the coordinator returns, so without this the
    entities of a station that left the radius would stay behind as
    unavailable orphans, and a favorite changed to another station would
    keep the old device next to the new one.
    """
    wanted_entities = {
        f"{entry.entry_id}_{item}_{measure}"
        for item in keep_ids
        for measure in _STATION_MEASURES + _BATHING_MEASURES
    }
    wanted_entities |= {f"{DOMAIN}_{entry.entry_id}_{item}" for item in keep_ids}
    ent_reg = er.async_get(hass)
    for reg in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
        if reg.unique_id not in wanted_entities:
            ent_reg.async_remove(reg.entity_id)

    # Device identifiers carry the entry id, so a device is never shared with
    # another entry and can be removed outright.
    wanted_devices = {(DOMAIN, f"{entry.entry_id}_{item}") for item in keep_ids}
    dev_reg = dr.async_get(hass)
    for device in list(dr.async_entries_for_config_entry(dev_reg, entry.entry_id)):
        if not device.identifiers & wanted_devices:
            dev_reg.async_remove_device(device.id)


@dataclass
class _Prepared:
    """A validated selection, ready to be stored."""

    title: str
    data: dict[str, Any]
    keep_ids: set[str] = field(default_factory=set)


def _radius_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_LATITUDE, default=defaults[CONF_LATITUDE]): vol.Coerce(float),
            vol.Required(CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]): vol.Coerce(float),
            vol.Required(CONF_RADIUS_KM, default=defaults[CONF_RADIUS_KM]): selector.NumberSelector(
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


def _picker_schema(
    key: str, options: list[selector.SelectOptionDict], default: str | None
) -> vol.Schema:
    kwargs = {"default": default} if default is not None else {}
    return vol.Schema(
        {
            vol.Required(key, **kwargs): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    sort=False,
                )
            )
        }
    )


class SwissWatersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup wizard: pick radius overview or favorite mode, then configure it."""

    VERSION = 1

    def __init__(self) -> None:
        # Picker lists, fetched once per flow (see _async_station_list).
        self._stations: dict[str, dict] = {}
        self._sites: dict[str, dict] = {}

    # ------------------------------------------------------------------ lists

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

    def _all_bathing_sites(self, official_sites: dict[str, dict]) -> dict[str, dict]:
        """Official sites plus the live lake stations, for the picker."""
        all_sites = dict(official_sites)
        for code, station in BATHING_TEMP_STATIONS.items():
            site_id = f"wapo_{code}"
            all_sites[site_id] = {**station, "site_id": site_id}
        return all_sites

    # --------------------------------------------------------------- commit

    async def _async_claim(self, unique_id: str, entry: ConfigEntry | None) -> None:
        """Reserve the unique id; refuse a duplicate of another entry."""
        await self.async_set_unique_id(unique_id)
        if entry is None or unique_id != entry.unique_id:
            self._abort_if_unique_id_configured()

    def _finish(self, prepared: _Prepared, entry: ConfigEntry | None) -> ConfigFlowResult:
        if entry is None:
            return self.async_create_entry(title=prepared.title, data=prepared.data)
        remove_entities_outside(self.hass, entry, prepared.keep_ids)
        return self.async_update_reload_and_abort(
            entry,
            unique_id=self.unique_id,
            title=prepared.title,
            data=prepared.data,
            reason="reconfigure_successful",
        )

    # ----------------------------------------------------------------- steps

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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change an entry with the form of its own mode."""
        mode = entry_mode(self._get_reconfigure_entry())
        if mode == MODE_FAVORITE:
            return await self.async_step_reconfigure_favorite(user_input)
        if mode == MODE_BATHING_RADIUS:
            return await self.async_step_reconfigure_bathing_radius(user_input)
        if mode == MODE_BATHING_FAVORITE:
            return await self.async_step_reconfigure_bathing_favorite(user_input)
        return await self.async_step_reconfigure_radius(user_input)

    # radius overview ------------------------------------------------------

    async def async_step_radius(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Radius overview: every station within a radius around a location."""
        return await self._async_radius_form("radius", user_input, None)

    async def async_step_reconfigure_radius(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_radius_form(
            "reconfigure_radius", user_input, self._get_reconfigure_entry()
        )

    async def _async_radius_form(
        self, step_id: str, user_input: dict[str, Any] | None, entry: ConfigEntry | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            radius = user_input[CONF_RADIUS_KM]
            await self._async_claim(f"radius_{round(lat, 2)}_{round(lon, 2)}_{radius}", entry)

            try:
                stations = await async_fetch_stations(self.hass, lat, lon, radius)
            except Exception as err:  # noqa: BLE001 - surface any fetch problem as a form error
                _LOGGER.warning("LINDAS validation query failed: %s", err)
                errors["base"] = "cannot_connect"
                stations = {}

            if not errors and not stations:
                errors["base"] = "no_stations"

            if not errors:
                return self._finish(
                    _Prepared(
                        title=t("entry_title", self.hass, radius=round(radius)),
                        data={
                            CONF_LATITUDE: lat,
                            CONF_LONGITUDE: lon,
                            CONF_RADIUS_KM: radius,
                            CONF_STATIONS: [],
                        },
                        keep_ids=set(stations),
                    ),
                    entry,
                )

        defaults: Mapping[str, Any] = entry.data if entry else {}
        schema = _radius_schema(
            {
                CONF_LATITUDE: defaults.get(CONF_LATITUDE, self.hass.config.latitude),
                CONF_LONGITUDE: defaults.get(CONF_LONGITUDE, self.hass.config.longitude),
                CONF_RADIUS_KM: defaults.get(CONF_RADIUS_KM) or DEFAULT_RADIUS_KM,
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    # favorite station -----------------------------------------------------

    async def async_step_favorite(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A single favorite station, picked by name — one entry per favorite."""
        return await self._async_favorite_form("favorite", user_input, None)

    async def async_step_reconfigure_favorite(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_favorite_form(
            "reconfigure_favorite", user_input, self._get_reconfigure_entry()
        )

    async def _async_favorite_form(
        self, step_id: str, user_input: dict[str, Any] | None, entry: ConfigEntry | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        all_stations = await self._async_station_list()

        if user_input is not None:
            station_id = user_input[CONF_STATION]
            await self._async_claim(f"station_{station_id}", entry)

            if not all_stations:
                errors["base"] = "cannot_connect"

            if not errors:
                station = all_stations.get(station_id)
                return self._finish(
                    _Prepared(
                        title=_station_label(station) if station else station_id,
                        data={
                            CONF_LATITUDE: self.hass.config.latitude,
                            CONF_LONGITUDE: self.hass.config.longitude,
                            CONF_RADIUS_KM: 0,
                            CONF_STATIONS: [station_id],
                        },
                        keep_ids={station_id},
                    ),
                    entry,
                )

        options = sorted(
            (
                selector.SelectOptionDict(value=s["station_id"], label=_station_label(s))
                for s in all_stations.values()
            ),
            key=lambda o: o["label"].lower(),
        )
        current = (entry.data.get(CONF_STATIONS) or [None])[0] if entry else None
        if current is not None and current not in all_stations:
            current = None
        schema = _picker_schema(CONF_STATION, options, current)
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    # bathing sites within a radius ----------------------------------------

    async def async_step_bathing_radius(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """All official bathing sites within a radius around a location."""
        return await self._async_bathing_radius_form("bathing_radius", user_input, None)

    async def async_step_reconfigure_bathing_radius(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_bathing_radius_form(
            "reconfigure_bathing_radius", user_input, self._get_reconfigure_entry()
        )

    async def _async_bathing_radius_form(
        self, step_id: str, user_input: dict[str, Any] | None, entry: ConfigEntry | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            radius = user_input[CONF_RADIUS_KM]
            await self._async_claim(
                f"bathing_radius_{round(lat, 2)}_{round(lon, 2)}_{radius}", entry
            )

            sites = await self._async_site_list()
            site_ids: set[str] = set()
            if not sites:
                errors["base"] = "cannot_connect"
            else:
                site_ids = _bathing_site_ids_within(sites, lat, lon, radius)
                if not site_ids:
                    errors["base"] = "no_sites"

            if not errors:
                return self._finish(
                    _Prepared(
                        title=t("bathing_entry_title", self.hass, radius=round(radius)),
                        data={
                            CONF_MODE: MODE_BATHING_RADIUS,
                            CONF_LATITUDE: lat,
                            CONF_LONGITUDE: lon,
                            CONF_RADIUS_KM: radius,
                            CONF_BATHING_SITES: [],
                        },
                        keep_ids=site_ids,
                    ),
                    entry,
                )

        defaults: Mapping[str, Any] = entry.data if entry else {}
        schema = _radius_schema(
            {
                CONF_LATITUDE: defaults.get(CONF_LATITUDE, self.hass.config.latitude),
                CONF_LONGITUDE: defaults.get(CONF_LONGITUDE, self.hass.config.longitude),
                CONF_RADIUS_KM: defaults.get(CONF_RADIUS_KM) or DEFAULT_RADIUS_KM,
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    # favourite bathing site -----------------------------------------------

    async def async_step_bathing_favorite(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A single favourite bathing site, picked by name."""
        return await self._async_bathing_favorite_form("bathing_favorite", user_input, None)

    async def async_step_reconfigure_bathing_favorite(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_bathing_favorite_form(
            "reconfigure_bathing_favorite", user_input, self._get_reconfigure_entry()
        )

    async def _async_bathing_favorite_form(
        self, step_id: str, user_input: dict[str, Any] | None, entry: ConfigEntry | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        official_sites = await self._async_site_list()

        # The live lake stations are offered alongside the official sites.
        # They are merged in after the emptiness check below: an unreachable
        # LINDAS must not be masked by a picker that still lists two stations.
        all_sites = self._all_bathing_sites(official_sites)

        if user_input is not None:
            site_id = user_input[CONF_BATHING_SITE]
            await self._async_claim(f"bathing_{site_id}", entry)

            if not official_sites:
                errors["base"] = "cannot_connect"

            if not errors:
                site = all_sites.get(site_id) or {}
                return self._finish(
                    _Prepared(
                        title=site.get("name") or site_id,
                        data={
                            CONF_MODE: MODE_BATHING_FAVORITE,
                            CONF_LATITUDE: self.hass.config.latitude,
                            CONF_LONGITUDE: self.hass.config.longitude,
                            CONF_RADIUS_KM: 0,
                            CONF_BATHING_SITES: [site_id],
                        },
                        keep_ids={site_id},
                    ),
                    entry,
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
        current = (entry.data.get(CONF_BATHING_SITES) or [None])[0] if entry else None
        if current is not None and current not in all_sites:
            current = None
        schema = _picker_schema(CONF_BATHING_SITE, options, current)
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)
