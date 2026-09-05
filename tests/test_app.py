"""Where the application thinks it is, what it refuses to do, and the one
promise that matters: no code path deletes or overwrites a disk image.

Headless: nothing here imports Tk.  Run:  python -m unittest discover -s tests
"""

from __future__ import annotations

import ast
import hashlib
import re
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
            executable="/Applications/qemu-g3/Qemu-system-ppc GUI.app/Contents/MacOS/Qemu-system-ppc GUI",
            source_root="/nowhere")
        self.assertEqual(got, Path("/Applications/qemu-g3"))

    def test_frozen_bundle_nested_deeper(self):
        got = paths.resolve_install_dir(
            frozen=True,
            executable="/Users/hsp/qemu/Qemu-system-ppc GUI.app/Contents/MacOS/sub/Qemu-system-ppc GUI",
            source_root="/nowhere")
        self.assertEqual(got, Path("/Users/hsp/qemu"))

    def test_frozen_windows_executable(self):
        got = paths.resolve_install_dir(frozen=True,
                                        executable="/c/qemu-g3/Qemu-system-ppc GUI.exe",
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
        exe = self.install / "Qemu-system-ppc GUI.app" / "Contents" / "MacOS" / "Qemu-system-ppc GUI"
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
        self.assertEqual(sorted(p.name for p in (self.install / "Qemu-system-ppc GUI.app").rglob("*")),
                         ["Contents", "MacOS", "Qemu-system-ppc GUI"])

    def test_a_frozen_bundle_without_the_emulator_still_refuses(self):
        (self.install / paths.qemu_binary_name()).unlink()
        problem = paths.startup_problem()
        self.assertIsNotNone(problem)
        # the message is one short line and names no folder, so assert the thing
        # that actually matters here: the folder it resolved is the one holding
        # the bundle, not somewhere inside it.
        self.assertEqual(paths.install_dir(), self.install)
        self.assertNotIn(".app", str(paths.install_dir()))


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
        self.assertNotIn("Traceback", message)
        # the user asked for one short line, not an explanation (2026-09-05)
        self.assertEqual(len(message.strip().splitlines()), 1)
        self.assertLess(len(message.strip()), 100)

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

    def test_nothing_offers_to_choose_a_folder(self):
        source = "\n".join((ROOT / "qemu_gui.py").read_text().splitlines()
                           + [(ROOT / "qemugui" / f).read_text()
                              for f in ("paths.py", "model.py", "command.py")])
        self.assertNotIn("askdirectory", source)
        for gone in ("library_dir", "qemu_dir_var", "discover_qemu_dir", "QEMU_DIR_CANDIDATES",
                     "BROWSE_FALLBACKS", "default_library_dir"):
            self.assertNotIn(gone, source, gone)


class TheEditorFillsNothingIn(unittest.TestCase):
    """A source-level guard for the rule the user restated on 2026-09-05: the
    editor must not put a file into a field by itself. The record-level proof
    is in test_command.NothingIsChosenForYou; this catches the interface
    growing a new "helpful" default later."""

    def test_the_editor_has_no_pre_filling_left_in_it(self):
        src = (ROOT / "qemugui" / "ui_machine.py").read_text()
        for gone in ("SecondGpu().romfile",          # seeded the card ROM
                     "_reapply_profile",             # re-applied a system's files
                     "PowerMacG3v3"):                # a ROM name as a value
            self.assertNotIn(gone, src, gone)

    def test_no_system_carries_a_file_to_seed(self):
        from qemugui import systems
        for p in systems.SYSTEMS.values():
            for value in vars(p).values():
                self.assertNotIn(".rom", str(value).lower(), f"{p.id}: {value}")


class TheWindowSaysWhatTheUserAskedItToSay(unittest.TestCase):
    """The interface list of 2026-09-05, checked at source level: these tests
    run headless, so they read the two interface modules rather than build a
    window. They exist so a later change cannot quietly bring back a wording
    or a control the user asked to be rid of."""

    def setUp(self):
        self.main = (ROOT / "qemugui" / "ui_main.py").read_text()
        self.editor = (ROOT / "qemugui" / "ui_machine.py").read_text()
        self.dialogs = (ROOT / "qemugui" / "ui_dialogs.py").read_text()

    def test_the_command_line_is_labelled_and_unexplained(self):
        self.assertIn("Command line constructed:", self.main)
        self.assertNotIn("What Start will run", self.main)
        self.assertNotIn("This is exactly", self.main)

    def test_no_paragraph_where_a_machine_has_not_been_chosen(self):
        self.assertNotIn("No machine chosen yet", self.main)

    def test_the_last_run_messages_section_is_gone_from_the_window(self):
        for gone in ("Messages from the last time", "log_tail", "self.log = tk.Text",
                     "only worth reading if something went wrong"):
            self.assertNotIn(gone, self.main, gone)
        # the launcher still keeps the emulator's output in the machine folder
        self.assertIn('LOG_NAME = "last-run.log"', self.main)
        self.assertIn("stdout=log_fh", self.main)

    def test_the_buttons_are_named_the_way_the_user_named_them(self):
        for wanted in ('"Duplicate"', '"Edit"', '"Open machine folder"'):
            self.assertIn(wanted, self.main, wanted)
        for gone in ("Make a copy", "Change this machine", "Open its folder",
                     "Forget saved settings", "clear_saved_settings"):
            self.assertNotIn(gone, self.main, gone)

    def test_there_is_no_new_machine_dialogue_left(self):
        for src in (self.main, self.editor, self.dialogs):
            self.assertNotIn("NewMachineDialog", src)
        for gone in ("What would you like to call it", "Which system are you going to run",
                     "This only sets the memory and the graphics card"):
            self.assertNotIn(gone, self.dialogs, gone)
        # it opens the settings window itself, on the Machine page
        self.assertIn("is_new=True", self.main)
        self.assertIn("self.nb.select(0)", self.editor)
        # and the Machine page keeps its plain labels, without the explanations
        self.assertIn('text="Name:"', self.editor)
        self.assertIn('text="System:"', self.editor)

    def test_a_file_field_can_be_typed_into(self):
        picker = self.editor[self.editor.index("class FilePicker:"):
                             self.editor.index("class DriveRow:")]
        self.assertNotIn("readonly", picker)            # it was a read-only field
        # the entry is the record's own variable, so what is typed is what is kept
        self.assertIn("ttk.Entry(master, textvariable=var, width=width)", picker)
        self.assertIn("<Double-Button-1>", picker)      # browsing is still there
        # and it carries no grey instructions inside it
        self.assertNotIn("Type or paste a path", picker)
        self.assertNotIn("PLACEHOLDER", picker)


class NothingOnScreenIsAParagraph(unittest.TestCase):
    """The rule the user set on 2026-09-05: "Good grief, this GUI is no
    wikipedia or help file." Nothing on screen explains, teaches, reassures or
    describes -- only labels, buttons, chooser entries, short status lines, and
    one short sentence when something actually fails.

    This walks every string literal the interface and the record layer can put
    in front of a person (docstrings and comments excluded, since they never
    reach the screen) and holds it to two limits: one sentence, and short.
    """

    UI = ("qemugui/ui_main.py", "qemugui/ui_machine.py", "qemugui/ui_dialogs.py",
          "qemugui/model.py", "qemugui/systems.py", "qemu_gui.py")
    STARTUP = ("qemugui/paths.py",)          # two startup failures, one line each
    SENTENCE_BREAK = re.compile(r"[.?!]\s+[A-Z(\u201c]")

    def literals(self, relpath: str):
        """Every string constant in the file that is not a docstring."""
        tree = ast.parse((ROOT / relpath).read_text())
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                        ast.ClassDef))
                      and ast.get_docstring(n, clean=False) is not None}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings):
                yield node.lineno, node.value

    def test_no_string_runs_to_a_second_sentence(self):
        offenders = [f"{f}:{line} {text!r}"
                     for f in self.UI + self.STARTUP
                     for line, text in self.literals(f)
                     if self.SENTENCE_BREAK.search(text) and "\n" not in text]
        # the launcher's own header comment is the one two-sentence string left
        self.assertEqual(offenders, [])

    # Short lines that exist to stop a person losing time or data. The user
    # asked for each one by name; anything not here has to fit in 60 chars.
    PROTECTIVE = ("Boot order: floppy",)

    def test_no_string_is_long_enough_to_be_a_paragraph(self):
        offenders = [f"{f}:{line} {text!r}"
                     for f in self.UI
                     for line, text in self.literals(f)
                     if len(text) > 60
                     and not text.startswith(self.PROTECTIVE)]
        self.assertEqual(offenders, [])

    def test_the_protective_lines_are_still_one_sentence(self):
        for f in self.UI:
            for _, text in self.literals(f):
                if text.startswith(self.PROTECTIVE):
                    self.assertLess(len(text), 130, text)
                    self.assertEqual(text.count("."), 1, text)

    def test_the_startup_failures_are_one_short_line_each(self):
        """The two messages shown before the window exists: one line each, no
        instructions for putting it right."""
        for text in (paths.MISSING_QEMU_MESSAGE, paths.UNWRITABLE_MESSAGE,
                     qemu_gui.NO_TKINTER):
            self.assertLess(len(text), 100, text)
            self.assertEqual(len(text.strip().splitlines()), 1, text)

    def test_the_grey_explanations_are_gone_by_name(self):
        """Positive control for the two tests above: these are the exact
        strings that were on screen before, one per screen that had one."""
        sources = "\n".join((ROOT / f).read_text() for f in self.UI)
        for gone in ("Machines are kept in",                 # main window footer
                     "The Mac has not saved any settings",   # main window, grey
                     "Type or paste a path",                 # every file field
                     "This Mac always has its own graphics",  # Display
                     "much happier with a proper graphics card",
                     "ati_nexus128_103_pci.rom",             # Display, grey hint
                     "The Mac has room for four drives",     # Drives, intro
                     "This Mac also has a SCSI chain",       # Drives, SCSI
                     "Pretend\u201d makes the drive",           # Drives, footnote
                     "How the old Mac reaches the outside world",   # Network
                     "The Mac can reach the internet through",      # NET_HINTS
                     "never seen by this program",           # SUDO_HINT
                     "Remote Desktop",                       # Sound
                     "Nothing on this page needs changing",  # Advanced
                     "Added to the end of the command",      # Advanced
                     "In gigabytes",                         # New hard disk
                     "is a plain disk",                      # New hard disk
                     "Also worth knowing",                   # save validation
                     "A disk image is never deleted here"):  # delete confirmation
            self.assertNotIn(gone, sources, gone)


