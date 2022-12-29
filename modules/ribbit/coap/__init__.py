import binascii
import logging
import socket
import random
import os
import ssl
import uasyncio as asyncio
import uasyncio.core as _asyncio_core

from micropython import const


_HEADER_SIZE = const(4)
_OPTION_HEADER_SIZE = const(1)
_PAYLOAD_MARKER = const(0xFF)
_MAX_OPTION_NUM = const(10)
_BUF_MAX_SIZE = const(1500)
_DEFAULT_PORT = const(5683)

_DEBUG = const(0)

VERSION_UNSUPPORTED = const(0)
VERSION_1 = const(1)

TYPE_CON = const(0)
TYPE_NONCON = const(1)
TYPE_ACK = const(2)
TYPE_RESET = const(3)

METHOD_EMPTY_MESSAGE = const(0)
METHOD_GET = const(1)
METHOD_POST = const(2)
METHOD_PUT = const(3)
METHOD_DELETE = const(4)

RESPONSE_CODE_CREATED = const(0x41)
RESPONSE_CODE_DELETED = const(0x42)
RESPONSE_CODE_VALID = const(0x43)
RESPONSE_CODE_CHANGED = const(0x44)
RESPONSE_CODE_CONTENT = const(0x45)
RESPONSE_CODE_BAD_REQUEST = const(0x80)
RESPONSE_CODE_UNAUTHORIZED = const(0x81)
RESPONSE_CODE_BAD_OPTION = const(0x82)
RESPONSE_CODE_FORBIDDEN = const(0x83)
RESPONSE_CODE_NOT_FOUND = const(0x84)
RESPONSE_CODE_METHOD_NOT_ALLOWD = const(0x85)
RESPONSE_CODE_NOT_ACCEPTABLE = const(0x86)
RESPONSE_CODE_PRECONDITION_FAILED = const(0x8C)
RESPONSE_CODE_REQUEST_ENTITY_TOO_LARGE = const(0x8D)
RESPONSE_CODE_UNSUPPORTED_CONTENT_FORMAT = const(0x8F)
RESPONSE_CODE_INTERNAL_SERVER_ERROR = const(0xA0)
RESPONSE_CODE_NOT_IMPLEMENTED = const(0xA1)
RESPONSE_CODE_BAD_GATEWAY = const(0xA2)
RESPONSE_CODE_SERVICE_UNAVALIABLE = const(0xA3)
RESPONSE_CODE_GATEWAY_TIMEOUT = const(0xA4)
RESPONSE_CODE_PROXYING_NOT_SUPPORTED = const(0xA5)

OPTION_IF_MATCH = const(1)
OPTION_URI_HOST = const(3)
OPTION_E_TAG = const(4)
OPTION_IF_NONE_MATCH = const(5)
OPTION_OBSERVE = const(6)
OPTION_URI_PORT = const(7)
OPTION_LOCATION_PATH = const(8)
OPTION_URI_PATH = const(11)
OPTION_CONTENT_FORMAT = const(12)
OPTION_MAX_AGE = const(14)
OPTION_URI_QUERY = const(15)
OPTION_ACCEPT = const(17)
OPTION_LOCATION_QUERY = const(20)
OPTION_BLOCK2 = const(23)
OPTION_BLOCK1 = const(27)
OPTION_PROXY_URI = const(35)
OPTION_PROXY_SCHEME = const(39)

CONTENT_FORMAT_NONE = const(-1)
CONTENT_FORMAT_TEXT_PLAIN = const(0x00)
CONTENT_FORMAT_APPLICATION_LINK_FORMAT = const(0x28)
CONTENT_FORMAT_APPLICATION_XML = const(0x29)
CONTENT_FORMAT_APPLICATION_OCTET_STREAM = const(0x2A)
CONTENT_FORMAT_APPLICATION_EXI = const(0x2F)
CONTENT_FORMAT_APPLICATION_JSON = const(0x32)
CONTENT_FORMAT_APPLICATION_CBOR = const(0x3C)


class COAPException(Exception):
    pass


class COAPDisconnectedError(COAPException):
    pass


class COAPRequestTimeoutError(COAPException):
    pass


class COAPInvalidPacketError(COAPException):
    pass


class _Semaphore(asyncio.Lock):
    def __init__(self, value=1):
        super().__init__()
        self._value = value

    async def acquire(self):
        if self._value > 0:
            self._value -= 1
        if self._value == 0:
            await super().acquire()

    async def release(self):
        self._value += 1
        if self._value == 1:
            await super().release()


