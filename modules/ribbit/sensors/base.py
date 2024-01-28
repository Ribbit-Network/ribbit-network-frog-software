import logging

import asyncio


class BaseSensor:
    def __init__(self, registry, id):
        self._output = registry.sensors_output
        self._sensor_id = id
        self._logger = logging.getLogger("sensor." + self.config.name)

    def metadata(self):
        return {}

    def export(self):
        return {}


class PollingSensor(BaseSensor):
    def __init__(self, registry, id, interval):
        super().__init__(registry, id)
        self._interval_ms = int(interval * 1000)

    async def loop(self):
        while True:
            try:
                await self.read_once()
                await self._output.write(self, self.export())
            except Exception as exc:
                self._logger.exc(exc, "Exception in polling loop")

            await asyncio.sleep_ms(self._interval_ms)

    async def read_once(self):
        pass
