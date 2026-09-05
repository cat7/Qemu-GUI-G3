"""Build the QEMU argv for a Machine and render it as run.command / run.bat.

Pure: no Tk, no filesystem access beyond string handling. The GUI renders
for the platform it runs on; tests pass ``platform=`` explicitly
(``"darwin"``, ``"win32"``, ``"linux"``).

QEMU itself parses ``vendor=X,product=Y Z``; the shell quoting produced
here only keeps each token whole. One argv list, two renderings.
"""

from __future__ import annotations

import shlex

from . import paths
from .model import Machine

HEADER_NOTE = ("Written by Qemu-GUI. Do not edit: this file is written again from "
               "scratch every time the machine is saved or started, and your changes "
               "would be lost. Change the machine in Qemu-GUI instead.")

AUDIO_DEFAULT = {"darwin": "coreaudio", "win32": "dsound"}


def qopt(value: str) -> str:
    """Escape a value for QEMU's key=value option parser (comma -> ,,)."""
    return str(value).replace(",", ",,")


def _path(p: str, base: str, platform: str) -> str:
    """Absolute path for *platform*; relative values resolve against *base*."""
    return paths.join_path(base, p, platform)


def split_extra_args(text: str, platform: str = paths.HOST_PLATFORM) -> list[str]:
    """Tokenise the free-text extra arguments line. On Windows backslashes are
    path separators, not escapes, so escape processing is disabled there."""
    text = (text or "").strip()
    if not text:
        return []
    lex = shlex.shlex(text, posix=True)
    lex.whitespace_split = True
    lex.commentchars = ""
    if paths.is_windows(platform):
        lex.escape = ""
    return list(lex)


def governor_option(m: Machine) -> str:
    g = m.governor
    if g.mode == "off":
        return f"{m.machine},calibration-governor=off"
    if g.mode == "mips":
        return f"{m.machine},calibration-governor=mips={int(g.mips)}"
    return m.machine


def nic_option(net) -> str:
    """The -nic value. Every mode goes through -nic with model=bmac: macio.c
    only instantiates the onboard bmac when such a nic exists."""
    if net.mode == "none":
        return "none"
    tail = f"model=bmac,mac={net.mac}"
    if net.mode == "user":
        return f"user,{tail}"
    if net.mode in ("vmnet-bridged", "tap"):
        return f"{net.mode},ifname={qopt(net.ifname)},{tail}"
    if net.mode in ("vmnet-shared", "vmnet-host"):
        return f"{net.mode},{tail}"
    raise ValueError(f"unknown network mode {net.mode!r}")


def needs_sudo(m: Machine, platform: str = paths.HOST_PLATFORM) -> bool:
    """vmnet-* launchers run the binary under sudo (macOS only; never in a .bat)."""
    return m.network.needs_sudo and not paths.is_windows(platform)


def build_argv(m: Machine, qemu_dir: str, machine_dir: str,
               platform: str = paths.HOST_PLATFORM) -> list[str]:
    """The complete argv, first token = absolute path of the QEMU binary.

    *qemu_dir* is the folder Qemu-GUI itself lives in; the caller passes it
    in so this module stays free of any notion of where that is."""
    qd = qemu_dir
    argv: list[str] = [paths.join_path(qd, paths.qemu_binary_name(platform), platform)]

    argv += ["-M", governor_option(m)]
    argv += ["-m", str(int(m.ram_mb))]
    argv += ["-bios", _path(m.rom, qd, platform)]
    argv += ["-display", m.display]

    audio = m.audio
    if audio == "default":
        audio = AUDIO_DEFAULT.get(platform, "sdl")
    argv += ["-audiodev", f"{audio},id=snd", "-global", "awacs.audiodev=snd"]

    if m.onboard_romfile:
        argv += ["-global", f"ati-mach64-gt.romfile={qopt(_path(m.onboard_romfile, qd, platform))}"]

    if m.second_gpu and m.second_gpu.device:
        parts = [m.second_gpu.device]
        if m.second_gpu.addr:
            parts.append(f"addr={m.second_gpu.addr}")
        if m.second_gpu.romfile:
            parts.append(f"romfile={qopt(_path(m.second_gpu.romfile, qd, platform))}")
        argv += ["-device", ",".join(parts)]

    argv += ["-nic", nic_option(m.network)]

    for index, d in enumerate(m.ata):
        if d is None or not d.file:
            continue  # empty slot, or a profile-seeded slot with no image yet
        media = "cdrom" if d.kind == "cdrom" else "disk"
        argv += ["-drive", f"file={qopt(_path(d.file, machine_dir, platform))},"
                           f"format={d.format or 'raw'},media={media},index={index}"]

    for s in sorted(m.scsi, key=lambda x: x.id):
        if not s.file:
            continue
        prefix = "scd" if s.kind == "cdrom" else "shd"
        drive_id = f"{prefix}{s.id}"
        dev = "scsi-cd" if s.kind == "cdrom" else "scsi-hd"
        argv += ["-drive", f"file={qopt(_path(s.file, machine_dir, platform))},"
                           f"format={s.format or 'raw'},if=none,id={drive_id}"]
        tok = f"{dev},drive={drive_id},scsi-id={s.id}"
        if s.identity:
            ident = s.identity
            tok += (f",vendor={qopt(ident.vendor)},product={qopt(ident.product)},"
                    f"ver={qopt(ident.ver)}")
        argv += ["-device", tok]

    if m.floppy and m.floppy.file:
        argv += ["-drive", f"if=none,id=fd,file={qopt(_path(m.floppy.file, machine_dir, platform))},"
                           f"format={m.floppy.format or 'raw'}",
                 "-global", "swim3.drive=fd"]

    argv += split_extra_args(m.extra_args, platform)
    return argv


