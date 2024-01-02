# mqtt_as.py Asynchronous version of umqtt.robust
# (C) Copyright Peter Hinch 2017-2022.
# Released under the MIT licence.

# Pyboard D support added also RP2/default
# Various improvements contributed by Kevin Köck.

# Modernized by Damien Tournoud.

import usocket as socket
import ustruct as struct
import collections
import logging

from ubinascii import hexlify
import uasyncio as asyncio

from utime import ticks_ms, ticks_diff


class MQTTError(Exception):
    pass


class NotConnectedError(MQTTError):
    pass


def _validate_qos(qos):
    if not (qos == 0 or qos == 1):
        raise ValueError("Only qos 0 and 1 are supported")


Message = collections.namedtuple(
    "Message",
    ["topic", "reader", "data", "size", "retained"],
)


class _MarkReader:
    def __init__(self, s):
        self._s = s
        self._last_rx = 0

    async def read(self, n=-1):
        buf = await self._s.read(n)
        self._last_rx = ticks_ms()
        return buf

    async def readinto(self, buf):
        while True:
            n = await self._s.readinto(buf)
            if not n:
                continue
            self._last_rx = ticks_ms()
            return n

    async def readexactly(self, n):
        buf = await self._s.readexactly(n)
        self._last_rx = ticks_ms()
        return buf

    def readline(self):
        raise NotImplemented()


class _LimitedStreamReader:
    def __init__(self, s, sz):
        self._s = s
        self._sz = sz

    async def read(self, n=-1):
        if n < 0:
            return await self.readexactly(self._sz)

        n = min(self._sz, n)
        buf = self._s.read(n)
        self._sz -= len(buf)
        return buf

    async def readinto(self, buf):
        if not isinstance(buf, memoryview):
            buf = memoryview(buf)
        buf = buf[: self._sz]

        n = await self._s.readinto(buf)
        self._sz -= n
        return n

    async def readexactly(self, n):
        if n > self._sz:
            raise EOFError()

        buf = await self._s.readexactly(n)
        self._sz -= len(buf)
        return buf

    def readline(self):
        raise NotImplemented()


_NONE = object()


class _AsyncResult:
    # TODO: this was modelled around gevent.event.AsyncResult, but
    # it is quite close to asyncio.Future. Contribute an implementation
    # of asyncio.Future to micropython.

    def __init__(self):
        self._ev = asyncio.Event()
        self._value = _NONE
        self._exception = None
        self._exc_info = None

    def _get(self):
        if self._value is not _NONE:
            return self._value
        else:
            raise self._exception

    async def wait(self):
        await self._ev.wait()

    async def get(self):
        if not self._ev.is_set():
            await self._ev.wait()
        return self._get()

    def set(self, value=None):
        self._value = value
        self._ev.set()

    def set_exception(self, exception, exc_info=None):
        self._exception = exception
        self._exc_info = exc_info
        self._ev.set()


