#!/usr/bin/env python3
"""
DEPRECATED: use `python scripts/generate_proxy_model.py all` instead.

This script is kept as a thin backward-compatibility wrapper.
"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if __name__ == '__main__':
    print("NOTE: prepare_data.py is deprecated. Use generate_proxy_model.py all",
          file=sys.stderr)
    # Map --use-ansys to all-ansys subcommand
    args = sys.argv[1:]
    subcmd = "all-ansys" if "--use-ansys" in args else "all"
    cmd = [sys.executable, str(ROOT / "scripts" / "generate_proxy_model.py"), subcmd] + args
    sys.exit(subprocess.run(cmd, cwd=str(ROOT)).returncode)
