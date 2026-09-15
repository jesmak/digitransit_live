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

from .conftest import NOON, REGION_STOPS, SERVICE_DAY, STOP


def config(**values: object) -> DeparturesConfig:
    return DeparturesConfig.from_data({"router": "hsl", "stop": "HSL:1020453", "departures": 5} | values)


def test_departures_are_in_order_without_cancelled_trips() -> None:
    result = parse_departures(STOP, config(departures=2))

    assert (result.stop_id, result.name, result.code) == ("HSL:1020453", "Kauppatori", "H0453")
    assert [departure.line for departure in result.departures] == ["4", "16"], "sorted by estimate, limited to 2"

    tram, bus = result.departures
    assert tram.estimated == dt_util.utc_from_timestamp(SERVICE_DAY + NOON + 90)
    assert tram.scheduled == dt_util.utc_from_timestamp(SERVICE_DAY + NOON + 120)
    assert bus.as_attribute() == {
        "line": "16",
        "headsign": "Katajanokka",
        "mode": "BUS",
        "scheduled": "2026-09-15T09:05:00+00:00",
        "estimated": "2026-09-15T09:06:30+00:00",
        "delay": 90,
        "realtime": True,
        "platform": "1",
    }


def test_lines_filter_departures_and_fetch_more() -> None:
    only_16 = config(lines=[" 16 "])
    assert only_16.fetch_count == 20
    assert config().fetch_count == 5

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
