import time
import asyncio

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
        # Write the command to read the voltage to the sensor.
        self._i2c_bus.writeto(self._i2c_addr, b"\x02")

        # Read the voltage from the sensor.
        self._i2c_bus.readfrom_into(self._i2c_addr, self._buf)

        # The voltage is a 12-bit value, so we need to combine the two bytes we read into a single value.
        # The voltage is in millivolts, so we need to divide by 16 to get the actual voltage.
        self.voltage = (self._buf[0] << 4) | (self._buf[1] >> 4)

    # The export method is called to get the data from the sensor.
    def export(self):
        # Return the voltage as a dictionary.
        return {
            "t": isotime(time.time()),
            "voltage": self.voltage,
        }