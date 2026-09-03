# Qemu-GUI -- a portable launcher for the QEMU Beige G3 (`-M g3beige`)

A small tkinter GUI that keeps one folder per emulated machine (Mac OS 9,
Mac OS X, OS X Server, Linux, ...), each with its own `machine.json`,
`nvram.img`, `pram.img` and a generated launcher (`run.command` on macOS,
`run.bat` on Windows), and that can start the machine itself.

Standard library only (Python 3.11+ with tkinter). No pip installs.

## Run from source

macOS (this Mac): Homebrew's `/opt/homebrew/bin/python3` has **no tkinter**.
Use a python.org build, e.g.

    /Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python qemu_gui.py
    # or the system one:
    /usr/bin/python3 qemu_gui.py

Windows: install Python 3.11+ from python.org (keep "tcl/tk and IDLE"
ticked), then

    py qemu_gui.py

Options: `--settings FILE` (use another settings file), `--library DIR`,
`--qemu-dir DIR` (both override and save the setting).

First run: File > Settings, point "QEMU folder" at the folder holding
`qemu-system-ppc[.exe]`, `qemu-img[.exe]` and the ROMs (`PowerMacG3v3.ROM`,
`ati_mach_gt.rom`, `ati_nexus128_103_pci.rom`). On this Mac
`/Applications/qemu-system-ppc-g3-mac-os` is auto-discovered.

## Where data lives

| what | macOS | Windows |
|---|---|---|
| settings (`library_dir`, `qemu_dir`, last machine) | `~/Library/Application Support/Qemu-GUI/settings.json` | `%APPDATA%\Qemu-GUI\settings.json` |
| machine library (changeable) | `~/Qemu-GUI-Machines/` | `%USERPROFILE%\Qemu-GUI-Machines\` |

Each machine is `<library>/<name>/` with `machine.json`, `run.command` /
`run.bat`, `last-run.log`, and after the first boot `nvram.img` (8192 bytes)
and `pram.img` (256 bytes). QEMU creates those two itself because the GUI
starts it with the machine folder as the working directory; that is what
keeps NVRAM/PRAM separate per machine. "Reset NVRAM/PRAM" deletes them.

The launcher is regenerated from `machine.json` every time the machine is
saved or started. Hand edits to it are lost.

## Tests

    python -m unittest discover -s tests

`tests/test_command.py` renders the fixtures in `tests/fixtures/` (the
user's three real launchers, plus a SCSI-with-identity machine for the
Windows `.bat` rendering) and compares them against the known-good command
lines. `qemugui/command.py`, `model.py`, `profiles.py`, `paths.py` import no
Tk, so the tests run headless.

## Packaging

    pyinstaller --noconfirm QemuGUI.spec

(equivalent to `pyinstaller --onedir --windowed --noconfirm qemu_gui.py`).
Drop the resulting `dist/QemuGUI` folder inside the QEMU folder and the QEMU
folder is found automatically.

## Tools

- `tools/smoke_boot.py <scratch-lib> <qemu-dir> <iso>`: scratch-only boot
  through the GUI's Start path with a QMP quit after 20 s.
- `tools/screenshots.py <settings.json> <out-dir>`: opens the GUI and
  captures the main window and the ATA tab (macOS `screencapture`).

## Platform notes

- Display: `sdl` or `cocoa` on macOS, `sdl` or `gtk` on Windows.
- Audio "platform default" = `coreaudio` on macOS, `dsound` on Windows;
  "none" boots over Remote Desktop.
- On Windows the `.bat` quotes any token containing a space or comma, so a
  SCSI identity comes out as
  `-device "scsi-hd,drive=shd0,scsi-id=0,vendor=QUANTUM,product=FIREBALL ST4.3S,ver=0F0C"`.
- Never boot a disk image from two machines at once.

## Networking (Addendum 1)

All modes attach the onboard bmac through `-nic ... model=bmac` (the machine
only instantiates bmac when such a nic exists). Pick the mode on the
"Network & Audio" tab; the list shows the modes for the host you are on plus
whatever the record already holds, so a record made on the other platform
loads and saves unchanged.

| mode | host | emitted |
|---|---|---|
| none | all | `-nic none` |
| user (default) | all | `-nic user,model=bmac,mac=<mac>` |
| vmnet-bridged | macOS | `-nic vmnet-bridged,ifname=<ifname>,model=bmac,mac=<mac>` (ifname default `en0`) |
| vmnet-shared | macOS | `-nic vmnet-shared,model=bmac,mac=<mac>` |
| vmnet-host | macOS | `-nic vmnet-host,model=bmac,mac=<mac>` |
| tap | Windows | `-nic tap,ifname=<adapter name>,model=bmac,mac=<mac>` |

**vmnet needs root on macOS.** For any `vmnet-*` mode the generated
`run.command` runs the binary under sudo and Start does not launch QEMU
itself: it writes the launcher and runs `open -a Terminal <machine>/run.command`,
so Terminal asks for your password (the GUI never sees it) and the status
line says "started in Terminal (sudo required for vmnet)"; there is no pid
tracking in that case. Files QEMU creates under sudo (`nvram.img`,
`pram.img`) become root-owned, so the launcher ends with exactly:

    sudo chown "${SUDO_USER:-$(id -un)}" nvram.img pram.img 2>/dev/null

(`$SUDO_USER` if the whole script was run under sudo, otherwise your own
user; sudo's cached credentials mean no second prompt). The launcher looks like:

    sudo /Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc \
    -M g3beige \
    ...
    -nic vmnet-bridged,ifname=en0,model=bmac,mac=00:05:02:12:34:56 \
    ...

    sudo chown "${SUDO_USER:-$(id -un)}" nvram.img pram.img 2>/dev/null

**Windows tap:** the `.bat` gets no sudo. A TAP-Windows adapter (from
OpenVPN's installer) must exist beforehand and `ifname` must be its name
exactly as shown in Control Panel > Network Connections (for example
`TAP-Windows Adapter V9`); run the `.bat` as Administrator if the adapter
cannot be opened.

SCSI: ids 0..6 are yours; id 7 is the Macintosh itself (the MESH
controller) and is shown as a fixed row that is never saved.
