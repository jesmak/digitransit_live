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

# Feed type (config subentry type)
SUBENTRY_VEHICLES: Final = "vehicles"

# Feed settings (config subentry data)
CONF_FEED: Final = "feed"
CONF_LINES: Final = "lines"
CONF_USE_AREA: Final = "use_area"
CONF_AREA: Final = "area"
CONF_MAX_AGE_MINUTES: Final = "max_age_minutes"
CONF_UPDATE_SECONDS: Final = "update_seconds"

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