class _WaitGroup:
    def __init__(self):
        self._in_flight = 0
        self._done_ev = asyncio.Event()

    def _done(self, tsk, err):
        self._in_flight -= 1
        if self._in_flight == 0:
            self._done_ev.set()

    def create_task(self, tsk):
        self._in_flight += 1
        tsk = asyncio.create_task(tsk)
        tsk.state = self._done

    async def wait(self):
        if self._in_flight == 0:
            return

        self._done_ev = ev = asyncio.Event()
        return await ev.wait()


class _DTLSocket:
    def __init__(self, s):
        self.s = s

    def close(self):
        self.s.close()

    def read(self, n=-1):
        while True:
            yield _asyncio_core._io_queue.queue_read(self.s)
            r = self.s.recv(n)
            if r is not None:
                return r

    def readinto(self, buf):
        yield _asyncio_core._io_queue.queue_read(self.s)
        return self.s.recv_into(buf)

    def write(self, buf):
        while True:
            yield _asyncio_core._io_queue.queue_write(self.s)
            r = self.s.send(buf)
            if r is not None:
                return r


class CoapOption:
    def __init__(self, number=-1, buffer=None):
        self.number = number
        byteBuf = bytearray()
        if buffer is not None:
            byteBuf.extend(buffer)
        self.buffer = byteBuf

    def __str__(self):
        return "<CoapOption(%d, %d, %s)>" % (
            self.number,
            len(self.buffer),
            bytes(self.buffer),
        )


class CoapPacket:
    def __init__(self):
        self.version = VERSION_UNSUPPORTED
        self.type = TYPE_CON  # uint8_t
        self.method = METHOD_GET  # uint8_t
        self.token = None
        self.payload = bytearray()
        self.message_id = 0
        self.content_format = CONTENT_FORMAT_NONE
        self.query = bytearray()  # uint8_t*
        self.options = []

    def __str__(self):
        return (
            "<CoapPacket(id=0x%x, token=%s, type=0x%02x, method=%d.%02d, payload_len=%d, options=%s)"
            % (
                self.message_id,
                self.token,
                self.type,
                (self.method & 0xE0) >> 5,
                self.method & 0x1F,
                len(self.payload) if self.payload is not None else 0,
                ", ".join(str(option) for option in self.options),
            )
        )

    def add_option(self, number, opt_payload):
        if len(self.options) >= _MAX_OPTION_NUM:
            raise ValueError("too many options")

        if self.options and self.options[0].number > number:
            raise ValueError("options must be sorted")

        self.options.append(CoapOption(number, opt_payload))

    def set_uri_host(self, address):
        self.add_option(OPTION_URI_HOST, address)

    def set_uri_path(self, url):
        for subPath in url.split("/"):
            self.add_option(OPTION_URI_PATH, subPath)


def _parse_option(packet, runningDelta, buffer):
    option = CoapOption()

    delta = (buffer[0] & 0xF0) >> 4
    length = buffer[0] & 0x0F
    buffer = buffer[1:]

    if delta == 15 or length == 15:
        raise COAPInvalidPacketError()

    if delta == 13:
        if not buffer:
            raise COAPInvalidPacketError()
        delta = buffer[0] + 13
        buffer = buffer[1:]
    elif delta == 14:
        if len(buffer) < 2:
            raise COAPInvalidPacketError()
        delta = ((buffer[0] << 8) | buffer[1]) + 269
        buffer = buffer[2:]

    option.number = delta + runningDelta

    if length == 13:
        if not buffer:
            raise COAPInvalidPacketError()
        length = buffer[0] + 13
        buffer = buffer[1:]
    elif length == 14:
        if len(buffer) < 2:
            raise COAPInvalidPacketError()
        length = ((buffer[0] << 8) | buffer[1]) + 269
        buffer = buffer[2:]

    if len(buffer) < length:
        raise COAPInvalidPacketError()

    option.buffer = buffer[:length]
    buffer = buffer[length:]
    packet.options.append(option)

    return runningDelta + delta, buffer


def _parse_packet(buffer, packet):
    packet.version = (buffer[0] & 0xC0) >> 6
    if packet.version != VERSION_1:
        raise ValueError("invalid version")
    packet.type = (buffer[0] & 0x30) >> 4
    packet.method = buffer[1]
    packet.message_id = 0xFF00 & (buffer[2] << 8)
    packet.message_id |= 0x00FF & buffer[3]

    token_len = buffer[0] & 0x0F
    if token_len == 0:
        packet.token = None
    elif token_len == 4:
        packet.token = (
            (buffer[4] << 24) | (buffer[5] << 16) | (buffer[6] << 8) | buffer[7]
        )
    else:
        raise COAPInvalidPacketError()

    buffer = buffer[4 + token_len :]

    if buffer:
        delta = 0
        while buffer and buffer[0] != 0xFF:
            delta, buffer = _parse_option(packet, delta, buffer)

    if buffer and buffer[0] == 0xFF:
        packet.payload = buffer[1:]
    else:
        packet.payload = None

    return True


