"""Now Playing data from macOS MediaRemote via mediaremote-adapter, mapped to the SMTC schema.

The adapter is a Perl script (Apple-entitled binary) that loads a small helper framework and
streams JSON lines to stdout. We keep one long-running `stream` process and hold the latest
state in memory, so HTTP requests never touch the subprocess.
"""

import base64
import hashlib
import json
import os
import platform
import subprocess
import threading
import time
from collections import OrderedDict

from . import APP_VERSION
from .util import get_resource_path

PERL = "/usr/bin/perl"
ADAPTER_DIR = "vendor/mediaremote-adapter"

# SMTC enums (see README)
STATUS_CLOSED, STATUS_OPENED, STATUS_CHANGING, STATUS_STOPPED, STATUS_PLAYING, STATUS_PAUSED = range(6)
TYPE_UNKNOWN, TYPE_MUSIC, TYPE_VIDEO, TYPE_IMAGE = range(4)
REPEAT_NONE, REPEAT_TRACK, REPEAT_LIST = range(3)

# mediaremote-adapter mode ids -> SMTC
_REPEAT_MAP = {1: REPEAT_NONE, 2: REPEAT_TRACK, 3: REPEAT_LIST}
_SHUFFLE_ON = {2, 3}

MAX_CACHE_SIZE = 50


def adapter_paths() -> dict:
    base = get_resource_path(ADAPTER_DIR)
    return {
        "script": os.path.join(base, "mediaremote-adapter.pl"),
        "framework": os.path.join(base, "MediaRemoteAdapter.framework"),
        "test_client": os.path.join(base, "MediaRemoteAdapterTestClient"),
    }


def adapter_self_test(timeout: float = 20.0) -> bool:
    """Run the adapter's own `test` command. Exit code 0 means MediaRemote access works."""
    p = adapter_paths()
    try:
        r = subprocess.run(
            [PERL, p["script"], p["framework"], p["test_client"], "test"],
            capture_output=True,
            timeout=timeout,
        )
        return r.returncode == 0
    except Exception:
        return False


def _ms(seconds) -> int:
    try:
        v = float(seconds)
    except (TypeError, ValueError):
        return 0
    if v != v or v in (float("inf"), float("-inf")):  # NaN / live streams
        return 0
    return int(v * 1000)


class ArtworkCache:
    """LRU of base64 data URLs keyed by a hash of the raw base64 payload."""

    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        self._cache: "OrderedDict[str, str]" = OrderedDict()
        self._max = max_size

    def data_url(self, b64: str, mime: str | None) -> str:
        key = hashlib.md5(b64.encode("ascii", "ignore")).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        url = f"data:{mime or 'image/jpeg'};base64,{b64}"
        self._cache[key] = url
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return url


def map_session(state: dict, artwork: ArtworkCache | None = None) -> dict | None:
    """Translate one adapter payload into one SMTC-shaped session dict. None if no media."""
    if not state or not state.get("bundleIdentifier"):
        return None
    artwork = artwork or ArtworkCache()

    playing = bool(state.get("playing"))
    media_type = str(state.get("mediaType") or "")
    playback_type = TYPE_VIDEO if "video" in media_type.lower() else TYPE_MUSIC

    playback_info = {
        "AutoRepeatMode": _REPEAT_MAP.get(state.get("repeatMode"), REPEAT_NONE),
        "IsShuffleActive": state.get("shuffleMode") in _SHUFFLE_ON,
        "PlaybackRate": state.get("playbackRate", 1.0) if state.get("playbackRate") is not None else 1.0,
        "PlaybackStatus": STATUS_PLAYING if playing else STATUS_PAUSED,
        "PlaybackType": playback_type,
    }

    end_ms = _ms(state.get("duration"))
    timeline = {
        "EndTime": end_ms,
        "LastUpdatedTime": state.get("timestamp"),
        "MaxSeekTime": end_ms,
        "MinSeekTime": 0,
        "Position": _ms(state.get("elapsedTime")),
        "StartTime": 0,
    }

    thumb = None
    b64 = state.get("artworkData")
    if isinstance(b64, str) and b64:
        thumb = artwork.data_url(b64, state.get("artworkMimeType"))

    artist = state.get("artist") or "Unknown"
    genre = state.get("genre")
    media = {
        "Title": state.get("title") or "Unknown",
        "Artist": artist,
        "AlbumTitle": state.get("album") or "Unknown",
        "AlbumArtist": state.get("albumArtist") or artist,  # MediaRemote has no separate album artist
        "TrackNumber": int(state.get("trackNumber") or 0),
        "AlbumTrackCount": int(state.get("totalTrackCount") or 0),
        "Genres": [genre] if genre else [],
        "Subtitle": "",
        "Thumbnail": thumb,
    }

    return {
        "source_app_id": state["bundleIdentifier"],
        "playback_info": playback_info,
        "timeline_properties": timeline,
        "media_properties": media,
    }


