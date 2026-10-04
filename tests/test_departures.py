"""Stop departures and stop search results from the routing API."""

from __future__ import annotations

from homeassistant.util import dt as dt_util

from custom_components.digitransit_live.departures import (
    DeparturesConfig,
    nearest_stops,
    parse_departures,
    region_centre,
    region_label,
    region_options,
    stop_options,
    stop_title,
)

from .conftest import NOON, REGION_STOPS, SERVICE_DAY, STOP, stoptime


def config(**values: object) -> DeparturesConfig:
    return DeparturesConfig.from_data({"router": "hsl", "stop": "HSL:1020453", "departures": 5} | values)


def test_departures_are_in_order_without_arrivals() -> None:
    result = parse_departures(STOP, config(departures=2))

    assert (result.stop_id, result.name, result.code) == ("HSL:1020453", "Kauppatori", "H0453")
    assert [departure.line for departure in result.departures] == ["4", "16"], "sorted by estimate, limited to 2"

    tram, bus = result.departures
    assert tram.estimated == dt_util.utc_from_timestamp(SERVICE_DAY + NOON + 90)
    assert tram.scheduled == dt_util.utc_from_timestamp(SERVICE_DAY + NOON + 120)
    assert bus.as_attribute() == {
        "id": f"trip:HSL:1016_{NOON + 300}/{SERVICE_DAY}",
        "line": "16",
        "mode": "bus",
        "headsign": "Katajanokka",
        "scheduled": "2026-09-15T09:05:00+00:00",
        "estimated": "2026-09-15T09:06:30+00:00",
        "realtime": True,
        "delay": 90,
        "platform": "1",
        "color": "#007ac9",
    }
    assert tram.as_attribute().keys() == {
        "id",
        "line",
        "mode",
        "headsign",
        "scheduled",
        "estimated",
        "realtime",
        "delay",
    }


def test_cancelled_departures_stay_but_are_never_next() -> None:
    result = parse_departures(STOP, config())

    assert [(departure.line, departure.cancelled) for departure in result.departures] == [
        ("4", False),
        ("16", False),
        ("16", False),
        ("2", True),
    ]
    assert result.departures[-1].as_attribute()["cancelled"] is True
    assert result.next_departure is result.departures[0]

    only_cancelled = parse_departures(STOP, config(lines=["2"]))
    assert only_cancelled.next_departure is None


def test_a_circular_line_departs_from_the_stop_it_ends_at() -> None:
    stop = {
        "gtfsId": "HSL:1",
        "name": "X",
        "stoptimesWithoutPatterns": [
            stoptime("90", "Ympyrä", NOON, position=1, last_position=30),
            stoptime("90", "Ympyrä", NOON + 60, position=30, last_position=30),
        ],
    }
    assert [departure.scheduled for departure in parse_departures(stop, config()).departures] == [
        dt_util.utc_from_timestamp(SERVICE_DAY + NOON)
    ]


def test_modes_are_the_departures_formats() -> None:
    stop = {
        "gtfsId": "HSL:1",
        "name": "X",
        "stoptimesWithoutPatterns": [
            stoptime(line, "Y", NOON + index, mode=mode)
            for index, (line, mode) in enumerate([("M1", "SUBWAY"), ("P", "RAIL"), ("19", "FERRY"), ("F", "FUNICULAR")])
        ],
    }
    assert [departure.mode for departure in parse_departures(stop, config()).departures] == [
        "metro",
        "train",
        "ferry",
        "other",
    ]


def test_lines_filter_departures_and_fetch_more() -> None:
    only_16 = config(lines=[" 16 "])
    assert only_16.fetch_count == 20
    assert config().fetch_count == 10, "twice the count, for the arrivals that are dropped"

    result = parse_departures(STOP, only_16)
    assert [departure.line for departure in result.departures] == ["16", "16"]
    assert result.departures[1].realtime is False
    assert result.departures[1].estimated == result.departures[1].scheduled


def test_stoptimes_without_times_are_skipped() -> None:
    stop = {
        "gtfsId": "HSL:1",
        "name": "X",
        "stoptimesWithoutPatterns": [{"serviceDay": None, "scheduledDeparture": 100}],
    }
    assert parse_departures(stop, config()).departures == []


def test_the_nearest_stops_come_first() -> None:
    stops = nearest_stops(REGION_STOPS, 60.1702, 24.941, 3)
    assert [(stop["gtfsId"], round(stop["distance"])) for stop in stops] == [
        ("HSL:1030003", 28),
        ("HSL:1020201", 33),
        ("HSL:1020453", 60),
    ]
    assert stop_title(stops[1]) == "Kauppatori (H0201)"
    assert stop_options(stops, "fi") == [
        ("HSL:1030003", "Ylioppilastalo (H0103) – 28 m, bus"),
        ("HSL:1020201", "Kauppatori (H0201) – Eteläranta, 33 m, tram"),
        ("HSL:1020453", "Kauppatori (H0453) – Pohjoisesplanadi, 60 m, bus"),
    ]

    everything = nearest_stops(REGION_STOPS, 60.1702, 24.941, 10)
    assert len(everything) == 8
    assert stop_options(everything[-1:], "fi") == [("HSL:2000003", "Vantaa (V1000) – 16,9 km, bus")]
    assert stop_options(everything[-1:], "en") == [("HSL:2000003", "Vantaa (V1000) – 16.9 km, bus")]
    assert nearest_stops(REGION_STOPS, 60.21, 25.05, 1)[0]["gtfsId"] == "HSL:2000002", "wherever the pin is"
    assert nearest_stops([{"gtfsId": "X:1", "lat": None, "lon": 25.0}], 60.0, 25.0, 5) == []


def test_a_region_centre_is_where_its_stops_are_densest() -> None:
    assert region_centre(REGION_STOPS) == (60.1702, 24.941)
    assert region_centre([{"lat": None, "lon": 25.0}]) is None
    assert region_centre([]) is None


def test_regions_are_named() -> None:
    assert region_label("HSL") == "Helsinki region (HSL)"
    assert region_label("LINKKI") == "Jyväskylä (LINKKI)"
    assert region_label("Lappeenranta") == "Lappeenranta"
    assert region_label("Uusi") == "Uusi"
    assert region_options(["Lappeenranta", "HSL"]) == [
        ("HSL", "Helsinki region (HSL)"),
        ("Lappeenranta", "Lappeenranta"),
    ]
