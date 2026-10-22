"""Linux client for the MetaTrader 5 terminal on a Windows PC.

The laptop bridge connects out to the engine. Calls are sent over that link.
"""
from types import SimpleNamespace

from .mt5_link import hub

_CALLABLES = set()


def _to_obj(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _to_obj(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_to_obj(v) for v in value]
    return value


class RemoteMetaTrader5:
    def __init__(self, host: str = "", port: int = 0):
        self._cache = {}

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._cache:
            return self._cache[name]
        info = hub.call("__lookup__", [name], {})
        if info.get("callable"):
            def invoke(*args, **kwargs):
                result = hub.call(name, args, kwargs, timeout=90 if name == "initialize" else 45)
                if name.startswith("copy_"):
                    return result
                return _to_obj(result)

            self._cache[name] = invoke
            return invoke
        self._cache[name] = info.get("value")
        return self._cache[name]
