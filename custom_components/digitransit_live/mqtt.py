"""The connection to Digitransit's MQTT broker.

paho-mqtt runs its own network thread and reconnects by itself. Messages are
decoded in that thread and handed to the Home Assistant event loop, where
everything else happens.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Callable, Iterable
from typing import Any

import paho.mqtt.client as mqtt
from homeassistant.util.ssl import get_default_context

from .const import DOMAIN, MQTT_HOST, MQTT_PORT
from .vehicles import VehicleReport, decode_report, feed_topic

_LOGGER = logging.getLogger(__name__)


class DigitransitMqtt:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        feed_ids: Iterable[str],
        on_report: Callable[[VehicleReport], None],
        host: str = MQTT_HOST,
        port: int = MQTT_PORT,
    ) -> None:
        self.connected = False
        self._loop = loop
        self._topics = sorted({feed_topic(feed_id) for feed_id in feed_ids})
        self._on_report = on_report
        self._host = host
        self._port = port

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{DOMAIN}-{secrets.token_hex(6)}")
        client.tls_set_context(get_default_context())
        client.reconnect_delay_set(min_delay=1, max_delay=120)
        client.on_connect = self._handle_connect
        client.on_disconnect = self._handle_disconnect
        client.on_message = self._handle_message
        self._client = client

    def start(self) -> None:
        """Starts connecting in the background. Returns at once; paho keeps reconnecting until stop()."""
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def stop(self) -> None:
        """Disconnects and stops the network thread. Blocks until the thread ends, so call it from an executor."""
        self._client.disconnect()
        self._client.loop_stop()

    # ---------------- paho callbacks, in paho's network thread ----------------

    def _handle_connect(
        self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any
    ) -> None:
        if reason_code.is_failure:
            _LOGGER.warning("Connecting to %s failed: %s", self._host, reason_code)
            return
        # Subscribing on every connect also restores the subscriptions after a reconnect.
        client.subscribe([(topic, 0) for topic in self._topics])
        self._call_in_loop(self._set_connected, True)

    def _handle_disconnect(
        self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any
    ) -> None:
        self._call_in_loop(self._set_connected, False)

    def _handle_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        report = decode_report(message.topic, message.payload, time.monotonic())
        if report is not None:
            self._call_in_loop(self._on_report, report)

    def _call_in_loop(self, callback: Callable[..., None], *args: Any) -> None:
        try:
            self._loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            # The event loop is closing; Home Assistant is shutting down.
            pass

    # ---------------- event loop ----------------

    def _set_connected(self, connected: bool) -> None:
        if connected != self.connected:
            _LOGGER.info("%s %s", "Connected to" if connected else "Disconnected from", self._host)
        self.connected = connected
