import ribbit.mqtt as _mqtt


def assert_matches(route, topics):
    r = _mqtt._Router()
    route = r._split_route(route)
    for topic in topics:
        assert r._match(route, r._split_topic(topic))


def assert_not_matches(route, topics):
    r = _mqtt._Router()
    route = route.split("/")
    for inp in topics:
        assert not r._match(route, inp.split("/"))


def test_router():
    assert_matches(
        "sport/tennis/player1/#",
        [
            "sport/tennis/player1",
            "sport/tennis/player1/ranking",
            "sport/tennis/player1/score/wimbledon",
        ],
    )
    assert_not_matches(
        "sport/tennis/player1/#",
        [
            "sport/tennis/player2",
            "sport/tennis/player2/ranking",
            "sport/tennis/player2/score/wimbledon",
        ],
    )

    assert_matches(
        "sport/tennis/+",
        [
            "sport/tennis/player1",
            "sport/tennis/player2",
        ],
    )
    assert_not_matches(
        "sport/tennis/+",
        [
            "sport/tennis/player1/ranking",
        ],
    )
    assert_matches(
        "sport/+",
        [
            "sport/",
        ],
    )
    assert_not_matches(
        "sport/+",
        [
            "sport",
        ],
    )
