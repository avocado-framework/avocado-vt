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
# Copyright: Red Hat Inc. 2015
# Author: Lucas Meneghel Rodrigues <lmr@redhat.com>

"""
Avocado VT plugin
"""

import imp
import logging
import os
import sys
import pipes

from avocado.core import exceptions
from avocado.core import test
from avocado.utils import stacktrace
from avocado.utils import process

from virttest import error_event
from virttest import data_dir
from virttest import env_process
from virttest import funcatexit
from virttest import utils_env
from virttest import utils_params
from virttest import utils_misc
from virttest import version

from avocado_vt import utils


# avocado-vt no longer needs autotest for the majority of its functionality,
# except by:
# 1) Run autotest on VMs
# 2) Multi host migration
# 3) Proper avocado-vt test status handling
# As in those cases we might want to use autotest, let's have a way for
# users to specify their autotest from a git clone location.
AUTOTEST_PATH = None

if 'AUTOTEST_PATH' in os.environ:
    AUTOTEST_PATH = os.path.expanduser(os.environ['AUTOTEST_PATH'])
    CLIENT_DIR = os.path.join(os.path.abspath(AUTOTEST_PATH), 'client')
    SETUP_MODULES_PATH = os.path.join(CLIENT_DIR, 'setup_modules.py')
    if not os.path.exists(SETUP_MODULES_PATH):
        raise EnvironmentError("Although AUTOTEST_PATH has been declared, "
                               "%s missing." % SETUP_MODULES_PATH)
    SETUP_MODULES = imp.load_source('autotest_setup_modules',
                                    SETUP_MODULES_PATH)
    SETUP_MODULES.setup(base_path=CLIENT_DIR,
                        root_module_name="autotest.client")


def cleanup_env(env_filename, env_version):
    """
    Pickable function to initialize and destroy the virttest env
    """
    env = utils_env.Env(env_filename, env_version)
    env.destroy()


