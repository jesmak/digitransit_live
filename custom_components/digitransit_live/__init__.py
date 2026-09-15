"""Digitransit Live: live public transport vehicles from Digitransit's MQTT broker, as map feeds.

One MQTT connection serves every feed. Each feed is a config subentry with its
own coordinator and sensor, and the sensor writes the Map Feed format that the
map feed plugin for ha-map-card draws.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from .const import CONF_FEED, CONF_LANGUAGE, SUBENTRY_VEHICLES
from .coordinator import DigitransitConfigEntry, DigitransitRuntimeData, VehicleFeedCoordinator
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
    entry.runtime_data = DigitransitRuntimeData(
        texts=await async_load_texts(hass, entry.data[CONF_LANGUAGE]),
        stores=stores,
        mqtt=client,
    )
    for subentry in subentries:
        entry.runtime_data.coordinators[subentry.subentry_id] = VehicleFeedCoordinator(hass, entry, subentry)

    # Coordinators start updating when their sensors are added; until vehicles have arrived the state is unknown.
    if client is not None:
        client.start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Adding, changing or removing a feed (subentry), or changing the language, reloads everything.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: DigitransitConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DigitransitConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.runtime_data.mqtt is not None:
        await hass.async_add_executor_job(entry.runtime_data.mqtt.stop)
    return unloaded
