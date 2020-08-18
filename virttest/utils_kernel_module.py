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
# Copyright: Red Hat Inc. 2020
# Author: Sebastian Mitterle <smitterl@redhat.com>

"""
Handle Linux kernel modules
"""

import os
import logging

from avocado.utils import process


class KernelModuleError(Exception):

    def __init__(self, handler, module_name, reason):
        self.handler = handler
        self.module_name = module_name
        self.reason = reason

    def __str__(self):
        return "Couldn't %s module %s: %s" % (self.handler, self.module_name,
                                              self.reason)


class KernelModuleUnloadError(KernelModuleError):

    def __init__(self, module_name, reason):
        super(KernelModuleUnloadError, self).__init__("unload", module_name,
                                                      reason)


class KernelModuleReloadError(KernelModuleError):

    def __init__(self, module_name, reason):
        super(KernelModuleReloadError, self).__init__("reload", module_name,
                                                      reason)


class KernelModuleRestoreError(KernelModuleError):

    def __init__(self, module_name, reason):
        super(KernelModuleRestoreError, self).__init__("restore", module_name,
                                                       reason)


def reload(module_name, force, params=""):
    """
    Convenience method that creates a KernelModuleHandler instance
    and reloads the module only if any action will is required.

    :param module_name: name of kernel module to be handled
    :param force: if to force load with params in any case, e.g. True
    :param params: parameters to load with, e.g. 'key1=param1 ...'
    :return: instance if module was loaded
    """

    if params != "" or force:
        handler = KernelModuleHandler(module_name)
        handler.reload_module(force, params)
        return handler
    return None


class KernelModuleHandler(object):
    """Class handling Linux kernel modules"""

    def __init__(self, module_name):
        """Create kernel module handler"""

        self._module_name = module_name
        self._module_path = os.path.join('/sys/module/',
                                         self._module_name.replace('-', '_'))
        self._module_params_path = os.path.join(self._module_path, 'parameters')
        self._module_holders_path = os.path.join(self._module_path, "holders")
        self._was_loaded = None
        self._config_backup = None
        self._backup_config()

    def unload_module(self):
        """
        Unload module and those modules that use it.

        If there are some modules using this module, they are unloaded first.
        """
        if os.path.exists(self._module_path):
            unload_cmd = 'rmmod ' + self._module_name
            logging.debug("Unloading module: %s", unload_cmd)
            status, output = process.getstatusoutput(unload_cmd)
            if status:
                raise KernelModuleUnloadError(self._module_name, output)

    def reload_module(self, force, params=""):
        """
        Reload module with given parameters.

        If force=False loading will be skipped when either the module is
        already loaded with the passed parameters or when the module has
        not been loaded at all.

        +----------------------+-+-+-+-+-+-+
        |**precondition**                  |
        +----------------------+-+-+-+-+-+-+
        |module loaded         |N|N|Y|Y|Y|Y|
        +----------------------+-+-+-+-+-+-+
        |params already loaded |*|*|Y|N|Y|N|
        +----------------------+-+-+-+-+-+-+
        |force load            |Y|N|Y|Y|N|N|
        +----------------------+-+-+-+-+-+-+
        |**result**                        |
        +----------------------+-+-+-+-+-+-+
        |issue reload          |Y|N|Y|Y|N|Y|
        +----------------------+-+-+-+-+-+-+

        :param force: if to force load with params in any case, e.g. True
        :param params: parameters to load with, e.g. 'key1=param1 ...'
        """

        current_config = self.current_config
        if not force:
            do_not_load = False
            if (current_config and
                    all(x in current_config.split() for x in params.split())):
                logging.debug("Not reloading module. Current module config"
                              " uration for %s already contains all reques"
                              " ted parameters. Requested: '%s'. Current:"
                              " '%s'. Use force=True to force loading.",
                              self._module_name, params, current_config)
                do_not_load = True
            elif not self._was_loaded:
                logging.debug("Module %s isn't loaded. Use force=True to force"
                              " loading.", self._module_name)
                do_not_load = True
            if do_not_load:
                return

        # TODO: Handle cases were module cannot be removed
        holders = self.module_holders
        for holder in holders:
            holder.unload_module()
        self.unload_module()
        reload_cmd = 'modprobe %s %s' % (self._module_name, params)
        logging.debug("Reloading module: %s", reload_cmd)
        status, output = process.getstatusoutput(reload_cmd.strip())
        if status:
            raise KernelModuleReloadError(self._module_name, output)
        for holder in holders:
            holder.restore()

    def restore(self):
        """
        Restore previous module state.

        The state will only be restored if the original state
        was altered.

        +-------------------+-+-+-+-+
        |**precondition**           |
        +-------------------+-+-+-+-+
        |module loaded      |Y|Y|N|N|
        +-------------------+-+-+-+-+
        |loaded with params |Y|N|Y|N|
        +-------------------+-+-+-+-+
        |**result**                 |
        +-------------------+-+-+-+-+
        |issue restore      |Y|N|Y|N|
        +-------------------+-+-+-+-+
        """

        if self.current_config != self._config_backup:
            # TODO: Handle cases were module cannot be removed
            holders = self.module_holders
            for holder in holders:
                holder.unload_module()
            self.unload_module()
            if self._was_loaded:
                restore_cmd = 'modprobe %s %s' % (self._module_name,
                                                  self._config_backup)
                logging.debug("Restoring module state: %s", restore_cmd)
                status, output = process.getstatusoutput(restore_cmd)
                if status:
                    raise KernelModuleRestoreError(self._module_name,
                                                   output)
            for holder in holders:
                holder.restore()

    def _backup_config(self):
        """
        Check if self.module_name is loaded and read config

        """
        config = self._get_serialized_config()
        if config is not None:
            self._config_backup = config
            self._was_loaded = True
        else:
            self._was_loaded = False
        logging.debug("Backed up %s module state (was_loaded, params)"
                      "=(%s, %s)", self._module_name, self._was_loaded,
                      self._config_backup)

    @property
    def was_loaded(self):
        """ Read-only property """

        return self._was_loaded

    @property
    def config_backup(self):
        """ Read-only property """

        return self._config_backup

    @property
    def current_config(self):
        """ Read-only property """

        return self._get_serialized_config()

    def _get_serialized_config(self):
        """
        Get current module parameters

        :return: String holding module config 'param1=value1 param2=value2 ...', None if
         module not loaded
        """

        if not os.path.exists(self._module_params_path):
            return None

        mod_params = {}
        params = os.listdir(self._module_params_path)
        for param in params:
            with open(os.path.join(self._module_params_path,
                                   param), 'r') as param_file:
                mod_params[param] = param_file.read().strip()
        return " ".join("%s=%s" % _ for _ in mod_params.items()) if mod_params else ""

    @property
    def module_holders(self):
        """Find out which modules use this module."""
        if os.path.exists(self._module_holders_path):
            module_used_by = os.listdir(self._module_holders_path)
            return [KernelModuleHandler(module) for module in module_used_by]
        return []
