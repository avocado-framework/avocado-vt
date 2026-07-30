#
# library for cpu related helper functions
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; specifically version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat (c) 2023 and Avocado contributors
# Author: Houqi Zuo <hzuo@redhat.com>
import re

from avocado.utils import process


def get_cpu_info():
    """
    Return information about the CPU information.

    :return: cpu information
    :rtype: list[dict]
    """
    cpu_info = list()
    with open("/proc/cpuinfo") as fd:
        processors = fd.read().strip().split("\n\n")
    for processor in processors:
        if processor != "":
            info = dict(
                map(
                    lambda x: [i.strip() for i in x.split(":", 1)],
                    processor.split("\n"),
                )
            )
            cpu_info.append(info)

    return cpu_info


def get_cpu_model_name():
    """
    Return physical cpu model.

    :return: cpu model name
    :rtype: string
    :raises: An OSError will be raised if it's NOT available on the platform
    """
    cpu_model = process.run("lscpu").stdout_text
    cpu_model_re = "(?m)^[mM]odel name:.*$"
    cpu_model = re.search(cpu_model_re, cpu_model)
    if not cpu_model:
        raise OSError("The cpu model name was NOT found!")
    cpu_model = cpu_model.group()
    return cpu_model.split(":", 1)[-1].strip()


def get_cpu_flags():
    """
    Return a list of the CPU flags.

    :return: cpu flags
    :rtype: list[string]
    :raises: An OSError will be raised if it's NOT available on the platform
    """
    cpu_flags_re = "(?m)^flags\s+:\s+([\w\s]+)$"
    with open("/proc/cpuinfo") as fd:
        cpu_info = fd.read()
    cpu_flags = re.search(cpu_flags_re, cpu_info)
    if not cpu_flags:
        raise OSError("The cpu flags were NOT found!")
    cpu_flags = cpu_flags.groups()[0]
    return re.split("\s+", cpu_flags.strip())


def get_cpu_features():
    """
    Return a list of the CPU features.

    :return: cpu features
    :rtype: list[string]
    :raises: An OSError will be raised if it's NOT available on the platform
    """
    cpu_features_re = "(?m)^[fF]eatures\s+:\s+([\w\s]+)$"
    with open("/proc/cpuinfo") as fd:
        cpu_info = fd.read()
    cpu_features = re.search(cpu_features_re, cpu_info)
    if not cpu_features:
        raise OSError("The cpu features were NOT found!")
    cpu_features = cpu_features.groups()[0]
    return re.split("\s+", cpu_features.strip())


def get_cpu_vendor_id():
    """
    Return the name of the CPU vendor ID.

    :return: the name of the CPU vendor ID in string
    :rtype: string
    :raises: An OSError will be raised if it's NOT available on the platform
    """
    vendor_re = "(?m)^vendor_id\s+:\s+(\w+)$"
    with open("/proc/cpuinfo") as fd:
        cpu_info = fd.read()
    vendor_id = re.search(vendor_re, cpu_info)
    if not vendor_id:
        raise OSError("The vendor id was NOT found!")
    vendor_id = vendor_id.groups()[0]
    return vendor_id


def get_cpu_family():
    """
    Return the name of cpu family.

    :return: the name of the cpu family in string
    :rtype: string
    :raises: An OSError will be raised if it's NOT available on the platform
    """
    cpu_family_re = "cpu family\s+:\s+(\w+)"
    with open("/proc/cpuinfo") as fd:
        cpu_info = fd.read()
    cpu_family = re.search(cpu_family_re, cpu_info)
    if not cpu_family:
        raise OSError("The cpu family was NOT found!")
    cpu_family = cpu_family.groups()[0]
    return cpu_family