class DeleteNeverTouchesADiskImage(unittest.TestCase):
    """A disk image can be hours of installing an operating system. Deleting
    a machine removes the record, the launcher and the saved settings, and
    nothing else."""

    def machine_with_images(self, root: Path) -> tuple[model.Library, Path, dict]:
        lib = model.Library(root)
        m = model.new_machine("Mac OS 9", "macos_8_to_9")
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
            lib.save(model.new_machine("Empty", "other"))
            folder = lib.folder("Empty")
            (folder / "nvram.img").write_bytes(b"\0" * 8192)
            result = lib.delete("Empty")
            self.assertTrue(result.folder_removed)
            self.assertFalse(folder.exists())
            self.assertEqual(result.kept, [])

    def test_an_image_in_a_subfolder_is_kept_too(self):
        with tempfile.TemporaryDirectory() as td:
            lib = model.Library(Path(td))
            lib.save(model.new_machine("Sub", "other"))
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
            self.assertIn("Mac OS 9.img", why)          # it names the file it will not touch
            target, why = model.check_new_image_path(folder, "Mac OS 9", "qcow2")
            self.assertEqual(target, folder / "Mac OS 9.qcow2")
            self.assertIsNone(why)
            target, why = model.check_new_image_path(folder, "a/b", "raw")
            self.assertIsNone(target)
            self.assertIn("slashes", why)
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


