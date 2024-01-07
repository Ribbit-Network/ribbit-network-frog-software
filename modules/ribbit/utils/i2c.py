import machine
import asyncio


class LockableI2CBus:
    def __init__(self, id=None, scl=None, sda=None, freq=None):
        if id is not None:
            i2c = machine.I2C(id, scl=scl, sda=sda, freq=freq)
        else:
            i2c = machine.SoftI2C(scl, sda, freq=freq)

        self._i2c = i2c
        self.lock = asyncio.Lock()

    def __getattr__(self, name):
        return getattr(self._i2c, name)
