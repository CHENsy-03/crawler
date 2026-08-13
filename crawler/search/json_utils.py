"""Single production strict JSON decoding helper."""

import json
from typing import Any


def load_strict_json(body: bytes) -> Any:
    def _pairs_hook(pairs):
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate object key")
            result[key] = value
        return result

    return json.loads(
        body.decode("utf-8"),
        object_pairs_hook=_pairs_hook,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("invalid JSON constant")),
    )