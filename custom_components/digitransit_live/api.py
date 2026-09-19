"""Digitransit's routing API (GraphQL): regions, their stops, and stop departures.

Every request needs a subscription key, free from https://portal-api.digitransit.fi/.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import ROUTER, ROUTING_API

API_KEY_HEADER = "digitransit-subscription-key"
TIMEOUT = aiohttp.ClientTimeout(total=20)

# The regions are the routing data's feeds. This is also the smallest query there is, for checking a key.
REGIONS = "query Regions { feeds { feedId } }"

# Every stop of a region: a box around Finland and Estonia, limited to the region's feed. The widest region has about
# 35,000 stops, a few megabytes. Stops near a pin are found from these, not with the API's stopsByRadius: that one
# searches along streets, finds nothing from a pin away from a street, and takes seconds for a wide circle.
REGION_STOPS = """
query RegionStops($feeds: [String!]) {
  stopsByBbox(minLat: 57.0, minLon: 19.0, maxLat: 70.2, maxLon: 31.7, feeds: $feeds) {
    gtfsId
    name
    code
    desc
    vehicleMode
    lat
    lon
  }
}
"""

STOP_DEPARTURES = """
query StopDepartures($id: String!, $count: Int!) {
  stop(id: $id) {
    gtfsId
    name
    code
    stoptimesWithoutPatterns(numberOfDepartures: $count, omitNonPickups: true) {
      scheduledDeparture
      realtimeDeparture
      departureDelay
      realtime
      realtimeState
      serviceDay
      headsign
      stop {
        platformCode
      }
      trip {
        tripHeadsign
        route {
          shortName
          longName
          mode
        }
      }
    }
  }
}
"""


class DigitransitError(Exception):
    """The routing API couldn't be reached, or it answered with an error."""


class DigitransitAuthError(DigitransitError):
    """The subscription key is wrong or no longer valid."""


class RoutingClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def query(self, router: str, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Runs a GraphQL query on a router and returns its data."""
        try:
            async with self._session.post(
                ROUTING_API.format(router=router),
                json={"query": query, "variables": variables or {}},
                headers={API_KEY_HEADER: self._api_key},
                timeout=TIMEOUT,
            ) as response:
                # 401 is a missing or wrong key. 403 means the quota ran out, which isn't the key's fault.
                if response.status == 401:
                    raise DigitransitAuthError("Digitransit refused the subscription key")
                if response.status != 200:
                    raise DigitransitError(f"Digitransit's routing API answered with status {response.status}")
                body = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise DigitransitError(f"Digitransit's routing API couldn't be reached: {err!r}") from err
        if not isinstance(body, dict):
            raise DigitransitError("Digitransit's routing API sent an unexpected response")
        if errors := body.get("errors"):
            raise DigitransitError(f"Digitransit's routing API returned an error: {errors[0].get('message')}")
        return body.get("data") or {}

    async def check_key(self) -> None:
        await self.regions()

    async def regions(self) -> list[str]:
        """The feed ids of every region, such as HSL, LINKKI or Lappeenranta."""
        data = await self.query(ROUTER, REGIONS)
        return sorted({str(feed["feedId"]) for feed in data.get("feeds") or [] if feed and feed.get("feedId")})

    async def region_stops(self, feed_id: str) -> list[dict[str, Any]]:
        """Every stop of a region, with its name, code, description, vehicle type and location."""
        data = await self.query(ROUTER, REGION_STOPS, {"feeds": [feed_id]})
        return [stop for stop in data.get("stopsByBbox") or [] if stop and stop.get("gtfsId")]

    async def stop_departures(self, router: str, stop_id: str, count: int) -> dict[str, Any] | None:
        """The stop with its next departures, or None when the router doesn't know the stop."""
        data = await self.query(router, STOP_DEPARTURES, {"id": stop_id, "count": count})
        return data.get("stop")
