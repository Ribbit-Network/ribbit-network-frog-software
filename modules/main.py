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
            _config.DOMAIN_LOCAL,
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

    import ribbit.config as _config
    import ribbit.golioth as _golioth
    import ribbit.http as _http
    import ribbit.network as _network

    class Registry:
        pass

    registry = Registry()

    config_schema = []
    config_schema.extend(_network.CONFIG_KEYS)
    config_schema.extend(_golioth.CONFIG_KEYS)

    registry.config = _config.ConfigRegistry(config_schema)

    registry.network = _network.NetworkManager(registry.config)

    _golioth.Golioth(
        registry.config,
    )

    _setup_improv(registry)

    app = _http.build_app(registry)
    asyncio.create_task(
        app.start_server(
            port=80,
        )
    )


if __name__ == "__main__":
    asyncio.create_task(_main())
    asyncio.get_event_loop().run_forever()