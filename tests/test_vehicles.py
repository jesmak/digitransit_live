"""Topics, messages, the vehicle store and feed building."""

from __future__ import annotations

import time

from custom_components.digitransit_live.geo import Area
from custom_components.digitransit_live.texts import load_texts
from custom_components.digitransit_live.vehicles import (
    VehicleFeedConfig,
    VehicleStore,
    build_vehicle_features,
    decode_report,
    feed_topic,
    parse_topic,
)

from .conftest import LAPPEENRANTA_AREA, vehicle_message

REAL_TOPIC = (
    "/gtfsrt/vp/Lappeenranta///BUS/4/0/Mäntylä/Ma-Pe_talvi_2026-2027_4_0_090000_093500_0/205275/09:00/90220/"
    "61;28/01/47/74/4//"
)


def config(**overrides) -> VehicleFeedConfig:
    values = {"feed_id": "Lappeenranta", "lines": frozenset(), "area": None, "max_age_minutes": 2}
    return VehicleFeedConfig(**(values | overrides))


def test_feed_topic() -> None:
    assert feed_topic("Lappeenranta") == "/gtfsrt/vp/Lappeenranta/#"


def test_parse_a_real_topic() -> None:
    info = parse_topic(REAL_TOPIC)
    assert info is not None
    assert (info.feed_id, info.mode, info.route_id, info.headsign) == ("Lappeenranta", "BUS", "4", "Mäntylä")
    assert (info.start_time, info.vehicle_id, info.short_name, info.color) == ("09:00", "90220", "4", "")
    assert parse_topic("/gtfsrt/vp/Lappeenranta/too/short") is None
    assert parse_topic("/something/else" + "/x" * 20) is None


def test_decode_a_message() -> None:
    topic, payload = vehicle_message(line="8A", color="1A4A8F")
    report = decode_report(topic, payload, received_at=100.0)
    assert report is not None
    assert report.feed_id == "Lappeenranta"
    assert report.vehicle_id == "90220"
    assert report.line == "8A"
    assert report.headsign == "Mäntylä"
    assert report.color == "#1a4a8f"
    assert report.bearing == 235.0
    assert round(report.speed_mps, 2) == 6.61
    assert report.received_at == 100.0


def test_unusable_messages_are_ignored() -> None:
    topic, payload = vehicle_message()
    assert decode_report(topic, b"not protobuf \xff\xff", 0) is None
    assert decode_report("/wrong/topic", payload, 0) is None
    no_position_topic, no_position = vehicle_message(latitude=0, longitude=0)
    assert decode_report(no_position_topic, no_position, 0) is None


def test_store_keeps_the_latest_report_of_each_vehicle() -> None:
    store = VehicleStore()
    now = time.monotonic()
    for vehicle_id, line, received in [("1", "4", now - 10), ("1", "4", now - 1), ("2", "1", now - 300)]:
        topic, payload = vehicle_message(vehicle_id=vehicle_id, line=line)
        store.update(decode_report(topic, payload, received))

    assert [report.vehicle_id for report in store.recent(120, now)] == ["1"]
    assert [report.line for report in store.recent(600, now)] == ["1", "4"]
    assert store.last_received == now - 300


def test_features_follow_the_map_feed_format() -> None:
    topic, payload = vehicle_message()
    report = decode_report(topic, payload, time.monotonic())
    [feature] = build_vehicle_features([report], config(), load_texts("fi"))

    assert feature["id"] == "vehicle:Lappeenranta/90220"
    assert feature["geometry"]["coordinates"] == [28.17423, 61.04792]
    props = feature["properties"]
    assert props["name"] == "Linja 4"
    assert props["kind"] == "bus"
    assert props["badge"] == "4"
    assert props["label"] == "→ Mäntylä"
    assert props["subtitle"] == "→ Mäntylä"
    assert props["heading"] == 235
    assert props["stationary"] is False
    assert props["speed_kmh"] == 23.8
    assert "color" not in props
    assert props["details"] == [
        {"label": "Lähtöaika", "value": "09:00"},
        {"label": "Ajoneuvo", "value": "90220"},
    ]
    assert props["updated"].endswith("+00:00")


def test_modes_and_stopped_vehicles() -> None:
    topic, payload = vehicle_message(mode="TRAM", speed=0.0, bearing=None)
    [feature] = build_vehicle_features([decode_report(topic, payload, 0)], config(), load_texts("en"))
    assert feature["properties"]["kind"] == "tram"
    assert feature["properties"]["stationary"] is True
    assert "heading" not in feature["properties"]


def test_line_and_area_filters() -> None:
    now = time.monotonic()
    reports = [
        decode_report(*vehicle_message(vehicle_id="1", line="4"), now),
        decode_report(*vehicle_message(vehicle_id="2", line="8a"), now),
        decode_report(*vehicle_message(vehicle_id="3", line="1", latitude=61.3, longitude=28.9), now),
    ]
    texts = load_texts("en")

    lines = build_vehicle_features(reports, config(lines=frozenset({"8A", "1"})), texts)
    assert [feature["properties"]["badge"] for feature in lines] == ["8a", "1"]

    nearby = build_vehicle_features(reports, config(area=Area.from_selector(LAPPEENRANTA_AREA)), texts)
    assert [feature["id"] for feature in nearby] == ["vehicle:Lappeenranta/1", "vehicle:Lappeenranta/2"]
