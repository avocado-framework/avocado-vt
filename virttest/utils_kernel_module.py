import os
import logging

from avocado.utils import process
from avocado.core import exceptions

"""Handle Linux kernel modules"""


class KernelModuleHandler(object):
    """Class handling Linux kernel modules"""

    def __init__(self, module_name):
        self._module_name = module_name
        self._was_loaded = True
        self._config_backup = ""
        self._backup_config()

    def load_module(self, force=True, params=""):
        """
        Load module with given parameters

        :param force: Force load if currently not loaded. Default is True as restore undoes loading.
        :param params: Parameters to load with, 'key1=param1 key2=param2 ...'
        """

        if not force and not self._was_loaded:
            logging.info("Module %s isn't loaded. Set force=True to force loading." % self._module_name)
        else:
            cmd = ""
            if self._was_loaded:
                cmd += 'rmmod %s; ' % self._module_name
            cmd += 'modprobe %s %s' % (self._module_name, params)
            logging.debug("Loading module: %s" % cmd)
            status, output = process.getstatusoutput(cmd, shell=True, ignore_status=True)
            if status:
                raise exceptions.TestError("Couldn't load module %s: %s" % (
                    self._module_name, output
                ))

    def restore(self):
        """Restore previous module state"""

        if not self._was_loaded:
            cmd = 'rmmod %s' % self._module_name
        else:
            cmd = 'rmmod %s; modprobe %s %s' % (self._module_name, self._module_name,
                                                self._config_backup)
        logging.debug("Restoring module state: %s" % cmd)
        status, output = process.getstatusoutput(cmd, shell=True, ignore_status=True)
        if status:
            raise exceptions.TestError("Couldn't restore module %s: %s" % (
                self._module_name, self._config_backup))

    def _backup_config(self):
        """
        Check if self.module_name is loaded and read config

        """
        config = KernelModuleHandler._load_config(self._module_name)
        if config:
            self._config_backup = KernelModuleHandler._to_line(config)
        else:
            self._was_loaded = False
        logging.debug("Backed up %s module state (was_loaded, params)"
                      "=(%s, %s)" % (self._module_name, self._was_loaded,
                                     self._config_backup))

    def get_was_loaded(self):
        """ Read-only property """

        return self._was_loaded

    def get_config_backup(self):
        """ Read-only property """

        return self._config_backup

    @staticmethod
    def _to_line(as_dict):
        """
        Write dictionary in one line

        :param as_dict: dictionary holding values {key1:value1, key2:value2, ...}
        :return: string holding values 'key1=value1 key2=value2 ...'
        """
        s = ""
        if as_dict and len(as_dict) > 0:
            p = " %s=%s"
            for k in as_dict:
                s += p % (k, as_dict[k])
        return s.strip()

    @staticmethod
    def _load_config(module_name):
        """
        Get current kvm module parameters

        :return: Dictionary holding kvm module config {param:value, ...}, None if module not loaded
        """

        mod_params_path = '/sys/module/%s/parameters/' % module_name
        if not os.path.exists(mod_params_path):
            return None

        mod_params = {}
        params = os.listdir(mod_params_path)
        for param in params:
            with open(os.path.join(mod_params_path, param), 'r') as v:
                mod_params[param] = v.read().strip()
        return mod_params
