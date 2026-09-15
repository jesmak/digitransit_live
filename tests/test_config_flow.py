"""The config flow and the vehicle feed subentry flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

from custom_components.digitransit_live.const import DOMAIN, ROUTING_API

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


async def setup_entry(hass: HomeAssistant, **data: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Digitransit", data={"language": "fi"} | data)
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


# ---------------- API key ----------------


async def test_an_entered_api_key_is_checked(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(ROUTING_API.format(router="finland"), status=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"language": "fi", "api_key": "wrong"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"api_key": "invalid_api_key"}

    aioclient_mock.clear_requests()
    aioclient_mock.post(ROUTING_API.format(router="finland"), json={"data": {"feeds": []}})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"language": "fi", "api_key": " right "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"language": "fi", "api_key": "right"}
    assert aioclient_mock.mock_calls[-1][3] == {"digitransit-subscription-key": "right"}


async def test_the_api_key_can_be_removed(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, api_key="old")
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"language": "sv"})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data == {"language": "sv"}


async def test_reauthentication_saves_a_new_key(hass: HomeAssistant, routing_api: AiohttpClientMocker) -> None:
    entry = await setup_entry(hass, api_key="old")
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "new"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data["api_key"] == "new"


# ---------------- stop departures ----------------


def suggested(result: dict, field: str) -> object:
    key = next(key for key in result["data_schema"].schema if key == field)
    return (key.description or {}).get("suggested_value")


async def test_adding_stop_departures(hass: HomeAssistant, routing_api: AiohttpClientMocker) -> None:
    entry = await setup_entry(hass, api_key="test-key")

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "departures"), context={"source": SOURCE_USER}
    )
    assert (result["step_id"], result["last_step"]) == ("user", False)
    assert result["data_schema"].schema["region"].config["options"] == [
        {"value": "HSL", "label": "Helsinki region (HSL)"},
        {"value": "Lappeenranta", "label": "Lappeenranta"},
    ]

    # Picking a region fetches its stops and shows the map, pinned at their densest spot.
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"region": "HSL"})
    assert (result["step_id"], result["last_step"]) == ("location", False)
    assert result["description_placeholders"] == {"region": "Helsinki region (HSL)"}
    assert suggested(result, "location") == {"latitude": 60.1702, "longitude": 24.941}
    requests = len(routing_api.mock_calls)

    # The pinned location lists the stops nearest it; the last choice goes back to the map.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"location": {"latitude": 60.1702, "longitude": 24.941}}
    )
    assert (result["step_id"], result["last_step"]) == ("stop", True)
    labels = [option["label"] for option in result["data_schema"].schema["stop"].config["options"]]
    assert labels[:3] == [
        "Ylioppilastalo (H0103) – 28 m, bus",
        "Kauppatori (H0201) – Eteläranta, 33 m, tram",
        "Kauppatori (H0453) – Pohjoisesplanadi, 60 m, bus",
    ]
    assert labels[-1] == "Siirrä merkkiä nähdäksesi muita pysäkkejä"
    assert len(labels) == 9
    assert suggested(result, "stop") is None, "no stop is chosen in advance"

    settings = {"departures": 3.0, "lines": [" 16 ", "4", "16", ""], "update_seconds": 60.0}
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"stop": "move_pin"} | settings)
    assert result["step_id"] == "location"
    assert suggested(result, "location") == {"latitude": 60.1702, "longitude": 24.941}, "the pin stays where it was"

    moved = {"latitude": 60.21, "longitude": 25.05}
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"location": moved})
    assert result["step_id"] == "stop"
    assert result["data_schema"].schema["stop"].config["options"][0]["label"] == "Malmi (H2400) – 0 m, bus"
    assert suggested(result, "departures") == 3.0, "settings are kept"
    assert len(routing_api.mock_calls) == requests, "moving the pin doesn't ask Digitransit"

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"stop": "HSL:1020453"} | settings)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kauppatori (H0453)"
    await hass.async_block_till_done()

    subentry = next(iter(entry.subentries.values()))
    assert subentry.data == {
        "router": "finland",
        "stop": "HSL:1020453",
        "departures": 3,
        "lines": ["16", "4"],
        "update_seconds": 60,
    }
    state = hass.states.get("sensor.kauppatori_h0453")
    assert state.state == "2026-09-15T09:01:30+00:00"
    assert len(state.attributes["departures"]) == 3
    _method, url, data, headers = routing_api.mock_calls[-1]
    assert str(url) == "https://api.digitransit.fi/routing/v2/finland/gtfs/v1"
    assert data["variables"] == {"id": "HSL:1020453", "count": 12}, "more are fetched when lines are filtered"
    assert headers == {"digitransit-subscription-key": "test-key"}

    # Changing it keeps the stop.
    result = await entry.start_subentry_reconfigure_flow(hass, subentry.subentry_id)
    assert [str(key) for key in result["data_schema"].schema] == ["departures", "lines", "update_seconds"]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"departures": 1.0, "update_seconds": 120.0}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.subentries[subentry.subentry_id].data == {
        "router": "finland",
        "stop": "HSL:1020453",
        "departures": 1,
        "lines": [],
        "update_seconds": 120,
    }


async def test_stop_departures_need_an_api_key(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "departures"), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "api_key_missing"


async def test_a_region_without_stops(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    entry = await setup_entry(hass, api_key="test-key")

    async def answer(method: str, url: object, data: dict) -> AiohttpClientMockResponse:
        empty = "RegionStops" in data["query"]
        return AiohttpClientMockResponse(
            method, url, json={"data": {"stopsByBbox": []} if empty else {"feeds": [{"feedId": "Tyhjä"}]}}
        )

    aioclient_mock.post(ROUTING_API.format(router="finland"), side_effect=answer)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "departures"), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"region": "Tyhjä"})
    assert result["step_id"] == "user"
    assert result["errors"] == {"region": "no_stops"}


async def test_a_refused_key_stops_adding_a_stop(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    entry = await setup_entry(hass, api_key="expired")
    aioclient_mock.post(ROUTING_API.format(router="finland"), status=401)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "departures"), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_api_key"