class MQTT:
    def __init__(
        self,
        client_id,
        host,
        port,
        user,
        password,
        subscriptions=None,
        will=None,
        ssl=False,
        ssl_params=None,
        on_connect_task=None,
    ):
        self._logger = logging.getLogger(__name__)

        self._router = _Router()

        self._client_id = client_id

        self._host = host
        self._port = port

        self._ssl = ssl
        self._ssl_params = ssl_params or {}

        self._user = user
        self._password = password
        self._keepalive = 60
        self._response_time = 10000
        self._max_publish_retries = 4

        self._clean_init = True
        self._clean = True

        self._subscriptions = subscriptions or {}

        will = will
        if will is None:
            self._lw_topic = False
        else:
            self._set_last_will(*will)

        self._closed = False
        self._close_event = asyncio.Event()

        self._sock = None
        self._stream = None
        self._reader = None
        self._has_connected = False  # Define 'Clean Session' value to use.
        self._next_pid = 1
        self._connection_epoch = 0  # Incremented every time we reconnect to the server

        self._rcv_pids = {}  # PUBACK and SUBACK pids awaiting ACK response
        self._lock = asyncio.Lock()

        self._is_connected = asyncio.Event()  # Current connection state
        keepalive = 1000 * self._keepalive  # ms
        self._ping_interval = keepalive // 4 if keepalive else 20000

        self._on_connect_task = on_connect_task

        self._tasks = None
        self._connection_task = asyncio.create_task(self._connection_loop())

    def _set_last_will(self, topic, msg, retain=False, qos=0):
        _validate_qos(qos)
        if not topic:
            raise ValueError("Empty topic")

        self._lw_topic = topic
        self._lw_msg = msg
        self._lw_qos = qos
        self._lw_retain = retain

    async def _send_str(self, s):
        if isinstance(s, str):
            s = s.encode("utf-8")
        await self._awrite(struct.pack("!H", len(s)))
        await self._awrite(s)

    async def _recv_len(self):
        n = 0
        sh = 0
        while True:
            res = await self._reader.readexactly(1)
            b = res[0]
            n |= (b & 0x7F) << sh
            if not b & 0x80:
                return n
            sh += 7

    async def close(self):
        # TODO: Forcefully shut everything down for now.
        # We should gracefully disconnect and wait for
        # ongoing processes to finish.
        self._closed = True

        self._is_connected.clear()
        if self._sock is not None:
            for task in self._tasks:
                task.cancel()
                await task

            self._tasks = None

            try:
                self._sock.close()
            except Exception:
                pass

            self._stream = None
            self._reader = None

    def _new_pid(self):
        pid = self._next_pid
        self._next_pid += 1
        if self._next_pid == 65536:
            self._next_pid = 1
        res = _AsyncResult()
        self._rcv_pids[pid] = res
        return pid, res

    async def publish(self, topic, msg, retain=False, qos=0):
        _validate_qos(qos)

        if not qos:
            async with self._lock:
                if not self._is_connected.is_set():
                    raise NotConnectedError()
                await self._publish(topic, msg, retain, 0, 0, 0)
                return

        pid = None
        try:
            async with self._lock:
                if not self._is_connected.is_set():
                    raise NotConnectedError()

                pid, res = self._new_pid()
                await self._publish(topic, msg, retain, qos, 0, pid)

            return await res.wait()  # Wait for PUBACK

        finally:
            if pid is not None:
                self._rcv_pids.pop(pid, None)

    async def _publish(self, topic, msg, retain, qos, dup, pid):
        pkt = bytearray(b"\x30\0\0\0")
        pkt_mv = memoryview(pkt)
        pkt[0] |= qos << 1 | retain | dup << 3
        sz = 2 + len(topic) + len(msg)
        if qos > 0:
            sz += 2
        if sz >= 2097152:
            raise MQTTError("Strings too long")
        i = 1
        while sz > 0x7F:
            pkt[i] = (sz & 0x7F) | 0x80
            sz >>= 7
            i += 1
        pkt[i] = sz

        await self._awrite(pkt_mv[: i + 1])

        await self._send_str(topic)
        if qos > 0:
            struct.pack_into("!H", pkt, 0, pid)
            await self._awrite(pkt_mv[:2])
        await self._awrite(msg)

    async def subscribe(self, topic, handler, stream=False, qos=0):
        _validate_qos(qos)
        self._router.add_route(topic, handler, stream)

        async with self._lock:
            if not self._is_connected.is_set():
                raise NotConnectedError()

            res = await self._send_subscribe_locked(topic, qos)

        return await res.get()

    async def _send_subscribe_locked(self, topic, qos=0):
        pkt = bytearray(b"\x82\0\0\0")
        pid, res = self._new_pid()
        try:
            struct.pack_into("!BH", pkt, 1, 2 + 2 + len(topic) + 1, pid)
            await self._awrite(pkt)
            await self._send_str(topic)
            await self._awrite(qos.to_bytes(1, "little"))
        except:
            self._rcv_pids.pop(pid, None)
            raise

        return res

    async def unsubscribe(self, topic):
        async with self._lock:
            if not self._is_connected.is_set():
                raise NotConnectedError()

            if not topic in self._router._routes:
                return

            res = await self._send_unsubscribe_locked(topic)

        await res.get()
        self._router.drop_route(topic)
        return

    async def _send_unsubscribe_locked(self, topic):
        pkt = bytearray(b"\xa2\0\0\0")
        pid, res = self._new_pid()
        try:
            struct.pack_into("!BH", pkt, 1, 2 + 2 + len(topic), pid)
            await self._awrite(pkt)
            await self._send_str(topic)

        except:
            self._rcv_pids.pop(pid, None)
            raise

        return res

    async def get(self, topic, handler, stream=False):
        """Subscribe to a topic and retrieve a message from it"""

        res = _AsyncResult()

        async def _handler(client, message):
            try:
                res.set(await handler(client, message))
            except BaseException as exc:
                res.set_exception(exc)

        await self.subscribe(topic, _handler, stream=True)
        try:
            return await res.get()

        finally:
            self.unsubscribe(topic)

    async def _read_msg(self):
        res = await self._reader.readexactly(1)
        if res == b"":
            raise OSError(-1, "EOF")

        if res == b"\xd0":  # PINGRESP
            await self._reader.readexactly(1)  # Update .last_rx time
            return

        op = res[0]

        if op == 0x40:  # PUBACK: save pid
            sz = await self._reader.readexactly(1)
            if sz != b"\x02":
                raise OSError(-1, "Invalid PUBACK packet")
            rcv_pid = await self._reader.readexactly(2)
            pid = rcv_pid[0] << 8 | rcv_pid[1]
            if pid in self._rcv_pids:
                res = self._rcv_pids.pop(pid)
                res.set()
            else:
                raise OSError(-1, "Invalid pid in PUBACK packet")

        if op == 0x90:  # SUBACK
            resp = await self._reader.readexactly(4)
            if resp[3] == 0x80:
                raise OSError(-1, "Invalid SUBACK packet")
            pid = resp[2] | (resp[1] << 8)
            if pid in self._rcv_pids:
                res = self._rcv_pids.pop(pid)
                res.set()
            else:
                raise OSError(-1, "Invalid pid in SUBACK packet")

        if op == 0xB0:  # UNSUBACK
            resp = await self._reader.readexactly(3)
            pid = resp[2] | (resp[1] << 8)
            if pid in self._rcv_pids:
                res = self._rcv_pids.pop(pid)
                res.set()
            else:
                raise OSError(-1)

        if op & 0xF0 != 0x30:  # PUBLISH
            return

        sz = await self._recv_len()
        topic_len = await self._reader.readexactly(2)
        topic_len = (topic_len[0] << 8) | topic_len[1]
        topic = await self._reader.readexactly(topic_len)
        sz -= topic_len + 2
        if op & 6:
            pid = await self._reader.readexactly(2)
            pid = pid[0] << 8 | pid[1]
            sz -= 2
        retained = op & 0x01

        msg = Message(
            topic=topic.decode("utf-8"),
            reader=_LimitedStreamReader(self._reader, sz),
            data=None,
            size=sz,
            retained=retained,
        )

        await self._router.dispatch(self, msg)

        if op & 6 == 2:  # qos 1
            with self._lock:
                pkt = bytearray(b"\x40\x02\0\0")  # Send PUBACK
                struct.pack_into("!H", pkt, 2, pid)
                await self._awrite(pkt)

        elif op & 6 == 4:  # qos 2 not supported
            raise OSError(-1, "QoS 2 not supported")

    async def _reader_loop(self):
        try:
            while True:
                await self._read_msg()  # Immediate return if no message

        except Exception as exc:
            self._logger.exc(exc, "Exception reading message")
        self._force_reconnect("read error")  # Broker or WiFi fail.

    async def _awrite(self, buf):
        self._stream.write(buf)
        await self._stream.drain()

    async def _connect_inner(self, clean):
        try:
            self._logger.info("Connecting to broker")
            self._sock = socket.socket()
            self._next_pid = 1
            self._sock.connect(self._addr)
            if self._ssl:
                import ussl

                self._sock = ussl.wrap_socket(
                    self._sock, do_handshake=False, **self._ssl_params
                )

            self._sock.setblocking(False)
            self._stream = asyncio.StreamReader(self._sock)
            self._reader = _MarkReader(self._stream)

            premsg = bytearray(b"\x10\0\0\0\0\0")
            premsg_mv = memoryview(premsg)
            msg = bytearray(b"\x04MQTT\x04\x02\0\0")  # Protocol 3.1.1

            sz = 10 + 2 + len(self._client_id)
            msg[6] = clean << 1
            if self._user:
                sz += 2 + len(self._user) + 2 + len(self._password)
                msg[6] |= 0xC0
            if self._keepalive:
                msg[7] |= self._keepalive >> 8
                msg[8] |= self._keepalive & 0x00FF
            if self._lw_topic:
                sz += 2 + len(self._lw_topic) + 2 + len(self._lw_msg)
                msg[6] |= 0x4 | (self._lw_qos & 0x1) << 3 | (self._lw_qos & 0x2) << 3
                msg[6] |= self._lw_retain << 5

            i = 1
            while sz > 0x7F:
                premsg[i] = (sz & 0x7F) | 0x80
                sz >>= 7
                i += 1
            premsg[i] = sz
            await self._awrite(premsg_mv[: i + 2])
            await self._awrite(msg)
            await self._send_str(self._client_id)
            if self._lw_topic:
                await self._send_str(self._lw_topic)
                await self._send_str(self._lw_msg)
            if self._user:
                await self._send_str(self._user)
                await self._send_str(self._password)
            await self._stream.drain()

            # Await CONNACK
            # read causes ECONNABORTED if broker is out; triggers a reconnect.
            resp = await self._reader.readexactly(4)
            if resp[3] != 0 or resp[0] != 0x20 or resp[1] != 0x02:
                raise OSError(
                    -1, "Bad CONNACK"
                )  # Bad CONNACK e.g. authentication fail.
            self._logger.info("Connected to broker")  # Got CONNACK

        except Exception:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
                self._stream = None
            raise

    async def _connect(self):
        async with self._lock:
            if not self._has_connected:
                # Note this blocks if DNS lookup occurs. Do it once to prevent
                # blocking during later internet outage:
                self._addr = socket.getaddrinfo(self._host, self._port)[0][-1]

            if not self._has_connected and self._clean_init and not self._clean:
                # Power up. Clear previous session data but subsequently save it.
                await self._connect_inner(True)  # Connect with clean session
                try:
                    self._sock.write(b"\xe0\0")  # Force disconnect but keep socket open
                except OSError:
                    pass
                self._logger.info("Waiting for disconnect")
                await asyncio.sleep(2)  # Wait for broker to disconnect
                self._logger.info("About to reconnect with unclean session.")
            else:
                await self._connect_inner(self._clean)

            self._rcv_pids = {}
            # If we get here without error broker/LAN must be up.
            self._has_connected = True  # Use normal clean flag on reconnect.

            self._tasks = [
                asyncio.create_task(self._reader_loop()),
                asyncio.create_task(self._keep_alive_loop()),
            ]

            self._is_connected.set()

        if True:  # TODO: "on clean connection"
            for topic, handler in self._subscriptions.items():
                self._logger.info("Subscribing to topic %s", topic)
                await self.subscribe(topic, handler)

        if self._on_connect_task is not None:
            await self._on_connect_task(self)

    async def _connection_loop(self):
        while not self._closed:
            try:
                await self._connect()
            except Exception as exc:
                self._logger.exc(exc, "Failed to connect")
                await asyncio.sleep_ms(10000)
                continue

            await self._close_event.wait()
            self._close_event.clear()

            self._is_connected.clear()
            if self._sock is not None:
                for task in self._tasks:
                    task.cancel()
                    await task

                self._tasks = None

                try:
                    self._sock.close()
                except Exception:
                    pass

                self._stream = None
                self._reader = None

    # Keep broker alive MQTT spec 3.1.2.10 Keep Alive.
    # Runs until ping failure or no response in keepalive period.
    async def _keep_alive_loop(self):
        while True:
            pings_due = (
                ticks_diff(ticks_ms(), self._reader._last_rx) // self._ping_interval
            )
            if pings_due >= 4:
                self._logger.info("Reconnect: broker failed to ping")
                break
            await asyncio.sleep_ms(self._ping_interval)
            async with self._lock:
                try:
                    await self._awrite(b"\xc0\0")
                except OSError:
                    break

        self._force_reconnect("error in ping loop")  # Broker or WiFi fail.

    def _force_reconnect(self, reason="unknown reason"):
        if self._close_event.is_set():
            return

        self._logger.info("Force reconnection, reason: %s", reason)
        self._close_event.set()


