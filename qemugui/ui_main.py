"""Main window: machine list, overview of the generated launcher, Start.

``start_machine()`` is the one code path that launches QEMU: it writes the
launcher file and then runs the argv list directly with the machine folder
as cwd (so nvram.img / pram.img land there). The smoke test drives
``MainWindow.start_selected()`` which calls it.
"""

from __future__ import annotations

import subprocess
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

from . import command, model, paths
from .model import Machine, Library
from .paths import Settings
from .profiles import PROFILES
from .ui_dialogs import (NewMachineDialog, ask_name, confirm_delete, confirm_reset_nvram,
                         reveal_folder)
from .ui_machine import MachineEditor

LOG_NAME = "last-run.log"
LOG_TAIL = 20
BAD_LOG_PATTERNS = ("invalid option", "could not open", "not found", "not a valid",
                    "Unknown", "error")


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

    def log_tail(self, n: int = LOG_TAIL) -> list[str]:
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as fh:
                return [ln.rstrip("\n") for ln in deque(fh, maxlen=n)]
        except OSError:
            return []


def start_machine(m: Machine, machine_dir: Path, qemu_dir: str) -> RunningMachine:
    """Write the launcher, then Popen(argv, cwd=machine_dir) with output to last-run.log."""
    machine_dir = Path(machine_dir)
    machine_dir.mkdir(parents=True, exist_ok=True)
    _launcher, argv = command.write_launcher(m, qemu_dir, str(machine_dir))
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
        self.settings_path = settings_path
        self.library = Library(settings.library_dir)
        self.running: dict[str, RunningMachine] = {}
        self.finished: dict[str, RunningMachine] = {}
        self.title("Qemu-GUI -- PowerMac G3 (g3beige)")
        self.geometry("1100x640")
        self.minsize(860, 480)
        self._build()
        self.refresh_list(select=settings.last_machine)
        self.after(1000, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._quit)

    # ---------------- layout
    def _build(self):
        menubar = tk.Menu(self)
        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="New machine...", command=self.new_machine)
        filem.add_command(label="Settings (library + QEMU folder)...", command=self.edit_settings)
        filem.add_separator()
        filem.add_command(label="Quit", command=self._quit)
        menubar.add_cascade(label="File", menu=filem)
        self.config(menu=menubar)

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        self.tree = ttk.Treeview(left, columns=("profile", "state"), show="headings", selectmode="browse", height=18)
        self.tree.heading("profile", text="Machine / profile")
        self.tree.heading("state", text="State")
        self.tree.column("profile", width=220, anchor="w")
        self.tree.column("state", width=90, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.on_select())
        self.tree.bind("<Double-1>", lambda _e: self.edit_machine())

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(6, 0))
        spec = [("New", self.new_machine), ("Duplicate", self.duplicate_machine),
                ("Delete", self.delete_machine), ("Edit", self.edit_machine),
                ("Reset NVRAM/PRAM", self.reset_nvram), ("Reveal folder", self.reveal),
                ("Start", self.start_selected)]
        for i, (label, cmd) in enumerate(spec):
            b = ttk.Button(btns, text=label, command=cmd)
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
            if label == "Start":
                self.start_button = b
                b.grid(columnspan=2, sticky="ew")
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        right = ttk.Frame(pane)
        pane.add(right, weight=3)
        ttk.Label(right, text="Overview: the launcher exactly as it is written to the machine folder").pack(anchor="w")
        self.overview = tk.Text(right, height=16, wrap="none", font=("Menlo", 11) if paths.HOST_PLATFORM == "darwin" else ("Consolas", 10))
        self.overview.pack(fill="both", expand=True)
        self.overview.config(state="disabled")
        self.status = ttk.Label(right, text="", foreground="gray", justify="left")
        self.status.pack(anchor="w", pady=(4, 0))
        self.run_status = ttk.Label(right, text="", justify="left")
        self.run_status.pack(anchor="w")
        ttk.Label(right, text="Notes").pack(anchor="w", pady=(6, 0))
        self.notes = tk.Text(right, height=4, wrap="word")
        self.notes.pack(fill="x")
        self.notes.config(state="disabled")
        ttk.Label(right, text="Last run log (tail)").pack(anchor="w", pady=(6, 0))
        self.log = tk.Text(right, height=7, wrap="none", font=("Menlo", 10) if paths.HOST_PLATFORM == "darwin" else ("Consolas", 9))
        self.log.pack(fill="x")
        self.log.config(state="disabled")

    @staticmethod
    def _set_text(widget: tk.Text, text: str):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    # ---------------- list / selection
    def refresh_list(self, select: str | None = None):
        self.library = Library(self.settings.library_dir)
        current = select or self.selected_name()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for m in self.library.load_all():
            state = "running" if m.name in self.running else ""
            self.tree.insert("", "end", iid=m.name,
                             values=(f"{m.name}  ({PROFILES[m.profile].label})", state))
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
            messagebox.showerror("machine.json", f"Cannot read {name}/machine.json:\n{e}")
            return None

    def on_select(self):
        name = self.selected_name()
        if name:
            self.settings.last_machine = name
            self._save_settings()
        self.refresh_overview()

    def refresh_overview(self):
        m = self.selected_machine()
        if not m:
            self._set_text(self.overview, "(no machine selected: File > New machine...)")
            self.status.config(text="")
            self._set_text(self.notes, "")
            self._set_text(self.log, "")
            self.run_status.config(text="")
            return
        folder = self.library.folder(m.name)
        qd = m.effective_qemu_dir(self.settings.qemu_dir)
        try:
            text = command.launcher_text(m, self.settings.qemu_dir, str(folder))
        except Exception as e:  # never let a bad record blank the window
            text = f"(cannot render launcher: {e})"
        self._set_text(self.overview, text)
        st = self.library.managed_status(m.name)
        parts = []
        for f, size in st.items():
            parts.append(f"{f}: present, {size} bytes" if size is not None else f"{f}: absent")
        parts.append("QEMU binary: " + ("found" if paths.has_qemu(qd) else "MISSING") + f" ({qd or 'no QEMU folder set'})")
        parts.append(f"folder: {folder}")
        self.status.config(text="\n".join(parts))
        self._set_text(self.notes, m.notes)
        self._refresh_run_status(m.name)

    def _refresh_run_status(self, name: str):
        r = self.running.get(name) or self.finished.get(name)
        if not r:
            self.run_status.config(text="not running")
            self._set_text(self.log, "")
            return
        if r.exit_code is None:
            self.run_status.config(text=f"running, pid {r.pid}, up {int(r.uptime())} s")
        else:
            self.run_status.config(text=f"exited with code {r.exit_code} (pid {r.pid}, ran {int(r.uptime())} s)")
        self._set_text(self.log, "\n".join(r.log_tail()))

    # ---------------- actions
    def new_machine(self):
        dlg = NewMachineDialog(self, self.library.names())
        if not dlg.result:
            return
        name, profile_id = dlg.result
        m = model.new_machine(name, profile_id, self.settings.qemu_dir)
        self.library.save(m)
        self._write_launcher(m)
        self.refresh_list(select=name)
        self.edit_machine()

    def duplicate_machine(self):
        name = self.selected_name()
        if not name:
            return
        new_name = ask_name(self, "Duplicate machine", "Name for the copy (machine.json, nvram and pram "
                            "are copied; disk images are shared, not copied):", f"{name} copy",
                            self.library.names())
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
            messagebox.showwarning("Delete", f"'{name}' is running; shut it down from inside the guest first.")
            return
        if not confirm_delete(self, name, self.library.folder_contents(name)):
            return
        self.library.delete(name)
        self.finished.pop(name, None)
        self.refresh_list()

    def edit_machine(self):
        m = self.selected_machine()
        if not m:
            return
        if m.name in self.running and self.running[m.name].poll() is None:
            messagebox.showinfo("Edit", f"'{m.name}' is running; changes apply to the next start.")
        MachineEditor(self, m, self.library, self.settings.qemu_dir, self._on_editor_save)

    def _on_editor_save(self, m: Machine, old_name: str):
        if old_name != m.name and old_name in self.running:
            raise ValueError("Cannot rename a running machine.")
        self.library.save(m, old_name=old_name)
        if old_name != m.name:
            self.finished.pop(old_name, None)
        self._write_launcher(m)
        self.refresh_list(select=m.name)

    def _write_launcher(self, m: Machine):
        try:
            command.write_launcher(m, self.settings.qemu_dir, str(self.library.folder(m.name)))
        except OSError as e:
            messagebox.showerror("Launcher", f"Could not write the launcher file:\n{e}")

    def reset_nvram(self):
        name = self.selected_name()
        if not name:
            return
        if name in self.running and self.running[name].poll() is None:
            messagebox.showwarning("Reset", f"'{name}' is running; shut it down first.")
            return
        if confirm_reset_nvram(self, name, self.library.managed_status(name)):
            removed = self.library.reset_nvram_pram(name)
            self.refresh_overview()
            messagebox.showinfo("Reset NVRAM + PRAM", "Deleted: " + (", ".join(removed) or "nothing"))

    def reveal(self):
        name = self.selected_name()
        if name:
            reveal_folder(self.library.folder(name))

    def start_selected(self) -> RunningMachine | None:
        """The Start button. Returns the RunningMachine (or None if refused)."""
        m = self.selected_machine()
        if not m:
            return None
        r = self.running.get(m.name)
        if r and r.poll() is None:
            messagebox.showwarning("Start", f"'{m.name}' is already running (pid {r.pid}). "
                                            "Shut it down from inside the guest first.")
            return None
        qd = m.effective_qemu_dir(self.settings.qemu_dir)
        if not paths.has_qemu(qd):
            messagebox.showerror("Start", f"QEMU binary not found in '{qd or '(no QEMU folder set)'}'.\n"
                                          "Set it under File > Settings or as a per-machine override.")
            return None
        errors, _warnings = model.validate(m, self.settings.qemu_dir)
        if errors:
            messagebox.showerror("Start", "The record has errors; fix them in Edit first:\n\n" +
                                 "\n".join(f"- {e}" for e in errors))
            return None
        try:
            r = start_machine(m, self.library.folder(m.name), self.settings.qemu_dir)
        except OSError as e:
            messagebox.showerror("Start", f"Could not start QEMU:\n{e}")
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

    # ---------------- settings
    def edit_settings(self):
        SettingsDialog(self)

    def _save_settings(self):
        try:
            self.settings.save(self.settings_path)
        except OSError:
            pass

    def _quit(self):
        self._save_settings()
        if self.running:
            names = ", ".join(self.running)
            if not messagebox.askyesno("Quit", f"Guests still running: {names}. They keep running if you quit "
                                               "the GUI (shut them down from inside the guest). Quit the GUI?"):
                return
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, app: MainWindow):
        super().__init__(app)
        self.app = app
        self.title("Settings")
        self.transient(app)
        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        self.lib_var = tk.StringVar(value=app.settings.library_dir)
        self.qemu_var = tk.StringVar(value=app.settings.qemu_dir)
        ttk.Label(f, text="Machine library folder:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(f, textvariable=self.lib_var, width=52).grid(row=0, column=1, sticky="ew")
        ttk.Button(f, text="Browse...", command=lambda: self._pick(self.lib_var)).grid(row=0, column=2, padx=3)
        ttk.Label(f, text="QEMU folder (qemu-system-ppc, qemu-img, ROMs):").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(f, textvariable=self.qemu_var, width=52).grid(row=1, column=1, sticky="ew")
        ttk.Button(f, text="Browse...", command=lambda: self._pick(self.qemu_var)).grid(row=1, column=2, padx=3)
        self.info = ttk.Label(f, text="", foreground="gray", wraplength=520)
        self.info.grid(row=2, column=0, columnspan=3, sticky="w", pady=4)
        bar = ttk.Frame(f)
        bar.grid(row=3, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=2)
        ttk.Button(bar, text="Save", command=self.save).pack(side="right", padx=2)
        self._check()
        self.qemu_var.trace_add("write", lambda *_: self._check())

    def _pick(self, var):
        d = filedialog.askdirectory(parent=self, initialdir=var.get() or str(Path.home()))
        if d:
            var.set(d)

    def _check(self):
        qd = self.qemu_var.get().strip()
        found = paths.has_qemu(qd)
        roms = [r for r in ("PowerMacG3v3.ROM", "ati_mach_gt.rom", "ati_nexus128_103_pci.rom")
                if qd and (Path(qd) / r).is_file()]
        self.info.config(text=f"{paths.qemu_binary_name()}: {'found' if found else 'not found'}; "
                              f"ROMs present: {', '.join(roms) or 'none'}. Settings file: "
                              f"{self.app.settings_path or paths.settings_path()}")

    def save(self):
        self.app.settings.library_dir = self.lib_var.get().strip() or str(paths.default_library_dir())
        self.app.settings.qemu_dir = self.qemu_var.get().strip()
        self.app._save_settings()
        self.app.refresh_list()
        self.destroy()
