import collections
import logging
import network
import uasyncio as asyncio
from micropython import const

import ribbit.config as _config
from ribbit.utils.asyncio import WatchableValue


CONFIG_WIFI_SSID = const("wifi.ssid")
CONFIG_WIFI_PASSWORD = const("wifi.password")


CONFIG_KEYS = [
    _config.ConfigKey(CONFIG_WIFI_SSID, None, _config.String()),
    _config.ConfigKey(CONFIG_WIFI_PASSWORD, None, _config.String(), protected=True),
]


State = collections.namedtuple(
    "State", ["state", "connected", "ip", "netmask", "gateway", "dns"]
)

_state_disconnected = State(
    state=network.STAT_IDLE,
    connected=False,
    ip=None,
    netmask=None,
    gateway=None,
    dns=None,
)

_state_connecting = State(
    state=network.STAT_CONNECTING,
    connected=False,
    ip=None,
    netmask=None,
    gateway=None,
    dns=None,
)


class _ConnectionRequest:
    def __init__(self, network_manager, timeout_ms=None):
        self._network_manager = network_manager
        self._timeout_ms = timeout_ms

    async def __aenter__(self):
        self._network_manager._connected_refs += 1
        if self._network_manager._connected_refs == 0:
            self._network_manager._connected_ref_event.set()

        if self._timeout_ms is not None:
            await asyncio.wait_for_ms(
                self._network_manager.connected.wait(), self._timeout_ms
            )
        else:
            await self._network_manager.connected.wait()

    async def __aexit__(self, exc_type, exc, tb):
        self._network_manager._connected_refs -= 1
        if self._network_manager._connected_refs == 0:
            self._network_manager._connected_ref_event.set()


class NetworkManager:
    def __init__(
        self,
        config,
        always_on=True,
        poll_interval_connected_ms=5000,
        poll_interval_connecting_ms=500,
    ):
        self._config = config
        self._iface = network.WLAN(network.STA_IF)
        self._iface.active(False)
        self._logger = logging.getLogger(__name__)

        self._reconnect_event = asyncio.Event()
        self.state = WatchableValue(_state_disconnected)
        self.connected = asyncio.Event()

        self._network_loop_task = asyncio.create_task(self._network_loop())
        self._poll_interval_connected_ms = poll_interval_connected_ms
        self._poll_interval_connecting_ms = poll_interval_connecting_ms

        self._on_connect_tasks = []

        self._connected_refs = 0
        self._connected_ref_event = asyncio.Event()

        if always_on:
            self._connected_refs += 1

    def connection(self, timeout_ms=None):
        """Returns a context manager that ensures that the network is connected"""
        return _ConnectionRequest(self, timeout_ms=timeout_ms)

    def force_reconnect(self, reason="unknown reason"):
        if not self._reconnect_event.is_set():
            self._logger.info("Forcing a reconnection: %s", reason)
            self._reconnect_event.set()

    def on_connect_task(self, cb):
        self._on_connect_tasks.append(cb)

    async def scan(self):
        # Force cancel the network loop, as most chips do not support
        # scanning while connecting / being connected.
        self._network_loop_task.cancel()
        try:
            await self._network_loop_task
        except asyncio.CancelledError:
            pass

        try:
            iface = self._iface
            iface.active(False)
            iface.active(True)
            return iface.scan()

        finally:
            iface.active(False)
            self._network_loop_task = asyncio.create_task(self._network_loop())

    async def _network_loop(self):
        while True:
            try:
                await self._network_loop_inner()
            except Exception as exc:
                self._logger.exc(exc, "Network loop crashed")
                await asyncio.sleep_ms(1000)

    async def _network_loop_inner(self):
        with self._config.watch(CONFIG_WIFI_SSID, CONFIG_WIFI_PASSWORD) as cfg_watcher:
            iface = self._iface
            connection_started = False

            while True:
                force_reconnect = cfg_watcher.changed or self._reconnect_event.is_set()
                ssid, password = cfg_watcher.get()
                has_config = ssid is not None and password is not None
                should_connect = has_config and (self._connected_refs > 0)

                status = iface.status()
                if status == network.STAT_GOT_IP:
                    config = iface.ifconfig()
                    self.state.set(
                        State(
                            state=status,
                            connected=True,
                            ip=config[0],
                            netmask=config[1],
                            gateway=config[2],
                            dns=config[3],
                        )
                    )
                    if not self.connected.is_set():
                        self.connected.set()
                        for task in self._on_connect_tasks:
                            await task(self.state.value)

                else:
                    self.state.set(_state_disconnected)
                    self.connected.clear()

                if force_reconnect or (connection_started and not should_connect):
                    self._logger.info("Deactivating wifi")
                    self.state.set(_state_disconnected)
                    iface.active(False)
                    connection_started = False

                if not connection_started and should_connect:
                    self._reconnect_event.clear()

                    self._logger.info("Activating wifi")
                    self.state.set(_state_connecting)
                    iface.active(False)
                    iface.active(True)
                    iface.connect(ssid, password)
                    connection_started = True

                if not has_config:
                    await cfg_watcher.wait()
                    continue

                poll_interval = (
                    self._poll_interval_connecting_ms
                    if self.state.value.state != network.STAT_GOT_IP
                    else self._poll_interval_connected_ms
                )

                try:
                    await asyncio.wait_for_ms(cfg_watcher.wait(), poll_interval)
                except asyncio.TimeoutError:
                    pass
