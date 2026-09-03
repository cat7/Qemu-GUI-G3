"""OS profiles: defaults applied when a machine is created (editable after).

Profiles only seed the record. Nothing in ``command.py`` branches on them.
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
    onboard_romfile: str | None     # Mach64 GT FCode ROM name in the QEMU folder
    ata_default: tuple            # ("disk"|"cdrom"|None) x 4
    notes: str = ""


PROFILES: dict[str, Profile] = {
    "macos8_9": Profile(
        "macos8_9", "Mac OS 8 / 9", 512, "sdl", True, "ati_mach_gt.rom",
        ("disk", None, "cdrom", None),
        "OS 8.1 needs the SCSI CD or ATA CD at index 2."),
    "macosx": Profile(
        "macosx", "Mac OS X 10.x", 512, "sdl", True, "ati_mach_gt.rom",
        ("disk", None, "cdrom", None),
        "Startup Disk in OS X delegates to the ROM: the bootable disk at index 0 wins."),
    "macosx_server": Profile(
        "macosx_server", "Mac OS X Server 1.x", 1024, "cocoa", False, "ati_mach_gt.rom",
        ("disk", None, "cdrom", None),
        "The known-working configuration has no second graphics card."),
    "linux": Profile(
        "linux", "Linux", 256, "sdl", False, "ati_gt_fcode.rom",
        (None, None, "cdrom", None), ""),
    "custom": Profile(
        "custom", "Custom", 512, "sdl", False, None,
        (None, None, None, None), ""),
}

# Old/alias names accepted when loading machine.json.
PROFILE_ALIASES = {"macos9": "macos8_9", "macos8": "macos8_9", "osx": "macosx",
                   "server": "macosx_server"}

DEFAULT_SECOND_GPU_ROM = "ati_nexus128_103_pci.rom"
DEFAULT_SECOND_GPU_ADDR = "0x0e"
DEFAULT_ROM = "PowerMacG3v3.ROM"
DEFAULT_MAC = "00:05:02:12:34:56"

# Prefilled SCSI identity strings, exactly as the user writes them.
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
