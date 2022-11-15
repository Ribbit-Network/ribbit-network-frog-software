import collections
import logging
import network
import uasyncio as asyncio

import ribbit.config as _config
from ribbit.utils.asyncio import WatchableValue


CONFIG_WIFI_SSID = const("wifi.ssid")
CONFIG_WIFI_PASSWORD = const("wifi.password")


CONFIG_KEYS = [
    _config.ConfigKey(CONFIG_WIFI_SSID, None, _config.String),
    _config.ConfigKey(CONFIG_WIFI_PASSWORD, None, _config.String, protected=True),
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


class NetworkManager:
    def __init__(
        self, config, poll_interval_connected_ms=5000, poll_interval_connecting_ms=500
    ):
        self._config = config
        self._iface = network.WLAN(network.STA_IF)
        self._logger = logging.getLogger(__name__)

        self._reconnect_event = asyncio.Event()
        self.state = WatchableValue(_state_disconnected)

        self._network_loop_task = asyncio.create_task(self._network_loop())
        self._poll_interval_connected_ms = poll_interval_connected_ms
        self._poll_interval_connecting_ms = poll_interval_connecting_ms

    def force_reconnect(self, reason="unknown reason"):
        if not self._reconnect_event.is_set():
            self._logger.info("Forcing a reconnection: %s", reason)
            self._reconnect_event.set()

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

                else:
                    self.state.set(_state_disconnected)

                if (
                    force_reconnect
                    or not connection_started
                    or (connection_started and not has_config)
                ):
                    self._logger.info("Deactivating wifi")
                    self.state.set(_state_disconnected)
                    iface.active(False)
                    connection_started = False

                if has_config and not connection_started:
                    self._reconnect_event.clear()

                    self._logger.info("Activating to wifi")
                    self.state.set(_state_connecting)
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
