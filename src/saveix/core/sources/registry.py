"""Registry save sources (Windows, current user only so no admin rights are needed).

A key and all of its subkeys are captured as one deterministic JSON document, which
is stored like a file under the template ``<registry>/HKCU/...``.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Protocol

TEMPLATE_PREFIX = "<registry>/"
ROOT = "HKCU"
_ROOT_ALIASES = ("HKEY_CURRENT_USER", "HKCU")

Tree = dict[str, Any]
"""``{"values": {name: [type, value]}, "keys": {name: Tree}}``"""


class RegistryError(ValueError):
    pass


def is_registry_path(text: str) -> bool:
    return text.replace("\\", "/").split("/", 1)[0].upper().startswith(("HKEY_", "HKCU", "HKLM"))


def normalize_key(text: str) -> str:
    """Turn ``HKEY_CURRENT_USER\\Software\\X`` into ``HKCU/Software/X``."""
    parts = [p for p in text.replace("\\", "/").split("/") if p]
    if not parts or parts[0].upper() not in _ROOT_ALIASES:
        raise RegistryError("Only keys under HKEY_CURRENT_USER can be backed up")
    if len(parts) < 3:
        raise RegistryError(f"'{text}' is too broad; choose a game's own key")
    return "/".join([ROOT, *parts[1:]])


def template_for(key: str) -> str:
    return TEMPLATE_PREFIX + key


def key_from_template(template: str) -> str | None:
    return template[len(TEMPLATE_PREFIX) :] if template.startswith(TEMPLATE_PREFIX) else None


def serialize(tree: Tree) -> bytes:
    return json.dumps(tree, sort_keys=True, separators=(",", ":")).encode()


def deserialize(data: bytes) -> Tree:
    return json.loads(data)


class RegistryBackend(Protocol):
    def read_tree(self, key: str) -> Tree | None: ...

    def write_tree(self, key: str, tree: Tree) -> None:
        """Replace the key and everything under it with ``tree``."""
        ...

    def delete_tree(self, key: str) -> None: ...


class MemoryRegistry:
    """An in-memory registry, for tests and non-Windows systems."""

    def __init__(self) -> None:
        self.trees: dict[str, Tree] = {}

    def read_tree(self, key: str) -> Tree | None:
        return self.trees.get(key.casefold())

    def write_tree(self, key: str, tree: Tree) -> None:
        self.trees[key.casefold()] = json.loads(json.dumps(tree))

    def delete_tree(self, key: str) -> None:
        self.trees.pop(key.casefold(), None)


class WindowsRegistry:
    def _sub(self, key: str) -> str:
        return key.split("/", 1)[1].replace("/", "\\")

    def read_tree(self, key: str) -> Tree | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._sub(key)) as handle:
                return self._read(handle)
        except FileNotFoundError:
            return None

    def _read(self, handle: Any) -> Tree:
        import winreg

        values = {}
        index = 0
        while True:
            try:
                name, data, kind = winreg.EnumValue(handle, index)
            except OSError:
                break
            if isinstance(data, bytes):
                data = {"hex": data.hex()}
            values[name] = [kind, data]
            index += 1
        keys = {}
        index = 0
        while True:
            try:
                name = winreg.EnumKey(handle, index)
            except OSError:
                break
            with winreg.OpenKey(handle, name) as child:
                keys[name] = self._read(child)
            index += 1
        return {"values": values, "keys": keys}

    def write_tree(self, key: str, tree: Tree) -> None:
        import winreg

        self.delete_tree(key)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._sub(key)) as handle:
            self._write(handle, tree)

    def _write(self, handle: Any, tree: Tree) -> None:
        import winreg

        for name, (kind, data) in tree.get("values", {}).items():
            if isinstance(data, dict) and "hex" in data:
                data = bytes.fromhex(data["hex"])
            winreg.SetValueEx(handle, name, 0, kind, data)
        for name, child in tree.get("keys", {}).items():
            with winreg.CreateKey(handle, name) as sub:
                self._write(sub, child)

    def delete_tree(self, key: str) -> None:
        import winreg

        def delete(parent: Any, name: str) -> None:
            try:
                handle = winreg.OpenKey(parent, name, 0, winreg.KEY_ALL_ACCESS)
            except FileNotFoundError:
                return
            with handle:
                while True:
                    try:
                        child = winreg.EnumKey(handle, 0)
                    except OSError:
                        break
                    delete(handle, child)
            winreg.DeleteKey(parent, name)

        delete(winreg.HKEY_CURRENT_USER, self._sub(key))


class UnavailableRegistry:
    """Used where there is no Windows registry; registry sources report an error."""

    def read_tree(self, key: str) -> Tree | None:
        raise RegistryError("registry sources only work on Windows")

    def write_tree(self, key: str, tree: Tree) -> None:
        raise RegistryError("registry sources only work on Windows")

    def delete_tree(self, key: str) -> None:
        raise RegistryError("registry sources only work on Windows")


def system_registry() -> RegistryBackend:
    return WindowsRegistry() if sys.platform == "win32" else UnavailableRegistry()
