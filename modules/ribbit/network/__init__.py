import binascii
import collections
import logging
import machine
import network
import uasyncio as asyncio
from micropython import const

import ribbit.config as _config
from ribbit.utils.asyncio import WatchableValue


CONFIG_NETWORK = const("network")


IFCONFIG_KEYS = [
    _config.String(name="ip"),
    _config.String(name="netmask"),
    _config.String(name="gateway"),
    _config.String(name="dns"),
]


CONFIG_KEYS = [
    _config.TypedObject(
        name=CONFIG_NETWORK,
        type_key="type",
        types=[
            _config.Object(
                name="none",
                keys=[],
            ),
            _config.Object(
                name="wifi",
                keys=[
                    _config.String(name="ssid", default=_config.required),
                    _config.String(name="password"),
                ]
                + IFCONFIG_KEYS,
            ),
            _config.Object(
                name="wifi-ap",
                keys=[
                    _config.String(name="ssid", default=_config.required),
                ],
            ),
            _config.Object(
                name="gsm",
                keys=[
                    _config.String(name="apn", default=_config.required),
                ],
            ),
            _config.Object(
                name="ethernet",
                keys=[] + IFCONFIG_KEYS,
            ),
        ],
    ),
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
        i2c_bus,
        always_on=True,
        poll_interval_connected_ms=5000,
        poll_interval_connecting_ms=500,
    ):
        self._config = config
        self._logger = logging.getLogger(__name__)

        self._i2c_bus = i2c_bus

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
            iface = network.WLAN(network.STA_IF)
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
        with self._config.watch(CONFIG_NETWORK) as cfg_watcher:
            driver = None
            connection_task = None
            disconnect_event = asyncio.Event()

            while True:
                force_reconnect = cfg_watcher.changed or self._reconnect_event.is_set()
                config = cfg_watcher.get()[0]
                if driver is None and config is not None and config["type"] != "none":
                    if config["type"] == "wifi" or config["type"] == "ethernet":
                        ifconfig = None
                        if config["ip"] is not None:
                            ifconfig = (
                                config["ip"],
                                config["netmask"],
                                config["gateway"],
                                config["dns"],
                            )

                        if config["type"] == "wifi":
                            from .wlan import _WLANDriver

                            driver = _WLANDriver(
                                ssid=config["ssid"],
                                password=config["password"],
                                ifconfig=ifconfig,
                            )

                        elif config["type"] == "ethernet":
                            from .ethernet import _EthernetDriver

                            driver = _EthernetDriver(
                                i2c_bus=self._i2c_bus,
                                ifconfig=ifconfig,
                            )

                    elif config["type"] == "wifi-ap":
                        from .wlan import _WLANDriver

                        machine_id = binascii.hexlify(machine.unique_id()).decode(
                            "ascii"
                        )
                        driver = _WLANDriver(
                            ssid=f"frog-{machine_id}",
                            password=None,
                            ap_mode=True,
                        )

                    elif config["type"] == "gsm":
                        from .gsm import _GSMDriver

                        uart = machine.UART(
                            2,
                            baudrate=115200,
                            bits=8,
                            parity=None,
                            stop=1,
                            rx=38,
                            tx=39,
                            rts=11,
                            cts=10,
                        )

                        driver = _GSMDriver(
                            uart=uart,
                            apn="hologram",
                        )

                    else:
                        raise ValueError("unsupported network type")

                if driver is not None:
                    status = driver.status()
                    poll_interval = self._poll_interval_connecting_ms
                    if status == network.STAT_GOT_IP:
                        config = driver.ifconfig()
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
                            self._logger.info("Network is up, ip=%s", config[0])
                            self.connected.set()
                            for task in self._on_connect_tasks:
                                await task(self.state.value)

                        poll_interval = self._poll_interval_connected_ms

                    elif self.connected.is_set():
                        self.state.set(_state_connecting)
                        self.connected.clear()

                    should_connect = self._connected_refs > 0

                    if connection_task is not None and (
                        force_reconnect or not should_connect
                    ):
                        self._logger.info("Deactivating network")
                        self.state.set(_state_disconnected)
                        disconnect_event.set()
                        await connection_task
                        connection_task = None
                        driver = None
                        continue

                    if connection_task is None and should_connect:
                        self._reconnect_event.clear()

                        self._logger.info("Activating network")
                        self.state.set(_state_connecting)
                        disconnect_event.clear()
                        connection_task = asyncio.create_task(
                            driver.connect(disconnect_event)
                        )

                    try:
                        await asyncio.wait_for_ms(cfg_watcher.wait(), poll_interval)
                    except asyncio.TimeoutError:
                        pass

                else:
                    await cfg_watcher.wait()
