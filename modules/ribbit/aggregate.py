from ribbit.utils.time import isotime
import time
import logging
import uasyncio as asyncio
import collections
import json

import ribbit.coap as _coap


class SensorAggregator:
    def __init__(self, registry):
        self._logger = logging.getLogger(__name__)
        self._registry = registry

        asyncio.create_task(self._loop())


    async def _loop(self):
        while True:
            # Send a data point every 5 seconds
            await asyncio.sleep_ms(5000)

            ret = collections.OrderedDict()
            for sensor in self._registry.sensors.values():
                if sensor.config.name == "dps310":
                    ret[sensor.config.name] = {
                        "temperature": sensor.temperature,
                        "pressure": sensor.pressure,
                        "t": isotime(sensor.last_update),
                    }
                elif sensor.config.name == "scd30":
                    ret[sensor.config.name] = {
                        "temperature": sensor.temperature,
                        "co2": sensor.co2,
                        "humidity": sensor.humidity,
                        "t": isotime(sensor.last_update),
                    }
                elif sensor.config.name == "gps":
                    ret[sensor.config.name] = {
                        "has_fix": sensor.has_fix,
                        "latitude": sensor.latitude,
                        "longitude": sensor.longitude,
                        "altitude": sensor.altitude,
                        "t": isotime(sensor.last_update),
                    }
                elif sensor.config.name == "memory":
                    ret[sensor.config.name] = {
                        "allocated": sensor.allocated,
                        "free": sensor.free,
                    }


            self._logger.info("Aggregated Data: %s", json.dumps(ret))
            try:
                coap = self._registry.golioth._coap
                await coap.post(
                    ".s/" + "ribbitnetwork.datapoint",
                    json.dumps(ret),
                    format=_coap.CONTENT_FORMAT_APPLICATION_JSON,
                )
            except Exception:
                pass