"""A stop's next departures from the routing API, and the regions and stops to choose from."""

from __future__ import annotations

import heapq
import math
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import CONF_DEPARTURES, CONF_LINES, CONF_ROUTER, CONF_STOP, DEFAULT_DEPARTURES, REGION_NAMES

# With a line filter, more departures are fetched so that enough of the chosen lines remain.
FILTERED_FETCH_FACTOR = 4
MAX_FETCH = 100
# Languages that write decimals with a comma.
DECIMAL_COMMA_LANGUAGES = frozenset({"fi", "sv"})

# A region's centre is found by counting its stops in squares of this size.
DENSITY_SQUARE_KM = 0.5
KM_PER_DEGREE_LATITUDE = 111.2
EARTH_RADIUS_M = 6_371_000


@dataclass(frozen=True)
class DeparturesConfig:
    router: str
    stop_id: str
    count: int
    # Upper-case line numbers; empty for every line.
    lines: frozenset[str]

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> DeparturesConfig:
        return cls(
            router=str(data[CONF_ROUTER]),
            stop_id=str(data[CONF_STOP]),
            count=int(data.get(CONF_DEPARTURES, DEFAULT_DEPARTURES)),
            lines=frozenset(str(line).strip().upper() for line in data.get(CONF_LINES) or ()),
        )

    @property
    def fetch_count(self) -> int:
        return min(self.count * FILTERED_FETCH_FACTOR, MAX_FETCH) if self.lines else self.count


@dataclass(frozen=True)
class Departure:
    line: str
    headsign: str | None
    mode: str | None
    scheduled: datetime
    # The real-time estimate when there is one, otherwise the scheduled time.
    estimated: datetime
    delay_seconds: int
    realtime: bool
    platform: str | None

    def as_attribute(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "headsign": self.headsign,
            "mode": self.mode,
            "scheduled": self.scheduled.isoformat(),
            "estimated": self.estimated.isoformat(),
            "delay": self.delay_seconds,
            "realtime": self.realtime,
            "platform": self.platform,
        }


@dataclass(frozen=True)
class StopDepartures:
    stop_id: str
    name: str
    code: str | None
    departures: list[Departure]


def parse_departures(stop: Mapping[str, Any], config: DeparturesConfig) -> StopDepartures:
    """The stop's next departures in order, limited to the chosen lines and count."""
    departures = []
    for stoptime in stop.get("stoptimesWithoutPatterns") or []:
        departure = parse_departure(stoptime)
        if departure is None or (config.lines and departure.line.upper() not in config.lines):
            continue
        departures.append(departure)
    departures.sort(key=lambda departure: departure.estimated)
    return StopDepartures(
        stop_id=str(stop.get("gtfsId") or config.stop_id),
        name=str(stop.get("name") or ""),
        code=stop.get("code"),
        departures=departures[: config.count],
    )


def parse_departure(stoptime: Mapping[str, Any]) -> Departure | None:
    """One departure. Times are seconds from the start of the service day, which is a Unix time."""
    service_day = stoptime.get("serviceDay")
    scheduled = stoptime.get("scheduledDeparture")
    if not is_int(service_day) or not is_int(scheduled) or stoptime.get("realtimeState") == "CANCELED":
        return None
    realtime_departure = stoptime.get("realtimeDeparture")
    estimated = realtime_departure if is_int(realtime_departure) else scheduled
    trip = stoptime.get("trip") or {}
    route = trip.get("route") or {}
    return Departure(
        line=str(route.get("shortName") or route.get("longName") or ""),
        headsign=stoptime.get("headsign") or trip.get("tripHeadsign"),
        mode=route.get("mode"),
        scheduled=dt_util.utc_from_timestamp(service_day + scheduled),
        estimated=dt_util.utc_from_timestamp(service_day + estimated),
        delay_seconds=int(stoptime.get("departureDelay") or 0),
        realtime=bool(stoptime.get("realtime")),
        platform=(stoptime.get("stop") or {}).get("platformCode"),
    )


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def stop_title(stop: Mapping[str, Any]) -> str:
    """A stop's name with its code, when it has one: "Kauppatori (H0453)"."""
    name = str(stop.get("name") or stop.get("gtfsId") or "")
    return f"{name} ({stop['code']})" if stop.get("code") else name


