"""Runtime string localization (entity names, device info, danger-level scale).

Home Assistant's built-in translation system (strings.json / translations/*.json)
only covers config/options flow text. Entity names, device info and the
danger-level scale are set directly by this
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
    "bathing_model": {
        "de": "Badestelle",
        "en": "Bathing site",
        "fr": "Site de baignade",
        "it": "Zona di balneazione",
    },
    "sensor_bathing_quality": {
        "de": "Badewasserqualität (Saisonbeurteilung)",
        "en": "Bathing water quality (seasonal assessment)",
        "fr": "Qualité de l'eau de baignade (évaluation saisonnière)",
        "it": "Qualità dell'acqua di balneazione (valutazione stagionale)",
    },
    "sensor_bathing_last_sample": {
        "de": "Letzte Probenahme",
        "en": "Last sampling",
        "fr": "Dernier prélèvement",
        "it": "Ultimo campionamento",
    },
    "bathing_not_live": {
        "de": (
            "Kein Live-Wert: amtliche Beurteilung aus den Proben der Kantone "
            "(EU-Badegewässerrichtlinie, Bewertungszeitraum bis {date})"
        ),
        "en": (
            "Not a live reading: official assessment from the cantonal samples "
            "(EU Bathing Water Directive, assessment period up to {date})"
        ),
        "fr": (
            "Pas une mesure en direct : évaluation officielle à partir des "
            "prélèvements cantonaux (directive UE, période allant jusqu'au {date})"
        ),
        "it": (
            "Non è una misura in tempo reale: valutazione ufficiale dai campioni "
            "cantonali (direttiva UE, periodo di valutazione fino al {date})"
        ),
    },
    "sensor_bathing_temperature": {
        "de": "Badewassertemperatur",
        "en": "Bathing water temperature",
        "fr": "Température de l'eau de baignade",
        "it": "Temperatura dell'acqua di balneazione",
    },
    "mode_bathing_radius": {
        "de": "Badestellen im Umkreis",
        "en": "Bathing sites within a radius",
        "fr": "Sites de baignade dans un rayon",
        "it": "Zone di balneazione entro un raggio",
    },
    "mode_bathing_favorite": {
        "de": "Einzelne Badestelle favorisieren",
        "en": "Single favourite bathing site",
        "fr": "Site de baignade favori",
        "it": "Zona di balneazione preferita",
    },
    "bathing_entry_title": {
        "de": "Badestellen im Umkreis {radius} km",
        "en": "Bathing sites within {radius} km",
        "fr": "Sites de baignade dans un rayon de {radius} km",
        "it": "Zone di balneazione entro {radius} km",
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


# EU Bathing Water Directive (2006/7/EC) quality classes, as used by the FOEN.
BATHING_QUALITY_TEXT: dict[str, dict[str, str]] = {
    "de": {
        "excellent": "Ausgezeichnet",
        "good": "Gut",
        "sufficient": "Ausreichend",
        "poor": "Mangelhaft",
    },
    "en": {
        "excellent": "Excellent",
        "good": "Good",
        "sufficient": "Sufficient",
        "poor": "Poor",
    },
    "fr": {
        "excellent": "Excellente",
        "good": "Bonne",
        "sufficient": "Suffisante",
        "poor": "Insuffisante",
    },
    "it": {
        "excellent": "Eccellente",
        "good": "Buona",
        "sufficient": "Sufficiente",
        "poor": "Scarsa",
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


def bathing_quality_text(quality: str | None, hass: HomeAssistant) -> str | None:
    """Localized label of an EU bathing water quality class."""
    if not quality:
        return None
    return BATHING_QUALITY_TEXT[get_language(hass)].get(quality, quality)
