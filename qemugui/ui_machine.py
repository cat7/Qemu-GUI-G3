"""Machine editor: tabs General, Graphics, ATA, SCSI, Floppy, Network & Audio, Advanced."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from . import model, paths
from .model import Machine, AtaDrive, ScsiDrive, Identity, Floppy, SecondGpu, Network, Governor
from .profiles import PROFILES, profile_labels, profile_by_label
from .ui_dialogs import show_validation, CreateDiskDialog

KIND_LABELS = {"": "Empty", "disk": "Hard disk", "cdrom": "CD-ROM"}
KIND_BY_LABEL = {v: k for k, v in KIND_LABELS.items()}
GPU_NONE = "None"
GPU_RAGE = "ATI Rage 128 Pro (ati-rage128-pro)"
GPU_SEPARATOR = "---- unsupported, experimental ----"
GPU_CHOICES = [GPU_NONE, GPU_RAGE, GPU_SEPARATOR, *model.SECOND_GPU_EXPERIMENTAL]
IMAGE_TYPES = [("Disk images", "*.img *.dsk *.qcow2 *.iso *.toast *.cdr"), ("All files", "*")]
ROM_TYPES = [("ROM files", "*.rom *.ROM *.bin"), ("All files", "*")]
FLOPPY_TYPES = [("Floppy images", "*.img *.dsk"), ("All files", "*")]


def browse_file(parent, var: tk.StringVar, kind: str, filetypes) -> None:
    start = paths.browse_start_dir(var.get(), kind)
    f = filedialog.askopenfilename(parent=parent, initialdir=str(start), filetypes=filetypes)
    if f:
        var.set(f)


def browse_dir(parent, var: tk.StringVar) -> None:
    start = var.get() if var.get() and Path(var.get()).is_dir() else str(Path.home())
    d = filedialog.askdirectory(parent=parent, initialdir=start)
    if d:
        var.set(d)


class FileRow:
    """Entry + Browse button pair bound to a StringVar."""

    def __init__(self, master, var: tk.StringVar, kind: str, filetypes, row: int, col: int,
                 width: int = 44, columnspan: int = 1):
        self.var = var
        self.entry = ttk.Entry(master, textvariable=var, width=width)
        self.entry.grid(row=row, column=col, sticky="ew", padx=2, pady=1, columnspan=columnspan)
        self.button = ttk.Button(master, text="Browse...", width=9,
                                 command=lambda: browse_file(master.winfo_toplevel(), var, kind, filetypes))
        self.button.grid(row=row, column=col + columnspan, padx=2, pady=1)


CDROM_EXTS = {".iso", ".toast", ".cdr", ".dmg"}


class DriveRow:
    """One ATA or SCSI row: kind, file, browse, format (+ identity for SCSI)."""

    def __init__(self, master, row: int, label: str, scsi: bool):
        self.scsi = scsi
        self.kind = tk.StringVar(value=KIND_LABELS[""])
        self.file = tk.StringVar()
        self.format = tk.StringVar(value="raw")
        ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=1)
        cb = ttk.Combobox(master, textvariable=self.kind, values=list(KIND_LABELS.values()),
                          state="readonly", width=9)
        cb.grid(row=row, column=1, padx=2, pady=1)
        cb.bind("<<ComboboxSelected>>", self._kind_changed)
        self.entry = ttk.Entry(master, textvariable=self.file, width=40 if scsi else 52)
        self.entry.grid(row=row, column=2, sticky="ew", padx=2, pady=1)
        ttk.Button(master, text="Browse...", width=9, command=self._browse).grid(row=row, column=3, padx=2)
        ttk.Combobox(master, textvariable=self.format, values=model.FORMATS, state="readonly",
                     width=6).grid(row=row, column=4, padx=2)
        if scsi:
            self.send_identity = tk.BooleanVar(value=False)
            self.vendor = tk.StringVar()
            self.product = tk.StringVar()
            self.ver = tk.StringVar()
            ttk.Checkbutton(master, text="identity", variable=self.send_identity).grid(row=row, column=5, padx=2)
            ttk.Entry(master, textvariable=self.vendor, width=9).grid(row=row, column=6, padx=1)
            ttk.Entry(master, textvariable=self.product, width=16).grid(row=row, column=7, padx=1)
            ttk.Entry(master, textvariable=self.ver, width=6).grid(row=row, column=8, padx=1)

    def _browse(self):
        kind = "iso" if KIND_BY_LABEL[self.kind.get()] == "cdrom" else "hd"
        browse_file(self.entry.winfo_toplevel(), self.file, kind, IMAGE_TYPES)
        self._infer_kind()

    def _infer_kind(self):
        """A file with Type still "(empty)" would be silently dropped on save:
        infer the type from the extension instead."""
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
            return None         # a type without an image is an empty slot
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
            return None         # a type without an image is an empty slot
        ident = None
        if self.send_identity.get():
            ident = Identity(self.vendor.get().strip(), self.product.get().strip(), self.ver.get().strip())
        return ScsiDrive(id=sid, kind=k, file=self.file.get().strip(),
                         format=self.format.get() or "raw", identity=ident)


class MachineEditor(tk.Toplevel):
    """Edit a Machine. ``on_save(machine, old_name)`` is called after validation."""

    def __init__(self, parent, machine: Machine, library: model.Library, qemu_dir: str, on_save):
        super().__init__(parent)
        self.machine = machine.copy()
        self.old_name = machine.name
        self.library = library
        self.global_qemu_dir = qemu_dir
        self.on_save = on_save
        self.title(f"Edit machine: {machine.name}")
        self.resizable(True, True)
        self.transient(parent)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_general()
        self._build_graphics()
        self._build_ata()
        self._build_scsi()
        self._build_floppy()
        self._build_net_audio()
        self._build_advanced()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        self.msg = ttk.Label(bar, text="", foreground="gray", wraplength=640)
        self.msg.pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=2)
        ttk.Button(bar, text="Save", command=self.save).pack(side="right", padx=2)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.load(self.machine)

    # ---------------- tabs
    def _tab(self, title: str) -> ttk.Frame:
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text=title)
        return f

    def _build_general(self):
        f = self._tab("General")
        f.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(f, text="Name:").grid(row=r, column=0, sticky="w", pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.name_var, width=40).grid(row=r, column=1, sticky="ew", pady=2)
        ttk.Label(f, text="= folder name in the library", foreground="gray").grid(row=r, column=2, sticky="w", padx=4)
        r += 1
        ttk.Label(f, text="Profile:").grid(row=r, column=0, sticky="w", pady=2)
        self.profile_var = tk.StringVar()
        ttk.Combobox(f, textvariable=self.profile_var, values=profile_labels(), state="readonly",
                     width=24).grid(row=r, column=1, sticky="w", pady=2)
        ttk.Button(f, text="Re-apply profile defaults", command=self._reapply_profile).grid(
            row=r, column=2, sticky="w", padx=4)
        r += 1
        ttk.Label(f, text="RAM (MB):").grid(row=r, column=0, sticky="w", pady=2)
        self.ram_var = tk.StringVar()
        ttk.Combobox(f, textvariable=self.ram_var, values=[str(x) for x in model.RAM_CHOICES],
                     width=10).grid(row=r, column=1, sticky="w", pady=2)
        ttk.Label(f, text="real hardware maxes at 768; the user runs 512 and 1024", foreground="gray").grid(
            row=r, column=2, sticky="w", padx=4)
        r += 1
        ttk.Label(f, text="Machine ROM (-bios):").grid(row=r, column=0, sticky="w", pady=2)
        self.rom_var = tk.StringVar()
        FileRow(f, self.rom_var, "rom", ROM_TYPES, r, 1)
        r += 1
        ttk.Label(f, text="", foreground="gray").grid(row=r, column=0)
        ttk.Label(f, text="A name without a folder is looked up in the QEMU folder. "
                          "Use PowerMacG3v3.ROM; PowerMacG3desktop.ROM is a different board revision.",
                  foreground="gray", wraplength=520).grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1
        ttk.Label(f, text="Display backend:").grid(row=r, column=0, sticky="w", pady=2)
        self.display_var = tk.StringVar()
        displays = model.DISPLAYS.get("win32" if paths.is_windows() else paths.HOST_PLATFORM, ("sdl", "gtk"))
        ttk.Combobox(f, textvariable=self.display_var, values=list(displays), state="readonly",
                     width=10).grid(row=r, column=1, sticky="w", pady=2)
        r += 1
        ttk.Label(f, text="QEMU folder override:").grid(row=r, column=0, sticky="w", pady=2)
        self.qemu_dir_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.qemu_dir_var, width=44).grid(row=r, column=1, sticky="ew", pady=2)
        ttk.Button(f, text="Browse...", width=9,
                   command=lambda: browse_dir(self, self.qemu_dir_var)).grid(row=r, column=2, sticky="w", padx=2)
        r += 1
        ttk.Label(f, text=f"empty = global setting ({self.global_qemu_dir or 'not set'})",
                  foreground="gray", wraplength=520).grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1
        ttk.Label(f, text="Notes:").grid(row=r, column=0, sticky="nw", pady=2)
        self.notes = tk.Text(f, width=60, height=6, wrap="word")
        self.notes.grid(row=r, column=1, columnspan=2, sticky="nsew", pady=2)
        f.rowconfigure(r, weight=1)

    def _build_graphics(self):
        f = self._tab("Graphics")
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Onboard ATI Mach64 GT (Rage Pro) -- always present",
                  font=("", 0, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.onboard_mode = tk.StringVar(value="none")
        ttk.Radiobutton(f, text="No FCode ROM (the machine ROM's built-in driver takes over)",
                        variable=self.onboard_mode, value="none").grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="FCode ROM file:", variable=self.onboard_mode, value="file").grid(
            row=2, column=0, sticky="w")
        self.onboard_rom_var = tk.StringVar()
        FileRow(f, self.onboard_rom_var, "rom", ROM_TYPES, 2, 1)
        ttk.Label(f, text="ati_mach_gt.rom (Mac OS) or ati_gt_fcode.rom (Linux); a bare name is "
                          "looked up in the QEMU folder.", foreground="gray", wraplength=520).grid(
            row=3, column=1, columnspan=2, sticky="w")

        ttk.Separator(f).grid(row=4, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Label(f, text="Second graphics card (PCI slot)", font=("", 0, "bold")).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(f, text="Card:").grid(row=6, column=0, sticky="w")
        self.gpu_var = tk.StringVar(value=GPU_NONE)
        self._gpu_prev = GPU_NONE
        cb = ttk.Combobox(f, textvariable=self.gpu_var, values=GPU_CHOICES, state="readonly", width=36)
        cb.grid(row=6, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", self._gpu_changed)
        ttk.Label(f, text="PCI addr:").grid(row=7, column=0, sticky="w")
        self.gpu_addr_var = tk.StringVar(value="0x0e")
        ttk.Entry(f, textvariable=self.gpu_addr_var, width=8).grid(row=7, column=1, sticky="w")
        ttk.Label(f, text="Card ROM:").grid(row=8, column=0, sticky="w")
        self.gpu_rom_var = tk.StringVar()
        FileRow(f, self.gpu_rom_var, "rom", ROM_TYPES, 8, 1)
        ttk.Label(f, text="The user runs addr=0x0e with ati_nexus128_103_pci.rom. Entries below the "
                          "separator are unsupported and untested.", foreground="gray", wraplength=520).grid(
            row=9, column=1, columnspan=2, sticky="w")

    def _gpu_changed(self, _e=None):
        if self.gpu_var.get() == GPU_SEPARATOR:
            self.gpu_var.set(self._gpu_prev)
            return
        self._gpu_prev = self.gpu_var.get()
        if self.gpu_var.get() == GPU_RAGE and not self.gpu_rom_var.get():
            self.gpu_rom_var.set(SecondGpu().romfile or "")
            if not self.gpu_addr_var.get():
                self.gpu_addr_var.set(SecondGpu().addr)

    def _build_ata(self):
        f = self._tab("ATA")
        f.columnconfigure(2, weight=1)
        for c, h in enumerate(("Slot", "Type", "Image", "", "Format")):
            ttk.Label(f, text=h, foreground="gray").grid(row=0, column=c, sticky="w", padx=4)
        self.ata_rows = [DriveRow(f, i + 1, name, scsi=False) for i, name in enumerate(model.ATA_SLOT_NAMES)]
        ttk.Label(f, text="The ROM boots the lowest-index bootable disk when NVRAM says \"ROM decides\" "
                          "(which is what OS X's Startup Disk writes), so the OS you want as default "
                          "must be at index 0. Convention: hard disks at index 0 (and 1), CD at index 2; "
                          "QEMU adds a medialess phantom CD-ROM at index 2 if nothing claims it.",
                  foreground="gray", wraplength=640, justify="left").grid(
            row=6, column=0, columnspan=5, sticky="w", padx=4, pady=(10, 2))
        ttk.Button(f, text="Create disk image...", command=self._create_disk).grid(
            row=7, column=0, columnspan=2, sticky="w", padx=4, pady=6)

    def _build_scsi(self):
        f = self._tab("SCSI")
        f.columnconfigure(2, weight=1)
        for c, h in enumerate(("ID", "Type", "Image", "", "Format", "", "Vendor", "Product", "Ver")):
            ttk.Label(f, text=h, foreground="gray").grid(row=0, column=c, sticky="w", padx=4)
        self.scsi_rows = [DriveRow(f, sid + 1, f"scsi-id {sid}", scsi=True) for sid in model.SCSI_IDS]
        # id 7 is the computer: a fixed, non-editable row, never saved
        ttk.Label(f, text=f"scsi-id {model.SCSI_SELF_ID}").grid(row=8, column=0, sticky="w", padx=4, pady=1)
        self_row = ttk.Label(f, text="--  the Macintosh itself (MESH controller)", foreground="gray")
        self_row.grid(row=8, column=1, columnspan=8, sticky="w", padx=2, pady=1)
        ttk.Label(f, text="MESH controller, built in (id 7). The ROM prefers a SCSI CD over an ATA CD; "
                          "holding C at boot picks the first CD; Startup Disk overrides. "
                          "Identity strings are optional and prefilled with the user's values.",
                  foreground="gray", wraplength=760, justify="left").grid(
            row=9, column=0, columnspan=9, sticky="w", padx=4, pady=(10, 2))

    def _build_floppy(self):
        f = self._tab("Floppy")
        f.columnconfigure(1, weight=1)
        self.floppy_mode = tk.StringVar(value="none")
        ttk.Radiobutton(f, text="No floppy", variable=self.floppy_mode, value="none").grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Image:", variable=self.floppy_mode, value="file").grid(row=1, column=0, sticky="w")
        self.floppy_var = tk.StringVar()
        FileRow(f, self.floppy_var, "fd", FLOPPY_TYPES, 1, 1)
        ttk.Label(f, text="SWIM3 controller, built in. .img or .dsk, read and write both work. Emitted as "
                          "-drive if=none,id=fd,file=...,format=raw -global swim3.drive=fd",
                  foreground="gray", wraplength=520, justify="left").grid(row=2, column=1, columnspan=2, sticky="w")

    def _build_net_audio(self):
        f = self._tab("Network & Audio")
        ttk.Label(f, text="Network (onboard bmac)", font=("", 0, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Mode:").grid(row=1, column=0, sticky="w")
        self.net_mode = tk.StringVar(value="user")
        self.net_mode_cb = ttk.Combobox(f, textvariable=self.net_mode, state="readonly", width=16,
                                        values=model.network_modes_for_host())
        self.net_mode_cb.grid(row=1, column=1, sticky="w")
        self.net_mode_cb.bind("<<ComboboxSelected>>", self._net_mode_changed)
        ttk.Label(f, text="MAC:").grid(row=2, column=0, sticky="w")
        self.mac_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.mac_var, width=20).grid(row=2, column=1, sticky="w")
        ttk.Label(f, text="Interface (ifname):").grid(row=3, column=0, sticky="w")
        self.ifname_var = tk.StringVar()
        self.ifname_entry = ttk.Entry(f, textvariable=self.ifname_var, width=28)
        self.ifname_entry.grid(row=3, column=1, sticky="w")
        self.net_hint = ttk.Label(f, text="", foreground="gray", wraplength=560, justify="left")
        self.net_hint.grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Separator(f).grid(row=5, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Label(f, text="Audio (awacs)", font=("", 0, "bold")).grid(row=6, column=0, columnspan=3, sticky="w")
        self.audio_var = tk.StringVar(value="default")
        default_name = {"darwin": "coreaudio", "win32": "dsound"}.get(
            "win32" if paths.is_windows() else paths.HOST_PLATFORM, "sdl")
        ttk.Radiobutton(f, text=f"Platform default ({default_name} here)", variable=self.audio_var,
                        value="default").grid(row=7, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="sdl", variable=self.audio_var, value="sdl").grid(row=8, column=0, sticky="w")
        ttk.Radiobutton(f, text="none (boots over Remote Desktop)", variable=self.audio_var,
                        value="none").grid(row=9, column=0, columnspan=3, sticky="w")

    NET_HINTS = {
        "none": "-nic none: the guest sees no network.",
        "user": "-nic user,model=bmac,mac=...: user-mode NAT, no setup needed (default).",
        "vmnet-bridged": "-nic vmnet-bridged,ifname=<if>,model=bmac,mac=...: guest joins the LAN of the "
                         "host interface (en0 = first Ethernet/Wi-Fi). macOS only.",
        "vmnet-shared": "-nic vmnet-shared,model=bmac,mac=...: NAT through Apple's vmnet with DHCP. macOS only.",
        "vmnet-host": "-nic vmnet-host,model=bmac,mac=...: host-only network. macOS only.",
        "tap": "-nic tap,ifname=<adapter>,model=bmac,mac=...: needs an installed TAP-Windows adapter "
               "(OpenVPN); ifname = its name as shown in Network Connections. Windows only.",
    }
    SUDO_HINT = ("vmnet needs root: run.command runs QEMU under sudo, Start opens it in Terminal, which asks "
                 "for the password (the GUI never sees it). Files QEMU creates under sudo (nvram.img, "
                 "pram.img) become root-owned; the launcher chowns them back to you afterwards.")

    def _net_mode_changed(self, _e=None):
        mode = self.net_mode.get()
        hint = self.NET_HINTS.get(mode, "")
        if mode.startswith("vmnet-"):
            hint += "\n" + self.SUDO_HINT
        self.net_hint.config(text=hint)
        if mode in model.NETWORK_MODES_WITH_IFNAME:
            self.ifname_entry.config(state="normal")
            if not self.ifname_var.get():
                self.ifname_var.set(model.default_ifname(mode))
        else:
            self.ifname_entry.config(state="disabled")

    def _build_advanced(self):
        f = self._tab("Advanced")
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Calibration governor (-M g3beige,calibration-governor=...)",
                  font=("", 0, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        self.gov_mode = tk.StringVar(value="default")
        ttk.Radiobutton(f, text="Default (on, 79 MIPS; emits nothing)", variable=self.gov_mode,
                        value="default").grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Off", variable=self.gov_mode, value="off").grid(row=2, column=0, sticky="w")
        ttk.Radiobutton(f, text="Custom MIPS:", variable=self.gov_mode, value="mips").grid(row=3, column=0, sticky="w")
        self.mips_var = tk.StringVar(value="100")
        ttk.Spinbox(f, textvariable=self.mips_var, from_=1, to=100000, width=8).grid(row=3, column=1, sticky="w")
        ttk.Separator(f).grid(row=4, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Label(f, text="Extra arguments (appended verbatim):").grid(row=5, column=0, columnspan=3, sticky="w")
        self.extra_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.extra_var, width=80).grid(row=6, column=0, columnspan=3, sticky="ew")
        ttk.Label(f, text="e.g. -qmp unix:/tmp/g92live.sock,server=on,wait=off   or   "
                          "-global ati-mach64-gt.host-cursor-tracking=off",
                  foreground="gray", wraplength=600, justify="left").grid(row=7, column=0, columnspan=3, sticky="w")

    # ---------------- load / collect
    def load(self, m: Machine):
        self.name_var.set(m.name)
        self.profile_var.set(PROFILES[m.profile].label)
        self.ram_var.set(str(m.ram_mb))
        self.rom_var.set(m.rom)
        self.display_var.set(m.display)
        self.qemu_dir_var.set(m.qemu_dir or "")
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", m.notes)
        self.onboard_mode.set("file" if m.onboard_romfile else "none")
        self.onboard_rom_var.set(m.onboard_romfile or "")
        if m.second_gpu:
            dev = m.second_gpu.device
            self.gpu_var.set(GPU_RAGE if dev == "ati-rage128-pro" else dev if dev in GPU_CHOICES else GPU_NONE)
            self.gpu_addr_var.set(m.second_gpu.addr or "")
            self.gpu_rom_var.set(m.second_gpu.romfile or "")
        else:
            self.gpu_var.set(GPU_NONE)
            self.gpu_addr_var.set(SecondGpu().addr)
            self.gpu_rom_var.set("")
        self._gpu_prev = self.gpu_var.get()
        for i, row in enumerate(self.ata_rows):
            row.set_ata(m.ata[i] if i < len(m.ata) else None)
        for sid, row in enumerate(self.scsi_rows):
            row.set_scsi(m.scsi_by_id(sid))
        self.floppy_mode.set("file" if m.floppy else "none")
        self.floppy_var.set(m.floppy.file if m.floppy else "")
        self.net_mode_cb.config(values=model.network_modes_for_host(current=m.network.mode))
        self.net_mode.set(m.network.mode)
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
        m.profile = profile_by_label(self.profile_var.get()).id
        try:
            m.ram_mb = int(self.ram_var.get().strip())
        except ValueError:
            m.ram_mb = -1
        m.rom = self.rom_var.get().strip() or "PowerMacG3v3.ROM"
        m.display = self.display_var.get()
        m.qemu_dir = self.qemu_dir_var.get().strip() or None
        m.notes = self.notes.get("1.0", "end").rstrip("\n")
        m.onboard_romfile = self.onboard_rom_var.get().strip() or None if self.onboard_mode.get() == "file" else None
        g = self.gpu_var.get()
        if g == GPU_NONE or g == GPU_SEPARATOR:
            m.second_gpu = None
        else:
            dev = "ati-rage128-pro" if g == GPU_RAGE else g
            m.second_gpu = SecondGpu(dev, self.gpu_addr_var.get().strip(),
                                     self.gpu_rom_var.get().strip() or None)
        m.ata = [row.get_ata() for row in self.ata_rows]
        m.scsi = [d for d in (row.get_scsi(sid) for sid, row in enumerate(self.scsi_rows)) if d]
        if self.floppy_mode.get() == "file" and self.floppy_var.get().strip():
            m.floppy = Floppy(self.floppy_var.get().strip(), "raw")
        else:
            m.floppy = None
        mode = self.net_mode.get()
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
    def _reapply_profile(self):
        p = profile_by_label(self.profile_var.get())
        if not messagebox.askyesno("Profile", f"Reset RAM, display, second card, onboard ROM and the "
                                              f"ATA slot types to the '{p.label}' defaults?", parent=self):
            return
        cur = self.collect()
        seeded = model.new_machine(cur.name, p.id, cur.effective_qemu_dir(self.global_qemu_dir))
        cur.ram_mb, cur.display = seeded.ram_mb, seeded.display
        cur.second_gpu, cur.onboard_romfile = seeded.second_gpu, seeded.onboard_romfile
        for i, k in enumerate(p.ata_default):
            if k and cur.ata[i] is None:
                cur.ata[i] = AtaDrive(kind=k)
        if not cur.notes:
            cur.notes = seeded.notes
        self.load(cur)

    def _create_disk(self):
        cur = self.collect()
        folder = self.library.folder(cur.name or self.old_name)
        dlg = CreateDiskDialog(self, cur, folder, cur.effective_qemu_dir(self.global_qemu_dir))
        if not dlg.result:
            return
        path, fmt, place = dlg.result
        if place and place[0] == "ata":
            row = self.ata_rows[place[1]]
            row.set_ata(AtaDrive("disk", path, fmt))
        elif place and place[0] == "scsi":
            row = self.scsi_rows[place[1]]
            row.set_scsi(ScsiDrive(place[1], "disk", path, fmt, None))
        self.msg.config(text=f"Created {path}")

    def save(self):
        m = self.collect()
        errors, warnings = model.validate(m, self.global_qemu_dir)
        if m.name != self.old_name and self.library.exists(m.name):
            errors.append(f"A machine named '{m.name}' already exists.")
        self.msg.config(text="; ".join(errors + warnings)[:300])
        if not show_validation(self, errors, warnings):
            return
        try:
            self.on_save(m, self.old_name)
        except (OSError, ValueError) as e:
            messagebox.showerror("Save", str(e), parent=self)
            return
        self.destroy()
