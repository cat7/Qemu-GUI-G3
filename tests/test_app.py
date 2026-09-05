"""Where the application thinks it is, what it refuses to do, and the one
promise that matters: no code path deletes or overwrites a disk image.

Headless: nothing here imports Tk.  Run:  python -m unittest discover -s tests
"""

from __future__ import annotations

import ast
import hashlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import qemu_gui                                    # noqa: E402
from qemugui import command, model, paths          # noqa: E402


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class InstallDir(unittest.TestCase):
    """One function answers "which folder am I installed in", for all three
    ways this program is ever started."""

    def test_running_from_source(self):
        got = paths.resolve_install_dir(frozen=False,
                                        executable="/usr/local/bin/python3.13",
                                        source_root="/Users/someone/Qemu-GUI")
        self.assertEqual(got, Path("/Users/someone/Qemu-GUI"))

    def test_frozen_inside_a_macos_application_bundle(self):
        """PyInstaller puts the executable four levels down, inside the
        bundle. The folder a person sees is the one holding the .app."""
        got = paths.resolve_install_dir(
            frozen=True,
            executable="/Applications/qemu-g3/QemuGUI.app/Contents/MacOS/QemuGUI",
            source_root="/nowhere")
        self.assertEqual(got, Path("/Applications/qemu-g3"))

    def test_frozen_bundle_nested_deeper(self):
        got = paths.resolve_install_dir(
            frozen=True,
            executable="/Users/hsp/qemu/QemuGUI.app/Contents/MacOS/sub/QemuGUI",
            source_root="/nowhere")
        self.assertEqual(got, Path("/Users/hsp/qemu"))

    def test_frozen_windows_executable(self):
        got = paths.resolve_install_dir(frozen=True,
                                        executable="/c/qemu-g3/QemuGUI.exe",
                                        source_root="/nowhere")
        self.assertEqual(got, Path("/c/qemu-g3"))

    def test_source_root_points_at_the_entry_script(self):
        self.assertTrue((paths.SOURCE_ROOT / "qemu_gui.py").is_file())

    def test_everything_hangs_off_install_dir(self):
        with tempfile.TemporaryDirectory() as td:
            paths.use_install_dir(td)
            try:
                here = Path(td).resolve()
                self.assertEqual(paths.install_dir(), here)
                self.assertEqual(paths.machines_dir(), here / "Machines")
                self.assertEqual(paths.settings_path(), here / "Machines" / "settings.json")
                self.assertEqual(paths.qemu_binary("darwin"), here / "qemu-system-ppc")
                self.assertEqual(paths.qemu_binary("win32"), here / "qemu-system-ppc.exe")
                self.assertEqual(model.Library().root, here / "Machines")
            finally:
                paths.use_install_dir(None)

    def test_no_settings_are_stored_inside_a_bundle(self):
        """An application bundle is read-only; Machines is beside it."""
        paths.use_install_dir("/Applications/qemu-g3")
        try:
            for p in (paths.machines_dir(), paths.settings_path()):
                self.assertNotIn(".app", str(p))
                self.assertTrue(str(p).startswith("/Applications/qemu-g3/Machines"))
        finally:
            paths.use_install_dir(None)


