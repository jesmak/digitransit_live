"""Config flow.

The config entry holds the language and, for stop departures, a Digitransit API
key. Vehicle feeds ("vehicles") and stops ("departures") are config subentries,
added and changed from the integration page.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import DigitransitAuthError, DigitransitError, RoutingClient
from .const import (
    CONF_API_KEY,
    CONF_AREA,
    CONF_DEPARTURES,
    CONF_FEED,
    CONF_LANGUAGE,
    CONF_LINES,
    CONF_LOCATION,
    CONF_MAX_AGE_MINUTES,
    CONF_REGION,
    CONF_ROUTER,
    CONF_STOP,
    CONF_UPDATE_SECONDS,
    CONF_USE_AREA,
    DEFAULT_DEPARTURE_UPDATE_SECONDS,
    DEFAULT_DEPARTURES,
    DEFAULT_MAX_AGE_MINUTES,
    DEFAULT_UPDATE_SECONDS,
    DOMAIN,
    FEEDS,
    LANGUAGES,
    MAX_DEPARTURES,
    MIN_DEPARTURE_UPDATE_SECONDS,
    MIN_UPDATE_SECONDS,
    ROUTER,
    STOP_CHOICES,
    SUBENTRY_DEPARTURES,
    SUBENTRY_VEHICLES,
)
from .departures import nearest_stops, region_centre, region_label, region_options, stop_options, stop_title
from .texts import async_load_texts

DEFAULT_RADIUS_M = 10_000

# Feed ids and line numbers become MQTT topic levels or filters: no slashes or wildcards.
FEED_ID = re.compile(r"^[A-Za-z0-9_-]+$")
LINE = re.compile(r"^[^/#+\s]{1,20}$")

API_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def entry_schema(language: str, api_key: str | None) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_LANGUAGE, default=language): SelectSelector(
                SelectSelectorConfig(options=LANGUAGES, translation_key=CONF_LANGUAGE, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_API_KEY, description={"suggested_value": api_key}): API_KEY_SELECTOR,
        }
    )


async def check_api_key(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Checks an entered API key with Digitransit. An empty key is removed from the data."""
    api_key = str(data.get(CONF_API_KEY) or "").strip()
    if not api_key:
        data.pop(CONF_API_KEY, None)
        return {}
    data[CONF_API_KEY] = api_key
    try:
        await RoutingClient(async_get_clientsession(hass), api_key).check_key()
    except DigitransitAuthError:
        return {CONF_API_KEY: "invalid_api_key"}
    except DigitransitError:
        return {"base": "cannot_connect"}
    return {}


class DigitransitLiveConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(user_input)
            errors = await check_api_key(self.hass, data)
            if not errors:
                return self.async_create_entry(title="Digitransit", data=data)
        language = self.hass.config.language[:2]
        values = user_input or {CONF_LANGUAGE: language if language in LANGUAGES else "en"}
        return self.async_show_form(
            step_id="user",
            data_schema=entry_schema(values[CONF_LANGUAGE], values.get(CONF_API_KEY)),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            if CONF_API_KEY not in user_input:
                data.pop(CONF_API_KEY, None)
            errors = await check_api_key(self.hass, data)
            if not errors:
                # The update listener in __init__.py reloads the entry.
                self.hass.config_entries.async_update_entry(entry, data=data)
                return self.async_abort(reason="reconfigure_successful")
        values = user_input or entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=entry_schema(values[CONF_LANGUAGE], values.get(CONF_API_KEY)),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Asks for a new API key when Digitransit refuses the key, or when stops were added without one."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_API_KEY: user_input.get(CONF_API_KEY)}
            errors = await check_api_key(self.hass, data)
            if not errors and CONF_API_KEY not in data:
                errors = {CONF_API_KEY: "invalid_api_key"}
            if not errors:
                entry = self._get_reauth_entry()
                self.hass.config_entries.async_update_entry(entry, data={**entry.data, **data})
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): API_KEY_SELECTOR}),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_VEHICLES: VehicleFeedFlow, SUBENTRY_DEPARTURES: DeparturesFlow}


