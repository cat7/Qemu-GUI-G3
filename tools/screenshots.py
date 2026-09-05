#!/usr/bin/env python3
"""Open the real GUI (MainWindow + mainloop) on a scratch install and capture
the main window and the Machine tab of a New machine, with
`screencapture -x -R`.

    python tools/screenshots.py <install-dir> <out-dir>
"""
import subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from qemugui import model, paths
from qemugui.systems import system_ids
from qemugui.ui_main import MainWindow
from qemugui.ui_machine import MachineEditor

paths.use_install_dir(Path(sys.argv[1]))
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
settings_file = paths.settings_path()
app = MainWindow(paths.Settings.load(settings_file), settings_file)

def region(w):
    w.update_idletasks()
    x, y = w.winfo_rootx(), w.winfo_rooty()
    return f"{x - 2},{y - 30},{w.winfo_width() + 4},{w.winfo_height() + 34}"   # include title bar

def capture(w, name):
    r = subprocess.run(["screencapture", "-x", "-R", region(w), str(out / name)], capture_output=True, text=True)
    print(name, "rc", r.returncode, r.stderr.strip())

def step1():
    app.lift(); app.attributes("-topmost", True); app.update()
    capture(app, "screenshot-main.png")
    app.attributes("-topmost", False)
    # exactly what "New machine…" does: the settings window, Machine page
    m = model.new_machine("", system_ids()[0])
    ed = MachineEditor(app, m, app.library, str(paths.install_dir()), lambda *a: None,
                       is_new=True)
    ed.lift(); ed.attributes("-topmost", True)
    app.after(3000, lambda: step2(ed))

def step2(ed):
    capture(ed, "screenshot-new-machine-tab.png")
    ed.destroy()
    app.after(500, app.destroy)

app.after(3000, step1)
app.mainloop()
