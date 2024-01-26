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
            for sensor_id, sensor in self._registry.sensors.items():
                ret[sensor_id] = sensor.export()

            ret["time_manager"] = self._registry.time_manager.export()

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