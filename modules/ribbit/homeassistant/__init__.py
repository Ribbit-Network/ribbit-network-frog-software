from micropython import const
import uasyncio as asyncio
import logging
import binascii
import json

import ribbit.config as _config
import ribbit.mqtt as _mqtt
import ribbit.sensors.base as _base

_CONFIG_KEYS = [
    "homeassistant.mqtt.host",
    "homeassistant.mqtt.port",
    "homeassistant.mqtt.user",
    "homeassistant.mqtt.password",
]

CONFIG_KEYS = [
    _config.String(name="homeassistant.mqtt.host"),
    _config.Integer(name="homeassistant.mqtt.port", default=1883),
    _config.String(name="homeassistant.mqtt.user"),
    _config.String(name="homeassistant.mqtt.password"),
]


class HomeAssistant:
    def __init__(self, registry):
        self._logger = logging.getLogger(__name__)
        self._config = registry.config
        self._sensors = registry.sensors
        self._mqtt = None

        self._machine_id = binascii.hexlify(registry.unique_id).decode("ascii")
        self._device_id = f"frog_{self._machine_id}"

        registry.sensors_output.add_output(self)
        asyncio.create_task(self._loop())

    async def _loop(self):
        with self._config.watch(*_CONFIG_KEYS) as cfg_watcher:
            host, port, user, password = cfg_watcher.get()
            enabled = host is not None and port is not None and user is not None and password is not None

            if self._mqtt is not None:
                self._logger.info("Stopping Home Assistant integration")
                self._mqtt.close()
                self._mqtt = None

            if enabled:
                self._mqtt = _mqtt.MQTT(
                    client_id=self._device_id,
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    on_connect_task=self._on_connect,
                    subscriptions={
                        "homeassistant/status": self._on_status_state,
                    },
                )

    async def _on_connect(self, mqtt):
        await self._register_sensors(mqtt)

    async def _on_status_state(self, mqtt, message):
        if message.data == b'online':
            await self._register_sensors(mqtt)

    def _adapt_config(self, config):
        entity_id = f"{config["device_id"]}_{config["sensor_id"]}_{config["measurement_id"]}"

        entity_config = {
            "unique_id": entity_id,
            "object_id": entity_id,

            "device": {
                "identifiers": [config["device_id"]],
                "name": f"Frog {config["device_id"]}",
            },

            "state_topic": f"ribbit/{config["device_id"]}/{config["sensor_id"]}/state",
        }

        def _copy_field(key, new_key=None):
            if new_key is None:
                new_key = key
            value = config.get(key, None)
            if value is not None:
                entity_config[new_key] = value

        _copy_field("label", "name")
        _copy_field("class", "device_class")
        _copy_field("state_class")
        _copy_field("force_update")
        _copy_field("expire_after")
        _copy_field("unit_of_measurement")
        _copy_field("suggested_display_precision")

        if config.get("diagnostic", False):
            entity_config["entity_category"] = "diagnostic"

        entity_config["value_template"] = "{{value_json." + config["measurement_id"] + "}}"

        return entity_id, entity_config

    async def _publish_sensor_config(self, mqtt, config):
        entity_id, entity_config = self._adapt_config(config)

        await mqtt.publish(
            "homeassistant/sensor/" + entity_id + "/config",
            json.dumps(entity_config).encode("utf-8"),
        )

    async def _register_sensors(self, mqtt):
        self._logger.info("Registering sensors")

        # Load the measurements from the sensor metadata:
        all_measurements = []
        measurements_by_label = {}
        for sensor_id, sensor in self._sensors.items():
            for measurement_id, config in sensor.metadata().items():
                config = config.copy()
                config["device_id"] = self._device_id
                config["sensor_id"] = sensor_id
                config["measurement_id"] = measurement_id

                if "class" in config:
                    config.setdefault("state_class", "measurement")
                    config.setdefault("force_update", True)

                if isinstance(sensor, _base.PollingSensor):
                    config.setdefault("expire_after", sensor._interval_ms * 5 // 1000)

                all_measurements.append(config)
                measurements_by_label.setdefault(config["label"], []).append(config)

        # Suffix the name of duplicate sensors:
        for label, measurements in measurements_by_label.items():
            if len(measurements) > 1:
                for config in measurements:
                    config["label"] = f"{label} ({config["sensor_id"]})"

        for config in all_measurements:
            await self._publish_sensor_config(
                mqtt,
                config,
            )

    async def write(self, sensor, data):
        try:
            await self._mqtt.publish(
                f"ribbit/{self._device_id}/{sensor._sensor_id}/state",
                json.dumps(data).encode("utf-8"),
            )
        except Exception:
            pass
