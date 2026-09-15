"""Vehicle positions from Digitransit's MQTT broker as map feed features.

Every message is a GTFS Realtime FeedMessage with one VehiclePosition. The
topic repeats the trip details, including the line number and destination
that the message itself doesn't carry:

  /gtfsrt/vp/<feed_id>/<agency_id>/<agency_name>/<mode>/<route_id>/<direction_id>/<trip_headsign>/<trip_id>/
  <next_stop>/<start_time>/<vehicle_id>/<geohash_head>/<geohash_firstdeg>/<geohash_seconddeg>/<geohash_thirddeg>/
  <short_name>/<color>/

See https://digitransit.fi/en/developers/apis/5-realtime-api/vehicle-positions/digitransit-mqtt/
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from .const import CONF_AREA, CONF_FEED, CONF_LINES, CONF_MAX_AGE_MINUTES, DEFAULT_MAX_AGE_MINUTES
from .feed import iso_from_epoch_ms, point_feature, row
from .geo import Area
from .texts import Texts

TOPIC_PREFIX = "/gtfsrt/vp"

# Feed kinds by the topic's transport mode. Everything else is "other".
MODE_KINDS: dict[str, str] = {
    "BUS": "bus",
    "TRAM": "tram",
    "SUBWAY": "metro",
    "RAIL": "train.commuter",
    "FERRY": "ferry",
}

# Below this speed a vehicle is drawn as a dot.
STATIONARY_SPEED_MPS = 0.5

# Reports older than this are dropped from memory, whatever the feeds' own age limits are.
STORE_RETENTION_SECONDS = 3600

HEX_COLOR = re.compile(r"^[0-9a-fA-F]{6}$")


def feed_topic(feed_id: str) -> str:
    """The subscription for every vehicle in a feed."""
    return f"{TOPIC_PREFIX}/{feed_id}/#"


@dataclass(frozen=True)
class TopicInfo:
    feed_id: str
    mode: str
    route_id: str
    headsign: str
    start_time: str
    vehicle_id: str
    short_name: str
    color: str


def parse_topic(topic: str) -> TopicInfo | None:
    parts = topic.split("/")
    if len(parts) < 20 or parts[1:3] != ["gtfsrt", "vp"]:
        return None
    return TopicInfo(
        feed_id=parts[3],
        mode=parts[6],
        route_id=parts[7],
        headsign=parts[9],
        start_time=parts[12],
        vehicle_id=parts[13],
        short_name=parts[18],
        color=parts[19],
    )


@dataclass(frozen=True)
class VehicleReport:
    """The latest position of one vehicle."""

    feed_id: str
    vehicle_id: str
    latitude: float
    longitude: float
    mode: str
    # The line number, or the route id when the feed has no line numbers.
    line: str
    headsign: str
    start_time: str
    color: str | None
    bearing: float | None
    speed_mps: float | None
    # Seconds since the epoch, as reported by the vehicle.
    timestamp: int | None
    # time.monotonic() when the message arrived.
    received_at: float


def decode_report(topic: str, payload: bytes, received_at: float) -> VehicleReport | None:
    """A report from one MQTT message, or None when the message isn't a usable vehicle position."""
    info = parse_topic(topic)
    if info is None:
        return None
    message = gtfs_realtime_pb2.FeedMessage()
    try:
        message.ParseFromString(payload)
    except DecodeError:
        return None

    for entity in message.entity:
        if not entity.HasField("vehicle") or not entity.vehicle.HasField("position"):
            continue
        vehicle = entity.vehicle
        position = vehicle.position
        if position.latitude == 0 and position.longitude == 0:
            continue
        return VehicleReport(
            feed_id=info.feed_id,
            vehicle_id=vehicle.vehicle.id or info.vehicle_id,
            latitude=position.latitude,
            longitude=position.longitude,
            mode=info.mode.upper(),
            line=info.short_name or info.route_id or vehicle.trip.route_id,
            headsign=info.headsign,
            start_time=info.start_time or vehicle.trip.start_time[:5],
            color=f"#{info.color.lower()}" if HEX_COLOR.match(info.color) else None,
            bearing=position.bearing if position.HasField("bearing") else None,
            speed_mps=position.speed if position.HasField("speed") else None,
            timestamp=vehicle.timestamp or None,
            received_at=received_at,
        )
    return None


class VehicleStore:
    """The latest report of every vehicle in one feed. Used only from the event loop."""

    def __init__(self) -> None:
        self._reports: dict[str, VehicleReport] = {}
        self.last_received: float | None = None

    def update(self, report: VehicleReport) -> None:
        self._reports[report.vehicle_id] = report
        self.last_received = report.received_at

    def recent(self, max_age_seconds: float, now: float) -> list[VehicleReport]:
        """Reports received within `max_age_seconds`, by line and vehicle."""
        for vehicle_id in [
            vehicle_id
            for vehicle_id, report in self._reports.items()
            if now - report.received_at > STORE_RETENTION_SECONDS
        ]:
            del self._reports[vehicle_id]
        return sorted(
            (report for report in self._reports.values() if now - report.received_at <= max_age_seconds),
            key=lambda report: (report.line, report.vehicle_id),
        )


@dataclass(frozen=True)
class VehicleFeedConfig:
    feed_id: str
    lines: frozenset[str]  # upper case; empty = every line
    area: Area | None
    max_age_minutes: float

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> VehicleFeedConfig:
        """From config subentry data."""
        return cls(
            feed_id=data[CONF_FEED],
            lines=frozenset(str(line).strip().upper() for line in data.get(CONF_LINES) or ()),
            area=Area.from_selector(data[CONF_AREA]) if data.get(CONF_AREA) else None,
            max_age_minutes=float(data.get(CONF_MAX_AGE_MINUTES, DEFAULT_MAX_AGE_MINUTES)),
        )


def build_vehicle_features(
    reports: list[VehicleReport], config: VehicleFeedConfig, texts: Texts
) -> list[dict[str, Any]]:
    features = []
    for report in reports:
        if config.lines and report.line.upper() not in config.lines:
            continue
        if config.area is not None and not config.area.contains(report.latitude, report.longitude):
            continue

        destination = f"→ {report.headsign}" if report.headsign else None
        details = []
        if report.start_time:
            details.append(row(texts("departure"), report.start_time))
        details.append(row(texts("vehicle"), report.vehicle_id))

        features.append(
            point_feature(
                f"vehicle:{report.feed_id}/{report.vehicle_id}",
                report.latitude,
                report.longitude,
                {
                    "name": texts("line", line=report.line) if report.line else report.vehicle_id,
                    "kind": MODE_KINDS.get(report.mode, "other"),
                    "updated": iso_from_epoch_ms(report.timestamp * 1000) if report.timestamp else None,
                    "heading": round(report.bearing) if report.bearing is not None else None,
                    "stationary": report.speed_mps is not None and report.speed_mps < STATIONARY_SPEED_MPS,
                    "speed_kmh": round(report.speed_mps * 3.6, 1) if report.speed_mps is not None else None,
                    "badge": report.line,
                    "label": destination,
                    "subtitle": destination,
                    "color": report.color,
                    "details": details,
                },
            )
        )
    return features
