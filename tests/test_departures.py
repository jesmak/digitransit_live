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

NOW = dt_util.utc_from_timestamp(SERVICE_DAY + NOON)


def config(**values: object) -> DeparturesConfig:
    return DeparturesConfig.from_data({"router": "hsl", "stop": "HSL:1020453", "departures": 5} | values)


def test_departures_are_in_order_without_arrivals() -> None:
    result = parse_departures(STOP, config(departures=2), "fi", NOW)

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
    result = parse_departures(STOP, config(), "fi", NOW)

    assert [(departure.line, departure.cancelled) for departure in result.departures] == [
        ("4", False),
        ("16", False),
        ("16", False),
        ("2", True),
    ]
    assert result.departures[-1].as_attribute()["cancelled"] is True
    assert result.next_departure is result.departures[0]

    only_cancelled = parse_departures(STOP, config(lines=["2"]), "fi", NOW)
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
    assert [departure.scheduled for departure in parse_departures(stop, config(), "fi", NOW).departures] == [
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
    assert [departure.mode for departure in parse_departures(stop, config(), "fi", NOW).departures] == [
        "metro",
        "train",
        "ferry",
        "other",
    ]


def test_lines_filter_departures_and_fetch_more() -> None:
    only_16 = config(lines=[" 16 "])
    assert only_16.fetch_count == 20
    assert config().fetch_count == 10, "twice the count, for the arrivals that are dropped"

    result = parse_departures(STOP, only_16, "fi", NOW)
    assert [departure.line for departure in result.departures] == ["16", "16"]
    assert result.departures[1].realtime is False
    assert result.departures[1].estimated == result.departures[1].scheduled


def test_stoptimes_without_times_are_skipped() -> None:
    stop = {
        "gtfsId": "HSL:1",
        "name": "X",
        "stoptimesWithoutPatterns": [{"serviceDay": None, "scheduledDeparture": 100}],
    }
    assert parse_departures(stop, config(), "fi", NOW).departures == []


def alert(text: str, effect: str = "OTHER_EFFECT", *, start: int = -3600, end: int = 3600, **translations: str):
    """An alert in force from start to end seconds around NOW, with translations by language ("blank" for none)."""
    return {
        "alertHeaderText": text,
        "alertHeaderTextTranslations": [
            {"language": "" if language == "blank" else language, "text": value} for language, value in translations.items()
        ],
        "alertEffect": effect,
        "effectiveStartDate": int(NOW.timestamp()) + start,
        "effectiveEndDate": int(NOW.timestamp()) + end,
    }


def stop_with_alerts() -> dict:
    detour = alert("Linja 16 poikkeusreitillä", "DETOUR")
    moved = alert("Pysäkki 760 Esimerkkimäki siirtynyt", "STOP_MOVED")
    bus = stoptime("16", "Katajanokka", NOON + 5 * 60)
    bus["trip"]["route"]["alerts"] = [detour, moved]
    tram = stoptime("4", "Munkkiniemi", NOON + 2 * 60, mode="TRAM")
    return {
        "gtfsId": "HSL:1020453",
        "name": "Kauppatori",
        "alerts": [alert("Pysäkki suljettu"), alert("Pysäkki suljettu")],
        "stoptimesWithoutPatterns": [tram, bus],
    }


def test_alert_levels() -> None:
    stop = stop_with_alerts()

    def notices(level: str) -> tuple[list[str], list[str | None]]:
        result = parse_departures(stop, config(alerts=level), "fi", NOW)
        return result.notices, [departure.notice for departure in result.departures]

    assert notices("off") == ([], [None, None])
    assert notices("stop") == (["Pysäkki suljettu"], [None, None]), "duplicates removed, no line alerts"
    assert notices("service_changes") == (["Pysäkki suljettu"], [None, "Linja 16 poikkeusreitillä"])
    assert notices("all") == (
        ["Pysäkki suljettu"],
        [None, "Linja 16 poikkeusreitillä · Pysäkki 760 Esimerkkimäki siirtynyt"],
    )


def test_existing_stops_get_service_changes() -> None:
    tram, bus = parse_departures(stop_with_alerts(), config(), "fi", NOW).departures
    assert "notice" not in tram.as_attribute()
    assert bus.as_attribute()["notice"] == "Linja 16 poikkeusreitillä"


def test_only_alerts_in_force_are_shown() -> None:
    stop = {
        "gtfsId": "HSL:1",
        "name": "X",
        "alerts": [
            alert("Alkaa huomenna", start=86400, end=2 * 86400),
            alert("Päättyi eilen", start=-2 * 86400, end=-86400),
            alert("Voimassa"),
            {**alert("Ei päättymispäivää"), "effectiveEndDate": None},
        ],
    }
    assert parse_departures(stop, config(), "fi", NOW).notices == ["Voimassa", "Ei päättymispäivää"]


def test_alert_language_falls_back() -> None:
    stop = {
        "gtfsId": "HSL:1",
        "name": "X",
        "alerts": [
            alert("Oletus", fi="Suomeksi", en="In English"),
            alert("Oletus", blank="Ilman kieltä", en="Also in English"),
            alert("Vain oletus"),
        ],
    }
    assert parse_departures(stop, config(), "en", NOW).notices == ["In English", "Also in English", "Vain oletus"]
    assert parse_departures(stop, config(), "fi", NOW).notices == ["Suomeksi", "Ilman kieltä", "Vain oletus"]


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