def region_label(feed_id: str) -> str:
    """A region's name with its feed id: "Jyväskylä (LINKKI)"."""
    name = REGION_NAMES.get(feed_id, feed_id)
    return name if feed_id in name else f"{name} ({feed_id})"


def region_options(feed_ids: Iterable[str]) -> list[tuple[str, str]]:
    """(feed id, label) for choosing a region, sorted by label."""
    return sorted(((feed_id, region_label(feed_id)) for feed_id in feed_ids), key=lambda option: option[1].lower())


def region_centre(stops: Iterable[Mapping[str, Any] | None] | None) -> tuple[float, float] | None:
    """Where a region's stops are densest, which is usually its city centre.

    Stops are counted in squares of half a kilometre, and the busiest block of 3 × 3 squares wins; the centre is the
    median of the stops in it. The median of all stops would land between the towns of a wide region instead.
    """
    points = [(stop["lat"], stop["lon"]) for stop in stops or [] if stop and is_number(stop.get("lat"))]
    points = [(latitude, longitude) for latitude, longitude in points if is_number(longitude)]
    if not points:
        return None

    latitude_step = DENSITY_SQUARE_KM / KM_PER_DEGREE_LATITUDE
    middle_latitude = statistics.median(latitude for latitude, _ in points)
    longitude_step = latitude_step / math.cos(math.radians(middle_latitude))

    def square(point: tuple[float, float]) -> tuple[int, int]:
        return math.floor(point[0] / latitude_step), math.floor(point[1] / longitude_step)

    counts = Counter(square(point) for point in points)

    def block(centre: tuple[int, int]) -> int:
        return sum(counts.get((centre[0] + row, centre[1] + column), 0) for row in (-1, 0, 1) for column in (-1, 0, 1))

    busiest = max(counts, key=block)
    in_block = [point for point in points if all(abs(a - b) <= 1 for a, b in zip(square(point), busiest, strict=True))]
    return (
        round(statistics.median(latitude for latitude, _ in in_block), 5),
        round(statistics.median(longitude for _, longitude in in_block), 5),
    )


def distance_m(latitude: float, longitude: float, other_latitude: float, other_longitude: float) -> float:
    """The straight-line distance between two points, along the earth's surface."""
    latitude_1, latitude_2 = math.radians(latitude), math.radians(other_latitude)
    half_chord = (
        math.sin((latitude_2 - latitude_1) / 2) ** 2
        + math.cos(latitude_1) * math.cos(latitude_2) * math.sin(math.radians(other_longitude - longitude) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(half_chord))


def nearest_stops(
    stops: Iterable[Mapping[str, Any] | None] | None, latitude: float, longitude: float, count: int
) -> list[dict[str, Any]]:
    """The stops nearest a point, nearest first, each with its straight-line `distance` in metres."""
    located = [
        {**stop, "distance": distance_m(latitude, longitude, stop["lat"], stop["lon"])}
        for stop in stops or []
        if stop and stop.get("gtfsId") and is_number(stop.get("lat")) and is_number(stop.get("lon"))
    ]
    return heapq.nsmallest(count, located, key=lambda stop: stop["distance"])


def format_distance(metres: float, language: str) -> str:
    """ "130 m", or "1,3 km" in Finnish and Swedish and "1.3 km" in English."""
    if metres < 1000:
        return f"{round(metres)} m"
    kilometres = f"{metres / 1000:.1f}"
    return f"{kilometres.replace('.', ',') if language in DECIMAL_COMMA_LANGUAGES else kilometres} km"


def stop_options(stops: Sequence[Mapping[str, Any]], language: str) -> list[tuple[str, str]]:
    """(id, label) for choosing one of the nearest stops: "Kauppatori (H0453) – Pohjoisesplanadi, 130 m, bus"."""
    options = []
    for stop in stops:
        modes = stop.get("vehicleMode") or []
        modes = [modes] if isinstance(modes, str) else modes
        details = [
            stop.get("desc"),
            format_distance(stop["distance"], language) if is_number(stop.get("distance")) else None,
            ", ".join(str(mode).lower() for mode in modes),
        ]
        details_text = ", ".join(detail for detail in details if detail)
        options.append((str(stop["gtfsId"]), stop_title(stop) + (f" – {details_text}" if details_text else "")))
    return options
