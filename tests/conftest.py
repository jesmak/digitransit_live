"""Shared fixtures: MQTT messages like Digitransit's, and a fake broker connection."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any
from unittest.mock import patch

import pytest
from google.transit import gtfs_realtime_pb2

from custom_components.digitransit_live.vehicles import VehicleReport, decode_report

LAPPEENRANTA_AREA = {"latitude": 61.058, "longitude": 28.186, "radius": 5000}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Lets Home Assistant load integrations from custom_components/."""


def vehicle_message(
    *,
    feed: str = "Lappeenranta",
    line: str = "4",
    headsign: str = "Mäntylä",
    vehicle_id: str = "90220",
    latitude: float = 61.04792,
    longitude: float = 28.17423,
    bearing: float | None = 235.0,
    speed: float | None = 6.6111,
    mode: str = "BUS",
    color: str = "",
    start_time: str = "09:00",
) -> tuple[str, bytes]:
    """A topic and payload shaped like Digitransit's (taken from a real Lappeenranta message)."""
    topic = (
        f"/gtfsrt/vp/{feed}///{mode}/{line}/0/{headsign}/Ma-Pe_talvi_2026-2027_{line}_0_090000_093500_0/205275/"
        f"{start_time}/{vehicle_id}/61;28/01/47/74/{line}/{color}/"
    )
    message = gtfs_realtime_pb2.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    entity = message.entity.add()
    entity.id = vehicle_id
    vehicle = entity.vehicle
    vehicle.vehicle.id = vehicle_id
    vehicle.vehicle.label = headsign
    vehicle.trip.route_id = line
    vehicle.position.latitude = latitude
    vehicle.position.longitude = longitude
    if bearing is not None:
        vehicle.position.bearing = bearing
    if speed is not None:
        vehicle.position.speed = speed
    vehicle.timestamp = int(time.time())
    return topic, message.SerializeToString()


class FakeMqtt:
    """Stands in for DigitransitMqtt: no network, messages are pushed by the test."""

    instances: list[FakeMqtt] = []

    def __init__(self, loop: Any, feed_ids: Iterable[str], on_report: Callable[[VehicleReport], None]) -> None:
        self.feed_ids = sorted(feed_ids)
        self.on_report = on_report
        self.connected = False
        self.stopped = False
        FakeMqtt.instances.append(self)

    def start(self) -> None:
        self.connected = True

    def stop(self) -> None:
        self.stopped = True
        self.connected = False

    def push(self, topic: str, payload: bytes, received_at: float | None = None) -> None:
        report = decode_report(topic, payload, time.monotonic() if received_at is None else received_at)
        assert report is not None
        self.on_report(report)


@pytest.fixture
def fake_mqtt() -> type[FakeMqtt]:
    FakeMqtt.instances = []
    with patch("custom_components.digitransit_live.DigitransitMqtt", FakeMqtt):
        yield FakeMqtt
