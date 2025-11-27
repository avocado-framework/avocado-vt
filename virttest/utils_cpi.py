"""
CPI (Control Program Information) utilities for s390 guests.

This module provides utilities to obtain and test CPI information from s390x guests
using QEMU monitor commands and compare them with actual guest distribution data.

For Secure Execution guests, CPI field access (system_level, system_type, system_name,
sysplex_name) requires the CPI_PERMIT_ON_PVGUEST parameter to be set to '1' in the
guest's /etc/sysconfig/cpi configuration file. Without this setting, these fields
will not be retrievable for Secure Execution guests.

Example usage:

    # Basic usage with VM instance
    from virttest.utils_cpi import CPIChecker

    def run(test, params, env):
        vm_name = params.get('main_vm')
        vm = env.get_vm(vm_name)

        # Create CPI checker
        checker = CPIChecker(vm, serial=False)  # Use serial=True for serial login

        # Get all CPI fields and run checks
        results = checker.run_all_checks()

        # Or get individual fields
        system_level = checker.get_cpi_field('system_level')

        # Or run individual checks
        checker.check_system_type()    # Compares with configured CPI_SYSTEM_TYPE
        checker.check_system_name()    # Compares with configured CPI_SYSTEM_NAME
        checker.check_sysplex_name()   # Compares with configured CPI_SYSPLEX_NAME
        checker.check_system_level()   # Compares with guest distribution info

    # Using convenience functions
    from virttest.utils_cpi import (get_cpi_field, check_cpi_fields,
                                    get_human_readable_timestamp,
                                    get_human_readable_system_level,
                                    get_human_readable_summary,
                                    set_cpi_config, get_cpi_config, restore_cpi_config)

    # Set CPI configuration in guest
    set_cpi_config(vm, system_type="LINUX", system_name="TESTVM", sysplex_name="TESTPLEX")

    # For Secure Execution guests, enable CPI field access
    set_cpi_config(vm, permit_on_pvguest="1")

    # Get current CPI configuration
    config = get_cpi_config(vm)
    print(f"Current config: {config}")

    # Restore original CPI configuration from backup
    restore_cpi_config(vm, reboot=True)  # reboot=True by default

    # Note: Configuration changes require a reboot to take effect
    # The reboot is performed automatically by default

    # Interactive console usage
    # >>> from virttest.utils_cpi import CPIChecker
    # >>> checker = CPIChecker(vm)
    # >>> checker.set_cpi_config(system_type="LINUX", system_name="MYVM")
    # >>> checker.get_all_cpi_fields()  # Get CPI data first
    # >>> print(checker.get_human_readable_summary())
    # >>> timestamp = checker.get_human_readable_timestamp()
    # >>> system_level = checker.get_human_readable_system_level()
    # >>> checker.restore_cpi_config(reboot=False)  # Restore original config
"""

import datetime
import json
import logging as log

from virttest import utils_misc, virsh
from virttest.utils_test import libvirt

logging = log.getLogger("avocado." + __name__)

# CPI field definitions
CPI_FIELDS = {
    "system_level": {"type": "uint64"},
    "system_name": {"type": "string"},
    "system_type": {"type": "string"},
    "timestamp": {"type": "uint64"},
    "sysplex_name": {"type": "string"},
}

# ref. qemu/hw/s390x/sclpcpi.c
DISTRIBUTION_MAP = {
    0: "generic Linux",
    1: "Red Hat Enterprise Linux",
    2: "SUSE Linux Enterprise Server",
    3: "Canonical Ubuntu",
    4: "Fedora",
    5: "openSUSE Leap",
    6: "Debian GNU/Linux",
    7: "Red Hat Enterprise Linux CoreOS",
}


