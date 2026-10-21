"""Bootstrap and virtual environment manager for openstick-installer."""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional

REQUIRED_MODULES = ["serial", "usb", "rich", "colorama", "Crypto", "docopt", "requests"]


def is_in_venv() -> bool:
    """Check if the script is currently running inside a virtual environment."""
    return (
        sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        or hasattr(sys, "real_prefix")
    )


def check_missing_modules(modules: Optional[List[str]] = None) -> List[str]:
    """Check which required modules are not currently importable."""
    if modules is None:
        modules = REQUIRED_MODULES
    missing = []
    for mod in modules:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return missing


def get_venv_executables(venv_dir: Path):
    """Return paths to python and pip binaries inside the virtual environment."""
    if sys.platform == "win32":
        python_bin = venv_dir / "Scripts" / "python.exe"
        pip_bin = venv_dir / "Scripts" / "pip.exe"
    else:
        python_bin = venv_dir / "bin" / "python"
        pip_bin = venv_dir / "bin" / "pip"
    return python_bin, pip_bin


def create_venv(venv_dir: Path) -> bool:
    """Create a virtual environment if it does not already exist."""
    if not venv_dir.exists():
        print(f"[*] Initializing Python virtual environment in {venv_dir.name}...")
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            print("[+] Virtual environment created successfully.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[-] Failed to create virtual environment: {e.stderr}", file=sys.stderr)
            return False
    return True


def download_and_extract_zip(url: str, dest_dir: Path) -> bool:
    """Download a zip archive from GitHub and extract into dest_dir using Python standard library."""
    import io
    import urllib.request
    import zipfile

    print(f"[*] Downloading {url}...")
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; OpenStickInstaller/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            zip_bytes = resp.read()

        print("[*] Extracting archive...")
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            namelist = z.namelist()
            if not namelist:
                return False
            root_prefix = namelist[0].split("/")[0]

            temp_extract = dest_dir.parent / f"_temp_{dest_dir.name}"
            if temp_extract.exists():
                shutil.rmtree(temp_extract, ignore_errors=True)
            z.extractall(temp_extract)

            extracted_root = temp_extract / root_prefix
            if extracted_root.exists():
                if dest_dir.exists():
                    shutil.rmtree(dest_dir, ignore_errors=True)
                shutil.move(str(extracted_root), str(dest_dir))
            shutil.rmtree(temp_extract, ignore_errors=True)

        return True
    except Exception as e:
        print(f"[-] Failed to download/extract zip: {e}", file=sys.stderr)
        return False


def ensure_edl_tool(project_root: Path, pip_bin: Path) -> bool:
    """Ensure Qualcomm EDL tool (bkerler/edl) is available (with or without git)."""
    from openstick.edl import find_edl_runner
    if find_edl_runner():
        return True

    edl_dir = project_root / "edl"
    zip_url = "https://github.com/bkerler/edl/archive/refs/heads/master.zip"

    if not edl_dir.exists():
        if shutil.which("git"):
            print("\n[*] Setting up Qualcomm EDL tool (bkerler/edl) via git...")
            try:
                subprocess.run(
                    [
                        "git", "clone", "--depth", "1",
                        "--recurse-submodules",
                        "https://github.com/bkerler/edl.git",
                        str(edl_dir),
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"[!] Git clone failed ({e}). Falling back to direct HTTPS download...")
                if not download_and_extract_zip(zip_url, edl_dir):
                    return False
        else:
            print("\n[*] 'git' not detected. Downloading Qualcomm EDL tool directly via HTTPS...")
            if not download_and_extract_zip(zip_url, edl_dir):
                return False

    if edl_dir.exists():
        print("[*] Configuring local edl package and dependencies...")
        edl_req = edl_dir / "requirements.txt"
        if edl_req.exists():
            subprocess.run(
                [str(pip_bin), "install", "-r", str(edl_req)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        try:
            subprocess.run(
                [str(pip_bin), "install", "--no-deps", "-e", str(edl_dir)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
        return (edl_dir / "edl.py").exists()

    return False


def install_requirements(pip_bin: Path, req_file: Path, project_root: Optional[Path] = None) -> bool:
    """Install dependencies into the virtual environment using pip."""
    if not req_file.exists():
        print(f"[-] Requirements file not found: {req_file}", file=sys.stderr)
        return False

    print(f"[*] Installing required dependencies from {req_file.name}...")
    try:
        # Upgrade pip first (silently ignore if fails)
        subprocess.run(
            [str(pip_bin), "install", "--upgrade", "pip"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Install requirements
        subprocess.run(
            [str(pip_bin), "install", "-r", str(req_file)],
            check=True,
            text=True,
        )
        print("[+] Core dependencies installed successfully.")

        if project_root:
            ensure_edl_tool(project_root, pip_bin)

        return True
    except subprocess.CalledProcessError as e:
        print(f"[-] Error installing dependencies: {e}", file=sys.stderr)
        return False


def re_exec_in_venv(python_bin: Path):
    """Re-execute the current process inside the virtual environment Python."""
    print(f"[*] Switching execution into virtual environment ({python_bin})...\n")
    args = [str(python_bin)] + sys.argv
    if sys.platform == "win32":
        code = subprocess.call(args)
        sys.exit(code)
    else:
        os.execv(str(python_bin), args)


def ensure_environment(project_root: Optional[Path] = None, dry_run: bool = False) -> bool:
    """
    Ensure the script is running inside a proper virtual environment with
    required dependencies installed automatically without manual intervention.
    """
    if dry_run or "--dry-run" in sys.argv:
        return True

    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    venv_dir = project_root / ".venv"
    req_file = project_root / "requirements.txt"
    python_bin, pip_bin = get_venv_executables(venv_dir)

    in_venv = is_in_venv()
    missing = check_missing_modules()

    # Case 1: Already inside an active virtual environment with all dependencies satisfied
    if in_venv and not missing:
        return True

    # Case 2: Already in active venv, but some dependencies are missing
    if in_venv and missing:
        print(f"[*] Running in virtual environment, installing missing dependencies: {', '.join(missing)}...")
        current_pip = shutil.which("pip") or str(pip_bin)
        success = install_requirements(Path(current_pip), req_file, project_root=project_root)
        return success

    # Case 3: Running from system Python - automatically set up .venv
    print("\n" + "=" * 60)
    print("       OpenStick Installer - Automatic Setup")
    print("=" * 60)
    print("[*] Preparing local virtual environment and installing dependencies...")

    if not create_venv(venv_dir):
        print("[-] Failed to create virtual environment.", file=sys.stderr)
        sys.exit(1)

    if not install_requirements(pip_bin, req_file, project_root=project_root):
        print("[-] Automatic dependency installation failed.", file=sys.stderr)
        sys.exit(1)

    # Re-execute seamlessly inside the newly created .venv
    re_exec_in_venv(python_bin)
    return True