def get_cpu_id():
    """
    Return the cpu model id.

    :return: the id of the cpu model in string
    :rtype: string
    :raises: An OSError will be raised if it's NOT available on the platform
    """
    cpu_model_re = r"(?m)^model\s+:\s+(\d+)$"
    with open("/proc/cpuinfo") as fd:
        cpu_info = fd.read()
    cpu_model = re.search(cpu_model_re, cpu_info)
    if not cpu_model:
        raise OSError("The cpu model id was NOT found!")
    cpu_model_id = cpu_model.groups()[0]
    return cpu_model_id


# AMD CPU codename mappings ordered from oldest to newest.
# Each entry is (codename, family, [(model_min, model_max), ...], generation).
# Codenames that share a generation (e.g. genoa and bergamo) are treated as
# equivalent for minimum-generation checks.  Ranges sourced from
# arch/x86/kernel/cpu/amd.c (upstream Linux kernel).
_AMD_CPU_CODENAMES = [
    ("milan", 25, [(0, 15)], 3),
    ("genoa", 25, [(16, 31)], 4),
    ("bergamo", 25, [(160, 175)], 4),
    ("turin", 26, [(0, 47), (64, 79), (96, 127), (208, 215)], 5),
    ("venice", 26, [(80, 95), (128, 175), (192, 207), (216, 239)], 6),
]


def get_cpu_codename(vendor=None):
    """
    Return the microarchitecture codename for the host CPU.

    :param vendor: optional vendor_id override (defaults to get_cpu_vendor_id())
    :type vendor: str or None
    :return: detected CPU codename
    :rtype: str
    :raises NotImplementedError: if codename detection is not implemented for
        the vendor
    :raises OSError: if family/model is unrecognised
    """
    vendor = vendor or get_cpu_vendor_id()
    if vendor != "AuthenticAMD":
        raise NotImplementedError(
            f"CPU codename detection is not implemented for vendor '{vendor}'."
        )

    family = int(get_cpu_family())
    model = int(get_cpu_id())
    for codename, fam, ranges, _generation in _AMD_CPU_CODENAMES:
        if fam == family and any(lo <= model <= hi for lo, hi in ranges):
            return codename
    raise OSError(f"Unrecognised AMD CPU: family={family}, model={model}.")


def verify_min_cpu_codename(min_codename, vendor=None):
    """
    Verify the host CPU codename meets a minimum generation requirement.

    :param min_codename: minimum required codename (e.g. "milan")
    :param vendor: optional vendor_id override (defaults to get_cpu_vendor_id())
    :return: detected CPU codename when the requirement is met
    :raises NotImplementedError: if codename detection is not implemented for
        the vendor
    :raises ValueError: if min_codename is not a recognised codename for the
        vendor
    :raises OSError: if family/model is unrecognised or the host CPU is older
        than min_codename
    """
    min_codename = min_codename.lower()
    generations = {
        codename: generation
        for codename, _fam, _ranges, generation in _AMD_CPU_CODENAMES
    }
    if min_codename not in generations:
        raise ValueError(
            f"Unknown CPU codename '{min_codename}'. "
            f"Valid options: {', '.join(generations)}"
        )

    detected = get_cpu_codename(vendor=vendor)
    detected_gen = generations[detected]
    required_gen = generations[min_codename]
    if detected_gen < required_gen:
        raise OSError(
            f"Detected CPU codename '{detected}' (generation {detected_gen}) "
            f"is older than the required minimum '{min_codename}' "
            f"(generation {required_gen})."
        )
    return detected


def get_cpu_stepping():
    """
    Return the name of cpu stepping.

    :return: the name of the cpu stepping in string
    :rtype: string
    :raises: An OSError will be raised if it's NOT available on the platform
    """
    stepping_re = "(?m)^stepping\s+:\s+(\w+)$"
    with open("/proc/cpuinfo") as fd:
        cpu_info = fd.read()
    stepping = re.search(stepping_re, cpu_info)
    if not stepping:
        raise OSError("The cpu stepping was NOT found!")
    stepping = stepping.groups()[0]
    return stepping