def build_payload(state: dict, artwork: ArtworkCache | None = None) -> dict:
    session = map_session(state, artwork)
    sessions = [session] if session else []
    return {
        "app_version": APP_VERSION,
        "os": f"macOS {platform.mac_ver()[0]}",
        "current_session_id": session["source_app_id"] if session else None,
        "sessions": sessions,
    }


# The adapter is wrapped in a tiny sh watchdog so it exits when this process dies for any
# reason (SIGTERM, crash, force quit), not only via the Quit menu. macOS has no PDEATHSIG.
_WATCHDOG = (
    '"$0" "$1" "$2" stream --debounce="$3" & C=$!; '
    'trap "kill $C 2>/dev/null" TERM INT; '
    'while kill -0 "$4" 2>/dev/null && kill -0 $C 2>/dev/null; do sleep 1; done; '
    'kill $C 2>/dev/null; wait $C'
)


def _watchdog_argv(paths: dict, debounce_ms: int, parent_pid: int) -> list[str]:
    return ["/bin/sh", "-c", _WATCHDOG, PERL, paths["script"], paths["framework"], str(debounce_ms), str(parent_pid)]


class MediaSource:
    """Supervises the adapter `stream` subprocess and holds the current now-playing state."""

    def __init__(self, debounce_ms: int = 100):
        self._state: dict = {}
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._debounce = debounce_ms
        self._artwork = ArtworkCache()
        self.available = True
        self.last_error: str | None = None

    # -- public API -------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._supervise, name="media-source", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._kill()

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def payload(self) -> dict:
        return build_payload(self.snapshot(), self._artwork)

    def session_ids(self) -> list[str]:
        s = self.snapshot()
        return [s["bundleIdentifier"]] if s.get("bundleIdentifier") else []

    # -- internals --------------------------------------------------------

    def _kill(self) -> None:
        p = self._proc
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def _supervise(self) -> None:
        backoff = 1.0
        paths = adapter_paths()
        while not self._stop.is_set():
            started = time.time()
            try:
                self._proc = subprocess.Popen(
                    _watchdog_argv(paths, self._debounce, os.getpid()),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
                self.available = True
                for line in self._proc.stdout:
                    if self._stop.is_set():
                        break
                    self._handle_line(line)
            except Exception as e:  # spawn failure, broken pipe, ...
                self.last_error = str(e)
                self.available = False
            finally:
                self._kill()
            if self._stop.is_set():
                break
            # Process died: clear state so clients don't see a frozen track, then restart.
            with self._lock:
                self._state = {}
            backoff = 1.0 if time.time() - started > 30 else min(backoff * 2, 30.0)
            time.sleep(backoff)

    def _handle_line(self, line: str) -> None:
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return
        if msg.get("type") != "data":
            return
        payload = msg.get("payload") or {}
        with self._lock:
            if msg.get("diff"):
                for k, v in payload.items():
                    if v is None:
                        self._state.pop(k, None)
                    else:
                        self._state[k] = v
            else:
                self._state = dict(payload)
