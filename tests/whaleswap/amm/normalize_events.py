import json


def try_json_parse(input_str):
    try:
        return True, json.loads(input_str)
    except Exception:
        return False, None


def deep_parse(v):
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


def parse_value(raw):
    s = str(raw or "")
    t = s.strip()
    if t.startswith("{") or t.startswith("["):
        ok, val = try_json_parse(s)
        if ok:
            return deep_parse(val)
    if t.startswith('"') and t.endswith('"'):
        ok, val = try_json_parse(s)
        if ok:
            return deep_parse(val)
    ok2, val2 = try_json_parse(s)
    if ok2:
        return deep_parse(val2)
    return s


def normalize_event_attrs(event):
    return {
        a.get("key"): parse_value(a.get("value")) for a in event.get("attributes", [])
    }


def normalize_events(events):
    event_dict = {}
    for e in events:
        if e.get("type") in event_dict:
            event_dict[e.get("type")].append(normalize_event_attrs(e))
        else:
            event_dict[e.get("type")] = [normalize_event_attrs(e)]
    return event_dict
