import os
import collections
import errno
import uasyncio as asyncio
import ujson as json
from micropython import const
import logging

from .utils.asyncio import Watcher


class Invalid(Exception):
    pass


required = object()


class Key:
    def __init__(self, name=None, default=None, protected=False):
        self.name = name
        self.default = default
        self.protected = protected

    def validate(self, value):
        pass

    def hydrate(self, value):
        if value is None:
            return self.default
        return value


class String(Key):
    type_name = "string"

    def validate(self, value):
        return isinstance(value, str)


class Integer(Key):
    type_name = "integer"

    def validate(self, value):
        return isinstance(value, int)


class Float(Key):
    type_name = "float"

    def validate(self, value):
        return isinstance(value, float)


class Boolean(Key):
    type_name = "boolean"

    def validate(self, value):
        return isinstance(value, bool)


class Object(Key):
    type_name = "object"

    def __init__(self, keys, name=None, default=None, protected=False):
        super().__init__(name, default, protected)
        self.keys = {}
        self.required = set()
        for key in keys:
            self.keys[key.name] = key
            if key.default is required:
                self.required.add(key.name)

    def validate(self, value):
        if not isinstance(value, dict):
            return False

        for k, v in value.items():
            try:
                key = self.keys[k]
            except KeyError:
                return False

            if not key.validate(v):
                return False

        for k in self.required:
            if k not in value:
                return False

        return True

    def hydrate(self, value):
        value = value.copy()
        for key in self.keys.values():
            if key.name not in value:
                value[key.name] = key.default
        return value


class TypedObject(Key):
    def __init__(self, type_key, types, name=None, default=None, protected=False):
        super().__init__(name, default, protected)
        self.type_key = type_key
        self.types = {}
        for typ in types:
            self.types[typ.name] = typ

    def validate(self, value):
        if not isinstance(value, dict):
            return False

        value = value.copy()

        try:
            typ = value.pop(self.type_key)
        except KeyError:
            return False

        try:
            subtyp = self.types[typ]
        except KeyError:
            return False

        return subtyp.validate(value)

    def hydrate(self, value):
        subtyp = self.types[value[self.type_key]]
        return subtyp.hydrate(value)


class Array(Key):
    type_name = "array"

    def __init__(self, item, name=None, default=None, protected=False):
        super().__init__(name, default, protected)
        self.item = item

    def validate(self, value):
        if not isinstance(value, list):
            return False

        for item in value:
            if not self.item.validate(item):
                return False

        return True

    def hydrate(self, value):
        if value is None:
            return value

        return [self.item.hydrate(item) for item in value]


# Domain of the config keys that are not set anywhere
# else and use their default values.
DOMAIN_DEFAULT = const(-1)

# Domain of the config keys that are set locally
# on this specific node.
#
# Note: this is the index in the ConfigRegistry._config list.
DOMAIN_LOCAL = const(0)

# Domain of the config keys that are set on the cloud.
#
# Note: this is the index in the ConfigRegistry._config list.
DOMAIN_REMOTE = const(1)

# Domain of the config keys that are locally overriden on this
# specific node.
#
# Note: this is the index in the ConfigRegistry._config list.
DOMAIN_LOCAL_OVERRIDE = const(2)

_STORED_DOMAINS = [DOMAIN_LOCAL, DOMAIN_REMOTE, DOMAIN_LOCAL_OVERRIDE]
_PRIORITY_ORDER = list(reversed(_STORED_DOMAINS))

# Mapping of domain constants to paths
DOMAIN_NAMES = {
    DOMAIN_DEFAULT: "default",
    DOMAIN_LOCAL: "local",
    DOMAIN_REMOTE: "remote",
    DOMAIN_LOCAL_OVERRIDE: "override",
}

DOMAIN_PATHS = {
    DOMAIN_LOCAL: "/config/000-local.json",
    DOMAIN_REMOTE: "/config/001-remote.json",
    DOMAIN_LOCAL_OVERRIDE: "/config/002-local-override",
}


class ConfigRegistry:
    def __init__(self, keys, stored=True, in_simulator=False):
        self._logger = logging.getLogger(__name__)

        self._watchers = {}

        self._keys = collections.OrderedDict()
        for key in keys:
            self._keys[key.name] = key
            if key.default is not None:
                key.default = key.hydrate(key.default)

        self._stored = stored
        if in_simulator:
            prefix = os.getcwd() + "/data"
            self._domain_paths = {k: prefix + v for k, v in DOMAIN_PATHS.items()}
        else:
            prefix = ""
            self._domain_paths = DOMAIN_PATHS

        if stored:
            try:
                os.mkdir(prefix + "/config")
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise

        self._config = [self._load_config(domain) for domain in _STORED_DOMAINS]

    def _load_config(self, domain):
        if not self._stored:
            return {}

        filepath = self._domain_paths[domain]
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                self._logger.info("Loading config from %s", filepath)
                data = json.load(f)
                for k in data.keys():
                    if not self.is_valid_key(k):
                        del data[k]
                return data

        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return {}

            self._logger.exc(exc, "Exception reading config %s", filepath)

        except Exception as exc:
            self._logger.exc(exc, "Exception reading config %s", filepath)

        self._logger.warning("Config %s was corrupted, deleting", filepath)

        try:
            os.remove(filepath)
        except Exception:
            pass

        return {}

    def _save_config(self, domain, values):
        if not self._stored:
            return {}

        filepath = self._domain_paths[domain]
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(values, f)
        except Exception as exc:
            self._logger.exc(exc, "Failed to save config %s", filepath)

    def is_valid_key(self, key):
        return key in self._keys

    def keys(self):
        return list(self._keys.keys())

    def get(self, key):
        key_info = self._keys[key]

        for domain in _PRIORITY_ORDER:
            value = self._config[domain].get(key, None)
            if value is not None:
                return (domain, key_info.hydrate(value), key_info)

        return (DOMAIN_DEFAULT, key_info.default, key_info)

    def watch(self, *keys):
        w = Watcher(None, self._unwatch)
        w.keys = keys

        values = tuple(self.get(k)[1] for k in keys)

        for k in keys:
            self._watchers.setdefault(k, set()).add(w)

        w.notify(values)
        return w

    def _unwatch(self, w):
        for k in w.keys:
            watcher_set = self._watchers.get(k, None)
            if watcher_set is not None:
                watcher_set.discard(w)
                if not watcher_set:
                    self._watchers.pop(k)

    def _set(self, domain, config):
        assert domain in _STORED_DOMAINS

        new_keys = {}
        for k, v in config.items():
            key_info = self._keys.get(k, None)
            if key_info is None:
                continue

            if v is not None and not key_info.validate(v):
                raise ValueError("invalid value", k, v)

            new_keys[k] = v

        affected_watchers = set()
        domain_config = self._config[domain]
        for k, v in new_keys.items():
            if v is not None:
                domain_config[k] = v
            else:
                domain_config.pop(k, None)

            affected_watchers.update(self._watchers.get(k, []))

        self._save_config(domain, domain_config)

        for w in affected_watchers:
            values = tuple(self.get(k)[1] for k in w.keys)
            w.notify(values)

    def set(self, config):
        return self._set(DOMAIN_LOCAL, config)

    def set_remote(self, config):
        return self._set(DOMAIN_REMOTE, config)

    def set_override(self, config):
        return self._set(DOMAIN_LOCAL_OVERRIDE, config)
