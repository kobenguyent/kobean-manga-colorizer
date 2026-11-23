#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LAUNCH_APP=false
BUILD_DMG=false
RELEASE_MODE=false
VERSION=""
BUILD_NUMBER="1"
GITHUB_REPO="kobenguyent/kobean-manga-colorizer"
ARCH_MODE="native" # native | universal
OUTPUT_DIR="${REPO_ROOT}/dist-macos"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --launch)
      LAUNCH_APP=true
      shift
      ;;
    --dmg)
      BUILD_DMG=true
      shift
      ;;
    --release)
      RELEASE_MODE=true
      BUILD_DMG=true
      shift
      ;;
    --version)
      VERSION="${2#v}"
      shift 2
      ;;
    --build-number)
      BUILD_NUMBER="$2"
      shift 2
      ;;
    --github-repo)
      GITHUB_REPO="$2"
      shift 2
      ;;
    --arch)
      ARCH_MODE="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--launch] [--dmg] [--release] [--version X.Y.Z] [--build-number N] [--github-repo owner/repo] [--arch native|universal] [--output-dir DIR]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${VERSION}" ]]; then
  if [[ -f "${REPO_ROOT}/pyproject.toml" ]]; then
    VERSION="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' "${REPO_ROOT}/pyproject.toml" | head -n 1 || true)"
  fi
  VERSION="${VERSION:-1.0.0}"
fi

MACOS_DIR="${REPO_ROOT}/macos"
DIST_DIR="${OUTPUT_DIR}"
APP_NAME="KobeanMangaColorizer"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
CONTENTS_DIR="${APP_BUNDLE}/Contents"
MACOS_BIN_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"
ICON_FILE="${MACOS_DIR}/AppIcon.icns"

echo "[1/5] Generating macOS AppIcon.icns..."
swift "${REPO_ROOT}/scripts/generate-macos-icon.swift" "${ICON_FILE}" "${REPO_ROOT}/static/brand-icon.png"

echo "[2/5] Building KobeanMangaApp (release, arch=${ARCH_MODE}, version=${VERSION})..."
cd "${MACOS_DIR}"
if [[ "${ARCH_MODE}" == "universal" ]]; then
  swift build -c release --arch arm64 --arch x86_64
  BIN_PATH="$(swift build -c release --arch arm64 --arch x86_64 --show-bin-path)"
  ARCH_LABEL="universal"
else
  swift build -c release
  BIN_PATH="$(swift build -c release --show-bin-path)"
  ARCH_LABEL="$(uname -m)"
fi

BUILT_EXECUTABLE="${BIN_PATH}/KobeanMangaApp"
if [[ ! -x "${BUILT_EXECUTABLE}" ]]; then
  echo "Error: Release executable not found at ${BUILT_EXECUTABLE}" >&2
  exit 1
fi

echo "==> Binary architecture:"
lipo -info "${BUILT_EXECUTABLE}" || file "${BUILT_EXECUTABLE}"

echo "[3/5] Assembling ${APP_BUNDLE}..."
if [[ "${RELEASE_MODE}" == "true" ]]; then
  rm -rf "${DIST_DIR}"
fi
rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS_BIN_DIR}" "${RESOURCES_DIR}"

cp -f "${BUILT_EXECUTABLE}" "${MACOS_BIN_DIR}/${APP_NAME}"
chmod +x "${MACOS_BIN_DIR}/${APP_NAME}"

cp -f "${ICON_FILE}" "${RESOURCES_DIR}/AppIcon.icns"
if [[ -f "${REPO_ROOT}/static/brand-icon.png" ]]; then
  cp -f "${REPO_ROOT}/static/brand-icon.png" "${RESOURCES_DIR}/brand-icon.png"
fi

# Bundle lightweight Python backend sources inside Contents/Resources/backend
# so standalone GitHub Release downloads work out-of-the-box without a git clone.
BACKEND_DEST="${RESOURCES_DIR}/backend"
mkdir -p "${BACKEND_DEST}"
for py_file in \
  main.py \
  colorizer_engine.py \
  file_processor.py \
  manga_presets.py \
  manga_translator.py \
  quality_scorer.py \
  series_adapter.py \
  series_memory.py \
  pyproject.toml \
  requirements.txt \
  uv.lock \
  README.md \
  LICENSE; do
  if [[ -f "${REPO_ROOT}/${py_file}" ]]; then
    cp -f "${REPO_ROOT}/${py_file}" "${BACKEND_DEST}/${py_file}"
  fi
done

