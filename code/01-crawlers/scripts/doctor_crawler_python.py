"""Diagnose and repair the Python environment used by crawler commands.

This script intentionally uses only the Python standard library so it can run
even when pandas or BeautifulSoup are broken.
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path


REQUIRED_PACKAGES = (
    ("pandas", "read_csv"),
    ("bs4", "BeautifulSoup"),
    ("requests", "get"),
    ("lxml", None),
    ("pyarrow", None),
)

PIP_PACKAGES = (
    "pandas",
    "beautifulsoup4",
    "requests",
    "lxml",
    "pyarrow",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check or repair crawler Python dependencies.")
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Install or reinstall crawler dependencies into this exact Python interpreter.",
    )
    parser.add_argument(
        "--force-reinstall",
        action="store_true",
        help="Force reinstall dependency wheels during --repair.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print_environment()
    ok_before = check_packages()
    if ok_before and not args.repair:
        print("Crawler Python environment looks OK.")
        return 0
    if not args.repair:
        print("Crawler Python environment is not ready. Re-run with --repair.")
        return 1

    ensure_pip()
    install_dependencies(force_reinstall=args.force_reinstall)
    print("\nAfter repair:")
    ok_after = check_packages()
    return 0 if ok_after else 1


def print_environment() -> None:
    print("Python executable:", sys.executable)
    print("Python version:", sys.version.replace("\n", " "))
    print("Working directory:", Path.cwd())
    print("PYTHONPATH:", os.environ.get("PYTHONPATH", ""))
    print("First sys.path entries:")
    for value in sys.path[:8]:
        print("  ", value)
    print()


def check_packages() -> bool:
    all_ok = True
    for module_name, required_attr in REQUIRED_PACKAGES:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            print(f"{module_name}: FAIL import {type(exc).__name__}: {exc}")
            all_ok = False
            continue
        module_file = getattr(module, "__file__", None)
        version = getattr(module, "__version__", "")
        print(f"{module_name}: file={module_file} version={version}")
        if required_attr and not hasattr(module, required_attr):
            print(f"{module_name}: FAIL missing attribute {required_attr}")
            all_ok = False
    return all_ok


def ensure_pip() -> None:
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], check=True)
        return
    except subprocess.CalledProcessError:
        pass
    subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=True)


def install_dependencies(*, force_reinstall: bool) -> None:
    command = [sys.executable, "-m", "pip", "install", "--upgrade"]
    if force_reinstall:
        command.append("--force-reinstall")
    command.extend(PIP_PACKAGES)
    subprocess.run(command, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
