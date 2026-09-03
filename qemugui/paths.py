"""Where things live: settings file, machine library, QEMU folder discovery.

No Tk in here. Platform strings follow ``sys.platform``: ``darwin``,
``win32``, anything else is treated as Linux/POSIX.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

APP_NAME = "Qemu-GUI"
HOST_PLATFORM = sys.platform  # "darwin" | "win32" | "linux"

# Fallback browse folders (the user's image library on this Mac). Used only
# if they exist; otherwise the file dialogs open in the home folder.
BROWSE_FALLBACKS = {
    "hd": Path("/Volumes/Macdata/qemu/hd"),
    "iso": Path("/Volumes/Macdata/qemu/iso"),
    "fd": Path("/Volumes/Macdata/qemu/fd"),
    "rom": Path("/Volumes/Macdata/qemu/rom"),
}

# Places a deployed QEMU install may sit on this Mac (used for discovery).
QEMU_DIR_CANDIDATES = [
    Path("/Applications/qemu-system-ppc-g3-mac-os"),
    Path("/Applications/qemu-system-ppc-g3-server12v3"),
    Path("/Applications/qemu-system-ppc-g3-linux"),
]


def is_windows(platform: str = HOST_PLATFORM) -> bool:
    return platform.startswith("win")


def qemu_binary_name(platform: str = HOST_PLATFORM) -> str:
    return "qemu-system-ppc.exe" if is_windows(platform) else "qemu-system-ppc"


def qemu_img_name(platform: str = HOST_PLATFORM) -> str:
    return "qemu-img.exe" if is_windows(platform) else "qemu-img"


def launcher_name(platform: str = HOST_PLATFORM) -> str:
    return "run.bat" if is_windows(platform) else "run.command"


def pure_path(p: str, platform: str = HOST_PLATFORM) -> PurePath:
    """A path object for *platform* without touching the filesystem."""
    return PureWindowsPath(p) if is_windows(platform) else PurePosixPath(p)


def join_path(base: str, name: str, platform: str = HOST_PLATFORM) -> str:
    """``base/name`` unless *name* is already absolute; rendered for *platform*."""
    n = pure_path(name, platform)
    if n.is_absolute():
        return str(n)
    return str(pure_path(base, platform) / n)


def settings_path(platform: str = HOST_PLATFORM) -> Path:
    """Global settings file location (overridable with $QEMU_GUI_SETTINGS)."""
    env = os.environ.get("QEMU_GUI_SETTINGS")
    if env:
        return Path(env)
    if is_windows(platform):
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return base / APP_NAME / "settings.json"
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "settings.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / APP_NAME / "settings.json"


def default_library_dir() -> Path:
    return Path.home() / "Qemu-GUI-Machines"


def app_dir() -> Path:
    """Folder holding the GUI itself (script folder, or the PyInstaller bundle folder)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def has_qemu(folder: Path | str | None, platform: str = HOST_PLATFORM) -> bool:
    if not folder:
        return False
    return (Path(folder) / qemu_binary_name(platform)).is_file()


def discover_qemu_dir(platform: str = HOST_PLATFORM) -> Path | None:
    """Best guess for the folder holding qemu-system-ppc: next to the app,
    the app's parent (a PyInstaller --onedir bundle placed inside the QEMU
    folder), the deployed installs on this Mac, then PATH."""
    candidates = [app_dir(), app_dir().parent, *QEMU_DIR_CANDIDATES]
    for c in candidates:
        if has_qemu(c, platform):
            return c
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry and has_qemu(entry, platform):
            return Path(entry)
    return None


def browse_start_dir(current: str | None, kind: str) -> Path:
    """Folder a file dialog should open in: the current value's folder, else
    the user's image library for *kind* (hd/iso/fd/rom), else home."""
    if current:
        p = Path(current).expanduser()
        d = p if p.is_dir() else p.parent
        if d.is_dir():
            return d
    fb = BROWSE_FALLBACKS.get(kind)
    if fb is not None and fb.is_dir():
        return fb
    return Path.home()


@dataclass
class Settings:
    library_dir: str = ""
    qemu_dir: str = ""
    last_machine: str = ""

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or settings_path()
        s = cls()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        for k in ("library_dir", "qemu_dir", "last_machine"):
            v = data.get(k)
            if isinstance(v, str):
                setattr(s, k, v)
        if not s.library_dir:
            s.library_dir = str(default_library_dir())
        if not s.qemu_dir:
            found = discover_qemu_dir()
            s.qemu_dir = str(found) if found else ""
        return s

    def save(self, path: Path | None = None) -> None:
        path = Path(path or settings_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
