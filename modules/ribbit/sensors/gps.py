import time

import uasyncio as asyncio
from micropython import const
import ribbit.config as _config
import ribbit.time_manager as _time
from ribbit.utils.time import isotime

from . import base as _base

_MAX_NMEA_PACKET_LEN = const(80)

_STATE_PACKET_START = const(0)
_STATE_PACKET_DATA = const(1)
_STATE_PACKET_CHECKSUM = const(2)
_STATE_PACKET_CHECKSUM2 = const(3)
_STATE_PACKET_END = const(4)

DEFAULT_ADDR = const(0x10)


def _append_checksum(packet):
    checksum = 0
    for c in packet[1:]:
        checksum ^= c
    return b"%s*%02x\r\n" % (
        packet,
        checksum,
    )


class GPS(_base.BaseSensor):
    config = _config.Object(
        name="gps",
        keys=[
            _config.Integer(name="address"),
            _config.Integer(name="interval", default=60),
        ],
    )

    def __init__(self, registry, address, interval=60):
        super().__init__(registry)
        self._i2c_bus = registry.i2c_bus
        self._i2c_addr = address
        self._report_interval = interval
        self._time_manager = registry.time_manager

        self.last_update = None
        self.last_fix = None
        self.latitude = None
        self.longitude = None
        self.altitude = None
        self.geoid_height = None
        self.has_fix = False
        self.satellites = 0
        self._first_fix = False
        self._last_time_update = None

        self._stop_event = asyncio.Event()

    async def loop(self):
        while True:
            try:
                await self._read_loop_inner()
            except Exception as exc:
                self._logger.exc(exc, "Error in GPS loop")
                await asyncio.sleep_ms(1000)

    async def _read_loop_inner(self):
        async with self._i2c_bus.lock:
            # Reduce the noise by only enabling the GNGGA sequence:
            self._i2c_bus.writeto(
                self._i2c_addr,
                _append_checksum(b"$PMTK314,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0"),
            )
            # Only return a fix every 10s
            self._i2c_bus.writeto(
                self._i2c_addr,
                _append_checksum(
                    b"$PMTK300,%d,0,0,0,0" % int(self._report_interval * 1000)
                ),
            )

        buf = bytearray(255)

        pkt = bytearray(_MAX_NMEA_PACKET_LEN)
        pkt_mv = memoryview(pkt)
        pkt_len = 0
        checksum = 0
        expected_checksum = 0
        state = _STATE_PACKET_START
        poll_interval = (self._report_interval * 1000) // 2
        poll_interval += 1000

        previous_update = None

        while True:
            async with self._i2c_bus.lock:
                self._i2c_bus.readfrom_into(self._i2c_addr, buf)

            seen_data = False
            for c in buf:
                if c == 0x0A:  # \n
                    continue

                seen_data = True

                if state == _STATE_PACKET_START:
                    if c == 0x24:  # $
                        pkt_len = 0
                        checksum = 0
                        expected_checksum = 0
                        state = _STATE_PACKET_DATA

                elif state == _STATE_PACKET_DATA:
                    if c == 0x2A:  # *
                        state = _STATE_PACKET_CHECKSUM
                    else:
                        pkt[pkt_len] = c
                        pkt_len += 1
                        checksum ^= c
                        if (
                            pkt_len == _MAX_NMEA_PACKET_LEN
                        ):  # Overlong packet, start over
                            state = _STATE_PACKET_START
                            continue

                elif (
                    state == _STATE_PACKET_CHECKSUM or state == _STATE_PACKET_CHECKSUM2
                ):
                    val = 0
                    if 48 <= c <= 57:  # 0-9
                        val = c - 48
                    elif 65 <= c <= 90:  # A-Z
                        val = 10 + c - 65
                    else:  # Malformed checksum byte (not in 0-9A-Z), start over
                        state = _STATE_PACKET_START
                        continue

                    expected_checksum = (expected_checksum << 4) + val
                    state += 1

                elif state == _STATE_PACKET_END:
                    if c == 0x0D and checksum == expected_checksum and len(pkt) >= 5:
                        self._parse_packet(pkt_mv[0:pkt_len])

                    state = _STATE_PACKET_START

            if not seen_data and previous_update != self.last_update:
                previous_update = self.last_update
                await self._output.write(self.export())

            try:
                await asyncio.wait_for_ms(
                    self._stop_event.wait(),
                    5 if seen_data else poll_interval,
                )
                return
            except asyncio.TimeoutError:
                pass

    def _parse_packet(self, pkt):
        if pkt[0:6] == b"GNGGA,":
            parts = bytes(pkt[6:]).split(b",")
            if len(parts) != 14:
                return

            self.has_fix = parts[5] != b"0"
            self.satellites = int(parts[6])
            self.last_update = time.time()

            if self.has_fix:
                latitude_raw = parts[1]
                if latitude_raw != b"":
                    if latitude_raw[4:5] != b".":
                        return
                    latitude = float(latitude_raw[:2]) + float(latitude_raw[2:]) / 60
                    if parts[2] == b"S":
                        latitude = -latitude
                else:
                    latitude = None

                longitude_raw = parts[3]
                if longitude_raw != b"":
                    if longitude_raw[5:6] != b".":
                        return
                    longitude = float(longitude_raw[:3]) + float(longitude_raw[3:]) / 60
                    if parts[4] == b"W":
                        longitude = -longitude
                else:
                    longitude = None

                self.last_fix = self.last_update
                self.latitude = latitude
                self.longitude = longitude

                altitude_raw = parts[8]
                if altitude_raw != b"":
                    self.altitude = float(altitude_raw)

                geoid_height_raw = parts[10]
                if geoid_height_raw != b"":
                    self.geoid_height = float(geoid_height_raw)

                if not self._first_fix:
                    self._logger.info(
                        "Got GPS fix: latitude=%f longitude=%f satellites=%d",
                        self.latitude,
                        self.longitude,
                        self.satellites,
                    )
                    self._first_fix = True

        elif pkt[0:6] == b"GNZDA,":
            if not self.has_fix:
                # The GPS could return bogus date/time before it has a fix.
                # To be on the safe side, only consider ZDA packets emitted while
                # the GPS has a fix.
                return

            parts = bytes(pkt[6:]).split(b",")
            if len(parts) != 6:
                return

            timepart = parts[0]
            hour = int(timepart[0:2])
            minute = int(timepart[2:4])
            second = int(timepart[4:6])
            day = int(parts[1])
            month = int(parts[2])
            year = int(parts[3])

            if self._time_manager is not None:
                t = time.mktime((year, month, day, hour, minute, second, 0, 0))
                self._time_manager.set_time(_time.TIMESOURCE_GPS, t)

    async def read_once(self):
        pass

    def export(self):
        return {
            "t": isotime(self.last_update),
            "@type": "ribbitnetwork/sensor.gps",
            "last_fix": isotime(self.last_fix),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "geoid_height": self.geoid_height,
            "has_fix": self.has_fix,
            "satellites": self.satellites,
        }
