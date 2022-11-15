import time


def isotime(t=None):
    if t is not None:
        parts = time.gmtime(t)
    else:
        parts = time.gmtime()

    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (
        parts[0],
        parts[1],
        parts[2],
        parts[3],
        parts[4],
        parts[5],
    )
