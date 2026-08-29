"""Constants for the Swiss Waters (BAFU) integration."""
from datetime import timedelta

DOMAIN = "swiss_waters"

LINDAS_QUERY_URL = "https://lindas.admin.ch/query"
HYDRO_DIMENSION = "https://environment.ld.admin.ch/foen/hydro/dimension/"
HYDRO_STATION_SET = "https://environment.ld.admin.ch/foen/hydro/measuring-stations"

ENVIRONMENT_QUERY_URL = "https://environment.ld.admin.ch/query"
BATHING_CUBE_BASE = "https://environment.ld.admin.ch/foen/ubd01041prod"
BATHING_SITE_TERM_SET = "https://ld.admin.ch/dimension/bgdi/inlandwaters/bathingwater"

# Lake stations of the Zurich water police (city of Zurich open data, CC0),
# read through the community-run API listed with the dataset — a third-party
# host, not a federal service.
BATHING_TEMP_URL = "https://tecdottir.metaodi.ch/measurements/{station}"
BATHING_TEMP_STATIONS = {
    "tiefenbrunnen": {
        "name": "Zürichsee Tiefenbrunnen",
        "latitude": 47.3479,
        "longitude": 8.5610,
    },
    "mythenquai": {
        "name": "Zürichsee Mythenquai",
        "latitude": 47.3567,
        "longitude": 8.5361,
    },
}

UPDATE_INTERVAL_MINUTES = 10
BATHING_UPDATE_INTERVAL_MINUTES = 30

# Freshness limits. A live reading older than the limit of its source is not
# presented as current: the sensors go unavailable and the map marker drops
# its measured values (the measurement time stays visible as an attribute).
# FOEN stations transmit every 10 minutes, a few only hourly, and the LINDAS
# pipeline may lag behind — six hours separate an outage from a slow station.
HYDRO_MAX_AGE = timedelta(hours=6)
# The Zurich lake stations measure every 10 minutes, but the community API
# the integration reads them from often serves its newest record hours
# late (a few hours is common, gaps of more than half a day have been
# seen). Six hours — the FOEN limit — keeps the temperature available
# through the usual lag; while the API lags beyond it, the sensor is
# unavailable rather than showing an old reading as live.
BATHING_TEMP_MAX_AGE = timedelta(hours=6)
# The bathing water quality is not a live reading. It is classified from the
# samples of the assessment period, which starts on 1 January of the year
# this many years back; a site without a sample in that period has no
# assessment, and its quality entities are unavailable.
BATHING_ASSESSMENT_YEARS = 4
# The published version of the bathing water cube is resolved again after
# this long (and whenever a query comes back empty), so a newly published
# dataset is picked up without a restart.
BATHING_CUBE_MAX_AGE = timedelta(hours=24)

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS_KM = "radius_km"
CONF_STATIONS = "stations"
CONF_MODE = "mode"
CONF_STATION = "station"
CONF_BATHING_SITES = "bathing_sites"
CONF_BATHING_SITE = "bathing_site"

MODE_RADIUS = "radius"
MODE_FAVORITE = "favorite"
MODE_BATHING_RADIUS = "bathing_radius"
MODE_BATHING_FAVORITE = "bathing_favorite"

DEFAULT_RADIUS_KM = 50

ATTRIBUTION = "Data: Swiss Federal Office for the Environment FOEN (BAFU)"
BATHING_ATTRIBUTION = (
    "Data: Swiss Federal Office for the Environment FOEN (BAFU) · "
    "Water police Zurich (City of Zurich, Open Data)"
)