class CPIChecker(object):
    """CPI checker for s390 guests"""

    def __init__(self, vm, serial=False):
        """
        Initialize CPI checker

        :param vm: libvirt_vm.VM instance to check
        :param serial: If True, use serial login for guest operations
        """
        self.vm = vm
        self.vm_name = vm.name
        self.serial = serial
        self.cpi_data = {}
        self.guest_distro_info = {}

    def get_cpi_field(self, field_name, debug=True):
        """
        Get a specific CPI field from the guest using QEMU monitor command

        :param field_name: Name of the CPI field to retrieve
        :param debug: If True, enable debug logging for the QEMU monitor command
        :return: The value of the CPI field
        :raises: RuntimeError if field retrieval fails
        """
        if field_name not in CPI_FIELDS:
            raise ValueError(f"Unknown CPI field: {field_name}")

        qmp_cmd = {
            "execute": "qom-get",
            "arguments": {
                "path": "/machine/sclp/s390-sclp-event-facility/sclpcpi",
                "property": field_name,
            },
        }

        try:
            result = virsh.qemu_monitor_command(
                self.vm_name, json.dumps(qmp_cmd), debug=debug
            )

            libvirt.check_exit_status(result)

            response = json.loads(result.stdout_text)

            if "return" not in response:
                raise RuntimeError(f"No 'return' field in QEMU response: {response}")

            value = response["return"]

            if CPI_FIELDS[field_name]["type"] == "string" and isinstance(value, str):
                value = value.strip()

            self.cpi_data[field_name] = value
            logging.debug(f"Retrieved CPI field '{field_name}': {value}")

            return value

        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse QEMU response as JSON: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to get CPI field '{field_name}': {e}")

    def get_all_cpi_fields(self, debug=True):
        """
        Get all CPI fields from the guest

        :param debug: If True, enable debug logging for QEMU monitor commands
        :return: Dictionary containing all CPI field values
        """
        for field_name in CPI_FIELDS.keys():
            try:
                self.get_cpi_field(field_name, debug=debug)
            except Exception as e:
                logging.warning(f"Failed to get CPI field '{field_name}': {e}")
                self.cpi_data[field_name] = None

        return self.cpi_data

    def get_guest_distro_info(self):
        """
        Get distribution information from guest VM using utils_misc function

        :return: Dictionary with guest distribution information
        """
        guest_distro_info = utils_misc.get_guest_distro_info(
            self.vm, serial=self.serial
        )
        self.guest_distro_info = guest_distro_info
        return guest_distro_info

    def _check_string(self, field_name):
        """
        Check that a string CPI field matches the configured value

        :param field_name: Name of the CPI field to check (e.g., 'system_type', 'system_name', 'sysplex_name')
        :return: True if check passes
        :raises: AssertionError if check fails
        :raises: RuntimeError if field not available in CPI data
        """
        if field_name not in self.cpi_data:
            raise RuntimeError(f"{field_name} not available in CPI data")

        value = self.cpi_data[field_name]

        # Map field names to config keys
        config_key_map = {
            "system_type": "CPI_SYSTEM_TYPE",
            "system_name": "CPI_SYSTEM_NAME",
            "sysplex_name": "CPI_SYSPLEX_NAME",
        }

        config_key = config_key_map.get(field_name)
        if config_key is None:
            raise ValueError(f"Unknown field name for string check: {field_name}")

        try:
            config = self.get_cpi_config()
            expected_value = config.get(config_key, "")
        except Exception as e:
            logging.warning(f"Could not read CPI config, using empty string: {e}")
            expected_value = ""

        if value == "" and expected_value != "":
            raise AssertionError(
                f"{field_name} is empty (Secure Execution guest without CPI_PERMIT_ON_PVGUEST='1'?). "
                f"Expected: {expected_value}"
            )

        if value != expected_value:
            raise AssertionError(
                f"{field_name} mismatch: expected '{expected_value}', got '{value}'"
            )

        logging.info(f"{field_name} check passed: {value}")
        return True

    def check_system_type(self):
        """
        Check that system_type matches the configured value

        :return: True if check passes
        :raises: AssertionError if check fails
        """
        return self._check_string("system_type")

    def check_system_name(self):
        """
        Check that system_name matches the configured value

        :return: True if check passes
        :raises: AssertionError if check fails
        """
        return self._check_string("system_name")

    def check_sysplex_name(self):
        """
        Check that sysplex_name matches the configured value

        :return: True if check passes
        :raises: AssertionError if check fails
        """
        return self._check_string("sysplex_name")

    def check_timestamp(self, max_age_delta=120):
        """
        Check timestamp field

        The CPI info is expected to be written and have timestamp during boot
        (when the cpi.service runs during boot), assume reasonable default value.

        :param max_age_delta: Maximum allowed age difference in seconds (default: 120)
        :return: True if timestamp is valid
        :raises: AssertionError if check fails
        """
        if "timestamp" not in self.cpi_data:
            raise RuntimeError("timestamp not available in CPI data")

        timestamp = self.cpi_data["timestamp"]
        if not isinstance(timestamp, (int, float)) or timestamp <= 0:
            raise AssertionError(f"Invalid timestamp: {timestamp}")

        timestamp_seconds = timestamp / 1_000_000_000

        current_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        time_diff = abs(current_time - timestamp_seconds)

        if time_diff > max_age_delta:
            raise AssertionError(
                f"Timestamp too old: {time_diff:.2f}s ago (max allowed: {max_age_delta}s). "
                f"Current time: {current_time}, CPI timestamp: {timestamp_seconds}"
            )

        logging.info(
            f"timestamp check passed: {timestamp} (converted to {timestamp_seconds})"
        )
        return True

    def check_system_level(self):
        """
        Check system_level against guest distribution information

        :return: True if check passes
        :raises: AssertionError if check fails
        """
        if "system_level" not in self.cpi_data:
            raise RuntimeError("system_level not available in CPI data")

        system_level = self.cpi_data["system_level"]
        parsed_level = self._parse_system_level(system_level)

        guest_distro_info = self.get_guest_distro_info()
        expected_type = self._map_distro_to_system_level(guest_distro_info)

        if expected_type != parsed_level["distribution_type"]:
            raise AssertionError(
                f"Distribution type mismatch: expected {expected_type} "
                f"({DISTRIBUTION_MAP.get(expected_type, 'Unknown')}), "
                f"got {parsed_level['distribution_type']} "
                f"({DISTRIBUTION_MAP.get(parsed_level['distribution_type'], 'Unknown')})"
            )

        kernel_parts = guest_distro_info["kernel_parts"]
        if (
            parsed_level["kernel_major"] != kernel_parts["major"]
            or parsed_level["kernel_minor"] != kernel_parts["minor"]
            or parsed_level["kernel_stable"] != kernel_parts["stable"]
            or parsed_level["patch_level"] != kernel_parts["patch_level"]
        ):
            raise AssertionError(
                f"Kernel version mismatch: expected "
                f"{kernel_parts['major']}.{kernel_parts['minor']}.{kernel_parts['stable']}-{kernel_parts['patch_level']}, "
                f"got {parsed_level['kernel_major']}.{parsed_level['kernel_minor']}.{parsed_level['kernel_stable']}-{parsed_level['patch_level']}"
            )

        logging.info(f"system_level check passed: {system_level} -> {parsed_level}")
        return True

    def _parse_system_level(self, system_level):
        """
        Parse the system_level value according to s390 specification

        :param system_level: The system_level value from CPI
        :return: Dictionary with parsed components
        """
        hex_value = f"0x{system_level:016x}"

        hex_str = hex_value[2:]

        if len(hex_str) != 16:
            raise ValueError(f"Invalid system level format: {hex_value}")

        parsed_level = {
            "hypervisor_bit": int(hex_str[0], 16) >> 3,
            "distribution_type": int(hex_str[1], 16),
            "major_version": int(hex_str[2:4], 16),
            "minor_version": int(hex_str[4:6], 16),
            "patch_level": int(hex_str[6:10], 16),
            "kernel_major": int(hex_str[10:12], 16),
            "kernel_minor": int(hex_str[12:14], 16),
            "kernel_stable": int(hex_str[14:16], 16),
        }

        return parsed_level

    def _map_distro_to_system_level(self, distro_info):
        """
        Map distribution info to expected system level type

        :param distro_info: Guest distribution information
        :return: Expected distribution type code
        """
        distro_id = distro_info.get("id", "").lower()
        distro_name = distro_info.get("name", "").lower()

        if "rhel" in distro_id or "redhat" in distro_id or "red hat" in distro_name:
            if "coreos" in distro_id or "coreos" in distro_name:
                return 7  # Red Hat Enterprise Linux CoreOS
            else:
                return 1  # Red Hat Enterprise Linux
        elif "sles" in distro_id or "suse" in distro_id or "suse" in distro_name:
            if "leap" in distro_id or "leap" in distro_name:
                return 5  # openSUSE Leap
            else:
                return 2  # SUSE Linux Enterprise Server
        elif "ubuntu" in distro_id or "ubuntu" in distro_name:
            return 3  # Canonical Ubuntu
        elif "fedora" in distro_id or "fedora" in distro_name:
            return 4  # Fedora
        elif "debian" in distro_id or "debian" in distro_name:
            return 6  # Debian GNU/Linux
        else:
            return 0  # generic Linux

    def run_all_checks(self, max_age_delta=120):
        """
        Run all CPI checks, collecting all results before reporting failures

        :param max_age_delta: Maximum allowed age difference for timestamp in seconds (default: 120)
        :return: Dictionary with check results and status
        """
        results = {"status": "PASS", "checks": {}, "errors": []}

        try:
            self.get_all_cpi_fields(debug=True)
        except Exception as e:
            results["status"] = "ERROR"
            results["errors"].append(f"Failed to get CPI data: {e}")
            return results

        check_methods = {
            "system_type": self.check_system_type,
            "system_name": self.check_system_name,
            "sysplex_name": self.check_sysplex_name,
            "timestamp": lambda: self.check_timestamp(max_age_delta),
            "system_level": self.check_system_level,
        }

        for check_name, check_method in check_methods.items():
            try:
                result = check_method()
                results["checks"][check_name] = {"status": "PASS", "result": result}
            except Exception as e:
                results["checks"][check_name] = {"status": "FAIL", "error": str(e)}
                results["errors"].append(f"{check_name}: {e}")
                results["status"] = "FAIL"

        if results["status"] == "PASS":
            logging.info("All CPI checks completed successfully")
        else:
            logging.error(f"CPI checks failed: {len(results['errors'])} errors")
            for error in results["errors"]:
                logging.error(f"  - {error}")

        return results

    def get_human_readable_timestamp(self):
        """
        Get human-readable UTC timestamp from CPI data

        Note: CPI data must be retrieved first using get_cpi_field('timestamp')
        or get_all_cpi_fields() before calling this method.

        :return: Human-readable timestamp string
        :raises: RuntimeError if timestamp not available
        """
        if "timestamp" not in self.cpi_data:
            raise RuntimeError("timestamp not available in CPI data")

        timestamp = self.cpi_data["timestamp"]

        timestamp_seconds = timestamp / 1_000_000_000

        try:
            try:
                dt = datetime.datetime.fromtimestamp(
                    timestamp_seconds, tz=datetime.timezone.utc
                )
                return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except AttributeError:
                dt = datetime.datetime.utcfromtimestamp(timestamp_seconds)
                return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, OSError) as e:
            return f"Invalid timestamp: {timestamp} (error: {e})"

    def get_human_readable_system_level(self):
        """
        Get human-readable system level information from CPI data

        Note: CPI data must be retrieved first using get_cpi_field('system_level')
        or get_all_cpi_fields() before calling this method.

        :return: Dictionary with human-readable system level info
        :raises: RuntimeError if system_level not available
        """
        if "system_level" not in self.cpi_data:
            raise RuntimeError("system_level not available in CPI data")

        system_level = self.cpi_data["system_level"]
        parsed_level = self._parse_system_level(system_level)

        try:
            guest_distro_info = self.get_guest_distro_info()
        except Exception as e:
            guest_distro_info = {"error": f"Failed to get guest distro info: {e}"}

        result = {
            "raw_value": system_level,
            "hex_value": f"0x{system_level:016x}",
            "hypervisor_used": bool(parsed_level["hypervisor_bit"]),
            "distribution": {
                "type_code": parsed_level["distribution_type"],
                "type_name": DISTRIBUTION_MAP.get(
                    parsed_level["distribution_type"], "Unknown"
                ),
                "major_version": parsed_level["major_version"],
                "minor_version": parsed_level["minor_version"],
            },
            "kernel": {
                "version": f"{parsed_level['kernel_major']}.{parsed_level['kernel_minor']}.{parsed_level['kernel_stable']}",
                "major": parsed_level["kernel_major"],
                "minor": parsed_level["kernel_minor"],
                "stable": parsed_level["kernel_stable"],
                "patch_level": parsed_level["patch_level"],
            },
            "guest_comparison": guest_distro_info,
        }

        return result

    def set_cpi_config(
        self,
        system_type=None,
        system_name=None,
        sysplex_name=None,
        permit_on_pvguest=None,
        reboot=True,
    ):
        """
        Set CPI configuration parameters in the guest's /etc/sysconfig/cpi file

        :param system_type: System type value (e.g., "LINUX")
        :param system_name: System name value
        :param sysplex_name: Sysplex name value
        :param permit_on_pvguest: If '1', allows CPI field access for Secure Execution guests
        :param reboot: If True, reboot the guest after configuration update
        :return: True if configuration was set successfully
        :raises: RuntimeError if configuration fails
        """
        config_file = "/etc/sysconfig/cpi"
        config_updates = {}

        if system_type is not None:
            config_updates["CPI_SYSTEM_TYPE"] = system_type
        if system_name is not None:
            config_updates["CPI_SYSTEM_NAME"] = system_name
        if sysplex_name is not None:
            config_updates["CPI_SYSPLEX_NAME"] = sysplex_name
        if permit_on_pvguest is not None:
            config_updates["CPI_PERMIT_ON_PVGUEST"] = str(permit_on_pvguest)

        if not config_updates:
            logging.warning("No CPI configuration parameters provided")
            return True

        session = None
        try:
            if self.serial:
                session = self.vm.wait_for_serial_login(timeout=60)
            else:
                session = self.vm.wait_for_login(timeout=60)

            try:
                result = session.cmd_output(f"cat {config_file}")
                existing_config = result.strip()
            except Exception:
                existing_config = ""
                logging.info(f"Creating new CPI configuration file: {config_file}")

            config_lines = existing_config.split("\n") if existing_config else []
            config_dict = {}

            for line in config_lines:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    config_dict[key.strip()] = value.strip().strip("\"'")

            config_dict.update(config_updates)

            new_config_lines = []
            new_config_lines.append("# CPI (Control Program Information) Configuration")
            new_config_lines.append(
                "# This file is automatically managed by CPI utilities"
            )
            new_config_lines.append("")

            for key in [
                "CPI_SYSTEM_TYPE",
                "CPI_SYSTEM_NAME",
                "CPI_SYSPLEX_NAME",
                "CPI_PERMIT_ON_PVGUEST",
            ]:
                if key in config_dict:
                    value = config_dict[key]
                    new_config_lines.append(f'{key}="{value}"')

            new_config_content = "\n".join(new_config_lines)

            temp_file = "/tmp/cpi_config_new"
            session.cmd(f"cat > {temp_file} << 'EOF'\n{new_config_content}\nEOF")

            session.cmd(f"cat {config_file} > {config_file}.backup 2>/dev/null || true")
            session.cmd(f"mv -f {temp_file} {config_file}")
            session.cmd(f"chmod 644 {config_file}")
            session.cmd(f"restorecon {config_file} 2>/dev/null || true")

            logging.info(f"CPI configuration updated: {list(config_updates.keys())}")

            if reboot:
                logging.info("Rebooting guest to apply CPI configuration changes...")
                try:
                    self.vm.reboot()
                    logging.info("Guest reboot completed successfully")
                except Exception as e:
                    logging.warning(f"Guest reboot failed: {e}")

            return True

        except Exception as e:
            raise RuntimeError(f"Failed to set CPI configuration: {e}")
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception as e:
                    logging.warning(f"Failed to close session: {e}")

    def restore_cpi_config(self, reboot=True):
        """
        Restore the original CPI configuration from backup file

        :param reboot: If True, reboot the guest after configuration restore
        :return: True if configuration was restored successfully
        :raises: RuntimeError if restore fails or no backup file exists
        """
        config_file = "/etc/sysconfig/cpi"
        backup_file = f"{config_file}.backup"
        session = None

        try:
            if self.serial:
                session = self.vm.wait_for_serial_login(timeout=60)
            else:
                session = self.vm.wait_for_login(timeout=60)

            result = session.cmd(
                f"test -f {backup_file} && echo 'exists' || echo 'not_found'"
            )
            if "not_found" in result:
                raise RuntimeError(f"No backup file found at {backup_file}")

            session.cmd(f"mv -f {backup_file} {config_file}")
            session.cmd(f"chmod 644 {config_file}")
            session.cmd(f"restorecon {config_file} 2>/dev/null || true")

            logging.info("CPI configuration restored from backup")

            if reboot:
                logging.info("Rebooting guest to apply restored CPI configuration...")
                try:
                    self.vm.reboot()
                    logging.info("Guest reboot completed successfully")
                except Exception as e:
                    logging.warning(f"Guest reboot failed: {e}")

            return True

        except Exception as e:
            raise RuntimeError(f"Failed to restore CPI configuration: {e}")
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception as e:
                    logging.warning(f"Failed to close session: {e}")

    def get_cpi_config(self):
        """
        Get current CPI configuration from the guest's /etc/sysconfig/cpi file

        :return: Dictionary with current CPI configuration
        :raises: RuntimeError if configuration cannot be read
        """
        config_file = "/etc/sysconfig/cpi"
        session = None

        try:
            if self.serial:
                session = self.vm.wait_for_serial_login(timeout=60)
            else:
                session = self.vm.wait_for_login(timeout=60)

            result = session.cmd_output(f"cat {config_file}")
            config_lines = result.strip().split("\n") if result.strip() else []

            config_dict = {}
            for line in config_lines:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    config_dict[key.strip()] = value.strip().strip("\"'")

            return config_dict

        except Exception as e:
            raise RuntimeError(f"Failed to read CPI configuration: {e}")
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception as e:
                    logging.warning(f"Failed to close session: {e}")

    def get_human_readable_summary(self):
        """
        Get a comprehensive human-readable summary of all CPI data

        Note: CPI data must be retrieved first using get_all_cpi_fields()
        before calling this method.

        :return: Formatted string with all CPI information
        """
        summary_lines = []
        summary_lines.append("CPI Information Summary")
        summary_lines.append("=" * 50)

        try:
            self.get_all_cpi_fields(debug=False)
        except Exception as e:
            summary_lines.append(f"Error getting CPI data: {e}")
            return "\n".join(summary_lines)

        if "system_type" in self.cpi_data:
            summary_lines.append(f"System Type: {self.cpi_data['system_type']}")

        if "system_name" in self.cpi_data:
            summary_lines.append(f"System Name: {self.cpi_data['system_name']}")

        if "sysplex_name" in self.cpi_data:
            summary_lines.append(f"Sysplex Name: {self.cpi_data['sysplex_name']}")

        try:
            timestamp_str = self.get_human_readable_timestamp()
            summary_lines.append(f"Timestamp: {timestamp_str}")
        except Exception as e:
            summary_lines.append(f"Timestamp: Error - {e}")

        try:
            system_level_info = self.get_human_readable_system_level()
            summary_lines.append("")
            summary_lines.append("System Level Details:")
            summary_lines.append(f"  Raw Value: {system_level_info['raw_value']}")
            summary_lines.append(f"  Hex Value: {system_level_info['hex_value']}")
            summary_lines.append(
                f"  Hypervisor Used: {system_level_info['hypervisor_used']}"
            )

            distro = system_level_info["distribution"]
            summary_lines.append(
                f"  Distribution: {distro['type_name']} (type {distro['type_code']})"
            )
            summary_lines.append(
                f"  Version: {distro['major_version']}.{distro['minor_version']}"
            )

            kernel = system_level_info["kernel"]
            summary_lines.append(
                f"  Kernel: {kernel['version']}-{kernel['patch_level']}"
            )

            guest_info = system_level_info["guest_comparison"]
            if "error" not in guest_info:
                summary_lines.append("")
                summary_lines.append("Guest Distribution (for comparison):")
                if "id" in guest_info:
                    summary_lines.append(f"  ID: {guest_info['id']}")
                if "name" in guest_info:
                    summary_lines.append(f"  Name: {guest_info['name']}")
                if "version_id" in guest_info:
                    summary_lines.append(f"  Version ID: {guest_info['version_id']}")
                if "kernel_version" in guest_info:
                    summary_lines.append(f"  Kernel: {guest_info['kernel_version']}")
            else:
                summary_lines.append("")
                summary_lines.append(f"Guest Distribution: {guest_info['error']}")

        except Exception as e:
            summary_lines.append(f"System Level: Error - {e}")

        return "\n".join(summary_lines)


