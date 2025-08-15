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
# Copyright: Red Hat Inc. 2024
# Authors: Yongxue Hong <yhong@redhat.com>

import importlib
import importlib.util
import logging
import os
import sys

from .data_dir import get_managers_module_dir, get_service_module_dir


class ServiceError(Exception):
    pass


LOG = logging.getLogger("avocado.agent." + __name__)


class _Services(object):
    """The representation of the services."""

    def __init__(self):
        self._services = {}

    def register_service(self, name, service):
        self._services[name] = service

    def get_service(self, name):
        try:
            return self._services[name]
        except KeyError:
            raise ServiceError("No support service '%s'." % name)

    def __iter__(self):
        for name, service in self._services.items():
            yield name, service


def _import_services(services_dir):
    """Import all the services."""
    service_sources = []
    for root, dirs, files in os.walk(services_dir):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                service_sources.append(os.path.join(root, file))

    modules = []
    for source in service_sources:
        module_name = source[:-3]
        spec = importlib.util.spec_from_file_location(module_name, source)
        if spec is None:
            raise ImportError(f"Can not find spec for {module_name} at {source}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def load_services():
    """Load all the services."""
    services = _Services()

    # Import the managers module firstly since we need its instances
    # from __init__ and import it as new module "managers" on the worker node.
    managers_package_path = get_managers_module_dir()
    init_file_path = os.path.join(managers_package_path, "__init__.py")
    spec = importlib.util.spec_from_file_location("managers", init_file_path)
    if spec is None:
        raise ImportError(f"Can not find spec for managers at {init_file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    services_dir = get_service_module_dir()
    modules = _import_services(services_dir)

    for service in modules:
        name = service.__dict__["__name__"]
        name = ".".join(name.split(services_dir)[-1].split("/")[1:])
        services.register_service(name, service)
    return services