class VehicleFeedFlow(ConfigSubentryFlow):
    """Adding (step "user") and changing (step "reconfigure") a vehicle feed with a single form."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return self._step_feed("user", user_input, None)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return self._step_feed("reconfigure", user_input, self._get_reconfigure_subentry())

    def _step_feed(
        self, step_id: str, user_input: dict[str, Any] | None, current: ConfigSubentry | None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(user_input)
            title = data.pop(CONF_NAME).strip()
            errors = validate(data)
            if not errors:
                data = clean(data)
                if current is None:
                    return self.async_create_entry(title=title, data=data)
                return self.async_update_and_abort(self._get_entry(), current, title=title, data=data)

        if user_input is not None:
            values = user_input
        elif current is not None:
            values = {CONF_NAME: current.title, **current.data}
        else:
            values = self._defaults()
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(feed_schema(), values),
            errors=errors,
        )

    def _defaults(self) -> dict[str, Any]:
        return {
            CONF_USE_AREA: False,
            CONF_AREA: {
                "latitude": self.hass.config.latitude,
                "longitude": self.hass.config.longitude,
                "radius": DEFAULT_RADIUS_M,
            },
            CONF_MAX_AGE_MINUTES: DEFAULT_MAX_AGE_MINUTES,
            CONF_UPDATE_SECONDS: DEFAULT_UPDATE_SECONDS,
        }


def feed_schema() -> vol.Schema:
    feeds = sorted(
        (SelectOptionDict(value=feed_id, label=f"{name} ({feed_id})") for feed_id, name in FEEDS.items()),
        key=lambda option: option["label"],
    )
    return vol.Schema(
        {
            vol.Required(CONF_NAME): TextSelector(),
            vol.Required(CONF_FEED): SelectSelector(
                SelectSelectorConfig(options=feeds, mode=SelectSelectorMode.DROPDOWN, custom_value=True)
            ),
            vol.Optional(CONF_LINES): SelectSelector(
                SelectSelectorConfig(options=[], multiple=True, custom_value=True)
            ),
            vol.Required(CONF_USE_AREA): BooleanSelector(),
            vol.Optional(CONF_AREA): LocationSelector(LocationSelectorConfig(radius=True, icon="mdi:bus")),
            vol.Required(CONF_MAX_AGE_MINUTES): NumberSelector(
                NumberSelectorConfig(min=1, max=60, step=1, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_UPDATE_SECONDS): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_UPDATE_SECONDS, max=3600, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX
                )
            ),
        }
    )


def validate(data: dict[str, Any]) -> dict[str, str]:
    if not FEED_ID.match(str(data.get(CONF_FEED, "")).strip()):
        return {CONF_FEED: "invalid_feed"}
    if any(not LINE.match(str(line).strip()) for line in data.get(CONF_LINES) or []):
        return {CONF_LINES: "invalid_line"}
    if data[CONF_USE_AREA] and not (data.get(CONF_AREA) or {}).get("radius"):
        return {CONF_AREA: "area_radius"}
    return {}


def clean(data: dict[str, Any]) -> dict[str, Any]:
    """Normalises submitted values before they are stored."""
    data[CONF_FEED] = str(data[CONF_FEED]).strip()
    data[CONF_LINES] = list(dict.fromkeys(str(line).strip() for line in data.get(CONF_LINES) or []))
    data[CONF_MAX_AGE_MINUTES] = int(data[CONF_MAX_AGE_MINUTES])
    data[CONF_UPDATE_SECONDS] = int(data[CONF_UPDATE_SECONDS])
    if not data[CONF_USE_AREA]:
        # Without the area enabled the feed covers every vehicle; don't keep a stale circle around.
        data.pop(CONF_AREA, None)
    return data


DEPARTURE_DEFAULTS: dict[str, Any] = {
    CONF_DEPARTURES: DEFAULT_DEPARTURES,
    CONF_UPDATE_SECONDS: DEFAULT_DEPARTURE_UPDATE_SECONDS,
}


def departure_fields() -> dict[vol.Marker, Any]:
    return {
        vol.Required(CONF_DEPARTURES): NumberSelector(
            NumberSelectorConfig(min=1, max=MAX_DEPARTURES, step=1, mode=NumberSelectorMode.BOX)
        ),
        vol.Optional(CONF_LINES): SelectSelector(SelectSelectorConfig(options=[], multiple=True, custom_value=True)),
        vol.Required(CONF_UPDATE_SECONDS): NumberSelector(
            NumberSelectorConfig(
                min=MIN_DEPARTURE_UPDATE_SECONDS, max=3600, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX
            )
        ),
    }


def departure_settings(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """The submitted departure settings, normalised for storing."""
    lines = (str(line).strip() for line in user_input.get(CONF_LINES) or [])
    return {
        CONF_DEPARTURES: int(user_input[CONF_DEPARTURES]),
        CONF_LINES: list(dict.fromkeys(line for line in lines if line)),
        CONF_UPDATE_SECONDS: int(user_input[CONF_UPDATE_SECONDS]),
    }


# The last choice in the stop list: back to the map instead of adding a stop. Stop ids always contain a colon.
MOVE_PIN = "move_pin"


class DeparturesFlow(ConfigSubentryFlow):
    """Adding a stop: pick a region, place a pin on the map, then choose one of the stops nearest the pin.

    The region's stops are fetched once and the nearest ones are worked out here, so moving the pin needs no requests.
    """

    _regions: list[str] | None = None
    _region: str = ""
    _region_stops: list[dict[str, Any]] | None = None
    _location: dict[str, float] | None = None
    # Departure settings from the stop form, kept when going back to the map.
    _settings: dict[str, Any] | None = None

    def _client(self) -> RoutingClient | None:
        api_key = self._get_entry().data.get(CONF_API_KEY)
        return RoutingClient(async_get_clientsession(self.hass), api_key) if api_key else None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        client = self._client()
        if client is None:
            return self.async_abort(reason="api_key_missing")
        if self._regions is None:
            try:
                self._regions = await client.regions()
            except DigitransitAuthError:
                return self.async_abort(reason="invalid_api_key")
            except DigitransitError:
                return self.async_abort(reason="cannot_connect")

        errors: dict[str, str] = {}
        if user_input is not None:
            region = str(user_input[CONF_REGION])
            try:
                stops = await client.region_stops(region)
            except DigitransitAuthError:
                errors["base"] = "invalid_api_key"
            except DigitransitError:
                errors["base"] = "cannot_connect"
            else:
                if (centre := region_centre(stops)) is not None:
                    self._region = region
                    self._region_stops = stops
                    self._location = {"latitude": centre[0], "longitude": centre[1]}
                    return await self.async_step_location()
                errors[CONF_REGION] = "no_stops"

        options = [SelectOptionDict(value=value, label=label) for value, label in region_options(self._regions)]
        schema = vol.Schema(
            {
                vol.Required(CONF_REGION): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN, sort=False)
                )
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
            last_step=False,
        )

    async def async_step_location(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """The map, with the pin at the region's busiest spot or where it was left."""
        if self._region_stops is None or self._location is None:
            return await self.async_step_user()
        if user_input is not None:
            location = user_input[CONF_LOCATION]
            self._location = {"latitude": float(location["latitude"]), "longitude": float(location["longitude"])}
            return await self.async_step_stop()
        schema = vol.Schema(
            {vol.Required(CONF_LOCATION): LocationSelector(LocationSelectorConfig(radius=False, icon="mdi:bus-stop"))}
        )
        return self.async_show_form(
            step_id="location",
            data_schema=self.add_suggested_values_to_schema(schema, {CONF_LOCATION: self._location}),
            description_placeholders={"region": region_label(self._region)},
            last_step=False,
        )

    async def async_step_stop(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """The stops nearest the pin, and what the sensor shows. The last choice goes back to the map."""
        if self._region_stops is None or self._location is None:
            return await self.async_step_user()
        stops = nearest_stops(self._region_stops, self._location["latitude"], self._location["longitude"], STOP_CHOICES)
        listed = {str(stop["gtfsId"]): stop for stop in stops}

        if user_input is not None:
            self._settings = {
                key: user_input[key] for key in (CONF_DEPARTURES, CONF_LINES, CONF_UPDATE_SECONDS) if key in user_input
            }
            stop_id = str(user_input[CONF_STOP])
            if stop_id in listed:
                return self.async_create_entry(
                    title=stop_title(listed[stop_id]),
                    data={CONF_ROUTER: ROUTER, CONF_STOP: stop_id, **departure_settings(user_input)},
                )
            return await self.async_step_location()

        language = self._get_entry().data.get(CONF_LANGUAGE, "en")
        texts = await async_load_texts(self.hass, language)
        options = [SelectOptionDict(value=value, label=label) for value, label in stop_options(stops, language)]
        options.append(SelectOptionDict(value=MOVE_PIN, label=texts("move_pin")))
        schema = vol.Schema(
            {
                vol.Required(CONF_STOP): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST, sort=False)
                ),
                **departure_fields(),
            }
        )
        return self.async_show_form(
            step_id="stop",
            data_schema=self.add_suggested_values_to_schema(schema, {**DEPARTURE_DEFAULTS, **(self._settings or {})}),
            description_placeholders={"region": region_label(self._region)},
            last_step=True,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, data={**subentry.data, **departure_settings(user_input)}
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(departure_fields()), {**DEPARTURE_DEFAULTS, **subentry.data}
            ),
            description_placeholders={"stop": subentry.title},
        )
