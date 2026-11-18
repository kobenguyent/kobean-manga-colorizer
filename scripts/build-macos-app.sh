#!/usr/bin/env bash
set -euo pipefail

LAUNCH_APP=false
BUILD_DMG=false

for arg in "$@"; do
  case "$arg" in
    --launch)
      LAUNCH_APP=true
      ;;
    --dmg)
      BUILD_DMG=true
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: $0 [--launch] [--dmg]" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MACOS_DIR="${REPO_ROOT}/macos"
DIST_DIR="${REPO_ROOT}/dist-macos"
APP_NAME="KobeanMangaColorizer"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
CONTENTS_DIR="${APP_BUNDLE}/Contents"
MACOS_BIN_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"
ICON_FILE="${MACOS_DIR}/AppIcon.icns"

echo "[1/4] Generating macOS AppIcon.icns..."
swift "${REPO_ROOT}/scripts/generate-macos-icon.swift" "${ICON_FILE}" "${REPO_ROOT}/static/brand-icon.png"

echo "[2/4] Building KobeanMangaApp (release)..."
cd "${MACOS_DIR}"
swift build -c release
BIN_PATH="$(swift build -c release --show-bin-path)"
BUILT_EXECUTABLE="${BIN_PATH}/KobeanMangaApp"

if [[ ! -x "${BUILT_EXECUTABLE}" ]]; then
  echo "Error: Release executable not found at ${BUILT_EXECUTABLE}" >&2
  exit 1
fi

echo "[3/4] Assembling ${APP_BUNDLE}..."
rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS_BIN_DIR}" "${RESOURCES_DIR}"

cp -f "${BUILT_EXECUTABLE}" "${MACOS_BIN_DIR}/${APP_NAME}"
chmod +x "${MACOS_BIN_DIR}/${APP_NAME}"

cp -f "${ICON_FILE}" "${RESOURCES_DIR}/AppIcon.icns"
if [[ -f "${REPO_ROOT}/static/brand-icon.png" ]]; then
  cp -f "${REPO_ROOT}/static/brand-icon.png" "${RESOURCES_DIR}/brand-icon.png"
fi

shopt -s nullglob
for bundle in "${BIN_PATH}"/*.bundle; do
  cp -R "${bundle}" "${RESOURCES_DIR}/"
  cp -R "${bundle}" "${APP_BUNDLE}/"
done
shopt -u nullglob

printf 'APPL????' > "${CONTENTS_DIR}/PkgInfo"

cat > "${CONTENTS_DIR}/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>ai.kobean.manga-colorizer.macos</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Kobean Manga Colorizer</string>
    <key>CFBundleDisplayName</key>
    <string>Kobean Manga Colorizer</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>KobeanWorkspacePath</key>
    <string>${REPO_ROOT}</string>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsLocalNetworking</key>
        <true/>
    </dict>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeName</key>
            <string>Manga Document &amp; Archive</string>
            <key>CFBundleTypeRole</key>
            <string>Editor</string>
            <key>LSHandlerRank</key>
            <string>Alternate</string>
            <key>CFBundleTypeExtensions</key>
            <array>
                <string>pdf</string>
                <string>epub</string>
                <string>cbz</string>
                <string>zip</string>
                <string>png</string>
                <string>jpg</string>
                <string>jpeg</string>
                <string>webp</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
PLIST

echo "[4/4] Codesigning & verifying ${APP_BUNDLE}..."
xattr -cr "${APP_BUNDLE}" || true
codesign --force --deep --sign - "${APP_BUNDLE}"
codesign --verify --deep --strict "${APP_BUNDLE}"

LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "${LSREGISTER}" ]]; then
  "${LSREGISTER}" -f "${APP_BUNDLE}" || true
fi

echo "Successfully packaged: ${APP_BUNDLE}"

if [[ "${BUILD_DMG}" == "true" ]]; then
  DMG_PATH="${DIST_DIR}/${APP_NAME}.dmg"
  rm -f "${DMG_PATH}"
  hdiutil create -volname "Kobean Manga Colorizer" -srcfolder "${APP_BUNDLE}" -ov -format UDZO "${DMG_PATH}"
  echo "Created DMG: ${DMG_PATH}"
fi

if [[ "${LAUNCH_APP}" == "true" ]]; then
  open "${APP_BUNDLE}"
fi
