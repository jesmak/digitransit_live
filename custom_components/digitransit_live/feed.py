"""Building blocks of the Map Feed format.

The format is documented in docs/map-feed-format.md of ha-map-card-plugin-map-feed.
"""

from __future__ import annotations

from typing import Any

from homeassistant.util import dt as dt_util

# 5 decimals is about 1 m: enough for a map, and it stops GPS noise from changing the state.
COORDINATE_DECIMALS = 5


def point_feature(feature_id: str, latitude: float, longitude: float, properties: dict[str, Any]) -> dict[str, Any]:
    """A GeoJSON Point feature. Properties without a value are left out, as the format asks."""
    return {
        "type": "Feature",
        "id": feature_id,
        "geometry": {
            "type": "Point",
            # GeoJSON order: longitude first.
            "coordinates": [
                round(float(longitude), COORDINATE_DECIMALS),
                round(float(latitude), COORDINATE_DECIMALS),
            ],
        },
        "properties": {key: value for key, value in properties.items() if value not in (None, "", [])},
    }


def feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def row(label: str, value: str | float, unit: str | None = None) -> dict[str, Any]:
    """One popup row."""
    result: dict[str, Any] = {"label": label, "value": value}
    if unit:
        result["unit"] = unit
    return result


def iso_from_epoch_ms(value: Any) -> str | None:
    """Milliseconds since the epoch as an ISO 8601 UTC time, or None when not a number."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return dt_util.utc_from_timestamp(value / 1000).isoformat(timespec="seconds")
