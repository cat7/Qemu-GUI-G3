# HANDOFF: Qemu-GUI -- a portable launcher GUI for the Beige G3 machine

Contract for a reader with zero shared context. Read this whole file before
writing code. Everything you need is either in this file or at a path it
names. Where this file and your own assumptions differ, this file wins.

Written 2026-09-03 by the main session. The user (git name `cat7`,
email `hsp.cat7@gmail.com`) owns the requirements listed in "What the user
asked for"; everything else is the main session's design, chosen to match
how the user already launches the machine today.

## What the user asked for (verbatim requirements, 2026-09-03)

"A simple portable GUI for the G3 for macOS and Windows. The GUI keeps
separate records for each machine created, for e.g. Mac OS 9, Mac OS X or
OS X Server. It also keeps pram and nvram separate for these machines. It
creates the command file to run these machines and shows it in overview.
The GUI can start the machine. It offers selection options for the various
hard disk and cd entries for both ATA and SCSI drives." Added a minute
later: "it will also offer floppy selection, and second graphics card
selection. The source should go into a separate local tree Qemu-GUI."

Every sentence above is an acceptance criterion. See "Acceptance" at the
end for the checkable form.

## Where things are

| what | path |
|---|---|
| this tree (your workspace, its own git repo, branch `main`, no remote) | `/Users/hsp/src/claude-code/Qemu-GUI` |
| the QEMU source tree that defines the machine (READ ONLY for you) | `/Users/hsp/src/claude-code/qemu-master-g3` (branch `g3beige`) |
| a freshly built binary + qemu-img for smoke tests | `/Users/hsp/src/claude-code/qemu-master-g3/build-g3/qemu-system-ppc`, `.../build-g3/qemu-img` |
| the user's deployed macOS "Mac OS" install (binary, ROMs, launchers) | `/Applications/qemu-system-ppc-g3-mac-os/` |
| the user's deployed "OS X Server 1.2v3" install | `/Applications/qemu-system-ppc-g3-server12v3/` |
| the user's deployed "Linux" install | `/Applications/qemu-system-ppc-g3-linux/` |
| the user's disk images (NEVER boot these, see Rules) | `/Volumes/Macdata/qemu/hd/*.img` |
| the user's CD images | `/Volumes/Macdata/qemu/iso/*.iso` |
| the user's floppy images | `/Volumes/Macdata/qemu/fd/**/*.img`, `*.dsk` |
| machine ROMs | `/Volumes/Macdata/qemu/rom/PowerMacG3v3.ROM` (the right one; `PowerMacG3desktop.ROM` is a different board revision, do not default to it) |
| the user's previous GUI attempt (mac99-era, FreeSimpleGUI, for style reference only, do NOT copy its prefs-slot design) | `/Users/hsp/PycharmProjects/QemuGUI-PPC/QemuGUI-ppc.py` |

`/Users/hsp/src/claude-code/SourceFiles/` and any `patches/` folder are
read-only reference material. Never write there.

## Ground truth about the machine you are launching

All of this was verified in the g3beige tree on 2026-09-03 unless a date
says otherwise. Do not re-derive it from upstream QEMU docs: this tree
carries ~80 local commits and several of these options exist only here.

### The user's real launcher today (macOS, "Mac OS" machine)

```bash
#!/bin/bash
cd "$(dirname "$0")"

./qemu-system-ppc \
-M g3beige \
-m 512 \
-bios PowerMacG3v3.ROM \
-display sdl \
-audiodev coreaudio,id=snd \
-global awacs.audiodev=snd \
-global ati-mach64-gt.romfile=ati_mach_gt.rom \
-device ati-rage128-pro,addr=0x0e,romfile=ati_nexus128_103_pci.rom \
-nic user,model=bmac,mac=00:05:02:12:34:56 \
-drive file=/Volumes/Macdata/qemu/hd/9.2-pristine-vm-off.img,format=raw,media=disk,index=0 \
-drive file=/Volumes/Macdata/qemu/iso/8.1.iso,format=raw,if=none,id=cd0 \
-device scsi-cd,drive=cd0,scsi-id=3
```

