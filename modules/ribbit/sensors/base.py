import logging

import asyncio


class BaseSensor:
    def __init__(self, registry, id):
        self._output = registry.sensors_output
        self._sensor_id = id
        self._logger = logging.getLogger("sensor." + self.config.name)


def find_sensor_by_id(registry, id, cls=None):
    for sensor in registry.sensors.values():
        if sensor._sensor_id == id and (cls is None or sensor.__class__ is cls):
            return sensor

    raise ValueError(f"Unknown sensor id ({id})")


def sensor_command(cls, command_method_name):
    def _command(registry, method, params):
        id = params.pop(0)
        sensor = find_sensor_by_id(registry, id, cls=cls)
        return getattr(sensor, command_method_name)(params)

    return _command


class PollingSensor(BaseSensor):
    def __init__(self, registry, id, interval):
        super().__init__(registry, id)
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
