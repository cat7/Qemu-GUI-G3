"""Small dialogs: new machine, duplicate name, confirmations, create disk image."""

from __future__ import annotations

import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog

from . import model, paths
from .profiles import PROFILES, profile_labels, profile_by_label

DISK_SIZES = ("1", "2", "4", "8", "10", "20")


def show_validation(parent, errors: list[str], warnings: list[str]) -> bool:
    """Show validation results. Returns True if saving may proceed."""
    if errors:
        text = "Cannot save:\n\n" + "\n".join(f"- {e}" for e in errors)
        if warnings:
            text += "\n\nAlso:\n" + "\n".join(f"- {w}" for w in warnings)
        messagebox.showerror("Validation", text, parent=parent)
        return False
    if warnings:
        text = "Saved with warnings:\n\n" + "\n".join(f"- {w}" for w in warnings) + "\n\nSave anyway?"
        return messagebox.askyesno("Validation", text, parent=parent)
    return True


def confirm_reset_nvram(parent, name: str, status: dict) -> bool:
    present = [f"{k} ({v} bytes)" for k, v in status.items() if v is not None]
    if not present:
        messagebox.showinfo("Reset NVRAM + PRAM",
                            f"'{name}' has no nvram.img or pram.img yet; nothing to reset.",
                            parent=parent)
        return False
    return messagebox.askyesno(
        "Reset NVRAM + PRAM",
        f"Delete from '{name}':\n\n" + "\n".join(f"- {p}" for p in present) +
        "\n\nQEMU recreates both files empty on the next start and the ROM "
        "re-initialises them.\n\nAfter a reset the first boot may show the flashing "
        "floppy until a CD boot re-initialises NVRAM.\n\nDelete them?",
        icon="warning", parent=parent)


def confirm_delete(parent, name: str, files: list[str]) -> bool:
    listing = "\n".join(f"- {f}" for f in files[:40])
    if len(files) > 40:
        listing += f"\n... and {len(files) - 40} more"
    if not files:
        listing = "(empty folder)"
    return messagebox.askyesno(
        "Delete machine",
        f"Delete the machine folder '{name}' and everything in it:\n\n{listing}\n\n"
        "Disk images stored elsewhere are NOT touched. This cannot be undone.",
        icon="warning", parent=parent)


