import json

from smtc_bridge.media_source import ArtworkCache, MediaSource, build_payload, map_session

# Captured from mediaremote-adapter v0.7.7 on macOS 27.0 (Brave playing a live video: no duration key)
SAMPLE = {
    "artist": "phweedomstudio",
    "contentItemIdentifier": "117D59AC-84A6-40B0-B0A8-F8A8EEDD184A",
    "title": "How to battle your octopus pt7",
    "elapsedTime": 0.099014,
    "bundleIdentifier": "com.brave.Browser",
    "playing": True,
    "processIdentifier": 26942,
    "album": "",
    "playbackRate": 1,
    "timestamp": "2026-09-12T02:32:10Z",
    "artworkMimeType": "image/jpeg",
    "artworkData": "/9j/4AAQSkZJRg",
}


def test_map_session_shape():
    s = map_session(SAMPLE)
    assert s["source_app_id"] == "com.brave.Browser"
    assert set(s) == {"source_app_id", "playback_info", "timeline_properties", "media_properties"}
    assert set(s["media_properties"]) == {
        "Title", "Artist", "AlbumTitle", "AlbumArtist", "Thumbnail",
        "AlbumTrackCount", "TrackNumber", "Genres", "Subtitle",
    }
    assert set(s["playback_info"]) == {"PlaybackStatus", "PlaybackType", "PlaybackRate", "IsShuffleActive", "AutoRepeatMode"}
    assert set(s["timeline_properties"]) == {"Position", "StartTime", "EndTime", "MinSeekTime", "MaxSeekTime", "LastUpdatedTime"}


def test_enums_and_values():
    s = map_session(SAMPLE)
    assert s["playback_info"]["PlaybackStatus"] == 4
    assert s["playback_info"]["PlaybackType"] == 1
    assert s["playback_info"]["AutoRepeatMode"] == 0
    assert s["playback_info"]["IsShuffleActive"] is False
    assert s["timeline_properties"]["Position"] == 99
    assert s["timeline_properties"]["EndTime"] == 0  # live stream, no duration
    assert s["media_properties"]["AlbumTitle"] == "Unknown"
    assert s["media_properties"]["AlbumArtist"] == "phweedomstudio"
    assert s["media_properties"]["Thumbnail"] == "data:image/jpeg;base64,/9j/4AAQSkZJRg"


def test_paused_shuffle_repeat_duration_video():
    st = dict(SAMPLE, playing=False, shuffleMode=3, repeatMode=2, duration=245.5, mediaType="MRMediaRemoteMediaTypeVideo",
              trackNumber=3, totalTrackCount=12, genre="Rock")
    s = map_session(st)
    assert s["playback_info"]["PlaybackStatus"] == 5
    assert s["playback_info"]["PlaybackType"] == 2
    assert s["playback_info"]["IsShuffleActive"] is True
    assert s["playback_info"]["AutoRepeatMode"] == 1
    assert s["timeline_properties"]["EndTime"] == 245500
    assert s["timeline_properties"]["MaxSeekTime"] == 245500
    assert s["media_properties"]["TrackNumber"] == 3
    assert s["media_properties"]["AlbumTrackCount"] == 12
    assert s["media_properties"]["Genres"] == ["Rock"]


def test_empty_state():
    p = build_payload({})
    assert p["current_session_id"] is None
    assert p["sessions"] == []
    assert p["os"].startswith("macOS")
    json.dumps(p)


def test_artwork_cache_lru():
    c = ArtworkCache(max_size=2)
    a = c.data_url("AAAA", "image/png")
    c.data_url("BBBB", None)
    c.data_url("AAAA", "image/png")  # touch A
    c.data_url("CCCC", None)         # evicts B
    assert list(c._cache.values())[0] == a
    assert len(c._cache) == 2


def test_stream_diff_merge():
    m = MediaSource()
    m._handle_line(json.dumps({"type": "data", "diff": False, "payload": SAMPLE}))
    m._handle_line(json.dumps({"type": "data", "diff": True, "payload": {"playing": False, "artworkData": None}}))
    st = m.snapshot()
    assert st["playing"] is False
    assert "artworkData" not in st
    assert st["title"] == SAMPLE["title"]
    m._handle_line("Invalid JSON value type in dictionary for key 'duration': inf")  # stderr-like noise ignored
    m._handle_line(json.dumps({"type": "data", "diff": False, "payload": {}}))
    assert m.snapshot() == {}


def test_bind_addresses():
    from smtc_bridge.server import bind_addresses
    assert bind_addresses("127.0.0.1") == ["127.0.0.1", "::1"]
    assert bind_addresses("0.0.0.0") == ["0.0.0.0", "::"]
    assert bind_addresses("192.168.1.5") == ["192.168.1.5"]
