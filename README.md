# Digitransit Live for Home Assistant

Home Assistant integration that turns Digitransit's live buses, trams and stop departures into map feeds and sensors.

[![GitHub Release][releases-shield]][releases] [![GitHub Release Date][release-date-shield]][releases] [![HACS][hacs-shield]][hacs] [![License][license-shield]](LICENSE)

<img src="https://raw.githubusercontent.com/jesmak/digitransit_live/main/docs/images/dashboard-light.png#gh-light-mode-only" width="1280" alt="A dashboard in Tampere, with a map of buses and trams showing their lines, the list of them beside it with one bus's details open, and the departures from two stops, one of them with a notice about the stop moving">
<img src="https://raw.githubusercontent.com/jesmak/digitransit_live/main/docs/images/dashboard-dark.png#gh-dark-mode-only" width="1280" alt="A dashboard in Tampere, with a map of buses and trams showing their lines, the list of them beside it with one bus's details open, and the departures from two stops, one of them with a notice about the stop moving">

## What is it?

A custom component that turns live public transport vehicles from [Digitransit](https://digitransit.fi/)'s MQTT
broker into **map feeds**: one sensor per feed, holding every bus, tram or train in it as GeoJSON.

Show the feeds on a map with [map-feed-card](https://github.com/jesmak/map-feed-card), which draws each vehicle with
its line number and heading, and lists the vehicles by line. The feed format is documented in
[map-feed-format.md](https://github.com/jesmak/map-feed-card/blob/main/docs/map-feed-format.md), so other integrations can produce feeds for the same card.

Digitransit publishes vehicle positions for many Finnish regions, including Tampere, Turku, Oulu, Jyväskylä, Kuopio,
Lahti, Lappeenranta, Joensuu, Pori, Vaasa, Kouvola and Kotka. The broker needs no API key. Helsinki region (HSL)
vehicles are not on it.

It also has **stop departure sensors**: the next departures from any stop in Finland, HSL included, with real-time
estimates from Digitransit's routing API. They need a free Digitransit API key; vehicle feeds don't.

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

| Name     | Type     | Description                                                   | Default                   |
| -------- | -------- | ------------------------------------------------------------- | ------------------------- |
| language | enum     | Language of the texts written into feeds: `fi` or `en`  | Home Assistant's language |
| API key  | password | Digitransit subscription key, needed only for stop departures | none                      |

Get an API key by registering at [portal-api.digitransit.fi](https://portal-api.digitransit.fi/) and subscribing to
the routing API. The key is checked when you save it.

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

### Stop departures

<img src="https://raw.githubusercontent.com/jesmak/digitransit_live/main/docs/images/stop-departures-light.png#gh-light-mode-only" width="510" alt="A stop departures sensor on departures-card, the next tram large with its countdown and delay, and the departures after it">
<img src="https://raw.githubusercontent.com/jesmak/digitransit_live/main/docs/images/stop-departures-dark.png#gh-dark-mode-only" width="510" alt="A stop departures sensor on departures-card, the next tram large with its countdown and delay, and the departures after it">

Add with **Add stop departures**. It takes three steps. First pick a region: a city's public transport, the Helsinki
region (HSL) or one of the wider areas. Then a map opens with a pin where the region's stops are densest, usually the
city centre: move the pin close to your stop and select **Next**. Last, choose your stop from the 10 stops nearest the
pin, nearest first with their distances, set the options below and select **Submit**. If your stop isn't listed, the
last choice in the list takes you back to the map.

| Name                 | Type    | Description                                            | Default                    |
| -------------------- | ------- | ------------------------------------------------------ | -------------------------- |
| Number of departures | number  | How many departures the sensor lists, 1–20             | 5                          |
| Lines                | list    | Line numbers such as `4` or `8A`. Empty for every line | every line                 |
| Update interval      | seconds | How often departures are fetched, at least 30          | 60                         |
| Service alerts       | choice  | Which of Digitransit's service alerts to show, below   | own and service changes    |

Changing a stop changes only these settings. To follow another stop, add it and remove the old one.

Service alerts come in two kinds. A stop's own alerts concern that stop: it's closed, moved or served differently.
Line alerts concern a whole line, and nothing in them says which of its stops they're about, so a line alert can be
about a stop at the other end of town. Some regions, such as Föli in Turku, publish almost everything as line alerts,
stop moves included. The choices:

| Choice                                          | Shows                                                                                                       |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Off                                             | No alerts                                                                                                   |
| The stop's own                                  | The stop's own alerts                                                                                       |
| The stop's own and service changes on its lines | Also line alerts that change the trip: detours, no or reduced service, modified service, significant delays |
| The stop's own and every alert on its lines     | Also every other line alert, such as a stop moved elsewhere on the line                                     |

Stops added before 1.1.0 use the default until changed.

## Sensors

### Vehicle feeds

The state is the number of vehicles in the feed. The attributes follow the
[Map Feed format](https://github.com/jesmak/map-feed-card/blob/main/docs/map-feed-format.md):

| Name               | Description                                   |
| ------------------ | --------------------------------------------- |
| `map_feed_version` | Always `1`                                    |
| `geojson`          | The vehicles as a GeoJSON FeatureCollection   |
| `area`             | The feed's area, if it has one                |
| `updated`          | When the vehicles last changed                |
| `attribution`      | Data credit                                   |
| `feed_type`        | Always `transit`                              |
| `list`             | The card's list sorts the vehicles by line    |

Each vehicle is named by its line and destination ("Line 4 → Mäntylä"), with its line number as the badge and its
destination as the label beside it. It has its heading, speed, trip departure time and vehicle id.

None of the attributes are stored in the recorder. The sensor is only written when a vehicle has moved, but on a busy
feed that can be every update interval, so you may want to exclude it from the recorder. The sensor becomes
unavailable when the broker connection is lost and no vehicle has reported within the maximum position age.

### Stop departures

The state is the time of the next departure that isn't cancelled: the real-time estimate when the vehicle is tracked,
otherwise the timetable time. The sensor is named after the stop, for example `sensor.kauppatori_h0453`. The attributes
follow the [departures format](https://github.com/jesmak/departures-card/blob/main/docs/departures-format.md), which
[departures-card](https://github.com/jesmak/departures-card) shows.

| Attribute            | Description                                      |
| -------------------- | ------------------------------------------------ |
| `departures_version` | Version of the departures format, `1`            |
| `stop_id`            | The stop's id in Digitransit, e.g. `HSL:1020453` |
| `stop_name`          | The stop's name                                  |
| `stop_code`          | The code shown at the stop, e.g. `H0453`         |
| `departures`         | The next departures, soonest first               |
| `notices`            | The stop's own service alerts in force now       |
| `attribution`        | Data credit                                      |

Each departure has:

| Key         | Description                                                          |
| ----------- | -------------------------------------------------------------------- |
| `id`        | The trip and its service day, the same on every update               |
| `line`      | Line number                                                          |
| `mode`      | Vehicle type: `bus`, `tram`, `metro`, `train`, `ferry` or `other`    |
| `headsign`  | Destination                                                          |
| `scheduled` | Departure time in the timetable                                      |
| `estimated` | Real-time estimate, or the timetable time when there is none         |
| `realtime`  | Whether `estimated` comes from a tracked vehicle                     |
| `delay`     | Seconds late; negative when early                                    |
| `platform`  | Platform or track, when the stop has one                             |
| `cancelled` | `true` when the trip is cancelled                                    |
| `notice`    | The line's service alerts in force now, joined with ` · `            |
| `color`     | The line's own colour, when the region gives one                     |

Alerts are shown in the integration's language when Digitransit has them in it, and otherwise in the region's own
language, usually Finnish. Only an alert's headline is used, from its start to its end. Keys with no value are left out. Cancelled trips stay in the list, marked `cancelled`, so you know not to wait for them.
Arrivals at a line's last stop are left out, since nobody can board them. Only the next departure time is stored in the
recorder, not the list. If Digitransit refuses the API key, the sensors become unavailable and Home Assistant asks for
a new key on the integration page.

## Examples

### Buses and trams on a map

The map is drawn by [map-feed-card](https://github.com/jesmak/map-feed-card), whose README has more options.

```yaml
type: custom:map-feed-card
list: true
entities:
  - entity: sensor.tampere_buses_and_trams
    labels: true
```

### Stop departures

[departures-card](https://github.com/jesmak/departures-card) shows the departures: the next one large with a
countdown, the ones after it below, and several stops in one card, such as both sides of a street.

```yaml
type: custom:departures-card
entities:
  - entity: sensor.keskustori_tke0001
    subtitle: towards Hervanta
  - sensor.hameenkatu_tke0002
```

## Upgrading from 1.1

Nothing is required. Swedish is no longer one of the integration's languages. An integration set to Swedish writes
its feed texts in English, and choosing Finnish or English in its settings makes that explicit. Feeds, stops, entity
IDs and attributes carry over.

## Data

The public transport data comes from [Digitransit](https://digitransit.fi/) and the regional transport authorities,
licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

### How it is fetched

One MQTT connection to `mqtt.digitransit.fi` (TLS, port 8883) serves every feed. For each region it subscribes to
`/gtfsrt/vp/<feed id>/#`: one GTFS Realtime vehicle position per message, with the line number and destination in the
topic. Line and area filters are applied in Home Assistant.

Stop departures come from Digitransit's routing API: one GraphQL request per stop per update interval to
`api.digitransit.fi/routing/v2/finland/gtfs/v1`, with the API key in the `digitransit-subscription-key` header. The
`finland` router covers every region with the same real-time estimates as the regional routers. While you add a stop,
the regions and the chosen region's stops come from the same API, one request each; the widest region has about 35,000
stops, a few megabytes. The pin starts where the stops are densest: they're counted in half-kilometre squares and the
busiest block of squares wins. The stops nearest the pin are worked out in Home Assistant, so moving the pin needs no
requests.

## Translating

The integration's own texts are in two places. `translations/<language>.json` has Home Assistant's UI, and
`texts/<language>.json` the texts written into feeds. To add a language, copy both `en.json` files to the new
language's code, translate the values, and add the code to `LANGUAGES` in `const.py`. The tests check that every
language has the same keys and placeholders as English. Stop names, destinations and service alerts come from
Digitransit as they are.

## Development

Requires Python 3.14.

```
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check .
```

| Path                                | What it contains                                                    |
| ----------------------------------- | ------------------------------------------------------------------- |
| `__init__.py`                       | Setup: one MQTT connection, one coordinator per feed or stop        |
| `config_flow.py`                    | The integration settings, the vehicle feed form and choosing a stop |
| `mqtt.py`                           | The broker connection (paho-mqtt in its own thread)                 |
| `vehicles.py`                       | Topics and messages → vehicle reports → feed items                  |
| `api.py`                            | The routing API client (GraphQL)                                    |
| `departures.py`                     | Stop departures, regions and the stops nearest a point              |
| `coordinator.py`                    | Turning recent reports into feeds, and fetching departures          |
| `sensor.py`                         | The feed and departure sensors                                      |
| `feed.py`, `geo.py`                 | Map Feed format building blocks and the area                        |
| `texts.py`, `texts/<language>.json` | Texts written into feeds                                            |
| `translations/<language>.json`      | Home Assistant UI texts                                             |
| `docs/screenshots.json`             | The made-up data the README's screenshots are taken from            |

## Support

Hey dude! Help me out for a couple of :beers: or a :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/jesmak)

## License

MIT, see [LICENSE](LICENSE).

[releases-shield]: https://img.shields.io/github/release/jesmak/digitransit_live.svg?style=for-the-badge
[release-date-shield]: https://img.shields.io/github/release-date/jesmak/digitransit_live?style=for-the-badge
[releases]: https://github.com/jesmak/digitransit_live/releases
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[hacs]: https://hacs.xyz/docs/faq/custom_repositories/
[license-shield]: https://img.shields.io/github/license/jesmak/digitransit_live.svg?style=for-the-badge