class TheSecondScreenIsOptional(unittest.TestCase):
    """The extra card and its ROM are optional, so neither may be complained
    about, and the only card offered is the Rage 128 (user, 2026-09-05)."""

    def test_no_card_and_no_card_rom_are_both_silent(self):
        m = model.new_machine("t", "macos_8_to_9")
        m.rom = "rom.bin"
        errors, warnings = model.validate(m, "darwin", check_files=False)
        self.assertFalse([w for w in warnings if "card" in w.lower()], warnings)
        m.second_gpu = model.SecondGpu("ati-rage128-pro", "0x0e", None)
        errors, warnings = model.validate(m, "darwin", check_files=False)
        self.assertFalse([w for w in warnings if "card" in w.lower()], warnings)
        self.assertFalse([e for e in errors if "card" in e.lower()], errors)

    def test_the_display_tab_offers_no_card_chooser(self):
        src = (Path(__file__).resolve().parent.parent / "qemugui" / "ui_machine.py").read_text()
        for gone in ("GPU_CHOICES", "GPU_SEPARATOR", "Card:", "Extra graphics card"):
            self.assertNotIn(gone, src)
        for kept in ("Enable dual screen", "Ati Rage 128 ROM:",
                     "Built-in ATI Mach64 GT", "Use built-in ROM", "Select ROM"):
            self.assertIn(kept, src)


def _tk_available():
    try:
        import tkinter
        r = tkinter.Tk(); r.withdraw(); r.destroy(); return True
    except Exception:
        return False


