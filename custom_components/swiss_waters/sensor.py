"""Sensors per monitoring station: water temperature, water level, discharge,
flood danger level — and per bathing site: quality class, last sampling, or
the live lake temperature.

Sensors are added as soon as their station or site shows up in the
coordinator data, and a measure a station starts reporting later (e.g. a
temperature probe that was silent at setup) gets its sensor on that update —
no reload needed. A measure a station never reports gets no entity.

Sensors are never removed from here on purpose: the network changes rarely,
a station that drops out of the feed is usually back after maintenance, and
its sensors read unavailable meanwhile. Removing a station that is gone for
good is left to the user (delete the device), so nothing the user customised
is thrown away by an automatic clean-up. The geo_location platform follows
the same rule.

Suggested entity ids end in a per-entry discriminator (device.entry_suffix)
so a station that is part of two entries gets distinct ids. Home Assistant
applies a suggested id only when it registers an entity for the first time;
existing entities keep the id they have.
"""
from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .bathing import QUALITY_CLASSES
from .const import ATTRIBUTION, BATHING_ATTRIBUTION, DOMAIN
from .coordinator import SwissWatersCoordinator
from .device import bathing_device_info, entry_suffix, station_device_info
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


def _new_station_entities(
    hass: HomeAssistant,
    coordinator,
    entry: ConfigEntry,
    known: set[tuple[str, str]],
) -> list[SensorEntity]:
    """Sensors for station measures not yet known; marks them as known."""
    entities: list[SensorEntity] = []
    for station in (coordinator.data or {}).get("stations", {}).values():
        for measure in _MEASURES:
            data_key = measure[0]
            key = (station["station_id"], data_key)
            if key in known:
                continue
            if data_key != "danger_level" and station.get(data_key) is None:
                continue
            known.add(key)
            entities.append(SwissWatersSensor(hass, coordinator, entry, station, *measure))
    return entities


def _new_bathing_entities(
    hass: HomeAssistant,
    coordinator,
    entry: ConfigEntry,
    known: set[tuple[str, str]],
) -> list[SensorEntity]:
    """Sensors for bathing sites not yet known; marks them as known."""
    entities: list[SensorEntity] = []
    for site in (coordinator.data or {}).get("sites", {}).values():
        if site.get("water_temperature") is not None:
            wanted = [("water_temperature", SwissBathingTemperatureSensor)]
        else:
            wanted = [
                ("quality", SwissBathingQualitySensor),
                ("last_sample", SwissBathingSampleDateSensor),
            ]
        for suffix, entity_class in wanted:
            key = (site["site_id"], suffix)
            if key in known:
                continue
            known.add(key)
            entities.append(entity_class(hass, coordinator, entry, site))
    return entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    from . import is_bathing_entry

    coordinator = hass.data[DOMAIN][entry.entry_id]
    builder = _new_bathing_entities if is_bathing_entry(entry) else _new_station_entities
    known: set[tuple[str, str]] = set()

    @callback
    def _sync_entities() -> None:
        new_entities = builder(hass, coordinator, entry, known)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))
    _sync_entities()


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
        self.entity_id = (
            f"sensor.swiss_waters_{self._station_id}_{data_key}_{entry_suffix(entry)}"
        )
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
        """Unavailable while the source is unreachable, while the station is
        missing from the feed, and once its latest reading is older than the
        freshness limit (HYDRO_MAX_AGE) — a stale value is not a current one."""
        station = self._station()
        return super().available and bool(station) and station.get("fresh", False)

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
    assessment by the cantons, not a live reading. Unavailable while the
    site has no sample within the assessment period: no samples, no
    assessment.
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
        self.entity_id = (
            f"sensor.swiss_waters_bathing_{slugify(self._site_id)}_quality_{entry_suffix(entry)}"
        )
        self._attr_device_info = bathing_device_info(hass, entry, site)
        self._attr_options = list(QUALITY_CLASSES)

    def _site(self) -> dict:
        return (self.coordinator.data or {}).get("sites", {}).get(self._site_id, {})

    @property
    def available(self) -> bool:
        site = self._site()
        return super().available and bool(site) and site.get("fresh", False)

    @property
    def native_value(self):
        return self._site().get("quality")

    @property
    def extra_state_attributes(self):
        site = self._site()
        values = site.get("last_values") or {}
        sampled = site.get("last_sample_date")
        return {
            "site_id": self._site_id,
            "quality_text": bathing_quality_text(site.get("quality"), self._hass_ref),
            "note": t("bathing_not_live", self._hass_ref, date=sampled or "?"),
            "live": False,
            "season": site.get("season"),
            "last_sample_date": site.get("last_sample_date"),
            "e_coli": values.get("E.coli"),
            "enterococci": values.get("Enterokokken"),
            "sample_count": site.get("sample_count"),
            "canton": site.get("canton"),
            "distance_km": site.get("distance_km"),
        }


class SwissBathingTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Live bathing water temperature of a lake station.

    Unavailable once the station's latest reading is older than
    BATHING_TEMP_MAX_AGE, so a station that went silent is not shown with a
    stale temperature as if it were live.
    """

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
        self.entity_id = (
            f"sensor.swiss_waters_bathing_{slugify(self._site_id)}_temperature_{entry_suffix(entry)}"
        )
        self._attr_device_info = bathing_device_info(hass, entry, site)

    def _site(self) -> dict:
        return (self.coordinator.data or {}).get("sites", {}).get(self._site_id, {})

    @property
    def available(self) -> bool:
        site = self._site()
        return super().available and bool(site) and site.get("fresh", False)

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


class SwissBathingSampleDateSensor(CoordinatorEntity, SensorEntity):
    """Date of the most recent sample behind the quality assessment.

    Exists so the age of the assessment is visible at a glance instead of
    being buried in the attributes of the quality sensor. Unavailable, like
    the quality sensor, while the site has no sample within the assessment
    period.
    """

    _attr_has_entity_name = True
    _attr_attribution = BATHING_ATTRIBUTION
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, hass: HomeAssistant, coordinator, entry: ConfigEntry, site: dict) -> None:
        super().__init__(coordinator)
        self._hass_ref = hass
        self._site_id = site["site_id"]
        self._attr_name = t("sensor_bathing_last_sample", hass)
        self._attr_unique_id = f"{entry.entry_id}_{self._site_id}_last_sample"
        self.entity_id = (
            f"sensor.swiss_waters_bathing_{slugify(self._site_id)}_last_sample_{entry_suffix(entry)}"
        )
        self._attr_device_info = bathing_device_info(hass, entry, site)

    def _site(self) -> dict:
        return (self.coordinator.data or {}).get("sites", {}).get(self._site_id, {})

    @property
    def available(self) -> bool:
        site = self._site()
        return super().available and bool(site) and site.get("fresh", False)

    @property
    def native_value(self):
        raw = self._site().get("last_sample_date")
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    @property
    def extra_state_attributes(self):
        site = self._site()
        return {
            "site_id": self._site_id,
            "season": site.get("season"),
            "sample_count": site.get("sample_count"),
            "live": False,
        }
