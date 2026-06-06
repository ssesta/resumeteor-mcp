"""Dotted-path access for YAML/dict structures.

Path syntax mirrors what the editable HTML uses:
    summary
    identity.name
    experience.0.bullets.2.text
    skills.1.items                 (list of strings — set with comma-split or list)
    certifications.0.issuer

Integer components address list indices. Missing intermediate keys / indices
raise KeyError / IndexError — we don't auto-create structure, because that
would let typos silently invent new fields.
"""

from __future__ import annotations

from typing import Any


def _split(path: str) -> list[str]:
    if not path:
        raise ValueError("empty path")
    return path.split(".")


def _step(cur: Any, key: str) -> Any:
    if isinstance(cur, list):
        return cur[int(key)]
    if isinstance(cur, dict):
        return cur[key]
    raise TypeError(f"cannot index {type(cur).__name__} with {key!r}")


def get_by_path(data: dict, path: str) -> Any:
    cur = data
    for part in _split(path):
        cur = _step(cur, part)
    return cur


def set_by_path(data: dict, path: str, value: Any) -> None:
    """Set the leaf at `path` to `value`. Path must already exist; we don't
    auto-create."""
    parts = _split(path)
    cur = data
    for part in parts[:-1]:
        cur = _step(cur, part)
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    elif isinstance(cur, dict):
        if last not in cur:
            raise KeyError(f"unknown leaf {last!r} at {path}")
        cur[last] = value
    else:
        raise TypeError(f"cannot index {type(cur).__name__} with {last!r}")
