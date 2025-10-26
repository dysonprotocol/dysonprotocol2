import json
from typing import Any


def try_json_parse(input_str):
    try:
        return True, json.loads(input_str)
    except Exception:
        return False, None


def deep_parse(v: Any) -> dict[str, Any] | list[Any] | Any:
    if isinstance(v, str):
        t = v.strip()
        if t.startswith("{") or t.startswith("["):
            ok, val = try_json_parse(v)
            return deep_parse(val) if ok else v
        return v
    if isinstance(v, list):
        return [deep_parse(x) for x in v]
    if isinstance(v, dict):
        out = {}
        for k in v:
            out[k] = deep_parse(v[k])
        return out
    return v
