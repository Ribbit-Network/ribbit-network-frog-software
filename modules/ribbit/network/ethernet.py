import machine
import network

from .base import _Driver


class _EthernetDriver(_Driver):
    def __init__(self, i2c_bus, ifconfig=None):
        self._ifconfig = ifconfig

        self._i2c_bus = i2c_bus

        spi = machine.SPI(
            1,
            sck=machine.Pin(36),
            mosi=machine.Pin(35),
            miso=machine.Pin(37),
        )

        self._iface = network.LAN(
            phy_type=network.PHY_W5500,
            phy_addr=1,
            spi=spi,
            cs=machine.Pin(10),
            int=machine.Pin(12),
        )

    async def connect(self, disconnect_event):
        if self._iface.active():
            self._iface.active(False)

        async with self._i2c_bus.lock:
            mac = self._i2c_bus.readfrom_mem(80, 0xFA, 6)

        self._iface.config(mac=mac)

        self._iface.active(True)

        if self._ifconfig is not None:
            self._iface.ifconfig(self._ifconfig)

    def status(self):
        status = self._iface.status()
        if status == network.ETH_CONNECTED:
            return network.STAT_CONNECTING
        elif status == network.ETH_GOT_IP:
            return network.STAT_GOT_IP
        else:
            return network.STAT_IDLE

    def ifconfig(self):
        return self._iface.ifconfig()
