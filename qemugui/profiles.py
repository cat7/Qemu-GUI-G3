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


# The five systems the System list offers, in the order it offers them. Each
# id is its own label written plainly, so a saved record or a fixture says
# which system it means without a lookup table.
PROFILES: dict[str, Profile] = {
    "macos_8_to_9": Profile("macos_8_to_9", "Mac OS 8 to 9", 512, True),
    "macosx_10_0_to_10_2": Profile("macosx_10_0_to_10_2", "Mac OS X 10.0 to 10.2", 512, True),
    "osx_server_1_2v3": Profile("osx_server_1_2v3", "OSX Server 1.2v3", 1024, False),
    "linux": Profile("linux", "Linux", 256, False),
    "other": Profile("other", "Other", 512, False),
}

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
    return PROFILES["other"]


def normalise_profile_id(pid: str | None) -> str:
    """A record names one of the five, or it is "Other". Nothing is
    translated here: there are no older names to translate."""
    return pid if pid in PROFILES else "other"
