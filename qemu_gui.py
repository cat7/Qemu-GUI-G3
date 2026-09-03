#!/usr/bin/env python3
"""Qemu-GUI entry point: a portable launcher for the QEMU Beige G3 machine.

    python qemu_gui.py [--settings FILE] [--library DIR] [--qemu-dir DIR]

Standard library only (tkinter). See README.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qemugui import paths  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--settings", help="settings.json to use (default: per-user location)")
    ap.add_argument("--library", help="machine library folder (overrides and saves the setting)")
    ap.add_argument("--qemu-dir", help="folder with qemu-system-ppc, qemu-img and ROMs (overrides and saves)")
    args = ap.parse_args(argv)

    settings_path = Path(args.settings) if args.settings else paths.settings_path()
    settings = paths.Settings.load(settings_path)
    if args.library:
        settings.library_dir = args.library
    if args.qemu_dir:
        settings.qemu_dir = args.qemu_dir
    try:
        settings.save(settings_path)
    except OSError as e:
        print(f"warning: cannot save settings to {settings_path}: {e}", file=sys.stderr)

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("This Python has no tkinter. On macOS use the python.org installer or a venv made "
              "from it (Homebrew's python3 lacks _tkinter); on Windows tick 'tcl/tk' in the "
              "python.org installer.", file=sys.stderr)
        return 2

    from qemugui.ui_main import MainWindow
    app = MainWindow(settings, settings_path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
