#!/usr/bin/env python3
"""Smoke boot through the GUI's own Start path (MainWindow.start_selected).

Scratch only: a fresh 1 GB raw disk in Drive 1 and 8.1.iso as the CD in
Drive 3, cwd = the scratch machine folder, quit through QMP after 20 s.
Never points at /Volumes/Macdata/qemu/hd/.

The scratch folder is made to look like an install: the emulator is linked
into it and paths.use_install_dir() points the program at it, so nothing is
written next to the real emulator. Usage:

    python tools/smoke_boot.py <scratch-dir> <qemu-dir> <8.1.iso>
"""
import json, os, signal, socket, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from qemugui import paths, model  # noqa: E402
from qemugui.model import Machine, AtaDrive, SecondGpu, Network  # noqa: E402
from qemugui.ui_main import MainWindow  # noqa: E402

BAD = ("invalid option", "could not open", "Property .* not found", "not a valid")

scratch = Path(sys.argv[1]).resolve()
qemu_dir = Path(sys.argv[2]).resolve()
iso = sys.argv[3]
assert not str(iso).startswith("/Volumes/Macdata/qemu/hd/")

# make the scratch folder look like an install of the program
scratch.mkdir(parents=True, exist_ok=True)
for name in (paths.qemu_binary_name(), paths.qemu_img_name()):
    link = scratch / name
    if not link.exists():
        link.symlink_to(qemu_dir / name)
paths.use_install_dir(scratch)
folder = paths.machines_dir() / "smoke"
sock_path = scratch / "qmp.sock"
if sock_path.exists():
    sock_path.unlink()

settings_file = paths.settings_path()
settings = paths.Settings()
settings_file.parent.mkdir(parents=True, exist_ok=True)
settings.save(settings_file)

lib = model.Library()
m = Machine(name="smoke", profile="custom", ram_mb=512,
            rom=str(qemu_dir / "PowerMacG3v3.ROM"),
            display="cocoa", audio="none",
            onboard_romfile=str(qemu_dir / "ati_mach_gt.rom"),
            second_gpu=SecondGpu("ati-rage128-pro", "0x0e",
                                 str(qemu_dir / "ati_nexus128_103_pci.rom")),
            network=Network(mode="none"),
            ata=[AtaDrive("disk", str(folder / "smoke.img"), "raw"), None, AtaDrive("cdrom", iso, "raw"), None],
            extra_args=f"-qmp unix:{sock_path},server=on,wait=off",
            notes="scratch smoke machine")
folder.mkdir(parents=True, exist_ok=True)
lib.save(m)
lib.clear_saved_settings("smoke")
errors, warnings = model.validate(m, str(paths.install_dir()), machine_dir=str(folder))
print("validate:", errors, warnings)
assert not errors

app = MainWindow(settings, settings_file)
app.update()
app.tree.selection_set("smoke")
app.on_select()
r = app.start_selected()
assert r is not None, "start_selected refused"
print(f"started pid {r.pid} at {time.strftime('%H:%M:%S')}")
print("argv:", " ".join(r.argv))

def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.1)

pump(20)
alive = r.poll() is None
print(f"alive after 20 s: {alive} (uptime {r.uptime():.1f} s); GUI run status: {app.run_status.cget('text')!r}")
log_text = (folder / "last-run.log").read_text(errors="replace")
import re
bad_lines = [ln for ln in log_text.splitlines() if any(re.search(p, ln) for p in BAD)]
print("bad log lines:", bad_lines)
sizes = {f: ((folder / f).stat().st_size if (folder / f).exists() else None)
         for f in model.SAVED_SETTINGS_FILES}
print("managed files:", sizes)

# quit via QMP
quit_ok = False
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(str(sock_path))
    greeting = s.recv(4096)
    s.sendall(b'{"execute":"qmp_capabilities"}\n'); s.recv(4096)
    s.sendall(b'{"execute":"quit"}\n')
    try:
        s.recv(4096)
    except OSError:
        pass
    s.close()
    quit_ok = True
    print("QMP quit sent; greeting:", greeting[:80])
except OSError as e:
    print("QMP unreachable:", e)

deadline = time.time() + 15
while r.poll() is None and time.time() < deadline:
    pump(0.5)
if r.poll() is None:
    print(f"still alive after QMP quit; kill {r.pid}")
    os.kill(r.pid, signal.SIGTERM)
    pump(3)
print(f"exit code: {r.poll()}; GUI run status: {app.run_status.cget('text')!r}")
app.update()
app.destroy()
result = {"pid": r.pid, "alive_after_20s": alive, "uptime_at_check": round(r.uptime(), 1),
          "bad_log_lines": bad_lines, "managed_files": sizes, "qmp_quit": quit_ok,
          "exit_code": r.exit_code}
(scratch / "smoke-result.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
ok = alive and not bad_lines and sizes["nvram.img"] == 8192 and sizes["pram.img"] == 256
print("SMOKE", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
