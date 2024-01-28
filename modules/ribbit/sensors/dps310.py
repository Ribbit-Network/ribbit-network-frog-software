import time
import asyncio
from micropython import const

import ribbit.config as _config
from ribbit.utils.time import isotime

from . import base as _base

DEFAULT_ADDR = const(0x77)

_scale_factors = [
    524288,
    1572864,
    3670016,
    7864320,
    253952,
    516096,
    1040384,
    2088960,
]


def _two_complement(val, bits):
    if val >> (bits - 1):
        val -= 1 << bits
    return val


class DPS310(_base.PollingSensor):
    config = _config.Object(
        name="dps310",
        keys=[
            _config.String(name="id"),
            _config.Integer(name="address"),
            _config.Integer(name="interval", default=60),
            _config.Integer(name="pressure_oversampling", default=6),
            _config.Integer(name="temperature_oversampling", default=6),
        ],
    )

    def __init__(
        self,
        registry,
        id,
        address,
        interval=60,
        pressure_oversampling=6,
        temperature_oversampling=6,
    ):
        super().__init__(registry, id, interval)

        self._i2c_bus = registry.i2c_bus
        self._i2c_addr = address

        self._buf = memoryview(bytearray(16))

        self._pressure_oversampling = pressure_oversampling
        self._pressure_scale = _scale_factors[self._pressure_oversampling]

        self._temperature_oversampling = temperature_oversampling
        self._temperature_scale = _scale_factors[self._temperature_oversampling]

        self._pressure_cfg = self._pressure_oversampling
        self._temperature_cfg = (1 << 7) | self._temperature_oversampling
        self._cfg_reg = 0
        if self._pressure_oversampling > 3:
            self._cfg_reg |= 1 << 2
        if self._pressure_oversampling > 3:
            self._cfg_reg |= 1 << 3

        self._initialized = False
        self._c0 = None
        self._c1 = None
        self._c00 = None
        self._c10 = None
        self._c01 = None
        self._c11 = None
        self._c20 = None
        self._c21 = None
        self._c30 = None

        self.last_update = None
        self.temperature = None
        self.pressure = None

    async def _read_coefficients(self):
        async with self._i2c_bus.lock:
            buf = self._i2c_bus.readfrom_mem(self._i2c_addr, 0x10, 18)

        self._c0 = _two_complement((buf[0] << 4) | (buf[1] >> 4), 12)
        self._c1 = _two_complement(((buf[1] & 0x0F) << 8) | buf[2], 12)
        self._c00 = _two_complement((buf[3] << 12) | (buf[4] << 4) | (buf[5] >> 4), 20)
        self._c10 = _two_complement(
            ((buf[5] & 0x0F) << 16) | (buf[6] << 8) | buf[7], 20
        )
        self._c01 = _two_complement((buf[8] << 8) | buf[9], 16)
        self._c11 = _two_complement((buf[10] << 8) | buf[11], 16)
        self._c20 = _two_complement((buf[12] << 8) | buf[13], 16)
        self._c21 = _two_complement((buf[14] << 8) | buf[15], 16)
        self._c30 = _two_complement((buf[16] << 8) | buf[17], 16)

    async def _read_register(self, addr, size):
        buf = self._buf[:size]
        async with self._i2c_bus.lock:
            self._i2c_bus.readfrom_mem_into(
                self._i2c_addr,
                addr,
                buf,
            )
            await asyncio.sleep_ms(10)
        return buf

    async def _write_register(self, addr, value):
        self._buf[0] = value
        async with self._i2c_bus.lock:
            self._i2c_bus.writeto_mem(
                self._i2c_addr,
                addr,
                self._buf[:1],
            )
            await asyncio.sleep_ms(10)

    async def _read_raw_measurement(self, addr):
        buf = await self._read_register(addr, 3)
        return _two_complement((buf[0] << 16) | (buf[1] << 8) | buf[0], 24)

    async def _wait_status(self, bit):
        while True:
            status = ((await self._read_register(0x08, 1))[0] >> bit) & 0x01
            if status:
                break
            await asyncio.sleep_ms(10)

    async def initialize(self):
        await self._write_register(0x0C, 0b1001)  # Generate a soft reset
        await asyncio.sleep_ms(10)

        await self._write_register(0x28, 1 << 7)

        buf = await self._read_register(0x0D, 1)
        rev_id = buf[0] >> 4
        prod_id = buf[0] & 0x0F
        self._logger.info(
            "Reading pressure from DPS310 (rev_id=%d, prod_id=%d)", rev_id, prod_id
        )
        await self._wait_status(7)

        self._logger.info("Reading coefficients")
        await self._read_coefficients()

        self._logger.info("Setting configuration")
        await self._write_register(0x06, self._pressure_cfg)
        await self._write_register(0x07, self._temperature_cfg)
        await self._write_register(0x09, self._cfg_reg)
        await self._wait_status(6)

        self._initialized = True

    async def read_once(self):
        if not self._initialized:
            await self.initialize()

        await self._write_register(0x08, 0x02)
        await self._wait_status(5)

        raw_temperature = (
            await self._read_raw_measurement(0x03) / self._temperature_scale
        )
        self.temperature = 0.5 * self._c0 + raw_temperature * self._c1

        await self._write_register(0x08, 0x01)
        await self._wait_status(4)

        raw_pressure = await self._read_raw_measurement(0x00) / self._pressure_scale
        self.pressure = (
            self._c00
            + raw_pressure
            * (self._c10 + raw_pressure * (self._c20 + raw_pressure * self._c30))
            + raw_temperature
            * (self._c01 + raw_pressure * (self._c11 + raw_pressure * self._c21))
        ) / 100

        self.last_update = time.time()

    def metadata(self):
        return {
            "pressure": {
                "label": "Pressure",
                "class": "pressure",
                "unit_of_measurement": "hPa",
                "suggested_display_precision": 1,
            },
            "temperature": {
                "label": "Temperature",
                "class": "temperature",
                "unit_of_measurement": "°C",
                "suggested_display_precision": 1,
            },
        }

    def export(self):
        return {
            "t": isotime(self.last_update),

            "temperature": self.temperature,
            "pressure": self.pressure,
        }
