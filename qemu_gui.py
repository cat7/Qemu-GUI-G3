#!/usr/bin/env python3
"""Qemu-system-ppc GUI: start an emulated PowerMac G3.

Qemu-system-ppc GUI runs from the folder that holds qemu-system-ppc and keeps its
machines in a "Machines" folder next to itself. There is nothing to
configure and nothing to point at.

    python qemu_gui.py

Standard library only (tkinter). See README.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qemugui import paths  # noqa: E402

NO_TKINTER = """\
Qemu-system-ppc GUI needs Python's tkinter, and this Python does not have it.

On macOS, install Python from python.org (Homebrew's python3 has no tkinter).
On Windows, re-run the python.org installer and tick "tcl/tk and IDLE".\
"""

EXIT_CANNOT_RUN = 3
EXIT_NO_TKINTER = 2


def report_problem_on_screen(message: str) -> None:
    """Say it in a window if we can, and on the terminal either way."""
    print(message, file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        return
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Qemu-system-ppc GUI", message)
        root.destroy()
    except Exception:      # no display: the terminal message stands
        pass


def main(argv=None, report_problem=None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    report = report_problem or report_problem_on_screen

    problem = paths.startup_problem()
    if problem:
        report(problem)
        return EXIT_CANNOT_RUN

    try:
        import tkinter  # noqa: F401
    except ImportError:
        report(NO_TKINTER)
        return EXIT_NO_TKINTER

    from qemugui.ui_main import MainWindow
    settings_file = paths.settings_path()
    app = MainWindow(paths.Settings.load(settings_file), settings_file)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
