"""The systems you might install, and sensible starting points for each.

A profile only seeds a new record and can be changed afterwards; nothing in
``command.py`` branches on it. Profiles never fill in a hard disk or a CD:
those start empty and are always the person's own choice.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    ram_mb: int
    display: str
    second_gpu: bool                # seed an ATI Rage 128 Pro in slot 0x0e
    onboard_romfile: str | None     # Mach64 GT FCode ROM name, beside the program
    ata_default: tuple              # always four empty positions; no guessed paths
    notes: str = ""


PROFILES: dict[str, Profile] = {
    "macos8_9": Profile(
        "macos8_9", "Mac OS 8 or 9", 512, "sdl", True, "ati_mach_gt.rom",
        (None, None, None, None),
        "Mac OS 8.1 wants its CD in Drive 3, or on the SCSI chain."),
    "macosx": Profile(
        "macosx", "Mac OS X (10.0 to 10.4)", 512, "sdl", True, "ati_mach_gt.rom",
        (None, None, None, None),
        "Mac OS X leaves the choice of startup disk to the Mac itself, so put the system "
        "you want to start in Drive 1."),
    "macosx_server": Profile(
        "macosx_server", "Mac OS X Server 1", 1024, "cocoa", False, "ati_mach_gt.rom",
        (None, None, None, None),
        "This one is known to work best without an extra graphics card."),
    "linux": Profile(
        "linux", "Linux", 256, "sdl", False, "ati_gt_fcode.rom",
        (None, None, None, None), ""),
    "custom": Profile(
        "custom", "Something else", 512, "sdl", False, None,
        (None, None, None, None), ""),
}

# Old/alias names accepted when loading machine.json.
PROFILE_ALIASES = {"macos9": "macos8_9", "macos8": "macos8_9", "osx": "macosx",
                   "server": "macosx_server"}

DEFAULT_SECOND_GPU_ROM = "ati_nexus128_103_pci.rom"
DEFAULT_SECOND_GPU_ADDR = "0x0e"
DEFAULT_ROM = "PowerMacG3v3.ROM"
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
