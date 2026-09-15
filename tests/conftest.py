"""Shared fixtures: MQTT messages like Digitransit's, and a fake broker connection."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from google.transit import gtfs_realtime_pb2
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

from custom_components.digitransit_live.const import ROUTING_API
from custom_components.digitransit_live.vehicles import VehicleReport, decode_report

LAPPEENRANTA_AREA = {"latitude": 61.058, "longitude": 28.186, "radius": 5000}

# Stop departures from the routing API, shaped like its GraphQL responses. Times are seconds after the service
# day's start, which is midnight in Finland.
SERVICE_DAY = int(datetime(2026, 9, 15, tzinfo=ZoneInfo("Europe/Helsinki")).timestamp())
NOON = 12 * 3600


def stoptime(
    line: str,
    headsign: str,
    scheduled: int,
    *,
    delay: int = 0,
    realtime: bool = True,
    mode: str = "BUS",
    platform: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    return {
        "scheduledDeparture": scheduled,
        "realtimeDeparture": scheduled + delay,
        "departureDelay": delay,
        "realtime": realtime,
        "realtimeState": state or ("UPDATED" if realtime else "SCHEDULED"),
        "serviceDay": SERVICE_DAY,
        "headsign": headsign,
        "stop": {"platformCode": platform},
        "trip": {"tripHeadsign": headsign, "route": {"shortName": line, "longName": None, "mode": mode}},
    }


STOP = {
    "gtfsId": "HSL:1020453",
    "name": "Kauppatori",
    "code": "H0453",
    "stoptimesWithoutPatterns": [
        stoptime("16", "Katajanokka", NOON + 5 * 60, delay=90, platform="1"),
        stoptime("4", "Munkkiniemi", NOON + 2 * 60, delay=-30, mode="TRAM"),
        stoptime("16", "Katajanokka", NOON + 20 * 60, realtime=False),
        stoptime("2", "Pasila", NOON + 25 * 60, mode="TRAM", state="CANCELED"),
    ],
}

# Every router's URL: new stops use "finland", stops added before regions existed may use the others.
ROUTERS = ["hsl", "waltti", "varely", "finland"]

REGIONS = [{"feedId": "Lappeenranta"}, {"feedId": "HSL"}]


def region_stop(
    gtfs_id: str, name: str, code: str | None, desc: str | None, mode: str, lat: float, lon: float
) -> dict[str, Any]:
    return {"gtfsId": gtfs_id, "name": name, "code": code, "desc": desc, "vehicleMode": mode, "lat": lat, "lon": lon}


# Stops of the HSL region: five close together in the centre, and three far apart. The centre is the median of the
# five, 60.1702, 24.941; the median of all eight would be elsewhere.
REGION_STOPS = [
    region_stop("HSL:1020453", "Kauppatori", "H0453", "Pohjoisesplanadi", "BUS", 60.1700, 24.9400),
    region_stop("HSL:2000003", "Vantaa", "V1000", None, "BUS", 60.3000, 25.1000),
    region_stop("HSL:1020201", "Kauppatori", "H0201", "Eteläranta", "TRAM", 60.1705, 24.9410),
    region_stop("HSL:2000001", "Pakila", "H2271", None, "BUS", 60.2500, 24.8000),
    region_stop("HSL:1030001", "Rautatientori", None, None, "SUBWAY", 60.1710, 24.9420),
    region_stop("HSL:1030002", "Lasipalatsi", "H0102", "Mannerheimintie", "TRAM", 60.1695, 24.9405),
    region_stop("HSL:2000002", "Malmi", "H2400", None, "BUS", 60.2100, 25.0500),
    region_stop("HSL:1030003", "Ylioppilastalo", "H0103", None, "BUS", 60.1702, 24.9415),
]


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


@pytest.fixture
def routing_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Digitransit's routing API on every router: regions, a region's stops, the Kauppatori stop's departures."""

    async def answer(method: str, url: Any, data: dict[str, Any]) -> AiohttpClientMockResponse:
        query = data["query"]
        if "RegionStops" in query:
            result = {"stopsByBbox": REGION_STOPS}
        elif "StopDepartures" in query:
            result = {"stop": STOP if data["variables"]["id"] == STOP["gtfsId"] else None}
        else:
            result = {"feeds": REGIONS}
        return AiohttpClientMockResponse(method, url, json={"data": result})

    for router in ROUTERS:
        aioclient_mock.post(ROUTING_API.format(router=router), side_effect=answer)
    return aioclient_mock
