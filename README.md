# SMTC Bridge for macOS

A macOS port of [SMTC Bridge](https://github.com/nuttylmao/smtc-bridge) by **nutty**. It is a lightweight menu bar
application that exposes whatever macOS reports as ***Now Playing*** (Music, Spotify, browsers, VLC, podcasts…) as
the same clean REST API the Windows version provides, so the same "Now Playing" widgets work on both platforms.

Run the app, and a local web server runs in the background. By default it is available at:<br>
[http://127.0.0.1:5000/now-playing/](http://127.0.0.1:5000/now-playing/)

A ready-to-use "Now Playing" widget utilizing SMTC Bridge is available here:<br>
**[https://widgets.nutty.gg/now-playing/settings/](https://widgets.nutty.gg/now-playing/settings/)**

## Quick Start

### Homebrew (recommended)
```bash
brew tap cromewar/smtc-bridge https://github.com/cromewar/smtc-bridge-mac
brew trust cromewar/smtc-bridge
brew install --cask --no-quarantine smtc-bridge
open -a "SMTC Bridge"
```
The `brew trust` step is required by Homebrew 6+ for third-party taps (older Homebrew ignores it).
`--no-quarantine` is needed because the app is ad-hoc signed, not notarized; without it macOS shows
"Apple could not verify SMTC Bridge.app is free of malware" and refuses to open it. If you already installed
without the flag, run `xattr -dr com.apple.quarantine "/Applications/SMTC Bridge.app"` once.

Upgrade with `brew upgrade --cask --no-quarantine smtc-bridge`; remove with `brew uninstall --cask smtc-bridge`
(add `--zap` to also delete settings, logs and the login item).

### Manual
1. Build the app (see below) or download the zip from the [Releases page](https://github.com/cromewar/smtc-bridge-mac/releases).
2. Copy `SMTC Bridge.app` to `/Applications`, strip quarantine as above, and open it.
3. A music note appears in the menu bar and a notification confirms the server port. Click the icon to view
   the API, toggle **Start at Login**, or quit.

### Settings
`~/Library/Application Support/SMTC Bridge/settings.ini` (or `settings.ini` in the repo when running from source):

```ini
[SERVER]
host = 127.0.0.1
port = 5000
```

Set `host = 0.0.0.0` to reach the bridge from other devices on your network. The menu then shows your LAN address.

### Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/now-playing` | Returns the current media state as JSON. |
| `GET` | `/sessions` | Returns a list of active media sessions. |

### Schema
Identical to the Windows version. See the [original README](https://github.com/nuttylmao/smtc-bridge#schema) for the
full field list and enums.

```json
{
  "app_version": "string",
  "os": "macOS 27.0",
  "current_session_id": "com.spotify.client",
  "sessions": [
    {
      "source_app_id": "com.spotify.client",
      "media_properties": { "Title": "...", "Artist": "...", "AlbumTitle": "...", "AlbumArtist": "...", "Thumbnail": "data:image/jpeg;base64,...", "AlbumTrackCount": 0, "TrackNumber": 0, "Genres": [], "Subtitle": "" },
      "playback_info": { "PlaybackStatus": 4, "PlaybackType": 1, "PlaybackRate": 1, "IsShuffleActive": false, "AutoRepeatMode": 0 },
      "timeline_properties": { "Position": 12345, "StartTime": 0, "EndTime": 245500, "MinSeekTime": 0, "MaxSeekTime": 245500, "LastUpdatedTime": "2026-09-12T02:32:10Z" }
    }
  ]
}
```

### Differences from Windows
- **One session.** macOS exposes a single Now Playing app, not a list. `sessions` has at most one entry and
  `current_session_id` is that app's bundle identifier (e.g. `com.spotify.client`, `com.apple.Music`).
- `PlaybackStatus` is only ever `4` (playing) or `5` (paused); the other Windows states have no macOS equivalent.
- `AlbumArtist` falls back to `Artist`; `Subtitle` is always empty; `EndTime` is `0` for live streams.
- `Position` is the value at `LastUpdatedTime` (same as Windows). Widgets should extrapolate from that timestamp.

## Troubleshooting

**Widget says "Waiting for SMTC Bridge" in OBS but works in a normal browser.**
macOS Control Center (AirPlay Receiver) also listens on port 5000. While the bridge is running it wins for
`127.0.0.1` and `localhost`, but if a widget polled while the bridge was stopped or restarting, AirPlay accepted
that connection, and OBS's browser keeps reusing it. Fix: restart OBS (or remove and re-add the browser source).
To make it never happen again, turn off **System Settings → General → AirDrop & Handoff → AirPlay Receiver**,
or change `port` in settings.ini and add `&smtcBridgePort=<port>` to the widget URL. The app shows a
notification at startup when the port is shared. Note this also happens if OBS starts before the bridge after a reboot;
enable **Start at Login** so the bridge is up first.

**"Apple could not verify SMTC Bridge.app is free of malware".** See the quarantine note in Quick Start.

**Menu shows "Media access unavailable".** The bundled MediaRemote adapter failed its self-test on this macOS
version. Check `~/Library/Logs/SMTC Bridge/` and report the macOS version.

## How it works
Apple locked the private `MediaRemote` framework to entitled processes in macOS 15.4. This app bundles
[mediaremote-adapter](https://github.com/ungive/mediaremote-adapter), which runs a small Perl script (Perl is an
Apple-entitled binary) that loads a helper framework and streams Now Playing updates as JSON. The bridge keeps one
adapter process running, holds the latest state in memory, and serves it instantly on every request.

## Development

Requires [uv](https://docs.astral.sh/uv/) and Xcode Command Line Tools.

```bash
uv sync --group dev      # creates .venv with Python 3.14
uv run pytest            # mapping/stream unit tests
./launch.sh              # run from source (menu bar icon appears)
./build.sh               # tests + PyInstaller → dist/SMTC Bridge.app (ad-hoc signed)
```

Set `CODESIGN_IDENTITY="Developer ID Application: ..."` before `./build.sh` to sign for distribution, then notarize
with `xcrun notarytool`. Once notarized, the `--no-quarantine` step above becomes unnecessary.

### Releasing (Homebrew cask)
The repo doubles as a Homebrew tap: [Casks/smtc-bridge.rb](Casks/smtc-bridge.rb) points at a GitHub release zip.

```bash
scripts/release.sh            # build, zip, update version + sha256 in the cask
scripts/release.sh --publish  # same, then commit, tag vX.Y.Z, push, and create the GitHub release with the zip
```
Bump `APP_VERSION` in `smtc_bridge/__init__.py` and `version` in `pyproject.toml` first.

### Rebuilding the adapter
`vendor/mediaremote-adapter/` holds a prebuilt framework, test client and script (version in `VERSION`). To rebuild:

```bash
brew install cmake
git clone --branch v0.7.7 https://github.com/ungive/mediaremote-adapter
cd mediaremote-adapter && mkdir build && cd build && cmake .. && cmake --build .
cp -R MediaRemoteAdapter.framework MediaRemoteAdapterTestClient ../bin/mediaremote-adapter.pl <repo>/vendor/mediaremote-adapter/
```

### Layout
```
smtc_bridge/        app.py (entry) · media_source.py (adapter + schema mapping) · server.py (Flask)
                    menubar.py (rumps) · autostart.py (LaunchAgent) · util.py (settings, lock, logs)
vendor/             mediaremote-adapter framework + script
assets/             icon.icns, menu bar template icons
windows-reference/  the original Windows implementation, kept for comparison
tests/              pytest
```

Crash logs go to `~/Library/Logs/SMTC Bridge/`.

## License
MIT, see [LICENSE](LICENSE). The bundled mediaremote-adapter is MIT licensed by ungive.

## Credits
Original SMTC Bridge by **nutty** — [check out their stream widgets!](https://nutty.gg/)<br>
MediaRemote access by [ungive/mediaremote-adapter](https://github.com/ungive/mediaremote-adapter) (MIT).
