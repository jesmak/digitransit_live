"""Constants for the Digitransit Live integration."""

from typing import Final

DOMAIN: Final = "digitransit_live"

ATTRIBUTION: Final = "Digitransit, CC BY 4.0"

# Version of the Map Feed format the sensors write (docs/map-feed-format.md in ha-map-card-plugin-map-feed).
MAP_FEED_VERSION: Final = 1

# Languages for the texts the integration writes into feeds. Each needs a texts/<code>.json file.
LANGUAGES: Final = ["fi", "sv", "en"]

MQTT_HOST: Final = "mqtt.digitransit.fi"
MQTT_PORT: Final = 8883

# Config entry
CONF_LANGUAGE: Final = "language"
# A Digitransit subscription key. Only stop departures need one.
CONF_API_KEY: Final = "api_key"

# Config subentry types
SUBENTRY_VEHICLES: Final = "vehicles"
SUBENTRY_DEPARTURES: Final = "departures"

# Feed settings (config subentry data)
CONF_FEED: Final = "feed"
CONF_LINES: Final = "lines"
CONF_USE_AREA: Final = "use_area"
CONF_AREA: Final = "area"
CONF_MAX_AGE_MINUTES: Final = "max_age_minutes"
CONF_UPDATE_SECONDS: Final = "update_seconds"

# Stop departure settings (config subentry data); lines and the update interval use the keys above.
CONF_ROUTER: Final = "router"
CONF_STOP: Final = "stop"
CONF_DEPARTURES: Final = "departures"
# Used only while adding a stop.
CONF_REGION: Final = "region"
CONF_LOCATION: Final = "location"

# Digitransit's routing API. The "finland" router knows every region, with the same real-time estimates as the
# regional routers (hsl, waltti, varely), so new stops use it.
ROUTING_API: Final = "https://api.digitransit.fi/routing/v2/{router}/gtfs/v1"
ROUTER: Final = "finland"
# Stops listed near the pin when adding a stop.
STOP_CHOICES: Final = 10
DEFAULT_DEPARTURES: Final = 5
MAX_DEPARTURES: Final = 20
# Timetables and delay estimates change slowly; polling more often only spends the API quota.
MIN_DEPARTURE_UPDATE_SECONDS: Final = 30
DEFAULT_DEPARTURE_UPDATE_SECONDS: Final = 60

# Vehicles report about once a second; the sensor is rewritten at most this often.
MIN_UPDATE_SECONDS: Final = 5
DEFAULT_UPDATE_SECONDS: Final = 15
# A vehicle that hasn't reported for this long has finished its trip or lost its connection.
DEFAULT_MAX_AGE_MINUTES: Final = 2

# Feeds on the Digitransit MQTT broker, by feed id (case-sensitive), from
# https://digitransit.fi/en/developers/apis/5-realtime-api/vehicle-positions/digitransit-mqtt/
# Other feed ids can still be typed in the feed form.
FEEDS: Final[dict[str, str]] = {
    "tampere": "Tampere",
    "LINKKI": "Jyväskylä",
    "Lappeenranta": "Lappeenranta",
    "Joensuu": "Joensuu",
    "Kuopio": "Kuopio",
    "FOLI": "Turku",
    "OULU": "Oulu",
    "Hameenlinna": "Hämeenlinna",
    "Lahti": "Lahti",
    "Vaasa": "Vaasa",
    "Mikkeli": "Mikkeli",
    "Pori": "Pori",
    "Kouvola": "Kouvola",
    "Kotka": "Kotka",
    "Rovaniemi": "Rovaniemi",
    "Salo": "Salo",
    "Kajaani": "Kajaani",
    "VARELY": "Varsinais-Suomen ELY",
    "Rauma": "Rauma",
    "digitraffic": "Finland trains",
    "Harma": "Härmän liikenne",
    "Korsisaari": "Uusimaa ELY Korsisaari",
    "IngvesSvanback": "Etelä-Pohjanmaa ELY Ingves & Svanbäck",
}

# Names for the routing API's regions (feed ids). Most are the MQTT feeds above; others are shown by their id.
REGION_NAMES: Final[dict[str, str]] = {
    **FEEDS,
    "HSL": "Helsinki region (HSL)",
    "MATKA": "matka.fi buses",
    "Raasepori": "Raasepori",
    "CAR_FERRIES": "Finferries car ferries",
    "02Taksi": "02 Taksi",
    "PohjolanMatka": "Pohjolan Matka",
    "flixbus": "FlixBus",
    "VR_bussit": "VR buses",
    "PahkakankaanLiikenne": "Pahkakankaan Liikenne",
    "Viro": "Estonia",
}
