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
#
# Copyright 2013-2026 Intranet AG and contributors
# Author: Plamen Dimitrov <plamen.dimitrov@intra2net.com>

"""
Utility to manage off and on test object states.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

import os
from typing import Any
from typing import Generator
import logging as log

from avocado.core import exceptions
from avocado_vt.test import VirtTest
from virttest.utils_env import Env
from virttest.utils_params import Params

logging = log.getLogger("avocado.job." + __name__)


#: list of all available state backends and operations
__all__ = [
    "BACKENDS",
    "ROOTS",
    "show_states",
    "check_states",
    "get_states",
    "set_states",
    "unset_states",
    "push_states",
    "pop_states",
]


class StateBackend:
    """A general backend implementing state manipulation."""

    @classmethod
    def show(cls, params: dict[str, str], object: Any = None) -> list[str]:
        """
        Return a list of available states of a specific type.

        :param params: configuration parameters
        :param object: object whose states are manipulated
        :returns: list of detected states
        """
        raise NotImplementedError("Cannot use abstract state backend")

    @classmethod
    def get(cls, params: dict[str, str], object: Any = None) -> None:
        """
        Retrieve a state disregarding the current changes.

        :param params: configuration parameters
        :param object: object whose states are manipulated
        """
        raise NotImplementedError("Cannot use abstract state backend")

    @classmethod
    def set(cls, params: dict[str, str], object: Any = None) -> None:
        """
        Store a state saving the current changes.

        :param params: configuration parameters
        :param object: object whose states are manipulated
        """
        raise NotImplementedError("Cannot use abstract state backend")

    @classmethod
    def unset(cls, params: dict[str, str], object: Any = None) -> None:
        """
        Remove a state with previous changes.

        :param params: configuration parameters
        :param object: object whose states are manipulated
        """
        raise NotImplementedError("Cannot use abstract state backend")

    @classmethod
    def check_root(cls, params: dict[str, str], object: Any = None) -> bool:
        """
        Check whether a root state or essentially the object exists.

        :param params: configuration parameters
        :param object: object whose states are manipulated
        :returns: whether the object (root state) is exists
        """
        raise NotImplementedError("Cannot use abstract state backend")

    @classmethod
    def get_root(cls, params: dict[str, str], object: Any = None) -> None:
        """
        Get a root state or essentially due to pre-existence do nothing.

        :param params: configuration parameters
        :param object: object whose states are manipulated
        """
        pass

    @classmethod
    def set_root(cls, params: dict[str, str], object: Any = None) -> None:
        """
        Set a root state to provide object existence.

        :param params: configuration parameters
        :param object: object whose states are manipulated
        """
        raise NotImplementedError("Cannot use abstract state backend")

    @classmethod
    def unset_root(cls, params: dict[str, str], object: Any = None) -> None:
        """
        Unset a root state to prevent object existence.

        :param params: configuration parameters
        :param object: object whose states are manipulated
        """
        raise NotImplementedError("Cannot use abstract state backend")


#: available state backend implementations
BACKENDS = {}
#: keywords reserved for root states
ROOTS = ["root", "0root", "boot", "0boot"]


def _parametric_object_iteration(
    params: dict[str, str], composites: list[tuple[str, str]] = None
) -> Generator[Params, None, None]:
    """
    Iterate over a hierarchy of stateful parametric objects.

    :param params: parameters of the parametric object is processed
    :param composites: current composite parametric object
    :raises: :py:class:`ValueError` if no hierarchy is configured
    """
    object_composition = params.objects("states_chain")
    if len(object_composition) == 0:
        raise ValueError(
            "Have to specify at least one parametric object type "
            "or an overall composition through `states_chain`"
        )
    if composites is None:
        composites = []
    params_obj_type = object_composition[len(composites)]
    composites.append(None)
    for params_obj_name in params.objects(params_obj_type):
        composites[-1] = (params_obj_name, params_obj_type)
        obj_params = params.object_params(params_obj_name)
        obj_params[params_obj_type] = params_obj_name
        obj_params["object_name"] = "/".join([c[0] for c in composites])
        obj_params["object_type"] = "/".join([c[1] for c in composites])
        if params_obj_type != object_composition[-1]:
            yield from _parametric_object_iteration(obj_params, composites)
        # object type parameters don't propagate downwards in the hierarchy
        obj_type_params = obj_params.object_params(params_obj_type)
        yield obj_type_params
    composites.pop()


def _state_check_chain(
    do: str,
    env: Env,
    params_obj_type: str,
    params_obj_name: str,
    state_params: dict[str, str],
) -> bool:
    """
    State chain from set/set/unset states to check states.

    :param do: get, set, or unset
    :param env: test environment
    :param params_obj_type: type of the parametric object to check
    :param params_obj_name: name of the parametric object to check
    :param state_params: image parameters of the vm's image which is processed
    """
    state_params["check_state"] = state_params[f"{do}_state"]
    if state_params.get(f"{do}_location"):
        state_params["show_location"] = state_params[f"{do}_location"]
    if do == "set":
        state_params["check_opts"] = "soft_boot=yes"
        state_params["soft_boot"] = "yes"
    else:
        state_params["check_opts"] = "soft_boot=no"
        state_params["soft_boot"] = "no"

    # restrict inner call parameteric object types and names
    composite_types = params_obj_type.split("/")
    composite_names = params_obj_name.split("/")
    for composite_type, composite_name in zip(composite_types, composite_names):
        state_params[composite_type] = composite_name
    state_params["states_chain"] = composite_types[-1]
    state_exists = check_states(state_params, env)

    return state_exists


def show_states(run_params: Params, env: Env = None) -> list[str]:
    """
    Return a list of available states of a specific type.

    :param run_params: configuration parameters
    :param env: test environment or nothing if not needed
    :returns: list of detected states
    """
    states = []
    for state_params in _parametric_object_iteration(run_params):
        params_obj_name = state_params["object_name"]
        params_obj_type = state_params["object_type"]
        if params_obj_type in state_params.objects("skip_types"):
            continue
        if params_obj_type == "nets/vms/images" and state_params.get_boolean(
            "image_readonly", False
        ):
            logging.warning(
                f"Incorrect configuration: cannot use any state "
                f"from readonly image {params_obj_name} - skipping"
            )
            continue

        logging.debug(
            "Checking %s for available %s states using %s",
            params_obj_name,
            params_obj_type,
            state_params["states"],
        )
        state_backend = BACKENDS[state_params["states"]]
        params_obj_states = state_backend.show(state_params, env)
        logging.info(
            "Detected %s states for %s: %s",
            params_obj_type,
            params_obj_name,
            ", ".join(params_obj_states),
        )
        states += params_obj_states
    return states


def check_states(run_params: Params, env: Env = None) -> bool:
    """
    Check whether a given state exits.

    :param run_params: configuration parameters
    :returns: whether the given state exists

    .. note:: We can check for multiple states of multiple objects at the
        same time through our choice of configuration.
    """
    for state_params in _parametric_object_iteration(run_params):
        params_obj_name = state_params["object_name"]
        params_obj_type = state_params["object_type"]
        if params_obj_type in state_params.objects("skip_types"):
            continue
        if params_obj_type == "nets/vms/images" and state_params.get_boolean(
            "image_readonly", False
        ):
            logging.warning(
                f"Incorrect configuration: cannot use any state "
                f"from readonly image {params_obj_name} - skipping"
            )
            continue

        # if the snapshot is not defined skip (leaf tests that are no setup)
        if not state_params.get("check_state"):
            logging.debug(
                f"Skip checking any {params_obj_type} state for {params_obj_name}"
            )
            continue
        else:
            state = state_params["check_state"]
        # NOTE: there is no concept of "check_mode" here
        state_params["check_opts"] = state_params.get("check_opts", "soft_boot=yes")
        # TODO: document after experimental period
        state_params["check_mode"] = state_params.get("check_mode", "rf")

        state_backend = BACKENDS[state_params["states"]]
        # TODO: we don't support other parametric object instances
        vm = env.get_vm(state_params["vms"]) if env is not None else None
        # TODO: consider whether we need this with more advanced env handling
        # if vm is None and env is not None:
        #    vm = env.create_vm(state_params.get('vm_type'), state_params.get('target'),
        #                       params_obj_name, state_params, None)
        state_object = env if params_obj_type == "nets" else vm

        action_if_root_exists = state_params["check_mode"][0]
        action_if_root_doesnt_exist = state_params["check_mode"][1]

        # always check the corresponding root state as a prerequisite
        root_exists = state_backend.check_root(state_params, state_object)
        root_params = state_params.copy()
        if not root_exists:
            if action_if_root_doesnt_exist == "f":
                root_params["pool_scope"] = "own"
                state_backend.set_root(root_params, state_object)
                root_exists = True
            elif action_if_root_doesnt_exist == "r":
                return False
            else:
                raise exceptions.TestError(
                    f"Invalid policy {action_if_root_doesnt_exist}: The root "
                    "nonexistence action can be either of 'reuse' or 'force'."
                )
        elif action_if_root_exists == "f":
            root_params["pool_scope"] = "own"
            # TODO: implement unset root for all parametric object types
            if params_obj_type == "nets/vms":
                vm.destroy(
                    gracefully=root_params.get_dict("check_opts").get(
                        "soft_boot", "yes"
                    )
                    == "yes"
                )
            else:
                state_backend.unset_root(root_params, state_object)
            state_backend.set_root(root_params, state_object)
            root_exists = True
        else:
            state_backend.get_root(root_params, state_object)

        if state in ROOTS:
            state_exists = root_exists
        else:
            state_exists = state in state_backend.show(state_params, state_object)

        if not state_exists:
            return False

    return True


def get_states(run_params: Params, env: Env = None) -> None:
    """
    Retrieve a state disregarding the current changes.

    :param run_params: configuration parameters
    :raises: :py:class:`exceptions.TestAbortError` if the retrieved state doesn't exist,
        the vm is unavailable from the env, or snapshot exists in passive mode (abort)
    :raises: :py:class:`exceptions.TestError` if invalid policy was used
    """
    for state_params in _parametric_object_iteration(run_params):
        params_obj_name = state_params["object_name"]
        params_obj_type = state_params["object_type"]
        if params_obj_type in state_params.objects("skip_types"):
            logging.debug(
                f"Skip getting states of types {', '.join(state_params.objects('skip_types'))}"
            )
            continue
        if params_obj_type == "nets/vms/images" and state_params.get_boolean(
            "image_readonly", False
        ):
            logging.warning(
                f"Incorrect configuration: cannot use any state "
                f"from readonly image {params_obj_name} - skipping"
            )
            continue

        # if the state is not defined skip (leaf tests that are no setup)
        if not state_params.get("get_state"):
            logging.debug(
                f"Skip getting any {params_obj_type} state for {params_obj_name}"
            )
            continue
        else:
            state = state_params["get_state"]
        state_params["get_mode"] = state_params.get("get_mode", "ra")

        logging.info(f"Getting {params_obj_type} state {state} for {params_obj_name}")
        state_exists = _state_check_chain(
            "get", env, params_obj_type, params_obj_name, state_params
        )
        state_backend = BACKENDS[state_params["states"]]
        # TODO: we don't support other parametric object instances
        vm = env.get_vm(state_params["vms"]) if env is not None else None
        state_object = env if params_obj_type == "nets" else vm

        action_if_exists = state_params["get_mode"][0]
        action_if_doesnt_exist = state_params["get_mode"][1]
        if not state_exists and "a" == action_if_doesnt_exist:
            logging.info("Aborting because of missing snapshot for setup")
            raise exceptions.TestAbortError(
                "Snapshot '%s' of %s doesn't exist. Aborting "
                "due to passive mode." % (state_params["get_state"], params_obj_name)
            )
        elif not state_exists and "i" == action_if_doesnt_exist:
            logging.warning("Ignoring missing snapshot for setup")
            continue
        elif not state_exists:
            raise exceptions.TestError(
                "Invalid policy %s: The start action on missing state can be "
                "either of 'abort', 'ignore'." % state_params["get_mode"]
            )
        elif state_exists and "a" == action_if_exists:
            logging.info("Aborting because of unwanted snapshot for setup")
            raise exceptions.TestAbortError(
                "Snapshot '%s' of %s already exists. Aborting "
                "due to passive mode." % (state_params["get_state"], params_obj_name)
            )
        elif state_exists and "r" == action_if_exists:
            pass
        elif state_exists and "i" == action_if_exists:
            logging.warning("Ignoring present snapshot for setup")
            continue
        elif state_exists:
            raise exceptions.TestError(
                "Invalid policy %s: The start action on present state can be "
                "either of 'abort', 'reuse', 'ignore'." % state_params["get_mode"]
            )

        if state_params["get_state"] in ROOTS:
            state_backend.get_root(state_params, state_object)
        else:
            state_backend.get(state_params, state_object)


def set_states(run_params: Params, env: Env = None) -> None:
    """
    Store a state saving the current changes.

    :param run_params: configuration parameters
    :raises: :py:class:`exceptions.TestAbortError` if unexpected/missing snapshot in passive mode (abort)
    :raises: :py:class:`exceptions.TestError` if invalid policy was used
    """
    for state_params in _parametric_object_iteration(run_params):
        params_obj_name = state_params["object_name"]
        params_obj_type = state_params["object_type"]
        if params_obj_type in state_params.objects("skip_types"):
            logging.debug(
                f"Skip setting states of types {', '.join(state_params.objects('skip_types'))}"
            )
            continue
        if params_obj_type == "nets/vms/images" and state_params.get_boolean(
            "image_readonly", False
        ):
            logging.warning(
                f"Incorrect configuration: cannot use any state "
                f"from readonly image {params_obj_name} - skipping"
            )
            continue

        # if the state is not defined skip (leaf tests that are no setup)
        if not state_params.get("set_state"):
            logging.debug(
                f"Skip setting any {params_obj_type} state for {params_obj_name}"
            )
            continue
        else:
            state = state_params["set_state"]
        state_params["set_mode"] = state_params.get("set_mode", "ff")

        logging.info(f"Setting {params_obj_type} state {state} for {params_obj_name}")
        state_exists = _state_check_chain(
            "set", env, params_obj_type, params_obj_name, state_params
        )
        state_backend = BACKENDS[state_params["states"]]
        # TODO: we don't support other parametric object instances
        vm = env.get_vm(state_params["vms"]) if env is not None else None
        state_object = env if params_obj_type == "nets" else vm

        action_if_exists = state_params["set_mode"][0]
        action_if_doesnt_exist = state_params["set_mode"][1]
        if state_exists and "a" == action_if_exists:
            logging.info("Aborting because of unwanted snapshot for later cleanup")
            raise exceptions.TestAbortError(
                "Snapshot '%s' of %s already exists. Aborting "
                "due to passive mode." % (state_params["set_state"], params_obj_name)
            )
        elif state_exists and "r" == action_if_exists:
            logging.info("Keeping the already existing snapshot untouched")
            continue
        elif state_exists and "f" == action_if_exists:
            logging.info("Overwriting the already existing snapshot")
            state_params["unset_state"] = state_params["set_state"]
            if state_params["set_state"] in ROOTS:
                state_backend.unset_root(state_params, state_object)
            else:
                from .pool import SourcedStateBackend

                if issubclass(state_backend, SourcedStateBackend):
                    # overwriting arbitrary external states in the backing chain can result in invalid
                    # derivative states when branching out and other problems, do this only manually if
                    # you really know what you are doing which would depend on a case-by-case basis
                    logging.warning(
                        "Preserving the already existing snapshot due to overwrite dependency coupling"
                    )
                else:
                    logging.info("Removing the already existing snapshot")
                    state_backend.unset(state_params, state_object)
        elif state_exists:
            raise exceptions.TestError(
                "Invalid policy %s: The end action on present state can be "
                "either of 'abort', 'reuse', 'force'." % state_params["set_mode"]
            )
        elif not state_exists and "a" == action_if_doesnt_exist:
            logging.info("Aborting because of missing snapshot for later cleanup")
            raise exceptions.TestAbortError(
                "Snapshot '%s' of %s doesn't exist. Aborting "
                "due to passive mode." % (state_params["set_state"], params_obj_name)
            )
        elif not state_exists and "f" == action_if_doesnt_exist:
            if not state_params["set_state"] in ROOTS and not state_backend.check_root(
                state_params, state_object
            ):
                raise exceptions.TestError(
                    "Cannot force set state without a root state, use enforcing check "
                    "policy to also force root (existing stateful object) creation."
                )
        elif not state_exists:
            raise exceptions.TestError(
                "Invalid policy %s: The end action on missing state can be "
                "either of 'abort', 'force'." % state_params["set_mode"]
            )

        if state_params["set_state"] in ROOTS:
            state_backend.set_root(state_params, state_object)
        else:
            state_backend.set(state_params, state_object)


def unset_states(run_params: Params, env: Env = None) -> None:
    """
    Remove a state with previous changes.

    :param run_params: configuration parameters
    :raises: :py:class:`exceptions.TestAbortError` if missing snapshot in passive mode (abort)
    :raises: :py:class:`exceptions.TestError` if invalid policy was used
    """
    for state_params in _parametric_object_iteration(run_params):
        params_obj_name = state_params["object_name"]
        params_obj_type = state_params["object_type"]
        if params_obj_type in state_params.objects("skip_types"):
            logging.debug(
                f"Skip unsetting states of types {', '.join(state_params.objects('skip_types'))}"
            )
            continue
        if params_obj_type == "nets/vms/images" and state_params.get_boolean(
            "image_readonly", False
        ):
            logging.warning(
                f"Incorrect configuration: cannot use any state "
                f"from readonly image {params_obj_name} - skipping"
            )
            continue

        # if the state is not defined skip (leaf tests that are no setup)
        if not state_params.get("unset_state"):
            logging.debug(
                f"Skip unsetting any {params_obj_type} state for {params_obj_name}"
            )
            continue
        else:
            state = state_params["unset_state"]
        state_params["unset_mode"] = state_params.get("unset_mode", "fi")

        logging.info(f"Unsetting {params_obj_type} state {state} for {params_obj_name}")
        state_exists = _state_check_chain(
            "unset", env, params_obj_type, params_obj_name, state_params
        )
        state_backend = BACKENDS[state_params["states"]]
        # TODO: we don't support other parametric object instances
        vm = env.get_vm(state_params["vms"]) if env is not None else None
        state_object = env if params_obj_type == "nets" else vm

        action_if_exists = state_params["unset_mode"][0]
        action_if_doesnt_exist = state_params["unset_mode"][1]
        if not state_exists and "a" == action_if_doesnt_exist:
            logging.info("Aborting because of missing snapshot for final cleanup")
            raise exceptions.TestAbortError(
                "Snapshot '%s' of %s doesn't exist. Aborting "
                "due to passive mode." % (state_params["unset_state"], params_obj_name)
            )
        elif not state_exists and "i" == action_if_doesnt_exist:
            logging.warning(
                "Ignoring missing snapshot for final cleanup (will not be removed)"
            )
            continue
        elif not state_exists:
            raise exceptions.TestError(
                "Invalid policy %s: The unset action on missing state can be "
                "either of 'abort', 'ignore'." % state_params["unset_mode"]
            )
        elif state_exists and "r" == action_if_exists:
            logging.info(
                "Preserving state '%s' of %s for later test runs",
                state_params["unset_state"],
                params_obj_name,
            )
            continue
        elif state_exists and "f" == action_if_exists:
            pass
        elif state_exists:
            raise exceptions.TestError(
                "Invalid policy %s: The unset action on present state can be "
                "either of 'reuse', 'force'." % state_params["unset_mode"]
            )

        if state_params["unset_state"] in ROOTS:
            state_backend.unset_root(state_params, state_object)
        else:
            state_backend.unset(state_params, state_object)


def push_states(run_params: Params, env: Env = None) -> None:
    """
    Identical to the set operation but used within the push/pop pair.

    :param run_params: configuration parameters
    """
    for state_params in _parametric_object_iteration(run_params):
        params_obj_name = state_params["object_name"]
        params_obj_type = state_params["object_type"]

        if not state_params.get("push_state"):
            continue
        else:
            state = state_params["push_state"]
        if state in ROOTS:
            # cannot be done with root states
            continue

        # restrict parametric objects of this type in the subroutine
        composite_types = params_obj_type.split("/")
        composite_names = params_obj_name.split("/")
        for composite_type, composite_name in zip(composite_types, composite_names):
            state_params[composite_type] = composite_name
        state_params["states_chain"] = composite_types[-1]

        state_params["set_state"] = state_params["push_state"]
        state_params["set_mode"] = state_params.get("push_mode", "af")

        set_states(state_params, env)


def pop_states(run_params: Params, env: Env = None) -> None:
    """
    Retrieve and remove a state/snapshot.

    :param run_params: configuration parameters
    """
    for state_params in _parametric_object_iteration(run_params):
        params_obj_name = state_params["object_name"]
        params_obj_type = state_params["object_type"]

        if not state_params.get("pop_state"):
            continue
        else:
            state = state_params["pop_state"]
        if state in ROOTS:
            # cannot be done with root states
            continue

        # restrict parametric objects of this type in the subroutine
        composite_types = params_obj_type.split("/")
        composite_names = params_obj_name.split("/")
        for composite_type, composite_name in zip(composite_types, composite_names):
            state_params[composite_type] = composite_name
        state_params["states_chain"] = composite_types[-1]

        state_params["get_state"] = state_params["pop_state"]
        state_params["get_mode"] = state_params.get("pop_mode", "ra")
        get_states(state_params, env)

        state_params["unset_state"] = state_params["pop_state"]
        state_params["unset_mode"] = state_params.get("pop_mode", "fa")
        unset_states(state_params, env)
