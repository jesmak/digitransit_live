"""Map feed sensors, one per vehicle feed, and departure sensors, one per stop.

A feed sensor's state is the number of vehicles; the vehicles are in the
`geojson` attribute, in the Map Feed format (docs/map-feed-format.md in
ha-map-card-plugin-map-feed). A departure sensor's state is the time of the
stop's next departure; the departures are in the `departures` attribute.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MAP_FEED_VERSION
from .coordinator import DeparturesCoordinator, DigitransitConfigEntry, VehicleFeedCoordinator
from .feed import feature_collection


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DigitransitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        if isinstance(coordinator, DeparturesCoordinator):
            async_add_entities([DeparturesSensor(coordinator)], config_subentry_id=subentry_id)
        else:
            async_add_entities([MapFeedSensor(coordinator)], config_subentry_id=subentry_id)


class MapFeedSensor(CoordinatorEntity[VehicleFeedCoordinator], SensorEntity):
    # The feed changes every few seconds and can be tens of kilobytes: only the count goes to the database.
    _unrecorded_attributes = frozenset({MATCH_ALL})
    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:bus"

    def __init__(self, coordinator: VehicleFeedCoordinator) -> None:
        super().__init__(coordinator)
        subentry = coordinator.subentry
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="Digitransit",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data.features)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes: dict[str, Any] = {"map_feed_version": MAP_FEED_VERSION}
        if area := self.coordinator.area:
            attributes["area"] = area.as_attribute()
        if data := self.coordinator.data:
            attributes["updated"] = data.updated.isoformat(timespec="seconds")
            attributes["geojson"] = feature_collection(data.features)
        return attributes


class DeparturesSensor(CoordinatorEntity[DeparturesCoordinator], SensorEntity):
    """The time of a stop's next departure, with the real-time estimate when there is one."""

    # The departures change on every update; the next departure time is history enough.
    _unrecorded_attributes = frozenset({"departures"})
    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator: DeparturesCoordinator) -> None:
        super().__init__(coordinator)
        subentry = coordinator.subentry
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="Digitransit",
            model_id=coordinator.departures_config.stop_id,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data
        return data.departures[0].estimated if data and data.departures else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "stop_id": data.stop_id,
            "stop_name": data.name,
            "stop_code": data.code,
            "departures": [departure.as_attribute() for departure in data.departures],
        }
