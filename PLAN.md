> **Status (2026-09-11):** implemented; see README.md. Remaining: verify hosted widget against Mac payload, Developer ID signing + notarization.

# SMTC Bridge for macOS — Port Plan

## 1. What the Windows app does (analysis of `smtc-bridge.pyw`)

Single ~500-line Python script, packaged with PyInstaller into a tray app.

| Concern | Windows implementation |
| :--- | :--- |
| Media source | `winsdk` → `GlobalSystemMediaTransportControlsSessionManager` (all sessions + current session) |
| HTTP API | Flask + flask-cors, `GET /now-playing` (JSON), `GET /sessions` (HTML list), `threaded=True` |
| Tray UI | `pystray` + Pillow icon; menu: version, open JSON, open sessions, promo links, "Start with Windows" toggle, Quit |
| Startup notification | `plyer` toast |
| Start at login | `.lnk` in the user Startup folder, created via PowerShell |
| Single instance | PID lockfile in temp dir, checked with `psutil` |
| Config | `settings.ini` next to the exe (`host`, `port`), defaults `127.0.0.1:5000`; `0.0.0.0` exposes on LAN |
| Perf | 0.5 s payload cache; MD5-keyed LRU cache (50) of base64 artwork |
| Crash handling | Whole script in `try`, writes `logs/crash_*.txt`, keeps 10 |
| Build | `smtc-bridge.spec` + `build.bat` → single `.exe`, no console |

Public contract that must be preserved exactly (the hosted widget at
widgets.nutty.gg consumes it): the `/now-playing` JSON schema and the
PlaybackStatus / PlaybackType / AutoRepeatMode enums in the README.

## 2. macOS equivalents

