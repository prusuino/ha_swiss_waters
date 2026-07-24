# Changelog

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