def _write_packet_header_info(buffer, packet):
    # make coap packet base header
    buffer.append(VERSION_1 << 6)
    buffer[0] |= (packet.type & 0x03) << 4
    # max: 8 bytes of tokens, if token length is greater, it is ignored
    token_len = 0
    if packet.token is not None:
        token_len = 4

    buffer[0] |= token_len & 0x0F
    buffer.append(packet.method)
    buffer.append(packet.message_id >> 8)
    buffer.append(packet.message_id & 0xFF)

    if packet.token is not None:
        buffer.append((packet.token >> 24) & 0xFF)
        buffer.append((packet.token >> 16) & 0xFF)
        buffer.append((packet.token >> 8) & 0xFF)
        buffer.append(packet.token & 0xFF)


def _coap_option_delta(v):
    if v < 13:
        return 0xFF & v
    if v <= 0xFF + 13:
        return 13
    return 14


def _write_packet_options(buffer, packet):
    running_delta = 0
    # make option header
    for opt in packet.options:
        buffer_len = len(opt.buffer)

        if len(buffer) + 5 + buffer_len >= _BUF_MAX_SIZE:
            raise ValueError("option buffer too big")

        delta = opt.number - running_delta
        delta_encoded = _coap_option_delta(delta)
        buffer_len_encoded = _coap_option_delta(buffer_len)

        buffer.append(0xFF & ((delta_encoded << 4) | buffer_len_encoded))
        if delta_encoded == 13:
            buffer.append(delta - 13)
        elif delta_encoded == 14:
            buffer.append((delta - 269) >> 8)
            buffer.append(0xFF & (delta - 269))

        if buffer_len_encoded == 13:
            buffer.append(buffer_len - 13)
        elif buffer_len_encoded == 14:
            buffer.append(buffer_len >> 8)
            buffer.append(0xFF & (buffer_len - 269))

        buffer.extend(opt.buffer)
        running_delta = opt.number


def _write_packet_payload(buffer, packet):
    # make payload
    if (packet.payload is not None) and (len(packet.payload)):
        if (len(buffer) + 1 + len(packet.payload)) >= _BUF_MAX_SIZE:
            return 0
        buffer.append(0xFF)
        buffer.extend(packet.payload)


