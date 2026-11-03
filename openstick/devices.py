"""Device models registry and hardware definitions for MSM8916 USB sticks."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DeviceModel:
    id: str
    name: str
    description: str
    soc: str = "Qualcomm MSM8916 (Snapdragon 410)"
    ram: str = "512MB / 1GB LPDDR3"
    storage: str = "4GB eMMC"
    default_gateway: str = "192.168.100.1"
    adb_enable_url: str = "http://192.168.100.1/usbdebug.html"
    recommended_loader: str = "prog_emmc_firehose_8916.mbn"
    critical_partitions: List[str] = field(
        default_factory=lambda: ["modemst1", "modemst2", "fsg", "fsc", "persist", "sec"]
    )
    notes: List[str] = field(default_factory=list)


# Supported devices registry
DEVICES: Dict[str, DeviceModel] = {
    "uz801": DeviceModel(
        id="uz801",
        name="UZ801 (4G LTE USB Modem Dongle)",
        description="Common white USB dongle with SIM slot and Qualcomm MSM8916 SoC.",
        default_gateway="192.168.100.1",
        adb_enable_url="http://192.168.100.1/usbdebug.html",
        recommended_loader="prog_emmc_firehose_8916.mbn",
        critical_partitions=["modemst1", "modemst2", "fsg", "fsc", "persist", "sec"],
        notes=[
            "To enable ADB: Connect to its Wi-Fi, open http://192.168.100.1/usbdebug.html in a browser, and toggle USB debug on.",
            "Fastboot reboot command: fastboot oem reboot-edl transitions directly to EDL mode.",
            "If soft-reboot to EDL fails: Hold physical recovery button or short EDL pins while plugging into USB.",
            "Critical calibration partitions: modemst1, modemst2, fsg, fsc, persist, sec (contain unique IMEI and RF calibration).",
        ],
    ),
    "hmuf02": DeviceModel(
        id="hmuf02",
        name="HMUF02 (4G LTE USB Modem Dongle)",
        description="Qualcomm MSM8916 4G LTE Wi-Fi USB dongle (commonly HMUF02-V05 PCB revision).",
        ram="512MB LPDDR3",
        storage="4GB eMMC",
        default_gateway="192.168.100.1",
        adb_enable_url="http://192.168.100.1",
        recommended_loader="prog_emmc_firehose_8916.mbn",
        critical_partitions=["modemst1", "modemst2", "fsg", "fsc", "persist", "sec"],
        notes=[
            "Stock ADB: Plug into USB and check 'adb devices' (or check USB debug settings in the stock Web UI at http://192.168.100.1).",
            "Fastboot reboot command: fastboot oem reboot-edl transitions directly to EDL mode.",
            "If soft-reboot to EDL fails: Hold physical reset/recovery button or short EDL test pads while plugging into USB.",
            "Critical calibration partitions: modemst1, modemst2, fsg, fsc, persist, sec (contain unique IMEI and RF calibration).",
        ],
    ),
}

DEVICE_ALIASES: Dict[str, str] = {
    "uz801-v3": "uz801",
    "hmuf": "hmuf02",
    "hmuf02-v05": "hmuf02",
}


def get_supported_devices() -> Dict[str, DeviceModel]:
    """Return all currently supported devices."""
    return DEVICES


def get_device_by_id(device_id: str) -> Optional[DeviceModel]:
    """Retrieve device by its string identifier or alias (case-insensitive)."""
    key = device_id.lower().strip()
    key = DEVICE_ALIASES.get(key, key)
    return DEVICES.get(key)


def get_device_by_index(idx: int) -> Optional[DeviceModel]:
    """Retrieve device by 1-based index corresponding to menu list."""
    keys = list(DEVICES.keys())
    if 1 <= idx <= len(keys):
        return DEVICES[keys[idx - 1]]
    return None
