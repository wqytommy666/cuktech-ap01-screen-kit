#!/usr/bin/env python3
"""Copy the bundled AP01 project template to a working directory."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--force", action="store_true", help="merge into an existing directory")
    parser.add_argument("--venv", action="store_true", help="create .venv and install requirements")
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    template = skill_root / "assets" / "project-template"
    output = args.output.expanduser().resolve()
    existed = output.exists()
    if existed and any(output.iterdir()) and not args.force:
        raise SystemExit(f"destination is not empty: {output}; pass --force to merge")
    shutil.copytree(template, output, dirs_exist_ok=existed or args.force)
    if args.venv:
        subprocess.run(["python3", "-m", "venv", str(output / ".venv")], check=True)
        subprocess.run(
            [str(output / ".venv" / "bin" / "python"), "-m", "pip", "install", "-r", str(output / "requirements.txt")],
            check=True,
        )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
