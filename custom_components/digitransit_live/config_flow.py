"""Config flow.

The config entry holds only the language. Each feed is a config subentry of
type "vehicles", added and changed from the integration page.
"""

from __future__ import annotations

import re
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
from homeassistant.core import callback
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
)

from .const import (
    CONF_AREA,
    CONF_FEED,
    CONF_LANGUAGE,
    CONF_LINES,
    CONF_MAX_AGE_MINUTES,
    CONF_UPDATE_SECONDS,
    CONF_USE_AREA,
    DEFAULT_MAX_AGE_MINUTES,
    DEFAULT_UPDATE_SECONDS,
    DOMAIN,
    FEEDS,
    LANGUAGES,
    MIN_UPDATE_SECONDS,
    SUBENTRY_VEHICLES,
)

DEFAULT_RADIUS_M = 10_000

# Feed ids and line numbers become MQTT topic levels or filters: no slashes or wildcards.
FEED_ID = re.compile(r"^[A-Za-z0-9_-]+$")
LINE = re.compile(r"^[^/#+\s]{1,20}$")


def language_schema(default: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_LANGUAGE, default=default): SelectSelector(
                SelectSelectorConfig(options=LANGUAGES, translation_key=CONF_LANGUAGE, mode=SelectSelectorMode.DROPDOWN)
            )
        }
    )


class DigitransitLiveConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Digitransit", data=user_input)
        language = self.hass.config.language[:2]
        default = language if language in LANGUAGES else "en"
        return self.async_show_form(step_id="user", data_schema=language_schema(default))

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            # The update listener in __init__.py reloads the entry.
            self.hass.config_entries.async_update_entry(entry, data={**entry.data, **user_input})
            return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(step_id="reconfigure", data_schema=language_schema(entry.data[CONF_LANGUAGE]))

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_VEHICLES: VehicleFeedFlow}


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
