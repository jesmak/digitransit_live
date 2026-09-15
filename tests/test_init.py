"""Setting up feeds, the sensors they create, and the broker connection."""

from __future__ import annotations

import time

from homeassistant.config_entries import ConfigEntryState, ConfigSubentryData
from homeassistant.const import MATCH_ALL, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.digitransit_live.const import DOMAIN
from custom_components.digitransit_live.sensor import MapFeedSensor

from .conftest import LAPPEENRANTA_AREA, FakeMqtt, vehicle_message


def feed_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Digitransit",
        data={"language": "fi"},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="vehicles",
                title="Linja 4",
                unique_id=None,
                data={
                    "feed": "Lappeenranta",
                    "lines": ["4"],
                    "use_area": False,
                    "max_age_minutes": 2,
                    "update_seconds": 15,
                },
            ),
            ConfigSubentryData(
                subentry_type="vehicles",
                title="Keskusta",
                unique_id=None,
                data={
                    "feed": "Lappeenranta",
                    "lines": [],
                    "use_area": True,
                    "area": LAPPEENRANTA_AREA,
                    "max_age_minutes": 2,
                    "update_seconds": 15,
                },
            ),
            ConfigSubentryData(
                subentry_type="vehicles",
                title="Tampere",
                unique_id=None,
                data={"feed": "tampere", "lines": [], "use_area": False, "max_age_minutes": 2, "update_seconds": 15},
            ),
        ],
    )
    entry.add_to_hass(hass)
    return entry


async def refresh_all(entry: MockConfigEntry) -> None:
    for coordinator in entry.runtime_data.coordinators.values():
        await coordinator.async_refresh()


async def test_feeds_share_one_connection_and_write_map_feeds(hass: HomeAssistant, fake_mqtt: type[FakeMqtt]) -> None:
    entry = feed_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    [client] = fake_mqtt.instances
    assert client.feed_ids == ["Lappeenranta", "tampere"]
    assert hass.states.get("sensor.linja_4").state == STATE_UNKNOWN, "nothing has arrived yet"

    client.push(*vehicle_message(vehicle_id="1", line="4"))
    client.push(*vehicle_message(vehicle_id="2", line="1"))
    client.push(*vehicle_message(vehicle_id="3", line="4", latitude=61.3, longitude=28.9))
    client.push(*vehicle_message(feed="tampere", vehicle_id="t1", line="8A", mode="TRAM", color="1a4a8f"))
    await refresh_all(entry)
    await hass.async_block_till_done()

    line_4 = hass.states.get("sensor.linja_4")
    assert line_4.state == "2"
    assert line_4.attributes["map_feed_version"] == 1
    assert line_4.attributes["attribution"] == "Digitransit, CC BY 4.0"
    assert [feature["id"] for feature in line_4.attributes["geojson"]["features"]] == [
        "vehicle:Lappeenranta/1",
        "vehicle:Lappeenranta/3",
    ]

    centre = hass.states.get("sensor.keskusta")
    assert centre.state == "2"
    assert centre.attributes["area"] == {"center": [61.058, 28.186], "radius_km": 5.0}

    tampere = hass.states.get("sensor.tampere")
    assert tampere.state == "1"
    properties = tampere.attributes["geojson"]["features"][0]["properties"]
    assert (properties["kind"], properties["badge"], properties["color"]) == ("tram", "8A", "#1a4a8f")

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert client.stopped


async def test_feeds_are_kept_out_of_the_recorder() -> None:
    assert MATCH_ALL in MapFeedSensor._unrecorded_attributes


async def test_old_vehicles_are_dropped_and_a_silent_disconnected_feed_is_unavailable(
    hass: HomeAssistant, fake_mqtt: type[FakeMqtt]
) -> None:
    entry = feed_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    [client] = fake_mqtt.instances

    client.push(*vehicle_message(vehicle_id="old", line="4"), received_at=time.monotonic() - 600)
    client.push(*vehicle_message(vehicle_id="new", line="4"))
    await refresh_all(entry)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.linja_4").state == "1"

    client.connected = False
    await refresh_all(entry)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.linja_4").state == "1", "still hearing vehicles"
    assert hass.states.get("sensor.tampere").state == STATE_UNAVAILABLE, "disconnected and silent"
