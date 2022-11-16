import json
import logging
import time
from micropython import const
import uasyncio as asyncio

import ribbit.config as _config
import ribbit.mqtt as _mqtt
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
CONFIG_GOLIOTH_MQTT_HOST = const("golioth.mqtt.host")
CONFIG_GOLIOTH_MQTT_PORT = const("golioth.mqtt.port")
CONFIG_GOLIOTH_MQTT_USER = const("golioth.mqtt.user")
CONFIG_GOLIOTH_MQTT_PASSWORD = const("golioth.mqtt.password")

_CONFIG_KEYS = [
    CONFIG_GOLIOTH_ENABLED,
    CONFIG_GOLIOTH_MQTT_HOST,
    CONFIG_GOLIOTH_MQTT_PORT,
    CONFIG_GOLIOTH_MQTT_USER,
    CONFIG_GOLIOTH_MQTT_PASSWORD,
]

CONFIG_KEYS = [
    _config.ConfigKey(CONFIG_GOLIOTH_ENABLED, True, _config.Boolean),
    _config.ConfigKey(CONFIG_GOLIOTH_MQTT_HOST, "mqtt.golioth.io", _config.String),
    _config.ConfigKey(CONFIG_GOLIOTH_MQTT_PORT, 8883, _config.Integer),
    _config.ConfigKey(CONFIG_GOLIOTH_MQTT_USER, None, _config.String),
    _config.ConfigKey(
        CONFIG_GOLIOTH_MQTT_PASSWORD, None, _config.String, protected=True
    ),
]


class Golioth:
    def __init__(self, config, commands=None):
        self._logger = logging.getLogger(__name__)
        self._config = config
        self._commands = commands or {}
        self._mqtt = None
        self._ota_manager = _ota.OTAManager()

        asyncio.create_task(self._loop())

    async def _loop(self):
        with self._config.watch(*_CONFIG_KEYS) as cfg_watcher:
            while True:
                enabled, host, port, user, password = cfg_watcher.get()

                enabled = enabled and (user is not None and password is not None)

                if self._mqtt is not None:
                    self._logger.info("Stopping Golioth integration")
                    self._mqtt.close()
                    self._mqtt = None

                if enabled:
                    self._logger.info("Starting Golioth integration")
                    self._mqtt = _mqtt.MQTT(
                        client_id=user,
                        user=user,
                        password=password,
                        host=host,
                        port=port,
                        ssl=True,
                        ssl_params={
                            "server_hostname": host,
                        },
                        subscriptions={
                            ".c": self._on_golioth_config,
                            ".rpc": self._on_golioth_rpc,
                            ".u/desired": self._on_golioth_firmware,
                        },
                        on_connect_task=self._on_connect,
                    )

                await cfg_watcher.wait()

    async def _on_connect(self, client):
        await self._send_firmware_report(client)

    async def _on_golioth_config(self, client, message):
        req = json.loads(message.data)
        self._logger.info("Config payload received: %s", req)

        config = {}
        for k, v in req["settings"].items():
            k = k.replace("_", ".").lower()
            config[k] = v

        self._config.set(_config.DOMAIN_REMOTE, config)

        await client.publish(
            ".c/status",
            json.dumps(
                {
                    "version": req["version"],
                    "error_code": 0,
                }
            ),
            qos=0,
        )

    def register_rpc(self, method, handler):
        self._commands[method] = handler

    def _reply_rpc(self, client, req, code, detail=None):
        res = {
            "id": req["id"],
            "statusCode": code,
        }
        if detail is not None:
            res["detail"] = detail

        return client.publish(
            ".rpc/status",
            json.dumps(res),
            qos=0,
        )

    async def _on_golioth_rpc(self, client, message):
        req = json.loads(message.data)

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

        await client.publish(
            ".u/c/" + package,
            json.dumps(req),
            qos=0,
        )

    async def _update_firmware(self, client, component):
        self._logger.info("Starting firmware update")

        await self._send_firmware_report(
            client,
            state=1,
            target_version=component["version"],
        )

        self._logger.info("Component %s", component)

        async def _do_firmware(client, message):
            self._logger.info("Receiving firmware package")

            await self._ota_manager.do_ota_update(
                _ota.OTAUpdate(
                    reader=message.reader,
                    sha256_hash=component["hash"],
                    size=component["size"],
                )
            )

        await client.get(component["uri"][1:], _do_firmware, stream=True)

        await self._send_firmware_report(
            client,
            state=2,
            target_version=component["version"],
        )

        import machine
        machine.reset()

    async def _on_golioth_firmware(self, client, message):
        import __version__

        req = json.loads(message.data)
        self._logger.info("Firmware payload received: %s", req)

        for component in req["components"]:
            if component["package"] == "main":
                if component["version"] != __version__.version:
                    asyncio.create_task(self._update_firmware(client, component))