class Coap:
    def __init__(
        self,
        host,
        port=_DEFAULT_PORT,
        ssl=False,
        ssl_options=None,
        ack_timeout_ms=2_000,
        ack_random_factor=1.5,
        max_retransmit=4,
        ping_interval_ms=60_000,
    ):
        self._logger = logging.getLogger(__name__)
        if _DEBUG:
            self._logger.setLevel(logging.DEBUG)
        self._callbacks = {}
        self._response_callback = None
        self._host = host
        self._port = port
        self._ssl = ssl
        self._ssl_opts = ssl_options or {}

        self._addr = None

        self._sock = None
        self.connected = False
        self._connection_epoch = 0
        self._next_message_id = 0
        self._read_loop_task = None
        self._ping_loop_task = None
        self._in_flight_requests = {}
        self._force_reconnect_event = asyncio.Event()

        # Protocol parameters:
        self._ack_timeout_min_ms = ack_timeout_ms
        self._ack_timeout_max_ms = int(self._ack_timeout_min_ms * ack_random_factor)
        self._max_retransmit = max_retransmit

        self._ping_interval_ms = ping_interval_ms

        self._on_connect_tasks = []

        self.lock = asyncio.Lock()

    def _get_message_id(self):
        message_id = self._next_message_id
        if message_id < 0xFFFF:
            self._next_message_id += 1
        else:
            self._next_message_id = 0
        return message_id

    def on_connect(self, cb):
        self._on_connect_tasks.append(cb)

    async def connect(self):
        self._logger.info("Connecting to CoAP server")
        self._force_reconnect_event.clear()

        rnd = os.urandom(2)
        self._connection_epoch = (rnd[0] << 8) | rnd[1]
        self._next_message_id = 0

        if self._addr is None:
            # TODO: this is blocking
            self._addr = socket.getaddrinfo(self._host, self._port)[0][-1]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setblocking(False)
            sock.bind(socket.getaddrinfo("0.0.0.0", 0)[0][-1])
            sock.connect(self._addr)

            if self._ssl:
                sock = ssl.wrap_socket(
                    sock,
                    dtls=True,
                    do_handshake=False,
                    **self._ssl_opts,
                )

            self._sock = _DTLSocket(sock)

            self._read_loop_task = asyncio.create_task(self._read_loop())

            await self.ping()

            self._logger.info("Connected to CoAP server")

            self._ping_loop_task = asyncio.create_task(self._ping_loop())

            for task in self._on_connect_tasks:
                await task(self)

            self.connected = True

        except Exception:
            sock.close()
            self.connected = False
            raise

    def _force_reconnect(self, reason):
        if not self._force_reconnect_event.is_set():
            self._force_reconnect_event.set()
            self._logger.warning("Force reconnection, reason: %s", reason)

    async def disconnect(self):
        if self.connected:
            self._logger.info("Disconnecting from CoAP server")
            self.connected = False

        if self._read_loop_task is not None:
            self._read_loop_task.cancel()
        if self._ping_loop_task is not None:
            self._ping_loop_task.cancel()

        for ev in self._in_flight_requests.values():
            ev.disconnected = True
            ev.set()

        self._in_flight_requests = {}
        self._sock.close()
        self._sock = None

    async def connect_loop(self):
        while True:
            try:
                await self.connect()
            except Exception as exc:
                self._logger.error("Error trying to connect: %s", str(exc))
                await asyncio.sleep_ms(10_000)
                try:
                    await self.disconnect()
                except Exception:
                    pass
                continue

            await self._force_reconnect_event.wait()

            try:
                await self.disconnect()
            except Exception:
                pass

    async def send_packet(self, packet):
        if packet.message_id is None:
            packet.message_id = self._get_message_id()

        if packet.content_format != CONTENT_FORMAT_NONE:
            optionBuffer = bytearray(2)
            optionBuffer[0] = (packet.content_format & 0xFF00) >> 8
            optionBuffer[1] = packet.content_format & 0x00FF
            packet.add_option(OPTION_CONTENT_FORMAT, optionBuffer)

        if packet.query is not None and len(packet.query) > 0:
            packet.add_option(OPTION_URI_QUERY, packet.query)

        buffer = bytearray()
        _write_packet_header_info(buffer, packet)
        _write_packet_options(buffer, packet)
        _write_packet_payload(buffer, packet)

        if _DEBUG:
            self._logger.debug(">>>>>> %s", packet)

        try:
            await self._sock.write(buffer)
        except Exception:
            self._force_reconnect("error writing packet")
            raise

    async def _send_ack(self, message_id):
        packet = CoapPacket()
        packet.type = TYPE_ACK
        packet.method = METHOD_EMPTY_MESSAGE
        packet.message_id = message_id
        return await self.send_packet(packet)

    async def ping(self):
        packet = CoapPacket()
        packet.type = TYPE_CON
        packet.method = METHOD_EMPTY_MESSAGE
        return await self.request(packet)

    async def _ping_loop(self):
        while True:
            await asyncio.sleep_ms(self._ping_interval_ms)
            try:
                await self.ping()
            except Exception:
                self._force_reconnect("error sending ping request")
                return

    async def request(self, packet, observe_cb=None):
        async with self.lock:
            is_ping = packet.method == METHOD_EMPTY_MESSAGE
            packet.message_id = self._get_message_id()
            if packet.token is None and not is_ping:
                packet.token = (self._connection_epoch << 16) | packet.message_id

            ev = asyncio.Event()
            ev.acked = False
            ev.disconnected = False
            ev.only_ack = is_ping
            ev.observe_cb = observe_cb
            self._in_flight_requests[packet.message_id] = ev
            self._in_flight_requests[packet.token] = ev

            retransmit_delay_ms = random.randint(
                self._ack_timeout_min_ms, self._ack_timeout_max_ms
            )
            retransmissions = 0

            epoch = self._connection_epoch
            try:
                while not ev.acked:
                    await self.send_packet(packet)

                    try:
                        await asyncio.wait_for_ms(ev.wait(), retransmit_delay_ms)
                        break
                    except asyncio.TimeoutError:
                        if self._connection_epoch != epoch:
                            raise COAPDisconnectedError()

                        if retransmissions == self._max_retransmit:
                            self._force_reconnect("reached max retransmissions")
                            raise COAPRequestTimeoutError()
                        retransmissions += 1
                        retransmit_delay_ms *= 2

                if not ev.is_set():
                    await ev.wait()
                if ev.disconnected:
                    raise COAPDisconnectedError()
                return ev.response

            finally:
                if self._connection_epoch == epoch:
                    if observe_cb is None:
                        self._in_flight_requests.pop(packet.message_id, None)
                        self._in_flight_requests.pop(packet.token, None)

    async def get(self, path, accept=CONTENT_FORMAT_TEXT_PLAIN):
        packet = CoapPacket()
        packet.type = TYPE_CON
        packet.method = METHOD_GET
        packet.set_uri_path(path)
        packet.add_option(OPTION_ACCEPT, encode_uint_option(accept))
        return await self.request(packet)

    async def observe(self, path, observe_cb, accept=CONTENT_FORMAT_TEXT_PLAIN):
        packet = CoapPacket()
        packet.type = TYPE_CON
        packet.method = METHOD_GET
        packet.add_option(OPTION_OBSERVE, b"")
        packet.set_uri_path(path)
        packet.add_option(OPTION_ACCEPT, encode_uint_option(accept))
        return await self.request(packet, observe_cb=observe_cb)

    def get_streaming(self, path):
        return BlockReader(self, path)

    async def post(self, path, data, format=CONTENT_FORMAT_TEXT_PLAIN):
        packet = CoapPacket()
        packet.type = TYPE_CON
        packet.method = METHOD_POST
        packet.set_uri_path(path)
        packet.add_option(OPTION_CONTENT_FORMAT, encode_uint_option(format))
        packet.payload = data
        return await self.request(packet)

    async def put(self, path, format=CONTENT_FORMAT_TEXT_PLAIN):
        packet = CoapPacket()
        packet.type = TYPE_CON
        packet.method = METHOD_PUT
        packet.set_uri_path(path)
        if format:
            packet.add_option(OPTION_CONTENT_FORMAT, encode_uint_option(format))
        return await self.request(packet)

    async def delete(self, path):
        packet = CoapPacket()
        packet.type = TYPE_CON
        packet.method = METHOD_DELETE
        packet.set_uri_path(path)
        return await self.request(packet)

    def _read_bytes_from_socket(self, numOfBytes):
        try:
            return self.sock.recvfrom(numOfBytes)
        except Exception:
            return (None, None)

    async def _read_loop(self):
        while True:
            try:
                buffer = await self._sock.read(_BUF_MAX_SIZE)
                if buffer is None:
                    continue

                buffer = memoryview(buffer)

                packet = CoapPacket()
                _parse_packet(buffer, packet)

            except Exception:
                self._force_reconnect("error reading packet")
                return

            if _DEBUG:
                self._logger.debug("<<<<<< %s", packet)

            if packet.type == TYPE_CON:
                await self._send_ack(packet.message_id)

            if packet.type == TYPE_ACK and packet.method == METHOD_EMPTY_MESSAGE:
                # Separate response (rfc7252 #5.2.2)
                request_ev = self._in_flight_requests.get(packet.message_id, None)
                if request_ev is not None:
                    request_ev.acked = True
                    if request_ev.only_ack:
                        request_ev.response = None
                        request_ev.set()
                continue

            request_id = packet.token
            if request_id is None:
                request_id = packet.message_id
            request_ev = self._in_flight_requests.get(request_id, None)
            if request_ev is not None:
                request_ev.acked = True
                request_ev.response = packet
                if request_ev.observe_cb is not None:
                    asyncio.create_task(request_ev.observe_cb(self, packet))
                request_ev.set()


