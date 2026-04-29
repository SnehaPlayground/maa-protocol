"""IPFS client compatibility layer with local mock store fallback."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IPFS_ROOT = Path('/tmp/maa-x-ipfs')
IPFS_ROOT.mkdir(parents=True, exist_ok=True)
OBJECTS = IPFS_ROOT / 'objects'
OBJECTS.mkdir(parents=True, exist_ok=True)
PINS = IPFS_ROOT / 'pins.json'


@dataclass
class IPFSObject:
    cid: str
    size: int
    pinned: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class IPFSClient:
    def __init__(self) -> None:
        self._pins = self._load_pins()

    def _load_pins(self) -> set[str]:
        if PINS.exists():
            try:
                return set(json.loads(PINS.read_text()))
            except Exception:
                pass
        return set()

    def _save_pins(self) -> None:
        PINS.write_text(json.dumps(sorted(self._pins), indent=2))

    def add_bytes(self, data: bytes, metadata: dict[str, Any] | None = None) -> IPFSObject:
        cid = hashlib.sha256(data).hexdigest()
        path = OBJECTS / cid
        path.write_bytes(data)
        return IPFSObject(cid, len(data), cid in self._pins, metadata or {})

    def add_text(self, text: str, metadata: dict[str, Any] | None = None) -> IPFSObject:
        return self.add_bytes(text.encode(), metadata)

    def cat(self, cid: str) -> bytes:
        return (OBJECTS / cid).read_bytes()

    def cat_text(self, cid: str) -> str:
        return self.cat(cid).decode('utf-8', errors='replace')

    def pin(self, cid: str) -> bool:
        if not (OBJECTS / cid).exists():
            return False
        self._pins.add(cid)
        self._save_pins()
        return True

    def unpin(self, cid: str) -> bool:
        existed = cid in self._pins
        self._pins.discard(cid)
        self._save_pins()
        return existed

    def is_pinned(self, cid: str) -> bool:
        return cid in self._pins

    def stat(self, cid: str) -> IPFSObject | None:
        path = OBJECTS / cid
        if not path.exists():
            return None
        return IPFSObject(cid, path.stat().st_size, cid in self._pins)

    def list_pins(self) -> list[str]:
        return sorted(self._pins)


_client = IPFSClient()


def add_text(text: str, metadata: dict[str, Any] | None = None) -> IPFSObject:
    return _client.add_text(text, metadata)


def add_bytes(data: bytes, metadata: dict[str, Any] | None = None) -> IPFSObject:
    return _client.add_bytes(data, metadata)


def cat(cid: str) -> bytes:
    return _client.cat(cid)


def cat_text(cid: str) -> str:
    return _client.cat_text(cid)


def pin(cid: str) -> bool:
    return _client.pin(cid)


def unpin(cid: str) -> bool:
    return _client.unpin(cid)


def list_pins() -> list[str]:
    return _client.list_pins()
