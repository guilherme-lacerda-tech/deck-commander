"""INI que preserva o arquivo: só a parte do valor das linhas alteradas muda."""
from __future__ import annotations

import re
from pathlib import Path

_SECTION = re.compile(r"^\s*\[(.+?)\]\s*$")
_KV = re.compile(r"^(\s*)([^=;#\[][^=]*?)(\s*=\s*)(.*?)(\r?\n?)$")


class IniDoc:
    def __init__(self, lines: list[str]):
        self.lines = lines

    @classmethod
    def load(cls, path: Path) -> IniDoc:
        return cls(Path(path).read_bytes().decode("utf-8").splitlines(keepends=True))

    def dump(self) -> bytes:
        return "".join(self.lines).encode("utf-8")

    def _find(self, section: str, key: str) -> int | None:
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

    def get(self, section: str, key: str) -> str | None:
        i = self._find(section, key)
        return None if i is None else _KV.match(self.lines[i]).group(4)

    def ensure(self, section: str, key: str, value: str) -> None:
        """set() se a chave existe; senão insere logo após o cabeçalho da seção (que precisa existir)."""
        if self._find(section, key) is not None:
            return self.set(section, key, value)
        for i, ln in enumerate(self.lines):
            m = _SECTION.match(ln)
            if m and m.group(1) == section:
                eol = "\r\n" if ln.endswith("\r\n") else "\n"
                self.lines.insert(i + 1, f"{key} = {value}{eol}")
                return
        raise KeyError(f"seção [{section}] não existe")

    def ensure_section(self, section: str, key: str, value: str) -> None:
        """Como ensure(), mas cria a seção no fim se ela não existir (arquivos recém-criados)."""
        try:
            self.ensure(section, key, value)
        except KeyError:
            if self.lines and not self.lines[-1].endswith("\n"):
                self.lines[-1] += "\n"
            self.lines += [f"[{section}]\n", f"{key} = {value}\n"]

    def delete(self, section: str, key: str) -> None:
        i = self._find(section, key)
        if i is not None:
            del self.lines[i]

    def set(self, section: str, key: str, value: str) -> None:
        i = self._find(section, key)
        if i is None:
            raise KeyError(f"[{section}] {key}")
        m = _KV.match(self.lines[i])
        self.lines[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{value}{m.group(5)}"


class CfgDoc:
    """Formato do RetroArch: chave = "valor" sem seções. Preserva todo o resto."""
    _RX = re.compile(r'^(\s*)([A-Za-z0-9_\-]+)(\s*=\s*)"(.*)"(\r?\n?)$')

    def __init__(self, lines: list[str]):
        self.lines = lines

    @classmethod
    def load(cls, path: Path) -> CfgDoc:
        p = Path(path)
        return cls(p.read_text("utf-8").splitlines(keepends=True) if p.exists() else [])

    def dump(self) -> bytes:
        return "".join(self.lines).encode("utf-8")

    def get(self, key: str) -> str | None:
        for ln in self.lines:
            m = self._RX.match(ln)
            if m and m.group(2) == key:
                return m.group(4)
        return None

    def set(self, key: str, value: str) -> None:
        for i, ln in enumerate(self.lines):
            m = self._RX.match(ln)
            if m and m.group(2) == key:
                self.lines[i] = f'{m.group(1)}{key}{m.group(3)}"{value}"{m.group(5) or chr(10)}'
                return
        if self.lines and not self.lines[-1].endswith("\n"):
            self.lines[-1] += "\n"
        self.lines.append(f'{key} = "{value}"\n')
