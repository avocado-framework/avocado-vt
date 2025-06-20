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
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>

"""
Manages the dynamic loading and registration of vt_agent services.

This module provides functionality to discover Python modules within a specified
service directory, import them, and make them available for registration
with the RPC server. It handles potential errors during service loading
to ensure the agent remains robust.
"""

import importlib
import importlib.util
import logging
import os
import sys

# pylint: disable=E0611
from avocado_vt.agent.core import data_dir
from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME

LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)


class ServiceError(Exception):
    """Custom exception for service-related errors."""

    pass


class _Services(object):
    """
    A container for managing registered service modules.

    This class holds a collection of service modules, mapping a registration
    name to the imported service module object. It allows iteration over
    these services for registration with the RPC server.
    """

    def __init__(self):
        """Initializes the service registry."""
        self._services = {}

    def register_service(self, name, service_module):
        """
        Registers a service module with a given name.

        :param name: The name to register the service under (e.g., "examples.hello").
        :type name: str
        :param service_module: The imported service module object.
        :type service_module: module
        """
        self._services[name] = service_module

    def get_service(self, name):
        """
        Retrieves a registered service module by its name.

        :param name: The name of the service to retrieve.
        :type name: str
        :return: The service module object.
        :rtype: module
        :raises ServiceError: If no service with the given name is found.
        """
        try:
            return self._services[name]
        except KeyError as e:
            raise ServiceError(f"No supported service '{name}'.") from e

    def __iter__(self):
        """Iterates over registered services, yielding (name, service_module) pairs."""
        for name, service_module in self._services.items():
            yield name, service_module


def _import_services(services_dir_path):
    """
    Discovers and imports Python modules from the given services directory.

    Recursively walks the `services_dir_path`, imports valid Python files
    (excluding `__init__.py`), and handles potential import errors gracefully.

    :param services_dir_path: Absolute path to the directory containing service modules.
    :type services_dir_path: str
    :return: A list of successfully imported service module objects.
    :rtype: list
    """
    service_sources = []
    for root, dirs, files in os.walk(services_dir_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file_name in files:
            if (
                not file_name.startswith(".")
                and file_name.endswith(".py")
                and file_name != "__init__.py"
            ):
                full_path = os.path.join(root, file_name)
                service_sources.append(full_path)

    imported_modules = []
    for source_path in service_sources:
        module_spec_name = source_path.replace(os.sep, ".")
        if module_spec_name.endswith(".py"):
            module_spec_name = module_spec_name[:-3]

        if module_spec_name.startswith("."):
            module_spec_name = module_spec_name.lstrip(".")

        module_to_load = None
        spec_for_module = None

        try:
            spec_for_module = importlib.util.spec_from_file_location(
                module_spec_name, source_path
            )
            if spec_for_module is None:
                LOG.warning("Failed to create module spec for %s", source_path)
                continue

            if spec_for_module.name in sys.modules:
                continue

            module_to_load = importlib.util.module_from_spec(spec_for_module)
            sys.modules[spec_for_module.name] = module_to_load
            spec_for_module.loader.exec_module(module_to_load)
            imported_modules.append(module_to_load)
        except Exception as e:
            LOG.error(
                "Exception loading service module %s from %s: %s",
                module_spec_name,
                source_path,
                e,
                exc_info=True,
            )
            if (
                spec_for_module
                and spec_for_module.name in sys.modules
                and sys.modules[spec_for_module.name] is module_to_load
            ):
                del sys.modules[spec_for_module.name]

    return imported_modules


def load_services():
    """
    Loads all service modules from the configured services directory.

    It discovers Python files, imports them, and registers them using a
    name derived from their file path relative to the services directory.

    :return: An _Services object populated with the loaded services.
    :rtype: _Services
    """
    services_obj = _Services()
    services_dir_path = data_dir.get_services_module_dir()

    if not os.path.isdir(services_dir_path):
        LOG.warning(
            "Services directory '%s' not found. No external services will be loaded.",
            services_dir_path,
        )
        return services_obj

    imported_service_modules = _import_services(services_dir_path)

    for service_module in imported_service_modules:
        try:
            module_file_path = service_module.__file__
            relative_path = os.path.relpath(module_file_path, services_dir_path)
            service_reg_name = os.path.splitext(relative_path)[0].replace(os.sep, ".")

            if not service_reg_name or service_reg_name.startswith("."):
                LOG.warning(
                    "Could not determine a valid registration name for service "
                    "module %s (path: %s). Skipping.",
                    service_module.__name__,
                    module_file_path,
                )
                continue

            services_obj.register_service(service_reg_name, service_module)
        except Exception as e:
            LOG.error(
                "Error processing service module %s for registration: %s",
                (
                    service_module.__name__
                    if hasattr(service_module, "__name__")
                    else "UnknownModule"
                ),
                e,
                exc_info=True,
            )

    return services_obj