class VirtTest(test.Test, utils.TestUtils):

    """
    Minimal test class used to run a virt test.
    """

    env_version = utils_env.get_env_version()

    def __init__(self, **kwargs):
        """
        :note: methodName, name, base_logdir, job/config and runner_queue
               params are inherited from test.Test
               From the avocado 86 the test.Test uses config instead of job
               instance. Because of the compatibility with avocado 82.0 LTS we
               can't remove the job instance. For avocado < 86 job instance is
               used and for avocado=>86 config is used.
        :param vt_params: avocado-vt/cartesian_config params stored as
                          `self.params`.
        """
        self.__vt_params = None
        self.bindir = data_dir.get_root_dir()
        self.virtdir = os.path.join(self.bindir, 'shared')
        # self.__vt_params must be initialized after super
        vt_params = utils_params.Params(kwargs.pop("vt_params", None))
        # for timeout use Avocado-vt timeout as default but allow
        # overriding from Avocado params (varianter)
        self.timeout = vt_params.get("test_timeout", self.timeout)

        self.iteration = 0
        self.resultsdir = None
        self.background_errors = error_event.error_events_bus
        # clear existing error events
        self.background_errors.clear()

        if "methodName" not in kwargs:
            kwargs["methodName"] = 'runTest'
        super(VirtTest, self).__init__(**kwargs)

        self.builddir = os.path.join(self.workdir, 'backends',
                                     vt_params.get("vm_type", ""))
        self.tmpdir = os.path.dirname(self.workdir)
        self.__vt_params = vt_params
        self.debugdir = self.logdir
        self.resultsdir = self.logdir
        utils_misc.set_log_file_dir(self.logdir)
        self.__status = None
        self.__exc_info = None

    @property
    def params(self):
        """
        Avocado-vt test params

        During `avocado.Test.__init__` this reports the original params but
        once the Avocado-vt params are set it reports those instead. This
        is necessary to complete the `avocado.Test.__init__` phase
        """
        if self.__vt_params is not None:
            return self.__vt_params
        else:
            # The `self.__params` is set after the `avocado.test.__init__`,
            # but in newer Avocado `self.params` is used during `__init__`
            # Report the parent's value in such case.
            return super(VirtTest, self).params

    def setUp(self):
        """
        Avocado-vt uses custom setUp/test/tearDown handling and unlike
        Avocado it allows skipping tests from any phase. To convince
        Avocado to allow skips let's say our tests run during setUp
        phase and report the status in test.
        """
        env_lang = os.environ.get('LANG')
        os.environ['LANG'] = 'C'
        try:
            self._runTest()
            self.__status = "PASS"
        # This trick will give better reporting of virt tests being executed
        # into avocado (skips, warns and errors will display correctly)
        except exceptions.TestSkipError:
            self.__exc_info = sys.exc_info()
            raise   # This one has to be raised in setUp
        except:  # nopep8 Old-style exceptions are not inherited from Exception()
            self.__exc_info = sys.exc_info()
            self.__status = self.__exc_info[1]
        finally:
            # Clean libvirtd debug logs if the test is not fail or error
            if self.params.get("libvirtd_log_cleanup", "no") == "yes":
                if(self.params.get("vm_type") == 'libvirt' and
                   self.params.get("enable_libvirtd_debug_log", "yes") == "yes"):
                    libvirtd_log = self.params["libvirtd_debug_file"]
                    if("TestFail" not in str(self.__exc_info) and
                       "TestError" not in str(self.__exc_info)):
                        if libvirtd_log and os.path.isfile(libvirtd_log):
                            logging.info("cleaning libvirtd logs...")
                            os.remove(libvirtd_log)
                    else:
                        # tar the libvirtd log and archive
                        logging.info("archiving libvirtd debug logs")
                        from virttest import utils_package
                        if utils_package.package_install("tar"):
                            if os.path.isfile(libvirtd_log):
                                archive = os.path.join(os.path.dirname(
                                    libvirtd_log), "libvirtd.tar.gz")
                                cmd = ("tar -zcf %s -P %s"
                                       % (pipes.quote(archive),
                                          pipes.quote(libvirtd_log)))
                                if process.system(cmd) == 0:
                                    os.remove(libvirtd_log)
                            else:
                                logging.error("Unable to find log file: %s",
                                              libvirtd_log)
                        else:
                            logging.error("Unable to find tar to compress libvirtd "
                                          "logs")

            if env_lang:
                os.environ['LANG'] = env_lang
            else:
                del os.environ['LANG']

    def runTest(self):
        """
        This only reports the results

        The actual testing happens inside setUp stage, this only
        reports the correct results
        """
        if self.__status != "PASS":
            raise self.__status  # pylint: disable=E0702

    def _runTest(self):
        params = self.params
        if params.get("test_pre_hook"):
            self.log.info(f"Executing VT test pre-hook from {params['test_pre_hook']}")
            with open(params["test_pre_hook"]) as f:
                exec(f.read())

        # Report virt test version
        logging.info(version.get_pretty_version_info())
        self._log_parameters()

        # Warn of this special condition in related location in output & logs
        if os.getuid() == 0 and params.get('nettype', 'user') == 'user':
            logging.warning("")
            logging.warning("Testing with nettype='user' while running "
                            "as root may produce unexpected results!!!")
            logging.warning("")

        subtest_dirs = self._get_subtest_dirs()

        # Get the test routine corresponding to the specified
        # test type
        logging.debug("Searching for test modules that match "
                      "'type = %s' and 'provider = %s' "
                      "on this cartesian dict",
                      params.get("type"),
                      params.get("provider", None))

        t_types = params.get("type").split()

        utils.insert_dirs_to_path(subtest_dirs)

        test_modules = utils.find_test_modules(t_types, subtest_dirs)

        # Open the environment file
        env_filename = os.path.join(data_dir.get_tmp_dir(),
                                    params.get("env", "env"))
        env = utils_env.Env(env_filename, self.env_version)
        if params.get_boolean("job_env_cleanup", "yes"):
            self.runner_queue.put({"func_at_exit": cleanup_env,
                                   "args": (env_filename, self.env_version),
                                   "once": True})

        test_passed = False
        t_type = None

        try:
            try:
                try:
                    # Pre-process
                    try:
                        params = env_process.preprocess(self, params, env)
                    finally:
                        self._safe_env_save(env)

                    # Run the test function
                    for t_type in t_types:
                        test_module = test_modules[t_type]
                        run_func = utils_misc.get_test_entrypoint_func(
                            t_type, test_module)
                        try:
                            run_func(self, params, env)
                            self.verify_background_errors()
                        finally:
                            self._safe_env_save(env)
                    test_passed = True
                    error_message = funcatexit.run_exitfuncs(env, t_type)
                    if error_message:
                        raise exceptions.TestWarn("funcatexit failed with: %s" %
                                                  error_message)

                except:  # nopep8 Old-style exceptions are not inherited from Exception()
                    stacktrace.log_exc_info(sys.exc_info(), 'avocado.test')
                    if t_type is not None:
                        error_message = funcatexit.run_exitfuncs(env, t_type)
                        if error_message:
                            logging.error(error_message)
                    try:
                        env_process.postprocess_on_error(self, params, env)
                    finally:
                        self._safe_env_save(env)
                    raise

            finally:
                # Post-process
                try:
                    try:
                        params['test_passed'] = str(test_passed)
                        env_process.postprocess(self, params, env)
                    except:  # nopep8 Old-style exceptions are not inherited from Exception()

                        stacktrace.log_exc_info(sys.exc_info(),
                                                'avocado.test')
                        if test_passed:
                            raise
                        logging.error("Exception raised during "
                                      "postprocessing: %s",
                                      sys.exc_info()[1])
                finally:
                    if self._safe_env_save(env) or params.get("env_cleanup", "no") == "yes":
                        env.destroy()   # Force-clean as it can't be stored

        except Exception as e:
            if params.get("abort_on_error") != "yes":
                raise
            # Abort on error
            logging.info("Aborting job (%s)", e)
            if params.get("vm_type") == "qemu":
                for vm in env.get_all_vms():
                    if vm.is_dead():
                        continue
                    logging.info("VM '%s' is alive.", vm.name)
                    for m in vm.monitors:
                        logging.info("It has a %s monitor unix socket at: %s",
                                     m.protocol, m.filename)
                    logging.info("The command line used to start it was:\n%s",
                                 vm.make_create_command())
                raise exceptions.JobError("Abort requested (%s)" % e)

        return test_passed
