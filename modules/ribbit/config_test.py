def test_config():
    import ribbit.config as _config

    c = _config.ConfigRegistry(
        keys=[
            _config.ConfigKey("foo", None, _config.String()),
            _config.ConfigKey("bar", None, _config.Integer()),
        ],
        stored=False,
    )

    with c.watch("foo", "bar") as cfg_watcher:
        foo, bar = cfg_watcher.get()
        assert foo is None
        assert bar is None

        c.set(_config.DOMAIN_LOCAL, {"foo": "test"})

        assert cfg_watcher.changed
        foo, bar = cfg_watcher.get()
        assert foo == "test"
        assert bar is None

    assert not c._watchers


def test_config_override():
    import ribbit.config as _config

    c = _config.ConfigRegistry(
        keys=[
            _config.ConfigKey("bar", None, _config.Integer()),
        ],
        stored=False,
    )

    c.set(_config.DOMAIN_LOCAL, {"bar": 1})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_LOCAL
    assert value == 1

    c.set(_config.DOMAIN_REMOTE, {"bar": 2})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_REMOTE
    assert value == 2

    c.set(_config.DOMAIN_REMOTE, {"bar": None})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_LOCAL
    assert value == 1

    c.set(_config.DOMAIN_LOCAL_OVERRIDE, {"bar": 4})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_LOCAL_OVERRIDE
    assert value == 4
