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


# Supported devices registry (initially supporting UZ801)
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
            "If soft-reboot to EDL fails: Hold the physical recovery button while plugging into USB.",
            "Critical calibration partitions: modemst1, modemst2, fsg, fsc, persist, sec (contain unique IMEI and RF calibration).",
        ],
    ),
}


def get_supported_devices() -> Dict[str, DeviceModel]:
    """Return all currently supported devices."""
    return DEVICES


def get_device_by_id(device_id: str) -> Optional[DeviceModel]:
    """Retrieve device by its string identifier (case-insensitive)."""
    return DEVICES.get(device_id.lower().strip())


def get_device_by_index(idx: int) -> Optional[DeviceModel]:
    """Retrieve device by 1-based index corresponding to menu list."""
    keys = list(DEVICES.keys())
    if 1 <= idx <= len(keys):
        return DEVICES[keys[idx - 1]]
    return None
