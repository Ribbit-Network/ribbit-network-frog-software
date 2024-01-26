import binascii
import sys
import time
import gc

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

    def __init__(self, registry, id, interval=24 * 3600):
        super().__init__(registry, id, interval)

    def export(self):
        import __version__

        return {
            "t": isotime(time.time()),

            "board": sys.implementation._machine,
            "version": __version__.version,
        }


class Memory(_base.PollingSensor):
    config = _config.Object(
        name="memory",
        keys=[
            _config.Integer(name="interval", default=60),
        ],
    )

    def __init__(self, registry, id, interval=60):
        super().__init__(registry, id, interval)

        self.allocated = None
        self.free = None

    async def read_once(self):
        gc.collect()
        self.allocated, self.free = gc.mem_alloc(), gc.mem_free()

    def export(self):
        return {
            "t": isotime(time.time()),

            "allocated": self.allocated,
            "free": self.free,
        }
