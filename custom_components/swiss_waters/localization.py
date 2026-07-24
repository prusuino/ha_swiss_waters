"""Runtime string localization (entity names, device info, dashboard content).

Home Assistant's built-in translation system (strings.json / translations/*.json)
only covers config/options flow text. Entity names, device info, the
auto-generated dashboard, and the danger-level scale are set directly by this
integration's Python code and are not covered by that mechanism, so we do our
own minimal lookup here, keyed by hass.config.language. Falls back to English
for any language we don't have strings for.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant

SUPPORTED_LANGUAGES = ("de", "en", "fr", "it")

STRINGS: dict[str, dict[str, str]] = {
    "entry_title": {
        "de": "Gewässer Schweiz (Umkreis {radius} km)",
        "en": "Swiss Waters (Radius {radius} km)",
        "fr": "Eaux suisses (Rayon {radius} km)",
        "it": "Acque svizzere (Raggio {radius} km)",
    },
    "mode_radius": {
        "de": "Umkreis-Übersicht (alle Stationen in einem Umkreis)",
        "en": "Radius overview (all stations within a radius)",
        "fr": "Aperçu par rayon (toutes les stations dans un rayon)",
        "it": "Panoramica per raggio (tutte le stazioni in un raggio)",
    },
    "mode_favorite": {
        "de": "Einzelne Station favorisieren",
        "en": "Favorite a single station",
        "fr": "Ajouter une station favorite",
        "it": "Aggiungere una stazione preferita",
    },
    "manufacturer": {
        "de": "Bundesamt für Umwelt BAFU",
        "en": "Federal Office for the Environment FOEN",
        "fr": "Office fédéral de l'environnement OFEV",
        "it": "Ufficio federale dell'ambiente UFAM",
    },
    "model": {
        "de": "Hydrologische Messstation",
        "en": "Hydrological monitoring station",
        "fr": "Station de mesure hydrologique",
        "it": "Stazione di misurazione idrologica",
    },
    "sensor_temperature": {
        "de": "Wassertemperatur",
        "en": "Water temperature",
        "fr": "Température de l'eau",
        "it": "Temperatura dell'acqua",
    },
    "sensor_water_level": {
        "de": "Pegelstand",
        "en": "Water level",
        "fr": "Niveau d'eau",
        "it": "Livello dell'acqua",
    },
    "sensor_discharge": {
        "de": "Abfluss",
        "en": "Discharge",
        "fr": "Débit",
        "it": "Portata",
    },
    "sensor_danger_level": {
        "de": "Hochwasser-Gefahrenstufe",
        "en": "Flood danger level",
        "fr": "Niveau de danger de crue",
        "it": "Livello di pericolo di piena",
    },
    "station_entity_prefix": {
        "de": "Gewässer",
        "en": "Water",
        "fr": "Eaux",
        "it": "Acque",
    },
    "dashboard_title": {
        "de": "Gewässer Schweiz",
        "en": "Swiss Waters",
        "fr": "Eaux suisses",
        "it": "Acque svizzere",
    },
    "map_card_title": {
        "de": "BAFU Messstationen (Beschriftung: Wassertemperatur °C)",
        "en": "FOEN monitoring stations (label: water temperature °C)",
        "fr": "Stations OFEV (étiquette : température de l'eau °C)",
        "it": "Stazioni UFAM (etichetta: temperatura dell'acqua °C)",
    },
}

# Official FOEN flood danger levels (1-5), see
# https://www.hydrodaten.admin.ch -> danger levels. Informational only.
DANGER_SCALE: dict[str, dict[str, str]] = {
    "de": {
        "1": "Keine oder geringe Gefahr",
        "2": "Mässige Gefahr",
        "3": "Erhebliche Gefahr",
        "4": "Grosse Gefahr",
        "5": "Sehr grosse Gefahr",
    },
    "en": {
        "1": "No or minor danger",
        "2": "Moderate danger",
        "3": "Considerable danger",
        "4": "High danger",
        "5": "Very high danger",
    },
    "fr": {
        "1": "Danger nul ou faible",
        "2": "Danger limité",
        "3": "Danger marqué",
        "4": "Danger fort",
        "5": "Danger très fort",
    },
    "it": {
        "1": "Pericolo nullo o debole",
        "2": "Pericolo moderato",
        "3": "Pericolo marcato",
        "4": "Pericolo forte",
        "5": "Pericolo molto forte",
    },
}


def get_language(hass: HomeAssistant) -> str:
    lang = (hass.config.language or "en").lower().split("-")[0]
    return lang if lang in SUPPORTED_LANGUAGES else "en"


def t(key: str, hass: HomeAssistant, **kwargs) -> str:
    """Look up a localized string by key, formatted with kwargs."""
    lang = get_language(hass)
    template = STRINGS.get(key, {}).get(lang) or STRINGS.get(key, {}).get("en") or key
    return template.format(**kwargs) if kwargs else template


def danger_scale(hass: HomeAssistant) -> dict[str, str]:
    """Return the flood danger level scale for the current language."""
    lang = get_language(hass)
    return DANGER_SCALE.get(lang, DANGER_SCALE["en"])
