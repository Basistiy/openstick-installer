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
            "Stock Android discriminator: ro.product.model='UZ801' and ro.product.manufacturer='Qualcomm Technology'.",
            "Stock ADB: Plug into USB and check 'adb devices'. If not detected, connect to its Wi-Fi, open http://192.168.100.1/usbdebug.html in a browser, and toggle USB debug on.",
            "Fastboot reboot command: fastboot oem reboot-edl transitions directly to EDL mode.",
            "If soft-reboot to EDL fails: Hold physical recovery button or short EDL pins while plugging into USB.",
            "Critical calibration partitions: modemst1, modemst2, fsg, fsc, persist, sec (contain unique IMEI and RF calibration).",
        ],
    ),
    "hmuf02": DeviceModel(
        id="hmuf02",
        name="HMUF02 (4G LTE USB Modem Dongle)",
        description="Qualcomm MSM8916 4G LTE Wi-Fi USB dongle (commonly HMUF02-V05 / zbx002 PCB revision).",
        ram="512MB LPDDR3",
        storage="4GB eMMC",
        default_gateway="192.168.100.1",
        adb_enable_url="http://192.168.100.1",
        recommended_loader="prog_emmc_firehose_8916.mbn",
        critical_partitions=["modemst1", "modemst2", "fsg", "fsc", "persist", "sec"],
        notes=[
            "Silkscreen: 'UF05 251208V05' / 'zbx002'. Stock Android reports ro.product.model='UFI' and ro.product.manufacturer='HiMI'.",
            "Stock ADB: Plug into USB and check 'adb devices' (ADB is pre-enabled on factory stock firmware; no web toggle needed).",
            "EDL mode: Hold physical reset button while plugging into USB (lands directly in 9008 EDL without opening case).",
            "Fastboot reboot command: fastboot oem reboot-edl transitions directly to EDL mode.",
            "Critical calibration partitions: modemst1, modemst2, fsg, fsc, persist, sec (contain unique IMEI and RF calibration).",
        ],
    ),
    "hmmifib": DeviceModel(
        id="hmmifib",
        name="HM-MIFIB (4G LTE Mobile Wi-Fi Router)",
        description="Qualcomm MSM8916 4G LTE portable Wi-Fi router with battery and 128x128 ST7735S LCD (MF800).",
        ram="512MB LPDDR3",
        storage="4GB eMMC",
        default_gateway="192.168.100.1",
        adb_enable_url="http://192.168.100.1",
        recommended_loader="prog_emmc_firehose_8916.mbn",
        critical_partitions=["modemst1", "modemst2", "fsg", "fsc", "persist", "sec"],
        notes=[
            "Stock ADB: Plug into USB and check 'adb devices' (or enable USB debugging via the stock Web UI at http://192.168.100.1).",
            "Fastboot reboot command: fastboot oem reboot-edl transitions directly to EDL mode.",
            "If soft-reboot to EDL fails: Remove battery, hold reset/recovery button (or short EDL pads) while plugging into USB.",
            "Critical calibration partitions: modemst1, modemst2, fsg, fsc, persist, sec (contain unique IMEI and RF calibration).",
        ],
    ),
}

CUSTOM_DEVICE = DeviceModel(
    id="custom",
    name="Custom Image (MSM8916)",
    description="Generic Qualcomm MSM8916 device using a user-provided custom Linux image.",
    soc="Qualcomm MSM8916 (Snapdragon 410)",
    ram="512MB / 1GB / 2GB LPDDR3",
    storage="4GB / 8GB eMMC",
    default_gateway="192.168.100.1 (or 192.168.5.1 / 192.168.68.1)",
    adb_enable_url="http://192.168.100.1",
    recommended_loader="prog_emmc_firehose_8916.mbn",
    critical_partitions=["modemst1", "modemst2", "fsg", "fsc", "persist", "sec"],
    notes=[
        "Generic MSM8916 device flow with a custom raw eMMC Linux image (.bin or .zip).",
        "Stock ADB: Connect PC to stick's Wi-Fi network and toggle USB debugging in the web panel.",
        "Fastboot reboot command: fastboot oem reboot-edl transitions directly to EDL mode.",
        "If soft-reboot to EDL fails: Hold physical recovery button or short EDL test pads while plugging into USB.",
        "You will be asked for the path to your custom image when installing Linux.",
        "Unique cellular calibration partitions will be backed up and injected into the custom image.",
    ],
)

DEVICE_ALIASES: Dict[str, str] = {
    "uz801-v3": "uz801",
    "hmuf": "hmuf02",
    "hmuf02-v05": "hmuf02",
    "zbx002": "hmuf02",
    "uf05": "hmuf02",
    "hm-mifib": "hmmifib",
    "mifib": "hmmifib",
    "mf800": "hmmifib",
    "custom-image": "custom",
    "custom_image": "custom",
    "other": "custom",
}


def get_supported_devices() -> Dict[str, DeviceModel]:
    """Return all currently supported devices."""
    return DEVICES


def get_device_by_id(device_id: str) -> Optional[DeviceModel]:
    """Retrieve device by its string identifier or alias (case-insensitive)."""
    key = device_id.lower().strip()
    key = DEVICE_ALIASES.get(key, key)
    if key == "custom":
        return CUSTOM_DEVICE
    return DEVICES.get(key)


def get_device_by_index(idx: int) -> Optional[DeviceModel]:
    """Retrieve device by 1-based index corresponding to menu list."""
    keys = list(DEVICES.keys())
    if 1 <= idx <= len(keys):
        return DEVICES[keys[idx - 1]]
    if idx == len(keys) + 1:
        return CUSTOM_DEVICE
    return None