def group_options(argv: list[str]) -> list[list[str]]:
    """Group [binary, -opt, value, -opt, ...] into one list per option so
    each option lands on its own line in the rendered launcher."""
    groups: list[list[str]] = []
    for tok in argv[1:]:
        if tok.startswith("-") or not groups:
            groups.append([tok])
        else:
            groups[-1].append(tok)
    return groups


SUDO_NOTE = ("# vmnet networking needs root: the binary runs under sudo (Terminal asks for "
             "the password). Files QEMU creates under sudo are root-owned, so they are "
             "given back to the user afterwards.")
# Ask for the password ONCE. Without the keep-alive, sudo's ticket expires
# during any run longer than its timeout (5 minutes by default) and the chown
# below prompts a second time, in the middle of the guest's own output.
SUDO_KEEPALIVE = ('sudo -v\n'
                  'while true; do sudo -n true; sleep 60; '
                  'kill -0 "$$" 2>/dev/null || exit; done &\n'
                  'SUDO_KEEPALIVE_PID=$!')
CHOWN_LINE = ('kill "$SUDO_KEEPALIVE_PID" 2>/dev/null\n'
              'sudo -n chown "${SUDO_USER:-$(id -un)}" nvram.img pram.img 2>/dev/null')


def render_shell(argv: list[str], sudo: bool = False) -> str:
    lines = ["#!/bin/bash",
             f"# {HEADER_NOTE}",
             'cd "$(dirname "$0")"',
             ""]
    if sudo:
        lines += [SUDO_NOTE, SUDO_KEEPALIVE, ""]
    lines.append(("sudo " if sudo else "") + shlex.quote(argv[0]) + " \\")
    groups = group_options(argv)
    for i, g in enumerate(groups):
        cont = " \\" if i < len(groups) - 1 else ""
        lines.append(" ".join(shlex.quote(t) for t in g) + cont)
    if sudo:
        lines += ["", CHOWN_LINE]
    return "\n".join(lines) + "\n"


def bat_quote(token: str) -> str:
    """cmd.exe quoting: whole-token double quotes when the token contains a
    space or a comma (contract rule); '%' must be doubled in a .bat file."""
    t = token.replace("%", "%%")
    if (" " in t or "," in t) and not (t.startswith('"') and t.endswith('"')):
        return f'"{t}"'
    return t


def render_bat(argv: list[str]) -> str:
    lines = ["@echo off",
             f"rem {HEADER_NOTE}",
             'cd /d "%~dp0"',
             "",
             bat_quote(argv[0]) + " ^"]
    groups = group_options(argv)
    for i, g in enumerate(groups):
        cont = " ^" if i < len(groups) - 1 else ""
        lines.append(" ".join(bat_quote(t) for t in g) + cont)
    return "\r\n".join(lines) + "\r\n"


def render_launcher(argv: list[str], platform: str = paths.HOST_PLATFORM, sudo: bool = False) -> str:
    """The .bat never gets sudo; *sudo* only affects the shell rendering."""
    return render_bat(argv) if paths.is_windows(platform) else render_shell(argv, sudo)


def launcher_text(m: Machine, qemu_dir: str, machine_dir: str,
                  platform: str = paths.HOST_PLATFORM) -> str:
    return render_launcher(build_argv(m, qemu_dir, machine_dir, platform), platform,
                           needs_sudo(m, platform))


def write_launcher(m: Machine, qemu_dir: str, machine_dir: str,
                   platform: str = paths.HOST_PLATFORM):
    """Write run.command / run.bat into the machine folder; returns (path, argv)."""
    from pathlib import Path
    import os
    import stat
    argv = build_argv(m, qemu_dir, machine_dir, platform)
    text = render_launcher(argv, platform, needs_sudo(m, platform))
    path = Path(machine_dir) / paths.launcher_name(platform)
    path.write_text(text, encoding="utf-8", newline="")
    if not paths.is_windows(platform):
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path, argv
