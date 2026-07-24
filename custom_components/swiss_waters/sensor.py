"""Sensors per monitoring station: water temperature, water level, discharge,
flood danger level.

Sensors are created from the station snapshot at setup time; a measure a
station does not report (e.g. no temperature probe) gets no entity. Stations
appearing later within the radius are picked up on the next reload/restart.
"""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import SwissWatersCoordinator
from .device import station_device_info
from .localization import danger_scale, t

# (data_key, name_key, device_class, state_class, unit, icon, precision)
_MEASURES = [
    ("temperature", "sensor_temperature", SensorDeviceClass.TEMPERATURE,
     SensorStateClass.MEASUREMENT, UnitOfTemperature.CELSIUS, "mdi:coolant-temperature", 1),
    ("water_level", "sensor_water_level", None,
     SensorStateClass.MEASUREMENT, "m", "mdi:waves-arrow-up", 2),
    ("discharge", "sensor_discharge", None,
     SensorStateClass.MEASUREMENT, "m³/s", "mdi:water-pump", 1),
    ("danger_level", "sensor_danger_level", None,
     None, None, "mdi:home-flood", 0),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SwissWatersCoordinator = hass.data[DOMAIN][entry.entry_id]
    stations = (coordinator.data or {}).get("stations", {})

    entities: list[SwissWatersSensor] = []
    for station in stations.values():
        for measure in _MEASURES:
            data_key = measure[0]
            if data_key != "danger_level" and station.get(data_key) is None:
                continue
            entities.append(SwissWatersSensor(hass, coordinator, entry, station, *measure))
    async_add_entities(entities)


class SwissWatersSensor(CoordinatorEntity[SwissWatersCoordinator], SensorEntity):
    # Entity name holds only the measure ("Water temperature"); Home Assistant
    # prepends the station device name ("Aare – Murgenthal") automatically.
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: SwissWatersCoordinator,
        entry: ConfigEntry,
        station: dict,
        data_key: str,
        name_key: str,
        device_class,
        state_class,
        unit,
        icon: str,
        precision: int,
    ) -> None:
        super().__init__(coordinator)
        self._hass_ref = hass
        self._station_id = station["station_id"]
        self._data_key = data_key
        self._attr_name = t(name_key, hass)
        self._attr_unique_id = f"{entry.entry_id}_{self._station_id}_{data_key}"
        self.entity_id = f"sensor.swiss_waters_{self._station_id}_{data_key}"
        self._attr_device_info = station_device_info(hass, entry, station)
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_suggested_display_precision = precision

    def _station(self) -> dict:
        return (self.coordinator.data or {}).get("stations", {}).get(self._station_id, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self._station())

    @property
    def native_value(self):
        return self._station().get(self._data_key)

    @property
    def extra_state_attributes(self):
        station = self._station()
        attrs = {
            "station_id": self._station_id,
            "water_body": station.get("water_body"),
            "measurement_time": station.get("measurement_time"),
            "distance_km": station.get("distance_km"),
        }
        if self._data_key == "danger_level":
            attrs["danger_scale"] = danger_scale(self._hass_ref)
        return attrs
