import sys
import time

from ribbit.utils.time import isotime as _isotime


CRITICAL = 50
ERROR = 40
WARNING = 30
INFO = 20
DEBUG = 10

_level_dict = {
    CRITICAL: "CRIT",
    ERROR: "ERROR",
    WARNING: "WARN",
    INFO: "INFO",
    DEBUG: "DEBUG",
}

_stream = sys.stderr


class LogRecord:
    def __init__(self):
        self.__dict__ = {}

    def __getattr__(self, key):
        return self.__dict__[key]


class Logger:
    def __init__(self, name):
        self.name = name
        self.setLevel(INFO)

    def setLevel(self, level):
        self.level = level
        self._level_str = _level_dict[level]

    def isEnabledFor(self, level):
        return level >= self.level

    def log(self, level, msg, *args):
        if self.isEnabledFor(level):
            if args:
                msg = msg % args
            print(
                _isotime(time.time()),
                ":",
                self._level_str,
                ":",
                self.name,
                ":",
                msg,
                sep="",
                file=_stream,
            )

    def debug(self, msg, *args):
        self.log(DEBUG, msg, *args)

    def info(self, msg, *args):
        self.log(INFO, msg, *args)

    def warning(self, msg, *args):
        self.log(WARNING, msg, *args)

    def error(self, msg, *args):
        self.log(ERROR, msg, *args)

    def critical(self, msg, *args):
        self.log(CRITICAL, msg, *args)

    def exc(self, e, msg, *args):
        self.log(ERROR, msg, *args)
        sys.print_exception(e, _stream)


_loggers: dict[str, Logger] = {}


def getLogger(name: str = "root") -> Logger:
    if name in _loggers:
        return _loggers[name]
    l = Logger(name)
    _loggers[name] = l
    return l
