"""
Windows CIM query utilities (PowerShell Get-CimInstance)

Replaces the legacy WMIC command-line tool, which is deprecated and
removed from Windows Server 2025+. The public API (make_query,
parse_list, is_noinstance, FMT_TYPE_LIST) is preserved so that
existing callers (drive.py, system.py, tp-qemu tests) work without
changes.
"""

import re

FMT_TYPE_LIST = "/format:list"

_WMIC_ALIAS_MAP = {
    "baseboard": "Win32_BaseBoard",
    "cdrom": "Win32_CDROMDrive",
    "computersystem": "Win32_ComputerSystem",
    "cpu": "Win32_Processor",
    "csproduct": "Win32_ComputerSystemProduct",
    "datafile": "CIM_DataFile",
    "diskdrive": "Win32_DiskDrive",
    "logicaldisk": "Win32_LogicalDisk",
    "memorychip": "Win32_PhysicalMemory",
    "memphysical": "Win32_PhysicalMemoryArray",
    "nic": "Win32_NetworkAdapter",
    "nicconfig": "Win32_NetworkAdapterConfiguration",
    "os": "Win32_OperatingSystem",
    "pagefileset": "Win32_PageFileSetting",
    "process": "Win32_Process",
    "product": "Win32_Product",
    "recoveros": "Win32_OSRecoveryConfiguration",
    "service": "Win32_Service",
    "sysdriver": "Win32_SystemDriver",
    "timezone": "Win32_TimeZone",
    "useraccount": "Win32_UserAccount",
    "volume": "Win32_Volume",
}


def _resolve_class(cmd):
    """Resolve a WMIC alias or 'path ClassName' to a WMI class name."""
    stripped = cmd.strip()
    lower = stripped.lower()
    if lower.startswith("path "):
        return stripped.split(None, 1)[1]
    return _WMIC_ALIAS_MAP.get(lower, stripped)


def make_query(cmd, cond=None, props=None, get_swch=None, gbl_swch=None):
    """
    Build a PowerShell Get-CimInstance query command.

    :param cmd: WMIC alias (e.g. "diskdrive") or "path ClassName".
    :param cond: WQL filter condition.
    :param props: Properties to retrieve.
    :param get_swch: Kept for API compat; ignored.
    :param gbl_swch: Kept for API compat; ignored.

    :return: PowerShell command string.
    """
    cls = _resolve_class(cmd)
    parts = ['powershell -command "Get-CimInstance', cls]
    if cond:
        escaped = cond.replace("'", "''")
        parts.append("-Filter '%s'" % escaped)
    parts.append("|")
    if props:
        parts.append("Format-List %s" % ",".join(props))
    else:
        parts.append("Format-List")
    return " ".join(parts) + '"'


def is_noinstance(data):
    """Check if the given data contains no instance(s)."""
    return not data.strip()


def parse_list(data):
    """
    Parse PowerShell Format-List output.

    Format-List produces lines like ``Key : Value`` (with spaces
    around the colon), separated by blank lines between objects.

    :param data: Raw command output.
    :return: List of dicts (multiple props) or strings (single prop).
    """
    out = []
    if not is_noinstance(data):
        for para in re.split(r"(?:\r?\n){2,}", data.strip()):
            keys, vals = [], []
            for line in para.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" : ", 1)
                if len(parts) == 2:
                    keys.append(parts[0].strip())
                    vals.append(parts[1].strip())
            if not keys:
                continue
            if len(keys) == 1:
                out.append(vals[0])
            else:
                out.append(dict(zip(keys, vals)))
    return out
