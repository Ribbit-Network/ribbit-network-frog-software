import time
import asyncio

from struct import unpack

import ribbit.config as _config
from ribbit.utils.time import isotime

from . import base as _base

# A sensor that reads the battery voltage and reports it.
# Inherits from PollingSensor, which means it will be polled at regular intervals.
# The battery sensor on the board is the max17048 sensor.
# That sensor can be found on the main i2c bus at address 0x36.

class Battery(_base.PollingSensor):
    # The configuration schema for the battery sensor.
    config = _config.Object(
        name="battery",
        keys=[
            _config.Integer(name="interval", default=60),
        ],
    )

    REG_VCELL = 0x02
    ADDRESS = 0x36

    # The constructor for the battery sensor.
    # The registry is passed in, which contains the i2c bus.
    # The id is the id of the sensor, and the interval is the interval at which the sensor should be polled.
    def __init__(self, registry, id, interval=60):
        # Call the constructor of the base class.
        super().__init__(registry, id, interval)

        # The i2c bus is stored in the registry, so we can access it here.
        self._i2c_bus = registry.i2c_bus

        # The address of the max17048 sensor.
        self._i2c_addr = 0x36

        # The buffer to read the data into.
        self._buf = memoryview(bytearray(2))

    # The read_once method is called every time the sensor is polled.
    async def read_once(self):
        # Read the two bytes of voltage from the sensor.
        bytes = self._i2c_bus.readfrom_mem(self.ADDRESS, self.REG_VCELL, 2)
        self.voltage = unpack(">H", bytes)[0] * 78.125 / 1_000_000

    # The export method is called to get the data from the sensor.
    def export(self):
        # Return the voltage as a dictionary.
        return {
            "t": isotime(time.time()),
            "voltage": self.voltage,
        }