class FrozenBundle(unittest.TestCase):
    """The packaged case, simulated on disk: a real .app-shaped folder with a
    real emulator file beside it, and the program started as if frozen.
    Proves install_dir() is wired to resolve_install_dir(), that the emulator
    is found from inside the bundle, and that Machines lands outside it."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.install = Path(self.td.name).resolve()
        exe = self.install / "QemuGUI.app" / "Contents" / "MacOS" / "QemuGUI"
        exe.parent.mkdir(parents=True)
        exe.write_text("")
        binary = self.install / paths.qemu_binary_name()
        binary.write_text("#!/bin/sh\n")
        os.chmod(binary, 0o755)
        self.exe = exe
        self._frozen = getattr(sys, "frozen", None)
        self._executable = sys.executable
        sys.frozen = True
        sys.executable = str(exe)

    def tearDown(self):
        sys.executable = self._executable
        if self._frozen is None:
            del sys.frozen
        else:
            sys.frozen = self._frozen
        self.td.cleanup()

    def test_a_frozen_bundle_finds_the_emulator_beside_the_bundle(self):
        self.assertEqual(paths.install_dir(), self.install)
        self.assertEqual(paths.machines_dir(), self.install / "Machines")
        self.assertNotIn(".app", str(paths.machines_dir()))
        self.assertIsNone(paths.startup_problem())
        self.assertTrue((self.install / "Machines").is_dir())
        # nothing was written inside the bundle
        self.assertEqual(sorted(p.name for p in (self.install / "QemuGUI.app").rglob("*")),
                         ["Contents", "MacOS", "QemuGUI"])

    def test_a_frozen_bundle_without_the_emulator_still_refuses(self):
        (self.install / paths.qemu_binary_name()).unlink()
        problem = paths.startup_problem()
        self.assertIn(str(self.install), problem)
        self.assertNotIn(".app", problem)      # it names the folder, not the bundle


class FakeMainWindow:
    """Stands in for the real window so the test can prove it is never built."""

    built = 0

    def __init__(self, *a, **k):
        FakeMainWindow.built += 1

    def mainloop(self):
        pass


class RefusesToStartWithoutTheEmulator(unittest.TestCase):
    """The emulator sitting beside the program is checked first, before
    anything else happens at all: no window, no machine list, no settings."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name).resolve()
        paths.use_install_dir(self.dir)
        FakeMainWindow.built = 0
        fake = types.ModuleType("qemugui.ui_main")
        fake.MainWindow = FakeMainWindow
        self._saved = sys.modules.get("qemugui.ui_main")
        sys.modules["qemugui.ui_main"] = fake

    def tearDown(self):
        paths.use_install_dir(None)
        if self._saved is None:
            sys.modules.pop("qemugui.ui_main", None)
        else:
            sys.modules["qemugui.ui_main"] = self._saved
        self.td.cleanup()

    def make_binary(self):
        p = self.dir / paths.qemu_binary_name()
        p.write_text("#!/bin/sh\n")
        os.chmod(p, 0o755)
        return p

    def test_missing_binary_stops_the_program(self):
        said = []
        rc = qemu_gui.main([], report_problem=said.append)
        self.assertEqual(rc, qemu_gui.EXIT_CANNOT_RUN)
        self.assertEqual(len(said), 1)
        message = said[0]
        self.assertIn(paths.qemu_binary_name(), message)
        self.assertIn(str(self.dir), message)          # names the folder it looked in
        self.assertNotIn("Traceback", message)

    def test_missing_binary_builds_no_window_and_touches_nothing(self):
        rc = qemu_gui.main([], report_problem=lambda _m: None)
        self.assertEqual(rc, qemu_gui.EXIT_CANNOT_RUN)
        self.assertEqual(FakeMainWindow.built, 0)      # no degraded, complaining interface
        self.assertFalse((self.dir / "Machines").exists())   # nothing was created either
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), [])

    def test_the_binary_is_checked_before_the_machines_folder(self):
        """Order matters: an unwritable install must still complain about the
        emulator first, because that is the thing that defines the folder."""
        os.chmod(self.dir, 0o500)
        try:
            self.assertIn(paths.qemu_binary_name(), paths.startup_problem())
        finally:
            os.chmod(self.dir, 0o700)

    def test_positive_control_the_check_passes_when_the_binary_is_there(self):
        """Proof the instrument works: the same call succeeds once the file
        is put beside the program, and then the window is built."""
        self.make_binary()
        self.assertIsNone(paths.startup_problem())
        rc = qemu_gui.main([], report_problem=lambda m: self.fail(m))
        self.assertEqual(rc, 0)
        self.assertEqual(FakeMainWindow.built, 1)
        self.assertTrue((self.dir / "Machines").is_dir())

    def test_unwritable_install_folder_is_explained(self):
        self.make_binary()
        os.chmod(self.dir, 0o500)
        try:
            problem = paths.startup_problem()
        finally:
            os.chmod(self.dir, 0o700)
        self.assertIsNotNone(problem)
        self.assertIn("Machines", problem)
        self.assertIn(str(self.dir), problem)

    def test_nothing_offers_to_choose_a_folder(self):
        source = "\n".join((ROOT / "qemu_gui.py").read_text().splitlines()
                           + [(ROOT / "qemugui" / f).read_text()
                              for f in ("paths.py", "model.py", "command.py")])
        self.assertNotIn("askdirectory", source)
        for gone in ("library_dir", "qemu_dir_var", "discover_qemu_dir", "QEMU_DIR_CANDIDATES",
                     "BROWSE_FALLBACKS", "default_library_dir"):
            self.assertNotIn(gone, source, gone)


