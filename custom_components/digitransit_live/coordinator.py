"""Coordinators: one per map feed (config subentry).

Vehicles arrive continuously over MQTT into a VehicleStore per feed id. Each
coordinator turns the recent reports into features every few seconds, and
writes the sensor only when something changed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_UPDATE_SECONDS, DEFAULT_UPDATE_SECONDS, DOMAIN, MIN_UPDATE_SECONDS
from .geo import Area
from .mqtt import DigitransitMqtt
from .texts import Texts
from .vehicles import VehicleFeedConfig, VehicleStore, build_vehicle_features

_LOGGER = logging.getLogger(__name__)


@dataclass
class DigitransitRuntimeData:
    texts: Texts
    # By feed id; feeds that use the same feed id share a store.
    stores: dict[str, VehicleStore]
    # None when there are no feeds, so there's nothing to subscribe to.
    mqtt: DigitransitMqtt | None
    coordinators: dict[str, VehicleFeedCoordinator] = field(default_factory=dict)


type DigitransitConfigEntry = ConfigEntry[DigitransitRuntimeData]


@dataclass(frozen=True)
class FeedData:
    features: list[dict[str, Any]]
    # Left out of comparisons, so an unchanged feed isn't written again just because time passed.
    updated: datetime = field(compare=False)


class VehicleFeedCoordinator(DataUpdateCoordinator[FeedData]):
    config_entry: DigitransitConfigEntry

    def __init__(self, hass: HomeAssistant, entry: DigitransitConfigEntry, subentry: ConfigSubentry) -> None:
        update_seconds = max(MIN_UPDATE_SECONDS, int(subentry.data.get(CONF_UPDATE_SECONDS, DEFAULT_UPDATE_SECONDS)))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=timedelta(seconds=update_seconds),
            always_update=False,
        )
        self.subentry = subentry
        self.feed_config = VehicleFeedConfig.from_data(subentry.data)

    @property
    def area(self) -> Area | None:
        return self.feed_config.area

    async def _async_update_data(self) -> FeedData:
        runtime = self.config_entry.runtime_data
        store = runtime.stores[self.feed_config.feed_id]
        max_age_seconds = self.feed_config.max_age_minutes * 60
        now = time.monotonic()

        connected = runtime.mqtt is not None and runtime.mqtt.connected
        heard_recently = store.last_received is not None and now - store.last_received <= max_age_seconds
        if not connected and not heard_recently:
            raise UpdateFailed("Not connected to the Digitransit MQTT broker")

        reports = store.recent(max_age_seconds, now)
        return FeedData(
            features=build_vehicle_features(reports, self.feed_config, runtime.texts),
            updated=dt_util.utcnow(),
        )
