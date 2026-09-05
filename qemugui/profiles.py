"""The systems you might install, and sensible starting points for each.

A profile only seeds a new record and can be changed afterwards; nothing in
``command.py`` branches on it.

**A profile never chooses a file.** Not a hard disk, not a CD, not a ROM: no
field that names a file is ever filled in by the program, whatever happens to
be lying next to the emulator. Files are the person's own choice, always.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    ram_mb: int
    second_gpu: bool                # seed an ATI Rage 128 Pro in slot 0x0e


PROFILES: dict[str, Profile] = {
    "macos8_9": Profile("macos8_9", "Mac OS 8 or 9", 512, True),
    "macosx": Profile("macosx", "Mac OS X (10.0 to 10.4)", 512, True),
    "macosx_server": Profile("macosx_server", "Mac OS X Server 1", 1024, False),
    "linux": Profile("linux", "Linux", 256, False),
    "custom": Profile("custom", "Something else", 512, False),
}

# Old/alias names accepted when loading machine.json.
PROFILE_ALIASES = {"macos9": "macos8_9", "macos8": "macos8_9", "osx": "macosx",
                   "server": "macosx_server"}

DEFAULT_SECOND_GPU_ADDR = "0x0e"
DEFAULT_MAC = "00:05:02:12:34:56"

# What a SCSI drive says it is when "Pretend" is ticked: a real Quantum disk
# and a real Matsushita CD drive, which old installers recognise.
DEFAULT_DISK_IDENTITY = {"vendor": "QUANTUM", "product": "FIREBALL ST4.3S", "ver": "0F0C"}
DEFAULT_CDROM_IDENTITY = {"vendor": "MATSHITA", "product": "CD-ROM CR-8005", "ver": "1.0k"}


def profile_ids() -> list[str]:
    return list(PROFILES)


def profile_labels() -> list[str]:
    return [p.label for p in PROFILES.values()]


def profile_by_label(label: str) -> Profile:
    for p in PROFILES.values():
        if p.label == label:
            return p
    return PROFILES["custom"]


def normalise_profile_id(pid: str | None) -> str:
    if not pid:
        return "custom"
    pid = PROFILE_ALIASES.get(pid, pid)
    return pid if pid in PROFILES else "custom"
