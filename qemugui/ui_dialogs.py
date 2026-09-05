"""The small windows: the name for a duplicate, the delete confirmation, and
create a disk. A new machine is not one of them -- it opens the settings
window straight away, on the Machine page.

Every message here is written for someone who wants to run an old Mac and
has never heard of a bus, a slot index or a device path.
"""

from __future__ import annotations

import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog

from . import model, paths

DISK_SIZES = ("1", "2", "4", "8", "10", "20")
NAME_RULE = "Names can use letters, numbers, spaces and the characters . _ -"


def show_validation(parent, errors: list[str], warnings: list[str]) -> bool:
    """Show what is wrong, or worth knowing. True if saving may go ahead."""
    if errors:
        text = "This machine cannot be saved yet:\n\n" + "\n".join(f"• {e}" for e in errors)
        if warnings:
            text += "\n\nAlso worth knowing:\n" + "\n".join(f"• {w}" for w in warnings)
        messagebox.showerror("Not quite right", text, parent=parent)
        return False
    if warnings:
        text = ("Saved — but there are a few things worth knowing:\n\n" +
                "\n".join(f"• {w}" for w in warnings) +
                "\n\nSave it anyway?")
        return messagebox.askyesno("Worth knowing", text, parent=parent)
    return True


def _bullets(files: list[str], limit: int = 20) -> str:
    shown = "\n".join(f"    {f}" for f in files[:limit])
    if len(files) > limit:
        shown += f"\n    … and {len(files) - limit} more"
    return shown


def confirm_delete(parent, name: str, will_go: list[str], will_stay: list[str],
                   folder: Path) -> bool:
    """Delete removes the record, the launcher and the saved settings. Disk
    images are never deleted, and this window says so before anything
    happens."""
    text = (f"Remove “{name}” from Qemu-system-ppc GUI?\n\n"
            "This deletes how the machine is set up, the file that starts it, and the "
            "settings the Mac itself had saved.")
    if will_stay:
        images = [f for f in will_stay if model.looks_like_disk_image(f)]
        subject = "Your disk images stay" if images else "These files stay"
        text += ("\n\n" + subject + " exactly where they are, untouched:\n\n" +
                 _bullets(will_stay) + f"\n\nin\n    {folder}\n\n"
                 "A disk image is never deleted here. If you want the space back, "
                 "delete them yourself in the Finder once you are sure.")
    else:
        text += "\n\nThere are no disk images in this machine's folder."
    text += "\n\nThis cannot be undone."
    return messagebox.askyesno("Remove this machine", text, icon="warning", parent=parent)


def report_delete(parent, name: str, result: model.DeleteResult) -> None:
    if not result.kept:
        return
    messagebox.showinfo(
        "Removed",
        f"“{name}” is gone from Qemu-system-ppc GUI.\n\nWhat was left untouched:\n\n" +
        _bullets(result.kept) + f"\n\nYou will find them in\n    {result.folder}",
        parent=parent)


def ask_name(parent, title: str, prompt: str, initial: str, existing: list[str]) -> str | None:
    while True:
        name = simpledialog.askstring(title, prompt, initialvalue=initial, parent=parent)
        if name is None:
            return None
        name = name.strip()
        if not model.NAME_RE.match(name):
            messagebox.showerror("That name will not work", NAME_RULE + ".", parent=parent)
            continue
        if name in existing:
            messagebox.showerror("That name is taken",
                                 f"You already have a machine called “{name}”.", parent=parent)
            continue
        return name


