import uasyncio as asyncio
import network

from .base import _Driver


class _WLANDriver(_Driver):
    def __init__(self, ssid, password, ifconfig=None, ap_mode=False):
        self._ssid = ssid
        self._password = password
        self._ifconfig = ifconfig
        self._ap_mode = ap_mode

        self._iface = network.WLAN(network.STA_IF if not ap_mode else network.AP_IF)

    async def connect(self, disconnect_event):
        if self._iface.active():
            self._iface.active(False)
        self._iface.active(True)
        await asyncio.sleep_ms(1_000)

        if self._ap_mode:
            self._iface.config(ssid=self._ssid)

        if self._ifconfig is not None:
            self._iface.ifconfig(self._ifconfig)

        if not self._ap_mode:
            self._iface.connect(self._ssid, self._password)

        await disconnect_event.wait()

    def status(self):
        return self._iface.status()

    def ifconfig(self):
        return self._iface.ifconfig()