@unittest.skipUnless(_tk_available(), "no display")
class SavingKeepsEverything(unittest.TestCase):
    """collect() once lost the drives, network, sound and advanced settings
    without a single test noticing (2026-09-05). It returns a whole record
    or this fails."""

    def test_every_part_of_the_record_survives_a_round_trip(self):
        import tkinter as tk
        from qemugui.ui_machine import MachineEditor
        with tempfile.TemporaryDirectory() as d:
            lib = model.Library(Path(d))
            m = model.new_machine("Round trip", "macos_8_to_9")
            m.rom = "rom.bin"
            m.ata[0] = model.AtaDrive("disk", "/disks/hd.img", "raw")
            m.ata[2] = model.AtaDrive("cdrom", "/disks/cd.iso", "raw")
            m.scsi = [model.ScsiDrive(3, "cdrom", "/disks/scsi.iso", "raw", None)]
            m.floppy = model.Floppy("/disks/fd.img", "raw")
            m.network = model.Network("user", "00:05:02:12:34:56", "")
            m.audio = "none"
            m.governor = model.Governor("mips", 200)
            m.extra_args = "-serial stdio"
            m.notes = "keep me"
            root = tk.Tk(); root.withdraw()
            try:
                ed = MachineEditor(root, m, lib, d, on_save=lambda *a: None)
                ed.withdraw()
                got = ed.collect()
            finally:
                root.destroy()
        self.assertIsNotNone(got, "collect() returned nothing")
        self.assertEqual(got.rom, "rom.bin")
        self.assertEqual(got.ata[0].file, "/disks/hd.img")
        self.assertEqual(got.ata[2].kind, "cdrom")
        self.assertEqual([s.id for s in got.scsi], [3])
        self.assertEqual(got.floppy.file, "/disks/fd.img")
        self.assertEqual(got.network.mode, "user")          # not its screen label
        self.assertEqual(got.network.mac, "00:05:02:12:34:56")
        self.assertEqual(got.audio, "none")
        self.assertEqual(got.governor.mode, "mips")
        self.assertEqual(got.governor.mips, 200)
        self.assertEqual(got.extra_args, "-serial stdio")
        self.assertEqual(got.notes, "keep me")


@unittest.skipUnless(_tk_available(), "no display")
class TheCreateDiskButton(unittest.TestCase):
    """It shells out to qemu-img, so it greys out when that is not beside
    the emulator, and says why (user, 2026-09-05)."""

    def _editor_state(self, with_qemu_img: bool):
        import tkinter as tk
        from qemugui import paths
        from qemugui.ui_machine import MachineEditor
        with tempfile.TemporaryDirectory() as d:
            install = Path(d)
            (install / paths.qemu_binary_name()).write_text("#!/bin/sh\n")
            if with_qemu_img:
                (install / paths.qemu_img_name()).write_text("#!/bin/sh\n")
            lib = model.Library(install / "Machines")
            m = model.new_machine("t", "macos_8_to_9")
            root = tk.Tk(); root.withdraw()
            old = paths.install_dir
            paths.install_dir = lambda: install
            try:
                ed = MachineEditor(root, m, lib, str(install), on_save=lambda *a: None)
                ed.withdraw()
                buttons = [w for w in self._walk(ed)
                           if w.winfo_class() == "TButton"
                           and "Create new disk" in str(w.cget("text"))]
                labels = [str(w.cget("text")) for w in self._walk(ed)
                          if w.winfo_class() == "TLabel"]
                return str(buttons[0].cget("state")), labels
            finally:
                paths.install_dir = old
                root.destroy()

    @staticmethod
    def _walk(w):
        yield w
        for c in w.winfo_children():
            yield from TheCreateDiskButton._walk(c)

    def test_greyed_out_and_labelled_when_qemu_img_is_missing(self):
        state, labels = self._editor_state(with_qemu_img=False)
        self.assertEqual(state, "disabled")
        self.assertTrue(any("not found" in l for l in labels), labels)

    def test_enabled_when_qemu_img_is_there(self):
        state, labels = self._editor_state(with_qemu_img=True)
        self.assertEqual(state, "normal")
        self.assertFalse(any("not found" in l for l in labels), labels)


class TheSecondScreenIsOptIn(unittest.TestCase):
    """Nothing fits the extra card for you: a new machine has none, whichever
    system is chosen (user, 2026-09-05)."""

    def test_no_system_fits_the_card(self):
        from qemugui import systems
        for sysid in [s.id for s in systems.SYSTEMS.values()]:
            m = model.new_machine("t", sysid)
            self.assertIsNone(m.second_gpu, sysid)
