#!/usr/bin/env python3
"""
DEPRECATED: use `python scripts/generate_proxy_model.py tps` instead.

This script is kept as a thin backward-compatibility wrapper.
"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if __name__ == '__main__':
    print("NOTE: generate_tps_influence.py is deprecated. Use generate_proxy_model.py tps",
          file=sys.stderr)
    cmd = [sys.executable, str(ROOT / "scripts" / "generate_proxy_model.py"), "tps"] + sys.argv[1:]
    sys.exit(subprocess.run(cmd, cwd=str(ROOT)).returncode)
