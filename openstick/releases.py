"""GitHub Releases management and universal raw image downloading for OpenStick."""

import hashlib
import json
import os
import shutil
import ssl
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_GITHUB_REPO = "Basistiy/openstick-installer"


def _urlopen_with_cert_fallback(req: urllib.request.Request, timeout: int = 30):
    """
    Open URL with standard SSL verification first.
    If local certificate verification fails (common on bare macOS Python installations),
    fall back to unverified SSL context since downloads are verified by SHA-256 digests.
    """
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            ctx = ssl._create_unverified_context()
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        raise


def get_latest_release(repo: str = DEFAULT_GITHUB_REPO) -> Optional[Dict]:
    """
    Fetch the newest published release from GitHub API.
    Returns the release dict or None on failure.
    """
    url = f"https://api.github.com/repos/{repo}/releases"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; OpenStickInstaller/1.0)",
        "Accept": "application/vnd.github.v3+json",
    }
    req = urllib.request.Request(url, headers=headers)

    try:
        with _urlopen_with_cert_fallback(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0:
                for r in data:
                    if not r.get("draft", False):
                        return r
    except Exception as e:
        print(f"[-] Failed to fetch releases from GitHub ({repo}): {e}", file=sys.stderr)

    return None


def find_matching_asset(release: Dict, device_id: str, mode: str = "linux") -> Optional[Dict]:
    """
    Find matching asset file in the release for the selected device model.
    Looks for assets like:
      - openstick-uz801-linux.zip
      - openstick-uz801-debian.zip
      - uz801-linux.zip
    """
    device_id = device_id.lower().strip()
    assets = release.get("assets", [])

    for asset in assets:
        name = asset.get("name", "").lower()
        if not name.endswith(".zip"):
            continue

        if device_id in name:
            if mode in ("linux", "debian") and ("linux" in name or "debian" in name):
                return asset
            elif mode == "stock" and ("stock" in name or "recovery" in name):
                return asset

    # Fallback: if only one zip is attached, use it
    for asset in assets:
        if asset.get("name", "").lower().endswith(".zip"):
            return asset

    return None


def calculate_sha256(file_path: Path) -> str:
    """Calculate the SHA-256 hexadecimal digest of a local file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def download_with_progress(url: str, output_path: Path, expected_size: Optional[int] = None) -> bool:
    """Download a file via HTTP streaming with a clean progress indicator."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".part")

    headers = {"User-Agent": "Mozilla/5.0 (compatible; OpenStickInstaller/1.0)"}
    req = urllib.request.Request(url, headers=headers)

    try:
        with _urlopen_with_cert_fallback(req, timeout=30) as resp:
            total_size = expected_size or int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 65536

            with open(temp_path, "wb") as f:
                while True:
                    chunk = resp.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        sys.stdout.write(f"\r[*] Downloading: {mb_done:.1f} MB / {mb_total:.1f} MB ({percent:.1f}%)")
                    else:
                        mb_done = downloaded / (1024 * 1024)
                        sys.stdout.write(f"\r[*] Downloading: {mb_done:.1f} MB")
                    sys.stdout.flush()

            print()  # newline
            if temp_path.exists():
                if output_path.exists():
                    output_path.unlink()
                shutil.move(str(temp_path), str(output_path))
            return True

    except Exception as e:
        print(f"\n[-] Download error: {e}", file=sys.stderr)
        if temp_path.exists():
            temp_path.unlink()
        return False


def find_raw_image_in_dir(extracted_dir: Path) -> Optional[Path]:
    """
    Locate full raw eMMC image inside an extracted directory.
    Checks for full_emmc.bin or any .bin/.img file containing 'EFI PART' at offset 512.
    """
    if not extracted_dir.exists():
        return None

    # Check for direct full_emmc.bin
    candidate = extracted_dir / "full_emmc.bin"
    if candidate.exists() and candidate.stat().st_size > 0:
        return candidate

    # Search all .bin and .img files
    for file in extracted_dir.glob("*"):
        if file.is_file() and file.suffix.lower() in (".bin", ".img"):
            try:
                if file.stat().st_size >= 1024:
                    with open(file, "rb") as f:
                        f.seek(512)
                        sig = f.read(8)
                        if sig == b"EFI PART":
                            return file
            except Exception:
                pass

    return None


def download_and_extract_asset(
    asset: Dict,
    tag_name: str,
    project_root: Path,
    mode: str = "linux",
    dry_run: bool = False,
) -> Tuple[bool, Optional[Path]]:
    """
    Download a release zip asset into .cache/releases/<tag>/, verify its checksum,
    and extract into a folder. Returns (success, extracted_path).
    """
    asset_name = asset["name"]
    cache_dir = project_root / ".cache" / "releases" / tag_name
    zip_path = cache_dir / asset_name
    extract_dir = cache_dir / Path(asset_name).stem

    if dry_run:
        print(f"[DRY-RUN] Simulating download and extraction of {asset_name}...")
        extract_dir.mkdir(parents=True, exist_ok=True)
        # Create a synthetic full_emmc.bin for dry-run
        from openstick.edl import create_synthetic_raw_image
        raw_img = extract_dir / "full_emmc.bin"
        if not raw_img.exists():
            create_synthetic_raw_image(raw_img)
        return True, extract_dir

    # 1. Check if already extracted
    if extract_dir.exists() and any(extract_dir.iterdir()):
        print(f"[+] Found cached image files in: {extract_dir.relative_to(project_root)}")
        return True, extract_dir

    # 2. Check if zip is already downloaded and valid
    expected_digest = asset.get("digest", "")
    expected_sha256 = expected_digest.split("sha256:", 1)[1] if expected_digest.startswith("sha256:") else None

    need_download = True
    if zip_path.exists():
        if expected_sha256:
            actual_sha = calculate_sha256(zip_path)
            if actual_sha == expected_sha256:
                print(f"[+] Using cached download: {zip_path.name} (SHA-256 verified)")
                need_download = False
            else:
                print(f"[!] Cached file checksum mismatch, re-downloading...")
        else:
            need_download = False

    # 3. Download if needed
    if need_download:
        download_url = asset["browser_download_url"]
        print(f"[*] Downloading {asset_name} from GitHub Release '{tag_name}'...")
        success = download_with_progress(download_url, zip_path, expected_size=asset.get("size"))
        if not success:
            return False, None

        if expected_sha256:
            actual_sha = calculate_sha256(zip_path)
            if actual_sha != expected_sha256:
                print("[-] Download verification failed: SHA-256 mismatch!", file=sys.stderr)
                zip_path.unlink()
                return False, None
            print("[+] SHA-256 checksum verified successfully.")

    # 4. Extract
    print(f"[*] Extracting {asset_name}...")
    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(zip_path), "r") as z:
            z.extractall(str(extract_dir))

        # Remove macOS and documentation metadata files
        for f in extract_dir.iterdir():
            if f.is_file() and (f.suffix.lower() in [".txt", ".md", ".json", ".zip", ".log"] or f.name.startswith(".")):
                try:
                    f.unlink()
                except OSError:
                    pass

        print(f"[+] Extracted firmware files to: {extract_dir.relative_to(project_root)}")
        return True, extract_dir
    except Exception as e:
        print(f"[-] Failed to extract zip: {e}", file=sys.stderr)
        return False, None