The "OS X Server 1.2v3" launcher differs only in: `-m 1024`,
`-display cocoa`, NO `ati-rage128-pro` line, and drives
`Server1.2v3.img ... media=disk,index=0` + `Server_1.2v3.iso ...
media=cdrom,index=2`. The "Linux" launcher: `-m 256`,
`-global ati-mach64-gt.romfile=ati_gt_fcode.rom`, one CD at `index=2`.

The generated command file for a machine configured like the user's must
be functionally identical to the above (same options, same values; order
and line breaks may differ). That is the primary correctness test.

### NVRAM and PRAM -- how "separate per machine" is achieved

The machine auto-manages two files **in the process's current working
directory**: `nvram.img` (8192 bytes, Open Firmware NVRAM,
`hw/ppc/mac_oldworld.c: mac_oldworld_default_nvram_blk()`) and `pram.img`
(256 bytes, CUDA PRAM, `hw/misc/macio/cuda.c: cuda_default_pram_blk()`).
Both are created empty on first run and sized up; the guest formats them.

**Design decision:** each machine gets its own folder and QEMU is started
with that folder as cwd. That alone gives separate NVRAM/PRAM per machine
with zero extra options, and it is exactly how the user's three deployed
installs already work (each has its own `nvram.img`/`pram.img` next to
its `.command`). Do NOT pass the files explicitly (`-drive if=mtd,...`,
`-global cuda.drive=...`) -- those paths exist but are unproven with
zero-byte files and gain nothing here.

Consequences the GUI must handle:
- The launcher file must `cd` to the machine folder first: `cd "$(dirname
  "$0")"` on macOS, `cd /d "%~dp0"` on Windows. When the GUI starts the
  machine itself it must pass `cwd=<machine folder>` to the subprocess.
- The QEMU binary and ROM files live elsewhere (the "QEMU folder"), so
  the launcher must reference them by absolute path, not `./`.
- A **"Reset NVRAM + PRAM"** action per machine = delete those two files
  from the machine folder (confirm first). This is a real, frequently
  needed operation: a polluted `nvram.img` makes the ROM hang mid-chime
  or boot to a flashing-floppy screen (`boot-device = fd:diags`). After a
  reset the first boot may show the flashing floppy until a CD boot
  re-initialises NVRAM; put that sentence in the confirmation dialog.

### Command-line facts (verified in the tree)

- Machine: `-M g3beige`. Optional machine property
  `-M g3beige,calibration-governor=<v>` where `<v>` is `on` (default,
  79 MIPS), `off`, or `mips=<n>` (1..100000). Expose as: Default / Off /
  Custom MIPS. Default emits nothing.
- RAM: `-m <MB>`. Real hardware maxes at 768 MB; the user runs 512 and
  1024. Offer 128/256/512/768/1024 plus free entry.
- ROM: `-bios <file>`. Default `PowerMacG3v3.ROM` from the QEMU folder.
- Display backend: `-display cocoa` or `-display sdl` on macOS, `-display
  sdl` or `-display gtk` on Windows. The user's daily macOS launcher uses
  `sdl`; the Server one uses `cocoa`. Default `sdl`, selectable.
- Audio: `-audiodev coreaudio,id=snd -global awacs.audiodev=snd` (macOS);
  `-audiodev dsound,id=snd -global awacs.audiodev=snd` (Windows, the user
  confirmed dsound is required there and "none" is the fallback that
  boots over Remote Desktop). Offer: platform default / sdl / none. With
  "none" emit `-audiodev none,id=snd -global awacs.audiodev=snd`.
