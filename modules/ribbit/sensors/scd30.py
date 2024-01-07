import time
import asyncio
from ustruct import unpack

from micropython import const

import ribbit.config as _config
from ribbit.utils.time import isotime

from . import base as _base

DEFAULT_ADDR = const(0x61)

_CMD_CONTINUOUS_MEASUREMENT = const(0x0010)
_CMD_SET_MEASUREMENT_INTERVAL = const(0x4600)
_CMD_GET_DATA_READY = const(0x0202)
_CMD_READ_MEASUREMENT = const(0x0300)
_CMD_AUTOMATIC_SELF_CALIBRATION = const(0x5306)
_CMD_SET_FORCED_RECALIBRATION_FACTOR = const(0x5204)
_CMD_SET_TEMPERATURE_OFFSET = const(0x5403)
_CMD_SET_ALTITUDE_COMPENSATION = const(0x5102)
_CMD_SOFT_RESET = const(0xD304)


_READ_DELAY_MS = const(10)

crc8_31 = b"\x00\x31\x62\x53\xc4\xf5\xa6\x97\xb9\x88\xdb\xea\x7d\x4c\x1f\x2e\x43\x72\x21\x10\x87\xb6\xe5\xd4\xfa\xcb\x98\xa9\x3e\x0f\x5c\x6d\x86\xb7\xe4\xd5\x42\x73\x20\x11\x3f\x0e\x5d\x6c\xfb\xca\x99\xa8\xc5\xf4\xa7\x96\x01\x30\x63\x52\x7c\x4d\x1e\x2f\xb8\x89\xda\xeb\x3d\x0c\x5f\x6e\xf9\xc8\x9b\xaa\x84\xb5\xe6\xd7\x40\x71\x22\x13\x7e\x4f\x1c\x2d\xba\x8b\xd8\xe9\xc7\xf6\xa5\x94\x03\x32\x61\x50\xbb\x8a\xd9\xe8\x7f\x4e\x1d\x2c\x02\x33\x60\x51\xc6\xf7\xa4\x95\xf8\xc9\x9a\xab\x3c\x0d\x5e\x6f\x41\x70\x23\x12\x85\xb4\xe7\xd6\x7a\x4b\x18\x29\xbe\x8f\xdc\xed\xc3\xf2\xa1\x90\x07\x36\x65\x54\x39\x08\x5b\x6a\xfd\xcc\x9f\xae\x80\xb1\xe2\xd3\x44\x75\x26\x17\xfc\xcd\x9e\xaf\x38\x09\x5a\x6b\x45\x74\x27\x16\x81\xb0\xe3\xd2\xbf\x8e\xdd\xec\x7b\x4a\x19\x28\x06\x37\x64\x55\xc2\xf3\xa0\x91\x47\x76\x25\x14\x83\xb2\xe1\xd0\xfe\xcf\x9c\xad\x3a\x0b\x58\x69\x04\x35\x66\x57\xc0\xf1\xa2\x93\xbd\x8c\xdf\xee\x79\x48\x1b\x2a\xc1\xf0\xa3\x92\x05\x34\x67\x56\x78\x49\x1a\x2b\xbc\x8d\xde\xef\x82\xb3\xe0\xd1\x46\x77\x24\x15\x3b\x0a\x59\x68\xff\xce\x9d\xac"


class CRCError(Exception):
    pass


def _crc8(a, b):
    crc = 0xFF
    crc = crc8_31[crc ^ a]
    crc = crc8_31[crc ^ b]
    return crc


def _decode16(buf):
    """Decode a buffer containing three bytes [MSB, LSB, CRC] from the sensor and return an int"""
    if _crc8(buf[0], buf[1]) != buf[2]:
        raise CRCError()

    return (buf[0] << 8) | buf[1]


def _decode_float(buf):
    """Decode a buffer containing two sets of three bytes from the sensor and return a float"""
    if _crc8(buf[0], buf[1]) != buf[2]:
        raise CRCError()
    if _crc8(buf[3], buf[4]) != buf[5]:
        raise CRCError()
    buf[2] = buf[3]
    buf[3] = buf[4]
    return unpack(">f", buf)[0]


def _encode16(buf, data):
    """Encode an 16 bit int into a set of three bytes [MSB, LSB, CRC]"""
    buf[0] = data >> 8
    buf[1] = data & 0xFF
    buf[2] = _crc8(buf[0], buf[1])


