"""The machine editor: Machine, Display, Drives, Network & sound, Advanced.

Two rules with teeth:

* **Nothing is ever filled in for you.** Every field that names a file starts
  empty and stays empty until it is chosen, the Mac's own ROM included.
* A file field is one control: a path can be typed or pasted straight into
  it, and double-clicking it opens the chooser.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from . import model, paths
from .model import Machine, AtaDrive, ScsiDrive, Identity, Floppy, SecondGpu, Network, Governor
from .systems import SYSTEMS, system_labels, system_by_label
from .ui_dialogs import show_validation, CreateDiskDialog

KIND_LABELS = {"": "Empty", "disk": "Hard disk", "cdrom": "CD"}
KIND_BY_LABEL = {v: k for k, v in KIND_LABELS.items()}
IMAGE_TYPES = [("Hard disks and CDs", "*.img *.dsk *.qcow2 *.iso *.toast *.cdr"),
               ("Every file", "*")]
ROM_TYPES = [("ROM files", "*.rom *.ROM *.bin"), ("Every file", "*")]
FLOPPY_TYPES = [("Floppy disks", "*.img *.dsk"), ("Every file", "*")]
CDROM_EXTS = {".iso", ".toast", ".cdr", ".dmg"}

GREY = "gray"

EDITOR_WIDTH = 813


def browse_file(parent, var: tk.StringVar, filetypes, fallback: Path | str | None = None) -> None:
    start = paths.browse_start_dir(var.get(), fallback)
    f = filedialog.askopenfilename(parent=parent, initialdir=str(start), filetypes=filetypes)
    if f:
        var.set(f)


class FilePicker:
    """One control for one file: type a path into it, paste one into it, or
    double-click it to go and find one. Empty until somebody fills it in."""

    def __init__(self, master, var: tk.StringVar, filetypes, width: int = 40, fallback=None):
        self.var = var
        self.filetypes = filetypes
        self.fallback = fallback
        self.entry = ttk.Entry(master, textvariable=var, width=width)
        self.entry.bind("<Double-Button-1>", self._browse)
        var.trace_add("write", lambda *_a: self._refresh())
        self._refresh()

    def grid(self, **kw) -> "FilePicker":
        self.entry.grid(**kw)
        return self

    def _refresh(self) -> None:
        if self.var.get():
            # a long path is shown from its end, where the file's name is
            self.entry.xview_moveto(1.0)

    def _browse(self, _e=None):
        fb = self.fallback() if callable(self.fallback) else self.fallback
        browse_file(self.entry.winfo_toplevel(), self.var, self.filetypes, fb)
        return "break"


class DriveRow:
    """One drive position (built-in or SCSI): what is in it, which file it is,
    and for SCSI what the drive should call itself."""

    def __init__(self, master, row: int, label: str, scsi: bool, fallback=None):
        self.scsi = scsi
        self.fallback = fallback
        self.kind = tk.StringVar(value=KIND_LABELS[""])
        self.file = tk.StringVar()
        self.format = tk.StringVar(value="raw")
        ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=(0, 4), pady=1)
        cb = ttk.Combobox(master, textvariable=self.kind, values=list(KIND_LABELS.values()),
                          state="readonly", width=9)
        cb.grid(row=row, column=1, padx=2, pady=1)
        cb.bind("<<ComboboxSelected>>", self._kind_changed)
        # asks for little and grows: the file column is the one that expands
        self.picker = FilePicker(master, self.file, IMAGE_TYPES, width=14 if scsi else 34,
                                 fallback=fallback)
        self.picker.grid(row=row, column=2, sticky="ew", padx=2, pady=1)
        self.file.trace_add("write", lambda *_a: self._infer_kind())
        ttk.Combobox(master, textvariable=self.format, values=model.FORMATS, state="readonly",
                     width=6).grid(row=row, column=3, padx=2)
        if scsi:
            self.send_identity = tk.BooleanVar(value=False)
            self.vendor = tk.StringVar()
            self.product = tk.StringVar()
            self.ver = tk.StringVar()
            ttk.Checkbutton(master, variable=self.send_identity).grid(row=row, column=4, padx=2)
            ttk.Entry(master, textvariable=self.vendor, width=7).grid(row=row, column=5, padx=1)
            ttk.Entry(master, textvariable=self.product, width=12).grid(row=row, column=6, padx=1)
            ttk.Entry(master, textvariable=self.ver, width=4).grid(row=row, column=7, padx=1)

    def _infer_kind(self):
        """A file chosen while the position still says "Empty" would be
        dropped on save, so work out from the file name what it is."""
        if KIND_BY_LABEL[self.kind.get()] or not self.file.get().strip():
            return
        ext = Path(self.file.get().strip()).suffix.lower()
        self.kind.set(KIND_LABELS["cdrom" if ext in CDROM_EXTS else "disk"])
        self._kind_changed()

    def _kind_changed(self, _e=None):
        k = KIND_BY_LABEL[self.kind.get()]
        if self.scsi and k and not (self.vendor.get() or self.product.get() or self.ver.get()):
            ident = model.default_identity(k)
            self.vendor.set(ident.vendor)
            self.product.set(ident.product)
            self.ver.set(ident.ver)

    def set_ata(self, d: AtaDrive | None):
        self.kind.set(KIND_LABELS[d.kind if d else ""])
        self.file.set(d.file if d else "")
        self.format.set((d.format if d else "raw") or "raw")

    def get_ata(self) -> AtaDrive | None:
        self._infer_kind()
        k = KIND_BY_LABEL[self.kind.get()]
        if not k or not self.file.get().strip():
            return None         # nothing chosen here: an empty position
        return AtaDrive(kind=k, file=self.file.get().strip(), format=self.format.get() or "raw")

    def set_scsi(self, d: ScsiDrive | None):
        self.kind.set(KIND_LABELS[d.kind if d else ""])
        self.file.set(d.file if d else "")
        self.format.set((d.format if d else "raw") or "raw")
        ident = d.identity if d else None
        self.send_identity.set(ident is not None)
        base = ident or (model.default_identity(d.kind) if d else Identity())
        self.vendor.set(base.vendor)
        self.product.set(base.product)
        self.ver.set(base.ver)

    def get_scsi(self, sid: int) -> ScsiDrive | None:
        self._infer_kind()
        k = KIND_BY_LABEL[self.kind.get()]
        if not k or not self.file.get().strip():
            return None
        ident = None
        if self.send_identity.get():
            ident = Identity(self.vendor.get().strip(), self.product.get().strip(),
                             self.ver.get().strip())
        return ScsiDrive(id=sid, kind=k, file=self.file.get().strip(),
                         format=self.format.get() or "raw", identity=ident)


class MachineEditor(tk.Toplevel):
    """One machine's settings. ``on_save(machine, old_name)`` runs after
    checking. With ``is_new`` the same window opens empty; nothing exists on
    disk until Save."""

    def __init__(self, parent, machine: Machine, library: model.Library, qemu_dir: str, on_save,
                 is_new: bool = False):
        super().__init__(parent)
        self.machine = machine.copy()
        self.old_name = machine.name
        self.is_new = is_new
        self.library = library
        self.qemu_dir = qemu_dir
        self.on_save = on_save
        self.title("New machine" if is_new else f"{machine.name} — settings")
        self.resizable(True, True)
        self.transient(parent)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_machine()
        self._build_display()
        self._build_drives()
        self._build_net_audio()
        self._build_advanced()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        self.msg = ttk.Label(bar, text="", foreground=GREY, wraplength=EDITOR_WIDTH - 310)
        self.msg.pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=2)
        ttk.Button(bar, text="Save", command=self.save).pack(side="right", padx=2)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.load(self.machine)
        self._size_window()
        self.nb.select(0)                       # the Machine page, always first
        self.name_entry.focus_set()

    def _size_window(self):
        """No taller than the screen it has to fit on."""
        self.update_idletasks()
        height = min(self.winfo_reqheight(), max(400, self.winfo_screenheight() - 160))
        self.geometry(f"{EDITOR_WIDTH}x{height}")
        self.minsize(640, 400)

    def machine_folder(self) -> Path:
        """Where this machine's own files live, named after the machine."""
        name = self.name_var.get().strip() or self.old_name
        return self.library.folder(name) if name else self.library.root

    # ---------------- tabs
    def _tab(self, title: str) -> ttk.Frame:
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text=title)
        return f

    def _build_machine(self):
        f = self._tab("Machine")
        f.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(f, text="Name:").grid(row=r, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(f, textvariable=self.name_var, width=40)
        self.name_entry.grid(row=r, column=1, sticky="ew", pady=4)
        r += 1
        ttk.Label(f, text="System:").grid(row=r, column=0, sticky="w", pady=4)
        self.system_var = tk.StringVar()
        ttk.Combobox(f, textvariable=self.system_var, values=system_labels(), state="readonly",
                     width=26).grid(row=r, column=1, sticky="w", pady=4)
        r += 1
        ttk.Label(f, text="Memory:").grid(row=r, column=0, sticky="w", pady=4)
        self.ram_var = tk.StringVar()
        ttk.Combobox(f, textvariable=self.ram_var, values=[str(x) for x in model.RAM_CHOICES],
                     width=10).grid(row=r, column=1, sticky="w", pady=4)
        r += 1
        ttk.Label(f, text="ROM (required):").grid(row=r, column=0, sticky="w", pady=4)
        self.rom_var = tk.StringVar()
        FilePicker(f, self.rom_var, ROM_TYPES, width=40,
                   fallback=lambda: self.qemu_dir).grid(row=r, column=1, sticky="ew", pady=4)
        r += 1
        ttk.Label(f, text="My notes:").grid(row=r, column=0, sticky="nw", pady=4)
        self.notes = tk.Text(f, width=52, height=8, wrap="word")
        self.notes.grid(row=r, column=1, sticky="nsew", pady=4)
        f.rowconfigure(r, weight=1)

    def _build_display(self):
        f = self._tab("Display")
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Display type", font=("", 0, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(f, text="Display:").grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.display_var = tk.StringVar()
        displays = model.DISPLAYS.get("win32" if paths.is_windows() else paths.HOST_PLATFORM,
                                      ("sdl", "gtk"))
        ttk.Combobox(f, textvariable=self.display_var, values=list(displays), state="readonly",
                     width=10).grid(row=1, column=1, sticky="w", pady=(0, 8))
        ttk.Label(f, text="Select sdl when enabling dual screen",
                  foreground=GREY).grid(row=1, column=2, sticky="w", padx=6, pady=(0, 8))

        ttk.Label(f, text="Built-in ATI Mach64 GT", font=("", 0, "bold")).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.onboard_mode = tk.StringVar(value="none")
        ttk.Radiobutton(f, text="Use built-in ROM",
                        variable=self.onboard_mode, value="none").grid(
            row=3, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Select ROM", variable=self.onboard_mode,
                        value="file").grid(row=4, column=0, sticky="w")
        self.onboard_rom_var = tk.StringVar()
        FilePicker(f, self.onboard_rom_var, ROM_TYPES, width=40,
                   fallback=lambda: self.qemu_dir).grid(row=4, column=1, columnspan=2,
                                                        sticky="ew", padx=2)

        ttk.Separator(f).grid(row=5, column=0, columnspan=3, sticky="ew", pady=10)
        self.gpu_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Enable dual screen", variable=self.gpu_on,
                        command=self._gpu_changed).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(f, text="Ati Rage 128 ROM:").grid(row=7, column=0, sticky="w", pady=(6, 0))
        self.gpu_rom_var = tk.StringVar()
        FilePicker(f, self.gpu_rom_var, ROM_TYPES, width=40,
                   fallback=lambda: self.qemu_dir).grid(row=7, column=1, columnspan=2,
                                                        sticky="ew", padx=2, pady=(6, 0))
        ttk.Label(f, text="Slot:").grid(row=8, column=0, sticky="w", pady=(6, 0))
        self.gpu_addr_var = tk.StringVar(value=SecondGpu().addr)
        ttk.Entry(f, textvariable=self.gpu_addr_var, width=8).grid(
            row=8, column=1, sticky="w", pady=(6, 0))

    def _gpu_changed(self, _e=None):
        """Enabling the card never chooses its ROM file."""
        if self.gpu_on.get() and not self.gpu_addr_var.get():
            self.gpu_addr_var.set(SecondGpu().addr)

    def _build_drives(self):
        f = self._tab("Drives")
        f.columnconfigure(0, weight=1)
        r = 0
        ttk.Label(f, text="IDE", font=("", 0, "bold")).grid(
            row=r, column=0, sticky="w", pady=(0, 4))
        r += 1
        ata = ttk.Frame(f)
        ata.grid(row=r, column=0, sticky="ew")
        ata.columnconfigure(2, weight=1)
        for c, h in enumerate(("Position", "", "", "Format")):
            ttk.Label(ata, text=h, foreground=GREY).grid(row=0, column=c, sticky="w", padx=4)
        self.ata_rows = [DriveRow(ata, 1 + i,
                                  model.ata_slot_name(i), scsi=False,
                                  fallback=self.machine_folder)
                         for i in range(len(model.ATA_SLOTS))]
        r += 1
        have_img = paths.qemu_img_binary().is_file()
        ttk.Button(f, text="Create new disk image…", command=self._create_disk,
                   state=("normal" if have_img else "disabled")).grid(
            row=r, column=0, sticky="w", padx=4, pady=(8, 4))
        if not have_img:
            ttk.Label(f, text=f"{paths.qemu_img_name()} not found",
                      foreground=GREY).grid(row=r, column=1, sticky="w", padx=6)
        r += 1
        ttk.Separator(f).grid(row=r, column=0, sticky="ew", pady=8)
        r += 1
        ttk.Label(f, text="SCSI", font=("", 0, "bold")).grid(
            row=r, column=0, sticky="w", padx=4, pady=(0, 4))
        r += 1
        scsi = ttk.Frame(f)
        scsi.grid(row=r, column=0, sticky="ew")
        scsi.columnconfigure(2, weight=1)
        for c, h in enumerate(("Device", "", "", "Format", "Pretend", "Make", "Model", "Version")):
            ttk.Label(scsi, text=h, foreground=GREY).grid(row=0, column=c, sticky="w", padx=4)
        self.scsi_rows = [DriveRow(scsi, sid + 1, model.scsi_name(sid), scsi=True,
                                   fallback=self.machine_folder)
                          for sid in model.SCSI_IDS]
        self_row = model.SCSI_SELF_ID + 1
        ttk.Label(scsi, text=model.scsi_name(model.SCSI_SELF_ID)).grid(
            row=self_row, column=0, sticky="w", padx=(0, 4), pady=1)
        ttk.Label(scsi, text=model.SCSI_SELF_LABEL, foreground=GREY).grid(
            row=self_row, column=1, columnspan=7, sticky="w", padx=2, pady=1)
        r += 1
        ttk.Separator(f).grid(row=r, column=0, sticky="ew", pady=8)
        r += 1
        ttk.Label(f, text="Floppy", font=("", 0, "bold")).grid(
            row=r, column=0, sticky="w", padx=4, pady=(0, 4))
        r += 1
        fd = ttk.Frame(f)
        fd.grid(row=r, column=0, sticky="ew")
        fd.columnconfigure(1, weight=1)
        self.floppy_mode = tk.StringVar(value="none")
        ttk.Radiobutton(fd, text="Empty", variable=self.floppy_mode,
                        value="none").grid(row=0, column=0, columnspan=2, sticky="w", padx=4)
        ttk.Radiobutton(fd, text="Disk:", variable=self.floppy_mode,
                        value="file").grid(row=1, column=0, sticky="w", padx=4)
        self.floppy_var = tk.StringVar()
        FilePicker(fd, self.floppy_var, FLOPPY_TYPES, width=44,
                   fallback=self.machine_folder).grid(row=1, column=1, sticky="ew", padx=2)
        ttk.Label(scsi,
                  text="Boot order: floppy (when bootable), SCSI, IDE — unless set "
                       "in the Startup Disk control panel.",
                  foreground=GREY, wraplength=640, justify="left").grid(
            row=self_row + 1, column=0, columnspan=7, sticky="w", pady=(8, 0))

    def _build_net_audio(self):
        f = self._tab("Network & sound")
        ttk.Label(f, text="Network", font=("", 0, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(f, text="Connection:").grid(row=2, column=0, sticky="w")
        self.net_mode = tk.StringVar(value=model.network_mode_label("user"))
        self.net_mode_cb = ttk.Combobox(f, textvariable=self.net_mode, state="readonly", width=18,
                                        values=model.network_labels_for_host())
        self.net_mode_cb.grid(row=2, column=1, sticky="w")
        self.net_mode_cb.bind("<<ComboboxSelected>>", self._net_mode_changed)
        ttk.Label(f, text="Vmnet host interface:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.ifname_var = tk.StringVar()
        self.ifname_entry = ttk.Entry(f, textvariable=self.ifname_var, width=28)
        self.ifname_entry.grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Label(f, text="Card MAC address:").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.mac_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.mac_var, width=22).grid(
            row=4, column=1, sticky="w", pady=(6, 0))
        ttk.Separator(f).grid(row=5, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(f, text="Sound interface", font=("", 0, "bold")).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.audio_var = tk.StringVar(value="default")
        ttk.Radiobutton(f, text="CoreAudio", variable=self.audio_var, value="default").grid(
            row=7, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="SDL", variable=self.audio_var, value="sdl").grid(
            row=8, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="None", variable=self.audio_var, value="none").grid(
            row=9, column=0, columnspan=3, sticky="w")

    def _net_mode_changed(self, _e=None):
        mode = model.network_mode_by_label(self.net_mode.get())
        if mode in model.NETWORK_MODES_WITH_IFNAME:
            self.ifname_entry.config(state="normal")
            if not self.ifname_var.get():
                self.ifname_var.set(model.default_ifname(mode))
        else:
            self.ifname_entry.config(state="disabled")

    def _build_advanced(self):
        f = self._tab("Advanced")
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Speed limiter", font=("", 0, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.gov_mode = tk.StringVar(value="default")
        ttk.Radiobutton(f, text="Normal (for Mac OS)", variable=self.gov_mode, value="default").grid(
            row=1, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Off (for Mac OS X)", variable=self.gov_mode,
                        value="off").grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Fixed:", variable=self.gov_mode, value="mips").grid(
            row=3, column=0, sticky="w")
        self.mips_var = tk.StringVar(value="100")
        ttk.Spinbox(f, textvariable=self.mips_var, from_=1, to=100000, width=8).grid(
            row=3, column=1, sticky="w")
        ttk.Separator(f).grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(f, text="Additional command line arguments", font=("", 0, "bold")).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.extra_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.extra_var, width=70).grid(
            row=6, column=0, columnspan=3, sticky="ew")

    # ---------------- load / collect
    def load(self, m: Machine):
        self.name_var.set(m.name)
        self.system_var.set(SYSTEMS[m.system].label)
        self.ram_var.set(str(m.ram_mb))
        self.rom_var.set(m.rom)
        self.display_var.set(m.display)
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", m.notes)
        self.onboard_mode.set("file" if m.onboard_romfile else "none")
        self.onboard_rom_var.set(m.onboard_romfile or "")
        if m.second_gpu:
            self.gpu_on.set(True)
            self.gpu_addr_var.set(m.second_gpu.addr or "")
            self.gpu_rom_var.set(m.second_gpu.romfile or "")
        else:
            self.gpu_on.set(False)
            self.gpu_addr_var.set(SecondGpu().addr)
            self.gpu_rom_var.set("")
        for i, row in enumerate(self.ata_rows):
            row.set_ata(m.ata[i] if i < len(m.ata) else None)
        for sid, row in enumerate(self.scsi_rows):
            row.set_scsi(m.scsi_by_id(sid))
        self.floppy_mode.set("file" if m.floppy else "none")
        self.floppy_var.set(m.floppy.file if m.floppy else "")
        self.net_mode_cb.config(
            values=model.network_labels_for_host(current=m.network.mode))
        self.net_mode.set(model.network_mode_label(m.network.mode))
        self.mac_var.set(m.network.mac)
        self.ifname_var.set(m.network.ifname)
        self._net_mode_changed()
        self.audio_var.set(m.audio)
        self.gov_mode.set(m.governor.mode)
        self.mips_var.set(str(m.governor.mips))
        self.extra_var.set(m.extra_args)

    def collect(self) -> Machine:
        m = self.machine.copy()
        m.name = self.name_var.get().strip()
        m.system = system_by_label(self.system_var.get()).id
        try:
            m.ram_mb = int(self.ram_var.get().strip())
        except ValueError:
            m.ram_mb = -1
        m.rom = self.rom_var.get().strip()          # empty until it is chosen
        m.display = self.display_var.get()
        m.notes = self.notes.get("1.0", "end").rstrip("\n")
        m.onboard_romfile = (self.onboard_rom_var.get().strip() or None
                             if self.onboard_mode.get() == "file" else None)
        if not self.gpu_on.get():
            m.second_gpu = None
        else:
            m.second_gpu = SecondGpu("ati-rage128-pro",
                                     self.gpu_addr_var.get().strip(),
                                     self.gpu_rom_var.get().strip() or None)
        m.ata = [row.get_ata() for row in self.ata_rows]
        m.scsi = [d for d in (row.get_scsi(sid) for sid, row in enumerate(self.scsi_rows)) if d]
        if self.floppy_mode.get() == "file" and self.floppy_var.get().strip():
            m.floppy = Floppy(self.floppy_var.get().strip(), "raw")
        else:
            m.floppy = None
        mode = model.network_mode_by_label(self.net_mode.get())
        ifname = self.ifname_var.get().strip() if mode in model.NETWORK_MODES_WITH_IFNAME else ""
        m.network = Network(mode, self.mac_var.get().strip(), ifname)
        try:
            mips = int(self.mips_var.get())
        except ValueError:
            mips = 0
        m.governor = Governor(self.gov_mode.get(), mips)
        m.audio = self.audio_var.get()
        m.extra_args = self.extra_var.get().strip()
        return m

    # ---------------- actions
    def _create_disk(self):
        if not self.name_var.get().strip():
            messagebox.showinfo("New hard disk", "Give this machine a name first.",
                                parent=self)
            return
        cur = self.collect()
        dlg = CreateDiskDialog(self, cur, self.machine_folder())
        if not dlg.result:
            return
        path, fmt, place = dlg.result
        if place and place[0] == "ata":
            self.ata_rows[place[1]].set_ata(AtaDrive("disk", path, fmt))
        elif place and place[0] == "scsi":
            self.scsi_rows[place[1]].set_scsi(ScsiDrive(place[1], "disk", path, fmt, None))
        self.msg.config(text=f"Made {Path(path).name}")

    def save(self):
        m = self.collect()
        errors, warnings = model.validate(m, self.qemu_dir,
                                          machine_dir=str(self.machine_folder()))
        if m.name != self.old_name and self.library.has_record(m.name):
            errors.append(f"You already have a machine called “{m.name}”.")
        self.msg.config(text="  ".join(errors + warnings)[:300])
        if not show_validation(self, errors, warnings):
            return
        try:
            self.on_save(m, self.old_name)
        except (OSError, ValueError) as e:
            messagebox.showerror("Save", str(e), parent=self)
            return
        self.destroy()
