def test_config():
    import ribbit.config as _config

    c = _config.ConfigRegistry(
        keys=[
            _config.String(name="foo"),
            _config.String(name="bar"),
        ],
        stored=False,
    )

    with c.watch("foo", "bar") as cfg_watcher:
        foo, bar = cfg_watcher.get()
        assert foo is None
        assert bar is None

        c.set({"foo": "test"})

        assert cfg_watcher.changed
        foo, bar = cfg_watcher.get()
        assert foo == "test"
        assert bar is None

    assert not c._watchers


def test_config_override():
    import ribbit.config as _config

    c = _config.ConfigRegistry(
        keys=[
            _config.Integer(name="bar"),
        ],
        stored=False,
    )

    c.set({"bar": 1})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_LOCAL
    assert value == 1

    c.set_remote({"bar": 2})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_REMOTE
    assert value == 2

    c.set_remote({"bar": None})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_LOCAL
    assert value == 1

    c.set_override({"bar": 4})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_LOCAL_OVERRIDE
    assert value == 4


def test_config_array():
    import ribbit.config as _config

    c = _config.ConfigRegistry(
        keys=[
            _config.Array(
                name="bar",
                item=_config.Object(
                    keys=[
                        _config.String(name="foo1"),
                        _config.String(name="foo2"),
                    ],
                ),
            ),
        ],
        stored=False,
    )

    c.set({"bar": []})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_LOCAL
    assert value == []

    raised_exc = None
    try:
        c.set({"bar": ["foo"]})
    except Exception as exc:
        raised_exc = exc

    assert isinstance(raised_exc, ValueError)

    c.set({"bar": [{"foo1": "value1"}]})
    domain, value, _ = c.get("bar")
    assert domain == _config.DOMAIN_LOCAL
    assert value == [{"foo1": "value1", "foo2": None}]
