"""The main window: the list of machines, the command line Start will run,
and Start.

``start_machine()`` is the one code path that launches the emulator: it
writes the launcher file and then runs the argument list directly with the
machine's own folder as the working directory, so the Mac's saved settings
(nvram.img, pram.img) land there.

The emulator is always the one sitting beside this program: ``qemu_dir()``
below is the only place that is decided, and it is decided by
``paths.install_dir()``.
"""

from __future__ import annotations

import subprocess
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

from . import command, model, paths
from .model import Machine, Library
from .paths import Settings
from .systems import SYSTEMS, system_ids
from .ui_dialogs import ask_name, confirm_delete, report_delete, open_folder
from .ui_machine import MachineEditor

APP_TITLE = "Qemu-system-ppc GUI"

# The emulator's own output still goes into the machine's folder; the window
# no longer shows any of it.
LOG_NAME = "last-run.log"


def qemu_dir() -> str:
    """The folder this program is installed in, which is the folder the
    emulator is in. There is nothing to configure."""
    return str(paths.install_dir())


class RunningMachine:
    def __init__(self, name: str, proc: subprocess.Popen, log_path: Path, argv: list[str], log_fh):
        self.name = name
        self.proc = proc
        self.log_path = log_path
        self.argv = argv
        self.started = time.time()
        self._log_fh = log_fh
        self.exit_code: int | None = None

    @property
    def pid(self) -> int:
        return self.proc.pid

    def poll(self) -> int | None:
        rc = self.proc.poll()
        if rc is not None and self.exit_code is None:
            self.exit_code = rc
            try:
                self._log_fh.close()
            except OSError:
                pass
        return rc

    def uptime(self) -> float:
        return time.time() - self.started


TERMINAL_STATUS = "Started in a Terminal window, which will ask for your password"


def start_in_terminal(m: Machine, machine_dir: Path) -> Path:
    """Joining the real network needs an administrator password, and only a
    Terminal window can ask for one. Write the launcher and let Terminal run
    it; the password is never seen here, and this run cannot be followed."""
    machine_dir = Path(machine_dir)
    machine_dir.mkdir(parents=True, exist_ok=True)
    launcher, _argv = command.write_launcher(m, qemu_dir(), str(machine_dir))
    subprocess.Popen(["open", "-a", "Terminal", str(launcher)], cwd=str(machine_dir))
    return launcher


def start_machine(m: Machine, machine_dir: Path) -> RunningMachine:
    """Write the launcher, then run it with the machine folder as the
    working directory, keeping everything it prints in last-run.log."""
    machine_dir = Path(machine_dir)
    machine_dir.mkdir(parents=True, exist_ok=True)
    _launcher, argv = command.write_launcher(m, qemu_dir(), str(machine_dir))
    log_path = machine_dir / LOG_NAME
    log_fh = open(log_path, "w", encoding="utf-8")
    log_fh.write("# " + " ".join(argv) + "\n")
    log_fh.flush()
    proc = subprocess.Popen(argv, cwd=str(machine_dir), stdout=log_fh, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL)
    return RunningMachine(m.name, proc, log_path, argv, log_fh)


