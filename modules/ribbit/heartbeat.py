import time
import logging
import uasyncio as asyncio


class Heartbeat:
    def __init__(self, in_simulator):
        self._in_simulator = in_simulator
        self._logger = logging.getLogger(__name__)

        if not self._in_simulator:
            self._setup_pixel()
            asyncio.create_task(self._loop())

    def _setup_pixel(self):
        import neopixel
        import machine

        machine.Pin(21, machine.Pin.OUT, value=1)
        neo_ctrl = machine.Pin(33, machine.Pin.OUT)
        self._pixel = neopixel.NeoPixel(neo_ctrl, 1)

    async def _loop(self):
        interval = 200
        warn_interval = 300

        on = True
        px = self._pixel

        while True:
            if not self._in_simulator:
                if on:
                    px[0] = (4, 2, 0)
                else:
                    px[0] = (0, 0, 0)
                on = not on
                px.write()

            start = time.ticks_ms()
            await asyncio.sleep_ms(interval)
            duration = time.ticks_diff(time.ticks_ms(), start)

            if duration > warn_interval:
                self._logger.warning(
                    "Event loop blocked for %d ms", duration - interval
                )
