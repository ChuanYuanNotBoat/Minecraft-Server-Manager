import json
import os
from typing import Any


def load_json_file(path: str, default: Any = None, encoding: str = 'utf-8') -> Any:
    """Load JSON file and return default on failure or missing file."""
    if not os.path.exists(path):
        return default

    try:
        with open(path, 'r', encoding=encoding) as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path: str, data: Any, encoding: str = 'utf-8', ensure_ascii: bool = False, indent: int = 2) -> bool:
    """Save JSON file and return whether it succeeded."""
    try:
        with open(path, 'w', encoding=encoding) as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        return True
    except Exception:
        return False
