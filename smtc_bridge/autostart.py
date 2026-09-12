"""'Start at Login' via a per-user LaunchAgent (macOS equivalent of the Startup folder)."""

import os
import plistlib
import subprocess
import sys

from . import BUNDLE_ID
from .util import is_frozen, project_root


def _plist_path() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{BUNDLE_ID}.plist")


def is_enabled() -> bool:
    return os.path.exists(_plist_path())


def _program_arguments() -> tuple[list[str], str]:
    if is_frozen():
        return [sys.executable], os.path.dirname(sys.executable)
    return [sys.executable, "-m", "smtc_bridge"], project_root()


def _launchctl(*args: str) -> None:
    try:
        subprocess.run(["launchctl", *args], capture_output=True, timeout=10)
    except Exception:
        pass


def set_enabled(enable: bool) -> None:
    path = _plist_path()
    domain = f"gui/{os.getuid()}"
    if enable:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        args, cwd = _program_arguments()
        plist = {
            "Label": BUNDLE_ID,
            "ProgramArguments": args,
            "WorkingDirectory": cwd,
            "RunAtLoad": True,
            "KeepAlive": False,
            "ProcessType": "Interactive",
        }
        with open(path, "wb") as f:
            plistlib.dump(plist, f)
        # Register now so it shows up in System Settings > Login Items without a re-login.
        # The app is already running, so RunAtLoad will not start a second copy (single-instance lock).
        _launchctl("bootstrap", domain, path)
    else:
        _launchctl("bootout", f"{domain}/{BUNDLE_ID}")
        try:
            os.remove(path)
        except OSError:
            pass


def toggle() -> bool:
    new_state = not is_enabled()
    set_enabled(new_state)
    return new_state
