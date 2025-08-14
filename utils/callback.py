# utils/callback.py
from urllib.parse import parse_qsl
import json

def parse_callback_data(data: str):
    """
    Возвращает (key, kwargs). Поддерживает формат key?x=1&y=2.
    Автоприведение типов: int, float, bool, json.
    """
    if not data:
        return "", {}

    if "?" not in data:
        return data, {}

    key, qs = data.split("?", 1)
    pairs = parse_qsl(qs, keep_blank_values=True, strict_parsing=False)

    def coerce(val: str):
        v = val.strip()
        # bool
        low = v.lower()
        if low in ("true", "false"):
            return low == "true"
        # int
        try:
            if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                return int(v)
        except Exception:
            pass
        # float
        try:
            return float(v)
        except Exception:
            pass
        # json (объекты/массивы/числа/true/false/null)
        if (v.startswith("{") and v.endswith("}")) or (v.startswith("[") and v.endswith("]")):
            try:
                return json.loads(v)
            except Exception:
                return v
        return v

    kwargs = {}
    for k, v in pairs:
        cv = coerce(v)
        if k in kwargs:
            # поддержим повторяющиеся ключи как список
            prev = kwargs[k]
            if isinstance(prev, list):
                prev.append(cv)
            else:
                kwargs[k] = [prev, cv]
        else:
            kwargs[k] = cv

    return key, kwargs
