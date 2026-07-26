"""Automatic setup of the 'Swiss Waters' dashboard with a preconfigured map card.

Uses Home Assistant's internal Lovelace storage API (there is no publicly
documented integration API for this — verified against the current HA core
source). Purely additive and idempotent: once the dashboard is created, this
code never touches it again (not even across restarts) — the user's own later
changes are preserved.
"""
from __future__ import annotations

import json
import logging

from homeassistant.components import frontend
from homeassistant.components.lovelace import dashboard as ll_dashboard
from homeassistant.components.lovelace.const import (
    CONF_ALLOW_SINGLE_WORD,
    CONF_ICON,
    CONF_REQUIRE_ADMIN,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    CONF_URL_PATH,
    DOMAIN as LOVELACE_DOMAIN,
    LOVELACE_DATA,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol

from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN
from .localization import t

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "swiss-waters"
DASHBOARD_ICON = "mdi:waves"


async def async_ensure_dashboard(hass: HomeAssistant, entry=None) -> None:
    """Create the waters dashboard if it doesn't exist yet (idempotent)."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.warning(
            "Lovelace data not available — could not automatically set up the "
            "Swiss Waters dashboard. Please create it manually."
        )
        return

    if DASHBOARD_URL_PATH in lovelace_data.dashboards:
        # Never overwrite the user's own changes; only append the bathing view
        # once, when a bathing entry is set up after the dashboard was created.
        await _async_ensure_bathing_view(hass, entry, lovelace_data)
        return

    dashboard_title = t("dashboard_title", hass)

    dashboards_collection = ll_dashboard.DashboardsCollection(hass)
    await dashboards_collection.async_load()

    try:
        item = await dashboards_collection.async_create_item(
            {
                CONF_URL_PATH: DASHBOARD_URL_PATH,
                CONF_TITLE: dashboard_title,
                CONF_ICON: DASHBOARD_ICON,
                CONF_SHOW_IN_SIDEBAR: True,
                CONF_REQUIRE_ADMIN: False,
                CONF_ALLOW_SINGLE_WORD: True,
            }
        )
    except (HomeAssistantError, vol.Invalid) as err:
        _LOGGER.warning("Could not create the Swiss Waters dashboard: %s", err)
        return

    view_config = {
        "views": [
            {
                "title": dashboard_title,
                "path": "waters",
                "type": "panel",
                "cards": [
                    {
                        "type": "map",
                        "title": t("map_card_title", hass),
                        "geo_location_sources": [
                            {
                                "source": DOMAIN,
                                "label_mode": "attribute",
                                "attribute": "temperature",
                            }
                        ],
                        "default_zoom": 9,
                    }
                ],
            }
        ]
    }

    storage = ll_dashboard.LovelaceStorage(hass, item)
    lovelace_data.dashboards[DASHBOARD_URL_PATH] = storage
    await storage.async_save(view_config)
    await _async_ensure_bathing_view(hass, entry, lovelace_data)

    frontend.async_register_built_in_panel(
        hass,
        LOVELACE_DOMAIN,
        frontend_url_path=DASHBOARD_URL_PATH,
        require_admin=False,
        show_in_sidebar=True,
        sidebar_title=dashboard_title,
        sidebar_icon=DASHBOARD_ICON,
        config={"mode": "storage"},
        update=False,
    )

    _LOGGER.info("Swiss Waters dashboard automatically set up at /%s", DASHBOARD_URL_PATH)


def _bathing_cards(hass: HomeAssistant, sites: list[tuple[str, str, str]]) -> list[dict]:
    """Heading plus tiles per bathing site."""
    cards: list[dict] = []
    for name, primary, secondary in sites:
        cards.append({"type": "heading", "heading": name, "icon": "mdi:swim"})
        cards.append({"type": "tile", "entity": primary, "grid_options": {"columns": 6}})
        if secondary:
            cards.append(
                {"type": "tile", "entity": secondary, "grid_options": {"columns": 6}}
            )
    return cards


def _collect_bathing_sites(hass: HomeAssistant, entry) -> list[tuple[str, str, str]]:
    """Resolve (device name, primary entity, secondary entity) per bathing site."""
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    by_site: dict[str, dict[str, str]] = {}
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        unique_id = reg_entry.unique_id or ""
        if not unique_id.startswith(prefix):
            continue
        rest = unique_id[len(prefix) :]
        for suffix in ("_quality", "_water_temperature", "_last_sample"):
            if rest.endswith(suffix):
                by_site.setdefault(rest[: -len(suffix)], {})[suffix[1:]] = reg_entry.entity_id
                break

    device_registry = dr.async_get(hass)
    sites: list[tuple[str, str, str]] = []
    for site_id, found in sorted(by_site.items()):
        primary = found.get("quality") or found.get("water_temperature")
        if not primary:
            continue
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, f"{entry.entry_id}_{site_id}")}
        )
        name = (device.name if device else None) or site_id
        secondary = found.get("last_sample", "") if found.get("quality") else ""
        sites.append((name, primary, secondary))
    return sites


async def _async_ensure_bathing_view(hass: HomeAssistant, entry, lovelace_data) -> None:
    """Add this bathing entry's sites to the dashboard exactly once."""
    if entry is None:
        return
    from . import is_bathing_entry

    if not is_bathing_entry(entry):
        return

    sites = _collect_bathing_sites(hass, entry)
    if not sites:
        return

    storage = lovelace_data.dashboards.get(DASHBOARD_URL_PATH)
    if storage is None:
        return
    try:
        config = await storage.async_load(False)
    except HomeAssistantError as err:
        _LOGGER.debug("Could not load the waters dashboard config: %s", err)
        return
    if not isinstance(config, dict):
        return
    if sites[0][1] in json.dumps(config):
        return  # already present (added earlier or placed by the user)

    views = config.setdefault("views", [])
    cards = _bathing_cards(hass, sites)
    existing = next((v for v in views if v.get("path") == "bathing"), None)
    if existing is None:
        views.append(
            {
                "title": t("bathing_view_title", hass),
                "path": "bathing",
                "type": "sections",
                "icon": "mdi:swim",
                "max_columns": 2,
                "sections": [{"type": "grid", "column_span": 2, "cards": cards}],
            }
        )
    else:
        sections = existing.setdefault(
            "sections", [{"type": "grid", "column_span": 2, "cards": []}]
        )
        sections[0].setdefault("cards", []).extend(cards)

    try:
        await storage.async_save(config)
    except HomeAssistantError as err:
        _LOGGER.warning("Could not add the bathing view to the dashboard: %s", err)
        return
    _LOGGER.info("Added bathing sites to the Swiss Waters dashboard")
