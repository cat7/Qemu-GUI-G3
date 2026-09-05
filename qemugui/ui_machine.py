"""The machine editor: Machine, Display, Drives, Network & sound, Advanced.

The wording rule for this file: say what the setting does for the person, not
what the hardware calls it. The Machine page carries no explanations at all --
it is the page of plain settings.

Two rules with teeth:

* **Nothing is ever filled in for you.** Every field that names a file starts
  empty and stays empty until it is chosen, the Mac's own ROM included.
* A file is picked with one control: the field *is* the chooser. There is no
  separate label and no separate button beside it.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from . import model, paths
from .model import Machine, AtaDrive, ScsiDrive, Identity, Floppy, SecondGpu, Network, Governor
from .profiles import PROFILES, profile_labels, profile_by_label
from .ui_dialogs import show_validation, CreateDiskDialog

KIND_LABELS = {"": "Empty", "disk": "Hard disk", "cdrom": "CD"}
KIND_BY_LABEL = {v: k for k, v in KIND_LABELS.items()}
GPU_NONE = "None"
GPU_RAGE = "ATI Rage 128 Pro — the one that works"
GPU_SEPARATOR = "──── untested, likely to fail ────"
GPU_CHOICES = [GPU_NONE, GPU_RAGE, GPU_SEPARATOR, *model.SECOND_GPU_EXPERIMENTAL]
IMAGE_TYPES = [("Hard disks and CDs", "*.img *.dsk *.qcow2 *.iso *.toast *.cdr"),
               ("Every file", "*")]
ROM_TYPES = [("ROM files", "*.rom *.ROM *.bin"), ("Every file", "*")]
FLOPPY_TYPES = [("Floppy disks", "*.img *.dsk"), ("Every file", "*")]
CDROM_EXTS = {".iso", ".toast", ".cdr", ".dmg"}

GREY = "gray"

# The settings window is two thirds of the width it used to be (it asked for
# 1220 pixels before the SCSI and Floppy pages moved into Drives).
EDITOR_WIDTH = 813
TEXT_WIDTH = EDITOR_WIDTH - 150         # wrapping width for the paragraphs


def browse_file(parent, var: tk.StringVar, filetypes, fallback: Path | str | None = None) -> None:
    start = paths.browse_start_dir(var.get(), fallback)
    f = filedialog.askopenfilename(parent=parent, initialdir=str(start), filetypes=filetypes)
    if f:
        var.set(f)


class FilePicker:
    """One control for one file: it shows what has been chosen and opens the
    chooser when clicked. Empty until somebody picks something."""

    PLACEHOLDER = "Click to choose a file…"

    def __init__(self, master, var: tk.StringVar, filetypes, width: int = 40, fallback=None):
        self.var = var
        self.filetypes = filetypes
        self.fallback = fallback
        self.shown = tk.StringVar()
        self.entry = ttk.Entry(master, textvariable=self.shown, width=width,
                               state="readonly", cursor="hand2")
        for seq in ("<Button-1>", "<Return>", "<space>"):
            self.entry.bind(seq, self._browse)
        self.var.trace_add("write", lambda *_a: self._refresh())
        self._refresh()

    def grid(self, **kw) -> "FilePicker":
        self.entry.grid(**kw)
        return self

    def _refresh(self) -> None:
        value = self.var.get().strip()
        self.shown.set(value or self.PLACEHOLDER)
        if value:
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
    """Change one machine. ``on_save(machine, old_name)`` runs after checking."""

    def __init__(self, parent, machine: Machine, library: model.Library, qemu_dir: str, on_save):
        super().__init__(parent)
        self.machine = machine.copy()
        self.old_name = machine.name
        self.library = library
        self.qemu_dir = qemu_dir
        self.on_save = on_save
        self.title(f"{machine.name} — settings")
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
        self.msg = ttk.Label(bar, text="", foreground=GREY, wraplength=TEXT_WIDTH - 160)
        self.msg.pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=2)
        ttk.Button(bar, text="Save", command=self.save).pack(side="right", padx=2)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.load(self.machine)
        self._size_window()

    def _size_window(self):
        """Two thirds of the width the window used to ask for, and no taller
        than the screen it has to fit on."""
        self.update_idletasks()
        height = min(self.winfo_reqheight(), max(400, self.winfo_screenheight() - 160))
        self.geometry(f"{EDITOR_WIDTH}x{height}")
        self.minsize(640, 400)

    def machine_folder(self) -> Path:
        return self.library.folder(self.name_var.get().strip() or self.old_name)

    # ---------------- tabs
    def _tab(self, title: str) -> ttk.Frame:
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text=title)
        return f

    @staticmethod
    def _hint(master, text: str, row: int, col: int = 1, span: int = 2,
              width: int = TEXT_WIDTH - 190):     # a hint sits beside a label column
        ttk.Label(master, text=text, foreground=GREY, wraplength=width, justify="left").grid(
            row=row, column=col, columnspan=span, sticky="w", padx=4)

    # -------- the plain settings, no explanations
    def _build_machine(self):
        f = self._tab("Machine")
        f.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(f, text="Name:").grid(row=r, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.name_var, width=40).grid(row=r, column=1, sticky="ew", pady=4)
        r += 1
        ttk.Label(f, text="System:").grid(row=r, column=0, sticky="w", pady=4)
        self.profile_var = tk.StringVar()
        ttk.Combobox(f, textvariable=self.profile_var, values=profile_labels(), state="readonly",
                     width=26).grid(row=r, column=1, sticky="w", pady=4)
        r += 1
        ttk.Label(f, text="Memory:").grid(row=r, column=0, sticky="w", pady=4)
        self.ram_var = tk.StringVar()
        ttk.Combobox(f, textvariable=self.ram_var, values=[str(x) for x in model.RAM_CHOICES],
                     width=10).grid(row=r, column=1, sticky="w", pady=4)
        r += 1
        ttk.Label(f, text="Display:").grid(row=r, column=0, sticky="w", pady=4)
        self.display_var = tk.StringVar()
        displays = model.DISPLAYS.get("win32" if paths.is_windows() else paths.HOST_PLATFORM,
                                      ("sdl", "gtk"))
        ttk.Combobox(f, textvariable=self.display_var, values=list(displays), state="readonly",
                     width=10).grid(row=r, column=1, sticky="w", pady=4)
        r += 1
        ttk.Label(f, text="ROM:").grid(row=r, column=0, sticky="w", pady=4)
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
        ttk.Label(f, text="The graphics built into the Mac",
                  font=("", 0, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 2))
        ttk.Label(f, text="This Mac always has its own graphics. Mac OS needs a small startup "
                          "file for the card before it will draw on it.",
                  foreground=GREY, wraplength=TEXT_WIDTH, justify="left").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.onboard_mode = tk.StringVar(value="none")
        ttk.Radiobutton(f, text="Let the Mac's own ROM handle it",
                        variable=self.onboard_mode, value="none").grid(
            row=2, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Use this card startup file:", variable=self.onboard_mode,
                        value="file").grid(row=3, column=0, sticky="w")
        self.onboard_rom_var = tk.StringVar()
        FilePicker(f, self.onboard_rom_var, ROM_TYPES, width=40,
                   fallback=lambda: self.qemu_dir).grid(row=3, column=1, columnspan=2,
                                                        sticky="ew", padx=2)
        self._hint(f, "ati_mach_gt.rom for Mac OS, ati_gt_fcode.rom for Linux.", 4)

        ttk.Separator(f).grid(row=5, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(f, text="An extra graphics card",
                  font=("", 0, "bold")).grid(row=6, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Mac OS 9 and Mac OS X are much happier with a proper graphics card "
                          "plugged in, and it is what most people here use.",
                  foreground=GREY, wraplength=TEXT_WIDTH, justify="left").grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(f, text="Card:").grid(row=8, column=0, sticky="w")
        self.gpu_var = tk.StringVar(value=GPU_NONE)
        self._gpu_prev = GPU_NONE
        cb = ttk.Combobox(f, textvariable=self.gpu_var, values=GPU_CHOICES, state="readonly",
                          width=38)
        cb.grid(row=8, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", self._gpu_changed)
        ttk.Label(f, text="Card startup file:").grid(row=9, column=0, sticky="w", pady=(6, 0))
        self.gpu_rom_var = tk.StringVar()
        FilePicker(f, self.gpu_rom_var, ROM_TYPES, width=40,
                   fallback=lambda: self.qemu_dir).grid(row=9, column=1, columnspan=2,
                                                        sticky="ew", padx=2, pady=(6, 0))
        self._hint(f, "ati_nexus128_103_pci.rom. Without it Mac OS will not put a picture on "
                      "the card.", 10)
        ttk.Label(f, text="Which slot:").grid(row=11, column=0, sticky="w", pady=(6, 0))
        self.gpu_addr_var = tk.StringVar(value=SecondGpu().addr)
        ttk.Entry(f, textvariable=self.gpu_addr_var, width=8).grid(
            row=11, column=1, sticky="w", pady=(6, 0))
        self._hint(f, "Which of the Mac's expansion slots the card is plugged into. Leave this "
                      "at 0x0e unless you have a reason.", 12)

    def _gpu_changed(self, _e=None):
        """Choosing a card never chooses its ROM file: that is a file, and
        files are picked by the person."""
        if self.gpu_var.get() == GPU_SEPARATOR:
            self.gpu_var.set(self._gpu_prev)
            return
        self._gpu_prev = self.gpu_var.get()
        if self.gpu_var.get() != GPU_NONE and not self.gpu_addr_var.get():
            self.gpu_addr_var.set(SecondGpu().addr)

    # -------- every drive this Mac can have: the four inside, the SCSI chain,
    #          and the floppy drive
    def _build_drives(self):
        f = self._tab("Drives")
        f.columnconfigure(0, weight=1)
        r = 0
        ttk.Label(f, text="The Mac has room for four drives inside it. Put your hard disk in "
                          "the first one and your CD in the third: that is what the Mac itself "
                          "expects, and it starts up from the first one.",
                  wraplength=TEXT_WIDTH, justify="left").grid(
            row=r, column=0, sticky="w", padx=4, pady=(0, 6))
        r += 1
        ata = ttk.Frame(f)
        ata.grid(row=r, column=0, sticky="ew")
        ata.columnconfigure(2, weight=1)
        for c, h in enumerate(("Position", "", "", "Format")):
            ttk.Label(ata, text=h, foreground=GREY).grid(row=0, column=c, sticky="w", padx=4)
        self.ata_rows = [DriveRow(ata, 1 + i, model.ata_slot_name(i), scsi=False,
                                  fallback=self.machine_folder)
                         for i in range(len(model.ATA_SLOTS))]
        r += 1
        ttk.Button(f, text="Create new disk image…", command=self._create_disk).grid(
            row=r, column=0, sticky="w", padx=4, pady=(8, 4))
        r += 1
        ttk.Separator(f).grid(row=r, column=0, sticky="ew", pady=8)
        r += 1
        ttk.Label(f, text="The SCSI chain", font=("", 0, "bold")).grid(
            row=r, column=0, sticky="w", padx=4)
        r += 1
        ttk.Label(f, text="This Mac also has a SCSI chain — the connector older Macs used for "
                          "hard disks and CD drives. Every device on it has its own number so "
                          "the Mac can tell them apart. Numbers 0 to 6 are yours to use; "
                          "number 7 is the Mac itself. Most people can leave this alone; it is "
                          "worth using when the system you are installing expects a SCSI CD, "
                          "as Mac OS 8.1 does.",
                  wraplength=TEXT_WIDTH, justify="left").grid(
            row=r, column=0, sticky="w", padx=4, pady=(0, 6))
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
        ttk.Label(scsi, text=model.SCSI_SELF_HINT, foreground=GREY,
                  wraplength=TEXT_WIDTH - 90, justify="left").grid(
            row=self_row, column=1, columnspan=7, sticky="w", padx=2, pady=1)
        r += 1
        ttk.Label(f, text="“Pretend” makes the drive introduce itself to the Mac as a real make "
                          "and model. Some old installers only accept drives they recognise; if "
                          "in doubt, leave it off.\n"
                          "The Mac prefers a SCSI CD over the CD in Drive 3. Holding down the "
                          "C key while it starts makes it use the first CD it finds, and "
                          "whatever you chose in the Startup Disk control panel wins over both.",
                  foreground=GREY, wraplength=TEXT_WIDTH, justify="left").grid(
            row=r, column=0, sticky="w", padx=4, pady=(8, 2))
        r += 1
        ttk.Separator(f).grid(row=r, column=0, sticky="ew", pady=8)
        r += 1
        ttk.Label(f, text="The floppy drive", font=("", 0, "bold")).grid(
            row=r, column=0, sticky="w", padx=4)
        r += 1
        fd = ttk.Frame(f)
        fd.grid(row=r, column=0, sticky="ew")
        fd.columnconfigure(1, weight=1)
        self.floppy_mode = tk.StringVar(value="none")
        ttk.Radiobutton(fd, text="Nothing in the drive", variable=self.floppy_mode,
                        value="none").grid(row=0, column=0, columnspan=2, sticky="w", padx=4)
        ttk.Radiobutton(fd, text="This floppy disk:", variable=self.floppy_mode,
                        value="file").grid(row=1, column=0, sticky="w", padx=4)
        self.floppy_var = tk.StringVar()
        FilePicker(fd, self.floppy_var, FLOPPY_TYPES, width=44,
                   fallback=self.machine_folder).grid(row=1, column=1, sticky="ew", padx=2)

    def _build_net_audio(self):
        f = self._tab("Network & sound")
        ttk.Label(f, text="Network", font=("", 0, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="How the old Mac reaches the outside world, through the Ethernet "
                          "socket it was built with.", foreground=GREY, wraplength=TEXT_WIDTH,
                  justify="left").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(f, text="Connection:").grid(row=2, column=0, sticky="w")
        self.net_mode = tk.StringVar(value="user")
        self.net_mode_cb = ttk.Combobox(f, textvariable=self.net_mode, state="readonly", width=18,
                                        values=model.network_modes_for_host())
        self.net_mode_cb.grid(row=2, column=1, sticky="w")
        self.net_mode_cb.bind("<<ComboboxSelected>>", self._net_mode_changed)
        ttk.Label(f, text="Which connection here:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.ifname_var = tk.StringVar()
        self.ifname_entry = ttk.Entry(f, textvariable=self.ifname_var, width=28)
        self.ifname_entry.grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Label(f, text="Card address:").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.mac_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.mac_var, width=22).grid(
            row=4, column=1, sticky="w", pady=(6, 0))
        ttk.Label(f, text="The Mac's network card needs a hardware address. Any is fine; only "
                          "change it if two of your machines are on the network at once.",
                  foreground=GREY, wraplength=TEXT_WIDTH, justify="left").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.net_hint = ttk.Label(f, text="", foreground=GREY, wraplength=TEXT_WIDTH,
                                  justify="left")
        self.net_hint.grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Separator(f).grid(row=7, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(f, text="Sound", font=("", 0, "bold")).grid(
            row=8, column=0, columnspan=3, sticky="w")
        self.audio_var = tk.StringVar(value="default")
        ttk.Radiobutton(f, text="Play through this computer's speakers",
                        variable=self.audio_var, value="default").grid(
            row=9, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Play through SDL, if the usual way misbehaves",
                        variable=self.audio_var, value="sdl").grid(
            row=10, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="No sound at all", variable=self.audio_var, value="none").grid(
            row=11, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Turn the sound off if you are connecting from another computer over "
                          "Remote Desktop, where sound can stop the Mac from starting.",
                  foreground=GREY, wraplength=TEXT_WIDTH, justify="left").grid(
            row=12, column=0, columnspan=3, sticky="w", pady=(2, 0))

    NET_HINTS = {
        "none": "The Mac has no network at all, as if the cable were unplugged.",
        "user": "The Mac can reach the internet through this computer, and nothing on your "
                "network can see it. This needs no setting up and is the right choice for "
                "almost everyone.",
        "vmnet-bridged": "The Mac appears on your home network in its own right, with its own "
                         "address, so other computers can see it and share files with it. Name "
                         "the connection this computer uses — usually en0. Macs only, and it "
                         "asks for your password.",
        "vmnet-shared": "The Mac shares this computer's network connection and is given an "
                        "address automatically. Macs only, and it asks for your password.",
        "vmnet-host": "The Mac can talk to this computer and to nothing else. Macs only, and it "
                      "asks for your password.",
        "tap": "The Mac appears on your network through a TAP adapter, which has to be installed "
               "beforehand (it comes with OpenVPN). Name it exactly as it appears in Network "
               "Connections. Windows only.",
    }
    SUDO_HINT = ("Because this puts the Mac on the real network, it needs an administrator "
                 "password. Start opens a Terminal window that asks for it; your password is "
                 "never seen by this program. That window is where the Mac then runs.")

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
        ttk.Label(f, text="Nothing on this page needs changing to run an old Mac.",
                  foreground=GREY, wraplength=TEXT_WIDTH, justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(f, text="How fast the Mac pretends to be", font=("", 0, "bold")).grid(
            row=1, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="The emulator keeps the old Mac's clock believable. Leave this alone "
                          "unless time inside the Mac runs visibly wrong.",
                  foreground=GREY, wraplength=TEXT_WIDTH, justify="left").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.gov_mode = tk.StringVar(value="default")
        ttk.Radiobutton(f, text="Normal", variable=self.gov_mode, value="default").grid(
            row=3, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Don't manage it at all", variable=self.gov_mode,
                        value="off").grid(row=4, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Pretend this speed:", variable=self.gov_mode, value="mips").grid(
            row=5, column=0, sticky="w")
        self.mips_var = tk.StringVar(value="100")
        ttk.Spinbox(f, textvariable=self.mips_var, from_=1, to=100000, width=8).grid(
            row=5, column=1, sticky="w")
        ttk.Separator(f).grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(f, text="Extra options for the emulator", font=("", 0, "bold")).grid(
            row=7, column=0, columnspan=3, sticky="w")
        self.extra_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.extra_var, width=70).grid(
            row=8, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        ttk.Label(f, text="Added to the end of the command, word for word. For example "
                          "-global ati-mach64-gt.host-cursor-tracking=off. A mistake here stops "
                          "the Mac from starting; empty it again if that happens.",
                  foreground=GREY, wraplength=TEXT_WIDTH, justify="left").grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(2, 0))

    # ---------------- load / collect
    def load(self, m: Machine):
        self.name_var.set(m.name)
        self.profile_var.set(PROFILES[m.profile].label)
        self.ram_var.set(str(m.ram_mb))
        self.rom_var.set(m.rom)
        self.display_var.set(m.display)
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", m.notes)
        self.onboard_mode.set("file" if m.onboard_romfile else "none")
        self.onboard_rom_var.set(m.onboard_romfile or "")
        if m.second_gpu:
            dev = m.second_gpu.device
            self.gpu_var.set(GPU_RAGE if dev == "ati-rage128-pro"
                             else dev if dev in GPU_CHOICES else GPU_NONE)
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
        m.rom = self.rom_var.get().strip()          # empty until it is chosen
        m.display = self.display_var.get()
        m.notes = self.notes.get("1.0", "end").rstrip("\n")
        m.onboard_romfile = (self.onboard_rom_var.get().strip() or None
                             if self.onboard_mode.get() == "file" else None)
        g = self.gpu_var.get()
        if g in (GPU_NONE, GPU_SEPARATOR):
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
    def _create_disk(self):
        cur = self.collect()
        dlg = CreateDiskDialog(self, cur, self.machine_folder())
        if not dlg.result:
            return
        path, fmt, place = dlg.result
        if place and place[0] == "ata":
            self.ata_rows[place[1]].set_ata(AtaDrive("disk", path, fmt))
        elif place and place[0] == "scsi":
            self.scsi_rows[place[1]].set_scsi(ScsiDrive(place[1], "disk", path, fmt, None))
        self.msg.config(text=f"Made {Path(path).name}. Press Save to keep it.")

    def save(self):
        m = self.collect()
        errors, warnings = model.validate(m, self.qemu_dir,
                                          machine_dir=str(self.library.folder(m.name or self.old_name)))
        if m.name != self.old_name and self.library.exists(m.name):
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