def get_cpi_field(vm, field_name, serial=False, debug=False):
    """
    Convenience function to get a single CPI field

    :param vm: libvirt_vm.VM instance
    :param field_name: Name of the CPI field
    :param serial: If True, use serial login for guest operations
    :param debug: If True, enable debug logging for QEMU monitor commands
    :return: The field value
    """
    checker = CPIChecker(vm, serial=serial)
    return checker.get_cpi_field(field_name, debug=debug)


def check_cpi_fields(vm, serial=False, max_age_delta=60):
    """
    Convenience function to check all CPI fields

    :param vm: libvirt_vm.VM instance
    :param serial: If True, use serial login for guest operations
    :param max_age_delta: Maximum allowed age difference for timestamp in seconds (default: 60)
    :return: Dictionary with check results
    """
    checker = CPIChecker(vm, serial=serial)
    return checker.run_all_checks(max_age_delta)


def get_human_readable_timestamp(vm, serial=False, debug=False):
    """
    Convenience function to get human-readable timestamp

    This function automatically retrieves the CPI data before formatting.
    For repeated calls, consider using CPIChecker directly.

    :param vm: libvirt_vm.VM instance
    :param serial: If True, use serial login for guest operations
    :param debug: If True, enable debug logging for QEMU monitor commands
    :return: Human-readable timestamp string
    """
    checker = CPIChecker(vm, serial=serial)
    checker.get_cpi_field("timestamp", debug=debug)
    return checker.get_human_readable_timestamp()


