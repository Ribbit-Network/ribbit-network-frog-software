import binascii
import sys
import time
import gc

import machine
import ribbit.config as _config
from ribbit.utils.time import isotime
from . import base as _base


class Board(_base.PollingSensor):
    config = _config.Object(
        name="board",
        keys=[
            _config.Integer(name="interval", default=24 * 3600),
        ],
    )

    def __init__(self, registry, interval=24 * 3600):
        super().__init__(registry, interval)

    def export(self):
        info = {
            "t": isotime(time.time()),
            "@type": "ribbitnetwork/sensor.board",
        }

        try:
            info["board_id"] = binascii.hexlify(machine.unique_id())
        except Exception:
            pass

        info["machine"] = sys.implementation._machine
        info["micropython"] = ".".join(str(part) for part in sys.implementation.version)
        return info


class Memory(_base.PollingSensor):
    config = _config.Object(
        name="memory",
        keys=[
            _config.Integer(name="interval", default=60),
        ],
    )

    def __init__(self, registry, interval=60):
        super().__init__(registry, interval)

    def export(self):
        gc.collect()
        return {
            "t": isotime(time.time()),
            "@type": "ribbitnetwork/sensor.memory",
            "allocated": gc.mem_alloc(),
            "free": gc.mem_free(),
        }
