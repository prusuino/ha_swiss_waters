"""Constants for the Swiss Waters (BAFU) integration."""
DOMAIN = "swiss_waters"

LINDAS_QUERY_URL = "https://lindas.admin.ch/query"
HYDRO_DIMENSION = "https://environment.ld.admin.ch/foen/hydro/dimension/"
HYDRO_STATION_SET = "https://environment.ld.admin.ch/foen/hydro/measuring-stations"

ENVIRONMENT_QUERY_URL = "https://environment.ld.admin.ch/query"
BATHING_CUBE_BASE = "https://environment.ld.admin.ch/foen/ubd01041prod"
BATHING_SITE_TERM_SET = "https://ld.admin.ch/dimension/bgdi/inlandwaters/bathingwater"

# Lake stations of the Zurich water police (city of Zurich open data, CC0).
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