class MainWindow(tk.Tk):
    def __init__(self, settings: Settings, settings_path: Path | None = None):
        super().__init__()
        self.settings = settings
        self.settings_path = settings_path or paths.settings_path()
        self.library = Library()
        self.library.ensure()
        self.running: dict[str, RunningMachine] = {}
        self.finished: dict[str, RunningMachine] = {}
        self.terminal_started: dict[str, float] = {}
        self.title(APP_TITLE)
        self.geometry("1100x680")
        self.minsize(880, 520)
        self._build()
        self.refresh_list(select=settings.last_machine)
        self.after(1000, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._quit)

    # ---------------- layout
    def _build(self):
        menubar = tk.Menu(self)
        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="New machine…", command=self.new_machine)
        filem.add_command(label="Open the Machines folder", command=self.open_machines_folder)
        filem.add_separator()
        filem.add_command(label="Quit", command=self._quit)
        menubar.add_cascade(label="File", menu=filem)
        self.config(menu=menubar)

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        ttk.Label(left, text="Your machines").pack(anchor="w")
        self.tree = ttk.Treeview(left, columns=("machine", "state"), show="headings",
                                 selectmode="browse", height=18)
        self.tree.heading("machine", text="Machine")
        self.tree.heading("state", text="")
        self.tree.column("machine", width=240, anchor="w")
        self.tree.column("state", width=80, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.on_select())
        self.tree.bind("<Double-1>", lambda _e: self.edit_machine())

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(6, 0))
        spec = [("New machine…", self.new_machine),
                ("Duplicate", self.duplicate_machine),
                ("Edit", self.edit_machine),
                ("Delete…", self.delete_machine),
                ("Open machine folder", self.open_machine_folder)]
        for i, (label, cmd) in enumerate(spec):
            ttk.Button(btns, text=label, command=cmd).grid(
                row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
        self.start_button = ttk.Button(btns, text="Start this Mac", command=self.start_selected)
        self.start_button.grid(row=(len(spec) + 1) // 2, column=0, columnspan=2, sticky="ew",
                               padx=2, pady=(8, 2))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        right = ttk.Frame(pane)
        pane.add(right, weight=3)
        self.run_status = ttk.Label(right, text="", justify="left", font=("", 0, "bold"))
        self.run_status.pack(anchor="w")
        self.status = ttk.Label(right, text="", foreground="gray", justify="left")
        self.status.pack(anchor="w", pady=(2, 6))

        ttk.Label(right, text="Command line constructed:").pack(anchor="w", pady=(8, 0))
        self.command_line = tk.Text(right, height=14, wrap="none", font=self._mono(11))
        self.command_line.pack(fill="both", expand=True)
        self.command_line.config(state="disabled")

        ttk.Label(right, text="My notes").pack(anchor="w", pady=(8, 0))
        self.notes = tk.Text(right, height=6, wrap="word")
        self.notes.pack(fill="x")
        self.notes.config(state="disabled")

        foot = ttk.Label(self, foreground="gray", justify="left",
                         text=f"Machines are kept in {paths.machines_dir()}\n"
                              f"Emulator: {paths.qemu_binary()}")
        foot.pack(anchor="w", padx=8, pady=(0, 6))

    @staticmethod
    def _mono(size: int):
        return ("Menlo", size) if paths.HOST_PLATFORM == "darwin" else ("Consolas", size - 1)

    @staticmethod
    def _set_text(widget: tk.Text, text: str):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    # ---------------- list / selection
    def refresh_list(self, select: str | None = None):
        current = select or self.selected_name()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for m in self.library.load_all():
            state = "running" if m.name in self.running else ""
            self.tree.insert("", "end", iid=m.name,
                             values=(f"{m.name}   ({SYSTEMS[m.system].label})", state))
        names = self.library.names()
        if current in names:
            self.tree.selection_set(current)
            self.tree.see(current)
        elif names:
            self.tree.selection_set(names[0])
        self.on_select()

    def selected_name(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def selected_machine(self) -> Machine | None:
        name = self.selected_name()
        if not name:
            return None
        try:
            return self.library.load(name)
        except (OSError, ValueError, KeyError, TypeError) as e:
            messagebox.showerror(APP_TITLE, f"The settings for “{name}” could not be "
                                             f"read, so it cannot be opened.\n\n{e}")
            return None

    def on_select(self):
        name = self.selected_name()
        if name:
            self.settings.last_machine = name
            self._save_settings()
        self.refresh_details()

    def refresh_details(self):
        """The right-hand side: how it ran, where it is kept, the command
        line Start will run, and the notes."""
        m = self.selected_machine()
        if not m:
            self._set_text(self.command_line, "")
            self.status.config(text="")
            self._set_text(self.notes, "")
            self.run_status.config(text="")
            self.start_button.state(["disabled"])
            return
        self.start_button.state(["!disabled"])
        folder = self.library.folder(m.name)
        try:
            text = command.launcher_text(m, qemu_dir(), str(folder))
        except Exception as e:      # never let one bad record blank the window
            text = f"(this machine's settings could not be turned into a command: {e})"
        self._set_text(self.command_line, text)
        saved = self.library.saved_settings_status(m.name)
        if any(v is not None for v in saved.values()):
            first = "The Mac has settings of its own saved from an earlier run."
        else:
            first = ("The Mac has not saved any settings of its own yet; it will the first "
                     "time you start it.")
        self.status.config(text=f"{first}\nKept in {folder}")
        self._set_text(self.notes, m.notes)
        self._refresh_run_status(m.name)

    def _refresh_run_status(self, name: str):
        r = self.running.get(name) or self.finished.get(name)
        if not r:
            if name in self.terminal_started:
                when = time.strftime("%H:%M", time.localtime(self.terminal_started[name]))
                self.run_status.config(text=f"{TERMINAL_STATUS} (at {when}).")
            else:
                self.run_status.config(text="Not running.")
            return
        if r.exit_code is None:
            self.run_status.config(text=f"Running now — {self._duration(r.uptime())} so far.")
        elif r.exit_code == 0:
            self.run_status.config(text=f"Stopped, after {self._duration(r.uptime())}.")
        else:
            self.run_status.config(
                text=f"Stopped after {self._duration(r.uptime())}. Something went wrong "
                     f"(code {r.exit_code}); {LOG_NAME} in the machine's folder says what.")

    @staticmethod
    def _duration(seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return f"{s} second{'' if s == 1 else 's'}"
        if s < 3600:
            return f"{s // 60} minute{'' if s // 60 == 1 else 's'}"
        return f"{s // 3600} hour{'' if s // 3600 == 1 else 's'} {(s % 3600) // 60} min"

    # ---------------- actions
    def new_machine(self):
        """No separate dialogue: the settings window opens on the Machine
        page with an empty Name and the System list, and the machine comes
        into being when it is saved. Cancel, and nothing has been made."""
        m = model.new_machine("", system_ids()[0])
        MachineEditor(self, m, self.library, qemu_dir(), self._on_editor_save, is_new=True)

    def duplicate_machine(self):
        name = self.selected_name()
        if not name:
            return
        new_name = ask_name(
            self, "Duplicate",
            "Name for the duplicate.\n\nThe copy starts out using the same hard disk and CD files "
            "as the original: nothing is copied and nothing is duplicated on your disk. Do "
            "not run both machines at the same time.",
            f"{name} copy", self.library.names())
        if not new_name:
            return
        try:
            m = self.library.duplicate(name, new_name)
        except (OSError, ValueError) as e:
            messagebox.showerror("Duplicate", str(e))
            return
        self._write_launcher(m)
        self.refresh_list(select=new_name)

    def delete_machine(self):
        name = self.selected_name()
        if not name:
            return
        if name in self.running and self.running[name].poll() is None:
            messagebox.showwarning("Delete", f"“{name}” is running. Shut the Mac down "
                                             "from inside its own window first.")
            return
        will_go, will_stay = self.library.delete_preview(name)
        if not confirm_delete(self, name, will_go, will_stay, self.library.folder(name)):
            return
        result = self.library.delete(name)
        self.finished.pop(name, None)
        self.terminal_started.pop(name, None)
        self.refresh_list()
        report_delete(self, name, result)

    def edit_machine(self):
        m = self.selected_machine()
        if not m:
            return
        if m.name in self.running and self.running[m.name].poll() is None:
            messagebox.showinfo("Edit",
                                f"“{m.name}” is running. Anything you change now will "
                                "apply the next time you start it, not straight away.")
        MachineEditor(self, m, self.library, qemu_dir(), self._on_editor_save)

    def _on_editor_save(self, m: Machine, old_name: str):
        if old_name != m.name and old_name in self.running:
            raise ValueError("A machine cannot be renamed while it is running.")
        self.library.save(m, old_name=old_name)
        if old_name != m.name:
            self.finished.pop(old_name, None)
        self._write_launcher(m)
        self.refresh_list(select=m.name)

    def _write_launcher(self, m: Machine):
        try:
            command.write_launcher(m, qemu_dir(), str(self.library.folder(m.name)))
        except OSError as e:
            messagebox.showerror(APP_TITLE, "The start-up file for this machine could not be "
                                             f"written.\n\n{e}")

    def open_machine_folder(self):
        name = self.selected_name()
        if name:
            open_folder(self.library.folder(name))

    def open_machines_folder(self):
        self.library.ensure()
        open_folder(self.library.root)

    def start_selected(self) -> RunningMachine | None:
        """The Start button. Returns the RunningMachine, or None if it did
        not start."""
        m = self.selected_machine()
        if not m:
            return None
        r = self.running.get(m.name)
        if r and r.poll() is None:
            messagebox.showwarning("Start", f"“{m.name}” is already running. Shut the "
                                            "Mac down from inside its own window first.")
            return None
        errors, _warnings = model.validate(m, qemu_dir(),
                                           machine_dir=str(self.library.folder(m.name)))
        errors += model.start_blockers(m)
        if errors:
            messagebox.showerror("Start", "This machine cannot start yet:\n\n" +
                                 "\n".join(f"• {e}" for e in errors) +
                                 "\n\nPress “Edit” to put it right.")
            return None
        if command.needs_sudo(m):
            if paths.HOST_PLATFORM != "darwin":
                messagebox.showerror("Start", "This machine is set to join the real network the "
                                              "way only a Mac can. Change its network setting "
                                              "first.")
                return None
            try:
                start_in_terminal(m, self.library.folder(m.name))
            except OSError as e:
                messagebox.showerror("Start", f"A Terminal window could not be opened.\n\n{e}")
                return None
            self.terminal_started[m.name] = time.time()
            self.finished.pop(m.name, None)
            self.refresh_list(select=m.name)
            return None
        try:
            r = start_machine(m, self.library.folder(m.name))
        except OSError as e:
            messagebox.showerror("Start", f"The Mac could not be started.\n\n{e}")
            return None
        self.running[m.name] = r
        self.finished.pop(m.name, None)
        self.refresh_list(select=m.name)
        return r

    def _poll(self):
        changed = False
        for name, r in list(self.running.items()):
            if r.poll() is not None:
                self.finished[name] = r
                del self.running[name]
                changed = True
        if changed:
            self.refresh_list()
        else:
            sel = self.selected_name()
            if sel and (sel in self.running or sel in self.finished):
                self._refresh_run_status(sel)
        self.after(1000, self._poll)

    # ---------------- housekeeping
    def _save_settings(self):
        try:
            self.settings.save(self.settings_path)
        except OSError:
            pass

    def _quit(self):
        self._save_settings()
        if self.running:
            names = ", ".join(self.running)
            if not messagebox.askyesno(
                    "Quit",
                    f"These Macs are still running: {names}.\n\nThey keep running if you quit "
                    "this program; shut them down from inside their own windows to be safe.\n\n"
                    "Quit anyway?"):
                return
        self.destroy()
