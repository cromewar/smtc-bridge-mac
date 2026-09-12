"""Settings, paths, single-instance lock, crash logging."""

import atexit
import configparser
import datetime
import os
import socket
import sys
import tempfile
import traceback

import psutil

from . import APP_NAME


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def project_root() -> str:
    """Directory that holds vendor/, assets/, settings.ini when running from source."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_path(relative_path: str) -> str:
    """Absolute path to a bundled resource, both from source and inside the .app."""
    base = getattr(sys, "_MEIPASS", project_root())
    return os.path.join(base, relative_path)


def app_support_dir() -> str:
    d = os.path.join(os.path.expanduser("~/Library/Application Support"), APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def log_dir() -> str:
    d = os.path.join(os.path.expanduser("~/Library/Logs"), APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def settings_path() -> str:
    # From source: settings.ini in the repo, like the Windows app.
    # From the .app: a writable per-user location (the app bundle itself may be read-only).
    if is_frozen():
        return os.path.join(app_support_dir(), "settings.ini")
    return os.path.join(project_root(), "settings.ini")


def load_settings() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config["SERVER"] = {"Host": "127.0.0.1", "Port": "5000"}
    ini_path = settings_path()
    if os.path.exists(ini_path):
        config.read(ini_path)
    else:
        with open(ini_path, "w") as f:
            config.write(f)
    return config


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def is_already_running() -> bool:
    lockfile = os.path.join(tempfile.gettempdir(), "smtc_bridge.lock")
    if os.path.exists(lockfile):
        try:
            with open(lockfile) as f:
                pid = int(f.read())
            if psutil.pid_exists(pid) and pid != os.getpid():
                return True
            os.remove(lockfile)
        except (ValueError, PermissionError, OSError):
            try:
                os.remove(lockfile)
            except OSError:
                pass
    try:
        with open(lockfile, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    atexit.register(lambda: os.remove(lockfile) if os.path.exists(lockfile) else None)
    return False


def log_crash(e: BaseException) -> None:
    d = log_dir()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    filename = os.path.join(d, f"crash_{timestamp}.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("--- CRASH DETECTED ---\n")
        f.write(f"Time: {timestamp}\n")
        f.write(str(e) + "\n\n")
        f.write(traceback.format_exc())
    files = [os.path.join(d, x) for x in os.listdir(d) if x.startswith("crash_") and x.endswith(".txt")]
    files.sort(key=os.path.getmtime)
    while len(files) > 10:
        try:
            os.remove(files.pop(0))
        except OSError:
            pass


def port_held_by_another_process(port: int) -> bool:
    """True if some other process already listens on the wildcard address for `port`.

    On macOS, Control Center's AirPlay Receiver squats on *:5000 and *:7000. We can still bind
    the loopback addresses next to it, but any client that connects while this app is down gets
    AirPlay instead and browsers (OBS included) keep reusing that stale keep-alive connection.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return False
    except OSError:
        return True
    finally:
        s.close()
