# Qemu-system-ppc GUI

A small window for starting an emulated PowerMac G3: one entry per machine,
each with its own settings, its own hard disk and CD, and its own copy of
what the Mac itself remembers.

Python 3.11+ with tkinter. Nothing to install, no pip packages.

## Where it goes

**Qemu-system-ppc GUI must sit in the same folder as `qemu-system-ppc`.** That folder is
the whole configuration: there is nothing to point at and nothing to set.

    /wherever/you/keep/qemu/
        qemu-system-ppc          <- the emulator
        qemu-img                 <- comes with it; needed to make a hard disk
        PowerMacG3v3.ROM         <- the Mac's ROM
        ati_mach_gt.rom          <- graphics startup files
        ati_nexus128_103_pci.rom
        "Qemu-system-ppc GUI.app" <- this program (or qemu_gui.py from source)
        Machines/                <- made by the program, one folder per machine

If the emulator is not beside it, the program says so and closes. It does not
offer to go looking, and it does not half-work.

On Windows the same, with `qemu-system-ppc.exe`, `qemu-img.exe` and
`"Qemu-system-ppc GUI.exe"`.

## Running it

From source, with a Python that has tkinter (Homebrew's `python3` on macOS
does **not**):

    /Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python qemu_gui.py
    # or the system one:
    /usr/bin/python3 qemu_gui.py

On Windows, install Python 3.11+ from python.org with "tcl/tk and IDLE"
ticked, then `py qemu_gui.py`.

There are no command-line options.

## The main window

On the left the machines, with **New machine…**, **Duplicate**, **Edit**,
**Delete…**, **Open machine folder** and **Start this Mac**. On the right,
for whichever machine is picked: how it ran and where it is kept, then
**Command line constructed:** — the exact command Start will run — and
**My notes** underneath it.

## The settings window

**New machine…** opens this window straight away, on the Machine page, with
Name empty and System on the first of the five. Nothing exists until Save;
Cancel makes nothing.

