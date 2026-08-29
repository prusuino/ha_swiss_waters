"""Per-station device info and entity id helpers shared by the platforms."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN
from .localization import t


def entry_suffix(entry: ConfigEntry) -> str:
    """Short per-entry discriminator for suggested entity ids.

    The last four characters of the config entry id, lower-cased. Appended to
    every suggested sensor id so a station that is part of two entries — a
    favorite that also lies inside a radius overview — gets two distinct ids
    instead of a numbered duplicate. Home Assistant applies a suggested id
    only when an entity is registered for the first time; entities that
    already exist keep theirs.
    """
    return entry.entry_id[-4:].lower()


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
        entry_type=DeviceEntryType.SERVICE,
    )


def bathing_device_info(hass: HomeAssistant, entry: ConfigEntry, site: dict) -> DeviceInfo:
    """One device per bathing site."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{site['site_id']}")},
        name=site.get("name") or site["site_id"],
        manufacturer=t("manufacturer", hass),
        model=t("bathing_model", hass),
        entry_type=DeviceEntryType.SERVICE,
    )
