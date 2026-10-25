#!/usr/bin/env python3
"""
Packaging script to generate pre-packaged standalone release ZIPs for OpenStick Installer.
Produces clean distribution archives suitable for publishing to GitHub Releases.
"""

import argparse
import hashlib
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def get_version(repo_root: Path) -> str:
    """Read version from openstick/__init__.py or fallback."""
    init_file = repo_root / "openstick" / "__init__.py"
    if init_file.exists():
        with open(init_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    parts = line.split("=")
                    if len(parts) >= 2:
                        return "v" + parts[1].strip().strip('"').strip("'").lstrip("v")
    return "v0.1.0"


def collect_release_files(repo_root: Path) -> Dict[str, Tuple[Path, bool]]:
    """
    Collect all files to include in the release zip.
    Returns a dict mapping archive_relative_path -> (source_path, is_executable).
    """
    files: Dict[str, Tuple[Path, bool]] = {}

    # 1. Root launchers and configuration
    root_items = [
        ("run.bat", False),
        ("run.command", True),
        ("run.sh", True),
        ("main.py", True),
        ("requirements.txt", False),
        ("README.md", False),
        ("LICENSE", False),
    ]

    for filename, is_exec in root_items:
        src = repo_root / filename
        if src.is_file():
            files[filename] = (src, is_exec)
        else:
            print(f"[-] Warning: Required file {filename} not found at {src}", file=sys.stderr)

    # 2. openstick/ module
    openstick_dir = repo_root / "openstick"
    if openstick_dir.is_dir():
        for path in openstick_dir.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel_path = path.relative_to(repo_root).as_posix()
            files[rel_path] = (path, False)

    # 3. Dedicated directories with placeholders / documentation
    # Loaders
    loaders_dir = repo_root / "loaders"
    if loaders_dir.is_dir():
        for path in sorted(loaders_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in (".mbn", ".elf", ".md"):
                rel_path = path.relative_to(repo_root).as_posix()
                files[rel_path] = (path, False)

    # Calibration folder
    calib_readme = repo_root / "calibration" / "README.md"
    if calib_readme.is_file():
        files["calibration/README.md"] = (calib_readme, False)

    calib_gitkeep = repo_root / "calibration" / ".gitkeep"
    if calib_gitkeep.is_file():
        files["calibration/.gitkeep"] = (calib_gitkeep, False)

    # Backups folder
    backups_gitkeep = repo_root / "backups" / ".gitkeep"
    if backups_gitkeep.is_file():
        files["backups/.gitkeep"] = (backups_gitkeep, False)

    return files


def validate_release_manifest(files: Dict[str, Tuple[Path, bool]]) -> bool:
    """Validate that forbidden files (dumps, tokens, bytecode, OS junk) are NOT in manifest."""
    forbidden_extensions = {".pyc", ".pyo", ".bin", ".img", ".part", ".log"}
    forbidden_names = {".DS_Store", "Thumbs.db", ".env"}

    for archive_path, (src, _) in files.items():
        p = Path(archive_path)
        if p.suffix.lower() in forbidden_extensions:
            raise ValueError(f"Forbidden file extension in release manifest: {archive_path}")
        if p.name in forbidden_names:
            raise ValueError(f"Forbidden file in release manifest: {archive_path}")
        if "backups" in p.parts and p.name != ".gitkeep":
            raise ValueError(f"Forbidden private backup file in release manifest: {archive_path}")
        if "calibration" in p.parts and p.name not in ("README.md", ".gitkeep"):
            raise ValueError(f"Forbidden calibration dump in release manifest: {archive_path}")
        if ".venv" in p.parts or ".git" in p.parts or "tests" in p.parts:
            raise ValueError(f"Forbidden directory in release manifest: {archive_path}")

    return True


def create_zip_archive(files: Dict[str, Tuple[Path, bool]], dest_zip: Path) -> Path:
    """Create zip file with specified permissions and timestamps."""
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    dt = datetime.now().timetuple()[:6]

    # Collect needed parent directories to ensure clean directory tree in zip
    dirs_to_create = set()
    for archive_path in files.keys():
        parts = archive_path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs_to_create.add("/".join(parts[:i]) + "/")

    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Write directory entries first
        for d in sorted(dirs_to_create):
            d_info = zipfile.ZipInfo(d, dt)
            d_info.external_attr = 0o040755 << 16  # directory permissions: rwxr-xr-x
            zf.writestr(d_info, "")

        # Write files
        for archive_path, (src, is_exec) in sorted(files.items()):
            content = src.read_bytes()
            info = zipfile.ZipInfo(archive_path, dt)
            info.compress_type = zipfile.ZIP_DEFLATED
            if is_exec:
                info.external_attr = 0o100755 << 16  # executable: -rwxr-xr-x
            else:
                info.external_attr = 0o100644 << 16  # regular file: -rw-r--r--
            zf.writestr(info, content)

    return dest_zip


def compute_sha256(file_path: Path) -> str:
    """Compute hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_release_packages(
    repo_root: Path, output_dir: Path, version: str
) -> Tuple[Path, Path]:
    """
    Build release ZIP archive and SHA256 checksums file.
    Returns (installer_zip, sha256_file).
    """
    files = collect_release_files(repo_root)
    validate_release_manifest(files)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean release archive 'openstick-installer.zip' (permanent /latest/download link)
    installer_zip = output_dir / "openstick-installer.zip"
    create_zip_archive(files, installer_zip)

    # SHA256 checksum file
    sha256_file = output_dir / "SHA256SUMS.txt"
    hash_installer = compute_sha256(installer_zip)

    with open(sha256_file, "w", encoding="utf-8") as f:
        f.write(f"{hash_installer}  {installer_zip.name}\n")

    return installer_zip, sha256_file


def main():
    parser = argparse.ArgumentParser(description="Package OpenStick Installer for GitHub Releases.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "dist",
        help="Destination directory for built archives (default: dist/)",
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Release version string (e.g. v0.1.0)",
    )

    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    version = args.version or get_version(repo_root)
    output_dir = args.output_dir.resolve()

    print(f"[*] Packaging OpenStick Installer ({version})...")
    print(f"[*] Repository root: {repo_root}")
    print(f"[*] Output directory: {output_dir}")

    installer_zip, sha256_file = build_release_packages(repo_root, output_dir, version)

    print(f"[+] Created: {installer_zip.name} ({installer_zip.stat().st_size:,} bytes)")
    print(f"[+] Created: {sha256_file.name}")
    print("\nSHA-256 Checksum:")
    print(sha256_file.read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    main()
