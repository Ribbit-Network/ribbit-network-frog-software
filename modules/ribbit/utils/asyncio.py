import asyncio


class WatchableValue:
    def __init__(self, value):
        self.value = value
        self._watchers = set()

    def watch(self):
        w = Watcher(self.value, self._release_watcher)
        self._watchers.add(w)
        return w

    def set(self, value):
        if value != self.value:
            self.value = value
            for w in self._watchers:
                w.notify(value)

    def _release_watcher(self, w):
        self._watchers.discard(w)


class Watcher:
    def __init__(self, value, release_cb=None):
        self._value = value
        self._release_cb = release_cb
        self._changed = asyncio.Event()
        self.generation = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()

    def release(self):
        if self._release_cb is not None:
            self._release_cb(self)

    def peek(self):
        return self._value

    def get(self):
        self._changed.clear()
        return self._value

    def notify(self, value):
        self._value = value
        self.generation += 1
        self._changed.set()

    @property
    def changed(self):
        return self._changed.is_set()

    def wait(self):
        return self._changed.wait()
