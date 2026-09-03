"""The machine record: dataclasses, JSON load/save, validation, library ops.

No Tk in here. ``machine.json`` schema version 1 (see doc/HANDOFF-qemu-gui.md).
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path
from typing import Any

from . import paths
from .profiles import (PROFILES, DEFAULT_ROM, DEFAULT_MAC, DEFAULT_SECOND_GPU_ADDR,
                       DEFAULT_SECOND_GPU_ROM, DEFAULT_DISK_IDENTITY,
                       DEFAULT_CDROM_IDENTITY, normalise_profile_id)

SCHEMA = 1
NAME_RE = re.compile(r"^[A-Za-z0-9._ -]+$")
MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
ADDR_RE = re.compile(r"^(0x[0-9A-Fa-f]{1,2}|[0-9]{1,2})(\.[0-7])?$")

ATA_SLOT_NAMES = ["index 0 - bus 0 master", "index 1 - bus 0 slave",
                  "index 2 - bus 1 master", "index 3 - bus 1 slave"]
SCSI_IDS = list(range(7))          # 7 is the controller
DRIVE_KINDS = ("disk", "cdrom")
FORMATS = ("raw", "qcow2")
DISPLAYS = {"darwin": ("sdl", "cocoa"), "win32": ("sdl", "gtk"), "linux": ("sdl", "gtk")}
AUDIO_MODES = ("default", "sdl", "none")
NETWORK_MODES = ("user", "none")
GOVERNOR_MODES = ("default", "off", "mips")
RAM_CHOICES = (128, 256, 512, 768, 1024)
RAM_MIN, RAM_MAX = 32, 4096
SECOND_GPU_SUPPORTED = ("ati-rage128-pro",)
SECOND_GPU_EXPERIMENTAL = ("ati-vga", "VGA", "cirrus-vga")
MANAGED_FILES = ("nvram.img", "pram.img")


@dataclass
class Identity:
    vendor: str = ""
    product: str = ""
    ver: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Any) -> "Identity | None":
        if not isinstance(d, dict):
            return None
        return cls(str(d.get("vendor", "")), str(d.get("product", "")), str(d.get("ver", "")))


@dataclass
class AtaDrive:
    kind: str = "disk"           # disk | cdrom
    file: str = ""
    format: str = "raw"

    def to_dict(self) -> dict:
        return {"kind": self.kind, "file": self.file, "format": self.format}

    @classmethod
    def from_dict(cls, d: Any) -> "AtaDrive | None":
        if not isinstance(d, dict):
            return None
        return cls(str(d.get("kind", "disk")), str(d.get("file", "")), str(d.get("format", "raw")))


@dataclass
class ScsiDrive:
    id: int = 0
    kind: str = "disk"
    file: str = ""
    format: str = "raw"
    identity: Identity | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "file": self.file, "format": self.format,
                "identity": self.identity.to_dict() if self.identity else None}

    @classmethod
    def from_dict(cls, d: Any) -> "ScsiDrive | None":
        if not isinstance(d, dict):
            return None
        return cls(int(d.get("id", 0)), str(d.get("kind", "disk")), str(d.get("file", "")),
                   str(d.get("format", "raw")), Identity.from_dict(d.get("identity")))


@dataclass
class Floppy:
    file: str = ""
    format: str = "raw"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Any) -> "Floppy | None":
        if not isinstance(d, dict):
            return None
        return cls(str(d.get("file", "")), str(d.get("format", "raw")))


@dataclass
class SecondGpu:
    device: str = "ati-rage128-pro"
    addr: str = DEFAULT_SECOND_GPU_ADDR
    romfile: str | None = DEFAULT_SECOND_GPU_ROM

    def to_dict(self) -> dict:
        return {"device": self.device, "addr": self.addr, "romfile": self.romfile}

    @classmethod
    def from_dict(cls, d: Any) -> "SecondGpu | None":
        if not isinstance(d, dict):
            return None
        rom = d.get("romfile")
        return cls(str(d.get("device", "ati-rage128-pro")), str(d.get("addr", "") or ""),
                   str(rom) if rom else None)


@dataclass
class Network:
    mode: str = "user"           # user | none
    mac: str = DEFAULT_MAC

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Any) -> "Network":
        if not isinstance(d, dict):
            return cls()
        return cls(str(d.get("mode", "user")), str(d.get("mac", DEFAULT_MAC)))


@dataclass
class Governor:
    mode: str = "default"        # default | off | mips
    mips: int = 100

    def to_dict(self) -> dict:
        d = {"mode": self.mode}
        if self.mode == "mips":
            d["mips"] = self.mips
        return d

    @classmethod
    def from_dict(cls, d: Any) -> "Governor":
        if not isinstance(d, dict):
            return cls()
        return cls(str(d.get("mode", "default")), int(d.get("mips", 100) or 100))


@dataclass
class Machine:
    name: str = "New machine"
    profile: str = "custom"
    machine: str = "g3beige"
    ram_mb: int = 512
    rom: str = DEFAULT_ROM
    qemu_dir: str | None = None
    display: str = "sdl"
    audio: str = "default"
    onboard_romfile: str | None = None
    second_gpu: SecondGpu | None = None
    network: Network = field(default_factory=Network)
    governor: Governor = field(default_factory=Governor)
    ata: list = field(default_factory=lambda: [None, None, None, None])
    scsi: list = field(default_factory=list)
    floppy: Floppy | None = None
    extra_args: str = ""
    notes: str = ""

    # ---- JSON ----
    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "name": self.name,
            "profile": self.profile,
            "machine": self.machine,
            "ram_mb": self.ram_mb,
            "rom": self.rom,
            "qemu_dir": self.qemu_dir,
            "display": self.display,
            "audio": self.audio,
            "onboard_romfile": self.onboard_romfile,
            "second_gpu": self.second_gpu.to_dict() if self.second_gpu else None,
            "network": self.network.to_dict(),
            "governor": self.governor.to_dict(),
            "ata": [d.to_dict() if d else None for d in self.ata],
            "scsi": [d.to_dict() for d in sorted(self.scsi, key=lambda s: s.id)],
            "floppy": self.floppy.to_dict() if self.floppy else None,
            "extra_args": self.extra_args,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Machine":
        ata_raw = list(d.get("ata") or [])
        ata = [AtaDrive.from_dict(x) for x in ata_raw][:4]
        while len(ata) < 4:
            ata.append(None)
        scsi = [s for s in (ScsiDrive.from_dict(x) for x in d.get("scsi") or []) if s]
        m = cls(
            name=str(d.get("name", "New machine")),
            profile=normalise_profile_id(d.get("profile")),
            machine=str(d.get("machine", "g3beige")),
            ram_mb=int(d.get("ram_mb", 512)),
            rom=str(d.get("rom") or DEFAULT_ROM),
            qemu_dir=(str(d["qemu_dir"]) if d.get("qemu_dir") else None),
            display=str(d.get("display", "sdl")),
            audio=str(d.get("audio", "default")),
            onboard_romfile=(str(d["onboard_romfile"]) if d.get("onboard_romfile") else None),
            second_gpu=SecondGpu.from_dict(d.get("second_gpu")),
            network=Network.from_dict(d.get("network")),
            governor=Governor.from_dict(d.get("governor")),
            ata=ata,
            scsi=scsi,
            floppy=Floppy.from_dict(d.get("floppy")),
            extra_args=str(d.get("extra_args", "")),
            notes=str(d.get("notes", "")),
        )
        return m

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Machine":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: Path) -> "Machine":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    def copy(self) -> "Machine":
        return Machine.from_dict(self.to_dict())

    # ---- helpers ----
    def scsi_by_id(self, sid: int) -> ScsiDrive | None:
        for s in self.scsi:
            if s.id == sid:
                return s
        return None

    def first_empty_ata(self) -> int | None:
        for i, d in enumerate(self.ata):
            if d is None:
                return i
        return None

    def effective_qemu_dir(self, settings_qemu_dir: str) -> str:
        return self.qemu_dir or settings_qemu_dir


def new_machine(name: str, profile_id: str, qemu_dir: str | None) -> Machine:
    """Seed a record from an OS profile. Onboard ROM is seeded only if the
    file exists in the QEMU folder (else none); the second card is seeded
    unconditionally for the profiles that want one."""
    p = PROFILES[normalise_profile_id(profile_id)]
    m = Machine(name=name, profile=p.id, ram_mb=p.ram_mb, display=p.display, notes=p.notes)
    if p.onboard_romfile and qemu_dir and (Path(qemu_dir) / p.onboard_romfile).is_file():
        m.onboard_romfile = p.onboard_romfile
    if p.second_gpu:
        m.second_gpu = SecondGpu()
    m.ata = [AtaDrive(kind=k) if k else None for k in p.ata_default]
    return m


def default_identity(kind: str) -> Identity:
    src = DEFAULT_CDROM_IDENTITY if kind == "cdrom" else DEFAULT_DISK_IDENTITY
    return Identity(**src)


# ---------------------------------------------------------------- validation

def validate(m: Machine, qemu_dir: str | None, platform: str = paths.HOST_PLATFORM,
             check_files: bool = True) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Save is blocked on errors, allowed on warnings."""
    errors: list[str] = []
    warnings: list[str] = []

    if not m.name or not NAME_RE.match(m.name) or m.name.strip() != m.name:
        errors.append("Name must be non-empty, use only letters, digits, space, '.', '_' or '-', "
                      "and not start or end with a space.")
    if not (RAM_MIN <= m.ram_mb <= RAM_MAX):
        errors.append(f"RAM must be between {RAM_MIN} and {RAM_MAX} MB.")
    elif m.ram_mb > 1024:
        warnings.append("RAM above 1024 MB is untested (real hardware maxes at 768 MB).")
    if m.display == "cocoa" and platform != "darwin":
        warnings.append("Display 'cocoa' only exists on macOS; use sdl or gtk here.")
    if m.network.mode == "user" and not MAC_RE.match(m.network.mac):
        errors.append("MAC address must look like 00:05:02:12:34:56.")
    if m.governor.mode == "mips" and not (1 <= m.governor.mips <= 100000):
        errors.append("Custom MIPS must be between 1 and 100000.")
    if m.second_gpu:
        if m.second_gpu.addr and not ADDR_RE.match(m.second_gpu.addr):
            errors.append("Second card slot must be a PCI address like 0x0e.")
        if m.second_gpu.device in SECOND_GPU_EXPERIMENTAL:
            warnings.append(f"Second card '{m.second_gpu.device}' is unsupported/experimental.")
        if m.second_gpu.device == "ati-rage128-pro" and not m.second_gpu.romfile:
            warnings.append("ATI Rage 128 Pro without a card ROM will not drive a display "
                            "under Mac OS.")

    seen_ids = set()
    scsi_cd = False
    for s in m.scsi:
        if s.id in seen_ids:
            errors.append(f"Two SCSI drives use id {s.id}.")
        seen_ids.add(s.id)
        if s.id not in SCSI_IDS:
            errors.append(f"SCSI id {s.id} is out of range (0..6; 7 is the controller).")
        if s.kind not in DRIVE_KINDS:
            errors.append(f"SCSI id {s.id}: unknown kind '{s.kind}'.")
        if not s.file:
            warnings.append(f"SCSI id {s.id}: no image file; the slot is skipped in the launcher.")
        if s.kind == "cdrom":
            scsi_cd = True
    if len(m.ata) != 4:
        errors.append("ATA table must have exactly 4 slots.")
    ata_cd_elsewhere = False
    for i, d in enumerate(m.ata):
        if d is None:
            continue
        if d.kind not in DRIVE_KINDS:
            errors.append(f"ATA index {i}: unknown kind '{d.kind}'.")
        if not d.file:
            warnings.append(f"ATA index {i}: no image file; the slot is skipped in the launcher.")
        if d.kind == "cdrom" and i != 2:
            ata_cd_elsewhere = True
    if ata_cd_elsewhere and m.ata[2] is None:
        warnings.append("An ATA CD-ROM is configured but index 2 is empty: QEMU adds a medialess "
                        "phantom CD-ROM at index 2 itself, so put the CD at index 2.")

    if check_files:
        qd = m.effective_qemu_dir(qemu_dir or "")
        if not qd:
            warnings.append("No QEMU folder set (Settings or per-machine override).")
        elif not paths.has_qemu(qd, platform):
            warnings.append(f"QEMU binary not found in {qd}.")
        else:
            for label, rel in (("ROM", m.rom), ("onboard graphics ROM", m.onboard_romfile),
                               ("second card ROM", m.second_gpu.romfile if m.second_gpu else None)):
                if rel and not Path(paths.join_path(qd, rel, platform)).is_file():
                    warnings.append(f"{label} file not found: {paths.join_path(qd, rel, platform)}")
        for label, f in _image_files(m):
            if f and not Path(f).expanduser().is_file():
                warnings.append(f"{label}: image not found (unmounted volume?): {f}")
    return errors, warnings


