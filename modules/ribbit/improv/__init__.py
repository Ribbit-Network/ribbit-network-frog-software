import asyncio
import sys
import micropython
from micropython import const
import logging


_header = const(b"IMPROV")
_version = const(b"1")

STATE_READY = const(0x02)
STATE_PROVISIONING = const(0x03)
STATE_PROVISIONED = const(0x04)

_ERROR_NO_ERROR = const(0x00)
_ERROR_INVALID_PACKET = const(0x01)
_ERROR_UNKNOWN_COMMAND = const(0x02)
_ERROR_UNABLE_TO_CONNECT = const(0x03)
_ERROR_UNKNOWN = const(0xFF)

_PACKET_CURRENT_STATE = const(0x01)
_PACKET_ERROR_STATE = const(0x02)
_PACKET_RPC_COMMAND = const(0x03)
_PACKET_RPC_RESULT = const(0x04)

_RPC_SEND_SETTINGS = const(0x01)
_RPC_REQUEST_CURRENT_STATE = const(0x02)
_RPC_REQUEST_DEVICE_INFO = const(0x03)
_RPC_REQUEST_SCAN_NETWORKS = const(0x04)


def _decode_string(buf):
    length = buf[0]
    return buf[1 + length :], buf[1 : 1 + length]


class _PacketBuilder:
    def __init__(self):
        self._buffer = memoryview(bytearray(256))
        self._buffer[0:6] = b"IMPROV"
        self._buffer[6] = 0x01
        self._idx = 0
        self._is_command = False

    def _append(self, c):
        self._buffer[self._idx] = c
        self._idx += 1

    def _append_string(self, s):
        if isinstance(s, str):
            s = s.encode("utf-8")
        self._buffer[self._idx] = len(s)
        self._idx += 1
        self._buffer[self._idx : self._idx + len(s)] = s
        self._idx += len(s)

    def _init_packet(self, typ, command=None):
        self._buffer[7] = typ
        self._idx = 9
        if command:
            self._buffer[self._idx] = command
            self._idx += 2
            self._is_command = True
        else:
            self._is_command = False

    def _finalize_packet(self):
        self._buffer[8] = self._idx - 9  # Length

        if self._is_command:
            self._buffer[10] = self._idx - 11

        checksum = 0
        for c in self._buffer[: self._idx]:
            checksum = (checksum + c) & 0xFF

        self._buffer[self._idx] = checksum
        self._idx += 1
        return self._buffer[: self._idx]


class ImprovHandler:
    def __init__(
        self,
        product_name,
        product_version,
        hardware_name,
        device_name,
        scan_wifi_cb,
        set_wifi_settings_cb,
        current_state_cb,
        logger=None,
    ):
        if logger is None:
            logger = logging.getLogger(__name__)
        self._logger = logger

        micropython.kbd_intr(-1)

        self._input = asyncio.StreamReader(sys.stdin.buffer)
        self._output = asyncio.StreamWriter(sys.stdout.buffer)

        self._builder = _PacketBuilder()

        self._product_name = product_name
        self._product_version = product_version
        self._hardware_name = hardware_name
        self._device_name = device_name

        self._scan_wifi_cb = scan_wifi_cb
        self._set_wifi_settings_cb = set_wifi_settings_cb
        self._current_state_cb = current_state_cb

        asyncio.create_task(self._improv_loop())

    async def _improv_loop(self):
        while True:
            try:
                await self._improv_loop_inner()
            except Exception as exc:
                self._logger.exc(exc, "Error in IMPROV loop")
                await asyncio.sleep_ms(1000)

    async def _improv_loop_inner(self):
        input_buf = memoryview(bytearray(1))
        buf = memoryview(bytearray(256))
        state = 0
        idx = 0
        calculated_checksum = 0

        while True:
            await self._input.readinto(input_buf)
            c = input_buf[0]

            if state == 10:
                state = 0
                if calculated_checksum != c:
                    self._logger.info("Failed checksum!")
                    continue

                await self._process_packet(packet_type, buf[:idx])
                continue

            if state != 0:
                calculated_checksum = (calculated_checksum + c) & 0xFF

            if state == 0 and c == 0x03:  # CTRL+C
                raise KeyboardInterrupt()

            if 0 <= state < len(_header):
                if c != _header[state]:
                    state = 0
                    continue
                if state == 0:
                    calculated_checksum = c
                state += 1

            elif state == 6:  # version
                if c != 1:
                    state = 0
                    continue
                state += 1

            elif state == 7:  # type
                packet_type = c
                state += 1

            elif state == 8:  # length
                packet_length = c
                idx = 0
                state += 1
                if idx == packet_length:
                    state += 1

            elif state == 9:  # packet data
                buf[idx] = c
                idx += 1
                if idx == packet_length:
                    state += 1

    async def _send_packet(self):
        self._output.write(self._builder._finalize_packet())
        await self._output.drain()

    async def _reply_current_state(self, command):
        self._builder._init_packet(_PACKET_CURRENT_STATE)
        state, url = await self._current_state_cb()
        self._builder._append(state)
        await self._send_packet()

        self._builder._init_packet(_PACKET_RPC_RESULT, command)
        if url:
            self._builder._append_string(url)
        await self._send_packet()

    async def _process_packet(self, packet_type, buf):
        if packet_type == _PACKET_RPC_COMMAND:
            if len(buf) < 2:
                self._builder._init_packet(_PACKET_ERROR_STATE)
                self._builder._append(_ERROR_INVALID_PACKET)
                await self._send_packet()
                return

            command = buf[0]
            # buf[1] is the length, which we are ignoring
            buf = buf[2:]

            if command == _RPC_SEND_SETTINGS:
                buf, ssid = _decode_string(buf)
                buf, password = _decode_string(buf)

                try:
                    await self._set_wifi_settings_cb(
                        bytes(ssid).decode("utf-8"), bytes(password).decode("utf-8")
                    )
                except Exception as exc:
                    self._logger.exc(exc, "Exception setting wifi")
                    self._builder._init_packet(_PACKET_ERROR_STATE)
                    self._builder._append(_ERROR_UNKNOWN)
                    await self._send_packet()
                    return

                await self._reply_current_state(command)

            elif command == _RPC_REQUEST_CURRENT_STATE:
                await self._reply_current_state(command)

            elif command == _RPC_REQUEST_DEVICE_INFO:
                self._builder._init_packet(_PACKET_RPC_RESULT, command)
                self._builder._append_string(self._product_name)
                self._builder._append_string(self._product_version)
                self._builder._append_string(self._hardware_name)
                self._builder._append_string(self._device_name)
                await self._send_packet()

            elif command == _RPC_REQUEST_SCAN_NETWORKS:
                seen = set()
                for net in await self._scan_wifi_cb():
                    if net[0] in seen:
                        continue
                    seen.add(net[0])

                    self._builder._init_packet(_PACKET_RPC_RESULT, command)
                    self._builder._append_string(net[0])
                    self._builder._append_string(str(net[3]).encode("ascii"))
                    self._builder._append_string(b"YES" if net[4] != 0 else "NO")
                    await self._send_packet()

                self._builder._init_packet(_PACKET_RPC_RESULT, command)
                await self._send_packet()

        else:
            await self._send_packet(_PACKET_ERROR_STATE, b"0x01")
