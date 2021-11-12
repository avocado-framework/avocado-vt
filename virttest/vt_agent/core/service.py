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
# Copyright: Red Hat Inc. 2022
# Authors: Yongxue Hong <yhong@redhat.com>

import logging
import os

try:
    import imp
except ModuleNotFoundError:
    import importlib as imp


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


def load_services():
    """Load all the services."""
    services = _Services()
    basedir = os.path.dirname(os.path.dirname(__file__))
    service_dir = os.path.join(basedir, "services")
    service_mods = []
    for root, dirs, files in os.walk(service_dir):
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                service_mods.append(os.path.join(root, file[:-3]))

    modules = []
    for service in service_mods:
        f, p, d = imp.find_module(service)
        modules.append(imp.load_module(service, f, p, d))
        f.close()

    for service in modules:
        name = service.__dict__["__name__"]
        name = ".".join(name.split(basedir + "/")[-1].split("/")[1:])
        services.register_service(name, service)
    return services
