import uasyncio as asyncio


def _setup_improv(registry):
    import binascii

    import machine
    import network
    import ribbit.config as _config
    import ribbit.improv as _improv
    import ribbit.network as _network

    async def _improv_set_wifi_settings(ssid, password):
        registry.config.set(
            {
                _network.CONFIG_WIFI_SSID: ssid,
                _network.CONFIG_WIFI_PASSWORD: password,
            },
        )

        await asyncio.sleep(15)

    async def _improv_current_state():
        network_state = registry.network.state.value
        if network_state.state == network.STAT_GOT_IP:
            return _improv.STATE_PROVISIONED, "http://%s/" % (network_state.ip)

        _, ssid, _ = registry.config.get(_network.CONFIG_WIFI_SSID)
        _, password, _ = registry.config.get(_network.CONFIG_WIFI_PASSWORD)

        if ssid is not None and password is not None:
            return _improv.STATE_PROVISIONING, ""

        return _improv.STATE_READY, ""

    _improv.ImprovHandler(
        product_name="Ribbit Frog Sensor",
        product_version="4.0",
        hardware_name="ESP32-S3",
        device_name=binascii.hexlify(machine.unique_id()),
        scan_wifi_cb=registry.network.scan,
        set_wifi_settings_cb=_improv_set_wifi_settings,
        current_state_cb=_improv_current_state,
    )


async def _main():
    global registry

    import sys
    import os
    import json
    import machine
    import logging

    in_simulator = sys.platform == "linux"

    if in_simulator:
        sys.path.append(os.getcwd() + "/../vendor/microdot/src")
        sys.path.append(os.getcwd() + "/..")

    import ribbit.aggregate as _aggregate
    import ribbit.config as _config
    import ribbit.golioth as _golioth
    import ribbit.coap as _coap
    import ribbit.http as _http
    import ribbit.heartbeat as _heartbeat

    if not in_simulator:
        import ribbit.network as _network
    import ribbit.sensors.dps310 as _dps310
    import ribbit.sensors.board as _board
    import ribbit.sensors.gps as _gps
    import ribbit.sensors.scd30 as _scd30
    import ribbit.time_manager as _time
    import ribbit.utils.i2c as _i2c
    import ribbit.utils.ota as _ota

    class Registry:
        pass

    registry = Registry()

    _aggregate.SensorAggregator(registry)
    _heartbeat.Heartbeat(in_simulator)

    config_schema = []
    if not in_simulator:
        config_schema.extend(_network.CONFIG_KEYS)
    config_schema.extend(_golioth.CONFIG_KEYS)

    sensor_types = {
        "gps": _gps.GPS,
        "dps310": _dps310.DPS310,
        "scd30": _scd30.SCD30,
        "board": _board.Board,
        "memory": _board.Memory,
    }

    default_sensors = [
        {
            "type": "board",
            "id": "",
        },
        {
            "type": "memory",
            "id": "",
        },
    ]

    if not in_simulator:
        default_sensors.extend(
            [
                {
                    "type": "gps",
                    "id": f"gps:{_gps.DEFAULT_ADDR}",
                    "address": _gps.DEFAULT_ADDR,
                },
                {
                    "type": "dps310",
                    "id": f"dps310:{_dps310.DEFAULT_ADDR}",
                    "address": _dps310.DEFAULT_ADDR,
                },
                {
                    "type": "scd30",
                    "id": f"scd30:{_scd30.DEFAULT_ADDR}",
                    "address": _scd30.DEFAULT_ADDR,
                },
            ]
        )

    config_schema.append(
        _config.Array(
            name="sensors",
            item=_config.TypedObject(
                type_key="type",
                types={cls.config for cls in sensor_types.values()},
            ),
            default=default_sensors,
        ),
    )

    if not in_simulator:
        registry.i2c_bus = _i2c.LockableI2CBus(
            0, scl=machine.Pin(4), sda=machine.Pin(3), freq=50000
        )

        # Turn on the I2C power:
        machine.Pin(7, mode=machine.Pin.OUT, value=1, hold=True)

    else:
        registry.i2c_bus = None

    registry.config = _config.ConfigRegistry(config_schema, in_simulator=in_simulator)

    if not in_simulator:
        registry.network = _network.NetworkManager(registry.config, registry.i2c_bus)
        registry.time_manager = _time.TimeManager(registry.network)

    registry.ota_manager = _ota.OTAManager(in_simulator=in_simulator)

    registry.golioth = _golioth.Golioth(
        registry.config,
        ota_manager=registry.ota_manager,
        in_simulator=in_simulator,
    )

    registry.sensors = {}

    class Output:
        def __init__(self):
            self._logger = logging.getLogger("output")

        async def write(self, data):
            coap = registry.golioth._coap
            if coap is None or not coap.connected:
                return

            if isinstance(data, dict):
                data = [data]

            for item in data:
                try:
                    typ = item.pop("@type")
                    data = json.dumps(item)
                except Exception:
                    pass

    registry.sensors_output = Output()

    _, sensors, _ = registry.config.get("sensors")

    for sensor in sensors:
        sensor = sensor.copy()
        sensor_type = sensor.pop("type")
        registry.sensors[sensor_type] = sensor_types[sensor_type](
            registry,
            **sensor,
        )

    for sensor in registry.sensors.values():
        asyncio.create_task(sensor.loop())

    if not in_simulator:
        _setup_improv(registry)

    registry.ota_manager.successful_boot()

    app = _http.build_app(registry)
    asyncio.create_task(
        app.start_server(
            port=80 if not in_simulator else 8082,
        )
    )


if __name__ == "__main__":
    asyncio.create_task(_main())
    asyncio.get_event_loop().run_forever()