class SCD30(_base.PollingSensor):
    config = _config.Object(
        name="scd30",
        keys=[
            _config.String(name="id"),
            _config.Integer(name="address"),
            _config.Integer(name="interval", default=60),
        ],
    )

    def __init__(self, registry, id, address, interval=60):
        super().__init__(registry, id, interval)

        self._i2c_bus = registry.i2c_bus
        self._i2c_addr = address

        self._req_buf = memoryview(bytearray(5))
        self._resp_buf = memoryview(bytearray(18))

        if not 2 <= interval <= 1800:
            raise ValueError("measurement interval out of range")
        self._mesurement_interval = int(interval)
        self._mesurement_interval_ms = int(interval) * 1000

        self._initialized = False

        self._pressure_reference = 0
        self._pressure_updated = True

        self._temperature_reference = 0
        self._temperature_updated = False

        self.last_update = None
        self.co2 = None
        self.temperature = None
        self._temperature_offset = None
        self.humidity = None

    async def _read_register_into(self, addr, buf):
        async with self._i2c_bus.lock:
            req = self._req_buf[:2]
            req[0] = addr >> 8
            req[1] = addr & 0xFF
            self._i2c_bus.writeto(self._i2c_addr, req)
            await asyncio.sleep_ms(_READ_DELAY_MS)

            self._i2c_bus.readfrom_into(self._i2c_addr, buf)
            await asyncio.sleep_ms(_READ_DELAY_MS)

    async def _read_register(self, addr):
        buf = self._resp_buf[:3]
        await self._read_register_into(addr, buf)
        return _decode16(buf)

    async def _send_command(self, addr, value=None):
        if value is not None:
            buf = self._req_buf[:5]
            _encode16(buf[2:5], value)
        else:
            buf = self._req_buf[:2]

        buf[0] = addr >> 8
        buf[1] = addr & 0xFF
        async with self._i2c_bus.lock:
            self._i2c_bus.writeto(self._i2c_addr, buf)
            await asyncio.sleep_ms(_READ_DELAY_MS)

    def set_pressure(self, pressure):
        self._pressure_reference = pressure
        self._pressure_updated = True

    def set_temperature(self, temperature):
        self._temperature_reference = int(temperature * 100)
        self._temperature_updated = True

    async def _wait_measurement(self):
        count = 0
        while True:
            status = await self._read_register(_CMD_GET_DATA_READY)
            if status:
                return
            count += 1
            await asyncio.sleep_ms(100)

    async def initialize(self):
        self._send_command(_CMD_SET_MEASUREMENT_INTERVAL, self._mesurement_interval)

        self._temperature_offset = await self._read_register(
            _CMD_SET_TEMPERATURE_OFFSET
        )
        self._logger.info(
            "Current temperature offset: %.2f °C", self._temperature_offset / 100
        )

        self._send_command(_CMD_AUTOMATIC_SELF_CALIBRATION, 1)
        self._initialized = True

    async def read_once(self):
        if not self._initialized:
            await self.initialize()

        if self._pressure_updated:
            if self._pressure_reference != 0:
                self._logger.info(
                    "Submitting pressure data to the sensor (%d hPa)",
                    self._pressure_reference,
                )
            await self._send_command(
                _CMD_CONTINUOUS_MEASUREMENT,
                int(self._pressure_reference),
            )
            self._pressure_updated = False

        if self._temperature_updated and self.temperature is not None:
            offset = (
                int(self.temperature * 100)
                - self._temperature_reference
                + self._temperature_offset
            )
            if offset < 0:
                offset = 0
            self._logger.info(
                "Submitting temperature offset to the sensor (%.2f °C)",
                offset / 100,
            )
            await self._send_command(_CMD_SET_TEMPERATURE_OFFSET, offset)
            self._temperature_offset = offset
            self._temperature_updated = False

        await self._wait_measurement()

        buf = self._resp_buf[:18]
        await self._read_register_into(_CMD_READ_MEASUREMENT, buf)

        co2 = _decode_float(buf[0:6])
        temperature = _decode_float(buf[6:12])
        humidity = _decode_float(buf[12:18])

        self.last_update = time.time()
        self.co2 = co2
        self.temperature = temperature
        self.humidity = humidity

    def export(self):
        t = isotime(self.last_update)
        sensor_id = self._sensor_id
        co2_concentration = self.co2
        temperature = self.temperature
        temperature_offset = (
            self._temperature_offset / 100
            if self._temperature_offset is not None
            else None
        )
        humidity = self.humidity

        return [
            {
                "t": t,
                "@type": "ribbitnetwork.sensor.Concentration",
                "sensor_model": "scd30",
                "sensor_id": sensor_id,
                "gas_type": "co2",
                "concentration": co2_concentration,
                "scd30": {
                    "temperature": temperature,
                    "temperature_offset": temperature_offset,
                    "humidity": humidity,
                },
            },
            {
                "t": t,
                "@type": "ribbitnetwork.sensor.Temperature",
                "sensor_model": "scd30",
                "sensor_id": sensor_id,
                "temperature": temperature,
            },
            {
                "t": t,
                "@type": "ribbitnetwork.sensor.Humidity",
                "sensor_model": "scd30",
                "sensor_id": sensor_id,
                "humidity": humidity,
            },
        ]
