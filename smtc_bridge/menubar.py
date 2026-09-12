"""Menu bar UI (rumps) mirroring the Windows tray menu."""

import os
import subprocess
import webbrowser

import rumps

from . import APP_NAME, APP_VERSION, DEVELOPER
from . import autostart
from .util import get_resource_path, is_frozen, settings_path


def notify(title: str, message: str) -> None:
    """Notification Center toast. rumps needs a bundle id (only inside the .app), so fall back to osascript."""
    if is_frozen():
        try:
            rumps.notification(title, None, message)
            return
        except Exception:
            pass
    safe_t = title.replace('"', '\\"')
    safe_m = message.replace('"', '\\"')
    try:
        subprocess.Popen(
            ["osascript", "-e", f'display notification "{safe_m}" with title "{safe_t}"'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


class BridgeApp(rumps.App):
    def __init__(self, display_host: str, port: int, media_available: bool, on_quit):
        super().__init__(APP_NAME, icon=get_resource_path("assets/menubar.png"), template=True, quit_button=None)
        self._on_quit = on_quit
        base = f"http://{display_host}:{port}"

        header = rumps.MenuItem(f"{APP_NAME} v{APP_VERSION} by {DEVELOPER}")
        header.set_callback(None)

        self.startup_item = rumps.MenuItem("Start at Login", callback=self._toggle_startup)
        self.startup_item.state = autostart.is_enabled()

        items = [header, None]
        if not media_available:
            warn = rumps.MenuItem("⚠ Media access unavailable (see logs)")
            warn.set_callback(None)
            items += [warn, None]
        items += [
            rumps.MenuItem("View Data (JSON)", callback=lambda _: webbrowser.open(f"{base}/now-playing")),
            rumps.MenuItem("View Active Sessions", callback=lambda _: webbrowser.open(f"{base}/sessions")),
            None,
            rumps.MenuItem("★ Customize Overlay", callback=lambda _: webbrowser.open("https://widgets.nutty.gg/now-playing/settings/")),
            rumps.MenuItem("★ Try my stream widgets!", callback=lambda _: webbrowser.open("https://nutty.gg/collections/member-exclusive-widgets")),
            None,
            self.startup_item,
            rumps.MenuItem("Open Settings File", callback=self._open_settings),
            None,
            rumps.MenuItem("Quit", callback=self._quit),
        ]
        self.menu = items

    def _toggle_startup(self, sender):
        sender.state = autostart.toggle()

    def _open_settings(self, _):
        path = settings_path()
        if os.path.exists(path):
            subprocess.Popen(["open", "-R", path])

    def _quit(self, _):
        self._on_quit()
        rumps.quit_application()
