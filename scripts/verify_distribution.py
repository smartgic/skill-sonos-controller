"""Verify built distributions contain exactly the current package sources."""

from __future__ import annotations

import tarfile
from pathlib import Path
from zipfile import ZipFile

PROJECT_ROOT = Path(__file__).parents[1]
PACKAGE_NAME = "skill_sonos_controller"
PACKAGE_ROOT = PROJECT_ROOT / PACKAGE_NAME
DIST_ROOT = PROJECT_ROOT / "dist"


def source_files() -> set[str]:
    """Return package paths that belong in both distribution formats."""
    return {
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def wheel_files(path: Path) -> set[str]:
    """Return package-relative files stored in a wheel."""
    prefix = f"{PACKAGE_NAME}/"
    with ZipFile(path) as archive:
        return {
            name.removeprefix(prefix)
            for name in archive.namelist()
            if name.startswith(prefix) and not name.endswith("/")
        }


def sdist_files(path: Path) -> set[str]:
    """Return package-relative files stored in a source archive."""
    marker = f"/{PACKAGE_NAME}/"
    with tarfile.open(path) as archive:
        return {
            member.name.partition(marker)[2]
            for member in archive.getmembers()
            if member.isfile() and marker in member.name
        }


def only_artifact(pattern: str) -> Path:
    """Require one unambiguous artifact for the current build."""
    matches = tuple(DIST_ROOT.glob(pattern))
    if len(matches) != 1:
        message = f"expected one {pattern} artifact, found {len(matches)}"
        raise RuntimeError(message)
    return matches[0]


def verify_contents(label: str, expected: set[str], actual: set[str]) -> None:
    """Report stale or missing package files with actionable paths."""
    missing = sorted(expected - actual)
    stale = sorted(actual - expected)
    if missing or stale:
        message = f"{label} content mismatch: missing={missing}, stale={stale}"
        raise RuntimeError(message)


def main() -> None:
    """Validate the wheel and source distribution in ``dist``."""
    expected = source_files()
    wheel = only_artifact("*.whl")
    sdist = only_artifact("*.tar.gz")
    verify_contents(wheel.name, expected, wheel_files(wheel))
    verify_contents(sdist.name, expected, sdist_files(sdist))
    print(f"Verified {len(expected)} package files in {wheel.name} and {sdist.name}.")


if __name__ == "__main__":
    main()