def encode_uint_option(v):
    l = 0
    vv = v
    while vv:
        l += 1
        vv >>= 8

    if l == 0:
        return b""

    buf = bytearray(l)
    while l > 0:
        l -= 1
        buf[l] = v & 0xFF
        v >>= 8
    return buf


def decode_uint_option(v):
    ret = 0
    for c in v:
        ret = (ret << 8) | c
    return ret


class BlockReader:
    def __init__(self, client, path):
        self._client = client
        self._path = path
        self._token = None
        self._block_num = 0

    async def readinto(self, buf):
        packet = CoapPacket()
        packet.token = self._token
        packet.type = TYPE_CON
        packet.method = METHOD_GET
        packet.set_uri_path(self._path)
        block_option_payload = encode_uint_option((self._block_num << 4) | 6)
        packet.add_option(
            OPTION_BLOCK2,
            block_option_payload,
        )
        response = await self._client.request(packet)

        options = [
            option for option in response.options if option.number == OPTION_BLOCK2
        ]
        if (
            len(options) != 1
            or (decode_uint_option(options[0].buffer) >> 4) != self._block_num
        ):
            raise RuntimeError("unexpected block option in server response")

        if len(buf) < len(response.payload):
            raise ValueError("buffer too small")

        buf[: len(response.payload)] = response.payload
        self._block_num += 1
        self._token = packet.token
        return len(response.payload)
