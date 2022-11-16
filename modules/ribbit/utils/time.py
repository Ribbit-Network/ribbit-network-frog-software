import time


def isotime(t):
    if t is None:
        return None

    parts = time.gmtime(t)

    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (
        parts[0],
        parts[1],
        parts[2],
        parts[3],
        parts[4],
        parts[5],
    )
