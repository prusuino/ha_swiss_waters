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

from homeassistant.util import slugify

from .bathing import QUALITY_CLASSES
from .const import ATTRIBUTION, BATHING_ATTRIBUTION, DOMAIN
from .coordinator import SwissWatersCoordinator
from .device import bathing_device_info, station_device_info
from .localization import bathing_quality_text, danger_scale, t

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
    from . import is_bathing_entry

    coordinator = hass.data[DOMAIN][entry.entry_id]

    if is_bathing_entry(entry):
        entities: list[SensorEntity] = []
        for site in (coordinator.data or {}).get("sites", {}).values():
            if site.get("water_temperature") is not None:
                entities.append(
                    SwissBathingTemperatureSensor(hass, coordinator, entry, site)
                )
            else:
                entities.append(SwissBathingQualitySensor(hass, coordinator, entry, site))
        async_add_entities(entities)
        return

    stations = (coordinator.data or {}).get("stations", {})
    entities = []
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


class SwissBathingQualitySensor(CoordinatorEntity, SensorEntity):
    """Bathing water quality class of one official bathing site.

    The state is the EU Bathing Water Directive class of the most recently
    reported season (excellent / good / sufficient / poor) — a seasonal
    assessment by the cantons, not a live reading.
    """

    _attr_has_entity_name = True
    _attr_attribution = BATHING_ATTRIBUTION
    _attr_icon = "mdi:swim"
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, hass: HomeAssistant, coordinator, entry: ConfigEntry, site: dict) -> None:
        super().__init__(coordinator)
        self._hass_ref = hass
        self._site_id = site["site_id"]
        self._attr_name = t("sensor_bathing_quality", hass)
        self._attr_unique_id = f"{entry.entry_id}_{self._site_id}_quality"
        self.entity_id = f"sensor.swiss_waters_bathing_{slugify(self._site_id)}_quality"
        self._attr_device_info = bathing_device_info(hass, entry, site)
        self._attr_options = list(QUALITY_CLASSES)

    def _site(self) -> dict:
        return (self.coordinator.data or {}).get("sites", {}).get(self._site_id, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self._site())

    @property
    def native_value(self):
        return self._site().get("quality")

    @property
    def extra_state_attributes(self):
        site = self._site()
        values = site.get("last_values") or {}
        return {
            "site_id": self._site_id,
            "quality_text": bathing_quality_text(site.get("quality"), self._hass_ref),
            "season": site.get("season"),
            "last_sample_date": site.get("last_sample_date"),
            "e_coli": values.get("E.coli"),
            "enterococci": values.get("Enterokokken"),
            "sample_count": site.get("sample_count"),
            "canton": site.get("canton"),
            "distance_km": site.get("distance_km"),
        }


class SwissBathingTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Live bathing water temperature of a lake station."""

    _attr_has_entity_name = True
    _attr_attribution = BATHING_ATTRIBUTION
    _attr_icon = "mdi:pool-thermometer"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, hass: HomeAssistant, coordinator, entry: ConfigEntry, site: dict) -> None:
        super().__init__(coordinator)
        self._site_id = site["site_id"]
        self._attr_name = t("sensor_bathing_temperature", hass)
        self._attr_unique_id = f"{entry.entry_id}_{self._site_id}_water_temperature"
        self.entity_id = f"sensor.swiss_waters_bathing_{slugify(self._site_id)}_temperature"
        self._attr_device_info = bathing_device_info(hass, entry, site)

    def _site(self) -> dict:
        return (self.coordinator.data or {}).get("sites", {}).get(self._site_id, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self._site())

    @property
    def native_value(self):
        return self._site().get("water_temperature")

    @property
    def extra_state_attributes(self):
        site = self._site()
        return {
            "site_id": self._site_id,
            "air_temperature": site.get("air_temperature"),
            "measurement_time": site.get("measurement_time"),
            "distance_km": site.get("distance_km"),
        }
