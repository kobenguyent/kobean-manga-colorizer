#!/usr/bin/env bash
set -euo pipefail

# Computes the next semantic release version from git tags & commits since the last vX.Y.Z tag.
#
# Usage:
#   ./scripts/next-version.sh [--bump auto|patch|minor|major] [--initial 1.0.0]
#
# Outputs shell-safe KEY=VALUE lines suitable for `eval "$(./scripts/next-version.sh)"`.

BUMP_OVERRIDE="auto"
INITIAL_VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bump)
      BUMP_OVERRIDE="$2"
      shift 2
      ;;
    --initial)
      INITIAL_VERSION="${2#v}"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$INITIAL_VERSION" ]]; then
  if [[ -f "pyproject.toml" ]]; then
    INITIAL_VERSION="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' pyproject.toml | head -n 1 || true)"
  fi
  INITIAL_VERSION="${INITIAL_VERSION:-1.0.0}"
fi

emit() {
  printf 'SHOULD_RELEASE=%q\n' "$1"
  printf 'REASON=%q\n' "$2"
  printf 'PREV_TAG=%q\n' "$3"
  printf 'NEXT_TAG=%q\n' "$4"
  printf 'NEXT_VERSION=%q\n' "$5"
  printf 'BUMP_KIND=%q\n' "$6"
}

# Skip if HEAD commit explicitly requests [skip release] or [no release] (unless manual bump override)
HEAD_MSG="$(git log -1 --pretty=%B 2>/dev/null || true)"
if [[ "$BUMP_OVERRIDE" == "auto" ]]; then
  if echo "$HEAD_MSG" | grep -qiE '\[(skip release|no release|release skip)\]'; then
    emit "false" "Commit message contains [skip release]" "" "" "" "none"
    exit 0
  fi
fi

# Check if HEAD is already tagged with a semantic version tag
EXISTING_HEAD_TAG="$(git tag --points-at HEAD --list 'v[0-9]*.[0-9]*.[0-9]*' | sort -V | tail -n 1 || true)"
if [[ "$BUMP_OVERRIDE" == "auto" && -n "$EXISTING_HEAD_TAG" ]]; then
  emit "false" "HEAD is already tagged with ${EXISTING_HEAD_TAG}" "$EXISTING_HEAD_TAG" "$EXISTING_HEAD_TAG" "${EXISTING_HEAD_TAG#v}" "none"
  exit 0
fi

# Find latest stable semver tag reachable from HEAD
PREV_TAG="$(git tag --merged HEAD --list 'v[0-9]*.[0-9]*.[0-9]*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n 1 || true)"

if [[ -z "$PREV_TAG" ]]; then
  emit "true" "No previous release tag found; starting at v${INITIAL_VERSION}" "" "v${INITIAL_VERSION}" "${INITIAL_VERSION}" "initial"
  exit 0
fi

COMMIT_COUNT="$(git rev-list --count "${PREV_TAG}..HEAD" 2>/dev/null || echo 0)"
if [[ "$BUMP_OVERRIDE" == "auto" && "$COMMIT_COUNT" -eq 0 ]]; then
  emit "false" "No new commits since ${PREV_TAG}" "$PREV_TAG" "$PREV_TAG" "${PREV_TAG#v}" "none"
  exit 0
fi

# Skip automatic release if every changed file since PREV_TAG is pure documentation
if [[ "$BUMP_OVERRIDE" == "auto" ]]; then
  NON_DOC_FILES="$(git diff --name-only "${PREV_TAG}..HEAD" | grep -vE '^(README\.md|LICENSE|docs/|.*\.md$)' || true)"
  if [[ -z "$NON_DOC_FILES" ]]; then
    emit "false" "Only documentation files changed since ${PREV_TAG}" "$PREV_TAG" "$PREV_TAG" "${PREV_TAG#v}" "none"
    exit 0
  fi
fi

RAW_VER="${PREV_TAG#v}"
IFS='.' read -r MAJOR MINOR PATCH <<< "$RAW_VER"
MAJOR="${MAJOR:-0}"
MINOR="${MINOR:-0}"
PATCH="${PATCH:-0}"

BUMP_KIND="patch"
if [[ "$BUMP_OVERRIDE" != "auto" ]]; then
  BUMP_KIND="$BUMP_OVERRIDE"
else
  COMMITS_TEXT="$(git log "${PREV_TAG}..HEAD" --pretty=%B)"
  if echo "$COMMITS_TEXT" | grep -qE '(^BREAKING CHANGE:|^[a-zA-Z0-9_-]+(\([^)]+\))?!:|\[major\])'; then
    BUMP_KIND="major"
  elif echo "$COMMITS_TEXT" | grep -qE '(^feat(\([^)]+\))?:|^Add |^Support |^Redesign |\[minor\])'; then
    BUMP_KIND="minor"
  else
    BUMP_KIND="patch"
  fi
fi

case "$BUMP_KIND" in
  major)
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
    ;;
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    ;;
  patch)
    PATCH=$((PATCH + 1))
    ;;
  *)
    echo "Invalid bump kind: ${BUMP_KIND}" >&2
    exit 1
    ;;
esac

NEXT_VERSION="${MAJOR}.${MINOR}.${PATCH}"
NEXT_TAG="v${NEXT_VERSION}"

emit "true" "Calculated ${BUMP_KIND} bump from ${PREV_TAG} (${COMMIT_COUNT} commit(s))" "$PREV_TAG" "$NEXT_TAG" "$NEXT_VERSION" "$BUMP_KIND"
