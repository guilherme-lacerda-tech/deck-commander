"""INI que preserva o arquivo: só a parte do valor das linhas alteradas muda."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_SECTION = re.compile(r"^\s*\[(.+?)\]\s*$")
_KV = re.compile(r"^(\s*)([^=;#\[][^=]*?)(\s*=\s*)(.*?)(\r?\n?)$")


class IniDoc:
    def __init__(self, lines: list[str]):
        self.lines = lines

    @classmethod
    def load(cls, path: Path) -> "IniDoc":
        return cls(Path(path).read_bytes().decode("utf-8").splitlines(keepends=True))

    def dump(self) -> bytes:
        return "".join(self.lines).encode("utf-8")

    def _find(self, section: str, key: str) -> Optional[int]:
        cur = None
        for i, ln in enumerate(self.lines):
            m = _SECTION.match(ln)
            if m:
                cur = m.group(1)
                continue
            if cur == section:
                kv = _KV.match(ln)
                if kv and kv.group(2).strip() == key:
                    return i
        return None

    def get(self, section: str, key: str) -> Optional[str]:
        i = self._find(section, key)
        return None if i is None else _KV.match(self.lines[i]).group(4)

    def set(self, section: str, key: str, value: str) -> None:
        i = self._find(section, key)
        if i is None:
            raise KeyError(f"[{section}] {key}")
        m = _KV.match(self.lines[i])
        self.lines[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{value}{m.group(5)}"
