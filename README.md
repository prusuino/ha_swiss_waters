![Swiss Waters](readme_header.png)

# Swiss Waters (BAFU)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
<a href="https://www.buymeacoffee.com/prusuino"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" height="20"></a>

A Home Assistant custom integration for the official Swiss hydrological monitoring network: live **water temperature**, **water level**, **discharge**, and **flood danger levels** of Swiss rivers and lakes, sourced from the **Federal Office for the Environment (FOEN/BAFU)**.

Want to know whether the Aare is warm enough for a swim, or keep an eye on the flood danger level of the river next to your house — right on your Home Assistant dashboard? That's what this integration does.

## Background

The FOEN operates around 230 automatic monitoring stations on Swiss rivers and lakes and publishes their raw data — updated **every 10 minutes** — through the Swiss federal [LINDAS linked-data service](https://lindas.admin.ch), its official machine-readable channel. No API key, no registration.

This integration queries LINDAS for all stations within a configurable radius around a location and creates one device per station.

## What it provides

| Entity | Description |
|---|---|
| `sensor.swiss_waters_<station>_temperature` | Water temperature (°C). Only created for stations with a temperature probe (~84 stations). |
| `sensor.swiss_waters_<station>_water_level` | Water level (m a.s.l.). |
| `sensor.swiss_waters_<station>_discharge` | Discharge (m³/s). Rivers only — lakes don't report discharge. |
| `sensor.swiss_waters_<station>_danger_level` | Official flood danger level (1–5), with the localized FOEN danger scale as an attribute. |
| `geo_location.*` | One map marker per station, labeled with the current water temperature on the integration's map card. |

Each sensor carries the station ID, water body, measurement time, and distance from your configured location as attributes. Data is refreshed every 10 minutes — the same cadence as the source.

### Flood danger levels

| Level | Meaning |
|---|---|
| 1 | No or minor danger |
| 2 | Moderate danger |
| 3 | Considerable danger |
| 4 | High danger |
| 5 | Very high danger |

## Language

Entity names, device info, the auto-generated dashboard, and the config flow adapt automatically to your Home Assistant language setting — German, English, French, and Italian are supported, with English as the fallback.

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations → ⋮ → Custom repositories**, add this repository URL with category **Integration**.
2. Search for **"Swiss Waters"** and install.
3. Restart Home Assistant.

### Manual

1. Copy the `custom_components/swiss_waters` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **"Swiss Waters (BAFU)"**.
3. Latitude/longitude default to your Home Assistant home location. Set the radius (km) to your preference.
4. Done. Add the integration again for a different location or radius — each instance is independent.

### Automatic dashboard

On first setup, the integration automatically creates a **"Swiss Waters"** dashboard (shown in the sidebar, title localized to your HA language) with a full-screen native Home Assistant Map card, already configured to label each station's marker with its current water temperature. This only happens once: if you later customize or delete that dashboard yourself, the integration won't touch it again.

If you prefer to build your own map card instead:

```yaml
type: map
geo_location_sources:
  - source: swiss_waters
    label_mode: attribute
    attribute: temperature
```

## Notes

- Stations that newly fall within your radius (the network changes rarely) are picked up after a reload or restart of the integration.
- Not every station reports every measure: lake stations have no discharge, and only about a third of the network has temperature probes. Sensors are only created for measures a station actually reports.
- If LINDAS is unreachable, entities become unavailable rather than showing stale data.
- This integration is unofficial and not affiliated with, endorsed by, or supported by the FOEN. It only reads their published data via the official LINDAS service.

## Data source & license

This integration reads live data from the FOEN's hydrological monitoring network via the Swiss federal LINDAS linked-data service. The FOEN requires that the data source is always credited — every entity sets Home Assistant's `attribution` attribute accordingly ("Data: Swiss Federal Office for the Environment FOEN (BAFU)").

## Disclaimer

This integration is provided **as-is, without any warranty**. Data is retrieved from a third-party published source and may be inaccurate, delayed, incomplete, or unavailable. Do not rely on this integration for safety-critical decisions — for official flood warnings, always consult the authorities (e.g. [www.naturgefahren.ch](https://www.naturgefahren.ch)). The author(s) accept **no responsibility or liability** for any damage, loss, incorrect readings, or other issues arising from using this integration, whether it stops working, behaves unexpectedly, or never worked correctly for your setup in the first place.

## License

Source code: MIT — see [LICENSE](LICENSE).

## Related integrations

More Home Assistant integrations from the same author:

- [Swiss Public Alerts](https://github.com/prusuino/ha_swiss_public_alerts) — official Alertswiss warnings for your location
- [Swiss Earthquakes](https://github.com/prusuino/ha_swiss_earthquakes) — recent earthquakes from the Swiss Seismological Service on a map
- [Swiss Avalanche Bulletin](https://github.com/prusuino/ha_swiss_avalanche_bulletin) — SLF avalanche danger for your region
- [Swiss Electricity Price](https://github.com/prusuino/ha_swiss_electricity_price) — official ElCom electricity tariffs for your municipality
- [Swiss Solar Reference Price](https://github.com/prusuino/ha_swiss_solar_reference_price) — Swiss solar feed-in reference market price
- [Swiss Charging Stations](https://github.com/prusuino/ha_swiss_charging_stations) — real-time availability and prices of public EV charging stations in Switzerland
- [Swiss Public Transport](https://github.com/prusuino/ha_swiss_transport) — departure boards and connections for Swiss public transport
- [Swiss Parking](https://github.com/prusuino/ha_swiss_parking) — real-time parking availability in Swiss cities
- [Austrian Charging Stations](https://github.com/prusuino/ha_austrian_charging_stations) — real-time availability of public EV charging stations in Austria
- [Innoxel Master 3](https://github.com/prusuino/ha_innoxel_master3) — local control for INNOXEL building automation

## Support

If you find this integration useful, you can support its development:

<a href="https://www.buymeacoffee.com/prusuino"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" height="41"></a>
