# Qemu-system-ppc GUI

A portable launcher for the `g3beige` machine (beige Power Mac G3) of the
`g3beige` branch of `qemu-system-ppc` (github.com/cat7/qemu). Needs a real
Apple ROM. The program must sit in the same folder as `qemu-system-ppc`
(and `qemu-img`).

## Requirements

- To run from source: Python 3.11+ with tkinter, plus `pyftpdlib` for the
  shared folder (`python -m pip install pyftpdlib`).
- To build a distributable bundle: PyInstaller, with `pyftpdlib` installed
  in the same Python.

## Run from source

    python qemu_gui.py

## Build on macOS

Needs a universal2 python.org framework build of Python (Homebrew's Python
is arch-specific and has no tkinter; Apple's `/usr/bin/python3` is arm64e
and not redistributable):

    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
        -m PyInstaller --noconfirm QemuGUI.spec

Result: `dist/Qemu-system-ppc GUI.app`. Put it in the folder that holds
`qemu-system-ppc`. For a build that runs only on the building machine's
architecture, prefix the command with `QEMUGUI_TARGET_ARCH=arm64` (or
`x86_64`).

## Shared folder

Each machine can share one host folder over FTP while it runs. With the
default (slirp) network the Mac reaches it at `ftp://10.0.2.2/`
(`:2121` when port 21 is taken); with vmnet choose "All interfaces", set
a password, and use the host's own address.

## Build on Windows

    pyinstaller --noconfirm QemuGUI.spec

`QemuGUI.spec` targets `universal2` only on macOS; on Windows it produces a
windowed, onedir build at `dist/Qemu-system-ppc GUI/`. Put that folder's
contents alongside `qemu-system-ppc.exe`.

## Tests

    python -m unittest discover -s tests
