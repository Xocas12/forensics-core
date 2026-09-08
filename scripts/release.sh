#!/usr/bin/env bash
# Cut a release of forensics_core.
#
#   scripts/release.sh X.Y.Z [--dry-run]
#
# A release is a tag plus a CHANGELOG entry. The project repositories move to it with their
# own scripts/bump_core.sh, which refuses to commit if their suites fail against it.
set -euo pipefail

VERSION="${1:?usage: release.sh X.Y.Z [--dry-run]}"
DRY="${2:-}"
TAG="core-v${VERSION}"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "version must look like X.Y.Z; got ${VERSION}" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "working tree is dirty; commit or stash first" >&2
  exit 1
fi
if git rev-parse --verify "$TAG" >/dev/null 2>&1; then
  echo "tag ${TAG} already exists" >&2
  exit 1
fi
if ! grep -q "^## ${VERSION}" CHANGELOG.md; then
  echo "CHANGELOG.md has no '## ${VERSION}' section. Every release names its INTERFACES" >&2
  echo "changes, because both project repositories code against that contract." >&2
  exit 1
fi

echo "would tag ${TAG} at $(git rev-parse --short HEAD)"
uv run pytest -q
uv run ruff check .

if [ "$DRY" = "--dry-run" ]; then
  echo "dry run: no tag created"
  exit 0
fi
git tag -a "$TAG" -m "forensics_core ${VERSION}"
git push origin "$TAG"
echo "tagged and pushed ${TAG}"
