# REPORT: Qemu-GUI -- portable launcher GUI for the Beige G3 machine

Written 2026-09-03 by the build agent against `doc/HANDOFF-qemu-gui.md`.
Repo: `/Users/hsp/src/claude-code/Qemu-GUI`, branch `main`, no remote.
Python used for everything below: `/Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python`
(3.13.5, Tk 8.6). `/usr/bin/python3` (3.9.6, Tk 8.5) also has tkinter.

## 1. What was built

| file | one line |
|---|---|
| `qemu_gui.py` | entry point; `--settings FILE`, `--library DIR`, `--qemu-dir DIR`; opens `MainWindow` |
| `qemugui/__init__.py` | package marker, version |
| `qemugui/paths.py` | settings file location (macOS `~/Library/Application Support/Qemu-GUI/settings.json`, Windows `%APPDATA%\Qemu-GUI\settings.json`, env override `QEMU_GUI_SETTINGS`), default library `~/Qemu-GUI-Machines`, QEMU folder discovery, browse-start folders, `Settings` dataclass |
| `qemugui/profiles.py` | OS profile seeds (Mac OS 8/9, Mac OS X 10.x, Mac OS X Server 1.x, Linux, Custom) and the prefilled SCSI identity strings |
| `qemugui/model.py` | `Machine` and sub-dataclasses, `machine.json` schema 1 load/save, `validate()` (errors block Save, warnings do not), `Library` (folder = machine: list, save/rename, duplicate, delete folder only, nvram/pram status + reset) |
| `qemugui/command.py` | pure argv builder `build_argv()`; `render_shell()` (`#!/bin/bash`, `cd "$(dirname "$0")"`, ` \` continuations, `shlex.quote`) and `render_bat()` (`@echo off`, `cd /d "%~dp0"`, ` ^` continuations, CRLF, double quotes on tokens with space/comma, `%`->`%%`); `write_launcher()` |
| `qemugui/ui_main.py` | main window: machine list, overview text = the launcher exactly as written, status line (nvram/pram/QEMU binary), notes, last-run log tail; buttons New/Duplicate/Delete/Edit/Reset NVRAM-PRAM/Reveal/Start; `start_machine()` = write launcher + `Popen(argv, cwd=machine folder)` with output to `last-run.log`; 1 s poll shows pid/uptime and "exited with code N" + last 20 log lines; one instance per machine; no Stop button |
| `qemugui/ui_machine.py` | editor tabs General / Graphics / ATA (4 index-named rows) / SCSI (7 id-named rows with identity checkbox + vendor/product/ver) / Floppy / Network & Audio / Advanced (governor, extra args); Browse buttons open in the current value's folder, else `/Volumes/Macdata/qemu/{hd,iso,fd,rom}`, else home |
| `qemugui/ui_dialogs.py` | New-machine (name + profile), duplicate name, delete confirmation listing the folder contents, Reset NVRAM+PRAM confirmation (with the flashing-floppy sentence), Create disk image (`qemu-img create -f raw|qcow2`, sizes 1/2/4/8/10/20 GB + free entry, then attach to first empty ATA slot or a free SCSI id), Reveal folder |
| `tests/test_command.py` | 28 unittest cases (section 3) |
| `tests/fixtures/mac-os.json`, `server12v3.json`, `linux.json` | the user's three deployed launchers as records |
| `tests/fixtures/scsi-windows.json` | the user's SCSI-with-identity launcher on Windows paths |
| `tools/smoke_boot.py` | scratch-only smoke boot through `MainWindow.start_selected()`, QMP quit after 20 s |
| `tools/screenshots.py` | opens the real GUI and captures the main window and the ATA tab |
| `tools/render_fixture.py` | prints the launcher for any `machine.json` for `darwin`/`win32`/`linux` |
| `QemuGUI.spec` | PyInstaller spec (not run) |
| `README.md` | how to run, where data lives, platform notes |
| `doc/smoke-last-run.log`, `doc/screenshot-main.png`, `doc/screenshot-ata-tab.png` | evidence |

No third-party runtime dependency; nothing was pip-installed.

## 2. How to run

macOS (Homebrew python3 has no tkinter; use a python.org build or the venv):

    cd /Users/hsp/src/claude-code/Qemu-GUI
    /Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python qemu_gui.py
    # or: /usr/bin/python3 qemu_gui.py

Windows (python.org Python 3.11+ with "tcl/tk" ticked):

    py qemu_gui.py

First run: File > Settings, set the QEMU folder (the folder with
`qemu-system-ppc[.exe]`, `qemu-img[.exe]` and the ROMs). On this Mac
`/Applications/qemu-system-ppc-g3-mac-os` is auto-discovered. New creates a
machine folder under the library; Edit fills in drives; Start writes
`run.command`/`run.bat` and launches with the machine folder as cwd, so
`nvram.img`/`pram.img` land in that folder and are separate per machine.

Re-verification, one command each:

    /Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python -m unittest discover -s tests -v
    /Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python tools/render_fixture.py tests/fixtures/mac-os.json
    /Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python tools/render_fixture.py tests/fixtures/scsi-windows.json win32 'C:\Machines\SCSI'

## 3. Test output (verbatim)

`/Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python -m unittest discover -s tests -v`

```
test_fixtures_round_trip (test_command.JsonRoundTrip.test_fixtures_round_trip) ... ok
test_full_record_round_trip (test_command.JsonRoundTrip.test_full_record_round_trip) ... ok
test_legacy_profile_alias (test_command.JsonRoundTrip.test_legacy_profile_alias) ... ok
test_create_save_duplicate_delete (test_command.LibraryOps.test_create_save_duplicate_delete) ... ok
test_write_launcher_is_executable_and_regenerated (test_command.LibraryOps.test_write_launcher_is_executable_and_regenerated) ... ok
test_ata_index_explicit_for_every_slot (test_command.Options.test_ata_index_explicit_for_every_slot) ... ok
test_audio_and_network_none (test_command.Options.test_audio_and_network_none) ... ok
test_comma_in_path_is_escaped_for_qemu (test_command.Options.test_comma_in_path_is_escaped_for_qemu) ... ok
test_extra_args_appended_verbatim (test_command.Options.test_extra_args_appended_verbatim) ... ok
test_floppy (test_command.Options.test_floppy) ... ok
test_global_qemu_dir_used_when_no_override (test_command.Options.test_global_qemu_dir_used_when_no_override) ... ok
test_governor (test_command.Options.test_governor) ... ok
test_onboard_rom_none (test_command.Options.test_onboard_rom_none) ... ok
test_relative_image_resolves_against_machine_folder (test_command.Options.test_relative_image_resolves_against_machine_folder) ... ok
test_second_gpu_none (test_command.Options.test_second_gpu_none) ... ok
test_binary_is_absolute_and_first (test_command.UserLaunchers.test_binary_is_absolute_and_first) ... ok
test_linux (test_command.UserLaunchers.test_linux) ... ok
test_mac_os (test_command.UserLaunchers.test_mac_os) ... ok
test_server12v3 (test_command.UserLaunchers.test_server12v3) ... ok
test_shell_rendering_shape (test_command.UserLaunchers.test_shell_rendering_shape) ... ok
test_bad_name_and_ram (test_command.Validation.test_bad_name_and_ram) ... ok
test_cd_elsewhere_with_index2_empty_warns (test_command.Validation.test_cd_elsewhere_with_index2_empty_warns) ... ok
test_duplicate_scsi_id_is_error (test_command.Validation.test_duplicate_scsi_id_is_error) ... ok
test_missing_image_is_warning_not_error (test_command.Validation.test_missing_image_is_warning_not_error) ... ok
test_seeded_slot_without_image_is_warning_and_skipped (test_command.Validation.test_seeded_slot_without_image_is_warning_and_skipped) ... ok
test_bat_scsi_identity (test_command.WindowsRendering.test_bat_scsi_identity) ... ok
test_extra_args_windows_backslashes_kept (test_command.WindowsRendering.test_extra_args_windows_backslashes_kept) ... ok
test_posix_scsi_identity_token_is_whole (test_command.WindowsRendering.test_posix_scsi_identity_token_is_whole) ... ok

----------------------------------------------------------------------
Ran 28 tests in 0.007s

OK
```

Coverage of the contract's required tests: `test_mac_os` / `test_server12v3`
/ `test_linux` compare the generated argv as a token set against the
launcher text quoted in the handoff (binary stripped, `cd0` -> `scd3`, and
the user's relative ROM names resolved against the install folder, see
deviation D5); `test_bat_scsi_identity` checks `cd /d "%~dp0"`, ` ^`
continuations, no ` \`, `qemu-system-ppc.exe` and the quoted `-device`
token; `test_floppy`; `test_second_gpu_none` + `test_governor`;
`test_fixtures_round_trip` + `test_full_record_round_trip` (save -> load ->
equal dataclass).

## 4. Smoke run evidence

Command: `tools/smoke_boot.py /Users/hsp/.claude/jobs/886cc763/tmp/gui-smoke /Users/hsp/src/claude-code/qemu-master-g3/build-g3 /Volumes/Macdata/qemu/iso/8.1.iso`

The script builds the scratch machine record, instantiates the real
`MainWindow`, selects "smoke" and calls `MainWindow.start_selected()` (the
Start button's method), pumps the Tk event loop for 20 s, then quits through
QMP. Nothing under `/Volumes/Macdata/qemu/hd/` was touched; the CD is the
read-only 8.1 ISO at ATA index 2; the disk is a fresh `qemu-img` 1 GB raw
file in the scratch folder.

```
validate: [] []
started pid 25600 at 07:28:02
argv: /Users/hsp/src/claude-code/qemu-master-g3/build-g3/qemu-system-ppc -M g3beige -m 512
  -bios .../gui-smoke/smoke/PowerMacG3v3.ROM -display cocoa -audiodev none,id=snd
  -global awacs.audiodev=snd -global ati-mach64-gt.romfile=.../gui-smoke/smoke/ati_mach_gt.rom
  -device ati-rage128-pro,addr=0x0e,romfile=.../gui-smoke/smoke/ati_nexus128_103_pci.rom
  -nic none -drive file=.../gui-smoke/smoke/smoke.img,format=raw,media=disk,index=0
  -drive file=/Volumes/Macdata/qemu/iso/8.1.iso,format=raw,media=cdrom,index=2
  -qmp unix:.../gui-smoke/qmp.sock,server=on,wait=off
alive after 20 s: True (uptime 20.1 s); GUI run status: 'running, pid 25600, up 19 s'
bad log lines: []
managed files: {'nvram.img': 8192, 'pram.img': 256}
QMP quit sent; greeting: b'{"QMP": {"version": {"qemu": {"micro": 50, "minor": 1, "major": 11}, "package": '
exit code: 0; GUI run status: 'exited with code 0 (pid 25600, ran 20 s)'
SMOKE PASS
```

`last-run.log` (kept as `doc/smoke-last-run.log`) contains only the argv
comment line the GUI writes; QEMU printed nothing to stdout/stderr in 20 s.
Grep for `invalid option`, `could not open`, `Property .* not found`, `not a
valid`: no hits. Scratch machine folder after the run:

```
PowerMacG3v3.ROM           4194304
ati_mach_gt.rom              65536
ati_nexus128_103_pci.rom    131072
last-run.log                   723
machine.json                  1075
nvram.img                     8192   <- created by QEMU (cwd = machine folder)
pram.img                       256   <- created by QEMU
run.command                    910   (chmod +x)
smoke.img               1073741824
```

No trace/log file over 50 MB was produced; nothing to delete. The 1 GB
`smoke.img` stays in the job's tmp folder.

## 5. Screenshots

`tools/screenshots.py` opened the GUI (real `MainWindow` + `mainloop`) on
the scratch library holding "Mac OS 9", "Mac OS X", "OS X Server" (created
through `model.new_machine` from the three profiles) and captured with
`screencapture -x -R <window geometry>` after 3 s:

- `doc/screenshot-main.png`: main window, overview of "Mac OS 9", status
  line, notes, log tail.
- `doc/screenshot-ata-tab.png`: editor, ATA tab with the four index-named
  rows, the boot-order hint and the Create disk image button.

`screencapture` was not blocked.

## 6. `run.command` diff for the "Mac OS" fixture

Generated: `tools/render_fixture.py tests/fixtures/mac-os.json` (written to
a scratch machine folder with `command.write_launcher`). Compared: first 13
non-comment lines of each.

```
--- /Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc-G3.command
+++ <machine>/run.command
@@ -1,13 +1,13 @@
 cd "$(dirname "$0")"
 
-./qemu-system-ppc \
+/Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc \
 -M g3beige \
 -m 512 \
--bios PowerMacG3v3.ROM \
+-bios /Applications/qemu-system-ppc-g3-mac-os/PowerMacG3v3.ROM \
 -display sdl \
 -audiodev coreaudio,id=snd \
 -global awacs.audiodev=snd \
--global ati-mach64-gt.romfile=ati_mach_gt.rom \
--device ati-rage128-pro,addr=0x0e,romfile=ati_nexus128_103_pci.rom \
+-global ati-mach64-gt.romfile=/Applications/qemu-system-ppc-g3-mac-os/ati_mach_gt.rom \
+-device ati-rage128-pro,addr=0x0e,romfile=/Applications/qemu-system-ppc-g3-mac-os/ati_nexus128_103_pci.rom \
 -nic user,model=bmac,mac=00:05:02:12:34:56 \
--drive file=/Volumes/Macdata/qemu/hd/9.2-pristine-vm-off.img,format=raw,media=disk,index=0
+-drive file=/Volumes/Macdata/qemu/hd/9.2-pristine-vm-off.img,format=raw,media=disk,index=0 \
```

Every difference explained:

1. `./qemu-system-ppc` -> absolute binary path. Required by the design: the
   launcher `cd`s into the *machine* folder (for nvram/pram), not the QEMU
   folder, so the binary must be referenced absolutely.
2. `-bios`, `ati-mach64-gt.romfile=`, `romfile=`: the same reason; the
   user's relative names only work because their launcher runs inside the
   QEMU folder. Values are identical files.
3. The trailing ` \` on the `index=0` drive line: in the user's file that
   line is followed by two blank lines, which ends the bash command there.
   The SCSI CD lines below it (`-drive ...id=cd0` / `-device scsi-cd`) are
   therefore **not** part of the command the deployed file actually runs
   (bash would try to execute `-drive` as a separate command after QEMU
   exits). The generated file continues with those two lines, as the
   handoff's "real launcher today" listing shows. See open question 1.
4. Line 2 of the generated file is a comment ("Hand edits are lost", as the
   contract requires); it is filtered out by the `grep -v '^#'` used for
   this comparison, hence 13 lines on both sides.

The full generated file (`tools/render_fixture.py tests/fixtures/mac-os.json`)
is 17 lines and ends with `-drive file=/Volumes/Macdata/qemu/iso/8.1.iso,format=raw,if=none,id=scd3 \`
/ `-device scsi-cd,drive=scd3,scsi-id=3`.

## 7. Deviations from the contract (with reasons)

- **D1 profile id.** The contract's JSON example says `"profile": "macos9"`
  while its own enumeration says `macos8_9`. The ids are `macos8_9`,
  `macosx`, `macosx_server`, `linux`, `custom`; `macos9` (and `macos8`,
  `osx`, `server`) are accepted as aliases on load.
- **D2 empty slot with a type.** A drive row whose type is set but whose
  image field is empty is a *warning* and is skipped in the argv, not an
  error. Reason: profiles seed slot types (HD at 0, CD at 2) without files;
  as an error this blocked saving anything on a freshly created machine
  until images were picked. Test `test_seeded_slot_without_image_is_warning_and_skipped`.
- **D3 CD-at-index-2 warning scope.** The warning fires only when an *ATA*
  CD sits at an index other than 2 while index 2 is empty. The contract's
  literal "a CD is configured but index 2 is empty" would fire on the user's
  own "Mac OS" configuration (SCSI CD, index 2 empty) on every save.
- **D4 screenshots.** Taken by `tools/screenshots.py`, which runs the real
  `MainWindow` + `mainloop` and opens the editor on the ATA tab, rather than
  by launching `python qemu_gui.py` and clicking; region capture needs the
  window geometry, which only the process itself knows. Same code paths.
- **D5 token-set test normalisation.** Besides `cd0 -> scd3` the test
  resolves the user's *relative* ROM names against the install folder
  before comparing (the contract mandates absolute paths in our output, so
  a raw set comparison could never be equal).
- **D6 `.bat` quoting is applied to every comma token**, exactly per the
  contract's rule, so `-audiodev "dsound,id=snd"` and `-nic "user,..."` are
  quoted too. cmd/CreateProcess strip the quotes; QEMU sees the bare token.
  Untested on a real Windows host (none available here).
- **D7 smoke machine also carries the Rage 128 Pro second card** (contract
  listed disk/CD/display/audio/network only). It boots with it; broader
  coverage, no downside.
- **D8 extra files/flags not in the contract's layout:** `tools/` (three
  helper scripts), `qemu_gui.py --settings/--library/--qemu-dir`, env
  `QEMU_GUI_SETTINGS`. Needed to keep the smoke run and screenshots away
  from the user's real settings file.
- **D9 Duplicate** copies `machine.json`, `nvram.img` and `pram.img`; disk
  images are shared (paths copied), stated in the dialog. The contract did
  not specify.
- **D10 Linux host** (neither darwin nor win32) gets `-audiodev sdl` as the
  platform default and `sdl`/`gtk` displays. Outside the contract's scope.
- **D11 validate() name rule** additionally rejects leading/trailing spaces
  (folder names ending in a space are trouble on both platforms).
- No machine feature was missing from the g3beige tree; nothing had to be
  written up as "needs a QEMU change". `qemu-master-g3` was not modified.

## 8. Open questions for the user

1. The deployed `/Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc-G3.command`
   has blank lines after the `index=0` drive line, so its SCSI CD is
   currently *not* attached when that file is double-clicked; likewise the
   Linux launcher's `-qmp` line after blank lines is dead. The fixtures
   follow the handoff's listing (SCSI CD included, no `-qmp`). Is that the
   intended configuration for the "Mac OS" machine, or should its CD be an
   ATA CD at index 2?
2. Should the Rage 128 Pro be seeded for the Mac OS X profile on Windows
   too (dsound + Rage 128 untested there)?
3. v1 has no Stop button by design. Wanted later, or keep "shut down from
   inside the guest" as the rule?
4. Duplicate shares images rather than copying multi-GB files. OK?
5. The "Re-apply profile defaults" button in the editor resets RAM,
   display, second card, onboard ROM and fills empty ATA slot types; it
   never touches chosen image paths. Right granularity?

## 9. Git log

```
d68427f GUI: main window, machine editor, dialogs, entry point; smoke/screenshot tools; README
0d33c56 Core: machine model, JSON schema v1, argv builder, .command/.bat renderers, tests
166e2c1 doc: hand-off contract for the Qemu-GUI launcher (G3, macOS + Windows)
```

plus the commit adding `tools/render_fixture.py` and this report.

## Addendum 1 (2026-09-03): SCSI id 7 row and networking modes

Implemented per the contract's Addendum 1 (commit `6145f59`).

What changed:

- `qemugui/model.py`: `Network` gains `ifname`; modes `none | user |
  vmnet-bridged | vmnet-shared | vmnet-host | tap`; `network_modes_for_host()`
  (host-filtered list plus the record's own mode); `default_ifname()`
  (`en0` for vmnet-bridged on macOS, empty otherwise); validation: unknown
  mode = error, empty ifname for vmnet-bridged/tap = error, mode-vs-host
  mismatch = warning ("Network mode tap is for Windows; it will not work
  here"), SCSI id 7 in a record = error "SCSI id 7 is the computer (the
  MESH controller itself)". `ifname` is written to `machine.json` for the
  two modes that need it (and whenever non-empty); user/none records are
  unchanged.
- `qemugui/command.py`: `nic_option()` emits exactly the addendum's table;
  `needs_sudo()`; `render_shell(argv, sudo)` prefixes `sudo ` to the binary
  line and appends the chown tail for `vmnet-*`; the `.bat` never gets
  either. `build_argv()` (what `Popen` would get) never contains sudo.
- `qemugui/ui_machine.py`: SCSI tab has 8 rows, row `scsi-id 7 -- the
  Macintosh itself (MESH controller)` fixed and non-editable, never saved.
  Network tab: mode combobox (host-filtered + current), MAC, ifname (enabled
  only for vmnet-bridged/tap, prefilled `en0`), per-mode hint text and the
  root-owned-files note for vmnet.
- `qemugui/ui_main.py`: `start_in_terminal()`; `start_selected()` for a
  vmnet machine writes the launcher and runs `open -a Terminal
  <machine>/run.command`; status line "started in Terminal (sudo required
  for vmnet) at HH:MM:SS"; no pid tracking. On a non-macOS host it refuses.
- Fixtures: `tests/fixtures/mac-os-vmnet-bridged.json` (the Mac OS fixture
  with vmnet-bridged/en0) and `tests/fixtures/tap-windows.json` (Windows
  record with `tap` + `TAP-Windows Adapter V9`).
- Tests added (13): one token check per mode (none, user, vmnet-bridged,
  vmnet-shared, vmnet-host, tap), sudo prefix + chown tail in the vmnet
  `.command`, no sudo in the user-mode `.command`, no sudo/chown in the
  `.bat` for both vmnet and tap records, the id-7 validation error (built
  and loaded), the cross-platform load/save round trip (tap record on
  macOS and vmnet record on Windows: identical dataclass, identical JSON
  network block, correct warning), host mode lists, ifname-required error.
- README: "Networking (Addendum 1)" section with the exact emitted lines,
  the sudo/Terminal behaviour, the chown line verbatim, the TAP adapter
  requirement, and the id-7 note.

No smoke boot (per the addendum). Existing fixture renders re-run:
`tools/render_fixture.py tests/fixtures/mac-os.json` is byte-identical to
the pre-addendum output; `server12v3`, `linux`, `scsi-windows` unchanged.
Headless Tk exercise: editor round-trips a vmnet record and a tap record
unchanged, the tap record saves unchanged on macOS, Start on the vmnet
machine issued `open -a Terminal .../run.command` and set the Terminal
status line.

### Test output (verbatim)

`/Users/hsp/PycharmProjects/QemuGUI-PPC/.venv/bin/python -m unittest discover -s tests -v`

```
test_fixtures_round_trip (test_command.JsonRoundTrip.test_fixtures_round_trip) ... ok
test_full_record_round_trip (test_command.JsonRoundTrip.test_full_record_round_trip) ... ok
test_legacy_profile_alias (test_command.JsonRoundTrip.test_legacy_profile_alias) ... ok
test_create_save_duplicate_delete (test_command.LibraryOps.test_create_save_duplicate_delete) ... ok
test_write_launcher_is_executable_and_regenerated (test_command.LibraryOps.test_write_launcher_is_executable_and_regenerated) ... ok
test_bat_never_has_sudo_or_chown (test_command.Networking.test_bat_never_has_sudo_or_chown) ... ok
test_cross_platform_load_save_round_trip (test_command.Networking.test_cross_platform_load_save_round_trip) ... ok
test_ifname_required (test_command.Networking.test_ifname_required) ... ok
test_modes_offered_per_host (test_command.Networking.test_modes_offered_per_host) ... ok
test_none (test_command.Networking.test_none) ... ok
test_tap (test_command.Networking.test_tap) ... ok
test_user (test_command.Networking.test_user) ... ok
test_user_mode_command_has_no_sudo (test_command.Networking.test_user_mode_command_has_no_sudo) ... ok
test_vmnet_bridged (test_command.Networking.test_vmnet_bridged) ... ok
test_vmnet_command_has_sudo_prefix_and_chown_tail (test_command.Networking.test_vmnet_command_has_sudo_prefix_and_chown_tail) ... ok
test_vmnet_host (test_command.Networking.test_vmnet_host) ... ok
test_vmnet_shared (test_command.Networking.test_vmnet_shared) ... ok
test_ata_index_explicit_for_every_slot (test_command.Options.test_ata_index_explicit_for_every_slot) ... ok
test_audio_and_network_none (test_command.Options.test_audio_and_network_none) ... ok
test_comma_in_path_is_escaped_for_qemu (test_command.Options.test_comma_in_path_is_escaped_for_qemu) ... ok
test_extra_args_appended_verbatim (test_command.Options.test_extra_args_appended_verbatim) ... ok
test_floppy (test_command.Options.test_floppy) ... ok
test_global_qemu_dir_used_when_no_override (test_command.Options.test_global_qemu_dir_used_when_no_override) ... ok
test_governor (test_command.Options.test_governor) ... ok
test_onboard_rom_none (test_command.Options.test_onboard_rom_none) ... ok
test_relative_image_resolves_against_machine_folder (test_command.Options.test_relative_image_resolves_against_machine_folder) ... ok
test_second_gpu_none (test_command.Options.test_second_gpu_none) ... ok
test_binary_is_absolute_and_first (test_command.UserLaunchers.test_binary_is_absolute_and_first) ... ok
test_linux (test_command.UserLaunchers.test_linux) ... ok
test_mac_os (test_command.UserLaunchers.test_mac_os) ... ok
test_server12v3 (test_command.UserLaunchers.test_server12v3) ... ok
test_shell_rendering_shape (test_command.UserLaunchers.test_shell_rendering_shape) ... ok
test_bad_name_and_ram (test_command.Validation.test_bad_name_and_ram) ... ok
test_cd_elsewhere_with_index2_empty_warns (test_command.Validation.test_cd_elsewhere_with_index2_empty_warns) ... ok
test_duplicate_scsi_id_is_error (test_command.Validation.test_duplicate_scsi_id_is_error) ... ok
test_missing_image_is_warning_not_error (test_command.Validation.test_missing_image_is_warning_not_error) ... ok
test_scsi_id_7_is_the_computer (test_command.Validation.test_scsi_id_7_is_the_computer) ... ok
test_seeded_slot_without_image_is_warning_and_skipped (test_command.Validation.test_seeded_slot_without_image_is_warning_and_skipped) ... ok
test_bat_scsi_identity (test_command.WindowsRendering.test_bat_scsi_identity) ... ok
test_extra_args_windows_backslashes_kept (test_command.WindowsRendering.test_extra_args_windows_backslashes_kept) ... ok
test_posix_scsi_identity_token_is_whole (test_command.WindowsRendering.test_posix_scsi_identity_token_is_whole) ... ok

----------------------------------------------------------------------
Ran 41 tests in 0.009s

OK
```

### Rendered `run.command` for the vmnet-bridged variant of the Mac OS fixture

`tools/render_fixture.py tests/fixtures/mac-os-vmnet-bridged.json`

```
#!/bin/bash
# Generated by Qemu-GUI from machine.json. Hand edits are lost: this file is rewritten every time the machine is saved or started.
cd "$(dirname "$0")"

# vmnet networking needs root: the binary runs under sudo (Terminal asks for the password). Files QEMU creates under sudo are root-owned, so they are given back to the user afterwards.
sudo /Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc \
-M g3beige \
-m 512 \
-bios /Applications/qemu-system-ppc-g3-mac-os/PowerMacG3v3.ROM \
-display sdl \
-audiodev coreaudio,id=snd \
-global awacs.audiodev=snd \
-global ati-mach64-gt.romfile=/Applications/qemu-system-ppc-g3-mac-os/ati_mach_gt.rom \
-device ati-rage128-pro,addr=0x0e,romfile=/Applications/qemu-system-ppc-g3-mac-os/ati_nexus128_103_pci.rom \
-nic vmnet-bridged,ifname=en0,model=bmac,mac=00:05:02:12:34:56 \
-drive file=/Volumes/Macdata/qemu/hd/9.2-pristine-vm-off.img,format=raw,media=disk,index=0 \
-drive file=/Volumes/Macdata/qemu/iso/8.1.iso,format=raw,if=none,id=scd3 \
-device scsi-cd,drive=scd3,scsi-id=3

sudo chown "${SUDO_USER:-$(id -un)}" nvram.img pram.img 2>/dev/null
```

### Deviations in the addendum

- **A1 chown line.** The addendum says both `chown "$(id -un)"` guarded by
  `[ -n "$SUDO_USER" ]` and `chown "$SUDO_USER"`. Because only the binary
  is prefixed with sudo, `$SUDO_USER` is never set in the launcher script
  itself, so that guard would make the chown a no-op; and a plain `chown`
  by the user cannot take ownership away from root. Emitted instead:
  `sudo chown "${SUDO_USER:-$(id -un)}" nvram.img pram.img 2>/dev/null` --
  works whether the script is run plainly (sudo credentials are still
  cached from the QEMU run, so no second prompt) or wholly under sudo.
  `last-run.log` is not included: a Terminal-started run does not write it.
- **A2 ifname required.** An empty ifname for vmnet-bridged/tap is a
  validation *error* (QEMU rejects `ifname=`), not a warning; the editor
  prefills `en0` on macOS. A Windows tap record with a name loads and saves
  unchanged on macOS (tested); one with an empty name would need the name
  filled before Save on either platform.
- **A3 mode-vs-host** is a warning, as specified; the overview still shows
  the launcher for the record's mode and Start on macOS refuses a vmnet
  machine only when the host is not macOS.
- **A4 vmnet Start** issues `open -a Terminal <run.command>` from the
  machine folder and records the time; the machine list "State" column is
  not set to "running" because there is no pid to poll.

### Open questions (addendum)

1. Should vmnet-shared / vmnet-host be seeded as the default for any
   profile, or stay opt-in (currently opt-in; default remains `user`)?
2. On Windows, should Start for a `tap` machine also go through a visible
   console (so adapter-open errors are seen), or keep `Popen` + `last-run.log`
   (current)?

## Fix 1 (2026-09-03, main session): ATA bus 0 master could not be given a drive

User report: "it seems impossible to add a drive at ATA bus 0 master."
Cause: every OS profile seeds index 0 as a placeholder row (`kind=disk`,
no file). `CreateDiskDialog` offered only `first_empty_ata()` (slot is
`None`), which skipped the placeholder and offered index 1 instead; there
was no way to pick index 0 from that dialog. Fix: the dialog lists all four
ATA slots with their status (`empty` / `disk, no image yet` / `replace
<file>`), defaulting to the new `Machine.first_unfilled_ata()`. Also, a
file browsed or typed into a row whose Type is still "(empty)" no longer
gets dropped on save: the type is inferred from the extension (`.iso`,
`.toast`, `.cdr`, `.dmg` = CD-ROM, else hard disk). Regression test
`AtaSlotZero`; 42 tests pass.

## Fix 2 (2026-09-03, main session): bogus "ATA index 1: no image file" warning

User report: "It seems the GUI thinks indexing starts at 1? I get warning
there is no image at ATA index 1. This is bogus." Indexing was 0-based all
along; the warning fired for any row whose Type was set while its image
field stayed empty (profiles seeded such placeholder rows at index 0 and 2,
and the editor kept a type-only row alive). New rule everywhere: a row
without an image IS an empty slot -- collected as `None`, no warning,
skipped in the launcher; profiles seed no placeholders any more. Tests
updated (`test_slot_without_image_is_silently_empty`); 42 pass.

## Fix 3 (2026-09-03, main session): vmnet launchers ask for the password once

The generated `run.command` for a vmnet machine ran the binary under sudo
and finished with a `sudo chown` of `nvram.img`/`pram.img`. On any run
longer than sudo's default 5-minute ticket, that tail prompted for the
password a SECOND time, in the middle of the guest's own terminal output
(observed on a real bridged run). The launcher now takes the ticket once
with `sudo -v`, refreshes it every 60 s in a background loop for as long
as the script lives, kills that loop on exit, and uses `sudo -n chown` so
the tail can never prompt at all. Test
`test_vmnet_command_has_sudo_prefix_and_chown_tail` extended to assert the
keep-alive, its teardown, and the ordering; 42 tests pass.

## Rework (2026-09-05): beside the emulator, safe to delete, plain words

User feedback, verbatim: *"the gui still needs a lot of other work too. I do
not like its logic concerning qemu-system-ppc localisation, preset cd and hd
paths etc. I also do not like it being able to run outside a folder that
contains qemu-system-ppc. And where it keeps it records, particularly that it
deletes HD's when they were created by the gui inside the machine path. I
would prefer it to run inside a folder with the qemu program. And there are
lots of texts that might be clear to me or a knowledgable user, but are of no
use to regular user."*

Five changes, all in this repository.

**1. The program lives beside the emulator.** The configurable QEMU folder is
gone entirely: the global setting, the per-machine `qemu_dir` override, the
`/Applications/...` candidate list and the `$PATH` search. One function,
`paths.resolve_install_dir(frozen=, executable=, source_root=)`, answers
"which folder am I installed in" for three cases — from source, frozen inside
a macOS `.app` (walk up out of `Contents/MacOS`), frozen as a plain
executable — and `install_dir()` is the only caller of it. `machines_dir()`,
`settings_path()` and `qemu_binary()` all hang off it. A machine record that
still carries a `qemu_dir` key loads and drops it.

**2. It refuses to run without the emulator, first thing.** `main()` calls
`paths.startup_problem()` before importing Tk and before any window exists.
Missing binary → one plain message naming the folder it looked in, exit code
3. No folder chooser, no degraded mode. Second check (only after that one
passes): can `Machines/` be created here.

**3. Machines live in `Machines/` beside the program.** `Library()` defaults
to `paths.machines_dir()`. Settings hold nothing but `last_machine` and live
in `Machines/settings.json` — never inside a bundle, which is read-only.

**4. Deleting a machine cannot delete a disk image.** `Library.delete()`
removes only the names in `model.OWNED_FILES` (`machine.json`, `run.command`,
`run.bat`, `last-run.log`, `nvram.img`, `pram.img`, `.DS_Store`) directly
inside the machine's own folder; everything else stays, and the folder itself
is only removed by `rmdir`, which refuses anything non-empty. `shutil.rmtree`
no longer appears anywhere in the sources. `delete_preview()` feeds the
confirmation, which lists what will be kept and where before anything
happens; `report_delete()` says it again afterwards.
`model.check_new_image_path()` refuses to write over an existing file when
making a disk. Renaming a machine re-points the record at images that moved
with the folder. An AST-level test asserts no other code path can call
`unlink`, `rmdir`, `rmtree` or `remove`.

**5. Preset paths gone, wording rewritten.** No `/Volumes/Macdata` browse
fallbacks; drive and CD fields start empty; browse opens at what is already
filled in, else the machine's own folder, else home. Every visible string is
rewritten for a newcomer: the four drive positions are **Drive 1..4** with a
quiet second line ("the Mac starts up from this one (IDE bus 0, master —
index 0)"), SCSI drives are **Device 0..6** with **Device 7** shown as the Mac
itself, and the tabs are Basics / Screen / Drives / SCSI drives / Floppy /
Network & sound / Advanced.

67 tests pass. `tests/test_app.py` is new and covers the install-dir cases
(including a simulated `.app` bundle on disk), the refusal and its ordering,
and the disk-image promise.
