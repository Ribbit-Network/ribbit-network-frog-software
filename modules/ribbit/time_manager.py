import logging
import time

import machine
import uasyncio as asyncio
from micropython import const
from ribbit.utils.time import isotime as _isotime

TIMESOURCE_UNKNOWN = const(0)
TIMESOURCE_NTP = const(1)
TIMESOURCE_GPS = const(2)

SOURCE_NAMES = {
    TIMESOURCE_UNKNOWN: "unknown",
    TIMESOURCE_NTP: "ntp",
    TIMESOURCE_GPS: "gps",
}


class TimeManager:
    def __init__(self, network, update_interval_per_source=None):
        self._logger = logging.getLogger(__name__)

        import __version__

        self._minimum_year = __version__.build_year

        if update_interval_per_source is not None:
            self._update_intervals = update_interval_per_source
        else:
            self._update_intervals = {
                TIMESOURCE_NTP: 24 * 3600,
                TIMESOURCE_GPS: 3600,
            }

        self.has_valid_time = self.is_valid_time(time.time())
        self.last_time_update = None
        self.last_time_source = TIMESOURCE_UNKNOWN

        network.on_connect_task(self._on_network_connect)

    def is_valid_time(self, t):
        return time.gmtime(t)[0] >= self._minimum_year

    def needs_time_update(self, source):
        if self.last_time_source is None or source > self.last_time_source:
            return True  # A better source is available

        update_interval = time.time() - self.last_time_update

        return update_interval >= self._update_intervals[source]

    def set_time(self, source, t):
        if not self.needs_time_update(source):
            return

        tm = time.gmtime(t)
        machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))

        self._logger.info(
            "Setting time to %s (source: %s)", _isotime(t), SOURCE_NAMES[source]
        )

        self.last_time_source = source
        self.last_time_update = t
        self.has_valid_time = True

    async def _on_network_connect(self, _state):
        if self.needs_time_update(TIMESOURCE_NTP):
            try:
                import ntptime
            except ImportError:
                return

            self._logger.info("Fetching current time via NTP")
            for _ in range(5):
                try:
                    t = ntptime.time()
                    break
                except OSError:
                    await asyncio.sleep_ms(100)
                    continue

            if self.is_valid_time(t):
                self.set_time(TIMESOURCE_NTP, t)

    def export(self):
        return {
            "source": SOURCE_NAMES[self.last_time_source],
            "last_update": _isotime(self.last_time_update),
            "has_valid_time": self.has_valid_time,
        }
