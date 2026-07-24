"""Per-station device info shared by the sensor and geo_location platforms."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .localization import t


def station_device_info(hass: HomeAssistant, entry: ConfigEntry, station: dict) -> DeviceInfo:
    """One device per monitoring station, named '<water body> – <station name>'."""
    water = station.get("water_body")
    name = station.get("name") or station["station_id"]
    device_name = f"{water} – {name}" if water else name
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{station['station_id']}")},
        name=device_name,
        manufacturer=t("manufacturer", hass),
        model=t("model", hass),
        entry_type="service",
    )
