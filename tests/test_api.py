"""Errors from the routing API client."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.digitransit_live.api import ROUTING_API, DigitransitError, RoutingClient


async def test_a_timeout_names_the_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(ROUTING_API.format(router="finland"), exc=TimeoutError())
    client = RoutingClient(async_get_clientsession(hass), "key")

    with pytest.raises(DigitransitError, match=r"couldn't be reached: TimeoutError\(\)"):
        await client.query("finland", "{ feeds { feedId } }")
