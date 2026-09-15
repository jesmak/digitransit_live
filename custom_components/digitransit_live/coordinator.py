"""Coordinators: one per vehicle feed or stop (config subentry).

Vehicles arrive continuously over MQTT into a VehicleStore per feed id. Each
feed coordinator turns the recent reports into features every few seconds, and
writes the sensor only when something changed. Stop departures are polled from
the routing API.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import DigitransitAuthError, DigitransitError, RoutingClient
from .const import (
    CONF_UPDATE_SECONDS,
    DEFAULT_DEPARTURE_UPDATE_SECONDS,
    DEFAULT_UPDATE_SECONDS,
    DOMAIN,
    MIN_DEPARTURE_UPDATE_SECONDS,
    MIN_UPDATE_SECONDS,
)
from .departures import DeparturesConfig, StopDepartures, parse_departures
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
    # None without an API key, which only stop departures need.
    routing: RoutingClient | None = None
    coordinators: dict[str, VehicleFeedCoordinator | DeparturesCoordinator] = field(default_factory=dict)


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


class DeparturesCoordinator(DataUpdateCoordinator[StopDepartures]):
    """The next departures from one stop."""

    config_entry: DigitransitConfigEntry

    def __init__(self, hass: HomeAssistant, entry: DigitransitConfigEntry, subentry: ConfigSubentry) -> None:
        update_seconds = max(
            MIN_DEPARTURE_UPDATE_SECONDS,
            int(subentry.data.get(CONF_UPDATE_SECONDS, DEFAULT_DEPARTURE_UPDATE_SECONDS)),
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=timedelta(seconds=update_seconds),
        )
        self.subentry = subentry
        self.departures_config = DeparturesConfig.from_data(subentry.data)

    async def _async_update_data(self) -> StopDepartures:
        routing = self.config_entry.runtime_data.routing
        if routing is None:
            # Asks for a key in Home Assistant's repairs, as a rejected key does.
            raise ConfigEntryAuthFailed("Stop departures need a Digitransit API key")
        config = self.departures_config
        try:
            stop = await routing.stop_departures(config.router, config.stop_id, config.fetch_count)
        except DigitransitAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DigitransitError as err:
            raise UpdateFailed(str(err)) from err
        if stop is None:
            raise UpdateFailed(f"Digitransit doesn't know stop {config.stop_id}")
        return parse_departures(stop, config)
