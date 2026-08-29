# Changelog

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