Five pages: **Machine** (name, system, memory, display, ROM, my notes),
**Display** (the built-in graphics and the extra card), **Drives** (the four
positions inside the Mac, the SCSI chain, the floppy drive, and "Create new
disk image…"), **Network & sound**, and **Advanced** (speed, extra options).

## Where your machines are kept

Everything is in `Machines/` next to the program, one folder per machine:

| file | what it is |
|---|---|
| `machine.json` | how the machine is set up |
| `run.command` / `run.bat` | the file that starts it, written afresh each time |
| `nvram.img`, `pram.img` | what the Mac itself remembers: startup disk, date, screen |
| `last-run.log` | what the emulator printed the last time it ran |
| anything else | **yours**, and never touched |

The emulator is started with the machine's own folder as the working
directory, which is what keeps each machine's saved settings separate.

## Deleting a machine never deletes a disk image

A disk image can be hours of installing an operating system, so **no disk
image is ever deleted here, and none is ever written over.**

"Delete…" removes exactly four kinds of file: `machine.json`, the launcher,
`last-run.log`, and the Mac's saved settings. Any other file in the folder —
a `.img`, a `.qcow2`, an `.iso`, your own notes — is left where it is, and
the folder itself stays behind to hold them. The confirmation lists what will
be kept, and where, before you press anything.

"Create new disk image…" refuses a name that already exists rather than
writing over it.

"Duplicate" copies the settings only. The copy points at the same disk
image as the original — do not run both at once.

Renaming a machine moves its folder; any image kept inside moves with it and
the record is re-pointed at the new place.

## Nothing is filled in for you

No field that names a file is ever filled in by the program: not the Mac's
ROM, not the graphics ROMs, not a hard disk, a CD or a floppy. Every one of
them starts empty and stays empty until you pick something, whatever files
happen to be sitting next to the emulator. A file field *is* its own chooser,
and is editable: type or paste a path into it, or double-click it to open the
file dialog at a sensible folder.

A new machine is therefore incomplete on purpose, and can be saved that way
and finished another day. It will not start without a ROM: Start says so
plainly instead of guessing one.

## The four drive positions

The Mac has room for four drives inside it, and they are named for what they
are for. They are the top of the **Drives** page, which also holds the SCSI
chain and the floppy drive:

| shown as | what it is for | what QEMU is told |
|---|---|---|
| Drive 1 | the Mac starts up from this one (IDE bus 0, master) | `index=0` |
| Drive 2 | room for a second hard disk (IDE bus 0, slave) | `index=1` |
| Drive 3 | the usual place for the CD drive (IDE bus 1, master) | `index=2` |
| Drive 4 | room for a fourth drive (IDE bus 1, slave) | `index=3` |

Put the CD in Drive 3: the Mac expects a CD drive there and invents an empty
one if nothing claims the position, which can hide the CD you did put in.

## SCSI

The SCSI chain is the second part of the **Drives** page. Every device on it
has its own number so the Mac can tell them apart; they are called
**Device 0** to **Device 6**,
and shows **Device 7** as the Mac itself, which cannot be given to a drive.
The number in the name is the SCSI ID.

"Pretend" makes a drive introduce itself as a real make and model
(`QUANTUM FIREBALL ST4.3S`, `MATSHITA CD-ROM CR-8005`), which some old
installers insist on.

The Mac prefers a SCSI CD over the CD in Drive 3; holding C at startup picks
the first CD it finds; the Startup Disk control panel wins over both.

## Tests

    /Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python -m unittest discover -s tests

`tests/test_command.py` builds the fixtures in `tests/fixtures/` and compares
them against the real, known-good command lines. `tests/test_app.py` covers
where the program thinks it is installed, its refusal to start without the
emulator, and the promise that no code path deletes or overwrites a disk
image. Both run headless: `command.py`, `model.py`, `profiles.py` and
`paths.py` import no Tk.

## Packaging

    pyinstaller --noconfirm QemuGUI.spec

Put the resulting `dist/Qemu-system-ppc GUI.app` (macOS) or the contents of
`dist/Qemu-system-ppc GUI/` (Windows) into the folder that holds the emulator.
The
packaged program works out that folder by walking up out of its own bundle,
so `Machines/` lands beside the application and never inside it — a bundle
is read-only.

## Networking

The onboard Ethernet is attached with `-nic ... model=bmac`. Pick the
connection on the "Network & sound" page; the list shows what works on the
computer you are on, plus whatever the machine is already set to, so a
machine set up on the other platform loads and saves unchanged.

| shown as | host | emitted |
|---|---|---|
| none | all | `-nic none` |
| user (the usual choice) | all | `-nic user,model=bmac,mac=<mac>` |
| vmnet-bridged | macOS | `-nic vmnet-bridged,ifname=<ifname>,model=bmac,mac=<mac>` |
| vmnet-shared | macOS | `-nic vmnet-shared,model=bmac,mac=<mac>` |
| vmnet-host | macOS | `-nic vmnet-host,model=bmac,mac=<mac>` |
| tap | Windows | `-nic tap,ifname=<adapter>,model=bmac,mac=<mac>` |

The `vmnet-*` connections put the Mac on the real network and need an
administrator password. Start writes the launcher and opens it in Terminal so
Terminal can ask for the password (the password is never seen here); the
launcher runs
the emulator under `sudo`, holds the password ticket open for the whole run
so it is asked for once only, and hands `nvram.img` and `pram.img` back to
you at the end:

    sudo chown "${SUDO_USER:-$(id -un)}" nvram.img pram.img 2>/dev/null

On Windows, `tap` needs a TAP-Windows adapter (from OpenVPN) installed
beforehand, named exactly as it appears in Network Connections.

## Other notes

- Display: `cocoa` or `sdl` on macOS, `sdl` or `gtk` on Windows. New machines
  start on `cocoa` on a Mac and `sdl` everywhere else.
- Sound plays through `coreaudio` on macOS and `dsound` on Windows; turn it
  off to boot over Remote Desktop.
- On Windows the `.bat` quotes any token with a space or a comma, so a SCSI
  identity comes out as
  `-device "scsi-hd,drive=shd0,scsi-id=0,vendor=QUANTUM,product=FIREBALL ST4.3S,ver=0F0C"`.
- Never start the same disk image from two machines at once.

## Tools

- `tools/smoke_boot.py <scratch-dir> <qemu-dir> <iso>` — a real boot through
  the Start button, into a scratch folder, quit over QMP after 20 s.
- `tools/screenshots.py <install-dir> <out-dir>` — the main window and the
  settings window.
- `tools/render_fixture.py <machine.json> [platform] [machine-dir]` — print
  the launcher a record produces.
