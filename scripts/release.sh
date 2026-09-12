#!/bin/sh
# Builds the app, zips it for Homebrew, and rewrites Casks/smtc-bridge.rb with the new version + sha256.
# With --publish it also tags, creates the GitHub release, and uploads the zip (needs `gh auth login`).
set -eu
cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' smtc_bridge/__init__.py)
ZIP="dist/SMTC-Bridge-${VERSION}.zip"

./build.sh
echo "--- Zipping ---"
rm -f "$ZIP"
ditto -c -k --keepParent "dist/SMTC Bridge.app" "$ZIP"
SHA=$(shasum -a 256 "$ZIP" | cut -d' ' -f1)
echo "$ZIP  $SHA"

echo "--- Updating cask ---"
sed -i '' -e "s/^  version \".*\"/  version \"${VERSION}\"/" -e "s/^  sha256 \".*\"/  sha256 \"${SHA}\"/" Casks/smtc-bridge.rb
grep -E '^  (version|sha256)' Casks/smtc-bridge.rb

if [ "${1:-}" = "--publish" ]; then
  echo "--- Publishing v${VERSION} ---"
  git add Casks/smtc-bridge.rb
  git commit -m "Release v${VERSION}" || true
  git tag -f "v${VERSION}"
  git push origin HEAD --tags
  gh release create "v${VERSION}" "$ZIP" --title "v${VERSION}" --notes "SMTC Bridge for macOS v${VERSION}" || gh release upload "v${VERSION}" "$ZIP" --clobber
  echo "Published. Users can now: brew tap cromewar/smtc-bridge https://github.com/cromewar/smtc-bridge-mac && brew install --cask smtc-bridge"
fi