class DeleteNeverTouchesADiskImage(unittest.TestCase):
    """A disk image can be hours of installing an operating system. Deleting
    a machine removes the record, the launcher and the saved settings, and
    nothing else."""

    def machine_with_images(self, root: Path) -> tuple[model.Library, Path, dict]:
        lib = model.Library(root)
        m = model.new_machine("Mac OS 9", "macos8_9", None)
        lib.save(m)
        folder = lib.folder("Mac OS 9")
        command.write_launcher(m, "/q", str(folder), "darwin")
        (folder / "nvram.img").write_bytes(b"\0" * 8192)
        (folder / "pram.img").write_bytes(b"\0" * 256)
        (folder / "last-run.log").write_text("log\n")
        images = {}
        for name, body in (("Mac OS 9.img", b"a whole afternoon of installing" * 100),
                           ("scratch.qcow2", b"qcow2 stand-in" * 50),
                           ("Install CD.iso", b"an iso" * 10),
                           ("notes about this disk.txt", b"my own notes")):
            (folder / name).write_bytes(body)
            images[name] = hashlib.sha256(body).hexdigest()
        return lib, folder, images

    def test_delete_leaves_disk_images_in_place(self):
        with tempfile.TemporaryDirectory() as td:
            lib, folder, images = self.machine_with_images(Path(td))

            will_go, will_stay = lib.delete_preview("Mac OS 9")
            self.assertEqual(sorted(will_go),
                             ["last-run.log", "machine.json", "nvram.img", "pram.img",
                              "run.command"])
            self.assertEqual(sorted(will_stay), sorted(images))

            result = lib.delete("Mac OS 9")

            # the record, the launcher and the saved settings are gone
            self.assertEqual(sorted(result.removed), sorted(will_go))
            for gone in will_go:
                self.assertFalse((folder / gone).exists(), gone)
            # every image is still there, byte for byte, in the same folder
            self.assertTrue(folder.is_dir())
            self.assertFalse(result.folder_removed)
            self.assertEqual(sorted(result.kept), sorted(images))
            for name, want in images.items():
                self.assertTrue((folder / name).is_file(), name)
                self.assertEqual(digest(folder / name), want, name)
            # and the person can be told where they are
            self.assertEqual(sorted(result.kept_images),
                             ["Install CD.iso", "Mac OS 9.img", "scratch.qcow2"])
            self.assertEqual(result.folder, folder)
            # the machine is no longer listed
            self.assertEqual(lib.names(), [])

    def test_folder_goes_away_only_when_nothing_is_left_in_it(self):
        with tempfile.TemporaryDirectory() as td:
            lib = model.Library(Path(td))
            lib.save(model.new_machine("Empty", "custom", None))
            folder = lib.folder("Empty")
            (folder / "nvram.img").write_bytes(b"\0" * 8192)
            result = lib.delete("Empty")
            self.assertTrue(result.folder_removed)
            self.assertFalse(folder.exists())
            self.assertEqual(result.kept, [])

    def test_an_image_in_a_subfolder_is_kept_too(self):
        with tempfile.TemporaryDirectory() as td:
            lib = model.Library(Path(td))
            lib.save(model.new_machine("Sub", "custom", None))
            folder = lib.folder("Sub")
            (folder / "disks").mkdir()
            (folder / "disks" / "big.img").write_bytes(b"x" * 1000)
            result = lib.delete("Sub")
            self.assertEqual(result.kept, ["disks/big.img"])
            self.assertTrue((folder / "disks" / "big.img").is_file())
            self.assertFalse(result.folder_removed)

    def test_a_disk_image_named_like_one_of_our_files_is_not_special(self):
        """The allow-list is by name, so this is the honest edge: a file
        actually called nvram.img is ours. Nothing that looks like a disk
        image can be given one of those names by the program itself."""
        self.assertNotIn("machine.img", model.OWNED_FILES)
        self.assertTrue(set(model.OWNED_FILES).isdisjoint(
            {"disk.img", "9.2.img", "Mac OS 9.qcow2", "Install.iso"}))

    def test_delete_refuses_to_walk_out_of_the_machines_folder(self):
        with tempfile.TemporaryDirectory() as td:
            outside = Path(td) / "outside"
            outside.mkdir()
            (outside / "machine.json").write_text("{}")
            lib = model.Library(Path(td) / "Machines")
            lib.ensure()
            result = lib.delete("../outside")
            self.assertEqual(result.removed, [])
            self.assertTrue((outside / "machine.json").is_file())

    def test_a_full_lifecycle_never_changes_an_image(self):
        """Create, save, rename, duplicate, clear the saved settings, write
        the launcher, delete -- and the images come out byte-identical."""
        with tempfile.TemporaryDirectory() as td:
            lib, folder, images = self.machine_with_images(Path(td))
            m = lib.load("Mac OS 9")
            m.ata[0] = model.AtaDrive("disk", str(folder / "Mac OS 9.img"))
            lib.save(m)
            m.name = "Mac OS 9.2"
            lib.save(m, old_name="Mac OS 9")
            new_folder = lib.folder("Mac OS 9.2")
            # the image moved with its folder, and the record followed it
            self.assertEqual(lib.load("Mac OS 9.2").ata[0].file,
                             str(new_folder / "Mac OS 9.img"))
            lib.duplicate("Mac OS 9.2", "Mac OS 9.2 copy")
            lib.clear_saved_settings("Mac OS 9.2")
            command.write_launcher(m, "/q", str(new_folder), "darwin")
            lib.delete("Mac OS 9.2 copy")
            lib.delete("Mac OS 9.2")
            for name, want in images.items():
                self.assertEqual(digest(new_folder / name), want, name)

    def test_creating_a_disk_never_overwrites_one(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / "Mac OS 9.img").write_bytes(b"precious")
            target, why = model.check_new_image_path(folder, "Mac OS 9", "raw")
            self.assertIsNone(target)
            self.assertIn("will not write over it", why)
            target, why = model.check_new_image_path(folder, "Mac OS 9", "qcow2")
            self.assertEqual(target, folder / "Mac OS 9.qcow2")
            self.assertIsNone(why)
            target, why = model.check_new_image_path(folder, "a/b", "raw")
            self.assertIsNone(target)
            self.assertIn("without any slashes", why)
            self.assertEqual(digest(folder / "Mac OS 9.img"),
                             hashlib.sha256(b"precious").hexdigest())


class NoOtherPathCanRemoveAFile(unittest.TestCase):
    """A source-level guard, so a later change cannot quietly reintroduce a
    recursive delete. Every call that can remove something is accounted for."""

    ALLOWED = {
        "rmtree": set(),                                    # nowhere, ever
        "remove": set(),
        "rmdir": {"delete"},                                # only empty folders
        "unlink": {"delete", "clear_saved_settings", "startup_problem"},
    }

    def test_removal_calls_are_only_in_the_places_that_may_remove(self):
        offenders = []
        for src in sorted(ROOT.glob("qemugui/*.py")) + [ROOT / "qemu_gui.py"]:
            tree = ast.parse(src.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        name = getattr(inner.func, "attr", None) or getattr(inner.func, "id", None)
                        if name in self.ALLOWED and node.name not in self.ALLOWED[name]:
                            offenders.append(f"{src.name}:{inner.lineno} {name}() in {node.name}()")
        self.assertEqual(offenders, [])

    def test_no_recursive_delete_anywhere_in_the_sources(self):
        for src in sorted(ROOT.glob("qemugui/*.py")) + [ROOT / "qemu_gui.py"]:
            self.assertNotIn("rmtree", src.read_text(), src.name)


if __name__ == "__main__":
    unittest.main()
