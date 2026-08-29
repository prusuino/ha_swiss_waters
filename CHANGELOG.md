# Changelog

## 1.4.1 — 2026-08-29

- Updated the bundled dashboard-strategy core to 1.1.1: `map: false` now also removes a map section inside a view, `max_columns` is honoured in the view-strategy flavour, and a view's header is kept when the strategy fills a single view. No change to the integration itself.

## 1.4.0 — 2026-08-29

The dashboard that 1.3.0 removed has a replacement: a **dashboard strategy**. A strategy is a recipe Home Assistant renders in the browser at display time — it stores nothing, overwrites nothing, and reflects your current setup on every page load. Add a station or a bathing site and its section appears; delete an entry and it is gone, with no stale card left behind. It is entirely optional, and existing dashboards are not touched.

- **New: dashboard strategy `custom:swiss-waters`.** It renders a full-screen **Map** of the monitoring stations (markers labeled with the water temperature; the view is left out when no station markers exist, so a bathing-only setup gets no empty map), a **Stations** view with one section per station (water temperature, water level, discharge and flood danger level as tiles — only the measures the station reports), and a **Bathing sites** view with one section per site (quality class and last sampling, or the live water temperature of the Lake Zurich stations). It also appears under **Settings → Dashboards → + Add dashboard**, can fill a single view of a dashboard you already have, and honours `title`, `max_columns` and `map: false` as options. Setup is in the README; in short, a new dashboard with:

  ```yaml
  strategy:
    type: custom:swiss-waters
  views: []
  ```

- **One-time step: register the resource.** The integration serves the file at `/swiss_waters_files/swiss-waters-dashboard.js` but does not add it to your Lovelace resources — the resource list is part of your dashboard configuration, and the integration stays out of it. Add it once under **Settings → Dashboards → ⋮ → Resources** with type *JavaScript module*, then reload the page.
- Changed: the minimum Home Assistant version is now **2025.4.0** (previously 2024.1.0). Serving the file uses the static-path API from 2024.7, and the generated dashboard relies on the sections view with heading cards and `grid_options` (2024.10/2024.11) and on the map card's attribute labels for geo-location sources (2025.4) — the same feature the README's manual map card has always used.
- Added: `http` is declared as a dependency in the manifest, so the static path is registered when the integration loads.
- Fixed: the map markers now become **unavailable** while the FOEN data source is unreachable — exactly like the station sensors — instead of keeping their last water temperature on the map label indefinitely. They come back by themselves with the next successful update.
- Nothing to do on update: no entity id, name or hidden/visible setting changes. The map markers have carried the config entry in their unique id since 1.0.0, so a favorite station that also lies inside a radius overview keeps its own marker in each entry.
- README: the installation section now describes the HACS listing (search for "Swiss Waters" in HACS, or use the *Open in HACS* button) instead of the custom-repository route, and a new section explains how to address the map markers — their entity ids follow the localized entity name, so cards and templates should select them by `source: swiss_waters` instead.

## 1.3.0 — 2026-08-29

**Breaking:** the integration no longer creates a "Swiss Waters" dashboard for you, and no longer adds a "Bathing sites" view to it. It wrote directly into Home Assistant's internal Lovelace storage, which could silently discard the entry again, recreated the dashboard even after a user had deliberately deleted it, and appended the bathing view to a dashboard the user may have customised. Dashboards are now left entirely to the user. An existing dashboard from an earlier version is kept and kept working — nothing is deleted on update. The README explains how to add the built-in Map card and a tile per bathing site; the map card configuration is unchanged, so an existing dashboard needs no adjustment.

- Entities that a user made visible by hand are no longer hidden again on every restart. New station entities are still hidden by default so they don't flood the auto-generated overview map; existing ones are no longer rewritten.
- A failure while fetching the live lake temperatures is now reported like any other data problem (entities unavailable) instead of surfacing as an unexpected error with a traceback.

## 1.2.0 — 2026-07-26

Bathing sites: bathing water quality and live lake bathing temperatures.

- **Two new setup modes**: *bathing sites within a radius* and *a single favourite bathing site*, alongside the existing monitoring-station modes
- One device per official bathing site with its **bathing water quality** class (excellent / good / sufficient / poor) per the EU Bathing Water Directive, computed from the cantonal E. coli and intestinal enterococci samples of the four-season assessment period published by the FOEN
- The assessment is explicitly **not a live reading**: the entity is named "Bathing water quality (seasonal assessment)", carries a plain-text note and `live: false`, and every site gets a dedicated **"Last sampling"** date sensor
- **Live bathing water temperature** of the two Zurich lake stations Tiefenbrunnen and Mythenquai (water police Zurich, city of Zurich open data), updated every 30 minutes
- New "Bathing sites" view on the automatically created dashboard
- Localised quality labels and setup texts in German, English, French and Italian

## 1.1.0 — 2026-07-25

- **Setup wizard with two modes**: choose between a *radius overview* (all stations around a location, as before) and *favoriting a single station* picked by name from a searchable dropdown (e.g. "Aare – Bern, Schönau"). Each favorite is its own entry — add the integration again for further favorites, independent of any radius. Radius overviews and favorites combine freely. Existing radius-based entries keep working unchanged.

## 1.0.0 — 2026-07-24

Initial public release.

- One device per official FOEN/BAFU hydrological monitoring station within the configured radius, with sensors for **water temperature**, **water level**, **discharge**, and the official **flood danger level (1–5)** — each station only gets the sensors it actually reports
- `geo_location` entity per station: shown on the integration's map card, labeled with the current water temperature
- Automatic dashboard setup with a native Map card
- Data from the FOEN's official LINDAS linked-data service (no API key required), refreshed every 10 minutes — matching the source's own update cadence
- Multi-language support (German, English, French, Italian) for entity names, device info, the dashboard, and the danger-level scale, based on the Home Assistant language setting
- Config flow: location (defaults to Home Assistant's home location) and radius; supports multiple locations/radii via multiple config entries
- All entities carry the FOEN source attribution