- Onboard graphics = ATI Mach64 "GT" (Rage Pro), always present. Its
  FCode ROM is optional: `-global ati-mach64-gt.romfile=<file>`. The
  user has two such files (`ati_mach_gt.rom` = 65536 bytes, and
  `ati_gt_fcode.rom`, same size, used by the Linux install). Offer: none
  (machine ROM's built-in driver takes over, verified to boot 10.2 to a
  desktop) / file chooser. Default: `ati_mach_gt.rom` if it exists in the
  QEMU folder, else none.
- **Second graphics card** (user requirement): a PCI Rage 128 Pro in a
  slot: `-device ati-rage128-pro,addr=0x0e,romfile=<file>`. Slot
  `addr=0x0e` is the value the user runs; keep it as the default and let
  it be edited. Card ROM: the user has `ati_nexus128_103_pci.rom`
  (131072 bytes). Offer: None / ATI Rage 128 Pro (with ROM chooser and
  addr field). Other display devices exist in the binary (`ati-vga`,
  `VGA`, `cirrus-vga`) -- put them in the dropdown as "unsupported,
  experimental" entries below a separator, do not test them.
- Network: `-nic user,model=bmac,mac=00:05:02:12:34:56` (bmac is the
  onboard chip, `model=bmac` is mandatory for the guest to see it).
  Offer: User-mode NAT (default, MAC editable) / None (`-nic none`).