class NewMachineDialog(simpledialog.Dialog):
    """Ask for a name and an OS profile."""

    def __init__(self, parent, existing: list[str], title="New machine"):
        self.existing = existing
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text="Name (folder name):").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.name_var = tk.StringVar(value="")
        e = ttk.Entry(master, textvariable=self.name_var, width=32)
        e.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(master, text="Profile:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.profile_var = tk.StringVar(value=profile_labels()[0])
        cb = ttk.Combobox(master, textvariable=self.profile_var, values=profile_labels(),
                          state="readonly", width=30)
        cb.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        self.hint = ttk.Label(master, text="", wraplength=360, foreground="gray")
        self.hint.grid(row=2, column=0, columnspan=2, sticky="w", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._hint())
        self._hint()
        return e

    def _hint(self):
        p = profile_by_label(self.profile_var.get())
        gpu = "Rage 128 Pro" if p.second_gpu else "none"
        self.hint.config(text=f"{p.ram_mb} MB, display {p.display}, second card {gpu}, "
                              f"onboard ROM {p.onboard_romfile or 'none'}. {p.notes}")

    def validate(self):
        name = self.name_var.get().strip()
        if not model.NAME_RE.match(name or ""):
            messagebox.showerror("Name", "Use only letters, digits, space, '.', '_' or '-'.", parent=self)
            return False
        if name in self.existing:
            messagebox.showerror("Name", f"A machine named '{name}' already exists.", parent=self)
            return False
        return True

    def apply(self):
        self.result = (self.name_var.get().strip(), profile_by_label(self.profile_var.get()).id)


def ask_name(parent, title: str, prompt: str, initial: str, existing: list[str]) -> str | None:
    while True:
        name = simpledialog.askstring(title, prompt, initialvalue=initial, parent=parent)
        if name is None:
            return None
        name = name.strip()
        if not model.NAME_RE.match(name):
            messagebox.showerror(title, "Use only letters, digits, space, '.', '_' or '-'.", parent=parent)
            continue
        if name in existing:
            messagebox.showerror(title, f"A machine named '{name}' already exists.", parent=parent)
            continue
        return name


class CreateDiskDialog(simpledialog.Dialog):
    """qemu-img create -f raw|qcow2 <machine>/<name>.img <N>G, then offer a slot."""

    def __init__(self, parent, machine: model.Machine, machine_dir: Path, qemu_dir: str):
        self.machine = machine
        self.machine_dir = Path(machine_dir)
        self.qemu_img = Path(paths.join_path(qemu_dir, paths.qemu_img_name())) if qemu_dir else None
        self.result = None  # (path, format, placement) placement = ("ata", i) | ("scsi", id) | None
        super().__init__(parent, "Create disk image")

    def body(self, master):
        r = 0
        ttk.Label(master, text="File name:").grid(row=r, column=0, sticky="w", padx=4, pady=3)
        self.name_var = tk.StringVar(value="disk")
        ttk.Entry(master, textvariable=self.name_var, width=28).grid(row=r, column=1, sticky="ew", padx=4)
        ttk.Label(master, text=f"in {self.machine_dir}", foreground="gray", wraplength=320).grid(
            row=r + 1, column=1, sticky="w", padx=4)
        r += 2
        ttk.Label(master, text="Format:").grid(row=r, column=0, sticky="w", padx=4, pady=3)
        self.fmt_var = tk.StringVar(value="raw")
        ttk.Combobox(master, textvariable=self.fmt_var, values=model.FORMATS, state="readonly",
                     width=8).grid(row=r, column=1, sticky="w", padx=4)
        r += 1
        ttk.Label(master, text="Size (GB):").grid(row=r, column=0, sticky="w", padx=4, pady=3)
        self.size_var = tk.StringVar(value="2")
        ttk.Combobox(master, textvariable=self.size_var, values=DISK_SIZES, width=8).grid(
            row=r, column=1, sticky="w", padx=4)
        r += 1
        ttk.Label(master, text="Then attach as:").grid(row=r, column=0, sticky="w", padx=4, pady=3)
        choices = ["(do not attach)"]
        for i, name in enumerate(model.ATA_SLOT_NAMES):
            choices.append(f"ATA {name}  ({self.machine.ata_slot_status(i)})")
        for sid in model.SCSI_IDS:
            if self.machine.scsi_by_id(sid) is None:
                choices.append(f"SCSI id {sid}")
        free = self.machine.first_unfilled_ata()
        default = choices[1 + free] if free is not None else choices[0]
        self.place_var = tk.StringVar(value=default)
        ttk.Combobox(master, textvariable=self.place_var, values=choices, state="readonly",
                     width=26).grid(row=r, column=1, sticky="w", padx=4)
        r += 1
        status = "qemu-img: found" if self.qemu_img and self.qemu_img.is_file() else "qemu-img: NOT found in the QEMU folder"
        ttk.Label(master, text=status, foreground="gray").grid(row=r, column=0, columnspan=2, sticky="w", padx=4)
        return None

    def validate(self):
        name = self.name_var.get().strip()
        if not name or "/" in name or "\\" in name:
            messagebox.showerror("Create disk", "Give a plain file name.", parent=self)
            return False
        try:
            size = float(self.size_var.get())
            if size <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Create disk", "Size must be a positive number of GB.", parent=self)
            return False
        if not (self.qemu_img and self.qemu_img.is_file()):
            messagebox.showerror("Create disk", "qemu-img was not found in the QEMU folder.", parent=self)
            return False
        ext = ".qcow2" if self.fmt_var.get() == "qcow2" else ".img"
        if not name.lower().endswith((".img", ".qcow2", ".dsk")):
            name += ext
        self.target = self.machine_dir / name
        if self.target.exists():
            messagebox.showerror("Create disk", f"{self.target} already exists.", parent=self)
            return False
        return True

    def apply(self):
        fmt = self.fmt_var.get()
        size = self.size_var.get().strip()
        size_arg = f"{size}G" if not size.upper().endswith(("G", "M")) else size
        self.machine_dir.mkdir(parents=True, exist_ok=True)
        cmd = [str(self.qemu_img), "create", "-f", fmt, str(self.target), size_arg]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as e:
            messagebox.showerror("Create disk", f"qemu-img failed to run:\n{e}", parent=self)
            return
        if out.returncode != 0:
            messagebox.showerror("Create disk", f"qemu-img failed:\n{out.stderr or out.stdout}", parent=self)
            return
        place = None
        p = self.place_var.get()
        if p.startswith("ATA "):
            slot = p[4:].split("  (")[0]
            place = ("ata", model.ATA_SLOT_NAMES.index(slot))
        elif p.startswith("SCSI id "):
            place = ("scsi", int(p[8:]))
        self.result = (str(self.target), fmt, place)


def reveal_folder(path: Path) -> None:
    path = Path(path)
    try:
        if paths.HOST_PLATFORM == "darwin":
            subprocess.Popen(["open", str(path)])
        elif paths.is_windows():
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as e:
        messagebox.showerror("Reveal", str(e))
