# Copyright 2013-2020 Intranet AG and contributors
#
# avocado-i2n is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# avocado-i2n is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with avocado-i2n.  If not, see <http://www.gnu.org/licenses/>.

"""
Parser for command line Cartesian parameters.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

import sys
import os
import re
from typing import Any, Callable
import logging

from avocado.core.settings import settings
from virttest import env_process
from virttest.utils_env import Env
from avocado_vt.test import VirtTest
from virttest.utils_params import Params

from . import params_parser as param
from .cartgraph import graph
from .states import setup as ss

log = logging.getLogger("avocado.job." + __name__)


def params_from_cmd(config: Params) -> None:
    """
    Produce Cartesian parameters from a command line.

    Take care of paths/utilities for all host controls.

    :param config: command line arguments
    :raises: :py:class:`ValueError` if a command line selected vm is not available
             from the configuration and thus supported or internal tests are
             restricted from the command line

    .. todo:: Any dynamically created config keys here are usually entire data
        structures like dictionaries and lists and only used internally during
        the run which makes them unfit for displaying to the user and putting
        in a namespace scope like the officially registered plugin settings.
        Let's wait to see if the multi-suite support in avocado would establish
        some standards for doing this first. Until then, the user won't directly
        interact with these keys anyway.
    """
    suite_path = settings.as_dict().get("vt.common.suite_path", ".")
    sys.path.insert(1, os.path.join(suite_path, "utils"))

    # validate typed vm names and possible vm specific restrictions
    available_vms = param.all_objects("vms")
    available_restrictions = param.all_restrictions()

    # defaults usage vs command line overriding
    use_tests_default = True
    with_nontrivial_restrictions = False
    use_vms_default = {vm_name: True for vm_name in available_vms}
    with_selected_vms = list(available_vms)

    # the run string includes only pure parameters
    param_dict = {}
    # the tests string includes the test restrictions while the vm strings include the ones for the vm variants
    tests_str, nets_str, vm_strs = "", "", {vm: "" for vm in available_vms}

    # main tokenizing loop
    for cmd_param in config["params"]:
        re_param = re.match(r"(\w+)=(.*)", cmd_param)
        if re_param is None:
            raise ValueError(
                f"Found malformed parameter on the command line '{cmd_param}' - "
                f"must be of the form <key>=<val>"
            )
        key, value = re_param.group(1, 2)
        if key == "only" or key == "no":
            # detect if this is the primary restriction to escape defaults
            for variant in re.split(r",|\.|\.\.", value):
                if variant in available_restrictions:
                    use_tests_default = False
                # else this is an auxiliary restriction
                else:
                    with_nontrivial_restrictions = True
            # main test restriction part
            tests_str += "%s %s\n" % (key, value)
        elif key.startswith("only_") or key.startswith("no_"):
            if re.match("(only|no)_nets", key):
                nets_str = (
                    "%s %s\n" % (key.replace("_nets", ""), value) if value else ""
                )
                # TODO: unify nets_str with vm_strs treatment across the Cartesian graph interface
                param_dict["nets"] = " ".join(
                    param.all_suffixes_by_restriction(nets_str)
                )
            else:
                for vm_name in available_vms:
                    if re.match(f"(only|no)_{vm_name}", key):
                        # escape defaults for this vm and use the command line
                        use_vms_default[vm_name] = False
                        # main vm restriction part
                        vm_str = (
                            "%s %s\n" % (key.replace(f"_{vm_name}", ""), value)
                            if value
                            else ""
                        )
                        vm_strs[vm_name] += vm_str
                        break
                else:
                    raise ValueError(
                        f"Invalid object restriction {key} (no such object)"
                    )
        # NOTE: comma in a parameter sense implies the same as space in config file
        elif key == "vms":
            # NOTE: no restrictions of the required vms are allowed during tests since
            # these are specified by each test (allowed only for manual setup steps)
            with_selected_vms[:] = value.split(",")
            for vm_name in with_selected_vms:
                if vm_name not in available_vms:
                    raise ValueError(
                        "The vm '%s' is not among the supported vms: "
                        "%s" % (vm_name, ", ".join(available_vms))
                    )
        elif key == "nets":
            if nets_str != "":
                raise ValueError(
                    f"Cannot specify explicit net suffixes {value} together with "
                    f"a nets restriction, currently also specified '{nets_str.rstrip()}'"
                )
            value = value.replace(",", " ")
            param_dict[key] = value
        else:
            # NOTE: comma on the command line is space in a config file
            value = value.replace(",", " ")
            param_dict[key] = value
    config["param_dict"] = param_dict
    log.debug("Parsed param dict '%s'", param_dict)

    # get minimal configurations and parse defaults if no command line arguments
    config["vms_params"], config["vm_strs"] = full_vm_params_and_strs(
        param_dict, vm_strs, use_vms_default
    )
    config["vms_params"]["vms"] = " ".join(with_selected_vms)
    config["available_vms"] = vm_strs.copy()
    for vm_name in available_vms:
        # the keys of vm strings must be equivalent to the selected vms
        if vm_name not in with_selected_vms:
            del config["vm_strs"][vm_name]
    config["tests_params"], config["tests_str"] = full_tests_params_and_str(
        param_dict, tests_str, use_tests_default
    )
    config["available_restrictions"] = available_restrictions

    # control against invoking only runnable tests and empty Cartesian products
    control_config = param.Reparsable()
    control_config.parse_next_batch(
        base_file="sets.cfg",
        ovrwrt_file=param.tests_ovrwrt_file(),
        ovrwrt_str=config["tests_str"],
        ovrwrt_dict=config["param_dict"],
    )
    control_parser = control_config.get_parser()
    if with_nontrivial_restrictions:
        log.info(
            "%s tests with nontrivial restriction %s",
            len(list(control_parser.get_dicts())),
            config["tests_str"],
        )

    # prefix for all tests of the current run making it possible to perform multiple runs in one command
    config["prefix"] = ""

    # log into files for each major level the way it was done for autotest
    config["job.run.store_logging_stream"] = ["avocado.core:DEBUG"]
    # dump parsed and traversed graph at each test loading and running step
    graph.set_graph_logging_level(
        level=config["tests_params"].get_numeric("cartgraph_verbose_level", 20)
    )

    # set default off and on state backends
    from .states import lvm, qcow2, lxc, btrfs, ramfile, pool, vmnet

    ss.BACKENDS = {
        "qcow2": qcow2.QCOW2Backend,
        "qcow2ext": qcow2.QCOW2ExtBackend,
        "lvm": lvm.LVMBackend,
        "lxc": lxc.LXCBackend,
        "btrfs": btrfs.BtrfsBackend,
        "qcow2vt": qcow2.QCOW2VTBackend,
        "ramfile": ramfile.RamfileBackend,
        "vmnet": vmnet.VMNetBackend,
    }
    ramfile.RamfileBackend.image_state_backend = qcow2.QCOW2ExtBackend

    # attach environment processing hooks
    env_process_hooks()


def full_vm_params_and_strs(
    param_dict: dict[str, str] | None,
    vm_strs: dict[str, str],
    use_vms_default: dict[str, bool],
) -> tuple[Params, dict[str, str]]:
    """
    Add default vm parameters and strings for missing command line such.

    :param param_dict: runtime parameters used for extra customization
    :param vm_strs: command line vm-specific names and variant restrictions
    :param use_vms_default: whether to use default variant restriction for a
                            particular vm
    :returns: complete vm parameters and strings
    :raises: :py:class:`ValueError` if no command line or default variant
             restriction could be found for some vm
    """
    vms_config = param.Reparsable()
    vms_config.parse_next_batch(
        base_file="guest-base.cfg",
        ovrwrt_file=param.vms_ovrwrt_file(),
        ovrwrt_dict=param_dict,
    )
    vms_params = vms_config.get_params()
    for vm_name in param.all_objects("vms"):
        if use_vms_default[vm_name]:
            default = vms_params.get("default_only_%s" % vm_name)
            vm_strs[vm_name] += "only %s\n" % default if default else ""
    log.debug("Parsed vm strings '%s'", vm_strs)
    return vms_params, vm_strs


def full_tests_params_and_str(
    param_dict: dict[str, str] | None, tests_str: str, use_tests_default: bool
) -> tuple[Params, str]:
    """
    Add default tests parameters and string for missing command line such.

    :param param_dict: runtime parameters used for extra customization
    :param tests_str: command line variant restrictions
    :param use_tests_default: whether to use default primary restriction
    :returns: complete tests parameters and string
    :raises: :py:class:`ValueError` if the default primary restriction could is
             not valid (among the available ones)
    """
    tests_config = param.Reparsable()
    tests_config.parse_next_batch(
        base_file="groups-base.cfg",
        ovrwrt_file=param.tests_ovrwrt_file(),
        ovrwrt_dict=param_dict,
    )
    tests_params = tests_config.get_params()
    if use_tests_default:
        default = tests_params.get("default_only", "all")
        available_restrictions = param.all_restrictions()
        if default not in available_restrictions:
            raise ValueError(
                "Invalid primary restriction 'only=%s'! It has to be one "
                "of %s" % (default, ", ".join(available_restrictions))
            )
        tests_str += "only %s\n" % default
    log.debug("Parsed tests string '%s'", tests_str)
    return tests_params, tests_str


def env_process_hooks() -> None:
    """
    Add env processing hooks to handle needed customization steps.

    These steps include on/off state get/set operations, vmnet networking,
    and instance attachment to environment.
    """

    def on_state(fn: Callable[[Any], Any]) -> Any:
        def wrapper(test: VirtTest, params: Params, env: Env) -> Any:
            params["skip_types"] = "nets/vms/images nets"
            fn(params, env)
            del params["skip_types"]

        return wrapper

    def off_state(fn: Callable[[Any], Any]) -> Any:
        def wrapper(test: VirtTest, params: Params, env: Env) -> Any:
            params["skip_types"] = "nets/vms"
            fn(params, env)
            del params["skip_types"]

        return wrapper

    env_process.preprocess_vm_off_hook = off_state(ss.get_states)
    env_process.preprocess_vm_on_hook = on_state(ss.get_states)
    env_process.postprocess_vm_on_hook = on_state(ss.set_states)
    env_process.postprocess_vm_off_hook = off_state(ss.set_states)
