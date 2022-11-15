def test_checksum():
    from ribbit.sensors.gps import _append_checksum

    assert (
        _append_checksum(b"$PMTK314,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
        == b"$PMTK314,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0*29\r\n"
    )
