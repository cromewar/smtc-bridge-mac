"""Entry point: single-instance guard, settings, media source, HTTP server thread, menu bar."""

import os
import sys
import threading

from . import APP_NAME, APP_VERSION
from .util import is_already_running, load_settings, get_local_ip, log_crash, port_held_by_another_process


def main() -> None:
    try:
        if is_already_running():
            print("Another instance is already running. Exiting...")
            sys.exit(0)

        settings = load_settings()
        host = settings.get("SERVER", "Host")
        port = settings.getint("SERVER", "Port")
        display_host = get_local_ip() if host == "0.0.0.0" else host

        from .media_source import MediaSource, adapter_self_test
        from .server import create_app, run_server
        from .menubar import BridgeApp, notify

        media_available = adapter_self_test()
        port_shared = port_held_by_another_process(port)
        source = MediaSource()
        source.start()

        flask_app = create_app(source)

        def run_flask():
            try:
                run_server(flask_app, host, port)
            except Exception as e:
                log_crash(e)

        threading.Thread(target=run_flask, name="http", daemon=True).start()

        notify(f"{APP_NAME} v{APP_VERSION}", f"Server successfully started on http://{display_host}:{port}")
        if port_shared:
            notify(
                f"{APP_NAME}: port {port} is shared",
                "Another service (usually AirPlay Receiver) also listens on this port. "
                "If a widget shows 'Waiting for SMTC Bridge', restart it (e.g. restart OBS), "
                "or turn off AirPlay Receiver in System Settings.",
            )

        def on_quit():
            source.stop()
            # Hard exit like the Windows app: Flask's thread has no clean shutdown hook.
            threading.Timer(0.2, lambda: os._exit(0)).start()

        BridgeApp(display_host, port, media_available, on_quit).run()
    except SystemExit:
        raise
    except Exception as e:
        log_crash(e)
        sys.exit(1)
