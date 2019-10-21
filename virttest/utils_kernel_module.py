import os
import os.path
import pickle
import logging

from avocado.utils import process
from avocado.core import exceptions

"""Handle Linux kernel modules"""


class KernelModuleHandler(object):
    """Class handling Linux kernel modules"""

    def __init__(self, module_name, persistence_file=""):
        """
        Create kernel module handler. It backs up the current status
        of the kernel module or get its current status from a backed up
        file.

        :param module_name:
        :param persistence_file: absolute file path to store object in
        """
        self._module_name = module_name
        self._was_loaded = None
        self._loaded_config = ""
        self._config_backup = ""
        self._persistence_file = persistence_file
        if os.path.isfile(self._persistence_file):
            self._load()
        else:
            self._backup_config()

    def load_module(self, force=True, params=""):
        """
        Load module with given parameters

        :param force: Force load if currently not loaded. Default is True as
        restore undoes loading.
        :param params: Parameters to load with, 'key1=param1 key2=param2 ...'
        """

        if params == self._loaded_config:
            logging.debug("Not reloading module, same parameters requested for"
                          " module %s: %s" % (self._module_name, params))
            return

        if not force and not self._was_loaded:
            logging.debug("Module %s isn't loaded. Set force=True to force"
                          " loading." % self._module_name)
        else:
            cmd = ""
            if self._was_loaded:
                cmd += 'rmmod %s; ' % self._module_name
            cmd += 'modprobe %s %s' % (self._module_name, params)
            logging.debug("Loading module: %s" % cmd)
            status, output = process.getstatusoutput(cmd, shell=True,
                                                     ignore_status=True)
            if status:
                raise exceptions.TestError("Couldn't load module %s: %s" % (
                    self._module_name, output
                ))
            else:
                self._loaded_config = params

        if self._persistence_file:
            self.save()

    def restore(self):
        """Restore previous module state"""

        if self._loaded_config:
            if not self._was_loaded:
                cmd = 'rmmod %s' % self._module_name
            else:
                cmd = 'rmmod %s; modprobe %s %s' % (self._module_name,
                                                    self._module_name,
                                                    self._config_backup)
            logging.debug("Restoring module state: %s" % cmd)
            status, output = process.getstatusoutput(cmd, shell=True,
                                                     ignore_status=True)
            if status:
                raise exceptions.TestError("Couldn't restore module %s: %s" % (
                    self._module_name, self._config_backup))

        if self._persistence_file and \
                os.path.isfile(self._persistence_file):
            os.remove(self._persistence_file)

    def _backup_config(self):
        """
        Check if self.module_name is loaded and read config

        """
        config = KernelModuleHandler._load_config(self._module_name)
        if config:
            self._config_backup = " ".join("%s=%s" % _ for _ in config.items())
            self._was_loaded = True
        else:
            self._was_loaded = False
        logging.debug("Backed up %s module state (was_loaded, params)"
                      "=(%s, %s)" % (self._module_name, self._was_loaded,
                                     self._config_backup))

    def _load(self):
        try:
            with open(self._persistence_file, 'rb') as pickled:
                self.__dict__.update(pickle.load(pickled))
        except pickle.UnpicklingError as e:
            logging.debug("Failed to unpickle kernel module helper for %s"
                          " from %s:%s" % (self._module_name,
                                           self._persistence_file,
                                           e))

    def save(self):
        try:
            with open(self._persistence_file, 'wb') as pickled:
                pickle.dump(self.__dict__, pickled)
        except pickle.PickleError as e:
            logging.debug("Failed to pickle kernel module helper for %s to %s"
                          ":%s" % (self._module_name, self._persistence_file, e))

    def get_was_loaded(self):
        """ Read-only property """

        return self._was_loaded

    def get_config_backup(self):
        """ Read-only property """

        return self._config_backup

    @staticmethod
    def _load_config(module_name):
        """
        Get current module parameters

        :return: Dictionary holding module config {param:value, ...}, None if
         module not loaded
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
