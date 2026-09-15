"""Map feed sensors: one per feed.

The state is the number of vehicles; the vehicles are in the `geojson`
attribute, in the Map Feed format (docs/map-feed-format.md in
ha-map-card-plugin-map-feed).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MAP_FEED_VERSION
from .coordinator import DigitransitConfigEntry, VehicleFeedCoordinator
from .feed import feature_collection


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DigitransitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
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