def _image_files(m: Machine):
    for i, d in enumerate(m.ata):
        if d:
            yield f"ATA index {i}", d.file
    for s in m.scsi:
        yield f"SCSI id {s.id}", s.file
    if m.floppy:
        yield "Floppy", m.floppy.file


# ---------------------------------------------------------------- library

class Library:
    """The folder of machine folders. Machine name == folder name."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser()

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self, name: str) -> Path:
        return self.root / name

    def json_path(self, name: str) -> Path:
        return self.folder(name) / "machine.json"

    def names(self) -> list[str]:
        if not self.root.is_dir():
            return []
        out = []
        for p in sorted(self.root.iterdir(), key=lambda x: x.name.lower()):
            if p.is_dir() and (p / "machine.json").is_file():
                out.append(p.name)
        return out

    def load(self, name: str) -> Machine:
        m = Machine.load(self.json_path(name))
        m.name = name  # the folder is authoritative
        return m

    def load_all(self) -> list[Machine]:
        out = []
        for n in self.names():
            try:
                out.append(self.load(n))
            except (OSError, ValueError, KeyError, TypeError):
                out.append(Machine(name=n, notes="(machine.json could not be read)"))
        return out

    def save(self, m: Machine, old_name: str | None = None) -> Path:
        """Write machine.json; rename the folder if the name changed."""
        if not NAME_RE.match(m.name):
            raise ValueError("illegal machine name")
        self.ensure()
        if old_name and old_name != m.name and self.folder(old_name).is_dir():
            if self.folder(m.name).exists():
                raise FileExistsError(f"A machine named '{m.name}' already exists.")
            self.folder(old_name).rename(self.folder(m.name))
        self.folder(m.name).mkdir(parents=True, exist_ok=True)
        m.save(self.json_path(m.name))
        return self.folder(m.name)

    def exists(self, name: str) -> bool:
        return self.folder(name).exists()

    def duplicate(self, name: str, new_name: str) -> Machine:
        """Copy machine.json (+ nvram/pram if present). Disk images are NOT
        copied: the duplicate points at the same image files."""
        if self.exists(new_name):
            raise FileExistsError(f"A machine named '{new_name}' already exists.")
        m = self.load(name)
        m.name = new_name
        self.save(m)
        for f in MANAGED_FILES:
            src = self.folder(name) / f
            if src.is_file():
                shutil.copy2(src, self.folder(new_name) / f)
        return m

    def folder_contents(self, name: str) -> list[str]:
        d = self.folder(name)
        if not d.is_dir():
            return []
        return sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())

    def delete(self, name: str) -> None:
        """Delete the machine folder only. Never touches files outside it."""
        d = self.folder(name)
        if d.is_dir() and d.parent == self.root:
            shutil.rmtree(d)

    def managed_status(self, name: str) -> dict[str, int | None]:
        """{'nvram.img': size|None, 'pram.img': size|None}"""
        out: dict[str, int | None] = {}
        for f in MANAGED_FILES:
            p = self.folder(name) / f
            out[f] = p.stat().st_size if p.is_file() else None
        return out

    def reset_nvram_pram(self, name: str) -> list[str]:
        removed = []
        for f in MANAGED_FILES:
            p = self.folder(name) / f
            if p.is_file():
                p.unlink()
                removed.append(f)
        return removed