- **ATA (IDE) drives -- the index rules matter, they were the root cause
  of two "bugs" that were not bugs:**
  - Four slots: `index=0` bus0 master, `index=1` bus0 slave, `index=2`
    bus1 master, `index=3` bus1 slave. Show them with those names.
  - Hard disk: `-drive file=<img>,format=raw,media=disk,index=<n>`.
  - CD-ROM: `-drive file=<iso>,format=raw,media=cdrom,index=<n>`.
  - Always emit `index=` explicitly. Never let QEMU auto-assign.
  - The ROM boots the **lowest-index bootable disk** when NVRAM says
    "ROM decides", which is what OS X's Startup Disk writes. So the OS the
    user wants as default must be at index 0. Put this sentence in the UI
    as a hint next to the ATA table.
  - Convention that works: HD at index 0 (and 1), CD at index 2. If
    nothing claims index 2 QEMU adds a medialess phantom CD-ROM there
    itself, so leaving index 2 empty and putting a CD at index 3 is a
    trap; warn if a CD is configured but index 2 is empty.
  - `format=raw` always (all the user's images are raw). Allow `qcow2`
    only via the "Create disk image" dialog and then record the format
    per drive.
- **SCSI drives** (MESH controller, built in, no `-device` for the
  controller):
  - `-drive file=<img>,format=raw,if=none,id=<id> -device
    scsi-hd,drive=<id>,scsi-id=<n>` and the same with `scsi-cd`.
  - Optional identity strings, exactly as the user writes them:
    `vendor="QUANTUM",product="FIREBALL ST4.3S",ver="0F0C"` for disks,
    `vendor="MATSHITA",product="CD-ROM CR-8005",ver="1.0k"` for CDs.
    Offer these as prefilled defaults with a checkbox "send drive
    identity strings". On Windows the quoting differs: see Portability.
  - SCSI IDs 0..6 (7 is the controller). Offer a table with 7 rows, each
    Empty / Hard disk / CD-ROM + image + optional identity.
  - Boot order fact (verified 2026-09-02): the ROM prefers a SCSI CD over
    an ATA CD; holding C at boot picks the first CD; Startup Disk
    overrides. Put a one-line hint under the SCSI table.
  - Use ids `shd<n>` / `scd<n>` for `-drive id=` to avoid collisions.
- **Floppy** (user requirement): the SWIM3 controller is built in; attach
  an image with `-drive if=none,id=fd,file=<img>,format=raw -global
  swim3.drive=fd`. Read and write both work (user-verified 2026-07-31).
  Offer: None / image chooser (accept `.img`, `.dsk`, any file).
- Extra arguments: one free-text line appended verbatim (the user keeps
  things like `-qmp unix:/tmp/g92live.sock,server=on,wait=off` and
  `-global ati-mach64-gt.host-cursor-tracking=off` around).

Things NOT to expose (no value, or known dead ends): `-prom-env` (this is
a real ROM, not OpenBIOS; no `-L pc-bios`, no `-boot c/d`),
`adb-mouse.extended-protocol` (tested, wrong fix), `-g WxH` (ignored by
this ROM), `via=` machine option (g3beige is always CUDA), the R350 /
Radeon devices (shelved).

## Design

### Technology

Python 3.11+ with the standard library **only** (`tkinter`/`ttk`, `json`,
`subprocess`, `pathlib`, `shlex`). No third-party runtime dependencies: that
is what makes it portable and what lets the user run it from source on
Windows with a plain python.org install. Package for distribution with
PyInstaller (`pyinstaller --onedir --windowed --noconfirm qemu_gui.py`),
which the user already uses; put the `.spec` in the tree but do not run
PyInstaller in this job.

Trap on this Mac: `/opt/homebrew/bin/python3` (3.14) has NO `_tkinter`.
Use `/Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python` (3.13.5,
tkinter works) for running the GUI and the tests, or
`/usr/bin/python3`. Record which one you used in the README.

### Layout of the tree

```
Qemu-GUI/
  README.md                 how to run, where data lives, platform notes
  qemu_gui.py               entry point (tkinter app, thin)
  qemugui/
    __init__.py
    model.py                Machine dataclass, JSON load/save, defaults per OS profile
    command.py              build argv list + render .command/.bat text (pure, no Tk)
    profiles.py             OS profile defaults (below)
    paths.py                settings location, library folder, QEMU folder discovery
    ui_main.py              machine list + overview + Start
    ui_machine.py           machine editor (tabs: General, Graphics, ATA, SCSI, Floppy, Network/Audio, Advanced)
    ui_dialogs.py           create disk image (qemu-img), reset NVRAM/PRAM, confirmations
  tests/
    test_command.py         golden-output tests, both platforms, run on macOS
    fixtures/               machine.json files that reproduce the user's 3 launchers
  doc/
    HANDOFF-qemu-gui.md     this file
    REPORT-qemu-gui.md      your report (see "Report")
  QemuGUI.spec              PyInstaller spec (not run here)
```

`command.py` must be importable without Tk so the tests run headless.

### Data on disk

- Settings file (global, small): `~/Library/Application Support/Qemu-GUI/
  settings.json` on macOS, `%APPDATA%\Qemu-GUI\settings.json` on Windows.
  Holds: `library_dir`, `qemu_dir` (folder holding `qemu-system-ppc[.exe]`,
  `qemu-img[.exe]`, the ROMs), last-selected machine.
- Library folder (default `~/Qemu-GUI-Machines`, user-changeable):
  ```
  <library>/<machine-name>/
      machine.json      the record
      nvram.img         created by QEMU on first run
      pram.img          created by QEMU on first run
      run.command       (macOS) generated launcher, chmod +x
      run.bat           (Windows) generated launcher
      *.img             disk images created by the GUI's "Create disk" default here
  ```
  Machine name = folder name; restrict to `[A-Za-z0-9._ -]`.
- `machine.json` schema (version it: `"schema": 1`):
  ```json
  {
    "schema": 1,
    "name": "Mac OS 9.2",
    "profile": "macos9",            // macos8_9 | macosx | macosx_server | linux | custom
    "machine": "g3beige",
    "ram_mb": 512,
    "rom": "PowerMacG3v3.ROM",      // relative to qemu_dir unless absolute
    "qemu_dir": null,               // per-machine override of the global setting
    "display": "sdl",               // cocoa | sdl | gtk
    "audio": "default",             // default | sdl | none
    "onboard_romfile": "ati_mach_gt.rom",   // or null
    "second_gpu": {"device": "ati-rage128-pro", "addr": "0x0e", "romfile": "ati_nexus128_103_pci.rom"},  // or null
    "network": {"mode": "user", "mac": "00:05:02:12:34:56"},          // mode: user | none
    "governor": {"mode": "default"},                                   // default | off | mips (+ "mips": 100)
    "ata": [  // exactly 4 entries, index 0..3, null = empty
      {"kind": "disk", "file": "/Volumes/Macdata/qemu/hd/9.2-G3.img", "format": "raw"},
      null,
      {"kind": "cdrom", "file": "/Volumes/Macdata/qemu/iso/8.1.iso", "format": "raw"},
      null
    ],
    "scsi": [ // up to 7 entries keyed by id
      {"id": 0, "kind": "disk", "file": "...", "format": "raw", "identity": {"vendor": "QUANTUM", "product": "FIREBALL ST4.3S", "ver": "0F0C"}},
      {"id": 3, "kind": "cdrom", "file": "...", "format": "raw", "identity": null}
    ],
    "floppy": null,                 // or {"file": "...", "format": "raw"}
    "extra_args": "",
    "notes": ""
  }
  ```
  Paths are stored as the user picked them (absolute). Relative paths
  are resolved against the machine folder when the launcher is written.

### OS profiles (defaults applied when a machine is created, editable after)

| profile | RAM | display | second GPU | onboard romfile | ATA default | notes shown |
|---|---|---|---|---|---|---|
| Mac OS 8 / 9 | 512 | sdl | Rage 128 Pro | ati_mach_gt.rom | HD idx0, CD idx2 | "OS 8.1 needs the SCSI CD or ATA CD at index 2" |
| Mac OS X 10.x | 512 | sdl | Rage 128 Pro | ati_mach_gt.rom | HD idx0, CD idx2 | "Startup Disk in OS X delegates to the ROM: the bootable disk at index 0 wins" |
| Mac OS X Server 1.x | 1024 | cocoa | none | ati_mach_gt.rom | HD idx0, CD idx2 | user's working config has no second card |
| Linux | 256 | sdl | none | ati_gt_fcode.rom | CD idx2 | |
| Custom | 512 | sdl | none | none | empty | |

Profiles only seed the record. Nothing in `command.py` may branch on the
profile.

### Main window

Left: list of machines (name + profile). Buttons: New, Duplicate, Delete
(deletes the machine folder only after a confirmation that lists what
will be removed; NEVER deletes an image outside the machine folder),
Edit, Reset NVRAM/PRAM, Reveal folder, **Start**.

Right: Overview = a read-only text box showing the generated launcher
exactly as it will be written (regenerated whenever the record changes or
the selection changes), a status line (`nvram.img: present, 8192 bytes /
absent`, same for pram, QEMU binary found / missing), and the machine's
notes.

Start = write the launcher file, then `subprocess.Popen(argv, cwd=machine
folder)` with the argv list (not the shell file), stdout/stderr to
`<machine>/last-run.log`. Show the pid; poll every second and show "exited
with code N" plus the last 20 log lines when it ends. One running instance
per machine; refuse a second Start while it runs. Never kill the guest
from the GUI (no Stop button in v1) -- the user shuts down from inside the
guest.

### Machine editor

Tabs: General (name, profile, RAM, ROM, display, QEMU folder override,
notes), Graphics (onboard romfile, second card), ATA (4 fixed rows),
SCSI (7 rows), Floppy, Network & Audio, Advanced (governor, extra args).
Every file field has a Browse button that opens in the folder of the
current value, else in `/Volumes/Macdata/qemu/{hd,iso,fd,rom}` if it
exists, else home. Save validates: name legal, files exist (warning, not
error -- images may live on an unmounted volume), no two ATA rows share
an index, no two SCSI rows share an id, CD-with-index-2-empty warning,
RAM in range. Validation messages appear in the dialog; Save is allowed
with warnings, blocked on errors.

### Portability rules (`command.py`)

- Build ONE list of argv tokens. Render it two ways:
  - macOS/Linux: `#!/bin/bash`, `cd "$(dirname "$0")"`, one option per
    line with ` \` continuations, tokens quoted with `shlex.quote`.
  - Windows: `@echo off`, `cd /d "%~dp0"`, one option per line with ` ^`
    continuations. Quote any token containing spaces or `,` with double
    quotes. Identity strings with spaces inside a `-device` token
    (`product="FIREBALL ST4.3S"`) must come out as
    `-device "scsi-hd,drive=shd0,scsi-id=0,vendor=QUANTUM,product=FIREBALL ST4.3S,ver=0F0C"`
    on Windows (whole token quoted) and as
    `-device scsi-hd,drive=shd0,scsi-id=0,vendor=QUANTUM,product='FIREBALL ST4.3S',ver=0F0C`
    or the shlex equivalent on macOS. QEMU parses `vendor=X,product=Y`;
    the shell quoting is only there to keep the token whole.
- The binary is `qemu-system-ppc` on macOS/Linux, `qemu-system-ppc.exe`
  on Windows; `qemu-img` likewise.
- The GUI generates the launcher for the platform it is running on, and
  the tests generate both by passing an explicit `platform=` argument.
- Path separators: use `pathlib`; on Windows emit backslashes.
- The launcher is regenerated from `machine.json` every time. Hand edits
  to the launcher are lost; say so in a comment at the top of the file.

### Create disk image dialog

`qemu-img create -f raw <machine>/<name>.img <N>G` (raw default, qcow2
selectable). After creation offer to place it in the first empty ATA slot
or a chosen SCSI id. Sizes: 1/2/4/8/10/20 GB + free entry. Mac OS 8/9
partitions above 2 GB with Drive Setup fine; no warning needed.

## Rules (binding)

1. **Never boot any image under `/Volumes/Macdata/qemu/hd/`.** A repeated
   quit/relaunch loop on the real disk image corrupted it once. For your
   smoke test use a fresh image created by `qemu-img` inside a scratch
   machine folder, plus `/Volumes/Macdata/qemu/iso/8.1.iso` as an ATA CD
   at index 2 (an ISO opened as `media=cdrom` is read-only; that is safe).
2. **Never write into `/Applications/qemu-system-ppc-g3-*`** and never
   copy a build there. Point your scratch machine's `qemu_dir` at
   `/Users/hsp/src/claude-code/qemu-master-g3/build-g3` and copy the three
   ROM files (`PowerMacG3v3.ROM`, `ati_mach_gt.rom`,
   `ati_nexus128_103_pci.rom`) from `/Applications/qemu-system-ppc-g3-mac-os/`
   into your scratch machine folder or reference them by absolute path.
3. Never run more than one guest at a time, and never let a smoke boot run
   longer than 60 s: add `-qmp unix:<scratch>/qmp.sock,server=on,wait=off`
   via `extra_args` for the smoke run only and quit through QMP
   (`{"execute":"qmp_capabilities"}` then `{"execute":"quit"}`). If QMP
   is unreachable, `kill <pid>` that exact pid (never `pkill` by pattern,
   the user may have their own QEMU running). Delete any trace/log file
   larger than 50 MB when you are done.
4. Do not modify anything under `qemu-master-g3`. If the GUI needs a
   machine feature that does not exist, write it up in the report; do not
   build it.
5. Commit in `Qemu-GUI` as you go with descriptive messages; there is no
   remote and you must not add one. End commit messages with the
   attribution trailer your environment specifies.
6. No third-party Python packages at runtime. Tests use `unittest`
   (stdlib), run with `python -m unittest discover -s tests`.
7. Don't over-build: no themes, no localisation, no plugin systems, no
   mac99 support (leave `machine` in the schema so it can come later).

## Verification you must perform (and report)

1. `python -m unittest discover -s tests` passes. Tests must include:
   - a fixture reproducing the user's "Mac OS" launcher above; the
     rendered argv, compared as a set of tokens after stripping the binary
     path, equals the user's token set (allow the SCSI `id=` names to
     differ: normalise `cd0` -> `scd3`).
   - the "OS X Server 1.2v3" and "Linux" launchers likewise.
   - Windows rendering of the SCSI fixture with identity strings: the
     `.bat` text contains `cd /d "%~dp0"`, ` ^` continuations, and the
     quoted `-device` token; no `\` continuations; `qemu-system-ppc.exe`.
   - floppy: `-global swim3.drive=fd` and the paired `-drive if=none,id=fd`.
   - second GPU none -> no `ati-rage128-pro` token; governor mips=100 ->
     `-M g3beige,calibration-governor=mips=100`.
   - JSON round trip: save -> load -> identical dataclass.
2. Smoke run (one boot, scratch only, per Rules 1-3): create a scratch
   library at `/Users/hsp/.claude/jobs/886cc763/tmp/gui-smoke/`, a
   machine "smoke" with a 1 GB raw disk at index 0 and `8.1.iso` at
   index 2, `qemu_dir` = build-g3, display `cocoa` (sdl is fine too),
   audio none, network none. Start it THROUGH THE GUI CODE PATH
   (`ui_main.start_machine` or whatever you name it, driven from a small
   script, not by hand-typing the command). Acceptance: the process is
   alive after 20 s, `last-run.log` contains no `invalid option`, `could
   not open`, `Property .* not found` or `not a valid` line, and
   `nvram.img` (8192 bytes) and `pram.img` (256 bytes) exist in the
   machine folder afterwards. Then quit via QMP. Keep the log in
   `doc/smoke-last-run.log` (trim to 200 lines).
3. Open the GUI once for real (`python qemu_gui.py`) pointed at the
   scratch library, take a screenshot of the main window and of the ATA
   tab with `screencapture -x <file>` after a 3 s delay (macOS has a
   display; the job runs as the user), save them under `doc/`, close it.
   If screencapture is blocked, say so; do not spend more than 10 minutes
   on it.
4. Byte-for-byte diff of the generated `run.command` for the "Mac OS"
   fixture against `/Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc-G3.command`
   (first 13 non-comment lines), included in the report with an
   explanation of every difference.

## Report

Write `doc/REPORT-qemu-gui.md` with: what was built (file list with one
line each), how to run it on macOS and on Windows, the test output
(verbatim), the smoke-run evidence (pid, uptime, log excerpt, file
sizes), the diff from step 4, every deviation from this contract with the
reason, and open questions for the user. Assume the reader has not seen
this file. The main session verifies the report by re-running the tests
and re-generating the fixtures; make that easy (one command each).

## Acceptance (the user's sentences, made checkable)

- [ ] runs from source on macOS with stdlib Python; the same source is
      documented to run on Windows with python.org Python (no pip installs)
- [ ] a machine is a folder with its own `machine.json`, `nvram.img`,
      `pram.img`, launcher; creating "Mac OS 9", "Mac OS X", "OS X Server"
      machines yields three independent folders
- [ ] the launcher (`run.command` / `run.bat`) is generated, shown in the
      overview, and regenerated on every change
- [ ] Start launches the machine with the machine folder as cwd
- [ ] ATA: 4 index-named slots, each empty / hard disk / CD-ROM
- [ ] SCSI: 7 id-named slots, each empty / hard disk / CD-ROM, optional
      identity strings
- [ ] floppy image selectable
- [ ] second graphics card selectable (None / ATI Rage 128 Pro with ROM
      and slot)
- [ ] source lives only in `/Users/hsp/src/claude-code/Qemu-GUI`, committed
