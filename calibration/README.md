# Device Calibration Partitions

This directory holds the unique cellular calibration and device-specific partitions for your MSM8916 stick.

## Key Calibration Partitions
| Partition | Recommended Filename | Description |
| :--- | :--- | :--- |
| `modemst1` | `modemst1.bin` (or `.img`) | Non-Volatile (NV) RAM & cellular calibration (IMEI) |
| `modemst2` | `modemst2.bin` (or `.img`) | NV RAM backup partition |
| `fsg` | `fsg.bin` (or `.img`) | Golden copy of modem file system |
| `fsc` | `fsc.bin` (or `.img`) | File system cookie & crypto state |
| `persist` | `persist.bin` (or `.img`) | Wi-Fi MAC, Bluetooth address, sensor calibration |
| `sec` | `sec.bin` (or `.img`) | Hardware security keystore |
| `modem` | `modem.bin` (or `.img`) | Baseband firmware image (optional) |

## How to Use
1. **Automatic Extraction (Recommended)**:
   - When you select your board and agree to backup original partitions, OpenStick Flasher automatically slices these partitions from your device's eMMC dump directly into this `calibration/` folder.
2. **Manual Placement**:
   - If you previously dumped partitions using QFIL, Qualcomm EDL (`edl r`), or another tool, copy your `.bin` or `.img` files directly into this directory before running `run.command` / `run.bat` / `run.sh`.

> [!WARNING]
> **Privacy & Security**: Files in this directory contain your stick's unique IMEI number and device identity. **Do not upload, share, or commit files from this folder to public repositories.**
