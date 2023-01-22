import json
import logging
import time
from micropython import const
import uasyncio as asyncio

import ribbit.config as _config
import ribbit.coap as _coap
import ribbit.utils.ota as _ota


# gRPC return codes
_RPC_OK = const(0)
_RPC_CANCELED = const(1)
_RPC_UNKNOWN = const(2)
_RPC_INVALID_ARGUMENT = const(3)
_RPC_DEADLINE_EXCEEDED = const(4)
_RPC_NOT_FOUND = const(5)
_RPC_ALREADYEXISTS = const(6)
_RPC_PERMISSION_DENIED = (const(7),)
_RPC_RESOURCE_EXHAUSTED = const(8)
_RPC_FAILED_PRECONDITION = const(9)
_RPC_ABORTED = const(10)
_RPC_OUT_OF_RANGE = const(11)
_RPC_UNIMPLEMENTED = const(12)
_RPC_INTERNAL = const(13)
_RPC_UNAVAILABLE = const(14)
_RPC_DATA_LOSS = const(15)
_RPC_UNAUTHENTICATED = const(16)


CONFIG_GOLIOTH_ENABLED = const("golioth.enabled")
CONFIG_GOLIOTH_HOST = const("golioth.host")
CONFIG_GOLIOTH_PORT = const("golioth.port")
CONFIG_GOLIOTH_USER = const("golioth.user")
CONFIG_GOLIOTH_PASSWORD = const("golioth.password")
CONFIG_GOLIOTH_OTA_ENABLED = const("golioth.ota.enabled")

_CONFIG_KEYS = [
    CONFIG_GOLIOTH_ENABLED,
    CONFIG_GOLIOTH_HOST,
    CONFIG_GOLIOTH_PORT,
    CONFIG_GOLIOTH_USER,
    CONFIG_GOLIOTH_PASSWORD,
    CONFIG_GOLIOTH_OTA_ENABLED,
]

CONFIG_KEYS = [
    _config.Boolean(name=CONFIG_GOLIOTH_ENABLED, default=True),
    _config.String(
        name=CONFIG_GOLIOTH_HOST,
        default="coap.golioth.io",
    ),
    _config.Integer(name=CONFIG_GOLIOTH_PORT, default=5684),
    _config.String(name=CONFIG_GOLIOTH_USER, default=None),
    _config.String(name=CONFIG_GOLIOTH_PASSWORD, default=None, protected=True),
    _config.Boolean(name=CONFIG_GOLIOTH_OTA_ENABLED, default=True),
]


class Golioth:
    def __init__(self, config, ota_manager, commands=None, in_simulator=False):
        self._logger = logging.getLogger(__name__)
        self._config = config
        self._commands = commands or {}
        self._coap = None
        self._ota_manager = ota_manager
        self._in_simulator = in_simulator
        self._ota_enabled = False

        self.register_rpc("ping", self._pong_rpc)

        asyncio.create_task(self._loop())

    async def _loop(self):
        with self._config.watch(*_CONFIG_KEYS) as cfg_watcher:
            while True:
                enabled, host, port, user, password, self._ota_enabled = cfg_watcher.get()

                enabled = enabled and (user is not None and password is not None)

                if self._coap is not None:
                    self._logger.info("Stopping Golioth integration")
                    self._coap.close()
                    self._coap = None

                if enabled:
                    self._logger.info("Starting Golioth integration")
                    self._coap = _coap.Coap(
                        host=host,
                        port=port,
                        ssl=True,
                        ssl_options={
                            "server_hostname": host,
                            "psk_identity": user,
                            "psk_key": password,
                        },
                    )
                    self._coap.on_connect(self._on_connect)
                    asyncio.create_task(self._coap.connect_loop())

                await cfg_watcher.wait()

    async def _on_connect(self, client):
        await self._send_firmware_report(client)
        await client.observe(
            ".c", self._on_golioth_config, accept=_coap.CONTENT_FORMAT_APPLICATION_JSON
        )
        await client.observe(
            ".rpc", self._on_golioth_rpc, accept=_coap.CONTENT_FORMAT_APPLICATION_JSON
        )
        if self._ota_enabled and not self._in_simulator:
            await client.observe(
                ".u/desired",
                self._on_golioth_firmware,
                accept=_coap.CONTENT_FORMAT_APPLICATION_JSON,
            )

    async def _on_golioth_config(self, client, packet):
        req = json.loads(packet.payload)
        self._logger.info("Config payload received: %s", req)

        config = {}
        for k, v in req["settings"].items():
            k = k.replace("_", ".").lower()
            config[k] = v

        self._config.set_remote(config)

        await client.post(
            ".c/status",
            json.dumps(
                {
                    "version": req["version"],
                    "error_code": 0,
                }
            ),
            format=_coap.CONTENT_FORMAT_APPLICATION_JSON,
        )

    def register_rpc(self, method, handler):
        self._commands[method] = handler

    async def _pong_rpc(self, *args):
        return "pong"

    def _reply_rpc(self, client, req, code, detail=None):
        res = {
            "id": req["id"],
            "statusCode": code,
        }
        if detail is not None:
            res["detail"] = detail

        return client.post(
            ".rpc/status",
            json.dumps(res),
            format=_coap.CONTENT_FORMAT_APPLICATION_JSON,
        )

    async def _on_golioth_rpc(self, client, packet):
        req = json.loads(packet.payload)
        if not isinstance(req, dict):
            return

        status = _RPC_OK
        details = None

        command = self._commands.get(req["method"], None)
        if command is not None:
            try:
                details = await command(*req["params"])
                if details is not None:
                    details = str(details)
            except Exception as exc:
                details = str(exc)
                status = _RPC_INTERNAL
        else:
            status = _RPC_UNIMPLEMENTED

        await self._reply_rpc(client, req, status, details)

    async def _send_firmware_report(
        self, client, package="main", state=0, reason=0, target_version=None
    ):
        import __version__

        req = {
            "state": state,
            "reason": reason,
            "package": package,
            "version": __version__.version,
        }

        if target_version is not None:
            req["target"] = target_version

        await client.post(
            ".u/c/" + package,
            json.dumps(req),
            format=_coap.CONTENT_FORMAT_APPLICATION_JSON,
        )

    async def _update_firmware(self, client, component):
        self._logger.info("Starting firmware update")

        await self._send_firmware_report(
            client,
            state=1,
            target_version=component["version"],
        )

        self._logger.info("Component %s", component)

        reader = client.get_streaming(component["uri"][1:])

        self._logger.info("Receiving firmware package")

        await self._ota_manager.do_ota_update(
            _ota.OTAUpdate(
                reader=reader,
                sha256_hash=component["hash"],
                size=component["size"],
            )
        )

        await self._send_firmware_report(
            client,
            state=2,
            target_version=component["version"],
        )

        import machine

        machine.reset()

    async def _on_golioth_firmware(self, client, packet):
        import __version__

        req = json.loads(packet.payload)
        self._logger.info("Firmware payload received: %s", req)

        if req.get("components", None) is None:
            return

        for component in req["components"]:
            if component["package"] == "main":
                if component["version"] != __version__.version:
                    asyncio.create_task(self._update_firmware(client, component))
