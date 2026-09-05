"""Golden-output tests for qemugui.command / qemugui.model (headless, no Tk).

Run:  python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import re
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from qemugui import command, model, paths, systems  # noqa: E402
from qemugui.model import Machine, AtaDrive, ScsiDrive, Identity, Floppy, SecondGpu, Governor, Network  # noqa: E402

FIXTURES = HERE / "fixtures"

# The folder each fixture's launcher was written for. The program now always
# uses the folder it is installed in, so this is no longer part of the
# record: the tests pass it in the way the application does.
FIXTURE_QEMU_DIR = {
    "mac-os.json": "/Applications/qemu-system-ppc-g3-mac-os",
    "mac-os-vmnet-bridged.json": "/Applications/qemu-system-ppc-g3-mac-os",
    "server12v3.json": "/Applications/qemu-system-ppc-g3-server12v3",
    "linux.json": "/Applications/qemu-system-ppc-g3-linux",
    "scsi-windows.json": r"C:\qemu-g3",
    "tap-windows.json": r"C:\qemu-g3",
}

# The user's launchers, verbatim from doc/HANDOFF-qemu-gui.md ("Ground truth").
USER_MAC_OS = r"""
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
"""

USER_SERVER = r"""
./qemu-system-ppc \
-M g3beige \
-m 1024 \
-bios PowerMacG3v3.ROM \
-display cocoa \
-audiodev coreaudio,id=snd -global awacs.audiodev=snd \
-global ati-mach64-gt.romfile=ati_mach_gt.rom \
-nic user,model=bmac,mac=00:05:02:12:34:56 \
-drive file=/Volumes/Macdata/qemu/hd/Server1.2v3.img,format=raw,media=disk,index=0 \
-drive file=/Volumes/Macdata/qemu/iso/Server_1.2v3.iso,format=raw,media=cdrom,index=2
"""

USER_LINUX = r"""
./qemu-system-ppc \
-M g3beige -m 256 \
-bios PowerMacG3v3.ROM \
-display sdl \
-global ati-mach64-gt.romfile=ati_gt_fcode.rom \
-audiodev coreaudio,id=snd -global awacs.audiodev=snd \
-nic user,model=bmac,mac=00:05:02:12:34:56 \
-drive file=/Users/hsp/Downloads/debian-8.11.0-powerpc-CD-1.iso,format=raw,media=cdrom,index=2
"""


def user_tokens(text: str, qemu_dir: str) -> set[str]:
    """Token set of a user launcher, normalised the way the contract allows:
    binary dropped, relative ROM names resolved against the install folder
    (the user's launcher cd's into it, ours uses absolute paths), and the
    SCSI drive id cd0 -> scd3."""
    toks = shlex.split(text.replace("\\\n", " "))
    assert toks[0] == "./qemu-system-ppc"
    out = []
    for i, t in enumerate(toks[1:], 1):
        if toks[i - 1] == "-bios" and not t.startswith("/"):
            t = f"{qemu_dir}/{t}"
        t = re.sub(r"romfile=(?!/)([^,]+)", lambda mm: f"romfile={qemu_dir}/{mm.group(1)}", t)
        t = t.replace("id=cd0", "id=scd3").replace("drive=cd0", "drive=scd3")
        out.append(t)
    return set(out)


def load_fixture(name: str) -> Machine:
    return Machine.load(FIXTURES / name)


def gen_tokens(m: Machine, qemu_dir: str, platform: str = "darwin") -> set[str]:
    argv = command.build_argv(m, qemu_dir, str(FIXTURES), platform)
    return set(argv[1:])


class UserLaunchers(unittest.TestCase):
    """The primary correctness test: the three deployed launchers."""

    def check(self, fixture: str, text: str):
        qd = FIXTURE_QEMU_DIR[fixture]
        self.assertEqual(gen_tokens(load_fixture(fixture), qd), user_tokens(text, qd))

    def test_mac_os(self):
        self.check("mac-os.json", USER_MAC_OS)

    def test_server12v3(self):
        self.check("server12v3.json", USER_SERVER)

    def test_linux(self):
        self.check("linux.json", USER_LINUX)

    def test_binary_is_absolute_and_first(self):
        m = load_fixture("mac-os.json")
        argv = command.build_argv(m, "/Applications/qemu-system-ppc-g3-mac-os", str(FIXTURES), "darwin")
        self.assertEqual(argv[0], "/Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc")

    def test_shell_rendering_shape(self):
        m = load_fixture("mac-os.json")
        text = command.launcher_text(m, "/q", str(FIXTURES), "darwin")
        lines = text.splitlines()
        self.assertEqual(lines[0], "#!/bin/bash")
        self.assertIn('cd "$(dirname "$0")"', lines)
        body = [ln for ln in lines if ln.startswith("-") or ln.startswith("/")]
        for ln in body[:-1]:
            self.assertTrue(ln.endswith(" \\"), ln)
        self.assertFalse(body[-1].endswith("\\"))
        # one option per line, options in argv order
        self.assertIn("-device scsi-cd,drive=scd3,scsi-id=3", lines)
        self.assertIn("-M g3beige \\", lines)


class WindowsRendering(unittest.TestCase):

    def test_bat_scsi_identity(self):
        m = load_fixture("scsi-windows.json")
        argv = command.build_argv(m, r"C:\qemu-g3", r"C:\Machines\SCSI", "win32")
        text = command.render_bat(argv)
        self.assertEqual(argv[0], r"C:\qemu-g3\qemu-system-ppc.exe")
        self.assertIn('cd /d "%~dp0"', text)
        self.assertIn("@echo off", text)
        self.assertIn(" ^\r\n", text)
        self.assertNotIn(" \\\r\n", text)
        self.assertNotIn(" \\\n", text)
        self.assertIn("qemu-system-ppc.exe", text)
        self.assertIn('-device "scsi-hd,drive=shd0,scsi-id=0,vendor=QUANTUM,product=FIREBALL ST4.3S,ver=0F0C"', text)
        self.assertIn('-device "scsi-cd,drive=scd3,scsi-id=3,vendor=MATSHITA,product=CD-ROM CR-8005,ver=1.0k"', text)
        # relative SCSI image resolved against the machine folder, backslashes
        self.assertIn(r'-drive "file=C:\Machines\SCSI\scsiblank.img,format=raw,if=none,id=shd0"', text)
        self.assertIn(r"-bios C:\qemu-g3\PowerMacG3v3.ROM", text)
        self.assertIn('-audiodev "dsound,id=snd"', text)  # comma -> quoted (contract rule)
        # last line has no continuation
        body = [ln for ln in text.split("\r\n") if ln.startswith("-")]
        self.assertFalse(body[-1].endswith("^"))

    def test_posix_scsi_identity_token_is_whole(self):
        m = load_fixture("scsi-windows.json")
        argv = command.build_argv(m, "/q", "/tmp/m", "darwin")
        tok = [t for t in argv if t.startswith("scsi-hd,")][0]
        self.assertEqual(tok, "scsi-hd,drive=shd0,scsi-id=0,vendor=QUANTUM,product=FIREBALL ST4.3S,ver=0F0C")
        text = command.render_shell(argv)
        # shlex-quoted whole token on one line, and it round-trips
        line = [ln for ln in text.splitlines() if "scsi-hd" in ln][0]
        self.assertEqual(shlex.split(line.rstrip(" \\")), ["-device", tok])

    def test_extra_args_windows_backslashes_kept(self):
        toks = command.split_extra_args(r'-qmp tcp:127.0.0.1:4444,server=on -L "C:\my dir\bios"', "win32")
        self.assertEqual(toks, ["-qmp", "tcp:127.0.0.1:4444,server=on", "-L", r"C:\my dir\bios"])


class Options(unittest.TestCase):

    def base(self) -> Machine:
        return load_fixture("mac-os.json")

    def test_floppy(self):
        m = self.base()
        m.floppy = Floppy(file="/Volumes/Macdata/qemu/fd/macos71/Install.img", format="raw")
        argv = command.build_argv(m, "", "/m", "darwin")
        i = argv.index("swim3.drive=fd")
        self.assertEqual(argv[i - 1], "-global")
        self.assertIn("if=none,id=fd,file=/Volumes/Macdata/qemu/fd/macos71/Install.img,format=raw", argv)
        j = argv.index("if=none,id=fd,file=/Volumes/Macdata/qemu/fd/macos71/Install.img,format=raw")
        self.assertEqual(argv[j - 1], "-drive")

    def test_second_gpu_none(self):
        m = self.base()
        m.second_gpu = None
        argv = command.build_argv(m, "/q", "/m", "darwin")
        self.assertFalse(any("ati-rage128-pro" in t for t in argv))
        # onboard card still there
        self.assertIn("ati-mach64-gt.romfile=/q/ati_mach_gt.rom", argv)

    def test_governor(self):
        m = self.base()
        m.governor = Governor(mode="mips", mips=100)
        argv = command.build_argv(m, "", "/m", "darwin")
        self.assertEqual(argv[argv.index("-M") + 1], "g3beige,calibration-governor=mips=100")
        m.governor = Governor(mode="off")
        argv = command.build_argv(m, "", "/m", "darwin")
        self.assertEqual(argv[argv.index("-M") + 1], "g3beige,calibration-governor=off")
        m.governor = Governor(mode="default")
        argv = command.build_argv(m, "", "/m", "darwin")
        self.assertEqual(argv[argv.index("-M") + 1], "g3beige")

    def test_audio_and_network_none(self):
        m = self.base()
        m.audio = "none"
        m.network = Network(mode="none")
        argv = command.build_argv(m, "", "/m", "darwin")
        self.assertIn("none,id=snd", argv)
        self.assertIn("awacs.audiodev=snd", argv)
        self.assertEqual(argv[argv.index("-nic") + 1], "none")
        m.audio = "default"
        self.assertIn("coreaudio,id=snd", command.build_argv(m, "", "/m", "darwin"))
        self.assertIn("dsound,id=snd", command.build_argv(m, "", "/m", "win32"))
        m.audio = "sdl"
        self.assertIn("sdl,id=snd", command.build_argv(m, "", "/m", "darwin"))

    def test_onboard_rom_none(self):
        m = self.base()
        m.onboard_romfile = None
        argv = command.build_argv(m, "", "/m", "darwin")
        self.assertFalse(any("ati-mach64-gt.romfile" in t for t in argv))

    def test_ata_index_explicit_for_every_slot(self):
        m = self.base()
        m.scsi = []
        m.ata = [AtaDrive("disk", "/a.img"), AtaDrive("disk", "/b.img"),
                 AtaDrive("cdrom", "/c.iso"), AtaDrive("cdrom", "/d.iso")]
        argv = command.build_argv(m, "", "/m", "darwin")
        drives = [t for t in argv if t.startswith("file=")]
        self.assertEqual(drives, ["file=/a.img,format=raw,media=disk,index=0",
                                  "file=/b.img,format=raw,media=disk,index=1",
                                  "file=/c.iso,format=raw,media=cdrom,index=2",
                                  "file=/d.iso,format=raw,media=cdrom,index=3"])

    def test_comma_in_path_is_escaped_for_qemu(self):
        m = self.base()
        m.ata[0] = AtaDrive("disk", "/Volumes/x/a,b.img")
        argv = command.build_argv(m, "", "/m", "darwin")
        self.assertIn("file=/Volumes/x/a,,b.img,format=raw,media=disk,index=0", argv)

    def test_relative_image_resolves_against_machine_folder(self):
        m = self.base()
        m.ata[0] = AtaDrive("disk", "disk.img", "qcow2")
        argv = command.build_argv(m, "", "/lib/Mac OS", "darwin")
        self.assertIn("file=/lib/Mac OS/disk.img,format=qcow2,media=disk,index=0", argv)

    def test_extra_args_appended_verbatim(self):
        m = self.base()
        m.extra_args = "-qmp unix:/tmp/g92live.sock,server=on,wait=off -global ati-mach64-gt.host-cursor-tracking=off"
        argv = command.build_argv(m, "", "/m", "darwin")
        self.assertEqual(argv[-4:], ["-qmp", "unix:/tmp/g92live.sock,server=on,wait=off",
                                     "-global", "ati-mach64-gt.host-cursor-tracking=off"])

    def test_binary_comes_from_the_folder_the_app_is_in(self):
        """There is no per-machine override any more: whatever folder the
        application is installed in is the folder the emulator comes from."""
        m = self.base()
        self.assertFalse(hasattr(m, "qemu_dir"))
        self.assertNotIn("qemu_dir", json.loads(m.to_json()))
        argv = command.build_argv(m, "/Applications/qemu-system-ppc-g3-mac-os", "/m", "darwin")
        self.assertEqual(argv[0], "/Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc")
        argv = command.build_argv(m, "/somewhere/else", "/m", "darwin")
        self.assertEqual(argv[0], "/somewhere/else/qemu-system-ppc")

    def test_old_record_with_a_qemu_dir_key_loads_and_drops_it(self):
        m = Machine.from_dict({"name": "old", "qemu_dir": "/Applications/whatever"})
        self.assertNotIn("qemu_dir", json.loads(m.to_json()))


class Networking(unittest.TestCase):
    """Addendum 1: all modes go through -nic with model=bmac."""

    def nic(self, mode, ifname="", platform="darwin"):
        m = load_fixture("mac-os.json")
        m.network = Network(mode, "00:05:02:12:34:56", ifname)
        argv = command.build_argv(m, "/q", "/m", platform)
        return argv[argv.index("-nic") + 1]

    def test_none(self):
        self.assertEqual(self.nic("none"), "none")

    def test_user(self):
        self.assertEqual(self.nic("user"), "user,model=bmac,mac=00:05:02:12:34:56")

    def test_vmnet_bridged(self):
        self.assertEqual(self.nic("vmnet-bridged", "en0"),
                         "vmnet-bridged,ifname=en0,model=bmac,mac=00:05:02:12:34:56")

    def test_vmnet_shared(self):
        self.assertEqual(self.nic("vmnet-shared"), "vmnet-shared,model=bmac,mac=00:05:02:12:34:56")

    def test_vmnet_host(self):
        self.assertEqual(self.nic("vmnet-host"), "vmnet-host,model=bmac,mac=00:05:02:12:34:56")

    def test_tap(self):
        self.assertEqual(self.nic("tap", "TAP-Windows Adapter V9", "win32"),
                         "tap,ifname=TAP-Windows Adapter V9,model=bmac,mac=00:05:02:12:34:56")

    def test_vmnet_command_has_sudo_prefix_and_chown_tail(self):
        m = load_fixture("mac-os-vmnet-bridged.json")
        text = command.launcher_text(m, "/Applications/qemu-system-ppc-g3-mac-os", "/m", "darwin")
        lines = text.splitlines()
        self.assertIn("sudo /Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc \\", lines)
        self.assertIn("-nic vmnet-bridged,ifname=en0,model=bmac,mac=00:05:02:12:34:56 \\", lines)
        self.assertTrue(lines[-1].startswith("sudo -n chown "), lines[-1])
        self.assertIn("nvram.img pram.img", lines[-1])
        self.assertIn("SUDO_USER", lines[-1])
        # one password prompt only: the ticket is refreshed while the guest runs,
        # so the chown at the end cannot prompt again mid-run (-n proves it never will)
        self.assertIn("sudo -v", lines)
        self.assertTrue(any("SUDO_KEEPALIVE_PID=$!" in ln for ln in lines), text)
        self.assertTrue(any(ln.startswith('kill "$SUDO_KEEPALIVE_PID"') for ln in lines), text)
        self.assertLess(lines.index("sudo -v"),
                        [i for i, ln in enumerate(lines) if ln.startswith("sudo /")][0])
        # the argv used by Popen never contains sudo
        argv = command.build_argv(m, "/Applications/qemu-system-ppc-g3-mac-os", "/m", "darwin")
        self.assertNotIn("sudo", argv[0])
        self.assertTrue(command.needs_sudo(m, "darwin"))
        self.assertFalse(command.needs_sudo(m, "win32"))

    def test_user_mode_command_has_no_sudo(self):
        m = load_fixture("mac-os.json")
        text = command.launcher_text(m, "/q", "/m", "darwin")
        self.assertNotIn("sudo", text)
        self.assertNotIn("chown", text)

    def test_bat_never_has_sudo_or_chown(self):
        for f in ("tap-windows.json", "mac-os-vmnet-bridged.json"):
            m = load_fixture(f)
            text = command.launcher_text(m, r"C:\q", r"C:\m", "win32")
            self.assertNotIn("sudo", text, f)
            self.assertNotIn("chown", text, f)
        m = load_fixture("tap-windows.json")
        text = command.launcher_text(m, r"C:\q", r"C:\m", "win32")
        self.assertIn('-nic "tap,ifname=TAP-Windows Adapter V9,model=bmac,mac=00:05:02:12:34:56"', text)

    def test_cross_platform_load_save_round_trip(self):
        # a Windows tap record loaded on macOS saves unchanged and still renders tap
        m = load_fixture("tap-windows.json")
        self.assertEqual(m.network, Network("tap", "00:05:02:12:34:56", "TAP-Windows Adapter V9"))
        again = Machine.from_json(m.to_json())
        self.assertEqual(again, m)
        self.assertEqual(json.loads(m.to_json())["network"],
                         {"mode": "tap", "mac": "00:05:02:12:34:56", "ifname": "TAP-Windows Adapter V9"})
        self.assertIn("tap,ifname=TAP-Windows Adapter V9,model=bmac,mac=00:05:02:12:34:56",
                      command.build_argv(m, "", "/m", "darwin"))
        errors, warnings = model.validate(m, None, "darwin", check_files=False)
        self.assertEqual(errors, [])
        self.assertTrue(any("only works on Windows" in w for w in warnings))
        # and a macOS vmnet record on Windows
        v = load_fixture("mac-os-vmnet-bridged.json")
        self.assertEqual(Machine.from_json(v.to_json()), v)
        errors, warnings = model.validate(v, None, "win32", check_files=False)
        self.assertEqual(errors, [])
        self.assertTrue(any("only works on a Mac" in w for w in warnings))
        # user/none records carry no ifname key
        self.assertNotIn("ifname", json.loads(load_fixture("mac-os.json").to_json())["network"])

    def test_modes_offered_per_host(self):
        self.assertEqual(model.network_modes_for_host("darwin"),
                         ["none", "user", "vmnet-bridged", "vmnet-shared", "vmnet-host"])
        self.assertEqual(model.network_modes_for_host("win32"), ["none", "user", "tap"])
        self.assertEqual(model.network_modes_for_host("win32", "vmnet-shared"),
                         ["none", "user", "tap", "vmnet-shared"])

    def test_ifname_required(self):
        m = load_fixture("mac-os.json")
        m.network = Network("vmnet-bridged", "00:05:02:12:34:56", "")
        errors, _ = model.validate(m, None, "darwin", check_files=False)
        # the message says what is wrong, and nothing about how to fix it
        self.assertEqual(errors, ["No interface named."])


class JsonRoundTrip(unittest.TestCase):

    def test_fixtures_round_trip(self):
        for f in sorted(FIXTURES.glob("*.json")):
            m = Machine.load(f)
            again = Machine.from_json(m.to_json())
            self.assertEqual(m, again, f.name)
            self.assertEqual(json.loads(m.to_json())["schema"], model.SCHEMA)

    def test_full_record_round_trip(self):
        m = Machine(name="Every field", system="macosx_10_0_to_10_2", ram_mb=768, rom="/abs/rom.ROM",
                    display="cocoa", audio="none",
                    onboard_romfile="ati_mach_gt.rom",
                    second_gpu=SecondGpu("ati-rage128-pro", "0x0f", "card.rom"),
                    network=Network("user", "00:11:22:33:44:55"),
                    governor=Governor("mips", 250),
                    ata=[AtaDrive("disk", "/a.img", "qcow2"), None, AtaDrive("cdrom", "/c.iso"), None],
                    scsi=[ScsiDrive(0, "disk", "/s.img", "raw", Identity("QUANTUM", "FIREBALL ST4.3S", "0F0C")),
                          ScsiDrive(3, "cdrom", "/s.iso", "raw", None)],
                    floppy=Floppy("/f.img"), extra_args="-qmp none", notes="n\u00f6tes")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "machine.json"
            m.save(p)
            self.assertEqual(Machine.load(p), m)

    def test_a_record_names_one_of_the_five_systems(self):
        """The stored id is the visible entry written plainly. Anything else
        is not translated -- it is "Other"."""
        self.assertEqual(systems.system_ids(),
                         ["macos_8_to_9", "macosx_10_0_to_10_2", "osx_server_1_2v3",
                          "linux", "other"])
        self.assertEqual([p.label for p in systems.SYSTEMS.values()],
                         ["Mac OS 8 to 9", "Mac OS X 10.0 to 10.2", "OSX Server 1.2v3",
                          "Linux", "Other"])
        self.assertEqual(Machine.from_dict({"name": "x", "system": "macos9"}).system, "other")
        self.assertEqual(Machine.from_dict({"name": "x"}).system, "other")


class Validation(unittest.TestCase):

    def test_cd_elsewhere_with_index2_empty_warns(self):
        m = load_fixture("mac-os.json")
        m.ata[3] = AtaDrive("cdrom", "/x.iso")
        errors, warnings = model.validate(m, None, "darwin", check_files=False)
        self.assertEqual(errors, [])
        # one plain statement, naming the position the tab names
        self.assertEqual(warnings, ["The CD is not in Drive 3."])

    def test_duplicate_scsi_id_is_error(self):
        m = load_fixture("mac-os.json")
        m.scsi.append(ScsiDrive(3, "disk", "/y.img"))
        errors, _ = model.validate(m, None, "darwin", check_files=False)
        self.assertTrue(any("both set to device 3" in e for e in errors))

    def test_scsi_id_7_is_the_computer(self):
        m = load_fixture("mac-os.json")
        m.scsi.append(ScsiDrive(7, "disk", "/y.img"))
        errors, _ = model.validate(m, None, "darwin", check_files=False)
        self.assertTrue(any("device 7 is the Macintosh" in e for e in errors))
        loaded = Machine.from_dict({"name": "x", "scsi": [{"id": 7, "kind": "disk", "file": "/y.img"}]})
        errors, _ = model.validate(loaded, None, "darwin", check_files=False)
        self.assertTrue(any("device 7 is the Macintosh" in e for e in errors))

    def test_bad_name_and_ram(self):
        m = load_fixture("mac-os.json")
        m.name = "bad/name"
        m.ram_mb = 8
        errors, _ = model.validate(m, None, "darwin", check_files=False)
        self.assertEqual(len(errors), 2)

    def test_slot_without_image_is_silently_empty(self):
        # user report 2026-09-03: "warning there is no image at ATA index 1. This is bogus."
        m = model.new_machine("Fresh", "macos_8_to_9")
        self.assertEqual(m.ata, [None, None, None, None])      # systems seed no placeholders
        m.ata[1] = model.AtaDrive("disk", "", "raw")           # type chosen, no image
        m.scsi = [model.ScsiDrive(2, "cdrom", "", "raw", None)]
        errors, warnings = model.validate(m, None, "darwin", check_files=False)
        self.assertEqual(errors, [])
        self.assertFalse(any("no image" in w for w in warnings), warnings)
        self.assertFalse(any("index 1" in w for w in warnings), warnings)
        argv = command.build_argv(m, "/q", "/m", "darwin")
        self.assertNotIn("-drive", argv)

    def test_missing_image_is_warning_not_error(self):
        m = load_fixture("mac-os.json")
        m.ata[0] = AtaDrive("disk", "/Volumes/Unmounted/x.img")
        errors, warnings = model.validate(m, "/nonexistent", "darwin", check_files=True)
        self.assertEqual(errors, [])
        self.assertTrue(any("Unmounted" in w for w in warnings))
        # named the way the tab names it, not "ATA index 0"
        self.assertTrue(any(w.startswith("Drive 1:") for w in warnings), warnings)


class LibraryOps(unittest.TestCase):

    def test_create_save_duplicate_delete(self):
        with tempfile.TemporaryDirectory() as td:
            lib = model.Library(td)
            m = model.new_machine("Mac OS 9", "macos_8_to_9")
            self.assertEqual(m.ram_mb, 512)
            self.assertIsNone(m.second_gpu)       # the second screen is opt-in
            self.assertIsNone(m.onboard_romfile)  # no file is ever chosen for you
            self.assertEqual([d.kind if d else None for d in m.ata], [None, None, None, None])
            lib.save(m)
            (lib.folder("Mac OS 9") / "nvram.img").write_bytes(b"\0" * 8192)
            self.assertEqual(lib.names(), ["Mac OS 9"])
            self.assertEqual(lib.saved_settings_status("Mac OS 9"), {"nvram.img": 8192, "pram.img": None})
            d = lib.duplicate("Mac OS 9", "Mac OS 9 copy")
            self.assertEqual(d.name, "Mac OS 9 copy")
            self.assertTrue((lib.folder("Mac OS 9 copy") / "nvram.img").is_file())
            self.assertEqual(lib.clear_saved_settings("Mac OS 9"), ["nvram.img"])
            self.assertEqual(lib.saved_settings_status("Mac OS 9"), {"nvram.img": None, "pram.img": None})
            # rename via save
            d.name = "Renamed"
            lib.save(d, old_name="Mac OS 9 copy")
            self.assertEqual(sorted(lib.names()), ["Mac OS 9", "Renamed"])
            lib.delete("Renamed")
            self.assertEqual(lib.names(), ["Mac OS 9"])

    def test_write_launcher_is_executable_and_regenerated(self):
        with tempfile.TemporaryDirectory() as td:
            m = load_fixture("mac-os.json")
            path, argv = command.write_launcher(m, "/q", td, "darwin")
            self.assertEqual(path.name, "run.command")
            self.assertTrue(path.stat().st_mode & 0o111)
            self.assertIn("Do not edit", path.read_text())
            m.ram_mb = 768
            path2, _ = command.write_launcher(m, "/q", td, "darwin")
            self.assertIn("-m 768", path2.read_text())
            pb, _ = command.write_launcher(m, "/q", td, "win32")
            self.assertEqual(pb.name, "run.bat")
            self.assertIn(b"\r\n", pb.read_bytes())


if __name__ == "__main__":
    unittest.main()


class AtaSlotZero(unittest.TestCase):
    """User report 2026-09-03: 'impossible to add a drive at ATA bus 0 master'.
    A system seeded index 0 as a placeholder (kind set, no file); the create-disk
    dialog offered only the first *empty* slot, so index 0 was never offered."""

    def test_first_unfilled_ata_offers_seeded_index_0(self):
        m = model.new_machine("t", "macos_8_to_9")
        m.ata[0] = model.AtaDrive("disk", "", "raw")      # a type-only row, as the editor once produced
        self.assertEqual(m.first_empty_ata(), 1)          # the old behaviour, kept for reference
        self.assertEqual(m.first_unfilled_ata(), 0)       # what the dialog must default to
        self.assertEqual(m.ata_slot_status(0), "empty")
        self.assertEqual(m.ata_slot_status(1), "empty")
        m.ata[0] = model.AtaDrive("disk", "/x/9.2.img", "raw")
        self.assertEqual(m.first_unfilled_ata(), 1)
        self.assertTrue(m.ata_slot_status(0).startswith("replace 9.2.img"))


class NothingIsChosenForYou(unittest.TestCase):
    """User instruction 2026-09-05: "the gui has self-selected files again,
    like the powermac rom, the ati mach rom. Make it stop doing these
    self-selections overal."

    So: no field that names a file is ever filled in by the program, for any
    system, whatever files happen to be sitting beside the emulator."""

    def test_a_new_machine_has_every_file_field_empty(self):
        for system_id in systems.system_ids():
            m = model.new_machine("Fresh", system_id)
            for field, value in model.file_fields(m).items():
                self.assertEqual(value, "", f"{system_id}: {field} was filled in")
            self.assertEqual(m.rom, "")
            self.assertIsNone(m.onboard_romfile)
            self.assertEqual(m.notes, "")
            if m.second_gpu:
                self.assertIsNone(m.second_gpu.romfile)

    def test_an_empty_record_names_no_files_either(self):
        self.assertEqual(model.Machine().rom, "")
        self.assertIsNone(model.SecondGpu().romfile)
        self.assertEqual(model.file_fields(model.Machine()),
                         {"rom": "", "onboard_romfile": "", "second_gpu.romfile": "",
                          "floppy": "", "ata[0]": "", "ata[1]": "", "ata[2]": "", "ata[3]": ""})

    def test_a_likely_looking_file_beside_the_emulator_is_not_picked_up(self):
        """The positive control for the test above: the files that used to be
        offered are really there, and are still not chosen."""
        with tempfile.TemporaryDirectory() as td:
            here = Path(td)
            for name in ("PowerMacG3v3.ROM", "ati_mach_gt.rom", "ati_gt_fcode.rom",
                         "ati_nexus128_103_pci.rom", "qemu-system-ppc"):
                (here / name).write_bytes(b"x")
            paths.use_install_dir(here)
            try:
                self.assertTrue(paths.has_qemu(here, "darwin"))     # a real install folder
                m = model.new_machine("Fresh", "macos_8_to_9")
                self.assertEqual(set(model.file_fields(m).values()), {""})
            finally:
                paths.use_install_dir(None)

    def test_new_machine_cannot_go_looking(self):
        """It is not given a folder to search, so it cannot search one."""
        import inspect
        self.assertEqual(list(inspect.signature(model.new_machine).parameters),
                         ["name", "system_id"])

    def test_no_default_rom_names_are_left_in_the_record_layer(self):
        for gone in ("DEFAULT_ROM", "DEFAULT_SECOND_GPU_ROM"):
            self.assertFalse(hasattr(systems, gone), gone)
        for src in ("systems.py", "model.py"):
            text = (HERE.parent / "qemugui" / src).read_text()
            for name in ("PowerMacG3v3.ROM", "ati_mach_gt.rom", "ati_gt_fcode.rom",
                         "ati_nexus128_103_pci.rom"):
                self.assertNotIn(name, text, f"{src} still names {name}")

    def test_a_machine_without_a_rom_saves_but_will_not_start(self):
        """Half-finished is allowed; starting half-finished is not."""
        m = model.new_machine("Fresh", "macos_8_to_9")
        errors, _warnings = model.validate(m, None, "darwin", check_files=False)
        self.assertEqual(errors, [])                       # Save is not blocked
        blockers = model.start_blockers(m)
        self.assertEqual(len(blockers), 1)
        self.assertIn("ROM", blockers[0])
        m.rom = "PowerMacG3v3.ROM"
        self.assertEqual(model.start_blockers(m), [])

    def test_no_rom_means_no_bios_option_rather_than_a_guess(self):
        m = model.new_machine("Fresh", "macos_8_to_9")
        argv = command.build_argv(m, "/install", "/m", "darwin")
        self.assertNotIn("-bios", argv)
        self.assertFalse(any("/install" in t for t in argv[1:]), argv)
        m.rom = "PowerMacG3v3.ROM"
        argv = command.build_argv(m, "/install", "/m", "darwin")
        self.assertEqual(argv[argv.index("-bios") + 1], "/install/PowerMacG3v3.ROM")


class DisplayChoice(unittest.TestCase):
    """The window on this computer: cocoa is offered first and is what a new
    machine starts with (2026-09-05)."""

    def test_cocoa_is_first_on_a_mac(self):
        self.assertEqual(model.DISPLAYS["darwin"][0], "cocoa")
        self.assertEqual(model.default_display("darwin"), "cocoa")

    def test_a_new_machine_starts_on_cocoa_on_a_mac(self):
        self.assertEqual(model.Machine().display, "cocoa")
        if paths.HOST_PLATFORM == "darwin":
            self.assertEqual(model.new_machine("Fresh", "macos_8_to_9").display, "cocoa")

    def test_the_other_platforms_keep_a_window_that_exists_there(self):
        self.assertEqual(model.default_display("win32"), "sdl")
        self.assertEqual(model.default_display("linux"), "sdl")
        m = model.Machine(display=model.default_display("win32"))
        errors, warnings = model.validate(m, None, "win32", check_files=False)
        self.assertEqual(errors, [])
        self.assertFalse(any("cocoa" in w for w in warnings), warnings)