class CreateDiskDialog(simpledialog.Dialog):
    """Make a new, empty hard disk for this machine and offer it a position.

    Never writes over an existing file: ``model.check_new_image_path`` is the
    guard, and it refuses rather than overwriting.
    """

    def __init__(self, parent, machine: model.Machine, machine_dir: Path):
        self.machine = machine
        self.machine_dir = Path(machine_dir)
        self.qemu_img = paths.qemu_img_binary()
        self.target: Path | None = None
        self.result = None  # (path, format, placement) placement = ("ata", i) | ("scsi", id) | None
        super().__init__(parent, "New hard disk")

    def body(self, master):
        r = 0
        ttk.Label(master, text="An empty hard disk for this Mac to install a system onto.",
                  wraplength=420, justify="left").grid(row=r, column=0, columnspan=2,
                                                       sticky="w", padx=4, pady=(4, 8))
        r += 1
        ttk.Label(master, text="Call it:").grid(row=r, column=0, sticky="w", padx=4, pady=3)
        self.name_var = tk.StringVar(value="hard disk")
        ttk.Entry(master, textvariable=self.name_var, width=30).grid(
            row=r, column=1, sticky="ew", padx=4)
        r += 1
        ttk.Label(master, text=f"It will be made in this machine's own folder,\n{self.machine_dir}",
                  foreground="gray", wraplength=420, justify="left").grid(
            row=r, column=1, sticky="w", padx=4)
        r += 1
        ttk.Label(master, text="How big?").grid(row=r, column=0, sticky="w", padx=4, pady=3)
        self.size_var = tk.StringVar(value="2")
        ttk.Combobox(master, textvariable=self.size_var, values=DISK_SIZES, width=8).grid(
            row=r, column=1, sticky="w", padx=4)
        r += 1
        ttk.Label(master, text="In gigabytes. Old systems cannot always cope with very large "
                               "disks; 2 GB is a safe choice for Mac OS 8 and 9.",
                  foreground="gray", wraplength=420, justify="left").grid(
            row=r, column=1, sticky="w", padx=4)
        r += 1
        ttk.Label(master, text="Format:").grid(row=r, column=0, sticky="w", padx=4, pady=3)
        self.fmt_var = tk.StringVar(value="raw")
        ttk.Combobox(master, textvariable=self.fmt_var, values=model.FORMATS, state="readonly",
                     width=8).grid(row=r, column=1, sticky="w", padx=4)
        r += 1
        ttk.Label(master, text="“raw” is a plain disk, the size you asked for, and works "
                               "everywhere. “qcow2” only takes up the space actually used.",
                  foreground="gray", wraplength=420, justify="left").grid(
            row=r, column=1, sticky="w", padx=4)
        r += 1
        ttk.Label(master, text="Put it in:").grid(row=r, column=0, sticky="w", padx=4, pady=3)
        self.choices: list[tuple[str, tuple | None]] = [("Nowhere for now", None)]
        for i in range(len(model.ATA_SLOTS)):
            self.choices.append((f"{model.ata_slot_full(i)} — {self.machine.ata_slot_status(i)}",
                                 ("ata", i)))
        for sid in model.SCSI_IDS:
            if self.machine.scsi_by_id(sid) is None:
                self.choices.append((f"SCSI {model.scsi_full(sid)} — empty", ("scsi", sid)))
        free = self.machine.first_unfilled_ata()
        self.place_var = tk.StringVar(
            value=self.choices[1 + free][0] if free is not None else self.choices[0][0])
        ttk.Combobox(master, textvariable=self.place_var, values=[c[0] for c in self.choices],
                     state="readonly", width=52).grid(row=r, column=1, sticky="w", padx=4)
        r += 1
        if not self.qemu_img.is_file():
            ttk.Label(master, text=f"Cannot make disks: the helper program "
                                   f"{self.qemu_img.name} is not in the folder this program "
                                   f"is in.",
                      foreground="#a00", wraplength=420, justify="left").grid(
                row=r, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 2))
        return None

    def validate(self):
        target, why = model.check_new_image_path(self.machine_dir, self.name_var.get(),
                                                 self.fmt_var.get())
        if why:
            messagebox.showerror("New hard disk", why, parent=self)
            return False
        try:
            size = float(self.size_var.get())
            if size <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("New hard disk", "How big should it be? Give a number of "
                                                  "gigabytes, such as 2.", parent=self)
            return False
        if not self.qemu_img.is_file():
            messagebox.showerror("New hard disk",
                                 f"The helper program “{self.qemu_img.name}” is needed to "
                                 "make a disk, and it is not in the folder this program is "
                                 "in:\n\n"
                                 f"    {self.qemu_img.parent}\n\n"
                                 "It normally comes with the emulator.", parent=self)
            return False
        self.target = target
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
            messagebox.showerror("New hard disk", f"The disk could not be made.\n\n{e}", parent=self)
            return
        if out.returncode != 0:
            messagebox.showerror("New hard disk",
                                 f"The disk could not be made.\n\n{out.stderr or out.stdout}",
                                 parent=self)
            return
        chosen = self.place_var.get()
        place = next((where for label, where in self.choices if label == chosen), None)
        self.result = (str(self.target), fmt, place)


def open_folder(path: Path) -> None:
    path = Path(path)
    try:
        if paths.HOST_PLATFORM == "darwin":
            subprocess.Popen(["open", str(path)])
        elif paths.is_windows():
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as e:
        messagebox.showerror("Qemu-system-ppc GUI",
                             f"That folder could not be opened.\n\n{e}")
