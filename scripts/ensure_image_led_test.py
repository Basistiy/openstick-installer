#!/usr/bin/env python3
"""
Ensure release firmware assets (e.g. dist/openstick-uz801-linux.zip)
have /usr/local/bin/led-test pre-installed in the ext4 rootfs partition.
Can be executed in GitHub Actions workflows and local builds.
"""

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openstick.edl import (
    clean_rootfs_sensitive_data,
    compress_raw_image_to_zip,
    find_debugfs,
    parse_gpt_from_raw_image,
)


def ensure_image_zip_has_led_test(zip_path: Path, dry_run: bool = False) -> bool:
    """Extract zip, check/inject led-test via debugfs, and repackage zip."""
    if dry_run:
        print(f"[DRY-RUN] Simulating led-test verification on {zip_path.name}...")
        return True

    if not zip_path.exists():
        print(f"[-] Error: Image zip not found: {zip_path}", file=sys.stderr)
        return False

    debugfs_bin = find_debugfs()
    if not debugfs_bin:
        print("[-] Warning: debugfs (e2fsprogs) not found. Cannot inspect/modify rootfs offline.", file=sys.stderr)
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        print(f"[*] Extracting {zip_path.name}...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_path)

        raw_image = None
        for p in tmp_path.iterdir():
            if p.is_file() and p.name.endswith(".bin"):
                raw_image = p
                break

        if not raw_image:
            print(f"[-] No raw .bin image found inside {zip_path.name}", file=sys.stderr)
            return False

        print(f"[*] Inspecting partitions of {raw_image.name}...")
        gpt = parse_gpt_from_raw_image(raw_image)
        rootfs_info = gpt.get("rootfs") or gpt.get("userdata")
        if not rootfs_info:
            print("[-] rootfs partition not found in GPT.", file=sys.stderr)
            return False

        offset = rootfs_info["byte_offset"]
        debugfs_target = f"{raw_image}?offset={offset}"

        # Check if /usr/local/bin/led-test already exists
        stat_res = subprocess.run(
            [str(debugfs_bin), "-R", "stat /usr/local/bin/led-test", debugfs_target],
            capture_output=True,
            text=True,
        )
        if "File not found" not in stat_res.stdout and "Size:" in stat_res.stdout:
            print(f"[+] /usr/local/bin/led-test is already installed in {zip_path.name}. No changes needed.")
            return True

        print(f"[*] /usr/local/bin/led-test missing in rootfs. Injecting...")
        clean_ok, cleaned = clean_rootfs_sensitive_data(raw_image, inject_led_test=True)
        if not clean_ok:
            print("[-] Failed to inject led-test via debugfs.", file=sys.stderr)
            return False

        print(f"[+] Successfully injected led-test ({', '.join(cleaned)}).")
        print(f"[*] Re-compressing {zip_path.name}...")
        ok, sha256 = compress_raw_image_to_zip(raw_image, zip_path)
        if not ok:
            print("[-] Failed to re-compress release image.", file=sys.stderr)
            return False

        print(f"[+] Release image updated: {zip_path.name} (SHA-256: {sha256})")
        return True


def main():
    parser = argparse.ArgumentParser(description="Ensure release firmware image zip contains /usr/local/bin/led-test.")
    parser.add_argument("zip_path", type=Path, help="Path to openstick-*-linux.zip")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without modifying files")

    args = parser.parse_args()
    success = ensure_image_zip_has_led_test(args.zip_path.resolve(), dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
