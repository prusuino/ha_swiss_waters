"""Geo-location entities for the monitoring stations — appear automatically on
the Home Assistant map card, labeled with the current water temperature via
the map card's label_mode: attribute option.

Unlike short-lived events (earthquakes), stations are long-lived and their
measured values change every 10 minutes, so the entities subscribe to the
coordinator and refresh their attributes on every update. Their availability
follows the coordinator as well: while the source is unreachable a marker is
unavailable, like the station's sensors, instead of keeping its last label.
"""
from __future__ import annotations

import logging

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTRIBUTION, DOMAIN
from .coordinator import SwissWatersCoordinator
from .device import station_device_info
from .localization import t

_LOGGER = logging.getLogger(__name__)
SOURCE = "swiss_waters"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    from . import is_bathing_entry

    if is_bathing_entry(entry):
        # Bathing sites are stationary devices without map markers for now.
        return

    coordinator: SwissWatersCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_entities: dict[str, SwissWatersStationEvent] = {}

    @callback
    def _sync_entities() -> None:
        stations = (coordinator.data or {}).get("stations", {})

        new_entities = [
            known_entities.setdefault(
                station_id, SwissWatersStationEvent(hass, coordinator, entry, station)
            )
            for station_id, station in stations.items()
            if station_id not in known_entities
        ]
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))
    _sync_entities()


class SwissWatersStationEvent(GeolocationEvent):
    """One map marker per monitoring station, values refreshed continuously,
    availability following the coordinator's last refresh."""

    _attr_should_poll = False
    _attr_source = SOURCE
    _attr_attribution = ATTRIBUTION
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_has_entity_name = False
    _attr_icon = "mdi:waves"
    # Hidden from Home Assistant's auto-generated default dashboard map (which
    # otherwise draws every geo_location entity in the system) — still shown
    # on a map card that references them by source, which does not go through
    # the visible-by-default list. This applies to entities registered for the
    # first time; whether an existing entity stays hidden is the user's
    # decision alone and is never rewritten from here.
    _attr_entity_registry_visible_default = False

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SwissWatersCoordinator,
        entry: ConfigEntry,
        station: dict,
    ) -> None:
        self._coordinator = coordinator
        self._station_id = station["station_id"]
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{self._station_id}"
        prefix = t("station_entity_prefix", hass)
        water = station.get("water_body")
        name = station.get("name") or self._station_id
        self._attr_name = f"{prefix} {water} – {name}" if water else f"{prefix} {name}"
        self._attr_latitude = station["latitude"]
        self._attr_longitude = station["longitude"]
        self._attr_distance = station["distance_km"]
        self._attr_device_info = station_device_info(hass, entry, station)

    def _station(self) -> dict:
        return (self._coordinator.data or {}).get("stations", {}).get(self._station_id, {})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # The coordinator notifies its listeners after every refresh that
        # changed something — new data, or the success flag flipping on a
        # failed refresh (which keeps the previous data) and again on
        # recovery. Writing state on each notification is what publishes
        # both the fresh label and the availability change.
        self.async_on_remove(self._coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        """Like the sensors: while the source is unreachable the marker is
        unavailable instead of showing its last known temperature on the map
        indefinitely. Not a CoordinatorEntity (the lifecycle is managed by the
        sync function), so this reads the coordinator directly; the listener
        registered in async_added_to_hass writes state whenever the flag
        flips, so the change reaches the state machine."""
        return self._coordinator.last_update_success and bool(self._station())

    @property
    def extra_state_attributes(self):
        station = self._station()
        temperature = station.get("temperature")
        return {
            "temperature": round(temperature, 1) if temperature is not None else None,
            "water_level": station.get("water_level"),
            "discharge": station.get("discharge"),
            "danger_level": station.get("danger_level"),
            "water_body": station.get("water_body"),
            "station_id": self._station_id,
            "measurement_time": station.get("measurement_time"),
        }
