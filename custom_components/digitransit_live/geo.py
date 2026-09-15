"""The area a feed covers. Coordinates are WGS84 decimal degrees."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Mean Earth radius (IUGG).
EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True)
class Area:
    """A circle around a point."""

    latitude: float
    longitude: float
    radius_km: float

    @classmethod
    def from_selector(cls, value: Mapping[str, Any]) -> Area:
        """From a location selector value: latitude, longitude and radius in metres."""
        return cls(float(value["latitude"]), float(value["longitude"]), float(value["radius"]) / 1000)

    def contains(self, latitude: Any, longitude: Any) -> bool:
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            return False
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return False
        return haversine_km(self.latitude, self.longitude, lat, lon) <= self.radius_km

    def as_attribute(self) -> dict[str, Any]:
        """The `area` attribute of the Map Feed format (latitude first)."""
        return {
            "center": [round(self.latitude, 5), round(self.longitude, 5)],
            "radius_km": round(self.radius_km, 3),
        }
