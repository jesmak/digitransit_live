"""The config flow and the vehicle feed subentry flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.digitransit_live.const import DOMAIN

from .conftest import LAPPEENRANTA_AREA, FakeMqtt

FEED = {
    "name": "Bussit Lappeenranta",
    "feed": "Lappeenranta",
    "lines": [" 4 ", "8A", "4"],
    "use_area": False,
    "area": LAPPEENRANTA_AREA,
    "max_age_minutes": 2,
    "update_seconds": 15,
}


async def setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Digitransit", data={"language": "fi"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def add_feed(hass: HomeAssistant, entry: MockConfigEntry, values: dict) -> dict:
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "vehicles"), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.subentries.async_configure(result["flow_id"], values)


async def test_user_flow_creates_the_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"language": "fi"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"language": "fi"}


async def test_only_one_entry_is_allowed(hass: HomeAssistant) -> None:
    await setup_entry(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_adding_a_feed_connects_and_creates_its_sensor(hass: HomeAssistant, fake_mqtt: type[FakeMqtt]) -> None:
    entry = await setup_entry(hass)
    assert fake_mqtt.instances == [], "no feeds, no connection"

    result = await add_feed(hass, entry, FEED)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    subentry = next(iter(entry.subentries.values()))
    assert subentry.title == "Bussit Lappeenranta"
    assert subentry.data["lines"] == ["4", "8A"]
    assert "area" not in subentry.data, "the area is dropped when it's not in use"

    assert fake_mqtt.instances[-1].feed_ids == ["Lappeenranta"]
    assert hass.states.get("sensor.bussit_lappeenranta") is not None


async def test_feed_validation(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)

    result = await add_feed(hass, entry, FEED | {"feed": "Lappeenranta/#"})
    assert result["errors"] == {"feed": "invalid_feed"}

    result = await add_feed(hass, entry, FEED | {"lines": ["4", "8 A"]})
    assert result["errors"] == {"lines": "invalid_line"}

    result = await add_feed(hass, entry, FEED | {"use_area": True, "area": {"latitude": 61.0, "longitude": 28.1}})
    assert result["errors"] == {"area": "area_radius"}


async def test_reconfiguring_a_feed(hass: HomeAssistant, fake_mqtt: type[FakeMqtt]) -> None:
    entry = await setup_entry(hass)
    await add_feed(hass, entry, FEED)
    await hass.async_block_till_done()
    subentry_id = next(iter(entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "vehicles"), context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry_id}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], FEED | {"feed": "tampere", "use_area": True}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert entry.subentries[subentry_id].data["feed"] == "tampere"
    assert entry.subentries[subentry_id].data["area"] == LAPPEENRANTA_AREA
    assert fake_mqtt.instances[-1].feed_ids == ["tampere"]