# See MQTT 3.1.1 section 4.7 "Topic Names and Topic Filters"
# https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html#_Toc398718106
#
# TODO: this is non-conformant for topics starting with $
class _Router:
    def __init__(self):
        self._routes = {}

    def _split_topic(self, topic):
        return topic.split("/")

    def _split_route(self, route):
        route = self._split_topic(route)
        for idx, part in enumerate(route):
            if (
                ("+" in part and part != "+")
                or ("#" in part and part != "#")
                or (part == "#" and idx != len(route) - 1)
            ):
                raise ValueError("invalid topic specifier")
        return route

    def _match(self, route, topic):
        route_len = len(route)
        topic_len = len(topic)

        while True:
            if route_len == 0:
                return topic_len == 0
            route_part = route[-route_len]
            if topic_len == 0:
                return route_part == "#"
            if route_part == "#":
                return True
            topic_part = topic[-topic_len]
            if route_part != "+" and route_part != topic_part:
                return False

            route_len -= 1
            topic_len -= 1

    def add_route(self, route, handler, stream=False):
        self._routes[route] = (
            self._split_route(route),
            (handler, stream),
        )

    def drop_route(self, route):
        self._routes.pop(route, None)

    async def dispatch(self, client, message):
        topic_parts = message.topic.split("/")
        matching_handlers = [
            handler
            for route, handler in self._routes.values()
            if self._match(route, topic_parts)
        ]

        matching_handlers = []
        must_load = False
        for route, (handler, stream) in self._routes.values():
            if self._match(route, topic_parts):
                matching_handlers.append(handler)
                if not stream:
                    must_load = True

        if must_load or not matching_handlers:
            message = Message(
                topic=message.topic,
                reader=None,
                data=await message.reader.read(),
                size=message.size,
                retained=message.retained,
            )

        for handler in matching_handlers:
            await handler(client, message)
