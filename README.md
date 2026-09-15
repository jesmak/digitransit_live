# Digitransit Live for Home Assistant

## What is it?

A custom component that turns live public transport vehicles from [Digitransit](https://digitransit.fi/)'s MQTT
broker into **map feeds**: one sensor per feed, holding every bus, tram or train in it as GeoJSON.

Show the feeds on a map with [ha-map-card](https://github.com/nathan-gs/ha-map-card) and the
[map feed plugin](https://github.com/jesmak/ha-map-card-plugin-map-feed), which draws each vehicle with its line
number, heading and destination. The feed format is documented in
[map-feed-format.md](https://github.com/jesmak/ha-map-card-plugin-map-feed/blob/main/docs/map-feed-format.md), so
other integrations can produce feeds for the same card.

Digitransit publishes vehicle positions for many Finnish regions, including Tampere, Turku, Oulu, Jyväskylä, Kuopio,
Lahti, Lappeenranta, Joensuu, Pori, Vaasa, Kouvola and Kotka. The broker needs no API key. Helsinki region (HSL)
vehicles are not on it.

## Installation

### With HACS

1. Add this repository to HACS custom repositories with type **Integration**
2. Search for Digitransit Live in HACS and download it
3. Restart Home Assistant
4. Add the integration in Settings › Devices & services, then add feeds from its page

### Manual

1. Download the source code from the latest release
2. Copy the `custom_components/digitransit_live` folder to your Home Assistant installation's
   `config/custom_components` folder
3. Restart Home Assistant
4. Add the integration in Settings › Devices & services, then add feeds from its page

## Settings

### Integration

| Name     | Type | Description                                                  | Default                   |
| -------- | ---- | ------------------------------------------------------------ | ------------------------- |
| language | enum | Language of the texts written into feeds: `fi`, `sv` or `en` | Home Assistant's language |

### Vehicle feed

Add with **Add vehicle feed** on the integration page. Every feed creates one sensor named after the feed.

| Name                 | Type    | Description                                                                    | Default     |
| -------------------- | ------- | ------------------------------------------------------------------------------ | ----------- |
| Name                 | string  | Name of the feed and its sensor                                                |             |
| Region               | enum    | The region's feed id on Digitransit, e.g. `Lappeenranta` or `tampere`          |             |
| Lines                | list    | Line numbers such as `4` or `8A`. Empty for every line                         | every line  |
| Limit to an area     | boolean | Only vehicles inside the area                                                  | off         |
| Area                 | circle  | Centre and radius, picked on a map                                             | home, 10 km |
| Maximum position age | minutes | Vehicles that haven't reported for longer are left out                         | 2           |
| Update interval      | seconds | How often the sensor is updated, at least 5. Vehicles report about once a second | 15          |

Large regions have hundreds of vehicles. Limit big feeds with lines or an area, so the sensor stays small.

## Sensors

The state is the number of vehicles in the feed. The attributes follow the
[Map Feed format](https://github.com/jesmak/ha-map-card-plugin-map-feed/blob/main/docs/map-feed-format.md):

| Name               | Description                                   |
| ------------------ | --------------------------------------------- |
| `map_feed_version` | Always `1`                                    |
| `geojson`          | The vehicles as a GeoJSON FeatureCollection   |
| `area`             | The feed's area, if it has one                |
| `updated`          | When the vehicles last changed                |
| `attribution`      | Data credit                                   |

Each vehicle has its line number as the badge, its destination, heading, speed, trip departure time and vehicle id.

None of the attributes are stored in the recorder. The sensor is only written when a vehicle has moved, but on a busy
feed that can be every update interval, so you may want to exclude it from the recorder. The sensor becomes
unavailable when the broker connection is lost and no vehicle has reported within the maximum position age.

## How it works

One MQTT connection to `mqtt.digitransit.fi` (TLS, port 8883) serves every feed. For each region it subscribes to
`/gtfsrt/vp/<feed id>/#`: one GTFS Realtime vehicle position per message, with the line number and destination in the
topic. Line and area filters are applied in Home Assistant.

## Data

Public transport data: [Digitransit](https://digitransit.fi/) and the regional transport authorities, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## Development

Requires Python 3.14.

```
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check .
```

| Path                                | What it contains                                            |
| ----------------------------------- | ----------------------------------------------------------- |
| `__init__.py`                       | Setup: one MQTT connection, one coordinator per feed        |
| `config_flow.py`                    | The integration and the vehicle feed form                   |
| `mqtt.py`                           | The broker connection (paho-mqtt in its own thread)         |
| `vehicles.py`                       | Topics and messages → vehicle reports → feed items          |
| `coordinator.py`                    | Turning recent reports into a feed every few seconds        |
| `sensor.py`                         | The feed sensors                                            |
| `feed.py`, `geo.py`                 | Map Feed format building blocks and the area                |
| `texts.py`, `texts/<language>.json` | Texts written into feeds                                    |
| `translations/<language>.json`      | Home Assistant UI texts                                     |

To add a language, copy `texts/en.json` and `translations/en.json` to `<code>.json`, translate the values, and add
the code to `LANGUAGES` in `const.py`. The tests check that every language has the same keys and placeholders as
English.
