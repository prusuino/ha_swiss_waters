"""Constants for the Swiss Waters (BAFU) integration."""
DOMAIN = "swiss_waters"

LINDAS_QUERY_URL = "https://lindas.admin.ch/query"
HYDRO_DIMENSION = "https://environment.ld.admin.ch/foen/hydro/dimension/"
HYDRO_STATION_SET = "https://environment.ld.admin.ch/foen/hydro/measuring-stations"

UPDATE_INTERVAL_MINUTES = 10

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS_KM = "radius_km"
CONF_STATIONS = "stations"

DEFAULT_RADIUS_KM = 50

ATTRIBUTION = "Data: Swiss Federal Office for the Environment FOEN (BAFU)"
