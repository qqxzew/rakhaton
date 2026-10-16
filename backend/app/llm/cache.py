"""Disk cache for language-model results under the git-ignored data directory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def cache_key(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class LlmCache:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, prompt_version: str, key: str) -> Path:
        return self.root / "llm" / prompt_version / f"{key}.json"

    def get(self, prompt_version: str, key: str) -> dict | None:
        path = self._path(prompt_version, key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def put(self, prompt_version: str, key: str, payload: dict) -> None:
        path = self._path(prompt_version, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
