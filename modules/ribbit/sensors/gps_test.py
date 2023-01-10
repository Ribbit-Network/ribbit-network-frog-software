def test_checksum():
    from ribbit.sensors.gps import _append_checksum

    assert (
        _append_checksum(b"$PMTK314,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
        == b"$PMTK314,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0*29\r\n"
    )


def test_location_obfuscation():
    from ribbit.sensors.gps import _obfuscate_gps_coordinate

    assert (
        _obfuscate_gps_coordinate(47.6350688) == 47.64
    )

    assert (
        _obfuscate_gps_coordinate(-122.3208268) == -122.32
    )

    assert (
        _obfuscate_gps_coordinate(0.0000000001) == 0.00
    )
