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
import pickle
import pipes
import traceback

from avocado.core import exceptions
from avocado.core import test
from avocado.utils import stacktrace
from avocado.utils import process
from avocado.utils import genio

from virttest import asset
from virttest import error_event
from virttest import bootstrap
from virttest import data_dir
from virttest import env_process
from virttest import funcatexit
from virttest import utils_env
from virttest import utils_params
from virttest import utils_misc
from virttest import version

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


BG_ERR_FILE = "background-error.log"


def cleanup_env(env_filename, env_version):
    """
    Pickable function to initialize and destroy the virttest env
    """
    env = utils_env.Env(env_filename, env_version)
    env.destroy()


class VirtTest(test.Test):

    """
    Minimal test class used to run a virt test.
    """

    env_version = utils_env.get_env_version()

    def __init__(self, methodName='runTest', name=None, params=None,
                 base_logdir=None, job=None, runner_queue=None,
                 vt_params=None):
        """
        :note: methodName, name, base_logdir, job and runner_queue params
               are inherited from test.Test
        :param params: avocado/multiplexer params stored as
                       `self.avocado_params`.
        :param vt_params: avocado-vt/cartesian_config params stored as
                          `self.params`.
        """
        self.__params_vt = None
        self.__avocado_params = None
        self.bindir = data_dir.get_root_dir()
        self.virtdir = os.path.join(self.bindir, 'shared')
        # self.__params_vt must be initialized after super
        params_vt = utils_params.Params(vt_params)
        # for timeout use Avocado-vt timeout as default but allow
        # overriding from Avocado params (varianter)
        self.timeout = params_vt.get("test_timeout", self.timeout)

        self.iteration = 0
        self.resultsdir = None
        self.background_errors = error_event.error_events_bus
        # clear existing error events
        self.background_errors.clear()
        super(VirtTest, self).__init__(methodName=methodName, name=name,
                                       params=params,
                                       base_logdir=base_logdir, job=job,
                                       runner_queue=runner_queue)
        self.builddir = os.path.join(self.workdir, 'backends',
                                     vt_params.get("vm_type", ""))
        self.tmpdir = os.path.dirname(self.workdir)
        # Move self.params to self.avocado_params and initialize virttest
        # (cartesian_config) params
        try:
            self.__avocado_params = super(VirtTest, self).params
        except AttributeError:
            # 36LTS set's `self.params` instead of having it as a property
            # which stores the avocado params in `self.__params`
            self.__avocado_params = self.__params
        self.__params_vt = params_vt
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
        if self.__params_vt is not None:
            return self.__params_vt
        else:
            # The `self.__params` is set after the `avocado.test.__init__`,
            # but in newer Avocado `self.params` is used during `__init__`
            # Report the parent's value in such case.
            return super(VirtTest, self).params

    @params.setter
    def params(self, value):
        """
        For compatibility with 36lts we need to support setter on params
        """
        self.__params_vt = value

    @property
    def avocado_params(self):
        """
        Original Avocado (multiplexer/varianter) params
        """
        return self.__avocado_params

    @property
    def datadir(self):
        """
        Returns the path to the directory that contains test data files

        For VT tests, this always returns None. The reason is that
        individual VT tests do not map 1:1 to a file and do not provide
        the concept of a datadir.
        """
        return None

    @property
    def filename(self):
        """
        Returns the name of the file (path) that holds the current test

        For VT tests, this always returns None. The reason is that
        individual VT tests do not map 1:1 to a file.
        """
        return None

    def get_state(self):
        """
        Pre Avocado-60.0 used to override self.__params attribute and
        requires special handling while reporting the state.

        TODO: Remove when 52LTS is deprecated.
        """
        state = super(VirtTest, self).get_state()
        if state["params"] == self.__params_vt:
            state["params"] = self.avocado_params
        return state

    def write_test_keyval(self, d):
        self.whiteboard = str(d)

    def verify_background_errors(self):
        """
        Verify if there are any errors that happened on background threads.
        Logs all errors in the background_errors into background-error.log and
        error the test.
        """
        err_file_path = os.path.join(self.logdir, BG_ERR_FILE)
        bg_errors = self.background_errors.get_all()
        error_messages = ["BACKGROUND ERROR LIST:"]
        for index, error in enumerate(bg_errors):
            error_messages.append(
                "- ERROR #%d -\n%s" % (index, "".join(
                    traceback.format_exception(*error)
                    )))
        genio.write_file(err_file_path, '\n'.join(error_messages))
        if bg_errors:
            msg = ["Background error"]
            msg.append("s are" if len(bg_errors) > 1 else " is")
            msg.append((" detected, please refer to file: "
                        "'%s' for more details.") % BG_ERR_FILE)
            self.error(''.join(msg))

    def __safe_env_save(self, env):
        """
        Treat "env.save()" exception as warnings

        :param env: The virttest env object
        :return: True on failure
        """
        try:
            env.save()
        except Exception as details:
            try:
                pickle.dumps(env.data)
            except Exception:
                self.log.warn("Unable to save environment: %s",
                              stacktrace.str_unpickable_object(env.data))
            else:
                self.log.warn("Unable to save environment: %s (%s)", details,
                              env.data)
            return True
        return False

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

        # If a dependency test prior to this test has failed, let's fail
        # it right away as TestNA.
        if params.get("dependency_failed") == 'yes':
            raise exceptions.TestSkipError("Test dependency failed")

        # Report virt test version
        logging.info(version.get_pretty_version_info())
        # Report the parameters we've received and write them as keyvals
        logging.debug("Test parameters:")
        keys = list(params.keys())
        keys.sort()
        for key in keys:
            logging.debug("    %s = %s", key, params[key])

        # Warn of this special condition in related location in output & logs
        if os.getuid() == 0 and params.get('nettype', 'user') == 'user':
            logging.warning("")
            logging.warning("Testing with nettype='user' while running "
                            "as root may produce unexpected results!!!")
            logging.warning("")

        # Find the test
        subtest_dirs = []
        test_filter = bootstrap.test_filter

        other_subtests_dirs = params.get("other_tests_dirs", "")
        for d in other_subtests_dirs.split():
            # If d starts with a "/" an absolute path will be assumed
            # else the relative path will be searched in the bin_dir
            subtestdir = os.path.join(self.bindir, d, "tests")
            if not os.path.isdir(subtestdir):
                raise exceptions.TestError("Directory %s does not "
                                           "exist" % subtestdir)
            subtest_dirs += data_dir.SubdirList(subtestdir,
                                                test_filter)

        provider = params.get("provider", None)

        if provider is None:
            # Verify if we have the correspondent source file for
            # it
            generic_subdirs = asset.get_test_provider_subdirs(
                'generic')
            for generic_subdir in generic_subdirs:
                subtest_dirs += data_dir.SubdirList(generic_subdir,
                                                    test_filter)
            specific_subdirs = asset.get_test_provider_subdirs(
                params.get("vm_type"))
            for specific_subdir in specific_subdirs:
                subtest_dirs += data_dir.SubdirList(
                    specific_subdir, bootstrap.test_filter)
        else:
            provider_info = asset.get_test_provider_info(provider)
            for key in provider_info['backends']:
                subtest_dirs += data_dir.SubdirList(
                    provider_info['backends'][key]['path'],
                    bootstrap.test_filter)

        subtest_dir = None

        # Get the test routine corresponding to the specified
        # test type
        logging.debug("Searching for test modules that match "
                      "'type = %s' and 'provider = %s' "
                      "on this cartesian dict",
                      params.get("type"),
                      params.get("provider", None))

        t_types = params.get("type").split()
        # Make sure we can load provider_lib in tests
        for s in subtest_dirs:
            if os.path.dirname(s) not in sys.path:
                sys.path.insert(0, os.path.dirname(s))

        test_modules = {}
        for t_type in t_types:
            for d in subtest_dirs:
                module_path = os.path.join(d, "%s.py" % t_type)
                if os.path.isfile(module_path):
                    logging.debug("Found subtest module %s",
                                  module_path)
                    subtest_dir = d
                    break
            if subtest_dir is None:
                msg = ("Could not find test file %s.py on test"
                       "dirs %s" % (t_type, subtest_dirs))
                raise exceptions.TestError(msg)
            # Load the test module
            f, p, d = imp.find_module(t_type, [subtest_dir])
            test_modules[t_type] = imp.load_module(t_type, f, p, d)
            f.close()

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
                        self.__safe_env_save(env)

                    # Run the test function
                    for t_type in t_types:
                        test_module = test_modules[t_type]
                        run_func = utils_misc.get_test_entrypoint_func(
                            t_type, test_module)
                        try:
                            run_func(self, params, env)
                            self.verify_background_errors()
                        finally:
                            self.__safe_env_save(env)
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
                        self.__safe_env_save(env)
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
                    if self.__safe_env_save(env) or params.get("env_cleanup", "no") == "yes":
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
