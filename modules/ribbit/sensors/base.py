import logging

import uasyncio as asyncio


class BaseSensor:
    def __init__(self, registry):
        self._output = registry.sensors_output
        self._logger = logging.getLogger("sensor." + self.config.name)


class PollingSensor(BaseSensor):
    def __init__(self, registry, interval):
        super().__init__(registry)
        self._interval_ms = int(interval * 1000)

    async def loop(self):
        while True:
            try:
                await self.read_once()
                await self._output.write(self.export())
            except Exception as exc:
                self._logger.exc(exc, "Exception in polling loop")

            await asyncio.sleep_ms(self._interval_ms)

    async def read_once(self):
        pass

    def export(self):
        return {}