def get_human_readable_system_level(vm, serial=False, debug=False):
    """
    Convenience function to get human-readable system level info

    This function automatically retrieves the CPI data before formatting.
    For repeated calls, consider using CPIChecker directly.

    :param vm: libvirt_vm.VM instance
    :param serial: If True, use serial login for guest operations
    :param debug: If True, enable debug logging for QEMU monitor commands
    :return: Dictionary with human-readable system level info
    """
    checker = CPIChecker(vm, serial=serial)
    checker.get_cpi_field("system_level", debug=debug)
    return checker.get_human_readable_system_level()


def get_human_readable_summary(vm, serial=False):
    """
    Convenience function to get comprehensive CPI summary

    This function automatically retrieves all CPI data before formatting.
    For repeated calls, consider using CPIChecker directly.

    :param vm: libvirt_vm.VM instance
    :param serial: If True, use serial login for guest operations
    :return: Formatted string with all CPI information
    """
    checker = CPIChecker(vm, serial=serial)
    return checker.get_human_readable_summary()


def set_cpi_config(
    vm,
    system_type=None,
    system_name=None,
    sysplex_name=None,
    permit_on_pvguest=None,
    reboot=True,
    serial=False,
):
    """
    Convenience function to set CPI configuration parameters

    :param vm: libvirt_vm.VM instance
    :param system_type: System type value (e.g., "LINUX")
    :param system_name: System name value
    :param sysplex_name: Sysplex name value
    :param permit_on_pvguest: If '1', allows CPI field access for Secure Execution guests
    :param reboot: If True, reboot the guest after configuration update
    :param serial: If True, use serial login for guest operations
    :return: True if configuration was set successfully
    """
    checker = CPIChecker(vm, serial=serial)
    return checker.set_cpi_config(
        system_type, system_name, sysplex_name, permit_on_pvguest, reboot
    )


def get_cpi_config(vm, serial=False):
    """
    Convenience function to get current CPI configuration

    :param vm: libvirt_vm.VM instance
    :param serial: If True, use serial login for guest operations
    :return: Dictionary with current CPI configuration
    """
    checker = CPIChecker(vm, serial=serial)
    return checker.get_cpi_config()


def restore_cpi_config(vm, reboot=True, serial=False):
    """
    Convenience function to restore CPI configuration from backup

    :param vm: libvirt_vm.VM instance
    :param reboot: If True, reboot the guest after configuration restore
    :param serial: If True, use serial login for guest operations
    :return: True if configuration was restored successfully
    """
    checker = CPIChecker(vm, serial=serial)
    return checker.restore_cpi_config(reboot=reboot)