for sub_dir in denoising networks static models; do
  if [[ -d "${REPO_ROOT}/${sub_dir}" ]]; then
    rsync -a \
      --exclude '__pycache__' \
      --exclude '*.pyc' \
      --exclude 'generator.zip' \
      --exclude 'archive' \
      --exclude '.DS_Store' \
      "${REPO_ROOT}/${sub_dir}/" "${BACKEND_DEST}/${sub_dir}/"
  fi
done

shopt -s nullglob
for bundle in "${BIN_PATH}"/*.bundle; do
  cp -R "${bundle}" "${RESOURCES_DIR}/"
  cp -R "${bundle}" "${APP_BUNDLE}/"
done
shopt -u nullglob

printf 'APPL????' > "${CONTENTS_DIR}/PkgInfo"

WORKSPACE_PLIST_ENTRY=""
if [[ "${RELEASE_MODE}" != "true" ]]; then
  WORKSPACE_PLIST_ENTRY="    <key>KobeanWorkspacePath</key>
    <string>${REPO_ROOT}</string>"
fi

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
    <string>${BUILD_NUMBER}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.graphics-design</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>KobeanGitHubRepo</key>
    <string>${GITHUB_REPO}</string>
${WORKSPACE_PLIST_ENTRY}
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

echo "[4/5] Codesigning & verifying ${APP_BUNDLE}..."
xattr -cr "${APP_BUNDLE}" || true
if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
  echo "==> Signing with Developer ID identity: ${CODESIGN_IDENTITY}"
  codesign --force --deep --options runtime --timestamp --sign "${CODESIGN_IDENTITY}" "${APP_BUNDLE}"
else
  echo "==> Applying ad-hoc signature..."
  codesign --force --deep --sign - "${APP_BUNDLE}"
fi
codesign --verify --deep --strict "${APP_BUNDLE}"

if [[ -z "${CI:-}" ]]; then
  LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  if [[ -x "${LSREGISTER}" ]]; then
    "${LSREGISTER}" -f "${APP_BUNDLE}" || true
  fi
fi

echo "Successfully packaged: ${APP_BUNDLE}"

if [[ "${RELEASE_MODE}" == "true" ]]; then
  echo "[5/5] Creating release ZIP, DMG & SHA256SUMS.txt..."
  ZIP_NAME="${APP_NAME}-${VERSION}-macOS-${ARCH_LABEL}.zip"
  ZIP_PATH="${DIST_DIR}/${ZIP_NAME}"
  rm -f "${ZIP_PATH}"
  ditto -c -k --sequesterRsrc --keepParent "${APP_BUNDLE}" "${ZIP_PATH}"
  echo "Created ZIP: ${ZIP_PATH}"

  DMG_NAME="${APP_NAME}-${VERSION}-macOS-${ARCH_LABEL}.dmg"
  DMG_PATH="${DIST_DIR}/${DMG_NAME}"
  DMG_STAGING="${DIST_DIR}/dmg-staging"
  rm -rf "${DMG_STAGING}" "${DMG_PATH}"
  mkdir -p "${DMG_STAGING}"
  cp -R "${APP_BUNDLE}" "${DMG_STAGING}/"
  ln -s /Applications "${DMG_STAGING}/Applications"

  hdiutil create \
    -volname "Kobean Manga Colorizer ${VERSION}" \
    -srcfolder "${DMG_STAGING}" \
    -ov \
    -format UDZO \
    "${DMG_PATH}"
  rm -rf "${DMG_STAGING}"
  echo "Created DMG: ${DMG_PATH}"

  (
    cd "${DIST_DIR}"
    shasum -a 256 "${DMG_NAME}" "${ZIP_NAME}" > SHA256SUMS.txt
  )
  echo "==> SHA256SUMS.txt:"
  cat "${DIST_DIR}/SHA256SUMS.txt"
elif [[ "${BUILD_DMG}" == "true" ]]; then
  echo "[5/5] Creating local DMG..."
  DMG_PATH="${DIST_DIR}/${APP_NAME}.dmg"
  DMG_STAGING="${DIST_DIR}/dmg-staging"
  rm -rf "${DMG_STAGING}" "${DMG_PATH}"
  mkdir -p "${DMG_STAGING}"
  cp -R "${APP_BUNDLE}" "${DMG_STAGING}/"
  ln -s /Applications "${DMG_STAGING}/Applications"
  hdiutil create -volname "Kobean Manga Colorizer" -srcfolder "${DMG_STAGING}" -ov -format UDZO "${DMG_PATH}"
  rm -rf "${DMG_STAGING}"
  echo "Created DMG: ${DMG_PATH}"
else
  echo "[5/5] Skipping archive creation (pass --dmg or --release to build DMG/ZIP)."
fi

if [[ "${LAUNCH_APP}" == "true" ]]; then
  open "${APP_BUNDLE}"
fi
