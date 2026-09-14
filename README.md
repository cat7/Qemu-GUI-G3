# Qemu-system-ppc GUI

A portable launcher for the `g3beige` machine (beige Power Mac G3) of the
`g3beige` branch of `qemu-system-ppc` (github.com/cat7/qemu). Needs a real
Apple ROM. The program must sit in the same folder as `qemu-system-ppc`
(and `qemu-img`).

## Requirements

- To run from source: Python 3.11+ with tkinter, no third-party packages.
- To build a distributable bundle: PyInstaller.

## Run from source

    python qemu_gui.py

## Build on macOS

Needs a universal2 python.org framework build of Python (Homebrew's Python
is arch-specific and has no tkinter; Apple's `/usr/bin/python3` is arm64e
and not redistributable):

    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
        -m PyInstaller --noconfirm QemuGUI.spec

Result: `dist/Qemu-system-ppc GUI.app`. Put it in the folder that holds
`qemu-system-ppc`.

## Build on Windows

    pyinstaller --noconfirm QemuGUI.spec

`QemuGUI.spec` targets `universal2` only on macOS; on Windows it produces a
windowed, onedir build at `dist/Qemu-system-ppc GUI/`. Put that folder's
contents alongside `qemu-system-ppc.exe`.

## Tests

    python -m unittest discover -s tests
