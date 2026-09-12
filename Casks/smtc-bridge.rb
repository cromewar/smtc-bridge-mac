cask "smtc-bridge" do
  version "1.0.0"
  sha256 "b65b2f2bec37f76b056556995a676868c4a5034e1ead4e415bd8a59830f7435d"

  url "https://github.com/cromewar/smtc-bridge-mac/releases/download/v#{version}/SMTC-Bridge-#{version}.zip"
  name "SMTC Bridge"
  desc "Exposes Now Playing media info as a local REST API for stream widgets"
  homepage "https://github.com/cromewar/smtc-bridge-mac"

  depends_on arch: :arm64
  depends_on macos: :ventura

  app "SMTC Bridge.app"

  uninstall launchctl: "gg.nutty.smtc-bridge",
            quit:      "gg.nutty.smtc-bridge"

  zap trash: [
    "~/Library/Application Support/SMTC Bridge",
    "~/Library/LaunchAgents/gg.nutty.smtc-bridge.plist",
    "~/Library/Logs/SMTC Bridge",
  ]

  caveats do
    <<~EOS
      SMTC Bridge is ad-hoc signed, not notarized, so macOS Gatekeeper blocks it after a
      normal install. Either install with:
        brew install --cask --no-quarantine smtc-bridge
      or strip the quarantine flag once:
        xattr -dr com.apple.quarantine "#{appdir}/SMTC Bridge.app"
      Then launch: open -a "SMTC Bridge"
    EOS
  end
end
