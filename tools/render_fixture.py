#!/usr/bin/env python3
"""Print the launcher generated for a machine.json, headless.

    python tools/render_fixture.py tests/fixtures/mac-os.json [darwin|win32|linux] [machine-dir]
"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from qemugui import command
from qemugui.model import Machine

path = Path(sys.argv[1])
platform = sys.argv[2] if len(sys.argv) > 2 else "darwin"
machine_dir = sys.argv[3] if len(sys.argv) > 3 else str(path.parent)
m = Machine.load(path)
sys.stdout.write(command.launcher_text(m, "", machine_dir, platform))
