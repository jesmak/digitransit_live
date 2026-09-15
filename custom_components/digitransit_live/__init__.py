"""Digitransit Live: live public transport vehicles and stop departures from Digitransit.

One MQTT connection serves every vehicle feed. Each feed is a config subentry
with its own coordinator and sensor, and the sensor writes the Map Feed format
that the map feed plugin for ha-map-card draws. Stops are subentries too: their
departures are polled from the routing API with the entry's API key.
"""

from __future__ import annotations

import asyncio

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RoutingClient
from .const import CONF_API_KEY, CONF_FEED, CONF_LANGUAGE, SUBENTRY_DEPARTURES, SUBENTRY_VEHICLES
from .coordinator import DeparturesCoordinator, DigitransitConfigEntry, DigitransitRuntimeData, VehicleFeedCoordinator
from .mqtt import DigitransitMqtt
from .texts import async_load_texts
from .vehicles import VehicleReport, VehicleStore

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: DigitransitConfigEntry) -> bool:
    subentries = [subentry for subentry in entry.subentries.values() if subentry.subentry_type == SUBENTRY_VEHICLES]
    stores = {subentry.data[CONF_FEED]: VehicleStore() for subentry in subentries}

    @callback
    def handle_report(report: VehicleReport) -> None:
        if store := stores.get(report.feed_id):
            store.update(report)

    client = DigitransitMqtt(hass.loop, stores, handle_report) if stores else None
    api_key = entry.data.get(CONF_API_KEY)
    entry.runtime_data = DigitransitRuntimeData(
        texts=await async_load_texts(hass, entry.data[CONF_LANGUAGE]),
        stores=stores,
        mqtt=client,
        routing=RoutingClient(async_get_clientsession(hass), api_key) if api_key else None,
    )
    for subentry in subentries:
        entry.runtime_data.coordinators[subentry.subentry_id] = VehicleFeedCoordinator(hass, entry, subentry)
    departures = [
        DeparturesCoordinator(hass, entry, subentry)
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_DEPARTURES
    ]
    for coordinator in departures:
        entry.runtime_data.coordinators[coordinator.subentry.subentry_id] = coordinator

    # Vehicle feed coordinators start updating when their sensors are added; until vehicles have arrived the state is
    # unknown. Departures are fetched once first, so their sensors start with a value; a stop that fails is unavailable.
    await asyncio.gather(*(coordinator.async_refresh() for coordinator in departures))
    if client is not None:
        client.start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Adding, changing or removing a feed or stop (subentry), or changing the settings, reloads everything.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: DigitransitConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DigitransitConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.runtime_data.mqtt is not None:
        await hass.async_add_executor_job(entry.runtime_data.mqtt.stop)
    return unloaded
