# pylint: disable=import-error,import-outside-toplevel,protected-access
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.

"""Environment-processing hooks for optional VT object state handling."""

from typing import Any, Callable

from virttest import env_process
from virttest.utils_env import Env
from virttest.utils_params import Params
from virttest.vmnet import setup_vmnet

from . import setup


def install_default_backends() -> None:
    """Install the state backends used by the multi-VM sample suite."""
    from . import (
        btrfs,
        lvm,
        lxc,
        qcow2,
        ramfile,
        vmnet,
    )

    setup.BACKENDS = {
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


def setup_vmnet_hook(_test: object, params: Params, env: Env) -> None:
    """Adapt state-independent VMNetwork setup to an environment hook.

    :param params: parameters used to configure the runtime VM network
    :param env: VT environment to attach the runtime VM network to
    """
    setup_vmnet(params, env)


def _with_vmnet(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Ensure the runtime VMNetwork exists after a previous hook.

    :param fn: environment hook to run before network preparation
    :returns: composed environment hook
    """

    def wrapper(test: Any, params: Any, env: Any) -> None:
        fn(test, params, env)
        setup_vmnet_hook(test, params, env)

    return wrapper


def _close_sessions(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Close state and GUI sessions after a previous hook.

    :param fn: final state operation hook
    :returns: hook that also closes persistent sessions
    """

    def wrapper(test: Any, params: Any, env: Any) -> None:
        fn(test, params, env)
        from . import pool

        for session in pool.TransferOps._session_cache.values():
            session.close()
        try:
            from vncdotool import api

            api.shutdown()
        except ImportError:
            pass

    return wrapper


def _on_state(fn: Callable[..., Any], action: str) -> Callable[..., Any]:
    """Adapt a state operation to the VM-on environment hook interface."""

    def wrapper(_test: Any, params: Any, env: Any) -> None:
        if action in ("set", "unset"):
            params["pool_scope"] = "own"
        params["skip_types"] = "nets/vms/images nets"
        try:
            fn(params, env)
        finally:
            del params["skip_types"]

    return wrapper


def _off_state(fn: Callable[..., Any], action: str) -> Callable[..., Any]:
    """Adapt a state operation to the VM-off environment hook interface."""

    def wrapper(_test: Any, params: Any, env: Any) -> None:
        if action in ("set", "unset"):
            params["pool_scope"] = "own"
        params["skip_types"] = "nets/vms"
        try:
            fn(params, env)
        finally:
            del params["skip_types"]

    return wrapper


def configure_env_process_hooks(use_states: bool) -> None:
    """Install stateful or state-free hooks with the same VMNetwork interface.

    :param use_states: whether to install VM, image, and network state hooks

    These steps include on/off state get/set operations, vmnet networking,
    and instance attachment to environment.
    """
    if not use_states:
        env_process.preprocess_vm_off_hook = setup_vmnet_hook
        env_process.preprocess_vm_on_hook = None
        env_process.postprocess_vm_on_hook = None
        env_process.postprocess_vm_off_hook = None
        return

    install_default_backends()
    env_process.preprocess_vm_off_hook = _with_vmnet(
        _off_state(setup.get_states, "get")
    )
    env_process.preprocess_vm_on_hook = _on_state(setup.get_states, "get")
    env_process.postprocess_vm_on_hook = _on_state(setup.set_states, "set")
    env_process.postprocess_vm_off_hook = _close_sessions(
        _off_state(setup.set_states, "set")
    )
