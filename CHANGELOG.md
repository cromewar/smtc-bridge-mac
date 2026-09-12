# Changelog

## 1.0.0 — 2026-09-11
First macOS release, ported from [nutty's SMTC Bridge](https://github.com/nuttylmao/smtc-bridge) for Windows.

- Same `/now-playing` and `/sessions` REST API and JSON schema as the Windows app.
- Now Playing data from MediaRemote via the bundled mediaremote-adapter v0.7.7 (works on macOS 15.4+ lockdown).
- Menu bar app (no Dock icon) with Start at Login, settings shortcut, and startup notification.
- Listens on IPv4 and IPv6 loopback; warns when the port is shared with AirPlay Receiver.
- Homebrew cask (`Casks/smtc-bridge.rb`) and `scripts/release.sh` for releases.
