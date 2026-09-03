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

from qemugui import command, model, paths  # noqa: E402
from qemugui.model import Machine, AtaDrive, ScsiDrive, Identity, Floppy, SecondGpu, Governor, Network  # noqa: E402

FIXTURES = HERE / "fixtures"

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


def gen_tokens(m: Machine, platform: str = "darwin") -> set[str]:
    argv = command.build_argv(m, "/nonexistent-global-qemu-dir", str(FIXTURES), platform)
    return set(argv[1:])


class UserLaunchers(unittest.TestCase):
    """The primary correctness test: the three deployed launchers."""

    def test_mac_os(self):
        m = load_fixture("mac-os.json")
        self.assertEqual(gen_tokens(m), user_tokens(USER_MAC_OS, m.qemu_dir))

    def test_server12v3(self):
        m = load_fixture("server12v3.json")
        self.assertEqual(gen_tokens(m), user_tokens(USER_SERVER, m.qemu_dir))

    def test_linux(self):
        m = load_fixture("linux.json")
        self.assertEqual(gen_tokens(m), user_tokens(USER_LINUX, m.qemu_dir))

    def test_binary_is_absolute_and_first(self):
        m = load_fixture("mac-os.json")
        argv = command.build_argv(m, "", str(FIXTURES), "darwin")
        self.assertEqual(argv[0], "/Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc")

    def test_shell_rendering_shape(self):
        m = load_fixture("mac-os.json")
        text = command.launcher_text(m, "", str(FIXTURES), "darwin")
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
        argv = command.build_argv(m, "", r"C:\Machines\SCSI", "win32")
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
        argv = command.build_argv(m, "", "/tmp/m", "darwin")
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
        m = load_fixture("mac-os.json")
        m.qemu_dir = "/q"
        return m

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
        argv = command.build_argv(m, "", "/m", "darwin")
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

    def test_global_qemu_dir_used_when_no_override(self):
        m = self.base()
        m.qemu_dir = None
        argv = command.build_argv(m, "/Applications/qemu-system-ppc-g3-mac-os", "/m", "darwin")
        self.assertEqual(argv[0], "/Applications/qemu-system-ppc-g3-mac-os/qemu-system-ppc")


class JsonRoundTrip(unittest.TestCase):

    def test_fixtures_round_trip(self):
        for f in sorted(FIXTURES.glob("*.json")):
            m = Machine.load(f)
            again = Machine.from_json(m.to_json())
            self.assertEqual(m, again, f.name)
            self.assertEqual(json.loads(m.to_json())["schema"], model.SCHEMA)

    def test_full_record_round_trip(self):
        m = Machine(name="Every field", profile="macosx", ram_mb=768, rom="/abs/rom.ROM",
                    qemu_dir="/q", display="cocoa", audio="none",
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

    def test_legacy_profile_alias(self):
        m = Machine.from_dict({"name": "x", "profile": "macos9"})
        self.assertEqual(m.profile, "macos8_9")


class Validation(unittest.TestCase):

    def test_cd_elsewhere_with_index2_empty_warns(self):
        m = load_fixture("mac-os.json")
        m.ata[3] = AtaDrive("cdrom", "/x.iso")
        errors, warnings = model.validate(m, None, "darwin", check_files=False)
        self.assertEqual(errors, [])
        self.assertTrue(any("index 2 is empty" in w for w in warnings))

    def test_duplicate_scsi_id_is_error(self):
        m = load_fixture("mac-os.json")
        m.scsi.append(ScsiDrive(3, "disk", "/y.img"))
        errors, _ = model.validate(m, None, "darwin", check_files=False)
        self.assertTrue(any("SCSI drives use id 3" in e for e in errors))

    def test_bad_name_and_ram(self):
        m = load_fixture("mac-os.json")
        m.name = "bad/name"
        m.ram_mb = 8
        errors, _ = model.validate(m, None, "darwin", check_files=False)
        self.assertEqual(len(errors), 2)

    def test_missing_image_is_warning_not_error(self):
        m = load_fixture("mac-os.json")
        m.ata[0] = AtaDrive("disk", "/Volumes/Unmounted/x.img")
        errors, warnings = model.validate(m, "/nonexistent", "darwin", check_files=True)
        self.assertEqual(errors, [])
        self.assertTrue(any("Unmounted" in w for w in warnings))


class LibraryOps(unittest.TestCase):

    def test_create_save_duplicate_delete(self):
        with tempfile.TemporaryDirectory() as td:
            lib = model.Library(td)
            m = model.new_machine("Mac OS 9", "macos8_9", None)
            self.assertEqual(m.ram_mb, 512)
            self.assertIsNotNone(m.second_gpu)
            self.assertIsNone(m.onboard_romfile)  # no ROM in a None qemu_dir
            self.assertEqual([d.kind if d else None for d in m.ata], ["disk", None, "cdrom", None])
            lib.save(m)
            (lib.folder("Mac OS 9") / "nvram.img").write_bytes(b"\0" * 8192)
            self.assertEqual(lib.names(), ["Mac OS 9"])
            self.assertEqual(lib.managed_status("Mac OS 9"), {"nvram.img": 8192, "pram.img": None})
            d = lib.duplicate("Mac OS 9", "Mac OS 9 copy")
            self.assertEqual(d.name, "Mac OS 9 copy")
            self.assertTrue((lib.folder("Mac OS 9 copy") / "nvram.img").is_file())
            self.assertEqual(lib.reset_nvram_pram("Mac OS 9"), ["nvram.img"])
            self.assertEqual(lib.managed_status("Mac OS 9"), {"nvram.img": None, "pram.img": None})
            # rename via save
            d.name = "Renamed"
            lib.save(d, old_name="Mac OS 9 copy")
            self.assertEqual(sorted(lib.names()), ["Mac OS 9", "Renamed"])
            lib.delete("Renamed")
            self.assertEqual(lib.names(), ["Mac OS 9"])

    def test_write_launcher_is_executable_and_regenerated(self):
        with tempfile.TemporaryDirectory() as td:
            m = load_fixture("mac-os.json")
            path, argv = command.write_launcher(m, "", td, "darwin")
            self.assertEqual(path.name, "run.command")
            self.assertTrue(path.stat().st_mode & 0o111)
            self.assertIn("Hand edits are lost", path.read_text())
            m.ram_mb = 768
            path2, _ = command.write_launcher(m, "", td, "darwin")
            self.assertIn("-m 768", path2.read_text())
            pb, _ = command.write_launcher(m, "", td, "win32")
            self.assertEqual(pb.name, "run.bat")
            self.assertIn(b"\r\n", pb.read_bytes())


if __name__ == "__main__":
    unittest.main()
