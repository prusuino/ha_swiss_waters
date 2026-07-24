"""Automatic setup of the 'Swiss Waters' dashboard with a preconfigured map card.

Uses Home Assistant's internal Lovelace storage API (there is no publicly
documented integration API for this — verified against the current HA core
source). Purely additive and idempotent: once the dashboard is created, this
code never touches it again (not even across restarts) — the user's own later
changes are preserved.
"""
from __future__ import annotations

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

from .const import DOMAIN
from .localization import t

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "swiss-waters"
DASHBOARD_ICON = "mdi:waves"


async def async_ensure_dashboard(hass: HomeAssistant) -> None:
    """Create the waters dashboard if it doesn't exist yet (idempotent)."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.warning(
            "Lovelace data not available — could not automatically set up the "
            "Swiss Waters dashboard. Please create it manually."
        )
        return

    if DASHBOARD_URL_PATH in lovelace_data.dashboards:
        return  # already exists — don't overwrite (respect the user's own changes)

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