| Windows | macOS choice | Why |
| :--- | :--- | :--- |
| SMTC (`winsdk`) | **MediaRemote.framework via [mediaremote-adapter](https://github.com/ungive/mediaremote-adapter)** | MediaRemote is the system-wide "Now Playing" source (Music, Spotify, browsers, VLC…). Since macOS 15.4 it returns nothing to unentitled processes. The adapter runs `/usr/bin/perl` (Apple-entitled, `com.apple.perl`) which loads a small bundled framework and prints JSON. Verified on this machine: macOS 27.0, framework present, no other viable public API. |
| `pystray` | **`rumps`** | Native NSStatusBar menu bar app with checkable items, built on PyObjC. `pystray` also works on macOS but rumps is the idiomatic choice and also gives notifications. |
| `plyer` toast | `rumps.notification` (fallback: `osascript -e 'display notification'`) | Native Notification Center; needs a bundle id, which the `.app` build provides. |
| Startup-folder `.lnk` | **LaunchAgent plist** in `~/Library/LaunchAgents/gg.nutty.smtc-bridge.plist` | Standard user-level login item; toggle = write/remove plist + `launchctl bootstrap/bootout`. |
| PyInstaller `.exe` | **PyInstaller `.app`** (`BUNDLE` target in spec) | Same tool, same spec file, adds `Info.plist` with `LSUIElement=1` (no Dock icon). |
| Flask / flask-cors / psutil / Pillow / configparser | unchanged | Cross-platform already. |

Runtime: Python 3.12+ from Homebrew (`python@3.14` is installed; system `/usr/bin/python3` is 3.9 and must not be used).

## 3. Semantics that differ, and how to map them

MediaRemote exposes **one** "now playing" client, not a list of sessions.

- `sessions` will contain exactly one entry (or be empty); `current_session_id` = that app's bundle identifier (e.g. `com.spotify.client`). Document this in the README.
- `PlaybackStatus`: adapter `playing: true` → `4 PLAYING`; `false` with metadata → `5 PAUSED`; no client → empty sessions.
- `PlaybackType`: `1 MUSIC` by default; `2 VIDEO` when the adapter reports a video media type.
- `timeline_properties`: `Position` = `elapsedTime` × 1000, `EndTime` = `duration` × 1000, `StartTime`/`MinSeekTime` = 0, `MaxSeekTime` = `EndTime`, `LastUpdatedTime` = adapter `timestamp` (ISO 8601). Note MediaRemote reports position only at the last state change, exactly like SMTC, so widgets that extrapolate from `LastUpdatedTime` keep working.
- `IsShuffleActive` / `AutoRepeatMode`: map from adapter `shuffleMode` / `repeatMode` when present, else `false` / `0`.
- `Thumbnail`: adapter gives `artworkData` (base64) + `artworkMimeType`; emit `data:<mime>;base64,…`, keep the MD5 LRU cache.
- `Genres`, `Subtitle`, `AlbumTrackCount`, `TrackNumber`: fill from adapter fields where present, else the Windows defaults (`[]`, `""`, `0`).
- `os`: `platform.system()` gives `Darwin`; use `f"macOS {platform.mac_ver()[0]}"`.

## 4. Architecture change: push instead of poll

Windows re-queries SMTC on every request (with a 0.5 s cache). On macOS spawning perl per request is too slow, so:

- Start `perl mediaremote-adapter.pl <framework> stream` once in a background thread at launch.
- Parse each JSON line, merge into an in-memory `current_state` dict under a lock.
- `/now-playing` builds the payload from `current_state` in microseconds; no per-request I/O.
- Supervise the subprocess: restart with backoff if it exits; if the adapter's `test` command fails at startup show a menu item "Media access unavailable" and log it.

## 5. Repo layout (new)

```
smtc-bridge-mac/
├── smtc_bridge/
│   ├── __main__.py        # entry: single-instance, settings, threads, rumps app
│   ├── media_source.py    # adapter subprocess + state store + schema mapping
│   ├── server.py          # Flask app, /now-playing, /sessions
│   ├── menubar.py         # rumps App, menu, notifications
│   ├── autostart.py       # LaunchAgent write/remove/query
│   └── util.py            # settings.ini, lockfile, crash log, resource paths
├── vendor/mediaremote-adapter/   # mediaremote-adapter.pl + MediaRemoteAdapter.framework (pinned release)
├── assets/icon.png, icon.icns    # menu bar template icon + app icon
├── settings.ini
├── requirements.txt       # flask flask-cors psutil pystray→rumps pyobjc-framework-Cocoa Pillow
├── smtc-bridge-mac.spec   # PyInstaller with BUNDLE
├── build.sh, launch.sh
└── README.md
```

Windows files (`*.bat`, `smtc-bridge.pyw`, `.ico`) stay in git history; remove them from the Mac repo or move to `windows/` for reference.

## 6. Execution steps

1. **Environment**: `brew install python@3.14`, `python3.14 -m venv .venv`, install deps. Download the pinned mediaremote-adapter release into `vendor/`, run `perl vendor/.../mediaremote-adapter.pl <fw> test` and `get` while Spotify/Music plays to confirm output on macOS 27 and capture a sample JSON for tests.
2. **`media_source.py`**: subprocess stream reader, state store, `to_session()` mapper implementing §3, artwork LRU. Unit-test the mapper against the captured sample.
3. **`server.py`**: port the two endpoints unchanged in shape; keep CORS, `threaded=True`, werkzeug logging off. Drop the unused `/artwork/<id>` route.
4. **`util.py`**: copy lockfile, `settings.ini` loader (resolve next to the `.app` when frozen, using `sys.executable` → `Contents/MacOS`), `get_local_ip`, crash logger writing to `~/Library/Logs/SMTC Bridge/` instead of a relative `logs/`.
5. **`menubar.py`**: rumps app with the same menu, `Start at Login` checkbox wired to `autostart.py`, Quit calls `os._exit(0)` after killing the perl child. Startup notification with host:port.
6. **`autostart.py`**: LaunchAgent plist pointing at the `.app` executable (`RunAtLoad`, `KeepAlive=false`); when running from source point at the venv python + module.
7. **Packaging**: PyInstaller spec with `BUNDLE(name='SMTC Bridge.app', bundle_identifier='gg.nutty.smtc-bridge', info_plist={'LSUIElement': True, ...})`, `datas` include `vendor/` and icons. `build.sh` mirrors `build.bat`. Ad-hoc sign (`codesign --force --deep -s -`) so the bundle runs locally; note Developer ID + notarization as a later step for public distribution.
8. **Verify**: run from source and from the `.app`; check `/now-playing` with Music, Spotify and a browser tab; test `host = 0.0.0.0` from another device; confirm the hosted widget at widgets.nutty.gg renders against the Mac payload; test login-item toggle and single-instance guard; kill the perl child and confirm it restarts.
9. **README**: macOS quick start, the one-session limitation, first-run Gatekeeper note (right-click → Open for unsigned builds).

## 7. Risks

- **Private API**: mediaremote-adapter depends on undocumented behaviour; a future macOS could break it. Pin the vendored version and keep the source abstraction so a Swift/XPC helper could replace it later.
- **Only one session** vs. Windows' list. Acceptable for a now-playing widget; documented.
- **Unsigned `.app`**: Gatekeeper warning for downloaded builds until notarized (needs an Apple Developer account).
- **Notifications** don't appear when running from source (no bundle id); use the osascript fallback there.
